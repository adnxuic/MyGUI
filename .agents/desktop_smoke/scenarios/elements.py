"""Elements (Text, Reflection Marks, Reference Guides, In-Axes) desktop smoke. Group id: elements."""

from __future__ import annotations

from typing import Any, Callable

from mygui.figuremodify.axes_layout import AxesLayoutSpec
from mygui.figuremodify.components import ComponentKind, ComponentRole
from mygui.widgets.title_bar.titlebar_dialog.py_element_dialog import (
    PyInAxesDialog,
    PyReferenceBandDialog,
    PyReferenceLineDialog,
    PyReferenceMarksDialog,
    PyTextDialog,
)

from desktop_smoke.harness import SmokeError, SmokeHarness


def run_elements_scenarios(harness: SmokeHarness) -> list[dict[str, Any]]:
    """Walk through Figure elements: Text, Reflection Marks, Reference Line/Band, In-Axes."""
    results: list[dict[str, Any]] = []

    results.append(
        _run_case(harness, "elements.text", lambda: _scenario_text(harness))
    )
    results.append(
        _run_case(
            harness,
            "elements.reflection_marks",
            lambda: _scenario_reflection_marks(harness),
        )
    )
    results.append(
        _run_case(
            harness,
            "elements.reference_guides",
            lambda: _scenario_reference_guides(harness),
        )
    )
    results.append(
        _run_case(
            harness, "elements.in_axes", lambda: _scenario_in_axes(harness)
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


def _scenario_text(harness: SmokeHarness) -> None:
    canvas = harness.create_project("Smoke_Elem_Text")
    canvas.create_axes_layout(AxesLayoutSpec.grid(1, 1))
    harness.pump(50)

    figure_window = harness.window.figure_window
    dialog = PyTextDialog(
        dialog_name="Text",
        figure_window=figure_window,
        parent=harness.window,
    )
    dialog.setModal(False)
    dialog.show()
    harness.pump(60)

    dialog.text_edit.setText("Sample Label Text")
    dialog.x_input.setValue(0.5)
    dialog.y_input.setValue(0.5)
    harness.grab(dialog, "elements-01-text-dialog")

    dialog.accept()
    harness.pump(80)

    texts = canvas.component_registry.query(kind=ComponentKind.TEXT)
    if not texts:
        raise SmokeError("Text component was not created.")

    harness.select_component(texts[0].component_id)
    harness.grab_canvas("elements-02-text-canvas")
    harness.grab_inspector("elements-03-text-inspector")


def _scenario_reflection_marks(harness: SmokeHarness) -> None:
    canvas = harness.create_project("Smoke_Elem_RefMarks")
    canvas.create_axes_layout(AxesLayoutSpec.grid(1, 1))
    harness.pump(50)

    figure_window = harness.window.figure_window
    dialog = PyReferenceMarksDialog(
        dialog_name="Reflection Positions",
        figure_window=figure_window,
        parent=harness.window,
    )
    dialog.setModal(False)
    dialog.show()
    harness.pump(60)

    if hasattr(dialog.input, "positions_input"):
        dialog.input.positions_input.setText("15.2, 22.9, 31.5, 45.0")
    harness.grab(dialog, "elements-04-refmarks-dialog")

    dialog.accept()
    harness.pump(80)

    marks = canvas.component_registry.query(kind=ComponentKind.REFERENCE_MARKS)
    if not marks:
        raise SmokeError("Reference marks component was not created.")

    harness.select_component(marks[0].component_id)
    harness.grab_canvas("elements-05-refmarks-canvas")
    harness.grab_inspector("elements-06-refmarks-inspector")


def _scenario_reference_guides(harness: SmokeHarness) -> None:
    canvas = harness.create_project("Smoke_Elem_Guides")
    canvas.create_axes_layout(AxesLayoutSpec.grid(1, 1))
    harness.pump(50)

    figure_window = harness.window.figure_window

    # Reference Line
    line_dialog = PyReferenceLineDialog(
        dialog_name="Reference Line",
        figure_window=figure_window,
        parent=harness.window,
    )
    line_dialog.setModal(False)
    line_dialog.show()
    harness.pump(60)
    harness.grab(line_dialog, "elements-07-refline-dialog")
    line_dialog.accept()
    harness.pump(80)

    # Reference Band
    band_dialog = PyReferenceBandDialog(
        dialog_name="Reference Band",
        figure_window=figure_window,
        parent=harness.window,
    )
    band_dialog.setModal(False)
    band_dialog.show()
    harness.pump(60)
    harness.grab(band_dialog, "elements-08-refband-dialog")
    band_dialog.accept()
    harness.pump(80)

    lines = canvas.component_registry.query(
        kind=ComponentKind.REFERENCE_GUIDE, role=ComponentRole.REFERENCE_LINE
    )
    bands = canvas.component_registry.query(
        kind=ComponentKind.REFERENCE_GUIDE, role=ComponentRole.REFERENCE_BAND
    )
    if not lines or not bands:
        raise SmokeError("Reference Line or Band was not created.")

    harness.select_component(lines[0].component_id)
    harness.grab_canvas("elements-09-guides-canvas")
    harness.grab_inspector("elements-10-refline-inspector")

    harness.select_component(bands[0].component_id)
    harness.grab_inspector("elements-11-refband-inspector")


def _scenario_in_axes(harness: SmokeHarness) -> None:
    canvas = harness.create_project("Smoke_Elem_InAxes")
    canvas.create_axes_layout(AxesLayoutSpec.grid(1, 1))
    harness.pump(50)
    canvas.add_curve("x**2", 0, 5, "-", "#1f77b4", "curve")
    harness.pump(50)

    figure_window = harness.window.figure_window
    dialog = PyInAxesDialog(
        dialog_name="In-Axes",
        figure_window=figure_window,
        parent=harness.window,
    )
    dialog.setModal(False)
    dialog.show()
    harness.pump(60)
    harness.grab(dialog, "elements-12-inaxes-dialog")

    dialog.accept()
    harness.pump(80)

    insets = canvas.component_registry.query(kind=ComponentKind.IN_AXES)
    if not insets:
        raise SmokeError("In-Axes component was not created.")

    harness.select_component(insets[0].component_id)
    harness.grab_canvas("elements-13-inaxes-canvas")
    harness.grab_inspector("elements-14-inaxes-inspector")
