"""Canonical full verification profiles for application and Agent Engineering."""

from __future__ import annotations

import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import nullcontext
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
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
    "mygui/application_settings/service.py",
    "mygui/application_theme/service.py",
]
APPLICATION_TEST_TIMEOUT_SECONDS = 3600
APPLICATION_BATCH_TIMEOUT_SECONDS = 1200
MAX_TEST_WORKERS = 16
DEFAULT_TEST_WORKERS = 4
TEST_BATCH_FACTOR = 4
RESULT_DIR = ROOT / "build" / "agent-results"
APPLICATION_RESULT_DIR = RESULT_DIR / "application"
COVERAGE_BATCH_RUNNER = ROOT / ".agents" / "checks" / "_coverage_batch.py"
APPLICATION_TIMINGS_PATH = RESULT_DIR / "application-test-timings.json"
PLAN_CONTRACT_VERSION = 3

# Isolation modes for the unified application process pool.
# gui-module: one fresh process per test module (Qt/Matplotlib lifecycle).
# gui-test: one fresh process per test ID (hotspots such as XRD combinations).
# core: contract/parsing/numerical tests packed into LPT micro-batches.
ISOLATION_GUI_MODULE = "gui-module"
ISOLATION_GUI_TEST = "gui-test"
ISOLATION_CORE = "core"
GUI_ISOLATION_MODES = frozenset({ISOLATION_GUI_MODULE, ISOLATION_GUI_TEST})

