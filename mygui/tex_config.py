"""Manage optional TeX rendering state and diagnostic logging."""

import json
import logging
from collections.abc import Callable
from dataclasses import dataclass
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

import matplotlib as mpl

from mygui.application_paths import user_log_directory
from mygui.bounded_process import (
    ProcessOutputLimitExceeded,
    run_bounded_process,
)
from mygui.resource_limits import load_resource_limits


_REPO_ROOT = Path(__file__).resolve().parents[1]
_DEFAULT_LOG_DIR = user_log_directory()
_LOG_FILE_NAME = "tex.log"
_LOG_MAX_BYTES = 1_000_000
_LOG_BACKUP_COUNT = 3
LOGGER_NAME = "mygui.tex"
_LOG_TO_FILE = True
_LOG_TO_STDERR = False
_FILE_HANDLER_MARKER = "_mygui_tex_file_handler"
_STDERR_HANDLER_MARKER = "_mygui_tex_stderr_handler"
_LOGGER_SIGNATURE = None
DEFAULT_PREAMBLE_LINES = (
    r"\usepackage{amsmath}",
    r"\usepackage{newtxtext,newtxmath}",
)
TEX_ENGINE_COMMANDS = ("latex", "pdflatex", "xelatex", "tectonic")


@dataclass(frozen=True, slots=True)
class TexRuntimeState:
    """Process-wide Matplotlib TeX configuration owned by MyGUI."""

    enabled: bool
    preamble: str


@dataclass(frozen=True, slots=True)
class TexRuntimeChange:
    """Describe one atomic TeX runtime configuration change."""

    before: TexRuntimeState
    after: TexRuntimeState

    @property
    def enabled_changed(self) -> bool:
        return self.before.enabled != self.after.enabled

    @property
    def preamble_changed(self) -> bool:
        return self.before.preamble != self.after.preamble


@dataclass(frozen=True, slots=True)
class TexRuntimeUpdate:
    """Return the committed configuration and per-Figure refresh warnings."""

    change: TexRuntimeChange
    warnings: tuple[str, ...] = ()


TexAvailabilityListener = Callable[[bool], None]
TexRenderListener = Callable[[TexRuntimeChange], str | None]
_TEX_AVAILABILITY_LISTENERS: list[TexAvailabilityListener] = []
_TEX_RENDER_LISTENERS: list[TexRenderListener] = []


def _configured_log_level() -> int:
    configured = os.environ.get("MYGUI_TEX_LOG_LEVEL", "INFO").upper()
    return getattr(logging, configured, logging.INFO)


def _configured_log_dir() -> Path:
    configured = os.environ.get("MYGUI_TEX_LOG_DIR")
    return Path(configured) if configured else _DEFAULT_LOG_DIR


def _remove_marked_handlers(logger: logging.Logger, marker: str) -> None:
    for handler in list(logger.handlers):
        if getattr(handler, marker, False):
            logger.removeHandler(handler)
            handler.close()


def _handler_path(handler: logging.Handler) -> Path | None:
    base_filename = getattr(handler, "baseFilename", None)
    return Path(base_filename) if base_filename else None


def _has_marked_handler(
    logger: logging.Logger,
    marker: str,
    path: Path | None = None,
) -> bool:
    for handler in logger.handlers:
        if not getattr(handler, marker, False):
            continue
        if path is None or _handler_path(handler) == path:
            return True
    return False


def _logger_has_expected_sinks(
    logger: logging.Logger,
    include_file: bool,
    include_stderr: bool,
    log_file: Path,
) -> bool:
    has_file = _has_marked_handler(logger, _FILE_HANDLER_MARKER, log_file)
    has_stderr = _has_marked_handler(logger, _STDERR_HANDLER_MARKER)
    return (has_file if include_file else not has_file) and (has_stderr if include_stderr else not has_stderr)


