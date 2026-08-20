"""Surface runtime font diagnostics through the application Message Bar."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
import logging
import re
import sys
import warnings
import weakref

from PySide6.QtCore import QObject, QTimer, Signal, Slot, qInstallMessageHandler

from mygui import status_messages


_DECIMAL_GLYPH_RE = re.compile(r"\bGlyph\s+(\d+)\b", re.IGNORECASE)
_HEX_GLYPH_RE = re.compile(r"\[U\+([0-9A-F]+)\]", re.IGNORECASE)
_DIRECTWRITE_FONT_RE = re.compile(
    r'DirectWrite:\s*CreateFontFaceFromHDC\(\)\s+failed.*?'
    r'QFontDef\(Family="([^"]+)"',
    re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class FontDiagnosticNotice:
    """One normalized, deduplicatable user-facing font diagnostic."""

    key: str
    message: str


class FontDiagnosticCapture:
    """Collect normalized diagnostics emitted during one render probe."""

    def __init__(self) -> None:
        self._notices: dict[str, FontDiagnosticNotice] = {}

    @property
    def notices(self) -> tuple[FontDiagnosticNotice, ...]:
        """Return unique diagnostics in their original emission order."""

        return tuple(self._notices.values())

    def report(self, message: object) -> bool:
        """Collect one supported diagnostic without publishing it globally."""

        notice = normalize_font_diagnostic(message)
        if notice is None:
            return False
        self._notices.setdefault(notice.key, notice)
        return True


_ACTIVE_CAPTURE: ContextVar[FontDiagnosticCapture | None] = ContextVar(
    "mygui_active_font_diagnostic_capture",
    default=None,
)


def normalize_font_diagnostic(message: object) -> FontDiagnosticNotice | None:
    """Normalize supported Matplotlib and Qt font diagnostics."""

    text = str(message)
    normalized = text.casefold()
    glyph_match = None
    if "missing from font" in normalized:
        glyph_match = _DECIMAL_GLYPH_RE.search(text)
    elif "does not have a glyph" in normalized:
        glyph_match = _HEX_GLYPH_RE.search(text)
    if glyph_match is not None:
        try:
            if glyph_match.re is _DECIMAL_GLYPH_RE:
                codepoint = int(glyph_match.group(1), 10)
            else:
                codepoint = int(glyph_match.group(1), 16)
        except (TypeError, ValueError, OverflowError):
            return FontDiagnosticNotice(
                "matplotlib-glyph:unknown",
                "The current font is missing a glyph; affected text may display a placeholder.",
            )
        if 0 <= codepoint <= 0x10FFFF:
            return FontDiagnosticNotice(
                f"matplotlib-glyph:{codepoint:X}",
                (
                    f"The current font is missing glyph U+{codepoint:04X}; "
                    "affected text may display a placeholder."
                ),
            )

    directwrite_match = _DIRECTWRITE_FONT_RE.search(text)
    if directwrite_match is not None:
        family = directwrite_match.group(1).strip() or "unknown"
        return FontDiagnosticNotice(
            f"directwrite-font:{family.casefold()}",
            (
                f'Windows could not load font "{family}"; '
                "a fallback font is being used."
            ),
        )
    return None


def missing_glyph_message(message: object) -> str | None:
    """Return only the user-facing Matplotlib missing-glyph message."""

    notice = normalize_font_diagnostic(message)
    if notice is None or not notice.key.startswith("matplotlib-glyph:"):
        return None
    return notice.message


class _MatplotlibFontLogHandler(logging.Handler):
    """Forward relevant Matplotlib log records without consuming them."""

    def __init__(self, bridge: "FontDiagnosticBridge"):
        super().__init__(level=logging.WARNING)
        self._bridge_ref = weakref.ref(bridge)

    def emit(self, record: logging.LogRecord) -> None:
        bridge = self._bridge_ref()
        if bridge is None:
            return
        try:
            bridge.report(record.getMessage())
        except Exception:
            self.handleError(record)


class _CapturedMatplotlibFontLogHandler(logging.Handler):
    """Collect Matplotlib diagnostics for one synchronous render probe."""

    def __init__(self, capture: FontDiagnosticCapture):
        super().__init__(level=logging.WARNING)
        self._capture = capture

    def emit(self, record: logging.LogRecord) -> None:
        if _ACTIVE_CAPTURE.get() is not self._capture:
            return
        try:
            self._capture.report(record.getMessage())
        except Exception:
            self.handleError(record)


@contextmanager
def capture_font_diagnostics() -> Iterator[FontDiagnosticCapture]:
    """Capture Matplotlib font logs as part of the current business action."""

    capture = FontDiagnosticCapture()
    handler = _CapturedMatplotlibFontLogHandler(capture)
    logger = logging.getLogger("matplotlib")
    token = _ACTIVE_CAPTURE.set(capture)
    logger.addHandler(handler)
    try:
        yield capture
    finally:
        logger.removeHandler(handler)
        _ACTIVE_CAPTURE.reset(token)


class FontDiagnosticBridge(QObject):
    """Bridge supported process-level font warnings onto the Qt GUI thread."""

    noticeReceived = Signal(str, str)

    def __init__(self, parent: QObject | None = None):
        super().__init__(parent)
        self.noticeReceived.connect(self._queue_notice)
        self._pending: dict[str, str] = {}
        self._published_keys: set[str] = set()
        self._flush_scheduled = False
        self._installed = False
        self._original_showwarning = None
        self._previous_qt_handler = None
        self._python_warning_handler = self._showwarning
        self._qt_message_handler = self._handle_qt_message
        self._logging_handler = _MatplotlibFontLogHandler(self)

    def report(self, message: object) -> bool:
        """Queue one recognized font diagnostic for user presentation."""

        notice = normalize_font_diagnostic(message)
        if notice is None:
            return False
        active_capture = _ACTIVE_CAPTURE.get()
        if active_capture is not None:
            active_capture.report(message)
            return True
        self.noticeReceived.emit(notice.key, notice.message)
        return True

    @Slot(str, str)
    def _queue_notice(self, key: str, message: str) -> None:
        if key in self._published_keys:
            return
        self._pending.setdefault(key, message)
        if self._flush_scheduled:
            return
        self._flush_scheduled = True
        QTimer.singleShot(0, self.flush_pending)

    @Slot()
    def flush_pending(self) -> bool:
        """Publish pending unique diagnostics as one yellow Message Bar result."""

        self._flush_scheduled = False
        if not self._pending:
            return False
        entries = tuple(self._pending.items())
        details = " ".join(message for _key, message in entries)
        prefix = "Font warning: " if len(entries) == 1 else "Font warnings: "
        if not status_messages.show_warning(prefix + details):
            return False
        self._published_keys.update(key for key, _message in entries)
        for key, _message in entries:
            self._pending.pop(key, None)
        return True

    def install(self) -> None:
        """Install process hooks while preserving existing console reporting."""

        if self._installed:
            return
        self._original_showwarning = warnings.showwarning
        warnings.showwarning = self._python_warning_handler
        logging.getLogger("matplotlib").addHandler(self._logging_handler)
        self._previous_qt_handler = qInstallMessageHandler(
            self._qt_message_handler
        )
        self._installed = True

    def uninstall(self) -> None:
        """Restore every process hook installed by this bridge."""

        if not self._installed:
            return
        if warnings.showwarning is self._python_warning_handler:
            warnings.showwarning = self._original_showwarning
        logging.getLogger("matplotlib").removeHandler(self._logging_handler)
        current_qt_handler = qInstallMessageHandler(self._previous_qt_handler)
        if current_qt_handler is not self._qt_message_handler:
            qInstallMessageHandler(current_qt_handler)
        self._pending.clear()
        self._flush_scheduled = False
        self._installed = False

    def _showwarning(
        self,
        message,
        category,
        filename,
        lineno,
        file=None,
        line=None,
    ) -> None:
        self.report(message)
        self._original_showwarning(
            message,
            category,
            filename,
            lineno,
            file=file,
            line=line,
        )

    def _handle_qt_message(self, message_type, context, message) -> None:
        self.report(message)
        if self._previous_qt_handler is not None:
            self._previous_qt_handler(message_type, context, message)
            return
        try:
            sys.stderr.write(str(message) + "\n")
            sys.stderr.flush()
        except Exception:
            pass


_RUNTIME_BRIDGE: FontDiagnosticBridge | None = None


def install_font_diagnostic_bridge() -> FontDiagnosticBridge:
    """Install and retain the single application font diagnostic bridge."""

    global _RUNTIME_BRIDGE
    if _RUNTIME_BRIDGE is None:
        _RUNTIME_BRIDGE = FontDiagnosticBridge()
    _RUNTIME_BRIDGE.install()
    return _RUNTIME_BRIDGE


def flush_font_diagnostics() -> bool:
    """Flush startup diagnostics once the Message Bar is available."""

    if _RUNTIME_BRIDGE is None:
        return False
    return _RUNTIME_BRIDGE.flush_pending()
