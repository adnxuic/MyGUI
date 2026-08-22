"""Canonical full verification profiles for application and Agent Engineering."""

from __future__ import annotations

import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time

from _runner import (
    ROOT,
    finish,
    not_run_step,
    run_step,
    runtime_errors,
    task_result,
)


CRITICAL_FILES = [
    "mygui/project_io.py",
    "mygui/widgets/figure_canvas/component_materializers.py",
    "mygui/widgets/figure_canvas/project_metadata.py",
    "mygui/widgets/figure_canvas/py_figure_canves.py",
]
APPLICATION_TEST_TIMEOUT_SECONDS = 3600
MAX_TEST_WORKERS = 16
TEST_BATCH_FACTOR = 4
RESULT_DIR = ROOT / "build" / "agent-results"
COVERAGE_BATCH_RUNNER = ROOT / ".agents" / "checks" / "_coverage_batch.py"
APPLICATION_TIMINGS_PATH = RESULT_DIR / "application-test-timings.json"

# Per-module wall-clock seconds measured 2026-08-22 (Windows, 20 logical CPUs,
# one process, no coverage instrumentation). Used only to balance parallel
# coverage batches; each module's weight is shared by its collected test IDs,
# and unmeasured tests fall back to 0.1 seconds each.
# Refresh this table whenever test suites change significantly.
TEST_MODULE_SECONDS = {
    "test_component_deletion_and_project_close": 174.3,
    "test_component_tree": 106.3,
    "test_component_runtime_integration": 94.7,
    "test_project_io": 91.9,
    "test_figure_history": 86.2,
    "test_colorbar_component": 69.7,
    "test_color_integration": 52.0,
    "test_batch_chart_creation": 45.4,
    "test_axes_layout": 27.8,
    "test_gui_data_flow": 24.2,
    "test_gui_layout": 21.5,
    "test_project_schema": 15.7,
    "test_project_object_roundtrip": 10.0,
    "test_in_axes": 9.3,
    "test_figure_dpi": 6.9,
    "test_text_import": 6.7,
    "test_excel_import": 6.6,
    "test_optional_dependencies": 4.1,
    "test_component_editors": 2.6,
    "test_resource_locator": 2.4,
    "test_gui_file_flow": 2.0,
    "test_font_diagnostics": 1.5,
    "test_component_inspector": 1.4,
    "test_command_gallery": 1.3,
    "test_matplotlib_boundaries": 1.2,
    "test_table_ui": 1.1,
    "test_component_controllers": 1.0,
    "test_bounded_process": 0.7,
    "test_package_boundary": 0.4,
    "test_color_library": 0.4,
    "test_style_creation_defaults": 0.4,
    "test_component_services": 0.3,
    "test_background_task": 0.2,
    "test_application_icon": 0.2,
    "test_table_document": 0.1,
    "test_safe_expression": 0.1,
    "test_data_preprocessing": 0.1,
    "test_agent_engineering": 0.1,
    "test_matplotlib_property_contract": 0.1,
    "test_bottom_bar": 0.0,
    "test_resource_limits": 0.0,
    "test_chart_modifier_styles": 0.0,
    "test_color_picker": 0.0,
    "test_fit_catalog": 0.0,
    "test_interpolate_func": 0.0,
    "test_color_models": 0.0,
    "test_scipy_fit_adapter": 0.0,
    "test_component_materializers": 0.0,
}

# Build the shared Matplotlib font cache once before parallel shards start so
# concurrent first-touch rebuilds cannot race on the same cache directory.
FONT_CACHE_WARMUP = (
    "import matplotlib.font_manager as fm; "
    "print('matplotlib font cache ready:', len(fm.fontManager.ttflist), 'fonts')"
)


def default_test_shards() -> int:
    env = os.environ.get("MYGUI_TEST_SHARDS")
    if env is not None:
        try:
            workers = int(env)
        except ValueError as exc:
            raise ValueError(
                "MYGUI_TEST_SHARDS must be an integer from 1 through 16."
            ) from exc
        if not 1 <= workers <= MAX_TEST_WORKERS:
            raise ValueError(
                "MYGUI_TEST_SHARDS must be an integer from 1 through 16."
            )
        return workers
    return min(8, max(2, os.cpu_count() or 2))


