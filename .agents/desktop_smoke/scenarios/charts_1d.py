"""1D Charts (Curve, Plot, Scatter, Error Bar, Fit, Interpolation) desktop smoke. Group id: charts_1d."""

from __future__ import annotations

from typing import Any, Callable

from mygui.figuremodify.axes_layout import AxesLayoutSpec
from mygui.figuremodify.components import ComponentKind, ComponentRole
from mygui.widgets.title_bar.titlebar_dialog.py_chart_dialog import (
    PyCurveDialog,
    PyErrorBarDialog,
    PyFitDialog,
    PyInterpolationDialog,
    PyPlotDialog,
    PyScatterDialog,
)

from desktop_smoke.harness import SmokeError, SmokeHarness
from desktop_smoke.creation_performance import measure_creation_performance


def run_charts_1d_scenarios(harness: SmokeHarness) -> list[dict[str, Any]]:
    """Walk through 1D charts: Curve, Plot, Scatter, Error Bar, Fit, Interpolation."""
    results: list[dict[str, Any]] = []

    results.append(
        _run_case(
            harness,
            "charts_1d.creation_performance",
            lambda: measure_creation_performance(harness),
        )
    )

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
        _run_case(
            harness,
            "charts_1d.errorbar",
            lambda: _scenario_errorbar(harness),
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


def _scenario_errorbar(harness: SmokeHarness) -> None:
    canvas = harness.create_project("Smoke_1D_ErrorBar")
    canvas.create_axes_layout(AxesLayoutSpec.grid(1, 1))
    harness.pump(50)
    x_ref, y_refs = harness.seed_multi_column_table(canvas)

    figure_window = harness.window.figure_window
    dialog = PyErrorBarDialog(
        dialog_name="Error Bar",
        figure_window=figure_window,
        parent=harness.window,
    )
    dialog.setModal(False)
    dialog.show()
    harness.pump(60)
    if dialog.height() > 720:
        raise SmokeError(
            f"Error Bar dialog is taller than its 720 px viewport: {dialog.height()}."
        )
    if dialog.scroll_area.verticalScrollBar().maximum() <= 0:
        raise SmokeError("Error Bar dialog content is not vertically scrollable.")
    if dialog.data_reference_input.get_x_ref() != x_ref:
        raise SmokeError("Error Bar dialog did not default X to the first column.")
    if dialog.data_reference_input.get_y_ref() != y_refs[0]:
        raise SmokeError("Error Bar dialog did not default Y to the second column.")
    # Y error: symmetric column; X error: asymmetric constant.
    dialog.data_reference_input.y_error_input.set_value(
        {"kind": "symmetric_ref", "ref": y_refs[1].to_dict()}
    )
    dialog.data_reference_input.x_error_input.set_value(
        {"kind": "constant", "minus": 0.05, "plus": 0.1}
    )
    dialog.style_group.ecolor_input.set_color("#C23B22")
    dialog.style_group.barsabove_input.setChecked(True)
    harness.grab(dialog, "charts1d-16-errorbar-dialog")

    dialog.accept()
    harness.pump(80)

    errorbars = canvas.component_registry.query(
        kind=ComponentKind.ERRORBAR, role=ComponentRole.ERROR_BAR
    )
    if not errorbars:
        raise SmokeError("Error Bar component was not created.")
    controller = errorbars[0]
    if controller.state.data["xerr"]["kind"] != "constant":
        raise SmokeError("Error Bar X error spec was not persisted as constant.")
    if controller.state.data["yerr"]["kind"] != "symmetric_ref":
        raise SmokeError(
            "Error Bar Y error spec was not persisted as symmetric_ref."
        )
    if controller.state.properties["ecolor"] != "#c23b22":
        raise SmokeError(
            "Error Bar dialog error color was not persisted: "
            f"{controller.state.properties['ecolor']!r}."
        )
    if not controller.state.properties["barsabove"]:
        raise SmokeError("Error Bar dialog barsabove switch was not persisted.")

    harness.select_component(controller.component_id)
    harness.grab_canvas("charts1d-17-errorbar-canvas")
    harness.grab_inspector("charts1d-18-errorbar-inspector")

    # Edit: raise capsize and restyle the error bars through the Controller.
    change = controller.set_property("capsize", 4.0)
    if not change.ok:
        raise SmokeError(f"Capsize edit failed: {change.message}")
    change = controller.set_property(
        "error_linestyle", {"kind": "custom", "offset": 0.0, "dashes": [4.0, 2.0]}
    )
    if not change.ok:
        raise SmokeError(f"Error linestyle edit failed: {change.message}")
    change = controller.set_property(
        "errorevery", {"kind": "stride", "start": 1, "step": 2}
    )
    if not change.ok:
        raise SmokeError(f"Errorevery edit failed: {change.message}")
    runtime = controller.resolve_target()
    if not runtime.caplines:
        raise SmokeError("Error Bar cap artists are missing after edit.")
    segments = {
        index: len(collection.get_segments())
        for index, collection in enumerate(runtime.barlinecols)
    }
    if all(count == 5 for count in segments.values()):
        raise SmokeError(
            "errorevery stride(1, 2) did not resample the error segments."
        )
    harness.grab_canvas("charts1d-19-errorbar-capsize")

    # Cover the remaining error modes through the production data service:
    # switch Y to an asymmetric column pair and X back to none.
    service = canvas.errorbar_service
    change = service.configure(
        controller,
        x_ref=x_ref,
        y_ref=y_refs[0],
        xerr={"kind": "none"},
        yerr={
            "kind": "asymmetric_ref",
            "minus_ref": y_refs[1].to_dict(),
            "plus_ref": y_refs[2].to_dict(),
        },
        preprocess=None,
    )
    if not change.ok:
        raise SmokeError(f"Asymmetric error edit failed: {change.message}")
    runtime_after = controller.resolve_target()
    if len(runtime_after.barlinecols) != 1 or len(runtime_after.caplines) != 2:
        raise SmokeError("Unexpected runtime structure after asymmetric edit.")
    if controller.state.data["xerr"]["kind"] != "none":
        raise SmokeError("Error Bar X error spec was not persisted as none.")
    harness.grab_canvas("charts1d-21-errorbar-asymmetric")

    # Delete through the production coordinator and verify cleanup.
    if not canvas.delete_component_group(
        (controller.component_id,), role_label="Error Bar"
    ):
        raise SmokeError("Error Bar deletion was rejected.")
    harness.pump(60)
    if canvas.component_registry.query(
        kind=ComponentKind.ERRORBAR, role=ComponentRole.ERROR_BAR
    ):
        raise SmokeError("Error Bar component survived deletion.")
    harness.grab_canvas("charts1d-20-errorbar-deleted")
