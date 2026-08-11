"""Route user-facing status messages to the active Message Bar."""

from collections.abc import Callable
import logging
import weakref


StatusHandler = Callable[[str, str], None]
LOGGER = logging.getLogger(__name__)
_status_handler: StatusHandler | weakref.WeakMethod | None = None


def _resolved_handler() -> StatusHandler | None:
    global _status_handler
    if isinstance(_status_handler, weakref.WeakMethod):
        handler = _status_handler()
        if handler is None:
            _status_handler = None
        return handler
    return _status_handler


def set_status_handler(handler: StatusHandler) -> None:
    """Set status handler without retaining a bound Qt owner indefinitely."""

    global _status_handler
    if getattr(handler, "__self__", None) is not None:
        try:
            _status_handler = weakref.WeakMethod(handler)
            return
        except TypeError:
            pass
    _status_handler = handler


def clear_status_handler(handler: StatusHandler | None = None) -> None:
    """Clear status handler."""

    global _status_handler
    if handler is None or _resolved_handler() == handler:
        _status_handler = None


def show_message(message: str, level: str = "info") -> bool:
    """Show one message without allowing presentation failures to escape."""

    global _status_handler
    handler = _resolved_handler()
    if handler is None:
        return False
    try:
        handler(message, level)
    except Exception:
        LOGGER.exception("Status message handler failed and was detached")
        _status_handler = None
        return False
    return True


def show_error(message: str) -> bool:
    """Show error."""

    return show_message(message, "error")


def show_success(message: str) -> bool:
    """Show success."""

    return show_message(message, "success")


def show_warning(message: str) -> bool:
    """Show warning."""

    return show_message(message, "warning")


def clear_message() -> bool:
    """Clear the current Message Bar text and reset its level."""

    return show_message("", "info")