def configure_tex_logging(
    include_file: bool | None = None,
    include_stderr: bool | None = None,
) -> logging.Logger:
    """Configure log routing for the optional TeX integration."""

    global _LOGGER_SIGNATURE
    if include_file is None:
        include_file = _LOG_TO_FILE
    if include_stderr is None:
        include_stderr = _LOG_TO_STDERR

    logger = logging.getLogger(LOGGER_NAME)
    level = _configured_log_level()
    log_file = _configured_log_dir() / _LOG_FILE_NAME
    signature = (include_file, include_stderr, level, str(log_file))
    logger.setLevel(level)
    logger.propagate = False
    if _LOGGER_SIGNATURE == signature and _logger_has_expected_sinks(
        logger,
        include_file,
        include_stderr,
        log_file,
    ):
        return logger

    _remove_marked_handlers(logger, _FILE_HANDLER_MARKER)
    _remove_marked_handlers(logger, _STDERR_HANDLER_MARKER)

    formatter = logging.Formatter(
        "%(asctime)s %(levelname)s %(name)s [%(process)d:%(threadName)s] %(message)s"
    )

    if include_file:
        try:
            log_file.parent.mkdir(parents=True, exist_ok=True)
            file_handler = RotatingFileHandler(
                log_file,
                maxBytes=_LOG_MAX_BYTES,
                backupCount=_LOG_BACKUP_COUNT,
                encoding="utf-8",
            )
            file_handler.setFormatter(formatter)
            file_handler.setLevel(level)
            setattr(file_handler, _FILE_HANDLER_MARKER, True)
            logger.addHandler(file_handler)
        except OSError as exc:
            if include_stderr:
                sys.stderr.write(f"TeX log file setup failed: {exc}\n")

    if include_stderr:
        stderr_handler = logging.StreamHandler(sys.stderr)
        stderr_handler.setFormatter(formatter)
        stderr_handler.setLevel(level)
        setattr(stderr_handler, _STDERR_HANDLER_MARKER, True)
        logger.addHandler(stderr_handler)

    for handler in logger.handlers:
        if getattr(handler, _FILE_HANDLER_MARKER, False) or getattr(handler, _STDERR_HANDLER_MARKER, False):
            handler.setLevel(level)
    _LOGGER_SIGNATURE = signature
    return logger


def set_tex_log_sinks(include_file: bool, include_stderr: bool) -> logging.Logger:
    """Set tex log sinks."""

    global _LOG_TO_FILE, _LOG_TO_STDERR
    _LOG_TO_FILE = include_file
    _LOG_TO_STDERR = include_stderr
    return configure_tex_logging()


def tex_logger() -> logging.Logger:
    """Return the logger used by the TeX integration."""

    return configure_tex_logging()


def is_tex_enabled() -> bool:
    """Return whether tex enabled."""

    return bool(mpl.rcParams.get("text.usetex", False))


def read_tex_runtime() -> TexRuntimeState:
    """Return the current process-wide TeX runtime configuration."""

    return TexRuntimeState(
        enabled=is_tex_enabled(),
        preamble=str(mpl.rcParams.get("text.latex.preamble", "")),
    )


def register_tex_availability_listener(
    listener: TexAvailabilityListener,
) -> None:
    """Register a listener for the enabled availability flag."""

    if listener not in _TEX_AVAILABILITY_LISTENERS:
        _TEX_AVAILABILITY_LISTENERS.append(listener)


def unregister_tex_availability_listener(
    listener: TexAvailabilityListener,
) -> None:
    """Unregister an availability listener."""

    try:
        _TEX_AVAILABILITY_LISTENERS.remove(listener)
    except ValueError:
        pass


def register_tex_render_listener(listener: TexRenderListener) -> None:
    """Register one Canvas-owned TeX render listener."""

    if listener not in _TEX_RENDER_LISTENERS:
        _TEX_RENDER_LISTENERS.append(listener)


def unregister_tex_render_listener(listener: TexRenderListener) -> None:
    """Unregister one Canvas-owned TeX render listener."""

    try:
        _TEX_RENDER_LISTENERS.remove(listener)
    except ValueError:
        pass


def clear_tex_runtime_listeners() -> None:
    """Clear availability and render listeners for process teardown/tests."""

    _TEX_AVAILABILITY_LISTENERS.clear()
    _TEX_RENDER_LISTENERS.clear()


def _notify_tex_availability_listeners(enabled: bool) -> None:
    for listener in list(_TEX_AVAILABILITY_LISTENERS):
        try:
            listener(enabled)
        except Exception:
            # Qt raises RuntimeError when a Python callback still references a
            # QObject whose C++ instance has already been destroyed.
            tex_logger().exception(
                "TeX availability listener failed and was detached"
            )
            unregister_tex_availability_listener(listener)


def _notify_tex_render_listeners(
    change: TexRuntimeChange,
) -> tuple[str, ...]:
    warnings: list[str] = []
    for listener in list(_TEX_RENDER_LISTENERS):
        try:
            message = listener(change)
            if message:
                warnings.append(str(message))
        except Exception as exc:
            tex_logger().exception(
                "TeX render listener failed and was detached"
            )
            unregister_tex_render_listener(listener)
            warnings.append(f"A Figure could not refresh its TeX rendering: {exc}")
    return tuple(warnings)


