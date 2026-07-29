"""Share component-editor widgets, status helpers, and data-reference logic."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Any

from Qt_core import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QObject,
    QPlainTextEdit,
    QSignalBlocker,
    QTimer,
    QVBoxLayout,
    QWidget,
    Signal,
)

from code import status_messages


LINE_STYLE_OPTIONS = (
    ("Solid", "-"),
    ("Dashed", "--"),
    ("Dash-dot", "-."),
    ("Dotted", ":"),
)

_LINE_STYLE_ALIASES = {
    "-": "-",
    "solid": "-",
    "--": "--",
    "dashed": "--",
    "-.": "-.",
    "dashdot": "-.",
    "dash-dot": "-.",
    ":": ":",
    "dotted": ":",
    "none": "None",
    "": "None",
    " ": "None",
    "null": "None",
    "None": "None",
}


def normalize_line_style(style: Any) -> str:
    """Return Matplotlib's canonical short notation for a line style."""

    text = str(style)
    return _LINE_STYLE_ALIASES.get(text, _LINE_STYLE_ALIASES.get(text.casefold(), text))


def _result_status_text(result: Any) -> str:
    for attribute in ("result", "status", "outcome"):
        value = getattr(result, attribute, None)
        if value is None:
            continue
        value = getattr(value, "value", value)
        return str(value).casefold()
    return ""


def modification_succeeded(result: Any) -> bool:
    """Interpret callback results and component changes uniformly."""

    if result is None:
        return True
    if isinstance(result, bool):
        return result
    success = getattr(result, "success", None)
    if success is not None:
        return bool(success() if callable(success) else success)
    ok = getattr(result, "ok", None)
    if ok is not None:
        return bool(ok() if callable(ok) else ok)
    status = _result_status_text(result)
    if status:
        return status not in {"rejected", "failed", "failure", "error", "invalid"}
    return True


def modification_message(result: Any) -> str:
    """Return a user-facing message for a component change."""

    message = getattr(result, "message", "")
    return str(message) if message else ""


def modification_status(result: Any) -> str:
    """Map a component change to a Message Bar status level."""

    return _result_status_text(result)


class DebouncedTextBinding(QObject):
    """Apply text after a short pause and restore the last accepted value.

    The callback may return ``None``, a bool, or a component change object
    exposing ``success``/``status`` and optionally ``message``.
    """

    applied = Signal(str)
    rejected = Signal(str)

    def __init__(
        self,
        editor: QLineEdit | QPlainTextEdit,
        callback: Callable[[str], Any],
        *,
        delay_ms: int = 250,
        result_presenter: Callable[[Any], bool] | None = None,
        parent: QObject | None = None,
    ):
        super().__init__(parent or editor)
        self.editor = editor
        self.callback = callback
        self.result_presenter = result_presenter
        self.delay_ms = max(0, int(delay_ms))
        self._last_valid_text = self._text()
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(self.delay_ms)
        self._timer.timeout.connect(self.flush)
        editor.textChanged.connect(self._queue)

    @property
    def last_valid_text(self) -> str:
        """Return the last valid text."""

        return self._last_valid_text

    def _text(self) -> str:
        if isinstance(self.editor, QPlainTextEdit):
            return self.editor.toPlainText()
        return self.editor.text()

    def _set_editor_text(self, text: str) -> None:
        blocker = QSignalBlocker(self.editor)
        if isinstance(self.editor, QPlainTextEdit):
            self.editor.setPlainText(text)
        else:
            self.editor.setText(text)
        del blocker

    def _queue(self, *_args) -> None:
        self._timer.start()

    def cancel(self) -> None:
        """Close the dialog without applying pending changes."""

        self._timer.stop()

    def set_text(self, text: str, *, accepted: bool = True) -> None:
        """Set text."""

        self.cancel()
        text = str(text)
        self._set_editor_text(text)
        if accepted:
            self._last_valid_text = text

    def rollback(self) -> None:
        """Restore the last valid control value after a failed update."""

        self.cancel()
        self._set_editor_text(self._last_valid_text)

    def flush(self) -> bool:
        """Commit the control's pending coalesced value."""

        self.cancel()
        candidate = self._text()
        if candidate == self._last_valid_text:
            return True
        try:
            result = self.callback(candidate)
        except Exception as exc:
            self.rollback()
            status_messages.show_error(str(exc))
            self.rejected.emit(candidate)
            return False
        if self.result_presenter is not None:
            if not self.result_presenter(result):
                self.rollback()
                self.rejected.emit(candidate)
                return False
            self._last_valid_text = candidate
            self.applied.emit(candidate)
            return True
        if not modification_succeeded(result):
            self.rollback()
            message = modification_message(result)
            if message:
                status_messages.show_error(message)
            self.rejected.emit(candidate)
            return False
        message = modification_message(result)
        status = modification_status(result)
        if status == "empty" and message:
            status_messages.show_warning(message)
        elif status != "noop":
            status_messages.show_success(message or "Text updated.")
        self._last_valid_text = candidate
        self.applied.emit(candidate)
        return True


