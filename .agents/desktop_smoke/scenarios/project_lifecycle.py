"""Project Save/Open (Schema v16), Multi-Project, Export & Popout desktop smoke. Group id: project_lifecycle."""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any, Callable

from mygui.figuremodify.axes_layout import AxesLayoutSpec
from mygui.figuremodify.components import ComponentKind, ComponentRole
from mygui.figuremodify.components.property_values import DEFAULT_COLOR_MAP
from mygui.project_io import (
    load_project_file,
    restore_project_snapshot,
    save_project_snapshot,
    validate_project_snapshot,
)
from mygui.widgets.title_bar.titlebar_dialog.figure_export_dialog import (
    FigureExportDialog,
)

from desktop_smoke.harness import SmokeError, SmokeHarness


def run_project_lifecycle_scenarios(
    harness: SmokeHarness,
) -> list[dict[str, Any]]:
    """Walk through Schema v16 save/restore, multi-project tabs, figure export, and canvas popout."""
    results: list[dict[str, Any]] = []

    results.append(
        _run_case(
            harness,
            "project_lifecycle.save_and_reopen_v16",
            lambda: _scenario_save_and_reopen_v16(harness),
        )
    )
    results.append(
        _run_case(
            harness,
            "project_lifecycle.multi_project_tabs",
            lambda: _scenario_multi_project_tabs(harness),
        )
    )
    results.append(
        _run_case(
            harness,
            "project_lifecycle.figure_export",
            lambda: _scenario_figure_export(harness),
        )
    )
    results.append(
        _run_case(
            harness,
            "project_lifecycle.canvas_popout",
            lambda: _scenario_canvas_popout(harness),
        )
    )
    return results


def _run_case(
    harness: SmokeHarness,
    scenario_id: str,
    body: Callable[[], None],
) -> dict[str, Any]:
    before = len(harness.screenshots)
    try:
        body()
        return {
            "id": scenario_id,
            "status": "passed",
            "screenshotCount": len(harness.screenshots) - before,
        }
    except Exception as exc:  # noqa: BLE001
        try:
            harness.dismiss_all_dialogs()
            harness.grab_main(f"{scenario_id.replace('.', '-')}-failure")
        except Exception:
            pass
        return {
            "id": scenario_id,
            "status": "failed",
            "error": f"{type(exc).__name__}: {exc}",
            "screenshotCount": len(harness.screenshots) - before,
        }


def _scenario_save_and_reopen_v16(harness: SmokeHarness) -> None:
    canvas = harness.create_project("Smoke_Save_Open")
    canvas.create_axes_layout(AxesLayoutSpec.grid(1, 1))
    harness.pump(50)

    # Seed 2D grid and 1D data
    x_2d, y_2d, z_2d = harness.seed_field_2d_table(canvas, n_x=5, n_y=5)
    cmap_spec = {**DEFAULT_COLOR_MAP, "cmap": "plasma"}
    canvas.add_contour(x_2d, y_2d, z_2d, {"colormap": cmap_spec})
    canvas.add_curve("sin(x)", 0, 5, "--", "#e377c2", "CurveSave")
    canvas.add_reference_line({"orientation": "vertical", "value": 2.0, "linestyle": ":"})

    harness.pump(80)
    canvas.redraw()
    harness.grab_canvas("lifecycle-01-before-save-canvas")

    # Save to temp file
    with tempfile.TemporaryDirectory(prefix="mygui-smoke-io-") as tmpdir:
        save_path = Path(tmpdir) / "project.mygui"
        save_project_snapshot(
            save_path,
            figure_window=harness.window.figure_window,
            canvas=canvas,
        )

        if not save_path.is_file():
            raise SmokeError("Saved project file was not created.")

        loaded_snapshot = load_project_file(save_path)
        validate_project_snapshot(loaded_snapshot)

        # Remove original project from windows to avoid duplicate ID collision on restore
        proj_id = canvas.project_id
        harness.window.figure_window.remove_project_by_id(proj_id)
        harness.window.table.remove_project_table(proj_id)
        harness.pump(50)

        # Restore snapshot
        restore_project_snapshot(
            save_path,
            table=harness.window.table,
            figure_window=harness.window.figure_window,
        )
        harness.pump(80)

        restored_canvas = harness.window.figure_window.current_canva
        if restored_canvas is None:
            raise SmokeError("Restored canvas not found in figure window.")
        restored_canvas.redraw()

        contours = restored_canvas.component_registry.query(
            kind=ComponentKind.FIELD_2D, role=ComponentRole.CONTOUR
        )
        curves = restored_canvas.component_registry.query(
            kind=ComponentKind.LINE
        )
        lines = restored_canvas.component_registry.query(
            kind=ComponentKind.REFERENCE_GUIDE, role=ComponentRole.REFERENCE_LINE
        )

        if not contours or not curves or not lines:
            raise SmokeError("Restored project missing expected components.")

        harness.grab_canvas("lifecycle-02-restored-canvas")


def _scenario_multi_project_tabs(harness: SmokeHarness) -> None:
    canvas1 = harness.create_project("Project_Alpha")
    canvas1.create_axes_layout(AxesLayoutSpec.grid(1, 1))
    canvas1.add_curve("x", 0, 3, "-", "#1f77b4", "AlphaLine")

    canvas2 = harness.create_project("Project_Beta")
    canvas2.create_axes_layout(AxesLayoutSpec.grid(1, 1))
    canvas2.add_curve("x**2", 0, 3, "-", "#ff7f0e", "BetaLine")

    harness.pump(80)
    harness.grab_main("lifecycle-03-multi-project-tabs-main")


def _scenario_figure_export(harness: SmokeHarness) -> None:
    canvas = harness.window.figure_window.current_canva
    if canvas is None:
        raise SmokeError("No active canvas for export scenario.")

    color_library = harness.window.figure_window.color_library
    dialog = FigureExportDialog(
        context=canvas.export_context(),
        color_library=color_library,
        export_preferences=None,
        export_callable=lambda req: None,
        parent=harness.window,
    )
    dialog.setModal(False)
    dialog.show()
    harness.pump(60)

    harness.grab(dialog, "lifecycle-04-export-dialog")
    dialog.reject()
    harness.pump(40)


def _scenario_canvas_popout(harness: SmokeHarness) -> None:
    canvas = harness.window.figure_window.current_canva
    if canvas is None:
        raise SmokeError("No active canvas for popout scenario.")

    canvas.open_canvas_window()
    harness.pump(100)

    popout = canvas._canvas_popout_window
    if popout is None or not popout.isVisible():
        raise SmokeError("Canvas popout window did not open.")

    harness.grab(popout, "lifecycle-05-canvas-popout-window")

    popout.close()
    harness.pump(60)

    if canvas._canvas_popout_window is not None:
        raise SmokeError("Canvas popout window remained after close.")

    harness.grab_canvas("lifecycle-06-canvas-restored-from-popout")
