"""Local Windows desktop smoke: open windows, click, and capture screenshots.

This check is not part of verify_full / APPLICATION_TEST_MODULES. It must run
on an interactive Windows session. Do not set QT_QPA_PLATFORM=offscreen.

    E:\\PycharmProjects\\ven\\pyside6_env\\Scripts\\python.exe .agents/checks/verify_desktop_smoke.py
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys

from _runner import ROOT, failed_required, finish, run_step, runtime_errors, task_result

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
AGENTS = ROOT / ".agents"
if str(AGENTS) not in sys.path:
    sys.path.insert(0, str(AGENTS))

from desktop_smoke.catalog import GROUPS  # noqa: E402
from desktop_smoke.runner import run_smoke  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run MyGUI desktop smoke (windows, clicks, screenshots)."
    )
    parser.add_argument("--json-out")
    parser.add_argument(
        "--only",
        help="Comma-separated groups: " + ",".join(GROUPS),
    )
    parser.add_argument(
        "--all-styles",
        action="store_true",
        help="Open every Style gallery dialog instead of the default sample.",
    )
    parser.add_argument(
        "--out",
        default=str(ROOT / "build" / "agent-results" / "desktop-smoke"),
        help="Evidence directory for screenshots and summary.json",
    )
    parser.add_argument(
        "--allow-offscreen",
        action="store_true",
        help="Allow QT_QPA_PLATFORM=offscreen (not true desktop smoke).",
    )
    args = parser.parse_args()

    platform = str(os.environ.get("QT_QPA_PLATFORM", "")).strip().lower()
    if platform == "offscreen" and not args.allow_offscreen:
        parser.error(
            "QT_QPA_PLATFORM=offscreen is not desktop smoke. Unset it, or pass "
            "--allow-offscreen for grab-only debugging."
        )

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
    verification.append(run_step(
        "compileall",
        [
            sys.executable, "-m", "compileall", "-q",
            str(AGENTS / "desktop_smoke"),
            str(AGENTS / "checks" / "verify_desktop_smoke.py"),
        ],
    ))
    verification.append(run_step(
        "ruff",
        [
            sys.executable, "-m", "ruff", "check",
            str(AGENTS / "desktop_smoke"),
            str(AGENTS / "checks" / "verify_desktop_smoke.py"),
        ],
    ))
    if failed_required(verification):
        result = task_result("desktop_smoke", verification)
        return finish(result, args.json_out, "desktop-smoke")

    groups = None
    if args.only:
        groups = [part.strip() for part in args.only.split(",") if part.strip()]
    output_dir = Path(args.out)
    if not output_dir.is_absolute():
        output_dir = ROOT / output_dir

    try:
        summary = run_smoke(
            output_dir,
            groups=groups,
            all_styles=bool(args.all_styles),
        )
        failed = summary.get("status") != "passed"
        evidence = (
            f"status={summary.get('status')} "
            f"screenshots={summary.get('screenshotCount')} "
            f"summary={output_dir / 'summary.json'}"
        )
        if failed:
            errors = [
                f"{item['id']}: {item.get('error')}"
                for item in summary.get("scenarios", [])
                if item.get("status") == "failed"
            ]
            evidence = evidence + "\n" + "\n".join(errors)
        verification.append({
            "id": "desktop_smoke",
            "command": "open windows, click controls, capture screenshots",
            "status": "failed" if failed else "passed",
            "required": True,
            "durationMs": 0,
            "evidence": evidence,
        })
    except Exception as exc:  # noqa: BLE001 — surface as a required step
        verification.append({
            "id": "desktop_smoke",
            "command": "open windows, click controls, capture screenshots",
            "status": "failed",
            "required": True,
            "durationMs": 0,
            "evidence": f"{type(exc).__name__}: {exc}",
        })

    result = task_result("desktop_smoke", verification)
    return finish(result, args.json_out, "desktop-smoke")


if __name__ == "__main__":
    raise SystemExit(main())
