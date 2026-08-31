"""Run focused schema, materialization, project IO, and round-trip tests."""

from __future__ import annotations

import argparse

from _runner import finish, python_unittest_step, runtime_errors, task_result


MODULES = [
    "tests.test_project_schema",
    "tests.test_project_io",
    "tests.test_project_object_roundtrip",
    "tests.test_component_materializers",
    "tests.test_gui_file_flow",
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
    verification.append(python_unittest_step("project_io_contracts", MODULES))
    return finish(
        task_result(
            "project-io",
            verification,
            persistence_impact=(
                "Schema-v23 behavior, strict content-preserving v22 migration, "
                "and the chained v10-v21 migrations were verified."
            ),
        ),
        args.json_out,
        "project-io",
    )


if __name__ == "__main__":
    raise SystemExit(main())
