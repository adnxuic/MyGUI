"""Run selected desktop smoke groups and write PNG + summary.json evidence."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from desktop_smoke.catalog import GROUPS


def run_smoke(
    output_dir: Path,
    groups: list[str] | None = None,
    all_styles: bool = False,
) -> dict[str, Any]:
    """Open the real MainWindow, walk selected groups, and capture screenshots.

    ``all_styles`` is accepted for the verify entrypoint and ignored: this walk
    does not open Style galleries.
    """

    _ = all_styles
    import matplotlib

    matplotlib.use("QtAgg")

    from desktop_smoke.harness import SmokeHarness
    from desktop_smoke.scenarios.charts_1d import run_charts_1d_scenarios
    from desktop_smoke.scenarios.deletion_history import (
        run_deletion_history_scenarios,
    )
    from desktop_smoke.scenarios.elements import run_elements_scenarios
    from desktop_smoke.scenarios.field_2d import run_field_2d_scenarios
    from desktop_smoke.scenarios.inspectors import run_inspectors_scenarios
    from desktop_smoke.scenarios.layouts_xrd import run_layouts_xrd_scenarios
    from desktop_smoke.scenarios.project_lifecycle import (
        run_project_lifecycle_scenarios,
    )
    from desktop_smoke.scenarios.settings import run_settings_scenarios
    from desktop_smoke.scenarios.templates import run_templates_scenarios

    selected = list(GROUPS) if not groups else list(groups)
    unknown = [name for name in selected if name not in GROUPS]
    if unknown:
        raise ValueError(
            "Unknown desktop smoke group(s): "
            + ", ".join(unknown)
            + ". Available: "
            + ", ".join(GROUPS)
        )

    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True)
    harness = SmokeHarness(destination)
    scenario_results: list[dict[str, Any]] = []
    status = "passed"
    try:
        harness.start()
        if "settings" in selected:
            scenario_results.extend(run_settings_scenarios(harness))
        if "templates" in selected:
            scenario_results.extend(run_templates_scenarios(harness))
        if "field_2d" in selected:
            scenario_results.extend(run_field_2d_scenarios(harness))
        if "charts_1d" in selected:
            scenario_results.extend(run_charts_1d_scenarios(harness))
        if "elements" in selected:
            scenario_results.extend(run_elements_scenarios(harness))
        if "inspectors" in selected:
            scenario_results.extend(run_inspectors_scenarios(harness))
        if "layouts_xrd" in selected:
            scenario_results.extend(run_layouts_xrd_scenarios(harness))
        if "deletion_history" in selected:
            scenario_results.extend(run_deletion_history_scenarios(harness))
        if "project_lifecycle" in selected:
            scenario_results.extend(run_project_lifecycle_scenarios(harness))
    except Exception as exc:  # noqa: BLE001 — required check surfaces the failure
        status = "failed"
        scenario_results.append(
            {
                "id": "harness",
                "status": "failed",
                "error": f"{type(exc).__name__}: {exc}",
            }
        )
    finally:
        try:
            harness.shutdown()
        except Exception as exc:  # noqa: BLE001 — shutdown must not hide walk errors
            status = "failed"
            scenario_results.append(
                {
                    "id": "shutdown",
                    "status": "failed",
                    "error": f"{type(exc).__name__}: {exc}",
                }
            )

    if any(item.get("status") == "failed" for item in scenario_results):
        status = "failed"
    summary = {
        "status": status,
        "screenshotCount": len(harness.screenshots),
        "screenshots": [
            {
                "name": item.name,
                "path": item.path,
                "width": item.width,
                "height": item.height,
            }
            for item in harness.screenshots
        ],
        "scenarios": scenario_results,
        "timingsMs": dict(harness.timings),
        "outputDir": str(destination),
        "groups": selected,
    }
    (destination / "summary.json").write_text(
        json.dumps(summary, indent=2) + "\n",
        encoding="utf-8",
    )
    return summary
