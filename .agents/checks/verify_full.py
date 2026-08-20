"""Canonical full verification profiles for application and Agent Engineering."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys

from _runner import ROOT, finish, run_step, runtime_errors, task_result


CRITICAL_FILES = [
    "mygui/project_io.py",
    "mygui/widgets/figure_canvas/component_materializers.py",
    "mygui/widgets/figure_canvas/project_metadata.py",
    "mygui/widgets/figure_canvas/py_figure_canves.py",
]


def _application_steps() -> list[dict]:
    verification = []
    errors = runtime_errors(require_gui=True)
    verification.append({
        "id": "runtime", "command": "validate Python/Matplotlib/PySide6 versions",
        "status": "failed" if errors else "passed", "required": True,
        "durationMs": 0, "evidence": "\n".join(errors) if errors else "Runtime versions match.",
    })
    verification.append(run_step(
        "compileall", [sys.executable, "-m", "compileall", "-q", "mygui", "tests", "main.py"]
    ))
    verification.append(run_step(
        "ruff", [sys.executable, "-m", "ruff", "check", "mygui", "tests", ".agents/checks", "main.py"]
    ))
    verification.append(run_step(
        "unittest_coverage",
        [sys.executable, "-m", "coverage", "run", "-m", "unittest", "discover", "-s", "tests", "-v"],
        env={"QT_QPA_PLATFORM": "offscreen", "MPLBACKEND": "qtagg"},
        timeout=1800,
    ))
    verification.append(run_step("coverage_global", [sys.executable, "-m", "coverage", "report", "--fail-under=74"]))
    verification.append(run_step("coverage_critical", [sys.executable, "-m", "coverage", "report", "--fail-under=80", *CRITICAL_FILES]))
    verification.append(run_step(
        "coverage_json", [sys.executable, "-m", "coverage", "json", "-o", "build/agent-results/coverage.json"]
    ))
    verification.append(run_step("agent_core", [sys.executable, ".agents/checks/verify_agent_core.py"]))
    return verification


def _agent_steps() -> list[dict]:
    verification = [run_step("agent_core", [sys.executable, ".agents/checks/verify_agent_core.py"])]
    command = ["bash", ".dsh/scripts/verify.sh", "--quiet"]
    if os.name == "nt":
        value = Path(ROOT).resolve().as_posix()
        wsl_root = f"/mnt/{value[0].lower()}/{value[3:]}"
        command = ["wsl", "-d", "Ubuntu", "bash", "-lc", f"cd '{wsl_root}' && bash .dsh/scripts/verify.sh --quiet"]
    verification.append(run_step("dsh_deterministic", command, timeout=1800))
    verification.append(run_step(
        "architecture_scanners",
        [sys.executable, ".agents/checks/verify_architecture.py", "--skip-python"],
        timeout=300,
    ))
    return verification


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", choices=["application", "agent-engineering", "local"], required=True)
    parser.add_argument("--json-out")
    args = parser.parse_args()
    verification = []
    if args.profile in {"application", "local"}:
        verification.extend(_application_steps())
    if args.profile in {"agent-engineering", "local"}:
        verification.extend(_agent_steps())
    if args.profile == "local":
        verification.append(run_step("mkdocs_strict", [sys.executable, "-m", "mkdocs", "build", "--strict"]))
    result = task_result(
        f"full:{args.profile}", verification,
        architecture_impact="Shared Agent Engineering and application gates executed.",
        persistence_impact="MyGUI schema-v11 behavior is verified.",
    )
    return finish(result, args.json_out, f"full-{args.profile}")


if __name__ == "__main__":
    raise SystemExit(main())
