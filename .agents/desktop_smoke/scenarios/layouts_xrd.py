"""Layouts & FullProf XRD Refinement desktop smoke. Group id: layouts_xrd."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from mygui.figuremodify.components import ComponentKind
from mygui.widgets.title_bar.titlebar_dialog.py_title_bar_dialog import (
    PyLayoutDialog,
)

from desktop_smoke.harness import SmokeError, SmokeHarness

XRD_FIXTURE_PATH = Path("tests/test_datas/XRD/YBCO.prf")


def run_layouts_xrd_scenarios(harness: SmokeHarness) -> list[dict[str, Any]]:
    """Walk through layout templates and FullProf XRD refinement import."""
    results: list[dict[str, Any]] = []

    results.append(
        _run_case(
            harness, "layouts_xrd.templates", lambda: _scenario_templates(harness)
        )
    )
    results.append(
        _run_case(
            harness, "layouts_xrd.xrd_single", lambda: _scenario_xrd_single(harness)
        )
    )
    results.append(
        _run_case(
            harness,
            "layouts_xrd.xrd_main_residual",
            lambda: _scenario_xrd_main_residual(harness),
        )
    )
    results.append(
        _run_case(
            harness,
            "layouts_xrd.compressed_geometry_edit",
            lambda: _scenario_compressed_layout_edit(harness),
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


def _scenario_templates(harness: SmokeHarness) -> None:
    figure_window = harness.window.figure_window

    presets = [
        ("single", "Single Axes"),
        ("horizontal_compare", "Horizontal Comparison"),
        ("vertical_stack", "Vertical Stack"),
        ("grid_2x2", "2x2 Grid"),
        ("grid_3x3", "3x3 Grid"),
        ("primary_right_y", "Primary + Right Y"),
        ("main_residual", "Main Plot + Residual"),
    ]

    for key, title in presets:
        canvas = harness.create_project(f"Layout_{key}")
        harness.pump(40)

        dialog = PyLayoutDialog(
            dialog_name=title,
            figure_window=figure_window,
            preset_key=key,
            parent=harness.window,
        )
        dialog.setModal(False)
        dialog.show()
        harness.pump(50)
        harness.grab(dialog, f"layout-dialog-{key}")

        dialog.accept()
        harness.pump(80)

        axes = canvas.component_registry.query(kind=ComponentKind.AXES)
        if not axes:
            raise SmokeError(f"Layout {key} created no Axes.")

        harness.grab_canvas(f"layout-canvas-{key}")


def _scenario_xrd_single(harness: SmokeHarness) -> None:
    if not XRD_FIXTURE_PATH.is_file():
        raise SmokeError(f"XRD fixture {XRD_FIXTURE_PATH} not found.")

    canvas = harness.create_project("XRD_Single")
    figure_window = harness.window.figure_window

    dialog = PyLayoutDialog(
        dialog_name="Single Axes",
        figure_window=figure_window,
        preset_key="single",
        parent=harness.window,
    )
    dialog.setModal(False)
    dialog.show()
    harness.pump(50)

    # Switch to XRD Refinement tab
    if dialog.input.tabs is not None and dialog.xrd_input is not None:
        dialog.input.tabs.setCurrentWidget(dialog.xrd_input)
        dialog.xrd_input.import_checkbox.setChecked(True)
        dialog.xrd_input.file_input.setText(str(XRD_FIXTURE_PATH.resolve()))
        dialog.xrd_input.parse_selected_file()
        harness.pump(60)

    harness.grab(dialog, "xrd-01-single-dialog")
    dialog.accept()
    harness.pump(120)

    # Check that XRD components were created
    scatters = canvas.component_registry.query(kind=ComponentKind.SCATTER)
    plots = canvas.component_registry.query(kind=ComponentKind.LINE)
    marks = canvas.component_registry.query(kind=ComponentKind.REFERENCE_MARKS)

    if not scatters or not plots or not marks:
        raise SmokeError("Single Axes XRD import did not create all components.")

    harness.grab_canvas("xrd-02-single-canvas")
    harness.grab_main("xrd-03-single-main-with-tables")


def _scenario_xrd_main_residual(harness: SmokeHarness) -> None:
    canvas = harness.create_project("XRD_MainResidual")
    figure_window = harness.window.figure_window

    dialog = PyLayoutDialog(
        dialog_name="Main Plot + Residual",
        figure_window=figure_window,
        preset_key="main_residual",
        parent=harness.window,
    )
    dialog.setModal(False)
    dialog.show()
    harness.pump(50)

    if dialog.input.tabs is not None and dialog.xrd_input is not None:
        dialog.input.tabs.setCurrentWidget(dialog.xrd_input)
        dialog.xrd_input.import_checkbox.setChecked(True)
        dialog.xrd_input.file_input.setText(str(XRD_FIXTURE_PATH.resolve()))
        dialog.xrd_input.parse_selected_file()
        harness.pump(60)

    harness.grab(dialog, "xrd-04-main-residual-dialog")
    dialog.accept()
    harness.pump(120)

    axes = canvas.component_registry.query(kind=ComponentKind.AXES)
    if len(axes) < 2:
        raise SmokeError(
            f"Expected at least 2 Axes in XRD Main+Residual, got {len(axes)}."
        )

    harness.grab_canvas("xrd-05-main-residual-canvas")


def _scenario_compressed_layout_edit(harness: SmokeHarness) -> None:
    canvas = harness.create_project("Compressed_Layout")
    figure_window = harness.window.figure_window
    root_ctrl = canvas.component_registry.get(canvas.root_component_id)

    # Configure Figure with compressed layout engine
    compressed_engine = {
        "kind": "compressed",
        "params": {
            "w_pad": 0.05,
            "h_pad": 0.05,
            "wspace": 0.15,
            "hspace": 0.15,
            "rect": None,
        },
    }
    result = root_ctrl.set_property("layout_engine", compressed_engine)
    if not result.ok:
        raise SmokeError(
            f"Failed to set compressed layout engine: {result.message}"
        )
    harness.pump(40)

    # Open layout dialog
    dialog = PyLayoutDialog(
        dialog_name="Horizontal Comparison",
        figure_window=figure_window,
        preset_key="horizontal_compare",
        parent=harness.window,
    )
    dialog.setModal(False)
    dialog.show()
    harness.pump(50)

    # Check read-only notice
    notice_text = dialog.input.layout_engine_notice.text()
    if "Compressed" not in notice_text:
        raise SmokeError(
            f"Expected 'Compressed' in layout notice, got {notice_text!r}"
        )
    if "Figure Inspector" not in notice_text:
        raise SmokeError(
            f"Expected 'Figure Inspector' in layout notice, got {notice_text!r}"
        )
    if "adjusted by" not in notice_text:
        raise SmokeError(
            f"Expected engine adjustment warning in layout notice, got {notice_text!r}"
        )

    harness.grab(dialog, "layout-06-compressed-dialog")
    dialog.accept()
    harness.pump(120)

    # Verify Figure layout engine is unchanged
    current_engine = root_ctrl.state.properties.get("layout_engine")
    if current_engine != compressed_engine:
        raise SmokeError(
            f"Figure layout engine mutated! Expected {compressed_engine}, got {current_engine}"
        )

    axes = canvas.component_registry.query(kind=ComponentKind.AXES)
    if len(axes) != 2:
        raise SmokeError(
            f"Expected 2 Axes in Horizontal Comparison, got {len(axes)}"
        )

    harness.grab_canvas("layout-07-compressed-canvas")
