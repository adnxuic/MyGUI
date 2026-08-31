"""Shared process and result helpers for MyGUI Agent Engineering checks."""

from __future__ import annotations

import ast
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from typing import Any, Iterable

import yaml
from jsonschema import Draft202012Validator


ROOT = Path(__file__).resolve().parents[2]
RESULT_DIR = ROOT / "build" / "agent-results"
EXPECTED_VERSIONS = {"matplotlib": "3.9.0", "PySide6": "6.7.1"}


class UniqueKeyLoader(yaml.SafeLoader):
    """Safe YAML loader that rejects duplicate mapping keys."""


def _construct_unique_mapping(loader, node, deep=False):
    mapping = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in mapping:
            raise ValueError(f"Duplicate YAML key: {key!r}")
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


UniqueKeyLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
    _construct_unique_mapping,
)


def load_yaml(path: Path) -> Any:
    return yaml.load(path.read_text(encoding="utf-8"), Loader=UniqueKeyLoader)


def load_task_map(root: Path = ROOT) -> dict[str, Any]:
    data = load_yaml(root / ".agents" / "task-map.yaml")
    if not isinstance(data, dict) or not isinstance(data.get("tasks"), dict):
        raise ValueError("task-map.yaml must contain a tasks mapping")
    return data


def discover_scanners(
    root: Path = ROOT,
) -> tuple[dict[str, Path], list[str]]:
    """Discover authored ScannerResult-v2 producers by stable scanner ID."""

    registry: dict[str, Path] = {}
    errors: list[str] = []
    scanner_root = root / ".agents" / "scanners"
    if not scanner_root.is_dir():
        return registry, errors
    for path in sorted(scanner_root.glob("*.py")):
        if path.name == "__init__.py":
            continue
        relative = path.relative_to(root).as_posix()
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=relative)
        except (OSError, SyntaxError, UnicodeError) as exc:
            errors.append(f"Cannot inspect scanner {relative}: {exc}")
            continue
        scanner_id = None
        for node in tree.body:
            if not isinstance(node, (ast.Assign, ast.AnnAssign)):
                continue
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            if not any(
                isinstance(target, ast.Name) and target.id == "SCANNER_ID"
                for target in targets
            ):
                continue
            value = node.value
            if isinstance(value, ast.Constant) and isinstance(value.value, str):
                scanner_id = value.value.strip()
            break
        if not scanner_id:
            errors.append(f"Scanner {relative} has no constant SCANNER_ID")
            continue
        if scanner_id in registry:
            errors.append(
                f"Duplicate scanner ID {scanner_id!r}: "
                f"{registry[scanner_id].relative_to(root).as_posix()} and {relative}"
            )
            continue
        registry[scanner_id] = path
    return registry, errors


def runtime_errors(*, require_gui: bool) -> list[str]:
    errors: list[str] = []
    if sys.version_info[:2] != (3, 12):
        errors.append(f"Python 3.12 is required; got {sys.version.split()[0]}")
    if require_gui:
        for package, expected in EXPECTED_VERSIONS.items():
            try:
                module = __import__(package)
                actual = str(module.__version__)
            except Exception as exc:  # pragma: no cover - environment failure
                errors.append(f"Cannot import {package}: {exc}")
                continue
            if actual != expected:
                errors.append(f"{package} {expected} is required; got {actual}")
    return errors


def run_step(
    step_id: str,
    command: Iterable[str],
    *,
    cwd: Path = ROOT,
    env: dict[str, str] | None = None,
    required: bool = True,
    timeout: int | None = None,
) -> dict[str, Any]:
    args = [str(part) for part in command]
    started = time.monotonic()
    merged_env = os.environ.copy()
    if env:
        merged_env.update(env)
    print(f"\n== {step_id} ==")
    print(" ".join(args))
    try:
        completed = subprocess.run(
            args,
            cwd=cwd,
            env=merged_env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=timeout,
            check=False,
        )
        output = completed.stdout or ""
        if output:
            print(output, end="" if output.endswith("\n") else "\n")
        status = "passed" if completed.returncode == 0 else "failed"
        evidence = output[-8000:]
    except FileNotFoundError as exc:
        status = "not_run"
        evidence = str(exc)
        print(evidence)
    except subprocess.TimeoutExpired as exc:
        status = "failed"
        evidence = f"Timed out after {timeout}s: {exc}"
        print(evidence)
    return {
        "id": step_id,
        "command": " ".join(args),
        "status": status,
        "required": required,
        "durationMs": round((time.monotonic() - started) * 1000, 3),
        "evidence": evidence,
    }


def failed_required(verification: Iterable[dict[str, Any]]) -> bool:
    return any(
        item.get("required") and item.get("status") != "passed"
        for item in verification
    )


def not_run_step(step_id: str, command: str, reason: str, *, required: bool = True) -> dict[str, Any]:
    return {
        "id": step_id,
        "command": command,
        "status": "not_run",
        "required": required,
        "durationMs": 0,
        "evidence": reason,
    }


def task_result(
    scope: str,
    verification: list[dict[str, Any]],
    *,
    changes: list[str] | None = None,
    findings: list[str] | None = None,
    architecture_impact: str = "No application architecture change.",
    persistence_impact: str = "No MyGUI project-schema change.",
    gray_boundaries: list[Any] | None = None,
    limitations: list[str] | None = None,
    remaining_risks: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "contractVersion": 1,
        "status": "failed" if failed_required(verification) else "completed",
        "scope": scope,
        "changes": changes or [],
        "findings": findings or [],
        "architectureImpact": architecture_impact,
        "persistenceImpact": persistence_impact,
        "verification": verification,
        "grayBoundaries": gray_boundaries or [],
        "limitations": limitations or [],
        "remainingRisks": remaining_risks or [],
    }


def write_result(result: dict[str, Any], output: str | Path | None, default_name: str) -> Path:
    schema = json.loads(
        (ROOT / ".agents" / "contracts" / "task-result.schema.json").read_text(encoding="utf-8")
    )
    validation_errors = sorted(
        Draft202012Validator(schema).iter_errors(result), key=lambda item: list(item.path)
    )
    if validation_errors:
        messages = "; ".join(item.message for item in validation_errors)
        raise ValueError(f"TaskResult does not match v1 contract: {messages}")
    path = Path(output) if output else RESULT_DIR / f"{default_name}.json"
    if not path.is_absolute():
        path = ROOT / path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"\nTask result: {path}")
    return path


def finish(result: dict[str, Any], output: str | Path | None, default_name: str) -> int:
    try:
        write_result(result, output, default_name)
    except OSError as exc:
        evidence = f"Cannot write requested TaskResult output: {exc}"
        print(evidence)
        result["verification"].append({
            "id": "task_result_output",
            "command": f"write TaskResult to {output}",
            "status": "failed",
            "required": True,
            "durationMs": 0,
            "evidence": evidence,
        })
        result["status"] = "failed"
        write_result(result, RESULT_DIR / f"{default_name}-write-failure.json", default_name)
        return 1
    return 1 if failed_required(result["verification"]) else 0


def python_unittest_step(step_id: str, modules: Iterable[str]) -> dict[str, Any]:
    return run_step(
        step_id,
        [sys.executable, "-m", "unittest", *modules, "-v"],
        env={"QT_QPA_PLATFORM": "offscreen"},
    )
