"""Run focused application-settings storage, service, session, and contract tests."""

from __future__ import annotations

import argparse
import re
from pathlib import Path

from _runner import (
    ROOT,
    finish,
    not_run_step,
    python_unittest_step,
    runtime_errors,
    task_result,
)


# Source of truth for the focused settings suite. Integrator also copies these
# stems into verify_full.APPLICATION_TEST_MODULES.
APPLICATION_SETTINGS_TEST_MODULES = [
    "tests.test_application_settings_contracts",
    "tests.test_application_settings_storage",
    "tests.test_application_settings_service",
    "tests.test_application_settings_session",
    "tests.test_application_settings_new_figure",
    "tests.test_application_settings_pages",
    "tests.test_application_settings_center",
    "tests.test_application_settings_center_c",
    "tests.test_color_library",
    "tests.test_figure_export",
    "tests.test_gui_layout",
    "tests.test_application_theme",
    "tests.test_application_theme_transactions",
    "tests.test_application_theme_chrome",
    "tests.test_application_theme_qss",
]

# GUI-heavy modules run in their own unittest processes so Qt/QApplication
# state from Settings Center, export, layout, and theme tests cannot deadlock.
APPLICATION_SETTINGS_ISOLATED_MODULES = frozenset({
    "tests.test_color_library",
    "tests.test_figure_export",
    "tests.test_gui_layout",
    "tests.test_application_theme",
    "tests.test_application_theme_transactions",
    "tests.test_application_theme_chrome",
    "tests.test_application_theme_qss",
})


def _module_path(root: Path, module: str) -> Path:
    return root / (module.replace(".", "/") + ".py")


def _discover_extra_modules(root: Path) -> list[str]:
    expected = set(APPLICATION_SETTINGS_TEST_MODULES)
    extras: list[str] = []
    tests_dir = root / "tests"
    if not tests_dir.is_dir():
        return extras
    for path in sorted(tests_dir.glob("test_application_settings*.py")):
        module = f"tests.{path.stem}"
        if module not in expected:
            extras.append(module)
    return extras


def _all_tests_skipped(evidence: str) -> bool:
    ran_match = re.search(r"Ran (\d+) tests?", evidence)
    if ran_match is None:
        return False
    ran = int(ran_match.group(1))
    if ran == 0:
        return True
    skipped_match = re.search(r"skipped=(\d+)", evidence)
    if skipped_match is None:
        return False
    return int(skipped_match.group(1)) == ran


def _honest_unittest_step(step_id: str, modules: list[str]) -> dict:
    step = python_unittest_step(step_id, modules)
    if step["status"] == "passed" and _all_tests_skipped(str(step.get("evidence", ""))):
        step["status"] = "not_run"
        step["evidence"] = (
            f"{step['evidence']}\n"
            "All discovered tests were skipped or empty; reporting not_run, not pass."
        )
    return step


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json-out")
    args = parser.parse_args()
    verification = []
    errors = runtime_errors(require_gui=True)
    verification.append({
        "id": "runtime",
        "command": "validate Python/Matplotlib/PySide6 versions",
        "status": "failed" if errors else "passed",
        "required": True,
        "durationMs": 0,
        "evidence": "\n".join(errors) if errors else "Runtime versions match.",
    })

    present: list[str] = []
    missing: list[str] = []
    for module in APPLICATION_SETTINGS_TEST_MODULES:
        if _module_path(ROOT, module).is_file():
            present.append(module)
        else:
            missing.append(module)

    extras = [
        module for module in _discover_extra_modules(ROOT)
        if _module_path(ROOT, module).is_file()
    ]
    runnable = list(dict.fromkeys([*present, *extras]))

    for module in missing:
        verification.append(not_run_step(
            f"unittest:{module}",
            f"{module} (unittest)",
            f"Test module {module} is not on disk yet; not treating as pass.",
        ))

    if runnable:
        shared = [
            module for module in runnable
            if module not in APPLICATION_SETTINGS_ISOLATED_MODULES
        ]
        isolated = [
            module for module in runnable
            if module in APPLICATION_SETTINGS_ISOLATED_MODULES
        ]
        if shared:
            verification.append(_honest_unittest_step("application_settings_tests", shared))
        for module in isolated:
            verification.append(_honest_unittest_step(f"unittest:{module}", [module]))
    else:
        verification.append(not_run_step(
            "application_settings_tests",
            "python -m unittest <application settings modules>",
            "No application-settings unittest modules exist yet.",
        ))

    findings = [f"Missing unittest module: {module}" for module in missing]
    if extras:
        findings.append("Discovered extra modules: " + ", ".join(extras))

    result = task_result(
        "application-settings",
        verification,
        findings=findings,
        architecture_impact=(
            "Application-settings contracts were checked; project schema v15 is unchanged."
        ),
        persistence_impact="No MyGUI project-schema change.",
        limitations=[
            "This check does not start MATLAB, MCR, or TeX.",
            "verify_agent_core and APPLICATION_TEST_MODULES are Integrator-owned.",
        ],
        remaining_risks=[
            "Missing focused modules keep this check from completing.",
            "Skipped-only unittest runs are reported as not_run.",
        ],
    )
    return finish(result, args.json_out, "application-settings")


if __name__ == "__main__":
    raise SystemExit(main())
