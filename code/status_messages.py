from collections.abc import Callable


StatusHandler = Callable[[str, str], None]
_status_handler: StatusHandler | None = None


def set_status_handler(handler: StatusHandler) -> None:
    global _status_handler
    _status_handler = handler


def clear_status_handler(handler: StatusHandler | None = None) -> None:
    global _status_handler
    if handler is None or _status_handler == handler:
        _status_handler = None


def show_message(message: str, level: str = "info") -> bool:
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
    return show_message(message, "error")


def show_success(message: str) -> bool:
    return show_message(message, "success")


def show_warning(message: str) -> bool:
    return show_message(message, "warning")


def clear_message() -> bool:
    return show_message("", "info")
