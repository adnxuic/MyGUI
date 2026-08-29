"""Run deterministic MyGUI architecture tests."""

from __future__ import annotations

import argparse

from _runner import finish, python_unittest_step, task_result


PYTHON_MODULES = [
    "tests.test_matplotlib_boundaries",
    "tests.test_package_boundary",
    "tests.test_matplotlib_property_contract",
]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-python", action="store_true")
    parser.add_argument("--skip-scanners", action="store_true")
    parser.add_argument("--fail-on-gray", action="store_true")
    parser.add_argument("--json-out")
    args = parser.parse_args()
    verification = []
    if not args.skip_python:
        verification.append(python_unittest_step("architecture_boundary_tests", PYTHON_MODULES))
    result = task_result(
        "architecture", verification, findings=[], gray_boundaries=[],
        architecture_impact="Architecture boundaries were checked.",
    )
    return finish(result, args.json_out, "architecture")


if __name__ == "__main__":
    raise SystemExit(main())
