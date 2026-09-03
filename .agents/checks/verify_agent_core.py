"""Validate MyGUI Agent Core routing, rule catalog, and JSON contracts."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
from typing import Any

from jsonschema import Draft202012Validator

from _runner import (
    ROOT,
    discover_scanners,
    finish,
    load_task_map,
    load_yaml,
    task_result,
)


REQUIRED_TASKS = {
    "add_figure_component", "modify_component_property", "schema_migration",
    "project_io_change", "debug_gui_regression", "architecture_audit",
    "evolve_architecture_rule", "fix_ci", "modify_application_setting",
    "maintain_agent_core", "modernize_ui_components",
}
KNOWN_CHECKS = {
    "verify_agent_core", "verify_fast", "verify_component_contracts",
    "verify_architecture", "verify_project_io", "verify_full",
    "verify_application_settings",
}
COMPILED_PYTHON_SUFFIXES = {".pyc", ".pyo"}
CORE_RULE_PATTERN = re.compile(r"\bCORE-[A-Z0-9-]+\b")
MARKDOWN_HEADING_PATTERN = re.compile(r"^#{1,6}\s+(.+?)\s*#*\s*$", re.MULTILINE)


def _agent_source_files(agents: Path):
    """Yield authored Agent Core files without generated Python bytecode."""
    for path in agents.rglob("*"):
        if not path.is_file():
            continue
        if "__pycache__" in path.parts or path.suffix.lower() in COMPILED_PYTHON_SUFFIXES:
            continue
        yield path


def _scanner_ids(root: Path) -> set[str]:
    registry, _errors = discover_scanners(root)
    return set(registry)


def _module_path(root: Path, module: str) -> Path:
    return root / (module.replace(".", "/") + ".py")


def _normalized_lf_size(path: Path) -> int:
    text = path.read_text(encoding="utf-8").replace("\r\n", "\n").replace("\r", "\n")
    return len(text.encode("utf-8"))


def _validate_agents_size(path: Path) -> list[str]:
    size = _normalized_lf_size(path)
    if size > 8 * 1024:
        return [f"AGENTS.md must not exceed 8 KiB after LF normalization; got {size} bytes"]
    return []


def _markdown_slug(value: str) -> str:
    value = re.sub(r"[^\w\- ]", "", value.strip().lower(), flags=re.UNICODE)
    return re.sub(r"[ -]+", "-", value).strip("-")


def _markdown_anchors(text: str) -> set[str]:
    anchors: set[str] = set()
    counts: dict[str, int] = {}
    for match in MARKDOWN_HEADING_PATTERN.finditer(text):
        base = _markdown_slug(match.group(1))
        count = counts.get(base, 0)
        counts[base] = count + 1
        anchors.add(base if count == 0 else f"{base}-{count}")
    return anchors


def _validate_rule_catalog(root: Path, catalog: dict[str, Any], agents_text: str) -> list[str]:
    errors: list[str] = []
    rules = catalog.get("rules", []) if isinstance(catalog, dict) else []
    entries = [entry for entry in rules if isinstance(entry, dict)]
    rule_ids = [str(entry.get("id", "")) for entry in entries]
    duplicates = sorted({item for item in rule_ids if rule_ids.count(item) > 1})
    if duplicates:
        errors.append(f"Duplicate rule IDs: {duplicates!r}")

    root_core_ids = set(CORE_RULE_PATTERN.findall(agents_text))
    catalog_core_ids = {rule_id for rule_id in rule_ids if rule_id.startswith("CORE-")}
    missing_from_root = sorted(catalog_core_ids - root_core_ids)
    unregistered_in_root = sorted(root_core_ids - catalog_core_ids)
    if missing_from_root:
        errors.append(f"Global rules absent from AGENTS.md: {missing_from_root!r}")
    if unregistered_in_root:
        errors.append(f"Unregistered global rules in AGENTS.md: {unregistered_in_root!r}")

    scanner_ids = _scanner_ids(root)
    for entry in entries:
        rule_id = str(entry.get("id", ""))
        source_ref = str(entry.get("source", ""))
        source, separator, anchor = source_ref.partition("#")
        source_path = root / source
        if not separator:
            errors.append(f"{rule_id}: rule source must include a Markdown anchor")
        if not source_path.is_file():
            errors.append(f"{rule_id}: missing rule source {source}")
        else:
            source_text = source_path.read_text(encoding="utf-8")
            if separator and anchor not in _markdown_anchors(source_text):
                errors.append(f"{rule_id}: missing source anchor #{anchor} in {source}")
            if rule_id not in source_text:
                errors.append(f"{rule_id}: rule ID is absent from {source}")

        enforcement = entry.get("enforcement", [])
        if not enforcement:
            errors.append(f"{rule_id}: no enforcement declared")
        for target in enforcement:
            if str(target).startswith("tests."):
                if not _module_path(root, str(target)).is_file():
                    errors.append(f"{rule_id}: missing enforcement test module {target}")
            elif target not in scanner_ids:
                errors.append(f"{rule_id}: unknown enforcement target {target}")
    return errors


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

    _scanner_registry, scanner_errors = discover_scanners(root)
    errors.extend(scanner_errors)

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

    try:
        schema = json.loads((agents / "contracts" / "rule-catalog.schema.json").read_text(encoding="utf-8"))
        schema_errors = sorted(Draft202012Validator(schema).iter_errors(catalog), key=lambda item: list(item.path))
        errors.extend(f"rule-catalog schema: {item.message}" for item in schema_errors)
    except Exception as exc:
        errors.append(f"Cannot validate rule-catalog schema: {exc}")

    errors.extend(validate_task_routes(root, task_map))

    agents_text = (root / "AGENTS.md").read_text(encoding="utf-8")
    errors.extend(_validate_rule_catalog(root, catalog, agents_text))

    errors.extend(_validate_agents_size(root / "AGENTS.md"))
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
