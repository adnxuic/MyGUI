"""Run every registered MyGUI CORE enforcement target deterministically."""

from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
import time

from jsonschema import Draft202012Validator

from _runner import (
    RESULT_DIR,
    ROOT,
    discover_scanners,
    finish,
    load_yaml,
    python_unittest_step,
    task_result,
)


def catalog_enforcement(root: Path = ROOT) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Return the complete, de-duplicated CORE test/scanner enforcement set."""

    catalog = load_yaml(root / ".agents" / "rule-catalog.yaml")
    python_modules: set[str] = set()
    scanner_ids: set[str] = set()
    for entry in catalog.get("rules", []):
        if not str(entry.get("id", "")).startswith("CORE-"):
            continue
        for target in entry.get("enforcement", []):
            target = str(target)
            if target.startswith("tests."):
                python_modules.add(target)
            else:
                scanner_ids.add(target)
    return tuple(sorted(python_modules)), tuple(sorted(scanner_ids))


def _load_scanner(path: Path, scanner_id: str):
    module_name = "_mygui_scanner_" + scanner_id.replace(".", "_").replace("-", "_")
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load scanner {scanner_id!r} from {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def scanner_step(
    scanner_id: str,
    *,
    root: Path = ROOT,
    fail_on_gray: bool = False,
) -> tuple[dict, dict | None]:
    """Execute and validate one ScannerResult-v2 producer."""

    started = time.monotonic()
    command = f"scanner:{scanner_id}"
    try:
        registry, discovery_errors = discover_scanners(root)
        if discovery_errors:
            raise ValueError("; ".join(discovery_errors))
        path = registry.get(scanner_id)
        if path is None:
            raise ValueError(f"Unknown registered scanner {scanner_id!r}")
        module = _load_scanner(path, scanner_id)
        if getattr(module, "SCANNER_ID", None) != scanner_id:
            raise ValueError(f"Scanner {path} published a mismatched ID")
        scan = getattr(module, "scan", None)
        if not callable(scan):
            raise ValueError(f"Scanner {path} has no callable scan(root)")
        result = scan(root)
        schema = json.loads(
            (root / ".agents" / "contracts" / "scanner-result.schema.json")
            .read_text(encoding="utf-8")
        )
        validation_errors = sorted(
            Draft202012Validator(schema).iter_errors(result),
            key=lambda item: list(item.path),
        )
        if validation_errors:
            raise ValueError(
                "ScannerResult v2 validation failed: "
                + "; ".join(item.message for item in validation_errors)
            )
        output = RESULT_DIR / "scanners" / f"{scanner_id}.json"
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            json.dumps(result, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        try:
            evidence_path = output.relative_to(root).as_posix()
        except ValueError:
            evidence_path = str(output)
        gray_count = len(result["grayBoundaries"])
        failed = (
            result["status"] != "completed"
            or result["verdict"] in {"violation", "unknown"}
            or (fail_on_gray and gray_count > 0)
        )
        evidence = (
            f"verdict={result['verdict']}; findings={len(result['findings'])}; "
            f"gray={gray_count}; errors={len(result['errors'])}; "
            f"evidence={evidence_path}"
        )
        return ({
            "id": command,
            "command": command,
            "status": "failed" if failed else "passed",
            "required": True,
            "durationMs": round((time.monotonic() - started) * 1000, 3),
            "evidence": evidence,
        }, result)
    except Exception as exc:
        return ({
            "id": command,
            "command": command,
            "status": "failed",
            "required": True,
            "durationMs": round((time.monotonic() - started) * 1000, 3),
            "evidence": str(exc),
        }, None)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-python", action="store_true")
    parser.add_argument("--skip-scanners", action="store_true")
    parser.add_argument("--fail-on-gray", action="store_true")
    parser.add_argument("--json-out")
    args = parser.parse_args()
    verification = []
    findings: list[str] = []
    gray_boundaries: list[dict] = []
    limitations: list[str] = []
    python_modules, scanner_ids = catalog_enforcement()
    if not args.skip_python:
        for module in python_modules:
            verification.append(
                python_unittest_step(f"core_enforcement:{module}", [module])
            )
    else:
        limitations.append("Registered Python enforcement was explicitly skipped.")
    if not args.skip_scanners:
        for scanner_id in scanner_ids:
            step, scanner_result = scanner_step(
                scanner_id,
                fail_on_gray=args.fail_on_gray,
            )
            verification.append(step)
            if scanner_result is None:
                continue
            findings.extend(
                f"{item['ruleId']}: {item['file']}:{item.get('line', 1)}: "
                f"{item['title']}"
                for item in scanner_result["findings"]
            )
            gray_boundaries.extend(scanner_result["grayBoundaries"])
    else:
        limitations.append("Registered architecture scanners were explicitly skipped.")
    result = task_result(
        "architecture",
        verification,
        findings=findings,
        gray_boundaries=gray_boundaries,
        limitations=limitations,
        architecture_impact=(
            f"Checked {len(python_modules)} registered Python enforcement modules "
            f"and {len(scanner_ids)} registered scanners."
        ),
    )
    return finish(result, args.json_out, "architecture")


if __name__ == "__main__":
    raise SystemExit(main())