def configure_tex_runtime(
    *,
    enabled: bool | None = None,
    preamble: str | None = None,
    notify: bool = True,
) -> TexRuntimeUpdate:
    """Atomically update global TeX rcParams and refresh interested Canvases."""

    before = read_tex_runtime()
    after = TexRuntimeState(
        enabled=before.enabled if enabled is None else bool(enabled),
        preamble=(
            before.preamble
            if preamble is None
            else normalize_preamble(str(preamble))
        ),
    )
    change = TexRuntimeChange(before, after)
    if not change.enabled_changed and not change.preamble_changed:
        return TexRuntimeUpdate(change)

    try:
        mpl.rcParams["text.latex.preamble"] = after.preamble
        mpl.rcParams["text.usetex"] = after.enabled
    except Exception:
        mpl.rcParams["text.latex.preamble"] = before.preamble
        mpl.rcParams["text.usetex"] = before.enabled
        raise

    warnings: tuple[str, ...] = ()
    if notify:
        if change.enabled_changed or (
            change.preamble_changed and change.after.enabled
        ):
            warnings = _notify_tex_render_listeners(change)
        if change.enabled_changed:
            _notify_tex_availability_listeners(change.after.enabled)
    return TexRuntimeUpdate(change, warnings)


def set_tex_enabled(enabled: bool, notify: bool = True) -> TexRuntimeUpdate:
    """Compatibility convenience routed through the atomic runtime update."""

    return configure_tex_runtime(enabled=enabled, notify=notify)


def initialize_tex_runtime() -> TexRuntimeUpdate:
    """Start MyGUI with TeX safely disabled and an editable preamble."""

    current = read_tex_runtime()
    preamble = (
        current.preamble
        if current.preamble.strip()
        else default_preamble_text()
    )
    return configure_tex_runtime(
        enabled=False,
        preamble=preamble,
        notify=False,
    )


def default_preamble_text() -> str:
    """Return the default preamble text."""

    return "\n".join(DEFAULT_PREAMBLE_LINES)


def normalize_preamble(text: str) -> str:
    """Normalize non-empty TeX preamble lines."""

    lines = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped:
            lines.append(stripped)
    return "\n".join(lines)


def has_tex_engine() -> bool:
    """Return whether a supported TeX executable is available."""

    for command in TEX_ENGINE_COMMANDS:
        path = shutil.which(command)
        if path:
            tex_logger().debug("TeX executable found command=%s path=%s", command, path)
            return True
    tex_logger().debug("TeX executable not found commands=%s", ",".join(TEX_ENGINE_COMMANDS))
    return False


def validate_tex_runtime(preamble: str) -> str | None:
    """Validate TeX in an isolated child process with a hard timeout."""

    logger = tex_logger()
    started_at = time.monotonic()
    preamble_line_count = len(preamble.splitlines()) if preamble else 0
    logger.debug("TeX runtime validation started preamble_line_count=%s", preamble_line_count)
    if not has_tex_engine():
        logger.warning("TeX runtime validation failed reason=no executable")
        return "No TeX executable was found on PATH."

    script = r'''
import io
import json
import sys

import matplotlib as mpl
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure

payload = json.loads(sys.stdin.read())
with mpl.rc_context({
    "text.usetex": True,
    "text.latex.preamble": payload["preamble"],
}):
    figure = Figure(figsize=(0.2, 0.2), dpi=50)
    FigureCanvasAgg(figure)
    figure.text(0.5, 0.5, r"$x$", ha="center", va="center")
    figure.canvas.print_png(io.BytesIO())
'''
    limits = load_resource_limits()
    input_bytes = json.dumps({"preamble": preamble}).encode("utf-8")
    try:
        result = run_bounded_process(
            [sys.executable, "-B", "-c", script],
            input_bytes=input_bytes,
            cwd=str(_REPO_ROOT),
            env={**os.environ, "MPLBACKEND": "Agg"},
            timeout=_timeout_from_environment(),
            max_input_bytes=limits.max_external_input_bytes,
            max_output_bytes=limits.max_external_output_bytes,
        )
        if result.returncode:
            detail = result.stderr.decode("utf-8", errors="replace").strip()
            if detail:
                detail = detail.splitlines()[-1]
            raise RuntimeError(detail or f"TeX child exited with {result.returncode}")
    except subprocess.TimeoutExpired:
        elapsed = time.monotonic() - started_at
        logger.warning("TeX runtime validation timed out elapsed=%.3fs", elapsed)
        return "TeX rendering timed out."
    except (ProcessOutputLimitExceeded, ValueError) as exc:
        elapsed = time.monotonic() - started_at
        logger.warning(
            "TeX runtime validation exceeded a resource budget elapsed=%.3fs error=%s",
            elapsed,
            exc,
        )
        return f"TeX rendering failed: {exc}"
    except Exception as exc:
        elapsed = time.monotonic() - started_at
        logger.warning("TeX runtime validation failed elapsed=%.3fs error=%s", elapsed, exc)
        return f"TeX rendering failed: {exc}"

    elapsed = time.monotonic() - started_at
    logger.debug(
        "TeX runtime validation succeeded elapsed=%.3fs preamble_line_count=%s",
        elapsed,
        preamble_line_count,
    )
    return None


def _timeout_from_environment() -> float:
    raw = os.environ.get("MYGUI_TEX_TIMEOUT_SECONDS", "15")
    try:
        timeout = float(raw)
    except ValueError:
        return 15.0
    return timeout if timeout > 0 else 15.0