def _module_from_test_id(test_id: str) -> str:
    parts = str(test_id).split(".")
    module = next(
        (part for part in parts[1:] if part.startswith("test_")),
        None,
    )
    if len(parts) < 2 or parts[0] != "tests" or module is None:
        raise ValueError(f"Invalid collected application test ID: {test_id!r}.")
    return module


def _test_weights(test_ids: list[str]) -> dict[str, float]:
    module_counts = Counter(_module_from_test_id(test_id) for test_id in test_ids)
    weights = {}
    for test_id in test_ids:
        module = _module_from_test_id(test_id)
        measured = TEST_MODULE_SECONDS.get(module)
        weights[test_id] = (
            measured / module_counts[module]
            if measured is not None and measured > 0
            else 0.1
        )
    return weights


def _balanced_test_batches(
    test_ids: list[str],
    workers: int,
    *,
    weights: dict[str, float] | None = None,
) -> list[list[str]]:
    """Create deterministic LPT micro-batches for a fixed worker pool."""

    if not test_ids:
        raise ValueError("Cannot create application test batches without tests.")
    if not 1 <= workers <= MAX_TEST_WORKERS:
        raise ValueError("Application test workers must be between 1 and 16.")
    if len(test_ids) != len(set(test_ids)):
        raise ValueError("Application test IDs must be unique before batching.")
    if workers == 1:
        return [sorted(test_ids)]

    test_weights = weights or _test_weights(test_ids)
    batch_count = min(len(test_ids), workers * TEST_BATCH_FACTOR)
    batches: list[list[str]] = [[] for _ in range(batch_count)]
    loads = [0.0] * batch_count
    ordered = sorted(
        test_ids,
        key=lambda test_id: (-float(test_weights[test_id]), test_id),
    )
    for test_id in ordered:
        target = min(range(batch_count), key=lambda index: (loads[index], index))
        batches[target].append(test_id)
        loads[target] += float(test_weights[test_id])
    return [sorted(batch) for batch in batches]


def _build_test_plan(test_ids: list[str], requested_workers: int) -> dict:
    workers = min(requested_workers, len(test_ids))
    weights = _test_weights(test_ids)
    batches = _balanced_test_batches(test_ids, workers, weights=weights)
    return {
        "contractVersion": 1,
        "testCount": len(test_ids),
        "uniqueTestCount": len(set(test_ids)),
        "requestedWorkers": requested_workers,
        "workers": workers,
        "batchCount": len(batches),
        "batches": [
            {
                "index": index,
                "estimatedSeconds": round(
                    sum(weights[test_id] for test_id in batch),
                    3,
                ),
                "testIds": batch,
            }
            for index, batch in enumerate(batches)
        ],
    }


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _failed_batch_metadata(index: int, expected: int, reason: str) -> dict:
    return {
        "batchIndex": index,
        "expectedCount": expected,
        "testsRun": 0,
        "complete": False,
        "successful": False,
        "failures": 0,
        "errors": 1,
        "skipped": 0,
        "durationMs": 0,
        "testTimings": [],
        "infrastructureError": reason,
    }


def _batch_step(index: int, batch_count: int, command: list[str], status: str,
                duration_ms: float, evidence: str) -> dict:
    return {
        "id": f"unittest_coverage_batch_{index + 1}_of_{batch_count}",
        "command": " ".join(command),
        "status": status,
        "required": True,
        "durationMs": round(duration_ms, 3),
        "evidence": evidence[-8000:],
    }


