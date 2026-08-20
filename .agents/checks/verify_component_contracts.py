"""Run the focused component declaration and editor contract suite."""

from __future__ import annotations

import argparse

from _runner import finish, python_unittest_step, runtime_errors, task_result


MODULES = [
    "tests.test_component_controllers",
    "tests.test_component_materializers",
    "tests.test_component_inspector",
    "tests.test_component_editors",
    "tests.test_matplotlib_property_contract",
]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json-out")
    args = parser.parse_args()
    errors = runtime_errors(require_gui=True)
    verification = [{
        "id": "runtime", "command": "validate runtime versions",
        "status": "failed" if errors else "passed", "required": True,
        "durationMs": 0, "evidence": "\n".join(errors) if errors else "Runtime versions match.",
    }]
    verification.append(python_unittest_step("component_contracts", MODULES))
    return finish(task_result("component-contracts", verification), args.json_out, "component-contracts")


if __name__ == "__main__":
    raise SystemExit(main())
