"""Isolate Inspector, container, and Editor Manager cleanup failures.

Cleanup is diagnostic only. Records are logged by default, remaining objects
continue to dispose, and callers must not turn these failures into Message Bar
results or a second business-state store.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
import logging
from typing import Any

LOGGER = logging.getLogger(__name__)

_RECORDED_FAILURES: list["CleanupFailure"] = []


@dataclass(frozen=True, slots=True)
class CleanupFailure:
    """Describe one isolated cleanup exception."""

    owner: str
    target: str
    operation: str
    error_type: str
    message: str


def drain_cleanup_failures() -> tuple[CleanupFailure, ...]:
    """Return and clear process-local cleanup diagnostics."""

    failures = tuple(_RECORDED_FAILURES)
    _RECORDED_FAILURES.clear()
    return failures


def record_cleanup_failure(
    *,
    owner: str,
    target: str,
    operation: str,
    error: BaseException,
    logger: logging.Logger | None = None,
) -> CleanupFailure:
    """Store and log one cleanup failure without raising."""

    failure = CleanupFailure(
        owner=str(owner),
        target=str(target),
        operation=str(operation),
        error_type=type(error).__name__,
        message=str(error),
    )
    _RECORDED_FAILURES.append(failure)
    (logger or LOGGER).error(
        "Cleanup failed: owner=%s target=%s operation=%s",
        failure.owner,
        failure.target,
        failure.operation,
        extra={
            "cleanup_failure": {
                "owner": failure.owner,
                "target": failure.target,
                "operation": failure.operation,
                "error_type": failure.error_type,
                "message": failure.message,
            }
        },
        exc_info=error,
    )
    return failure


def dispose_object(obj: object) -> None:
    """Invoke ``dispose()`` when the object exposes that hook."""

    cleanup = getattr(obj, "dispose", None)
    if callable(cleanup):
        cleanup()


def isolate_cleanup(
    action: Callable[[], Any],
    *,
    owner: str,
    target: str,
    operation: str,
    logger: logging.Logger | None = None,
) -> CleanupFailure | None:
    """Run one cleanup action and record any exception without raising."""

    try:
        action()
    except Exception as exc:
        return record_cleanup_failure(
            owner=owner,
            target=target,
            operation=operation,
            error=exc,
            logger=logger,
        )
    return None


def isolate_cleanup_steps(
    steps: Iterable[tuple[str, Callable[[], Any]]],
    *,
    owner: str,
    target: str,
    logger: logging.Logger | None = None,
) -> tuple[CleanupFailure, ...]:
    """Run independent cleanup steps and continue after each failure."""

    failures: list[CleanupFailure] = []
    for operation, action in steps:
        failure = isolate_cleanup(
            action,
            owner=owner,
            target=target,
            operation=operation,
            logger=logger,
        )
        if failure is not None:
            failures.append(failure)
    return tuple(failures)


def dispose_subscription(
    unsubscribe: Callable[[], Any] | None,
    *,
    owner: str,
    target: str,
    logger: logging.Logger | None = None,
) -> CleanupFailure | None:
    """Call a Registry or repository unsubscribe callback once, without raising."""

    if unsubscribe is None:
        return None
    return isolate_cleanup(
        unsubscribe,
        owner=owner,
        target=target,
        operation="unsubscribe",
        logger=logger,
    )
