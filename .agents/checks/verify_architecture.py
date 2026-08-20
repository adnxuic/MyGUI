"""Run deterministic MyGUI architecture tests and DSH scanners."""

from __future__ import annotations

import argparse
import json
import os
import shutil

from jsonschema import Draft202012Validator

from _runner import ROOT, finish, not_run_step, python_unittest_step, run_step, task_result


PYTHON_MODULES = [
    "tests.test_matplotlib_boundaries",
    "tests.test_package_boundary",
    "tests.test_matplotlib_property_contract",
]


def _wsl_path(path) -> str:
    value = path.resolve().as_posix()
    return f"/mnt/{value[0].lower()}/{value[3:]}"


def _scanner_build_command() -> tuple[list[str], object]:
    scanner_root = ROOT / ".dsh" / "scanners"
    if os.name == "nt":
        node = shutil.which("node")
        compiler = scanner_root / "node_modules" / "typescript" / "bin" / "tsc"
        if node is not None and compiler.is_file():
            return [node, str(compiler), "-p", "tsconfig.cli.json"], scanner_root
        command = f"cd '{_wsl_path(scanner_root)}' && npm run build"
        return ["wsl", "-d", "Ubuntu", "bash", "-lc", command], ROOT
    return ["npm", "run", "build"], scanner_root


def _scanner_step(scanner_id: str, *, fail_on_gray: bool) -> tuple[dict, dict | None]:
    cli = ROOT / ".dsh" / "scanners" / "dist" / "cli" / "scan.js"
    output = ROOT / "build" / "agent-results" / f"{scanner_id.replace('.', '-')}.json"
    command = ["node", str(cli), str(ROOT), "--scanner", scanner_id, "--json-out", str(output)]
    if os.name == "nt" and shutil.which("node") is None:
        command = [
            "wsl", "-d", "Ubuntu", "bash", "-lc",
            f"cd '{_wsl_path(ROOT)}' && node .dsh/scanners/dist/cli/scan.js '{_wsl_path(ROOT)}' "
            f"--scanner '{scanner_id}' --json-out '{_wsl_path(output)}'",
        ]
    step = run_step(
        f"scanner:{scanner_id}",
        command,
        required=True,
    )
    payload = None
    if step["status"] == "passed":
        try:
            payload = json.loads(output.read_text(encoding="utf-8"))
            schema = json.loads(
                (ROOT / ".agents" / "contracts" / "scanner-result.schema.json").read_text(encoding="utf-8")
            )
            contract_errors = list(Draft202012Validator(schema).iter_errors(payload))
            if contract_errors:
                raise ValueError("; ".join(item.message for item in contract_errors))
            if payload.get("verdict") not in {"clean", "gray_boundary"}:
                step["status"] = "failed"
                step["evidence"] += f"\nBlocking scanner verdict: {payload.get('verdict')}"
            elif fail_on_gray and payload.get("verdict") == "gray_boundary":
                step["status"] = "failed"
                step["evidence"] += "\nUnresolved gray boundaries block an architecture audit."
        except Exception as exc:
            step["status"] = "failed"
            step["evidence"] += f"\nCannot read ScannerResult: {exc}"
    return step, payload


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
    gray = []
    findings = []
    if not args.skip_scanners:
        build_command, build_cwd = _scanner_build_command()
        build_step = run_step(
            "scanner_build", build_command, cwd=build_cwd, timeout=180,
        )
        verification.append(build_step)
        if build_step["status"] != "passed":
            for scanner_id in ("mygui.architecture", "mygui.qt-lifecycle"):
                verification.append(not_run_step(
                    f"scanner:{scanner_id}", "node dist/cli/scan.js", "Scanner build failed.",
                ))
        else:
            for scanner_id in ("mygui.architecture", "mygui.qt-lifecycle"):
                step, payload = _scanner_step(scanner_id, fail_on_gray=args.fail_on_gray)
                verification.append(step)
                if payload:
                    gray.extend(payload.get("grayBoundaries", []))
                    findings.extend(item.get("id", "") for item in payload.get("findings", []))
    result = task_result(
        "architecture", verification, findings=findings, gray_boundaries=gray,
        architecture_impact="Architecture boundaries were checked; gray candidates are preserved.",
    )
    return finish(result, args.json_out, "architecture")


if __name__ == "__main__":
    raise SystemExit(main())
