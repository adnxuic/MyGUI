"""Route user-facing status messages to the active Message Bar."""

from collections.abc import Callable


StatusHandler = Callable[[str, str], None]
_status_handler: StatusHandler | None = None


def set_status_handler(handler: StatusHandler) -> None:
    """Set status handler."""

    global _status_handler
    _status_handler = handler


def clear_status_handler(handler: StatusHandler | None = None) -> None:
    """Clear status handler."""

    global _status_handler
    if handler is None or _status_handler == handler:
        _status_handler = None


def show_message(message: str, level: str = "info") -> bool:
    """Show message."""

    global _status_handler
    if _status_handler is None:
        return False
    try:
        _status_handler(message, level)
    except RuntimeError:
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