# Complete classification: isolation plus historical wall-clock seconds.
# Measured 2026-08-22 except XRD/reference/canvas modules added later.
# Plan validation fails if discovery adds, removes, or leaves a module
# unclassified, so new suites cannot enter LPT with a 0.1s fallback.
APPLICATION_TEST_MODULES = {
    "test_component_deletion_and_project_close": (ISOLATION_GUI_MODULE, 174.3),
    "test_component_tree": (ISOLATION_GUI_MODULE, 106.3),
    "test_component_runtime_integration": (ISOLATION_GUI_MODULE, 94.7),
    "test_project_io": (ISOLATION_GUI_MODULE, 91.9),
    "test_figure_history": (ISOLATION_GUI_MODULE, 86.2),
    "test_colorbar_component": (ISOLATION_GUI_MODULE, 69.7),
    "test_color_integration": (ISOLATION_GUI_MODULE, 52.0),
    "test_batch_chart_creation": (ISOLATION_GUI_MODULE, 45.4),
    "test_axes_layout": (ISOLATION_GUI_MODULE, 27.8),
    "test_reference_guides": (ISOLATION_GUI_MODULE, 25.0),
    "test_gui_data_flow": (ISOLATION_GUI_MODULE, 24.2),
    "test_gui_layout": (ISOLATION_GUI_MODULE, 21.5),
    "test_xrd_refinement": (ISOLATION_GUI_TEST, 260.0),
    "test_project_schema": (ISOLATION_GUI_MODULE, 15.7),
    "test_project_object_roundtrip": (ISOLATION_GUI_MODULE, 10.0),
    "test_in_axes": (ISOLATION_GUI_MODULE, 9.3),
    "test_canvas_popout": (ISOLATION_GUI_MODULE, 8.0),
    "test_reference_marks_table": (ISOLATION_GUI_MODULE, 8.0),
    "test_figure_dpi": (ISOLATION_GUI_MODULE, 6.9),
    "test_figure_export": (ISOLATION_GUI_MODULE, 12.0),
    "test_text_import": (ISOLATION_GUI_MODULE, 6.7),
    "test_excel_import": (ISOLATION_GUI_MODULE, 6.6),
    "test_optional_dependencies": (ISOLATION_GUI_MODULE, 4.1),
    "test_component_editors": (ISOLATION_GUI_MODULE, 2.6),
    "test_resource_locator": (ISOLATION_GUI_MODULE, 2.4),
    "test_gui_file_flow": (ISOLATION_GUI_MODULE, 2.0),
    "test_application_settings_storage": (ISOLATION_GUI_MODULE, 2.5),
    "test_application_settings_new_figure": (ISOLATION_GUI_MODULE, 10.0),
    "test_application_settings_pages": (ISOLATION_GUI_MODULE, 2.0),
    "test_application_settings_center": (ISOLATION_GUI_MODULE, 4.0),
    "test_application_settings_center_c": (ISOLATION_GUI_MODULE, 3.0),
    "test_application_theme": (ISOLATION_GUI_MODULE, 3.0),
    "test_application_theme_transactions": (ISOLATION_GUI_MODULE, 3.0),
    "test_application_theme_chrome": (ISOLATION_GUI_MODULE, 8.0),
    "test_application_theme_qss": (ISOLATION_GUI_MODULE, 3.0),
    "test_font_diagnostics": (ISOLATION_GUI_MODULE, 1.5),
    "test_component_inspector": (ISOLATION_GUI_MODULE, 1.4),
    "test_command_gallery": (ISOLATION_GUI_MODULE, 1.3),
    "test_matplotlib_boundaries": (ISOLATION_CORE, 1.2),
    "test_table_ui": (ISOLATION_GUI_MODULE, 1.1),
    "test_component_controllers": (ISOLATION_GUI_MODULE, 1.0),
    "test_bounded_process": (ISOLATION_CORE, 0.7),
    "test_component_documentation": (ISOLATION_CORE, 0.5),
    "test_application_settings_service": (ISOLATION_CORE, 0.5),
    "test_application_settings_session": (ISOLATION_CORE, 0.4),
    "test_application_settings_contracts": (ISOLATION_CORE, 0.2),
    "test_package_boundary": (ISOLATION_CORE, 0.4),
    "test_color_library": (ISOLATION_GUI_MODULE, 0.4),
    "test_style_creation_defaults": (ISOLATION_GUI_MODULE, 0.4),
    "test_fullprof_prf": (ISOLATION_CORE, 0.3),
    "test_component_services": (ISOLATION_GUI_MODULE, 0.3),
    "test_y_axis_reserve": (ISOLATION_CORE, 0.2),
    "test_x_axis_tight": (ISOLATION_CORE, 0.2),
    "test_background_task": (ISOLATION_GUI_MODULE, 0.2),
    "test_application_icon": (ISOLATION_GUI_MODULE, 0.2),
    "test_table_document": (ISOLATION_GUI_MODULE, 0.1),
    "test_safe_expression": (ISOLATION_CORE, 0.1),
    "test_data_preprocessing": (ISOLATION_CORE, 0.1),
    "test_agent_engineering": (ISOLATION_CORE, 0.1),
    "test_matplotlib_property_contract": (ISOLATION_GUI_MODULE, 0.1),
    "test_bottom_bar": (ISOLATION_GUI_MODULE, 0.0),
    "test_resource_limits": (ISOLATION_CORE, 0.0),
    "test_chart_modifier_styles": (ISOLATION_GUI_MODULE, 0.0),
    "test_color_picker": (ISOLATION_GUI_MODULE, 0.0),
    "test_fit_catalog": (ISOLATION_CORE, 0.0),
    "test_interpolate_func": (ISOLATION_CORE, 0.0),
    "test_color_models": (ISOLATION_CORE, 0.0),
    "test_scipy_fit_adapter": (ISOLATION_CORE, 0.0),
    "test_component_materializers": (ISOLATION_CORE, 0.0),
    "test_e2e_acceptance": (ISOLATION_GUI_MODULE, 24.0),
    "test_py_figure_canvas": (ISOLATION_GUI_MODULE, 5.5),
    "test_project_metadata": (ISOLATION_GUI_MODULE, 0.5),
}