def _run_coverage_batch(
    index: int,
    test_ids: list[str],
    batch_count: int,
    plan_path: Path,
    result_path: Path,
    deadline: float,
) -> tuple[dict, dict, str]:
    command = [
        sys.executable, "-m", "coverage", "run", "--parallel-mode",
        str(COVERAGE_BATCH_RUNNER.relative_to(ROOT)),
        "--run",
        "--plan", str(plan_path),
        "--batch", str(index),
        "--json-out", str(result_path),
    ]
    env = os.environ.copy()
    env.update({"QT_QPA_PLATFORM": "offscreen", "MPLBACKEND": "qtagg"})
    started = time.monotonic()
    remaining = deadline - started
    if remaining <= 0:
        evidence = "The global one-hour application test budget expired before launch."
        return (
            _batch_step(index, batch_count, command, "failed", 0, evidence),
            _failed_batch_metadata(index, len(test_ids), evidence),
            evidence,
        )
    try:
        completed = subprocess.run(
            command,
            cwd=ROOT,
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=max(1, int(remaining)),
            check=False,
        )
        output = completed.stdout or ""
        metadata = json.loads(result_path.read_text(encoding="utf-8"))
        observed_ids = [
            item.get("id")
            for item in metadata.get("testTimings", [])
            if isinstance(item, dict)
        ]
        complete = (
            metadata.get("complete") is True
            and metadata.get("expectedCount") == len(test_ids)
            and metadata.get("testsRun") == len(test_ids)
            and sorted(observed_ids) == sorted(test_ids)
        )
        metadata["complete"] = complete
        status = (
            "passed"
            if completed.returncode == 0
            and complete
            and metadata.get("successful") is True
            else "failed"
        )
        summary = (
            f"Batch {index + 1}/{batch_count}: expected={len(test_ids)}, "
            f"ran={metadata.get('testsRun')}, complete={complete}, "
            f"returncode={completed.returncode}."
        )
        evidence = f"{output[-7000:]}\n{summary}".strip()
    except subprocess.TimeoutExpired as exc:
        status = "failed"
        raw_output = exc.stdout or ""
        if isinstance(raw_output, bytes):
            raw_output = raw_output.decode(errors="replace")
        evidence = (
            f"{raw_output[-6000:]}\nTimed out at the global application test deadline."
        ).strip()
        metadata = _failed_batch_metadata(index, len(test_ids), evidence)
        output = evidence
    except OSError as exc:
        status = "failed"
        evidence = f"Coverage batch infrastructure failure: {exc}"
        metadata = _failed_batch_metadata(index, len(test_ids), evidence)
        output = evidence
    duration_ms = (time.monotonic() - started) * 1000
    metadata["wallDurationMs"] = round(duration_ms, 3)
    return (
        _batch_step(index, batch_count, command, status, duration_ms, evidence),
        metadata,
        output,
    )


