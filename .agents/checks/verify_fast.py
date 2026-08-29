"""Fast routed MyGUI development verification."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

from _runner import finish, load_task_map, python_unittest_step, run_step, runtime_errors, task_result


# GUI-heavy modules keep process isolation. Packing them with Settings Center
# or each other in one unittest process can hang Qt offscreen runs.
_ISOLATED_FOCUSED_MODULES = frozenset({
    "tests.test_application_settings_component_creation",
    "tests.test_application_settings_axes_creation",
    "tests.test_color_library",
    "tests.test_figure_export",
    "tests.test_gui_layout",
    "tests.test_application_theme",
    "tests.test_application_theme_transactions",
    "tests.test_application_theme_chrome",
    "tests.test_application_theme_qss",
    "tests.test_field_2d_component",
    "tests.test_errorbar_component",
})


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
    compile_targets = ["mygui", "tests", "main.py"]
    ruff_targets = ["mygui", "tests", ".agents/checks", "main.py"]
    smoke = Path(".agents/desktop_smoke")
    if smoke.is_dir():
        compile_targets.append(str(smoke))
        ruff_targets.insert(-1, str(smoke))
    verification.append(run_step(
        "compileall", [sys.executable, "-m", "compileall", "-q", *compile_targets]
    ))
    verification.append(run_step(
        "ruff", [sys.executable, "-m", "ruff", "check", *ruff_targets]
    ))
    modules = tasks[args.task]["focused_tests"]
    if modules:
        shared = [module for module in modules if module not in _ISOLATED_FOCUSED_MODULES]
        isolated = [module for module in modules if module in _ISOLATED_FOCUSED_MODULES]
        if shared:
            verification.append(python_unittest_step("focused_tests", shared))
        for module in isolated:
            verification.append(python_unittest_step(f"focused_tests:{module}", [module]))
    result = task_result(f"fast:{args.task}", verification)
    return finish(result, args.json_out, f"fast-{args.task}")


if __name__ == "__main__":
    raise SystemExit(main())
