"""Run optional integrations off the UI thread with owner-safe callbacks."""

from Qt_core import *

import itertools
import logging
import time
import weakref


_background_task_counter = itertools.count(1)
_active_background_tasks = {}


class BackgroundTaskWorker(QObject):
    """Run background task work outside the UI thread."""

    finished = Signal(object)
    failed = Signal(str)

    def __init__(self, task_id, task_name, func, logger, task_log_prefix, *args, **kwargs):
        super().__init__()
        self.task_id = task_id
        self.task_name = task_name
        self.func = func
        self.logger = logger
        self.task_log_prefix = task_log_prefix
        self.args = args
        self.kwargs = kwargs

    @Slot()
    def run(self):
        """Execute the background operation and emit its result."""

        self.logger.debug(
            "%s worker started task_id=%s task=%s",
            self.task_log_prefix,
            self.task_id,
            self.task_name,
        )
        try:
            result = self.func(*self.args, **self.kwargs)
        except Exception as exc:
            self.logger.debug(
                "%s worker failed task_id=%s task=%s error=%s",
                self.task_log_prefix,
                self.task_id,
                self.task_name,
                exc,
            )
            self.failed.emit(str(exc))
        else:
            self.logger.debug(
                "%s worker succeeded task_id=%s task=%s",
                self.task_log_prefix,
                self.task_id,
                self.task_name,
            )
            self.finished.emit(result)


class BackgroundTaskCallbacks(QObject):
    """Group callbacks used to deliver background task results."""

    def __init__(
        self,
        task_id,
        task_name,
        owner_ref,
        logger,
        task_log_prefix,
        started_at,
        on_finished,
        on_failed,
    ):
        super().__init__()
        self.task_id = task_id
        self.task_name = task_name
        self.owner_ref = owner_ref
        self.owner_alive = True
        self.logger = logger
        self.task_log_prefix = task_log_prefix
        self.started_at = started_at
        self.on_finished = on_finished
        self.on_failed = on_failed
        self.thread = None

    def bind_thread(self, thread):
        """Record the worker thread used to run this task."""

        self.thread = thread

    @Slot()
    def mark_owner_destroyed(self):
        """Prevent callbacks after the owning Qt object is destroyed."""

        self.owner_alive = False
        self.logger.debug(
            "%s owner destroyed task_id=%s task=%s",
            self.task_log_prefix,
            self.task_id,
            self.task_name,
        )

    def should_deliver(self, result_type):
        """Return whether callbacks may still be delivered to the owner."""

        if not self.owner_alive or self.owner_ref() is None:
            self.logger.debug(
                "%s %s ignored after owner destruction task_id=%s task=%s",
                self.task_log_prefix,
                result_type,
                self.task_id,
                self.task_name,
            )
            return False
        return True

    def complete_task(self):
        """Finalize task bookkeeping without delivering duplicate callbacks."""

        thread = self.thread
        if thread is not None and QThread.currentThread() is not thread:
            # Waiting from the worker itself would deadlock.  Delivery normally
            # runs on the UI thread, where joining guarantees deterministic
            # cleanup before a result callback starts another task.
            if thread.isRunning():
                thread.quit()
                thread.wait()
        self.cleanup()

    @Slot(object)
    def deliver_finished(self, result):
        """Deliver a background-task result when the owner is still alive."""

        elapsed = time.monotonic() - self.started_at
        self.logger.debug(
            "%s finished task_id=%s task=%s elapsed=%.3fs",
            self.task_log_prefix,
            self.task_id,
            self.task_name,
            elapsed,
        )
        self.complete_task()
        if self.should_deliver("success"):
            try:
                self.on_finished(result)
            except Exception:
                self.logger.exception(
                    "%s success callback failed task_id=%s task=%s",
                    self.task_log_prefix,
                    self.task_id,
                    self.task_name,
                )

    @Slot(str)
    def deliver_failed(self, message):
        """Deliver a background-task failure when the owner is still alive."""

        elapsed = time.monotonic() - self.started_at
        self.logger.debug(
            "%s failed task_id=%s task=%s elapsed=%.3fs message=%s",
            self.task_log_prefix,
            self.task_id,
            self.task_name,
            elapsed,
            message,
        )
        self.complete_task()
        if self.should_deliver("failure"):
            try:
                self.on_failed(message)
            except Exception:
                self.logger.exception(
                    "%s failure callback failed task_id=%s task=%s",
                    self.task_log_prefix,
                    self.task_id,
                    self.task_name,
                )

    @Slot()
    def cleanup(self):
        """Release resources and detach registered callbacks."""

        if _active_background_tasks.pop(self.task_id, None) is not None:
            self.logger.debug(
                "%s cleaned up task_id=%s task=%s",
                self.task_log_prefix,
                self.task_id,
                self.task_name,
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
    """Start background task."""

    task_id = next(_background_task_counter)
    task_name = getattr(func, "__name__", func.__class__.__name__)
    if logger is None:
        logger = logging.getLogger("mygui.background")
    logger.debug(
        "%s queued task_id=%s task=%s owner=%s",
        task_log_prefix,
        task_id,
        task_name,
        owner.__class__.__name__,
    )

    thread = QThread()
    worker = BackgroundTaskWorker(task_id, task_name, func, logger, task_log_prefix, *args, **kwargs)
    worker.moveToThread(thread)
    owner_ref = weakref.ref(owner)
    started_at = time.monotonic()
    callbacks = BackgroundTaskCallbacks(
        task_id,
        task_name,
        owner_ref,
        logger,
        task_log_prefix,
        started_at,
        on_finished,
        on_failed,
    )
    callbacks.bind_thread(thread)
    owner.destroyed.connect(callbacks.mark_owner_destroyed)

    task_record = (task_id, thread, worker, callbacks)
    _active_background_tasks[task_id] = task_record

    thread.started.connect(worker.run)
    worker.finished.connect(callbacks.deliver_finished)
    worker.failed.connect(callbacks.deliver_failed)
    worker.finished.connect(thread.quit)
    worker.failed.connect(thread.quit)
    thread.finished.connect(callbacks.cleanup)
    thread.start()
    return thread, worker