def _execute_test_plan(plan: dict, plan_path: Path, result_dir: Path,
                       timeout: int) -> tuple[list[dict], bool]:
    started = time.monotonic()
    deadline = started + timeout
    workers = int(plan["workers"])
    batches = plan["batches"]
    outcomes: dict[int, tuple[dict, dict]] = {}

    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {
            executor.submit(
                _run_coverage_batch,
                int(batch["index"]),
                list(batch["testIds"]),
                len(batches),
                plan_path,
                result_dir / f"batch-{int(batch['index']):03d}.json",
                deadline,
            ): batch
            for batch in batches
        }
        for future in as_completed(futures):
            batch = futures[future]
            index = int(batch["index"])
            try:
                step, metadata, output = future.result()
            except Exception as exc:
                evidence = f"Coverage batch future failed: {type(exc).__name__}: {exc}"
                command = ["coverage batch", str(index)]
                step = _batch_step(
                    index,
                    len(batches),
                    command,
                    "failed",
                    0,
                    evidence,
                )
                metadata = _failed_batch_metadata(
                    index,
                    len(batch["testIds"]),
                    evidence,
                )
                output = evidence
            outcomes[index] = (step, metadata)
            print(f"\n== {step['id']} ({step['status']}) ==")
            print(output[-6000:], end="" if output.endswith("\n") else "\n")

    wall_duration_ms = round((time.monotonic() - started) * 1000, 3)
    ordered = [outcomes[index] for index in range(len(batches))]
    steps = [item[0] for item in ordered]
    batch_results = [item[1] for item in ordered]
    expected_ids = [
        test_id
        for batch in batches
        for test_id in batch["testIds"]
    ]
    observed_ids = [
        timing.get("id")
        for result in batch_results
        for timing in result.get("testTimings", [])
        if isinstance(timing, dict)
    ]
    coverage_complete = (
        len(outcomes) == len(batches)
        and all(result.get("complete") is True for result in batch_results)
        and sum(int(result.get("testsRun", 0)) for result in batch_results)
        == len(expected_ids)
        and sorted(observed_ids) == sorted(expected_ids)
    )
    successful = coverage_complete and all(step["status"] == "passed" for step in steps)
    summary = {
        "contractVersion": 1,
        "workers": workers,
        "batchCount": len(batches),
        "testCount": len(expected_ids),
        "uniqueTestCount": len(set(expected_ids)),
        "testsRun": len(observed_ids),
        "uniqueTestsRun": len(set(observed_ids)),
        "coverageComplete": coverage_complete,
        "successful": successful,
        "wallDurationMs": wall_duration_ms,
        "batches": batch_results,
        "testTimings": [
            timing
            for result in batch_results
            for timing in result.get("testTimings", [])
            if isinstance(timing, dict)
        ],
    }
    _write_json(APPLICATION_TIMINGS_PATH, summary)
    summary_evidence = (
        f"workers={workers}, batches={len(batches)}, "
        f"expected={len(expected_ids)}, ran={len(observed_ids)}, "
        f"unique={len(set(observed_ids))}, coverage_complete={coverage_complete}, "
        f"wall={wall_duration_ms / 1000:.3f}s; "
        f"timings={APPLICATION_TIMINGS_PATH}"
    )
    steps.append({
        "id": "unittest_coverage_parallel_summary",
        "command": "validate complete application test plan execution",
        "status": "passed" if successful else "failed",
        "required": True,
        "durationMs": wall_duration_ms,
        "evidence": summary_evidence,
    })
    return steps, coverage_complete


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
    try:
        requested_workers = default_test_shards()
        worker_error = ""
    except ValueError as exc:
        requested_workers = 0
        worker_error = str(exc)
    verification.append({
        "id": "test_worker_configuration",
        "command": "validate MYGUI_TEST_SHARDS",
        "status": "failed" if worker_error else "passed",
        "required": True,
        "durationMs": 0,
        "evidence": worker_error or f"Requested {requested_workers} application test workers.",
    })

    coverage_commands = {
        "coverage_combine": f"{sys.executable} -m coverage combine",
        "coverage_global": f"{sys.executable} -m coverage report --fail-under=74",
        "coverage_critical": (
            f"{sys.executable} -m coverage report --fail-under=80 "
            + " ".join(CRITICAL_FILES)
        ),
        "coverage_json": (
            f"{sys.executable} -m coverage json -o "
            "build/agent-results/coverage.json"
        ),
    }

    def append_unavailable_test_steps(reason: str) -> None:
        verification.append(not_run_step(
            "test_collection",
            f"{sys.executable} {COVERAGE_BATCH_RUNNER} --collect",
            reason,
        ))
        verification.append(not_run_step(
            "application_test_plan",
            "build deterministic LPT application test plan",
            reason,
        ))
        verification.append(not_run_step(
            "unittest_coverage_parallel_summary",
            "execute complete application test plan",
            reason,
        ))
        for step_id, command in coverage_commands.items():
            verification.append(not_run_step(step_id, command, reason))

    if worker_error:
        append_unavailable_test_steps(worker_error)
        verification.append(run_step(
            "agent_core", [sys.executable, ".agents/checks/verify_agent_core.py"]
        ))
        return verification

    RESULT_DIR.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix="application-test-plan-",
        dir=RESULT_DIR,
    ) as directory:
        run_dir = Path(directory)
        collection_path = run_dir / "collection.json"
        plan_path = run_dir / "plan.json"
        collection_step = run_step(
            "test_collection",
            [
                sys.executable,
                str(COVERAGE_BATCH_RUNNER.relative_to(ROOT)),
                "--collect",
                "--json-out", str(collection_path),
            ],
            env={"QT_QPA_PLATFORM": "offscreen", "MPLBACKEND": "qtagg"},
            timeout=300,
        )
        verification.append(collection_step)
        if collection_step["status"] != "passed":
            reason = "Application test discovery failed; coverage would be incomplete."
            verification.append(not_run_step(
                "application_test_plan", "build LPT application test plan", reason
            ))
            verification.append(not_run_step(
                "unittest_coverage_parallel_summary",
                "execute complete application test plan",
                reason,
            ))
            for step_id, command in coverage_commands.items():
                verification.append(not_run_step(step_id, command, reason))
        else:
            try:
                collection = json.loads(collection_path.read_text(encoding="utf-8"))
                test_ids = collection["testIds"]
                if (
                    not isinstance(test_ids, list)
                    or not test_ids
                    or not all(isinstance(test_id, str) for test_id in test_ids)
                    or len(test_ids) != len(set(test_ids))
                    or collection.get("testCount") != len(test_ids)
                    or collection.get("uniqueTestCount") != len(test_ids)
                ):
                    raise ValueError("Collected application test IDs are incomplete or invalid.")
                plan = _build_test_plan(test_ids, requested_workers)
                flattened = [
                    test_id
                    for batch in plan["batches"]
                    for test_id in batch["testIds"]
                ]
                if sorted(flattened) != sorted(test_ids):
                    raise ValueError("Application test plan changed its collected test IDs.")
                _write_json(plan_path, plan)
                plan_error = ""
            except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
                plan = {}
                plan_error = str(exc)
            verification.append({
                "id": "application_test_plan",
                "command": "build deterministic LPT application test plan",
                "status": "failed" if plan_error else "passed",
                "required": True,
                "durationMs": 0,
                "evidence": plan_error or (
                    f"tests={plan['testCount']}, unique={plan['uniqueTestCount']}, "
                    f"workers={plan['workers']}, batches={plan['batchCount']}"
                ),
            })
            if plan_error:
                reason = "Application test planning failed; coverage would be incomplete."
                verification.append(not_run_step(
                    "unittest_coverage_parallel_summary",
                    "execute complete application test plan",
                    reason,
                ))
                for step_id, command in coverage_commands.items():
                    verification.append(not_run_step(step_id, command, reason))
            else:
                coverage_erase = run_step(
                    "coverage_erase", [sys.executable, "-m", "coverage", "erase"]
                )
                font_warmup = run_step(
                    "font_cache_warmup", [sys.executable, "-c", FONT_CACHE_WARMUP]
                )
                verification.extend([coverage_erase, font_warmup])
                if any(
                    step["status"] != "passed"
                    for step in (coverage_erase, font_warmup)
                ):
                    reason = (
                        "Coverage cleanup or Matplotlib font-cache warmup failed; "
                        "parallel coverage was not started."
                    )
                    verification.append(not_run_step(
                        "unittest_coverage_parallel_summary",
                        "execute complete application test plan",
                        reason,
                    ))
                    for step_id, command in coverage_commands.items():
                        verification.append(not_run_step(step_id, command, reason))
                else:
                    batch_steps, coverage_complete = _execute_test_plan(
                        plan,
                        plan_path,
                        run_dir,
                        APPLICATION_TEST_TIMEOUT_SECONDS,
                    )
                    verification.extend(batch_steps)
                    if coverage_complete:
                        verification.append(run_step(
                            "coverage_combine",
                            [sys.executable, "-m", "coverage", "combine"],
                        ))
                        verification.append(run_step(
                            "coverage_global",
                            [
                                sys.executable, "-m", "coverage", "report",
                                "--fail-under=74",
                            ],
                        ))
                        verification.append(run_step(
                            "coverage_critical",
                            [
                                sys.executable, "-m", "coverage", "report",
                                "--fail-under=80", *CRITICAL_FILES,
                            ],
                        ))
                        verification.append(run_step(
                            "coverage_json",
                            [
                                sys.executable, "-m", "coverage", "json", "-o",
                                "build/agent-results/coverage.json",
                            ],
                        ))
                    else:
                        reason = (
                            "At least one application test batch was incomplete; "
                            "partial coverage cannot satisfy the gate."
                        )
                        for step_id, command in coverage_commands.items():
                            verification.append(not_run_step(step_id, command, reason))
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
