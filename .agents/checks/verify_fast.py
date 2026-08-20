"""Fast routed MyGUI development verification."""

from __future__ import annotations

import argparse
import sys

from _runner import finish, load_task_map, python_unittest_step, run_step, runtime_errors, task_result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--task", required=True)
    parser.add_argument("--json-out")
    args = parser.parse_args()
    tasks = load_task_map()["tasks"]
    if args.task not in tasks:
        parser.error(f"unknown task {args.task!r}; choose from {', '.join(sorted(tasks))}")

    verification = []
    errors = runtime_errors(require_gui=True)
    verification.append({
        "id": "runtime", "command": "validate Python/Matplotlib/PySide6 versions",
        "status": "failed" if errors else "passed", "required": True,
        "durationMs": 0, "evidence": "\n".join(errors) if errors else "Runtime versions match.",
    })
    verification.append(run_step(
        "compileall", [sys.executable, "-m", "compileall", "-q", "mygui", "tests", "main.py"]
    ))
    verification.append(run_step(
        "ruff", [sys.executable, "-m", "ruff", "check", "mygui", "tests", ".agents/checks", "main.py"]
    ))
    modules = tasks[args.task]["focused_tests"]
    if modules:
        verification.append(python_unittest_step("focused_tests", modules))
    result = task_result(f"fast:{args.task}", verification)
    return finish(result, args.json_out, f"fast-{args.task}")


if __name__ == "__main__":
    raise SystemExit(main())