class LineStyleEditor(QWidget):
    """Reusable line-style and optional marker-size editor."""

    styleChanged = Signal(str)
    sizeChanged = Signal(float)

    def __init__(
        self,
        style: str = "-",
        size: float | None = None,
        *,
        show_size: bool = False,
        size_label: str = "Marker size:",
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        style_row = QHBoxLayout()
        style_row.addWidget(QLabel("Line style:", self))
        self.style_combo = QComboBox(self)
        for label, value in LINE_STYLE_OPTIONS:
            self.style_combo.addItem(label, value)
        style_row.addWidget(self.style_combo, 1)
        layout.addLayout(style_row)

        self.size_row = QWidget(self)
        size_layout = QHBoxLayout(self.size_row)
        size_layout.setContentsMargins(0, 0, 0, 0)
        size_layout.addWidget(QLabel(size_label, self.size_row))
        self.size_input = QDoubleSpinBox(self.size_row)
        self.size_input.setRange(0.0, 1_000_000.0)
        self.size_input.setDecimals(3)
        self.size_input.setSingleStep(0.5)
        if size is not None:
            self.size_input.setValue(float(size))
        size_layout.addWidget(self.size_input, 1)
        self.size_row.setVisible(bool(show_size))
        layout.addWidget(self.size_row)

        self.set_style(style)
        self.style_combo.currentIndexChanged.connect(self._emit_style)
        self.size_input.valueChanged.connect(self.sizeChanged)

    def _emit_style(self, *_args) -> None:
        self.styleChanged.emit(self.style())

    def style(self) -> str:
        """Return the selected style."""

        value = self.style_combo.currentData()
        return normalize_line_style(value)

    def set_style(self, style: str) -> None:
        """Set style."""

        canonical = normalize_line_style(style)
        index = self.style_combo.findData(canonical)
        if index < 0:
            index = self.style_combo.findData("-")
        blocker = QSignalBlocker(self.style_combo)
        self.style_combo.setCurrentIndex(index)
        del blocker

    def size(self) -> float:
        """Return the selected size."""

        return float(self.size_input.value())

    def set_size(self, size: float) -> None:
        """Set size."""

        blocker = QSignalBlocker(self.size_input)
        self.size_input.setValue(float(size))
        del blocker


class RangeEditor(QWidget):
    """Two-value numerical range editor with signal-safe synchronization."""

    rangeChanged = Signal(float, float)

    def __init__(
        self,
        minimum: float = 0.0,
        maximum: float = 1.0,
        *,
        lower_label: str = "Minimum:",
        upper_label: str = "Maximum:",
        bounds: tuple[float, float] = (-1e300, 1e300),
        step: float = 1.0,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.minimum_input = QDoubleSpinBox(self)
        self.maximum_input = QDoubleSpinBox(self)
        for spin in (self.minimum_input, self.maximum_input):
            spin.setRange(float(bounds[0]), float(bounds[1]))
            spin.setSingleStep(float(step))
            spin.setDecimals(6)
        layout.addWidget(QLabel(lower_label, self))
        layout.addWidget(self.minimum_input)
        layout.addWidget(QLabel(upper_label, self))
        layout.addWidget(self.maximum_input)
        self.set_range(minimum, maximum)
        self.minimum_input.valueChanged.connect(self._emit_range)
        self.maximum_input.valueChanged.connect(self._emit_range)

    def _emit_range(self, *_args) -> None:
        self.rangeChanged.emit(*self.values())

    def values(self) -> tuple[float, float]:
        """Return the current collection of values."""

        return float(self.minimum_input.value()), float(self.maximum_input.value())

    def set_range(self, minimum: float, maximum: float) -> None:
        """Set range."""

        lower_blocker = QSignalBlocker(self.minimum_input)
        upper_blocker = QSignalBlocker(self.maximum_input)
        self.minimum_input.setValue(float(minimum))
        self.maximum_input.setValue(float(maximum))
        del lower_blocker, upper_blocker


class NullableDoubleEditor(QWidget):
    """A double-spin editor that can explicitly preserve Matplotlib ``None``."""

    valueChanged = Signal(object)

    def __init__(
        self,
        value: float | None = None,
        *,
        fallback: float = 1.0,
        bounds: tuple[float, float] = (-1e300, 1e300),
        decimals: int = 6,
        step: float = 0.1,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.use_value_input = QCheckBox("Set", self)
        self.value_input = QDoubleSpinBox(self)
        self.value_input.setRange(float(bounds[0]), float(bounds[1]))
        self.value_input.setDecimals(int(decimals))
        self.value_input.setSingleStep(float(step))
        self._fallback = float(fallback)
        layout.addWidget(self.use_value_input)
        layout.addWidget(self.value_input, 1)
        self.set_value(value)
        self.use_value_input.toggled.connect(self._use_value_changed)
        self.value_input.valueChanged.connect(self._value_changed)

    def value(self) -> float | None:
        """Return the current control value."""

        if not self.use_value_input.isChecked():
            return None
        return float(self.value_input.value())

    def set_value(self, value: float | None, *, emit: bool = False) -> None:
        """Set value."""

        use_blocker = QSignalBlocker(self.use_value_input)
        value_blocker = QSignalBlocker(self.value_input)
        enabled = value is not None
        self.use_value_input.setChecked(enabled)
        self.value_input.setValue(
            self._fallback if value is None else float(value)
        )
        self.value_input.setEnabled(enabled)
        del use_blocker, value_blocker
        if emit:
            self.valueChanged.emit(self.value())

    def _use_value_changed(self, checked: bool) -> None:
        self.value_input.setEnabled(bool(checked))
        self.valueChanged.emit(self.value())

    def _value_changed(self, _value: float) -> None:
        if self.use_value_input.isChecked():
            self.valueChanged.emit(self.value())


class NumericTupleEditor(QWidget):
    """Reusable two/four-value numerical editor with optional ``None``."""

    valueChanged = Signal(object)

    def __init__(
        self,
        value,
        *,
        length: int = 2,
        nullable: bool = False,
        fallback=None,
        bounds: tuple[float, float] = (-1e300, 1e300),
        decimals: int = 6,
        step: float = 0.1,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        if int(length) < 1:
            raise ValueError("NumericTupleEditor length must be positive.")
        self.length = int(length)
        self.nullable = bool(nullable)
        self._fallback = tuple(
            float(item)
            for item in (
                fallback
                if isinstance(fallback, (tuple, list))
                and len(fallback) == self.length
                else (0.0,) * self.length
            )
        )
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.use_value_input = None
        if self.nullable:
            self.use_value_input = QCheckBox("Set", self)
            layout.addWidget(self.use_value_input)
        self.inputs: list[QDoubleSpinBox] = []
        for _index in range(self.length):
            editor = QDoubleSpinBox(self)
            editor.setRange(float(bounds[0]), float(bounds[1]))
            editor.setDecimals(int(decimals))
            editor.setSingleStep(float(step))
            editor.valueChanged.connect(self._input_changed)
            self.inputs.append(editor)
            layout.addWidget(editor, 1)
        self.set_value(value)
        if self.use_value_input is not None:
            self.use_value_input.toggled.connect(self._use_value_changed)

    def value(self):
        """Return the current control value."""

        if (
            self.use_value_input is not None
            and not self.use_value_input.isChecked()
        ):
            return None
        return tuple(float(editor.value()) for editor in self.inputs)

    def set_value(self, value, *, emit: bool = False) -> None:
        """Set value."""

        enabled = value is not None or not self.nullable
        values = (
            tuple(float(item) for item in value)
            if isinstance(value, (tuple, list)) and len(value) == self.length
            else self._fallback
        )
        blockers = [QSignalBlocker(editor) for editor in self.inputs]
        use_blocker = (
            QSignalBlocker(self.use_value_input)
            if self.use_value_input is not None
            else None
        )
        if self.use_value_input is not None:
            self.use_value_input.setChecked(enabled)
        for editor, item in zip(self.inputs, values):
            editor.setValue(item)
            editor.setEnabled(enabled)
        del blockers, use_blocker
        if emit:
            self.valueChanged.emit(self.value())

    def _use_value_changed(self, checked: bool) -> None:
        for editor in self.inputs:
            editor.setEnabled(bool(checked))
        self.valueChanged.emit(self.value())

    def _input_changed(self, _value: float) -> None:
        if (
            self.use_value_input is None
            or self.use_value_input.isChecked()
        ):
            self.valueChanged.emit(self.value())


class SpinePositionEditor(QWidget):
    """Editor for ``center``/``zero`` and coordinate-system spine positions."""

    valueChanged = Signal(object)

    POSITION_TYPES = (
        ("Center", "center"),
        ("Zero", "zero"),
        ("Outward", "outward"),
        ("Axes", "axes"),
        ("Data", "data"),
    )

    def __init__(self, value=("outward", 0.0), parent: QWidget | None = None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.kind_input = QComboBox(self)
        for label, item in self.POSITION_TYPES:
            self.kind_input.addItem(label, item)
        self.value_input = QDoubleSpinBox(self)
        self.value_input.setRange(-1e300, 1e300)
        self.value_input.setDecimals(6)
        self.value_input.setSingleStep(0.1)
        layout.addWidget(self.kind_input)
        layout.addWidget(self.value_input, 1)
        self.set_value(value)
        self.kind_input.currentIndexChanged.connect(self._changed)
        self.value_input.valueChanged.connect(self._changed)

    def value(self):
        """Return the current control value."""

        kind = str(self.kind_input.currentData())
        if kind in {"center", "zero"}:
            return kind
        return kind, float(self.value_input.value())

    def set_value(self, value, *, emit: bool = False) -> None:
        """Set value."""

        if isinstance(value, str):
            kind, number = value, 0.0
        elif isinstance(value, (tuple, list)) and len(value) == 2:
            kind, number = str(value[0]), float(value[1])
        else:
            kind, number = "outward", 0.0
        index = self.kind_input.findData(kind)
        if index < 0:
            index = self.kind_input.findData("outward")
        kind_blocker = QSignalBlocker(self.kind_input)
        value_blocker = QSignalBlocker(self.value_input)
        self.kind_input.setCurrentIndex(index)
        self.value_input.setValue(number)
        self.value_input.setEnabled(
            self.kind_input.currentData() not in {"center", "zero"}
        )
        del kind_blocker, value_blocker
        if emit:
            self.valueChanged.emit(self.value())

    def _changed(self, *_args) -> None:
        self.value_input.setEnabled(
            self.kind_input.currentData() not in {"center", "zero"}
        )
        self.valueChanged.emit(self.value())


class ScatterStyleEditor(QWidget):
    """Reusable marker and size editor for scatter collections."""

    markerChanged = Signal(str)
    sizeChanged = Signal(float)

    DEFAULT_MARKERS = ("o", "s", "D", "^", "v", "<", ">", "x", "+", "*", "P", "X")

    def __init__(
        self,
        marker: str = "o",
        size: float = 20.0,
        *,
        markers: Iterable[str] | None = None,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(QLabel("Marker:", self))
        self.marker_input = QComboBox(self)
        self.marker_input.addItems([str(item) for item in (markers or self.DEFAULT_MARKERS)])
        if self.marker_input.findText(str(marker)) < 0:
            self.marker_input.addItem(str(marker))
        self.marker_input.setCurrentText(str(marker))
        layout.addWidget(self.marker_input)

        layout.addWidget(QLabel("Size:", self))
        self.size_input = QDoubleSpinBox(self)
        self.size_input.setRange(0.0, 1_000_000.0)
        self.size_input.setDecimals(3)
        self.size_input.setValue(float(size))
        layout.addWidget(self.size_input)

        self.marker_input.currentTextChanged.connect(self.markerChanged)
        self.size_input.valueChanged.connect(self.sizeChanged)

    def marker(self) -> str:
        """Return the selected marker."""

        return self.marker_input.currentText()

    def size(self) -> float:
        """Return the selected size."""

        return float(self.size_input.value())

    def set_marker(self, marker: str) -> None:
        """Set marker."""

        marker = str(marker)
        if self.marker_input.findText(marker) < 0:
            self.marker_input.addItem(marker)
        blocker = QSignalBlocker(self.marker_input)
        self.marker_input.setCurrentText(marker)
        del blocker

    def set_size(self, size: float) -> None:
        """Set size."""

        blocker = QSignalBlocker(self.size_input)
        self.size_input.setValue(float(size))
        del blocker
