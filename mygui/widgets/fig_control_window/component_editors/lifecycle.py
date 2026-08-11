"""Small reverse-order cleanup stack for externally subscribed UI objects."""

from __future__ import annotations

from collections.abc import Callable


class CallbackLifecycle:
    """Own idempotent callbacks and release every one in reverse order."""

    def __init__(self) -> None:
        self._callbacks: list[Callable[[], None]] = []
        self._closed = False

    def add(self, callback: Callable[[], None]) -> Callable[[], None]:
        if self._closed:
            raise RuntimeError("Lifecycle is already closed.")
        if not callable(callback):
            raise TypeError("Lifecycle cleanup must be callable.")
        self._callbacks.append(callback)
        return callback

    def close(self) -> tuple[BaseException, ...]:
        if self._closed:
            return ()
        self._closed = True
        errors = []
        for callback in reversed(self._callbacks):
            try:
                callback()
            except BaseException as exc:
                errors.append(exc)
        self._callbacks.clear()
        return tuple(errors)
