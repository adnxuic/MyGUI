"""1D Charts (Curve, Plot, Scatter, Fit, Interpolation) desktop smoke. Group id: charts_1d."""

from __future__ import annotations

from typing import Any, Callable

from mygui.figuremodify.axes_layout import AxesLayoutSpec
from mygui.figuremodify.components import ComponentKind, ComponentRole
from mygui.widgets.title_bar.titlebar_dialog.py_chart_dialog import (
    PyCurveDialog,
    PyFitDialog,
    PyInterpolationDialog,
    PyPlotDialog,
    PyScatterDialog,
)

from desktop_smoke.harness import SmokeError, SmokeHarness


def run_charts_1d_scenarios(harness: SmokeHarness) -> list[dict[str, Any]]:
    """Walk through 1D charts: Curve, Plot, Scatter, Fit, and Interpolation."""
    results: list[dict[str, Any]] = []

    results.append(
        _run_case(harness, "charts_1d.curve", lambda: _scenario_curve(harness))
    )
    results.append(
        _run_case(harness, "charts_1d.plot", lambda: _scenario_plot(harness))
    )
    results.append(
        _run_case(
            harness, "charts_1d.scatter", lambda: _scenario_scatter(harness)
        )
    )
    results.append(
        _run_case(harness, "charts_1d.fit", lambda: _scenario_fit(harness))
    )
    results.append(
        _run_case(
            harness,
            "charts_1d.interpolation",
            lambda: _scenario_interpolation(harness),
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


def _scenario_curve(harness: SmokeHarness) -> None:
    canvas = harness.create_project("Smoke_1D_Curve")
    canvas.create_axes_layout(AxesLayoutSpec.grid(1, 1))
    harness.pump(50)

    figure_window = harness.window.figure_window
    dialog = PyCurveDialog(
        dialog_name="Curve",
        figure_window=figure_window,
        parent=harness.window,
    )
    dialog.setModal(False)
    dialog.show()
    harness.pump(60)

    dialog.expression_edit.setText("sin(x) * exp(-0.2*x)")
    dialog.x_start_input.setValue(0.0)
    dialog.x_stop_input.setValue(10.0)
    harness.grab(dialog, "charts1d-01-curve-dialog")

    dialog.accept()
    harness.pump(80)

    curves = canvas.component_registry.query(
        kind=ComponentKind.LINE, role=ComponentRole.FUNCTION_CURVE
    )
    if not curves:
        raise SmokeError("Function curve was not created in registry.")
    curve_id = curves[0].component_id

    harness.select_component(curve_id)
    harness.grab_canvas("charts1d-02-curve-canvas")
    harness.grab_inspector("charts1d-03-curve-inspector")


def _scenario_plot(harness: SmokeHarness) -> None:
    canvas = harness.create_project("Smoke_1D_Plot")
    canvas.create_axes_layout(AxesLayoutSpec.grid(1, 1))
    harness.pump(50)
    x_ref, y_refs = harness.seed_multi_column_table(canvas)

    figure_window = harness.window.figure_window
    dialog = PyPlotDialog(
        dialog_name="Plot",
        figure_window=figure_window,
        parent=harness.window,
    )
    dialog.setModal(False)
    dialog.show()
    harness.pump(60)
    dialog.data_reference_input.set_x_ref(x_ref)
    dialog.data_reference_input.set_y_refs(y_refs)
    harness.grab(dialog, "charts1d-04-plot-dialog")

    dialog.accept()
    harness.pump(80)

    plots = canvas.component_registry.query(
        kind=ComponentKind.LINE, role=ComponentRole.DATA_PLOT
    )
    if len(plots) < 2:
        raise SmokeError(
            f"Expected at least 2 Data Plot components, found {len(plots)}."
        )

    harness.select_component(plots[0].component_id)
    harness.grab_canvas("charts1d-05-plot-canvas")
    harness.grab_inspector("charts1d-06-plot-inspector")


def _scenario_scatter(harness: SmokeHarness) -> None:
    canvas = harness.create_project("Smoke_1D_Scatter")
    canvas.create_axes_layout(AxesLayoutSpec.grid(1, 1))
    harness.pump(50)
    x_ref, y_refs = harness.seed_multi_column_table(canvas)

    figure_window = harness.window.figure_window
    dialog = PyScatterDialog(
        dialog_name="Scatter",
        figure_window=figure_window,
        parent=harness.window,
    )
    dialog.setModal(False)
    dialog.show()
    harness.pump(60)
    dialog.data_reference_input.set_x_ref(x_ref)
    dialog.data_reference_input.set_y_refs(y_refs[:2])
    harness.grab(dialog, "charts1d-07-scatter-dialog")

    dialog.accept()
    harness.pump(80)

    scatters = canvas.component_registry.query(kind=ComponentKind.SCATTER)
    if not scatters:
        raise SmokeError("Scatter component was not created.")

    harness.select_component(scatters[0].component_id)
    harness.grab_canvas("charts1d-08-scatter-canvas")
    harness.grab_inspector("charts1d-09-scatter-inspector")


def _scenario_fit(harness: SmokeHarness) -> None:
    canvas = harness.create_project("Smoke_1D_Fit")
    canvas.create_axes_layout(AxesLayoutSpec.grid(1, 1))
    harness.pump(50)
    x_ref, y_refs = harness.seed_multi_column_table(canvas)

    figure_window = harness.window.figure_window
    dialog = PyFitDialog(
        dialog_name="Fit Curve",
        figure_window=figure_window,
        parent=harness.window,
    )
    dialog.setModal(False)
    dialog.show()
    harness.pump(60)
    if hasattr(dialog.data_reference_input, "set_x_ref"):
        dialog.data_reference_input.set_x_ref(x_ref)
    if hasattr(dialog.data_reference_input, "set_y_ref"):
        dialog.data_reference_input.set_y_ref(y_refs[0])

    harness.grab(dialog, "charts1d-10-fit-dialog")
    dialog.accept()
    harness.pump(80)

    fits = canvas.component_registry.query(
        kind=ComponentKind.LINE, role=ComponentRole.FIT_CURVE
    )
    if not fits:
        raise SmokeError("Fit curve component was not created.")

    harness.select_component(fits[0].component_id)
    harness.grab_canvas("charts1d-11-fit-canvas")
    harness.grab_inspector("charts1d-12-fit-inspector")


def _scenario_interpolation(harness: SmokeHarness) -> None:
    canvas = harness.create_project("Smoke_1D_Interp")
    canvas.create_axes_layout(AxesLayoutSpec.grid(1, 1))
    harness.pump(50)
    x_ref, y_refs = harness.seed_multi_column_table(canvas)

    figure_window = harness.window.figure_window
    dialog = PyInterpolationDialog(
        dialog_name="Interpolation",
        figure_window=figure_window,
        parent=harness.window,
    )
    dialog.setModal(False)
    dialog.show()
    harness.pump(60)
    dialog.data_reference_input.set_x_ref(x_ref)
    dialog.data_reference_input.set_y_refs((y_refs[0],))
    harness.grab(dialog, "charts1d-13-interp-dialog")

    dialog.accept()
    harness.pump(80)

    interps = canvas.component_registry.query(
        kind=ComponentKind.LINE, role=ComponentRole.INTERPOLATION
    )
    if not interps:
        raise SmokeError("Interpolation component was not created.")

    harness.select_component(interps[0].component_id)
    harness.grab_canvas("charts1d-14-interp-canvas")
    harness.grab_inspector("charts1d-15-interp-inspector")
