"""Field 2D (Contour, Heatmap, Pseudocolor) & Colorbar desktop smoke. Group id: field_2d."""

from __future__ import annotations

from typing import Any, Callable

from mygui.figuremodify.axes_layout import AxesLayoutSpec
from mygui.figuremodify.components import ComponentKind, ComponentRole
from mygui.widgets.title_bar.titlebar_dialog.py_chart_dialog import (
    PyContourDialog,
    PyHeatmapDialog,
    PyPseudocolorDialog,
)
from mygui.widgets.title_bar.titlebar_dialog.py_element_dialog import (
    PyColorbarDialog,
)

from desktop_smoke.harness import SmokeError, SmokeHarness


def run_field_2d_scenarios(harness: SmokeHarness) -> list[dict[str, Any]]:
    """Walk through 2D field charts (Contour, Heatmap, Pseudocolor) and Colorbar."""
    results: list[dict[str, Any]] = []

    results.append(
        _run_case(harness, "field_2d.contour", lambda: _scenario_contour(harness))
    )
    results.append(
        _run_case(harness, "field_2d.heatmap", lambda: _scenario_heatmap(harness))
    )
    results.append(
        _run_case(
            harness,
            "field_2d.pseudocolor",
            lambda: _scenario_pseudocolor(harness),
        )
    )
    results.append(
        _run_case(
            harness, "field_2d.colorbar", lambda: _scenario_colorbar(harness)
        )
    )
    results.append(
        _run_case(
            harness,
            "field_2d.validation_rollback",
            lambda: _scenario_validation_rollback(harness),
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


def _scenario_contour(harness: SmokeHarness) -> None:
    canvas = harness.create_project("Smoke_Contour")
    canvas.create_axes_layout(AxesLayoutSpec.grid(1, 1))
    harness.pump(50)
    x_ref, y_ref, z_ref = harness.seed_field_2d_table(canvas, n_x=6, n_y=6)

    figure_window = harness.window.figure_window
    dialog = PyContourDialog(
        dialog_name="Contour",
        figure_window=figure_window,
        parent=harness.window,
    )
    dialog.setModal(False)
    dialog.show()
    harness.pump(60)
    dialog.data_reference_input.set_refs(x_ref, y_ref, z_ref)
    harness.grab(dialog, "field2d-01-contour-dialog")

    dialog.accept()
    harness.pump(80)

    contours = canvas.component_registry.query(
        kind=ComponentKind.FIELD_2D, role=ComponentRole.CONTOUR
    )
    if not contours:
        raise SmokeError("Contour component was not created in registry.")
    contour_id = contours[0].component_id

    harness.select_component(contour_id)
    harness.grab_canvas("field2d-02-contour-canvas")
    harness.grab_inspector("field2d-03-contour-inspector")

    controller = canvas.component_registry.get(contour_id)
    if controller is None:
        raise SmokeError("Contour controller missing.")
    canvas.field_2d_service.apply_properties(
        controller,
        {"filled": True},
    )
    harness.pump(60)
    canvas.redraw()
    harness.grab_canvas("field2d-04-contour-filled-canvas")


def _scenario_heatmap(harness: SmokeHarness) -> None:
    canvas = harness.create_project("Smoke_Heatmap")
    canvas.create_axes_layout(AxesLayoutSpec.grid(1, 1))
    harness.pump(50)
    x_ref, y_ref, z_ref = harness.seed_field_2d_table(canvas, n_x=6, n_y=6)

    figure_window = harness.window.figure_window
    dialog = PyHeatmapDialog(
        dialog_name="Heatmap",
        figure_window=figure_window,
        parent=harness.window,
    )
    dialog.setModal(False)
    dialog.show()
    harness.pump(60)
    dialog.data_reference_input.set_refs(x_ref, y_ref, z_ref)
    harness.grab(dialog, "field2d-05-heatmap-dialog")

    dialog.accept()
    harness.pump(80)

    heatmaps = canvas.component_registry.query(
        kind=ComponentKind.FIELD_2D, role=ComponentRole.HEATMAP
    )
    if not heatmaps:
        raise SmokeError("Heatmap component was not created.")
    heatmap_id = heatmaps[0].component_id

    harness.select_component(heatmap_id)
    harness.grab_canvas("field2d-06-heatmap-canvas")
    harness.grab_inspector("field2d-07-heatmap-inspector")

    controller = canvas.component_registry.get(heatmap_id)
    if controller is not None:
        canvas.field_2d_service.apply_properties(
            controller,
            {"interpolation": "bilinear", "origin": "upper"},
        )
        harness.pump(60)
        canvas.redraw()
        harness.grab_canvas("field2d-08-heatmap-bilinear-canvas")


def _scenario_pseudocolor(harness: SmokeHarness) -> None:
    canvas = harness.create_project("Smoke_Pseudocolor")
    canvas.create_axes_layout(AxesLayoutSpec.grid(1, 1))
    harness.pump(50)
    x_ref, y_ref, z_ref = harness.seed_field_2d_table(canvas, n_x=6, n_y=6)

    figure_window = harness.window.figure_window
    dialog = PyPseudocolorDialog(
        dialog_name="Pseudocolor",
        figure_window=figure_window,
        parent=harness.window,
    )
    dialog.setModal(False)
    dialog.show()
    harness.pump(60)
    dialog.data_reference_input.set_refs(x_ref, y_ref, z_ref)
    harness.grab(dialog, "field2d-09-pseudocolor-dialog")

    dialog.accept()
    harness.pump(80)

    pseudocolors = canvas.component_registry.query(
        kind=ComponentKind.FIELD_2D, role=ComponentRole.PSEUDOCOLOR
    )
    if not pseudocolors:
        raise SmokeError("Pseudocolor component was not created.")
    pcolor_id = pseudocolors[0].component_id

    harness.select_component(pcolor_id)
    harness.grab_canvas("field2d-10-pseudocolor-canvas")
    harness.grab_inspector("field2d-11-pseudocolor-inspector")


def _scenario_colorbar(harness: SmokeHarness) -> None:
    canvas = harness.window.figure_window.current_canva
    if canvas is None:
        raise SmokeError("No active canvas for Colorbar scenario.")

    figure_window = harness.window.figure_window
    dialog = PyColorbarDialog(
        dialog_name="Colorbar",
        figure_window=figure_window,
        parent=harness.window,
    )
    dialog.setModal(False)
    dialog.show()
    harness.pump(60)
    harness.grab(dialog, "field2d-12-colorbar-dialog")

    dialog.accept()
    harness.pump(80)

    colorbars = canvas.component_registry.query(kind=ComponentKind.COLORBAR)
    if not colorbars:
        raise SmokeError("Colorbar component was not created.")
    cbar_id = colorbars[0].component_id

    harness.select_component(cbar_id)
    harness.grab_canvas("field2d-13-colorbar-canvas")
    harness.grab_inspector("field2d-14-colorbar-inspector")

    canvas.delete_components([cbar_id])
    harness.pump(60)
    canvas.redraw()
    harness.pump(40)

    if canvas.component_registry.query(kind=ComponentKind.COLORBAR):
        raise SmokeError("Colorbar was not removed after deletion request.")
    harness.grab_canvas("field2d-15-canvas-after-colorbar-removed")


def _scenario_validation_rollback(harness: SmokeHarness) -> None:
    from PySide6.QtCore import QTimer
    from mygui.database import ColumnRef

    canvas = harness.create_project("Smoke_Rollback")
    canvas.create_axes_layout(AxesLayoutSpec.grid(1, 1))
    harness.pump(50)

    subtable = harness.window.table.current_subtable()
    sheet = subtable.get_table(0).table_model.sheet
    bad_rows = [
        [0.0, 0.0, 1.0],
        [0.0, 0.0, 2.0],
        [1.0, 1.0, 3.0],
        [1.0, 1.0, 4.0],
    ]
    sheet.set_block(0, 0, bad_rows)
    harness.pump(40)
    x_ref = ColumnRef(canvas.project_id, sheet.id, sheet.columns[0].id)
    y_ref = ColumnRef(canvas.project_id, sheet.id, sheet.columns[1].id)
    z_ref = ColumnRef(canvas.project_id, sheet.id, sheet.columns[2].id)

    figure_window = harness.window.figure_window
    dialog = PyPseudocolorDialog(
        dialog_name="Pseudocolor",
        figure_window=figure_window,
        parent=harness.window,
    )
    dialog.setModal(False)
    dialog.show()
    harness.pump(60)
    dialog.data_reference_input.set_refs(x_ref, y_ref, z_ref)

    # Schedule modal dismissal right before accept
    QTimer.singleShot(0, harness.dismiss_confirmation)
    dialog.accept()
    harness.pump(80)
    harness.dismiss_all_dialogs()

    pseudocolors = canvas.component_registry.query(
        kind=ComponentKind.FIELD_2D, role=ComponentRole.PSEUDOCOLOR
    )
    if pseudocolors:
        raise SmokeError(
            "Pseudocolor was created from invalid duplicate grid data!"
        )
    harness.grab_main("field2d-16-validation-rollback-main")