GUI_SENSITIVE_TEST_MODULES = frozenset(
    module
    for module, (isolation, _seconds) in APPLICATION_TEST_MODULES.items()
    if isolation in GUI_ISOLATION_MODES
)
TEST_MODULE_SECONDS = {
    module: seconds
    for module, (_isolation, seconds) in APPLICATION_TEST_MODULES.items()
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
    return DEFAULT_TEST_WORKERS


def configured_timeout_seconds(name: str, default: int) -> int:
    """Return one positive timeout override in seconds."""

    value = os.environ.get(name)
    if value is None:
        return default
    try:
        seconds = int(value)
    except ValueError as exc:
        raise ValueError(f"{name} must be a positive integer.") from exc
    if seconds < 1:
        raise ValueError(f"{name} must be a positive integer.")
    return seconds


def _module_from_test_id(test_id: str) -> str:
    parts = str(test_id).split(".")
    module = next(
        (part for part in parts[1:] if part.startswith("test_")),
        None,
    )
    if len(parts) < 2 or parts[0] != "tests" or module is None:
        raise ValueError(f"Invalid collected application test ID: {test_id!r}.")
    return module


def _module_spec(module: str) -> tuple[str, float]:
    try:
        isolation, seconds = APPLICATION_TEST_MODULES[module]
    except KeyError as exc:
        raise ValueError(
            f"Unclassified application test module: {module}."
        ) from exc
    return str(isolation), float(seconds)


def _classification_errors(modules: set[str]) -> list[str]:
    configured = set(APPLICATION_TEST_MODULES)
    missing = sorted(modules - configured)
    extra = sorted(configured - modules)
    errors = []
    if missing:
        errors.append(f"unclassified test modules: {missing}")
    if extra:
        errors.append(f"classified modules not collected: {extra}")
    return errors


def _test_weights(test_ids: list[str]) -> dict[str, float]:
    module_counts = Counter(_module_from_test_id(test_id) for test_id in test_ids)
    weights = {}
    for test_id in test_ids:
        module = _module_from_test_id(test_id)
        _isolation, measured = _module_spec(module)
        count = module_counts[module]
        weights[test_id] = measured / count if measured > 0 else 0.0
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
    if not test_ids:
        raise ValueError("Cannot create application test batches without tests.")
    if not 1 <= requested_workers <= MAX_TEST_WORKERS:
        raise ValueError("Application test workers must be between 1 and 16.")
    if len(test_ids) != len(set(test_ids)):
        raise ValueError("Application test IDs must be unique before batching.")

    modules = sorted({_module_from_test_id(test_id) for test_id in test_ids})
    classification_errors = _classification_errors(set(modules))
    if classification_errors:
        raise ValueError(
            "Application test module classification is incomplete: "
            + "; ".join(classification_errors)
            + "."
        )

    weights = _test_weights(test_ids)
    gui_module_ids: dict[str, list[str]] = {}
    gui_test_ids: list[str] = []
    core_ids: list[str] = []
    for test_id in test_ids:
        module = _module_from_test_id(test_id)
        isolation, _seconds = _module_spec(module)
        if isolation == ISOLATION_GUI_MODULE:
            gui_module_ids.setdefault(module, []).append(test_id)
        elif isolation == ISOLATION_GUI_TEST:
            gui_test_ids.append(test_id)
        elif isolation == ISOLATION_CORE:
            core_ids.append(test_id)
        else:
            raise ValueError(
                f"Unknown isolation mode {isolation!r} for module {module}."
            )

    raw_batches: list[dict] = []
    for module in sorted(gui_module_ids):
        batch_ids = sorted(gui_module_ids[module])
        raw_batches.append({
            "isolation": ISOLATION_GUI_MODULE,
            "module": module,
            "estimatedSeconds": round(
                sum(weights[test_id] for test_id in batch_ids),
                3,
            ),
            "testIds": batch_ids,
        })
    for test_id in sorted(gui_test_ids):
        raw_batches.append({
            "isolation": ISOLATION_GUI_TEST,
            "module": _module_from_test_id(test_id),
            "estimatedSeconds": round(weights[test_id], 3),
            "testIds": [test_id],
        })
    if core_ids:
        core_workers = min(requested_workers, len(core_ids))
        for test_batch in _balanced_test_batches(
            core_ids,
            core_workers,
            weights=weights,
        ):
            raw_batches.append({
                "isolation": ISOLATION_CORE,
                "module": None,
                "estimatedSeconds": round(
                    sum(weights[test_id] for test_id in test_batch),
                    3,
                ),
                "testIds": test_batch,
            })

    ordered = sorted(
        raw_batches,
        key=lambda batch: (
            -float(batch["estimatedSeconds"]),
            str(batch["isolation"]),
            tuple(batch["testIds"]),
        ),
    )
    batches = []
    for index, batch in enumerate(ordered):
        batches.append({
            "index": index,
            "pool": "application",
            "isolation": batch["isolation"],
            "module": batch["module"],
            "estimatedSeconds": batch["estimatedSeconds"],
            "launchOrder": index,
            "testIds": batch["testIds"],
        })

    max_workers = min(requested_workers, len(batches)) if batches else 0
    launch_order = [batch["index"] for batch in batches]
    return {
        "contractVersion": PLAN_CONTRACT_VERSION,
        "testCount": len(test_ids),
        "uniqueTestCount": len(set(test_ids)),
        "requestedWorkers": requested_workers,
        "maxWorkers": max_workers,
        "workers": max_workers,
        "isolationMode": "process",
        "serial": requested_workers == 1,
        "guiTestCount": (
            sum(len(values) for values in gui_module_ids.values())
            + len(gui_test_ids)
        ),
        "coreTestCount": len(core_ids),
        "batchCount": len(batches),
        "launchOrder": launch_order,
        "groups": [{
            "name": "application",
            "workers": max_workers,
            "serial": requested_workers == 1,
            "isolationMode": "process",
            "batchIndexes": launch_order,
            "testCount": len(test_ids),
        }],
        "batches": batches,
        "timingBaseline": {
            "collectedModules": modules,
            "classifiedModules": sorted(APPLICATION_TEST_MODULES),
            "guiModules": sorted(GUI_SENSITIVE_TEST_MODULES),
            "measuredModules": sorted(TEST_MODULE_SECONDS),
            "missingModules": [],
            "extraModules": [],
        },
    }


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _write_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value, encoding="utf-8")


