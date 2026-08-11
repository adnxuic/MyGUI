"""Run child processes with bounded input, output, time, and tree cleanup."""

from __future__ import annotations

from dataclasses import dataclass
import os
import signal
import subprocess
import threading
import time
from typing import Mapping, Sequence


@dataclass(frozen=True, slots=True)
class BoundedProcessResult:
    """Captured bounded process result."""

    args: tuple[str, ...]
    returncode: int
    stdout: bytes
    stderr: bytes


class ProcessOutputLimitExceeded(RuntimeError):
    """Raised when a child writes more output than the configured budget."""


def _terminate_process_tree(process: subprocess.Popen) -> None:
    if process.poll() is not None:
        return
    if os.name == "nt":
        try:
            subprocess.run(
                [
                    "taskkill",
                    "/PID",
                    str(process.pid),
                    "/T",
                    "/F",
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=5,
                check=False,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except (OSError, subprocess.SubprocessError):
            process.kill()
    else:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except OSError:
            process.kill()


def run_bounded_process(
    args: Sequence[str],
    *,
    input_bytes: bytes = b"",
    cwd: str | None = None,
    env: Mapping[str, str] | None = None,
    timeout: float,
    max_input_bytes: int,
    max_output_bytes: int,
) -> BoundedProcessResult:
    """Run a process while retaining at most ``max_output_bytes`` per stream."""

    if len(input_bytes) > max_input_bytes:
        raise ValueError("External process input exceeds the configured budget.")
    command = tuple(str(item) for item in args)
    creationflags = 0
    popen_kwargs = {}
    if os.name == "nt":
        creationflags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    else:
        popen_kwargs["start_new_session"] = True
    process = subprocess.Popen(
        command,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=cwd,
        env=None if env is None else dict(env),
        creationflags=creationflags,
        **popen_kwargs,
    )
    buffers = {"stdout": bytearray(), "stderr": bytearray()}
    overflow = threading.Event()

    def read_stream(name: str, stream) -> None:
        try:
            while True:
                chunk = stream.read(64 * 1024)
                if not chunk:
                    return
                remaining = max_output_bytes + 1 - len(buffers[name])
                if remaining > 0:
                    buffers[name].extend(chunk[:remaining])
                if len(buffers[name]) > max_output_bytes:
                    overflow.set()
                    return
        finally:
            stream.close()

    def write_input() -> None:
        try:
            if input_bytes:
                process.stdin.write(input_bytes)
                process.stdin.flush()
        except (BrokenPipeError, OSError):
            pass
        finally:
            process.stdin.close()

    readers = [
        threading.Thread(
            target=read_stream,
            args=(name, stream),
            daemon=True,
        )
        for name, stream in (
            ("stdout", process.stdout),
            ("stderr", process.stderr),
        )
    ]
    writer = threading.Thread(target=write_input, daemon=True)
    for thread in readers:
        thread.start()
    writer.start()

    deadline = time.monotonic() + timeout
    timed_out = False
    while process.poll() is None:
        if overflow.is_set():
            _terminate_process_tree(process)
            break
        if time.monotonic() >= deadline:
            timed_out = True
            _terminate_process_tree(process)
            break
        time.sleep(0.01)
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()
    writer.join(timeout=1)
    for thread in readers:
        thread.join(timeout=1)

    if timed_out:
        raise subprocess.TimeoutExpired(command, timeout)
    if overflow.is_set():
        raise ProcessOutputLimitExceeded(
            "External process output exceeds the configured budget."
        )
    return BoundedProcessResult(
        command,
        int(process.returncode),
        bytes(buffers["stdout"]),
        bytes(buffers["stderr"]),
    )
