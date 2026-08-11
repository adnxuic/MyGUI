"""Run optional integrations off the UI thread with owner-safe callbacks."""

from __future__ import annotations

from dataclasses import dataclass
from PySide6.QtCore import QObject, Qt, Signal, Slot
from shiboken6 import isValid

import itertools
import logging
import threading
import time
import weakref


_background_task_counter = itertools.count(1)
_active_background_tasks: dict[int, "_TaskRecord"] = {}
_background_bridge: "_BackgroundTaskBridge | None" = None


@dataclass
class _TaskRecord:
    task_id: int
    task_name: str
    owner_ref: weakref.ReferenceType
    owner_alive: bool
    logger: logging.Logger
    task_log_prefix: str
    started_at: float
    on_finished: object
    on_failed: object
    thread: threading.Thread | None = None


class _BackgroundTaskBridge(QObject):
    """One application-lifetime bridge for all daemon-thread results.

    A per-task QObject is tempting here, but destroying it from its own queued
    delivery slot leaves PySide with fragile queued-connection bookkeeping.
    Keeping one bridge alive for the application lifetime removes that race.
    """

    finished = Signal(int, object)
    failed = Signal(int, str)

    def __init__(self):
        super().__init__()
        self.finished.connect(
            self.deliver_finished,
            Qt.ConnectionType.QueuedConnection,
        )
        self.failed.connect(
            self.deliver_failed,
            Qt.ConnectionType.QueuedConnection,
        )

    @Slot(int, object)
    def deliver_finished(self, task_id, result):
        record = _take_record(task_id)
        if record is None:
            return
        _log_completion(record, "finished")
        if _should_deliver(record, "success"):
            try:
                record.on_finished(result)
            except Exception:
                record.logger.exception(
                    "%s success callback failed task_id=%s task=%s",
                    record.task_log_prefix,
                    record.task_id,
                    record.task_name,
                )

    @Slot(int, str)
    def deliver_failed(self, task_id, message):
        record = _take_record(task_id)
        if record is None:
            return
        _log_completion(record, "failed", message=message)
        if _should_deliver(record, "failure"):
            try:
                record.on_failed(message)
            except Exception:
                record.logger.exception(
                    "%s failure callback failed task_id=%s task=%s",
                    record.task_log_prefix,
                    record.task_id,
                    record.task_name,
                )


def _get_background_bridge() -> _BackgroundTaskBridge:
    global _background_bridge
    if _background_bridge is None:
        _background_bridge = _BackgroundTaskBridge()
    return _background_bridge


def _take_record(task_id: int) -> _TaskRecord | None:
    record = _active_background_tasks.pop(task_id, None)
    if record is None:
        return None
    thread = record.thread
    if thread is not None and thread is not threading.current_thread():
        thread.join(1.0)
    return record


def _log_completion(record: _TaskRecord, result_type: str, message=None) -> None:
    elapsed = time.monotonic() - record.started_at
    if message is None:
        record.logger.debug(
            "%s %s task_id=%s task=%s elapsed=%.3fs",
            record.task_log_prefix,
            result_type,
            record.task_id,
            record.task_name,
            elapsed,
        )
    else:
        record.logger.debug(
            "%s %s task_id=%s task=%s elapsed=%.3fs message=%s",
            record.task_log_prefix,
            result_type,
            record.task_id,
            record.task_name,
            elapsed,
            message,
        )


def _should_deliver(record: _TaskRecord, result_type: str) -> bool:
    owner = record.owner_ref()
    if not record.owner_alive or owner is None or not isValid(owner):
        record.logger.debug(
            "%s %s ignored after owner destruction task_id=%s task=%s",
            record.task_log_prefix,
            result_type,
            record.task_id,
            record.task_name,
        )
        return False
    return True


def _mark_owner_destroyed(task_id: int) -> None:
    record = _active_background_tasks.get(task_id)
    if record is None:
        return
    record.owner_alive = False
    record.logger.debug(
        "%s owner destroyed task_id=%s task=%s",
        record.task_log_prefix,
        record.task_id,
        record.task_name,
    )


def start_background_task(
    owner,
    func,
    on_finished,
    on_failed,
    *args,
    logger=None,
    task_log_prefix="Background task",
    **kwargs,
):
    """Start a daemon worker and queue its result onto the Qt owner thread."""

    task_id = next(_background_task_counter)
    task_name = getattr(func, "__name__", func.__class__.__name__)
    if logger is None:
        logger = logging.getLogger("mygui.background")
    bridge = _get_background_bridge()
    record = _TaskRecord(
        task_id=task_id,
        task_name=task_name,
        owner_ref=weakref.ref(owner),
        owner_alive=True,
        logger=logger,
        task_log_prefix=task_log_prefix,
        started_at=time.monotonic(),
        on_finished=on_finished,
        on_failed=on_failed,
    )
    owner.destroyed.connect(lambda *_args, value=task_id: _mark_owner_destroyed(value))

    def run() -> None:
        logger.debug(
            "%s worker started task_id=%s task=%s",
            task_log_prefix,
            task_id,
            task_name,
        )
        try:
            result = func(*args, **kwargs)
        except Exception as exc:
            logger.debug(
                "%s worker failed task_id=%s task=%s error=%s",
                task_log_prefix,
                task_id,
                task_name,
                exc,
            )
            bridge.failed.emit(task_id, str(exc))
        else:
            logger.debug(
                "%s worker succeeded task_id=%s task=%s",
                task_log_prefix,
                task_id,
                task_name,
            )
            bridge.finished.emit(task_id, result)

    thread = threading.Thread(
        target=run,
        name=f"mygui-{task_name}-{task_id}",
        daemon=True,
    )
    record.thread = thread
    _active_background_tasks[task_id] = record
    thread.start()
    return thread, record


def cancel_background_tasks(owner=None) -> int:
    """Suppress callbacks for matching tasks; workers finish cooperatively."""

    cancelled = 0
    for record in tuple(_active_background_tasks.values()):
        if owner is not None and record.owner_ref() is not owner:
            continue
        record.owner_alive = False
        cancelled += 1
    return cancelled


def drain_background_tasks(timeout_ms: int = 1000) -> bool:
    """Bound shutdown waiting across all live daemon workers."""

    records = tuple(_active_background_tasks.values())
    if not records:
        return True
    cancel_background_tasks()
    deadline = time.monotonic() + max(0, timeout_ms) / 1000
    for record in records:
        thread = record.thread
        if thread is None:
            continue
        remaining = max(0.0, deadline - time.monotonic())
        if thread.is_alive() and remaining:
            thread.join(remaining)
    return all(
        record.thread is None or not record.thread.is_alive()
        for record in records
    )
