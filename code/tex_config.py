import io
import logging
from collections.abc import Callable
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import shutil
import sys
import time

import matplotlib as mpl
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure


_REPO_ROOT = Path(__file__).resolve().parents[1]
_DEFAULT_LOG_DIR = _REPO_ROOT / "logs"
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
TexStateListener = Callable[[bool], None]
_TEX_STATE_LISTENERS: list[TexStateListener] = []


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
    global _LOG_TO_FILE, _LOG_TO_STDERR
    _LOG_TO_FILE = include_file
    _LOG_TO_STDERR = include_stderr
    return configure_tex_logging()


def tex_logger() -> logging.Logger:
    return configure_tex_logging()


def is_tex_enabled() -> bool:
    return bool(mpl.rcParams.get("text.usetex", False))


def register_tex_state_listener(listener: TexStateListener) -> None:
    if listener not in _TEX_STATE_LISTENERS:
        _TEX_STATE_LISTENERS.append(listener)


def unregister_tex_state_listener(listener: TexStateListener) -> None:
    try:
        _TEX_STATE_LISTENERS.remove(listener)
    except ValueError:
        pass


def clear_tex_state_listeners() -> None:
    _TEX_STATE_LISTENERS.clear()


def _notify_tex_state_listeners(enabled: bool) -> None:
    for listener in list(_TEX_STATE_LISTENERS):
        try:
            listener(enabled)
        except RuntimeError:
            unregister_tex_state_listener(listener)


def set_tex_enabled(enabled: bool, notify: bool = True) -> None:
    previous = is_tex_enabled()
    mpl.rcParams["text.usetex"] = bool(enabled)
    if notify and previous != bool(enabled):
        _notify_tex_state_listeners(bool(enabled))


def default_preamble_text() -> str:
    return "\n".join(DEFAULT_PREAMBLE_LINES)


def normalize_preamble(text: str) -> str:
    lines = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped:
            lines.append(stripped)
    return "\n".join(lines)


def has_tex_engine() -> bool:
    for command in TEX_ENGINE_COMMANDS:
        path = shutil.which(command)
        if path:
            tex_logger().debug("TeX executable found command=%s path=%s", command, path)
            return True
    tex_logger().debug("TeX executable not found commands=%s", ",".join(TEX_ENGINE_COMMANDS))
    return False


def validate_tex_runtime(preamble: str) -> str | None:
    logger = tex_logger()
    started_at = time.monotonic()
    preamble_line_count = len(preamble.splitlines()) if preamble else 0
    logger.debug("TeX runtime validation started preamble_line_count=%s", preamble_line_count)
    if not has_tex_engine():
        logger.warning("TeX runtime validation failed reason=no executable")
        return "No TeX executable was found on PATH."

    try:
        with mpl.rc_context({
            "text.usetex": True,
            "text.latex.preamble": preamble,
        }):
            figure = Figure(figsize=(0.2, 0.2), dpi=50)
            FigureCanvasAgg(figure)
            figure.text(0.5, 0.5, r"$x$", ha="center", va="center")
            figure.canvas.print_png(io.BytesIO())
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
