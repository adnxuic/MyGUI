"""Validate MyGUI Agent Core routing, rule catalog, and JSON contracts."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
from typing import Any

from jsonschema import Draft202012Validator

from _runner import ROOT, finish, load_task_map, load_yaml, task_result


REQUIRED_TASKS = {
    "add_figure_component", "modify_component_property", "schema_migration",
    "project_io_change", "debug_gui_regression", "architecture_audit",
    "evolve_architecture_rule", "fix_ci",
}
KNOWN_CHECKS = {
    "verify_agent_core", "verify_fast", "verify_component_contracts",
    "verify_architecture", "verify_project_io", "verify_full",
}
FORBIDDEN_IMPLEMENTATION_TOKENS = {
    "cordis_define", "cordis_run", "cordis_stop", "dynamicCordisRunner",
    "scanner-readonly.mjs",
}
COMPILED_PYTHON_SUFFIXES = {".pyc", ".pyo"}


def _agent_source_files(agents: Path):
    """Yield authored Agent Core files without generated Python bytecode."""
    for path in agents.rglob("*"):
        if not path.is_file():
            continue
        if "__pycache__" in path.parts or path.suffix.lower() in COMPILED_PYTHON_SUFFIXES:
            continue
        yield path


def _scanner_ids(root: Path) -> set[str]:
    ids: set[str] = set()
    scanners = root / ".dsh" / "scanners" / "src" / "scanners"
    for path in scanners.glob("*/scanner.ts"):
        text = path.read_text(encoding="utf-8")
        match = re.search(r"\bSCANNER_ID\s*=\s*['\"]([^'\"]+)['\"]", text)
        if match is None:
            match = re.search(r"\bid:\s*['\"]([^'\"]+)['\"]", text)
        if match:
            ids.add(match.group(1))
    return ids


def _module_path(root: Path, module: str) -> Path:
    return root / (module.replace(".", "/") + ".py")


def validate_task_routes(root: Path, task_map: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    agents = root / ".agents"
    tasks = task_map.get("tasks", {})
    if set(tasks) != REQUIRED_TASKS:
        errors.append(f"Task IDs must be exactly {sorted(REQUIRED_TASKS)!r}; got {sorted(tasks)!r}")
    scanner_ids = _scanner_ids(root)
    for task_id, route in tasks.items():
        skill_path = root / route.get("skill", "")
        if not skill_path.is_file():
            errors.append(f"{task_id}: missing skill {skill_path.relative_to(root)}")
        for key in ("architecture", "documentation"):
            for value in route.get(key, []):
                if not (root / value).is_file():
                    errors.append(f"{task_id}: missing {key} path {value}")
        for check in route.get("checks", []):
            if check not in KNOWN_CHECKS or not (agents / "checks" / f"{check}.py").is_file():
                errors.append(f"{task_id}: unknown or missing check {check}")
        for scanner in route.get("scanners", []):
            if scanner not in scanner_ids:
                errors.append(f"{task_id}: unknown scanner {scanner}")
        for module in route.get("focused_tests", []):
            if not _module_path(root, module).is_file():
                errors.append(f"{task_id}: missing focused test module {module}")
        if skill_path.is_file() and "CORE-" not in skill_path.read_text(encoding="utf-8"):
            errors.append(f"{task_id}: Skill does not reference a CORE-* invariant")
    return errors


def validate_agent_core(root: Path = ROOT) -> list[str]:
    errors: list[str] = []
    agents = root / ".agents"
    try:
        task_map = load_task_map(root)
        catalog = load_yaml(agents / "rule-catalog.yaml")
    except Exception as exc:
        return [str(exc)]

    for schema_path in sorted((agents / "contracts").glob("*.schema.json")):
        try:
            Draft202012Validator.check_schema(json.loads(schema_path.read_text(encoding="utf-8")))
        except Exception as exc:
            errors.append(f"Invalid JSON Schema {schema_path.relative_to(root)}: {exc}")

    try:
        schema = json.loads((agents / "contracts" / "task-map.schema.json").read_text(encoding="utf-8"))
        schema_errors = sorted(Draft202012Validator(schema).iter_errors(task_map), key=lambda item: list(item.path))
        errors.extend(f"task-map schema: {item.message}" for item in schema_errors)
    except Exception as exc:
        errors.append(f"Cannot validate task-map schema: {exc}")

    errors.extend(validate_task_routes(root, task_map))

    rules = catalog.get("rules", []) if isinstance(catalog, dict) else []
    rule_ids = [entry.get("id") for entry in rules if isinstance(entry, dict)]
    duplicates = sorted({item for item in rule_ids if rule_ids.count(item) > 1})
    if duplicates:
        errors.append(f"Duplicate rule IDs: {duplicates!r}")
    agents_text = (root / "AGENTS.md").read_text(encoding="utf-8")
    for entry in rules:
        rule_id = entry.get("id", "")
        source = str(entry.get("source", "")).split("#", 1)[0]
        source_path = root / source
        if not source_path.is_file():
            errors.append(f"{rule_id}: missing rule source {source}")
        elif rule_id.startswith("CORE-") and rule_id not in agents_text:
            errors.append(f"{rule_id}: global rule is absent from AGENTS.md")
        elif not rule_id.startswith("CORE-") and rule_id not in source_path.read_text(encoding="utf-8"):
            errors.append(f"{rule_id}: rule ID is absent from {source}")
        if not entry.get("enforcement"):
            errors.append(f"{rule_id}: no enforcement declared")

    for path in _agent_source_files(agents):
        if path.resolve() == Path(__file__).resolve():
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        for token in FORBIDDEN_IMPLEMENTATION_TOKENS:
            if token in text:
                errors.append(f"{path.relative_to(root)} duplicates DSH implementation token {token}")

    size = (root / "AGENTS.md").stat().st_size
    if not 8 * 1024 <= size <= 12 * 1024:
        errors.append(f"AGENTS.md must stay between 8 and 12 KiB; got {size} bytes")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json-out")
    args = parser.parse_args()
    errors = validate_agent_core()
    status = "passed" if not errors else "failed"
    evidence = "Agent Core is consistent." if not errors else "\n".join(errors)
    print(evidence)
    verification = [{
        "id": "verify_agent_core", "command": "internal Agent Core validation",
        "status": status, "required": True, "durationMs": 0, "evidence": evidence,
    }]
    return finish(task_result("agent-core", verification, findings=errors), args.json_out, "agent-core")


if __name__ == "__main__":
    raise SystemExit(main())