def _failed_batch_metadata(
    index: int,
    test_ids: list[str],
    reason: str,
    *,
    pool: str,
    isolation: str = ISOLATION_CORE,
    exception_type: str = "InfrastructureError",
) -> dict:
    return {
        "contractVersion": PLAN_CONTRACT_VERSION,
        "batchIndex": index,
        "pool": pool,
        "isolation": isolation,
        "expectedCount": len(test_ids),
        "assignedTestIds": list(test_ids),
        "testsRun": 0,
        "complete": False,
        "successful": False,
        "failureCount": 0,
        "errorCount": 1,
        "failures": [],
        "errors": [{
            "testId": "",
            "exceptionType": exception_type,
            "message": reason,
            "traceback": "",
        }],
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
    batch_timeout: int = APPLICATION_BATCH_TIMEOUT_SECONDS,
    pool: str = "application",
    isolation: str = ISOLATION_CORE,
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
    log_path = result_path.with_suffix(".log")
    if remaining <= 0:
        evidence = "The global application test budget expired before launch."
        metadata = _failed_batch_metadata(
            index,
            test_ids,
            evidence,
            pool=pool,
            isolation=isolation,
            exception_type="GlobalTimeout",
        )
        metadata["timeoutReason"] = "global_timeout_before_launch"
        metadata["effectiveTimeoutSeconds"] = 0
        metadata["wallDurationMs"] = 0
        _write_json(result_path, metadata)
        _write_text(log_path, evidence + "\n")
        return (
            _batch_step(index, batch_count, command, "failed", 0, evidence),
            metadata,
            evidence,
        )
    effective_timeout = min(float(batch_timeout), remaining)
    timeout_reason = (
        "batch_timeout"
        if float(batch_timeout) <= remaining
        else "remaining_global_budget"
    )
    output = ""
    try:
        completed = subprocess.run(
            command,
            cwd=ROOT,
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=max(0.001, effective_timeout),
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
            f"Batch {index + 1}/{batch_count} ({pool}): expected={len(test_ids)}, "
            f"ran={metadata.get('testsRun')}, complete={complete}, "
            f"returncode={completed.returncode}."
        )
        full_log = f"{output}{'' if output.endswith(chr(10)) or not output else chr(10)}{summary}\n"
        evidence = full_log[-8000:].strip()
    except subprocess.TimeoutExpired as exc:
        status = "failed"
        raw_output = exc.stdout or ""
        if isinstance(raw_output, bytes):
            raw_output = raw_output.decode(errors="replace")
        elapsed = time.monotonic() - started
        timeout_message = (
            f"Batch {index + 1}/{batch_count} ({pool}) timed out after "
            f"{elapsed:.3f}s; reason={timeout_reason}; "
            f"assigned_tests={len(test_ids)}."
        )
        assigned = "\n".join(f"- {test_id}" for test_id in test_ids)
        full_log = (
            f"{raw_output}{'' if raw_output.endswith(chr(10)) or not raw_output else chr(10)}"
            f"{timeout_message}\nAssigned test IDs:\n{assigned}\n{timeout_message}\n"
        )
        evidence = full_log[-8000:].strip()
        metadata = _failed_batch_metadata(
            index,
            test_ids,
            timeout_message,
            pool=pool,
            isolation=isolation,
            exception_type=(
                "BatchTimeout"
                if timeout_reason == "batch_timeout"
                else "GlobalTimeout"
            ),
        )
        metadata["timeoutReason"] = timeout_reason
    except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
        status = "failed"
        message = f"Coverage batch infrastructure failure: {type(exc).__name__}: {exc}"
        full_log = (
            f"{output}{'' if output.endswith(chr(10)) or not output else chr(10)}"
            f"{message}\n"
        )
        evidence = full_log[-8000:].strip()
        metadata = _failed_batch_metadata(
            index,
            test_ids,
            message,
            pool=pool,
            isolation=isolation,
            exception_type=type(exc).__name__,
        )
    duration_ms = (time.monotonic() - started) * 1000
    metadata["contractVersion"] = PLAN_CONTRACT_VERSION
    metadata["pool"] = pool
    metadata["isolation"] = isolation
    metadata["assignedTestIds"] = list(test_ids)
    metadata["effectiveTimeoutSeconds"] = round(effective_timeout, 3)
    metadata["wallDurationMs"] = round(duration_ms, 3)
    _write_json(result_path, metadata)
    _write_text(log_path, full_log)
    return (
        _batch_step(index, batch_count, command, status, duration_ms, evidence),
        metadata,
        full_log,
    )


def _execute_test_plan(plan: dict, plan_path: Path, result_dir: Path,
                       timeout: int,
                       batch_timeout: int = APPLICATION_BATCH_TIMEOUT_SECONDS,
                       ) -> tuple[list[dict], bool]:
    started = time.monotonic()
    deadline = started + timeout
    batches = plan["batches"]
    outcomes: dict[int, tuple[dict, dict]] = {}
    batch_by_index = {int(batch["index"]): batch for batch in batches}
    max_workers = max(
        1,
        int(plan.get("maxWorkers") or plan.get("workers") or 1),
    )
    launch_order = list(
        plan.get("launchOrder")
        or [int(batch["index"]) for batch in batches]
    )
    ordered_batches = [batch_by_index[int(index)] for index in launch_order]
    pool = "application"
    print(
        f"\n=== APPLICATION TEST POOL "
        f"(maxWorkers={max_workers}, batches={len(ordered_batches)}, "
        f"isolation=process, lptLaunchOrder={launch_order}) ==="
    )
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(
                _run_coverage_batch,
                int(batch["index"]),
                list(batch["testIds"]),
                len(batches),
                plan_path,
                result_dir / f"batch-{int(batch['index']):03d}.json",
                deadline,
                batch_timeout,
                str(batch.get("pool") or pool),
                str(batch.get("isolation") or ISOLATION_CORE),
            ): batch
            for batch in ordered_batches
        }
        for future in as_completed(futures):
            batch = futures[future]
            index = int(batch["index"])
            isolation = str(batch.get("isolation") or ISOLATION_CORE)
            try:
                step, metadata, output = future.result()
            except Exception as exc:
                evidence = (
                    f"Coverage batch future failed: {type(exc).__name__}: {exc}"
                )
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
                    list(batch["testIds"]),
                    evidence,
                    pool=str(batch.get("pool") or pool),
                    isolation=isolation,
                    exception_type=type(exc).__name__,
                )
                _write_json(
                    result_dir / f"batch-{index:03d}.json",
                    metadata,
                )
                _write_text(
                    result_dir / f"batch-{index:03d}.log",
                    evidence + "\n",
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
    test_timings = [
        timing
        for result in batch_results
        for timing in result.get("testTimings", [])
        if isinstance(timing, dict)
    ]
    module_timings: dict[str, dict[str, float | int]] = {}
    for timing in test_timings:
        module = _module_from_test_id(str(timing["id"]))
        aggregate = module_timings.setdefault(
            module,
            {"testCount": 0, "durationMs": 0.0},
        )
        aggregate["testCount"] = int(aggregate["testCount"]) + 1
        aggregate["durationMs"] = round(
            float(aggregate["durationMs"]) + float(timing.get("durationMs", 0)),
            3,
        )
    groups = plan.get("groups") or [{
        "name": pool,
        "workers": max_workers,
        "serial": max_workers == 1,
        "isolationMode": plan.get("isolationMode", "process"),
        "batchIndexes": launch_order,
        "testCount": len(expected_ids),
    }]
    summary = {
        "contractVersion": PLAN_CONTRACT_VERSION,
        "maxWorkers": max_workers,
        "requestedWorkers": int(plan.get("requestedWorkers", max_workers)),
        "isolationMode": plan.get("isolationMode", "process"),
        "serial": bool(plan.get("serial", max_workers == 1)),
        "launchOrder": launch_order,
        "groups": groups,
        "batchCount": len(batches),
        "testCount": len(expected_ids),
        "uniqueTestCount": len(set(expected_ids)),
        "testsRun": len(observed_ids),
        "uniqueTestsRun": len(set(observed_ids)),
        "coverageComplete": coverage_complete,
        "successful": successful,
        "wallDurationMs": wall_duration_ms,
        "batches": batch_results,
        "testTimings": test_timings,
        "moduleTimings": module_timings,
        "failures": [
            {
                **issue,
                "batchIndex": result.get("batchIndex"),
                "pool": result.get("pool"),
                "isolation": result.get("isolation"),
            }
            for result in batch_results
            for issue in result.get("failures", [])
            if isinstance(issue, dict)
        ],
        "errors": [
            {
                **issue,
                "batchIndex": result.get("batchIndex"),
                "pool": result.get("pool"),
                "isolation": result.get("isolation"),
            }
            for result in batch_results
            for issue in result.get("errors", [])
            if isinstance(issue, dict)
        ],
    }
    _write_json(APPLICATION_TIMINGS_PATH, summary)
    _write_json(result_dir / "summary.json", summary)
    issues = [*summary["failures"], *summary["errors"]]
    if issues:
        print("\n=== APPLICATION TEST FAILURES ===")
        for issue in issues:
            print(
                f"batch: {int(issue['batchIndex']) + 1}/{len(batches)} "
                f"({issue['pool']}/{issue.get('isolation') or 'unknown'})"
            )
            print(f"test: {issue.get('testId') or '<batch infrastructure>'}")
            print(f"exception: {issue.get('exceptionType') or 'Unknown'}")
            print(f"message: {issue.get('message') or ''}")
            traceback_text = str(issue.get("traceback") or "").strip()
            if traceback_text:
                print("traceback:")
                print(traceback_text)
    summary_evidence = (
        f"maxWorkers={max_workers}, isolation=process, "
        f"serial={plan.get('serial', max_workers == 1)}, "
        f"gui_tests={plan.get('guiTestCount', 0)}, "
        f"core_tests={plan.get('coreTestCount', len(expected_ids))}, "
        f"batches={len(batches)}, expected={len(expected_ids)}, "
        f"ran={len(observed_ids)}, unique={len(set(observed_ids))}, "
        f"coverage_complete={coverage_complete}, "
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
        "compileall", [sys.executable, "-m", "compileall", "-q", "mygui", "tests", "main.py", ".agents/desktop_smoke"]
    ))
    verification.append(run_step(
        "ruff", [sys.executable, "-m", "ruff", "check", "mygui", "tests", ".agents/checks", ".agents/desktop_smoke", "main.py"]
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
        "evidence": worker_error or (
            f"Requested {requested_workers} application test pool workers "
            f"(MYGUI_TEST_SHARDS default {DEFAULT_TEST_WORKERS})."
        ),
    })
    try:
        global_timeout = configured_timeout_seconds(
            "APPLICATION_TEST_TIMEOUT_SECONDS",
            APPLICATION_TEST_TIMEOUT_SECONDS,
        )
        batch_timeout = configured_timeout_seconds(
            "APPLICATION_BATCH_TIMEOUT_SECONDS",
            APPLICATION_BATCH_TIMEOUT_SECONDS,
        )
        timeout_error = ""
    except ValueError as exc:
        global_timeout = 0
        batch_timeout = 0
        timeout_error = str(exc)
    verification.append({
        "id": "application_timeout_configuration",
        "command": (
            "validate APPLICATION_TEST_TIMEOUT_SECONDS and "
            "APPLICATION_BATCH_TIMEOUT_SECONDS"
        ),
        "status": "failed" if timeout_error else "passed",
        "required": True,
        "durationMs": 0,
        "evidence": timeout_error or (
            f"global={global_timeout}s, per_batch={batch_timeout}s; "
            "effective timeout is the smaller remaining budget."
        ),
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

    configuration_error = worker_error or timeout_error
    if configuration_error:
        append_unavailable_test_steps(configuration_error)
        verification.append(run_step(
            "agent_core", [sys.executable, ".agents/checks/verify_agent_core.py"]
        ))
        return verification

    RESULT_DIR.mkdir(parents=True, exist_ok=True)
    if APPLICATION_RESULT_DIR.exists():
        shutil.rmtree(APPLICATION_RESULT_DIR)
    APPLICATION_RESULT_DIR.mkdir(parents=True, exist_ok=True)
    with nullcontext(APPLICATION_RESULT_DIR) as directory:
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
                plan["globalTimeoutSeconds"] = global_timeout
                plan["batchTimeoutSeconds"] = batch_timeout
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
                    f"contract=v{plan['contractVersion']}, "
                    f"tests={plan['testCount']}, unique={plan['uniqueTestCount']}, "
                    f"maxWorkers={plan['maxWorkers']}, serial={plan['serial']}, "
                    f"isolation={plan['isolationMode']}, "
                    f"gui={plan['guiTestCount']}, core={plan['coreTestCount']}, "
                    f"batches={plan['batchCount']}"
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
                        global_timeout,
                        batch_timeout,
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
        persistence_impact="MyGUI schema-v15 behavior and predecessor migrations are verified.",
    )
    return finish(result, args.json_out, f"full-{args.profile}")


if __name__ == "__main__":
    raise SystemExit(main())
