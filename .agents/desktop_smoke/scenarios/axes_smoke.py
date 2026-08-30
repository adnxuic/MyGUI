"""Comprehensive Axes & Axes-Structure desktop smoke test.

Group id: axes_smoke.
Covers:
- Axes root (limits, margin, facecolor, box_aspect, visibility)
- Axes Structure (Left/Right/Top/Bottom Spines, Title, Legend)
- X Axis (locators, formatters, major/minor ticks, tick labels, major/minor grids, x-label)
- Y Axis (locators, formatters, major/minor ticks, tick labels, major/minor grids, y-label)
- Axes Geometry mode switching & Inspector UI controls (Grid vs Manual, spinboxes, clamp, reset, return to grid)
- Twin Axes coupled manual geometry & alignment
- Colorbar docking & follower scaling on manual axes, clean rebuild on grid return
- Multi-Axes mixed geometry & layout engine neutrality (none, tight, constrained)
- Schema v22 persistence save/restore visual roundtrip & pixel diffing
- Undo/Redo validation across geometry operations
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from pathlib import Path
import tempfile
from typing import Any, Callable

from PIL import Image, ImageChops

from mygui.database import ColumnRef
from mygui.figuremodify.axes_layout import AxesLayoutSpec, ShareMode
from mygui.figuremodify.components import ComponentKind, ComponentRole
from mygui.figuremodify.style_base.color_models import ColorSelection
from mygui.project_io import (
    PROJECT_SCHEMA_VERSION,
    load_project_file,
    restore_project_snapshot,
    save_project_snapshot,
)
from mygui.widgets.fig_control_window.component_editors.sections.axes import (
    AxesLayoutSection,
)
from mygui.widgets.fig_control_window.component_editors.sections.axis_ticks import (
    AxisTickSettingsDialog,
    AxisTickSettingsSection,
)
from tests.axes_helpers import create_regular_axes, create_twin_axes_pair

from desktop_smoke.harness import SmokeError, SmokeHarness

MAPPED_COLOR = {
    "enabled": True,
    "cmap": "viridis",
    "norm": {
        "kind": "linear",
        "params": {"vmin": None, "vmax": None, "clip": False},
    },
    "bad": "#00000000",
    "under": None,
    "over": None,
    "nonfinite": "drop",
}


def run_axes_smoke_scenarios(harness: SmokeHarness) -> list[dict[str, Any]]:
    """Execute all Axes-related smoke scenarios."""
    results: list[dict[str, Any]] = []

    results.append(
        _run_case(harness, "axes_smoke.axes_root", lambda: _scenario_axes_root(harness))
    )
    results.append(
        _run_case(
            harness,
            "axes_smoke.axes_structure_spines",
            lambda: _scenario_axes_structure_spines(harness),
        )
    )
    results.append(
        _run_case(
            harness,
            "axes_smoke.axes_structure_title",
            lambda: _scenario_axes_structure_title(harness),
        )
    )
    results.append(
        _run_case(
            harness,
            "axes_smoke.axes_structure_legend",
            lambda: _scenario_axes_structure_legend(harness),
        )
    )
    results.append(
        _run_case(
            harness, "axes_smoke.x_axis_system", lambda: _scenario_x_axis_system(harness)
        )
    )
    results.append(
        _run_case(
            harness, "axes_smoke.y_axis_system", lambda: _scenario_y_axis_system(harness)
        )
    )
    results.append(
        _run_case(
            harness,
            "axes_smoke.geometry_mode_and_inspector",
            lambda: _scenario_geometry_mode_and_inspector(harness),
        )
    )
    results.append(
        _run_case(
            harness,
            "axes_smoke.twin_axes_coupling",
            lambda: _scenario_twin_axes_coupling(harness),
        )
    )
    results.append(
        _run_case(
            harness,
            "axes_smoke.colorbar_followers",
            lambda: _scenario_colorbar_followers(harness),
        )
    )
    results.append(
        _run_case(
            harness,
            "axes_smoke.mixed_layout_engines",
            lambda: _scenario_mixed_layout_engines(harness),
        )
    )
    results.append(
        _run_case(
            harness,
            "axes_smoke.shared_tickers_v22_roundtrip",
            lambda: _scenario_shared_tickers_v22_roundtrip(harness),
        )
    )
    results.append(
        _run_case(
            harness,
            "axes_smoke.schema_v22_persistence_roundtrip",
            lambda: _scenario_schema_v22_persistence_roundtrip(harness),
        )
    )
    results.append(
        _run_case(
            harness,
            "axes_smoke.undo_redo_validation",
            lambda: _scenario_undo_redo_validation(harness),
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


def _verify_canvas_changed(
    harness: SmokeHarness,
    before_path: Path,
    after_name: str,
    action_description: str,
) -> Path:
    """Capture post-action canvas screenshot, verify pixel difference > 0."""
    canvas = harness.window.figure_window.current_canva
    if canvas is not None:
        try:
            canvas.draw()
        except Exception:
            pass
    harness.pump(60)
    after_path = harness.grab_canvas(after_name)

    img_before = Image.open(before_path).convert("RGB")
    img_after = Image.open(after_path).convert("RGB")

    diff = ImageChops.difference(img_before, img_after)
    bbox = diff.getbbox()
    if bbox is None:
        raise SmokeError(
            f"Fake implementation / No canvas change detected after '{action_description}'. "
            f"Canvas before ({before_path.name}) and after ({after_path.name}) are pixel-identical!"
        )
    return after_path


def _setup_test_project(harness: SmokeHarness, project_name: str) -> tuple[Any, str, Any]:
    """Create a project with 1x1 Axes, a curve, and a plot to ensure visual context."""
    canvas = harness.create_project(project_name)
    axes_ids = canvas.create_axes_layout(
        AxesLayoutSpec.grid(
            1,
            1,
            cell_view=canvas.axes_layout_service.creation_view_defaults(),
        )
    )
    if not axes_ids:
        raise SmokeError("Axes creation failed.")
    axes_id = str(axes_ids[0])
    harness.pump(50)

    # Populate table with test data
    subtable = harness.window.table.current_subtable()
    sheet = subtable.get_table(0).table_model.sheet
    rows = [
        [1.0, 2.0, 5.0],
        [2.0, 4.0, 8.0],
        [3.0, 6.0, 11.0],
        [4.0, 8.0, 14.0],
        [5.0, 10.0, 17.0],
        [6.0, 12.0, 20.0],
        [7.0, 14.0, 23.0],
        [8.0, 16.0, 26.0],
    ]
    sheet.set_block(0, 0, rows)
    x_ref = ColumnRef(canvas.project_id, sheet.id, sheet.columns[0].id)
    y1_ref = ColumnRef(canvas.project_id, sheet.id, sheet.columns[1].id)
    y2_ref = ColumnRef(canvas.project_id, sheet.id, sheet.columns[2].id)
    harness.pump(40)

    # Add a function curve and a data plot
    canvas.add_curve("2 * x", 1, 8, "-", "#1f77b4", "Linear Curve")
    canvas.add_plots(
        x_ref,
        (y1_ref, y2_ref),
        style="--",
        size=6.0,
        linewidth=1.5,
        preprocess=None,
        color_selection=ColorSelection(color="#ff7f0e"),
    )
    canvas.axes_commands.ensure_legend(axes_id)
    harness.pump(80)
    canvas.redraw()
    harness.pump(50)

    target_ax = canvas.component_registry.resolve_target(axes_id)
    return canvas, axes_id, target_ax


def _axes_layout_section(harness: SmokeHarness, axes_id: str) -> AxesLayoutSection:
    """Retrieve the exact AxesLayoutSection for the selected Axes."""
    harness.select_component(axes_id)
    inspector_host = harness.window.fig_control_window.figure_inspector_host
    figure_inspector = inspector_host.current_figure_inspector()
    if figure_inspector is None:
        raise SmokeError("Current figure inspector panel not found in host!")
    panel = figure_inspector.axes_inspector(axes_id)
    if panel is None:
        raise SmokeError(f"Axes inspector panel not found for axes {axes_id!r}")
    inspector = panel.semantic_panel.inspector(axes_id)
    if inspector is None:
        raise SmokeError(f"Component inspector not found for axes {axes_id!r}")
    section = inspector.section("layout")
    if not isinstance(section, AxesLayoutSection):
        raise SmokeError(f"Layout section is not AxesLayoutSection for {axes_id!r}")
    return section


def _axis_tick_section(
    harness: SmokeHarness,
    canvas,
    axis_id: str,
) -> AxisTickSettingsSection:
    """Retrieve the unified tick section for one selected Axis."""

    harness.select_component(axis_id)
    inspector_host = harness.window.fig_control_window.figure_inspector_host
    figure_inspector = inspector_host.current_figure_inspector()
    if figure_inspector is None:
        raise SmokeError("Current figure inspector panel not found in host!")
    axis = canvas.component_registry.get(axis_id)
    panel = figure_inspector.axes_inspector(axis.state.parent_id)
    if panel is None:
        raise SmokeError(f"Axes inspector panel not found for Axis {axis_id!r}")
    inspector = panel.semantic_panel.inspector(axis_id)
    if inspector is None:
        raise SmokeError(f"Axis inspector not found for {axis_id!r}")
    section = inspector.section("ticks_labels")
    if not isinstance(section, AxisTickSettingsSection):
        raise SmokeError(
            f"Ticks & Labels section is not AxisTickSettingsSection for {axis_id!r}"
        )
    return section


def _scenario_axes_root(harness: SmokeHarness) -> None:
    """Test Axes Root Component (facecolor, limits, margins, box_aspect, visible)."""
    canvas, axes_id, ax = _setup_test_project(harness, "Smoke_Axes_Root")

    # Select Axes root
    harness.select_component(axes_id)
    harness.grab_inspector("axes-01-root-inspector")
    before_p = harness.grab_canvas("axes-01-root-initial-canvas")

    axes_ctrl = canvas.component_registry.get(axes_id)

    # 1. Modify facecolor
    axes_ctrl.set_property("facecolor", "#FFF9E6")  # Light warm yellow
    harness.pump(60)
    canvas.redraw()
    harness.pump(50)

    # Verify live Matplotlib Artist
    facecolor_rgba = ax.get_facecolor()
    if facecolor_rgba[0] < 0.9 or facecolor_rgba[1] < 0.9:
        raise SmokeError(f"Artist facecolor did not update! Got {facecolor_rgba}")
    before_p = _verify_canvas_changed(
        harness, before_p, "axes-02-facecolor-changed", "Axes facecolor changed to #FFF9E6"
    )

    # 2. Modify limits
    axes_ctrl.set_property("xlim", (0.0, 10.0))
    axes_ctrl.set_property("ylim", (0.0, 30.0))
    axes_ctrl.set_property("autoscalex_on", False)
    axes_ctrl.set_property("autoscaley_on", False)
    harness.pump(60)
    canvas.redraw()
    harness.pump(50)

    xlim = ax.get_xlim()
    ylim = ax.get_ylim()
    if abs(xlim[0] - 0.0) > 0.01 or abs(xlim[1] - 10.0) > 0.01:
        raise SmokeError(f"Artist xlim did not update! Got {xlim}")
    if abs(ylim[0] - 0.0) > 0.01 or abs(ylim[1] - 30.0) > 0.01:
        raise SmokeError(f"Artist ylim did not update! Got {ylim}")
    before_p = _verify_canvas_changed(
        harness, before_p, "axes-03-limits-changed", "Axes limits changed to [0,10],[0,30]"
    )

    # 3. Modify box_aspect
    axes_ctrl.set_property("box_aspect", 1.0)
    harness.pump(60)
    canvas.redraw()
    harness.pump(50)

    if ax.get_box_aspect() != 1.0:
        raise SmokeError(f"Artist box_aspect did not update! Got {ax.get_box_aspect()}")
    before_p = _verify_canvas_changed(
        harness, before_p, "axes-04-box-aspect-changed", "Axes box_aspect set to 1.0"
    )

    # 4. Modify visible (toggle False then True)
    axes_ctrl.set_property("visible", False)
    harness.pump(60)
    canvas.redraw()
    harness.pump(50)
    if ax.get_visible():
        raise SmokeError("Artist visible did not update to False!")
    before_p = _verify_canvas_changed(
        harness, before_p, "axes-05-invisible-canvas", "Axes visible set to False"
    )

    axes_ctrl.set_property("visible", True)
    harness.pump(60)
    canvas.redraw()
    harness.pump(50)
    if not ax.get_visible():
        raise SmokeError("Artist visible did not update to True!")
    _verify_canvas_changed(
        harness, before_p, "axes-06-visible-restored", "Axes visible restored to True"
    )


def _scenario_axes_structure_spines(harness: SmokeHarness) -> None:
    """Test Axes Structure Spines (Left, Right, Top, Bottom)."""
    canvas, axes_id, ax = _setup_test_project(harness, "Smoke_Axes_Spines")
    before_p = harness.grab_canvas("axes-spines-00-initial")

    # Query spine controllers
    spines = {
        ctrl.state.selector.get("name"): ctrl
        for ctrl in canvas.component_registry.query(kind=ComponentKind.SPINE)
        if ctrl.state.parent_id == axes_id
    }
    if set(spines.keys()) != {"left", "right", "top", "bottom"}:
        raise SmokeError(f"Missing spine controllers: found {list(spines.keys())}")

    # 1. Left Spine: make it thick red dashed
    left_ctrl = spines["left"]
    harness.select_component(left_ctrl.component_id)
    harness.grab_inspector("axes-spines-01-left-inspector")

    left_ctrl.set_property("color", "#E74C3C")
    left_ctrl.set_property("linewidth", 3.5)
    left_ctrl.set_property("linestyle", "--")
    harness.pump(60)
    canvas.redraw()
    harness.pump(50)

    left_spine = ax.spines["left"]
    if left_spine.get_linewidth() != 3.5:
        raise SmokeError(f"Left spine linewidth did not update: {left_spine.get_linewidth()}")
    if left_spine.get_linestyle() != "--":
        raise SmokeError(f"Left spine linestyle did not update: {left_spine.get_linestyle()}")
    before_p = _verify_canvas_changed(
        harness, before_p, "axes-spines-02-left-thick-red", "Left spine styled to thick red dashed"
    )

    # 2. Bottom Spine: make it thick blue with outward offset
    bottom_ctrl = spines["bottom"]
    harness.select_component(bottom_ctrl.component_id)
    bottom_ctrl.set_property("color", "#2980B9")
    bottom_ctrl.set_property("linewidth", 3.0)
    bottom_ctrl.set_property("position", ("outward", 8.0))
    harness.pump(60)
    canvas.redraw()
    harness.pump(50)

    bottom_spine = ax.spines["bottom"]
    if bottom_spine.get_linewidth() != 3.0:
        raise SmokeError(f"Bottom spine linewidth did not update: {bottom_spine.get_linewidth()}")
    pos = bottom_spine.get_position()
    if pos[0] != "outward" or abs(pos[1] - 8.0) > 0.1:
        raise SmokeError(f"Bottom spine position did not update: {pos}")
    before_p = _verify_canvas_changed(
        harness, before_p, "axes-spines-03-bottom-outward", "Bottom spine styled outward blue"
    )

    # 3. Top & Right Spines: hide them
    top_ctrl = spines["top"]
    right_ctrl = spines["right"]
    top_ctrl.set_property("visible", False)
    right_ctrl.set_property("visible", False)
    harness.pump(60)
    canvas.redraw()
    harness.pump(50)

    if ax.spines["top"].get_visible():
        raise SmokeError("Top spine visible is not False in artist!")
    if ax.spines["right"].get_visible():
        raise SmokeError("Right spine visible is not False in artist!")
    _verify_canvas_changed(
        harness, before_p, "axes-spines-04-top-right-hidden", "Top and right spines hidden"
    )


def _scenario_axes_structure_title(harness: SmokeHarness) -> None:
    """Test Title component (text, size, weight, color, alignment, background box)."""
    canvas, axes_id, ax = _setup_test_project(harness, "Smoke_Axes_Title")
    before_p = harness.grab_canvas("axes-title-00-initial")

    title_ctrls = canvas.component_registry.query(
        kind=ComponentKind.TEXT, role=ComponentRole.TITLE
    )
    if not title_ctrls:
        raise SmokeError("Title controller not found in registry.")
    title_ctrl = title_ctrls[0]

    harness.select_component(title_ctrl.component_id)
    harness.grab_inspector("axes-title-01-inspector")

    # Set Title properties
    title_ctrl.set_property("text", "Axes Smoke Verified Title")
    title_ctrl.set_property("fontsize", 16.0)
    title_ctrl.set_property("fontweight", "bold")
    title_ctrl.set_property("color", "#D9534F")
    title_ctrl.set_property("horizontalalignment", "left")
    title_ctrl.set_property("bbox", {
        "enabled": True,
        "facecolor": "#FFFF99",
        "edgecolor": "#333333",
        "boxstyle": "round,pad=0.3",
        "alpha": 1.0,
        "linewidth": 1.0,
    })
    harness.pump(60)
    canvas.redraw()
    harness.pump(50)

    # Check Artist
    title_artist = ax.title
    if title_artist.get_text() != "Axes Smoke Verified Title":
        raise SmokeError(f"Title text did not update: {title_artist.get_text()}")
    if abs(title_artist.get_fontsize() - 16.0) > 0.5:
        raise SmokeError(f"Title font size did not update: {title_artist.get_fontsize()}")

    _verify_canvas_changed(
        harness, before_p, "axes-title-02-styled", "Title configured with text, font and box"
    )


def _scenario_axes_structure_legend(harness: SmokeHarness) -> None:
    """Test Legend component (title, location, ncols, frame, fancybox, shadow)."""
    canvas, axes_id, ax = _setup_test_project(harness, "Smoke_Axes_Legend")
    before_p = harness.grab_canvas("axes-legend-00-initial")

    legend_ctrls = canvas.component_registry.query(
        kind=ComponentKind.LEGEND, role=ComponentRole.LEGEND
    )
    if not legend_ctrls:
        raise SmokeError("Legend controller not found in registry.")
    legend_ctrl = legend_ctrls[0]

    harness.select_component(legend_ctrl.component_id)
    harness.grab_inspector("axes-legend-01-inspector")

    legend_ctrl.set_property("title", "Curves Legend")
    legend_ctrl.set_property("location", "upper left")
    legend_ctrl.set_property("ncols", 2)
    legend_ctrl.set_property("frameon", True)
    legend_ctrl.set_property("facecolor", "#E8F5E9")  # Soft light green
    legend_ctrl.set_property("edgecolor", "#2E7D32")  # Forest green
    legend_ctrl.set_property("fancybox", True)
    legend_ctrl.set_property("shadow", True)
    legend_ctrl.set_property("framealpha", 0.9)
    legend_ctrl.set_property("frame_linewidth", 1.5)
    harness.pump(60)
    canvas.redraw()
    harness.pump(50)

    legend_artist = ax.get_legend()
    if legend_artist is None or not legend_artist.get_visible():
        raise SmokeError("Legend is missing or not visible!")
    if legend_artist.get_title().get_text() != "Curves Legend":
        raise SmokeError(f"Legend title did not update: {legend_artist.get_title().get_text()}")
    if legend_artist._ncols != 2:
        raise SmokeError(f"Legend ncols did not update: {legend_artist._ncols}")

    _verify_canvas_changed(
        harness, before_p, "axes-legend-02-styled", "Legend configured with title, 2 cols, frame"
    )


def _scenario_x_axis_system(harness: SmokeHarness) -> None:
    """Test complete X Axis sub-components (Axis root, Ticks, Tick Labels, Grids, X Label)."""
    canvas, axes_id, ax = _setup_test_project(harness, "Smoke_X_Axis_System")
    before_p = harness.grab_canvas("axes-xaxis-00-initial")

    # 1. X Axis Root: set major locator & formatter
    x_axis_ctrls = canvas.component_registry.query(
        kind=ComponentKind.AXIS, role=ComponentRole.X_AXIS
    )
    if not x_axis_ctrls:
        raise SmokeError("X Axis controller not found.")
    x_axis_ctrl = x_axis_ctrls[0]

    harness.select_component(x_axis_ctrl.component_id)
    harness.grab_inspector("axes-xaxis-01-root-inspector")

    # Exercise the native unified dialog: fixed-row preview, cancel, one Undo.
    tick_section = _axis_tick_section(harness, canvas, x_axis_ctrl.component_id)
    if not tick_section.configure_button.isEnabled():
        raise SmokeError("Ticks & Labels entry is disabled for an ordinary X Axis.")
    opening = canvas.axis_tick_settings_service.snapshot(x_axis_ctrl.component_id)
    fixed_locator = {
        "kind": "fixed",
        "params": {"locations": [0.0, 1.0, 2.0, 3.0, 4.0], "nbins": None},
    }
    fixed_formatter = {
        "kind": "fixed",
        "params": {"labels": ["zero", "one", "two", "three", "four"]},
    }
    dialog = AxisTickSettingsDialog(
        opening,
        context=canvas.editor_context,
        parent=tick_section,
    )
    dialog.major_page.locator_editor.set_value(fixed_locator, emit=True)
    dialog.major_page.formatter_editor.set_value(fixed_formatter, emit=True)
    dialog.show()
    harness.pump(250)
    harness.grab(dialog, "axes-xaxis-02-ticks-labels-fixed-preview")
    dialog.reject()
    dialog.deleteLater()
    harness.pump(30)
    if x_axis_ctrl.state != opening.expected_states[0]:
        raise SmokeError("Cancelling Ticks & Labels changed authoritative state.")

    undo_stack = harness.window.repository.undo_stack(canvas.project_id)
    command_count = undo_stack.count()
    dialog = AxisTickSettingsDialog(
        opening,
        context=canvas.editor_context,
        parent=tick_section,
    )
    dialog.major_page.locator_editor.set_value(fixed_locator, emit=True)
    dialog.major_page.formatter_editor.set_value(fixed_formatter, emit=True)
    dialog._accept_settings()
    harness.pump(80)
    if undo_stack.count() != command_count + 1:
        raise SmokeError("Unified tick confirmation did not create exactly one Undo.")
    if x_axis_ctrl.state.properties["major_locator"] != fixed_locator:
        raise SmokeError("Fixed Locator did not commit from the unified dialog.")
    if x_axis_ctrl.state.properties["major_formatter"] != fixed_formatter:
        raise SmokeError("Fixed Formatter did not commit from the unified dialog.")
    undo_stack.undo()
    harness.pump(50)
    if x_axis_ctrl.state != opening.expected_states[0]:
        raise SmokeError("Undo did not restore the opening tick snapshot.")
    undo_stack.redo()
    harness.pump(50)
    if x_axis_ctrl.state.properties["major_formatter"] != fixed_formatter:
        raise SmokeError("Redo did not restore the fixed tick labels.")
    dialog.deleteLater()

    x_axis_ctrl.set_property("major_locator", {
        "kind": "multiple",
        "params": {"base": 2.0, "offset": 0.0},
    })
    x_axis_ctrl.set_property("major_formatter", {
        "kind": "str_method",
        "params": {"format": "{x:.1f} s"},
    })
    harness.pump(60)
    canvas.redraw()
    harness.pump(50)
    before_p = _verify_canvas_changed(
        harness, before_p, "axes-xaxis-02-locator-formatter", "X Axis locator multiple 2.0 and format"
    )

    # 2. X Major Ticks: styling & direction
    x_maj_ticks = canvas.component_registry.query(
        kind=ComponentKind.TICK_GROUP, role=ComponentRole.MAJOR_TICK
    )
    x_maj_tick_ctrl = [c for c in x_maj_ticks if c.state.selector.get("axis") == "x"][0]
    harness.select_component(x_maj_tick_ctrl.component_id)
    harness.grab_inspector("axes-xaxis-03-major-ticks-inspector")

    x_maj_tick_ctrl.set_property("direction", "in")
    x_maj_tick_ctrl.set_property("length", 10.0)
    x_maj_tick_ctrl.set_property("width", 2.5)
    x_maj_tick_ctrl.set_property("color", "#C0392B")
    x_maj_tick_ctrl.set_property("secondary_visible", True)
    harness.pump(60)
    canvas.redraw()
    harness.pump(50)
    before_p = _verify_canvas_changed(
        harness, before_p, "axes-xaxis-04-major-ticks-styled", "X Major ticks set to in, thick red, top"
    )

    # 3. X Major Tick Labels: font & rotation
    x_maj_labels = canvas.component_registry.query(
        kind=ComponentKind.TICK_LABEL_GROUP, role=ComponentRole.MAJOR_TICK_LABEL
    )
    x_maj_label_ctrl = [c for c in x_maj_labels if c.state.selector.get("axis") == "x"][0]
    harness.select_component(x_maj_label_ctrl.component_id)
    harness.grab_inspector("axes-xaxis-05-major-tick-labels-inspector")

    x_maj_label_ctrl.set_property("fontsize", 12.0)
    x_maj_label_ctrl.set_property("fontweight", "bold")
    x_maj_label_ctrl.set_property("color", "#8E44AD")
    x_maj_label_ctrl.set_property("rotation", 45.0)
    harness.pump(60)
    canvas.redraw()
    harness.pump(50)
    before_p = _verify_canvas_changed(
        harness, before_p, "axes-xaxis-06-major-tick-labels-styled", "X Tick labels rotated 45 deg, purple bold"
    )

    # 4. X Minor Ticks
    x_min_ticks = canvas.component_registry.query(
        kind=ComponentKind.TICK_GROUP, role=ComponentRole.MINOR_TICK
    )
    x_min_tick_ctrl = [c for c in x_min_ticks if c.state.selector.get("axis") == "x"][0]
    x_axis_ctrl.set_property("minor_locator", {
        "kind": "multiple",
        "params": {"base": 0.5, "offset": 0.0},
    })
    x_min_tick_ctrl.set_property("primary_visible", True)
    x_min_tick_ctrl.set_property("length", 5.0)
    x_min_tick_ctrl.set_property("width", 1.5)
    x_min_tick_ctrl.set_property("color", "#2980B9")
    harness.pump(60)
    canvas.redraw()
    harness.pump(50)
    before_p = _verify_canvas_changed(
        harness, before_p, "axes-xaxis-07-minor-ticks", "X Minor ticks enabled at step 0.5"
    )

    # 5. X Major Grid
    x_grids = canvas.component_registry.query(kind=ComponentKind.GRID)
    x_maj_grid_ctrl = [
        c for c in x_grids
        if c.state.selector.get("axis") == "x" and c.state.selector.get("level") == "major"
    ][0]
    harness.select_component(x_maj_grid_ctrl.component_id)
    harness.grab_inspector("axes-xaxis-08-major-grid-inspector")

    x_maj_grid_ctrl.set_property("visible", True)
    x_maj_grid_ctrl.set_property("color", "#95A5A6")
    x_maj_grid_ctrl.set_property("linestyle", {"kind": "preset", "value": "--"})
    x_maj_grid_ctrl.set_property("linewidth", 1.5)
    x_maj_grid_ctrl.set_property("alpha", 0.8)
    harness.pump(60)
    canvas.redraw()
    harness.pump(50)
    before_p = _verify_canvas_changed(
        harness, before_p, "axes-xaxis-09-major-grid-styled", "X Major grid enabled with dashed gray"
    )

    # 6. X Minor Grid
    x_min_grid_ctrl = [
        c for c in x_grids
        if c.state.selector.get("axis") == "x" and c.state.selector.get("level") == "minor"
    ][0]
    x_min_grid_ctrl.set_property("visible", True)
    x_min_grid_ctrl.set_property("color", "#BDC3C7")
    x_min_grid_ctrl.set_property("linestyle", {"kind": "preset", "value": ":"})
    x_min_grid_ctrl.set_property("linewidth", 1.0)
    harness.pump(60)
    canvas.redraw()
    harness.pump(50)
    before_p = _verify_canvas_changed(
        harness, before_p, "axes-xaxis-10-minor-grid-styled", "X Minor grid enabled with dotted light-gray"
    )

    # 7. X Label
    x_label_ctrls = canvas.component_registry.query(
        kind=ComponentKind.TEXT, role=ComponentRole.X_LABEL
    )
    x_label_ctrl = x_label_ctrls[0]
    harness.select_component(x_label_ctrl.component_id)
    harness.grab_inspector("axes-xaxis-11-label-inspector")

    x_label_ctrl.set_property("text", "Time (seconds) [Smoke Verified]")
    x_label_ctrl.set_property("position", (0.5, 0.05))
    x_label_ctrl.set_property("fontsize", 14.0)
    x_label_ctrl.set_property("fontweight", "bold")
    x_label_ctrl.set_property("color", "#16A085")
    harness.pump(60)
    canvas.redraw()
    harness.pump(50)

    if ax.xaxis.label.get_text() != "Time (seconds) [Smoke Verified]":
        raise SmokeError(f"X Label text did not update: {ax.xaxis.label.get_text()}")
    _verify_canvas_changed(
        harness, before_p, "axes-xaxis-12-label-styled", "X Label configured with teal bold text"
    )


def _scenario_y_axis_system(harness: SmokeHarness) -> None:
    """Test complete Y Axis sub-components (Axis root, Ticks, Tick Labels, Grids, Y Label)."""
    canvas, axes_id, ax = _setup_test_project(harness, "Smoke_Y_Axis_System")
    before_p = harness.grab_canvas("axes-yaxis-00-initial")

    # 1. Y Axis Root: locator & formatter
    y_axis_ctrls = canvas.component_registry.query(
        kind=ComponentKind.AXIS, role=ComponentRole.Y_AXIS
    )
    if not y_axis_ctrls:
        raise SmokeError("Y Axis controller not found.")
    y_axis_ctrl = y_axis_ctrls[0]

    harness.select_component(y_axis_ctrl.component_id)
    harness.grab_inspector("axes-yaxis-01-root-inspector")

    y_axis_ctrl.set_property("major_locator", {
        "kind": "multiple",
        "params": {"base": 5.0, "offset": 0.0},
    })
    y_axis_ctrl.set_property("major_formatter", {
        "kind": "str_method",
        "params": {"format": "{x:.0f} mV"},
    })
    harness.pump(60)
    canvas.redraw()
    harness.pump(50)
    before_p = _verify_canvas_changed(
        harness, before_p, "axes-yaxis-02-locator-formatter", "Y Axis locator multiple 5.0 and format"
    )

    # 2. Y Major Ticks
    y_maj_ticks = canvas.component_registry.query(
        kind=ComponentKind.TICK_GROUP, role=ComponentRole.MAJOR_TICK
    )
    y_maj_tick_ctrl = [c for c in y_maj_ticks if c.state.selector.get("axis") == "y"][0]
    harness.select_component(y_maj_tick_ctrl.component_id)
    harness.grab_inspector("axes-yaxis-03-major-ticks-inspector")

    y_maj_tick_ctrl.set_property("direction", "in")
    y_maj_tick_ctrl.set_property("length", 8.0)
    y_maj_tick_ctrl.set_property("width", 2.0)
    y_maj_tick_ctrl.set_property("color", "#27AE60")
    y_maj_tick_ctrl.set_property("secondary_visible", True)
    harness.pump(60)
    canvas.redraw()
    harness.pump(50)
    before_p = _verify_canvas_changed(
        harness, before_p, "axes-yaxis-04-major-ticks-styled", "Y Major ticks set to in, green, right"
    )

    # 3. Y Major Tick Labels
    y_maj_labels = canvas.component_registry.query(
        kind=ComponentKind.TICK_LABEL_GROUP, role=ComponentRole.MAJOR_TICK_LABEL
    )
    y_maj_label_ctrl = [c for c in y_maj_labels if c.state.selector.get("axis") == "y"][0]
    harness.select_component(y_maj_label_ctrl.component_id)
    harness.grab_inspector("axes-yaxis-05-major-tick-labels-inspector")

    y_maj_label_ctrl.set_property("fontsize", 11.0)
    y_maj_label_ctrl.set_property("fontweight", "bold")
    y_maj_label_ctrl.set_property("color", "#2C3E50")
    y_maj_label_ctrl.set_property("rotation", 30.0)
    harness.pump(60)
    canvas.redraw()
    harness.pump(50)
    before_p = _verify_canvas_changed(
        harness, before_p, "axes-yaxis-06-major-tick-labels-styled", "Y Tick labels rotated 30 deg"
    )

    # 4. Y Minor Ticks
    y_min_ticks = canvas.component_registry.query(
        kind=ComponentKind.TICK_GROUP, role=ComponentRole.MINOR_TICK
    )
    y_min_tick_ctrl = [c for c in y_min_ticks if c.state.selector.get("axis") == "y"][0]
    y_axis_ctrl.set_property("minor_locator", {
        "kind": "multiple",
        "params": {"base": 1.0, "offset": 0.0},
    })
    y_min_tick_ctrl.set_property("primary_visible", True)
    y_min_tick_ctrl.set_property("length", 4.0)
    y_min_tick_ctrl.set_property("color", "#1ABC9C")
    harness.pump(60)
    canvas.redraw()
    harness.pump(50)
    before_p = _verify_canvas_changed(
        harness, before_p, "axes-yaxis-07-minor-ticks", "Y Minor ticks enabled at step 1.0"
    )

    # 5. Y Major Grid
    y_grids = canvas.component_registry.query(kind=ComponentKind.GRID)
    y_maj_grid_ctrl = [
        c for c in y_grids
        if c.state.selector.get("axis") == "y" and c.state.selector.get("level") == "major"
    ][0]
    harness.select_component(y_maj_grid_ctrl.component_id)
    harness.grab_inspector("axes-yaxis-08-major-grid-inspector")

    y_maj_grid_ctrl.set_property("visible", True)
    y_maj_grid_ctrl.set_property("color", "#E67E22")
    y_maj_grid_ctrl.set_property("linestyle", {"kind": "preset", "value": "--"})
    y_maj_grid_ctrl.set_property("linewidth", 1.2)
    harness.pump(60)
    canvas.redraw()
    harness.pump(50)
    before_p = _verify_canvas_changed(
        harness, before_p, "axes-yaxis-09-major-grid-styled", "Y Major grid enabled with orange dashed"
    )

    # 6. Y Minor Grid
    y_min_grid_ctrl = [
        c for c in y_grids
        if c.state.selector.get("axis") == "y" and c.state.selector.get("level") == "minor"
    ][0]
    y_min_grid_ctrl.set_property("visible", True)
    y_min_grid_ctrl.set_property("color", "#F39C12")
    y_min_grid_ctrl.set_property("linestyle", {"kind": "preset", "value": ":"})
    y_min_grid_ctrl.set_property("linewidth", 0.8)
    harness.pump(60)
    canvas.redraw()
    harness.pump(50)
    before_p = _verify_canvas_changed(
        harness, before_p, "axes-yaxis-10-minor-grid-styled", "Y Minor grid enabled with dotted yellow"
    )

    # 7. Y Label
    y_label_ctrls = canvas.component_registry.query(
        kind=ComponentKind.TEXT, role=ComponentRole.Y_LABEL
    )
    y_label_ctrl = y_label_ctrls[0]
    harness.select_component(y_label_ctrl.component_id)
    harness.grab_inspector("axes-yaxis-11-label-inspector")

    y_label_ctrl.set_property("text", "Voltage (mV) [Smoke Verified]")
    y_label_ctrl.set_property("fontsize", 14.0)
    y_label_ctrl.set_property("fontweight", "bold")
    y_label_ctrl.set_property("color", "#8E44AD")
    harness.pump(60)
    canvas.redraw()
    harness.pump(50)

    if ax.yaxis.label.get_text() != "Voltage (mV) [Smoke Verified]":
        raise SmokeError(f"Y Label text did not update: {ax.yaxis.label.get_text()}")
    _verify_canvas_changed(
        harness, before_p, "axes-yaxis-12-label-styled", "Y Label configured with purple bold text"
    )


def _scenario_geometry_mode_and_inspector(harness: SmokeHarness) -> None:
    """Test Axes Geometry mode transitions, interactive inspector spinboxes, buttons, and clamping."""
    canvas, axes_id, ax = _setup_test_project(harness, "Smoke_Axes_Geometry")
    harness.select_component(axes_id)
    harness.grab_inspector("axes-geom-01-grid-inspector")
    before_p = harness.grab_canvas("axes-geom-01-initial-canvas")

    section = _axes_layout_section(harness, axes_id)

    # Verify initial grid mode UI
    if section.grid_container.isHidden():
        raise SmokeError("grid_container should not be hidden initially!")
    if not section.manual_container.isHidden():
        raise SmokeError("manual_container should be hidden initially!")

    # 1. Click switch_manual_button
    harness.click(section.switch_manual_button)
    harness.pump(60)
    canvas.redraw()
    harness.pump(40)

    if not section.grid_container.isHidden():
        raise SmokeError("grid_container should be hidden after switching to manual!")
    if section.manual_container.isHidden():
        raise SmokeError("manual_container should not be hidden after switching to manual!")

    harness.grab_inspector("axes-geom-02-manual-inspector")
    target = canvas.component_registry.get(axes_id).resolve_target()
    if target.get_in_layout():
        raise SmokeError("Axes target get_in_layout() should be False in manual mode!")
    if target.get_subplotspec() is not None:
        raise SmokeError("Axes target get_subplotspec() should be None in manual mode!")

    # 2. Modify manual spinboxes
    init_left = section.left_spin.value()
    init_bottom = section.bottom_spin.value()
    init_width = section.width_spin.value()
    init_height = section.height_spin.value()

    new_left = round(min(0.8, init_left + 0.12), 4)
    new_bottom = round(min(0.8, init_bottom + 0.10), 4)
    new_width = round(max(0.1, init_width * 0.75), 4)
    new_height = round(max(0.1, init_height * 0.75), 4)

    section.left_spin.setValue(new_left)
    harness.pump(40)
    section.bottom_spin.setValue(new_bottom)
    harness.pump(40)
    section.width_spin.setValue(new_width)
    harness.pump(40)
    section.height_spin.setValue(new_height)
    harness.pump(60)
    canvas.redraw()
    harness.pump(50)

    # Verify computed labels
    expected_right = f"{new_left + new_width:.6f}"
    expected_top = f"{new_bottom + new_height:.6f}"
    if section.right_label.text() != expected_right:
        raise SmokeError(f"right_label mismatch: got {section.right_label.text()!r}, expected {expected_right!r}")
    if section.top_label.text() != expected_top:
        raise SmokeError(f"top_label mismatch: got {section.top_label.text()!r}, expected {expected_top!r}")

    before_p = _verify_canvas_changed(
        harness, before_p, "axes-geom-03-bounds-modified", "Axes manual bounds modified via spinboxes"
    )

    # 3. Test boundary clamping
    section.left_spin.setValue(0.85)
    harness.pump(30)
    section.width_spin.setValue(0.40)  # 0.85 + 0.40 = 1.25 > 1.0
    harness.pump(60)
    if section.width_spin.value() > 0.150001:
        raise SmokeError(f"width_spin was not clamped: got {section.width_spin.value()}")

    # 4. Click reset_button ("Reset Position")
    harness.click(section.reset_button)
    harness.pump(60)
    canvas.redraw()
    harness.pump(40)
    before_p = _verify_canvas_changed(
        harness, before_p, "axes-geom-04-reset-bounds", "Reset Position button restored grid cell bounds"
    )

    # 5. Click return_grid_button ("Return to Grid Layout")
    harness.click(section.return_grid_button)
    harness.pump(60)
    canvas.redraw()
    harness.pump(40)

    if section.grid_container.isHidden():
        raise SmokeError("grid_container should not be hidden after return to grid!")
    if not section.manual_container.isHidden():
        raise SmokeError("manual_container should be hidden after return to grid!")
    if not target.get_in_layout():
        raise SmokeError("Axes target get_in_layout() should be True in grid mode!")
    if target.get_subplotspec() is None:
        raise SmokeError("Axes target get_subplotspec() should not be None in grid mode!")

    harness.grab_inspector("axes-geom-05-returned-grid-inspector")
    _verify_canvas_changed(
        harness, before_p, "axes-geom-05-returned-to-grid", "Returned Axes to Grid layout"
    )


def _scenario_twin_axes_coupling(harness: SmokeHarness) -> None:
    """Test Twin Axes synchronized manual placement and twin badge in Inspector."""
    canvas = harness.create_project("Smoke_Twin_Axes_Coupling")
    primary_id, twin_id = create_twin_axes_pair(canvas)
    harness.pump(60)

    # Add curves to both axes
    canvas.add_curve("x", 1, 10, "-", "#1f77b4", "Primary Line")
    canvas.add_curve("100 - x**2", 1, 10, "--", "#d62728", "Twin Line")
    canvas.redraw()
    harness.pump(60)

    # Select Primary
    section = _axes_layout_section(harness, primary_id)
    if section.twin_label.isHidden():
        raise SmokeError("twin_label should not be hidden for twinned axes!")

    harness.grab_inspector("axes-twin-01-primary-inspector")
    before_p = harness.grab_canvas("axes-twin-01-canvas-initial")

    # Switch primary to manual
    harness.click(section.switch_manual_button)
    harness.pump(60)

    # Set manual bounds
    section.left_spin.setValue(0.20)
    section.bottom_spin.setValue(0.25)
    section.width_spin.setValue(0.55)
    section.height_spin.setValue(0.50)
    harness.pump(60)
    canvas.redraw()
    harness.pump(50)

    # Verify both artists have matching bounds
    target_p = canvas.component_registry.get(primary_id).resolve_target()
    target_t = canvas.component_registry.get(twin_id).resolve_target()
    pos_p = tuple(round(v, 4) for v in target_p.get_position().bounds)
    pos_t = tuple(round(v, 4) for v in target_t.get_position().bounds)
    if pos_p != pos_t:
        raise SmokeError(f"Twin positions do not match: primary={pos_p}, twin={pos_t}")

    before_p = _verify_canvas_changed(
        harness, before_p, "axes-twin-02-manual-moved", "Twin axes moved in lockstep to [0.2, 0.25, 0.55, 0.5]"
    )

    # Select secondary axes and verify inspector
    section_twin = _axes_layout_section(harness, twin_id)
    if section_twin.twin_label.isHidden():
        raise SmokeError("twin_label should not be hidden on secondary twin inspector!")
    harness.grab_inspector("axes-twin-03-secondary-inspector")

    # Return to grid via secondary axes
    harness.click(section_twin.return_grid_button)
    harness.pump(60)
    canvas.redraw()
    harness.pump(50)

    if not target_p.get_in_layout() or not target_t.get_in_layout():
        raise SmokeError("Both primary and twin must have get_in_layout() == True after return to grid!")

    _verify_canvas_changed(
        harness, before_p, "axes-twin-04-returned-grid", "Twin axes pair returned to Grid layout"
    )


def _scenario_colorbar_followers(harness: SmokeHarness) -> None:
    """Test Colorbar following manual axes movement and rebuilding on grid return."""
    canvas = harness.create_project("Smoke_Colorbar_Followers")
    axes_ids = create_regular_axes(canvas)
    axes_id = str(axes_ids[0])
    harness.pump(50)

    # Seed data with color mapping
    subtable = harness.window.table.current_subtable()
    sheet = subtable.get_table(0).table_model.sheet
    sheet.set_block(
        0,
        0,
        [
            [0.0, 1.0, 10.0],
            [1.0, 2.0, 20.0],
            [2.0, 4.0, 30.0],
            [3.0, 8.0, 40.0],
            [4.0, 16.0, 50.0],
        ],
    )
    x_ref = ColumnRef(canvas.project_id, sheet.id, sheet.columns[0].id)
    y_ref = ColumnRef(canvas.project_id, sheet.id, sheet.columns[1].id)
    c_ref = ColumnRef(canvas.project_id, sheet.id, sheet.columns[2].id)
    pair = harness.window.repository.valid_pair(x_ref, y_ref)

    canvas.add_scatter(
        pair.x,
        pair.y,
        28.0,
        "#336699",
        "o",
        "temperature_points",
        x_ref,
        y_ref,
        object_id="scatter-smoke",
        color_ref=c_ref,
        color_mapping=deepcopy(MAPPED_COLOR),
    )
    canvas.add_colorbar(
        "scatter-smoke",
        {"label": "Temperature (K)", "location": "right"},
        object_id="colorbar-smoke",
    )
    canvas.redraw()
    harness.pump(60)

    harness.select_component("colorbar-smoke")
    harness.grab_inspector("axes-cb-01-colorbar-inspector")
    before_p = harness.grab_canvas("axes-cb-01-initial-canvas")

    # Select owner Axes and switch to manual
    harness.select_component(axes_id)
    geom_service = canvas.axes_geometry_service
    res = geom_service.switch_to_manual(axes_id)
    if not res.ok:
        raise SmokeError("Failed to switch owner axes to manual with colorbar!")

    # Change manual bounds on owner axes
    new_bounds = [0.15, 0.20, 0.45, 0.50]
    res = geom_service.set_manual_bounds(axes_id, new_bounds)
    if not res.ok:
        raise SmokeError("Failed to update owner axes manual bounds!")
    canvas.redraw()
    harness.pump(50)

    # Verify colorbar follower position updated
    cb_controller = canvas.component_registry.get("colorbar-smoke")
    cax = cb_controller.resolve_target().ax
    cax_pos = cax.get_position()
    if cax_pos.x0 < 0.60 or cax_pos.y0 < 0.19:
        raise SmokeError(f"Colorbar did not follow manual owner axes bounds! cax_pos={cax_pos.bounds}")

    before_p = _verify_canvas_changed(
        harness, before_p, "axes-cb-03-owner-moved", "Colorbar followed resized/translated owner axes"
    )

    # Return owner axes to grid
    res = geom_service.return_to_grid(axes_id)
    if not res.ok:
        raise SmokeError("Failed to return owner axes to grid!")
    canvas.redraw()
    harness.pump(50)

    _verify_canvas_changed(
        harness, before_p, "axes-cb-04-returned-to-grid", "Owner axes and colorbar cleanly returned to grid"
    )


def _scenario_mixed_layout_engines(harness: SmokeHarness) -> None:
    """Test 2x2 multi-axes layout with mixed manual/grid axes & layout engine neutrality."""
    canvas = harness.create_project("Smoke_Mixed_Layout_Engines")
    axes_ids = create_regular_axes(canvas, nrows=2, ncols=2)
    harness.pump(60)

    # Add lines and titles to each axes so layout engines have margin work
    for idx, ax_id in enumerate(axes_ids):
        canvas.select_component(ax_id)
        canvas.add_curve(f"(x + {idx}) ** 1.2", 0, 5, "-", "#2c3e50", f"Line {idx}")
        ctrl = canvas.component_registry.get(ax_id)
        ctrl.set_property("title", f"Subplot Grid {idx + 1}")
    canvas.redraw()
    harness.pump(60)

    before_p = harness.grab_canvas("axes-engines-01-2x2-initial")

    # Switch Axes (0,0) to manual position and place in custom floating bounds
    manual_id = str(axes_ids[0])
    geom_service = canvas.axes_geometry_service
    geom_service.switch_to_manual(manual_id)
    geom_service.set_manual_bounds(manual_id, [0.08, 0.55, 0.35, 0.35])
    canvas.redraw()
    harness.pump(60)

    before_p = _verify_canvas_changed(
        harness, before_p, "axes-engines-02-mixed-manual", "Axes (0,0) set to floating manual position"
    )

    # Set Figure Layout Engine to constrained
    fig_ctrl = canvas.component_registry.get(canvas.root_component_id)
    fig_ctrl.set_property(
        "layout_engine",
        {
            "kind": "constrained",
            "params": {
                "w_pad": None,
                "h_pad": None,
                "wspace": None,
                "hspace": None,
                "rect": None,
            },
        },
    )
    canvas.redraw()
    harness.pump(60)

    # Verify manual axes stayed strictly pinned
    target_manual = canvas.component_registry.get(manual_id).resolve_target()
    pos = target_manual.get_position()
    if abs(pos.x0 - 0.08) > 0.001 or abs(pos.y0 - 0.55) > 0.001:
        raise SmokeError(f"Manual axes shifted under constrained layout engine! Got {pos.bounds}")

    _verify_canvas_changed(
        harness, before_p, "axes-engines-03-constrained", "Constrained layout applied without shifting manual axes"
    )


def _scenario_schema_v22_persistence_roundtrip(harness: SmokeHarness) -> None:
    """Test schema-v22 project save and visual pixel-accurate restore."""
    canvas, axes_id, ax = _setup_test_project(harness, "Smoke_Schema_v22_Persistence")

    # Set manual geometry on axes
    geom_service = canvas.axes_geometry_service
    geom_service.switch_to_manual(axes_id)
    target_bounds = [0.16, 0.22, 0.62, 0.52]
    geom_service.set_manual_bounds(axes_id, target_bounds)

    # Style axes elements
    axes_ctrl = canvas.component_registry.get(axes_id)
    axes_ctrl.set_property("facecolor", "#FAF9F6")
    canvas.redraw()
    harness.pump(60)

    harness.grab_canvas("axes-v22-01-pre-save")

    # Save project snapshot to temporary file
    with tempfile.TemporaryDirectory(prefix="mygui-smoke-v22-") as tmpdir:
        save_path = Path(tmpdir) / "project.mygui"
        save_project_snapshot(
            save_path,
            figure_window=harness.window.figure_window,
            canvas=canvas,
        )

        # Validate file
        loaded = load_project_file(save_path)
        if loaded.get("schema_version") != PROJECT_SCHEMA_VERSION:
            raise SmokeError(f"Saved file schema_version is {loaded.get('schema_version')}, expected {PROJECT_SCHEMA_VERSION}")

        # Check geometry record in JSON
        axes_record = next(
            c for c in loaded["figure"]["components"] if c.get("kind") == "axes"
        )
        if axes_record.get("data", {}).get("geometry", {}).get("mode") != "manual":
            raise SmokeError(f"JSON axes record geometry mode is not manual: {axes_record.get('data')}")

        # Remove original project from windows to avoid duplicate ID collision on restore
        proj_id = canvas.project_id
        harness.window.figure_window.remove_project_by_id(proj_id)
        harness.window.table.remove_project_table(proj_id)
        harness.pump(50)

        # Restore snapshot into the active MainWindow
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
        harness.pump(60)

        # Verify restored geometry on controller and artist
        restored_ctrl = restored_canvas.component_registry.query(kind=ComponentKind.AXES)[0]
        if restored_ctrl.state.data.get("geometry", {}).get("mode") != "manual":
            raise SmokeError("Restored controller geometry mode is not manual!")
        restored_target = restored_ctrl.resolve_target()
        if restored_target.get_in_layout():
            raise SmokeError("Restored target get_in_layout() should be False!")

        post_restore_p = harness.grab_canvas("axes-v22-02-post-restore")

        # Verify that restored canvas screenshot exists and is valid
        img_post = Image.open(post_restore_p).convert("RGB")
        if img_post.size[0] < 10 or img_post.size[1] < 10:
            raise SmokeError("Restored canvas produced invalid empty image!")


def _scenario_shared_tickers_v22_roundtrip(harness: SmokeHarness) -> None:
    """Verify sharex/sharey ticker synchronization and schema-v22 restore."""

    canvas = harness.create_project("Smoke_Shared_Tickers_v22")
    axes_ids = canvas.create_axes_layout(
        AxesLayoutSpec.grid(
            2,
            1,
            share_x=ShareMode.ALL,
            share_y=ShareMode.ALL,
            cell_view=canvas.axes_layout_service.creation_view_defaults(),
        )
    )
    if len(axes_ids) != 2:
        raise SmokeError("Shared ticker smoke did not create two Axes.")

    # IndexLocator intentionally relies on a finite data interval. Populate
    # both shared Axes through the production chart path before selecting it.
    subtable = harness.window.table.current_subtable()
    sheet = subtable.get_table(0).table_model.sheet
    sheet.set_block(0, 0, [[0.0, 0.0], [1.0, 1.0], [2.0, 2.0]])
    x_ref = ColumnRef(canvas.project_id, sheet.id, sheet.columns[0].id)
    y_ref = ColumnRef(canvas.project_id, sheet.id, sheet.columns[1].id)
    for axes_id in axes_ids:
        if not canvas.select_component(axes_id):
            raise SmokeError("Could not select a shared Axes for index data.")
        result = canvas.add_plots(
            x_ref,
            (y_ref,),
            style="-",
            size=4.0,
            linewidth=1.0,
            preprocess=None,
            color_selection=ColorSelection(color="#1f77b4"),
            record_recent=False,
        )
        if len(result.component_ids) != 1:
            raise SmokeError("Could not create index data on a shared Axes.")

    axis_controllers = canvas.component_registry.query(kind=ComponentKind.AXIS)
    x_by_parent = {
        controller.state.parent_id: controller
        for controller in axis_controllers
        if controller.state.selector == {"axis": "x"}
    }
    y_by_parent = {
        controller.state.parent_id: controller
        for controller in axis_controllers
        if controller.state.selector == {"axis": "y"}
    }
    first_x, second_x = (x_by_parent[axes_id] for axes_id in axes_ids)
    first_y, second_y = (y_by_parent[axes_id] for axes_id in axes_ids)
    service = canvas.axis_tick_settings_service

    fixed_locator = {
        "kind": "fixed",
        "params": {"locations": [0.0, 1.0, 2.0], "nbins": None},
    }
    fixed_formatter = {
        "kind": "fixed",
        "params": {"labels": ["A", "B", "C"]},
    }
    x_opening = service.snapshot(first_x.component_id)
    if x_opening.shared_axis_count != 2:
        raise SmokeError("sharex group was not exposed by the unified service.")
    x_candidate = replace(
        x_opening,
        major=replace(
            x_opening.major,
            locator=fixed_locator,
            formatter=fixed_formatter,
            tick_properties={**x_opening.major.tick_properties, "length": 9.0},
        ),
    )
    x_result = service.apply(x_candidate)
    if not x_result.committed:
        raise SmokeError(f"Shared X ticker commit failed: {x_result.message}")
    for controller in (first_x, second_x):
        if controller.state.properties["major_locator"] != fixed_locator:
            raise SmokeError("Fixed Locator did not synchronize across sharex.")
        if controller.state.properties["major_formatter"] != fixed_formatter:
            raise SmokeError("Fixed Formatter did not synchronize across sharex.")

    major_x_ticks = [
        controller
        for controller in canvas.component_registry.query(
            kind=ComponentKind.TICK_GROUP,
            role=ComponentRole.MAJOR_TICK,
        )
        if controller.state.selector.get("axis") == "x"
    ]
    selected_tick = next(
        controller
        for controller in major_x_ticks
        if controller.state.parent_id == first_x.component_id
    )
    peer_tick = next(
        controller
        for controller in major_x_ticks
        if controller.state.parent_id == second_x.component_id
    )
    if selected_tick.state.properties["length"] != 9.0:
        raise SmokeError("Selected Axes tick appearance was not applied.")
    if peer_tick.state.properties["length"] == 9.0:
        raise SmokeError("Tick appearance leaked to the shared peer Axes.")

    index_locator = {
        "kind": "index",
        "params": {"base": 1.0, "offset": 0.0},
    }
    format_str = {"kind": "format_str", "params": {"format": "%.1f"}}
    y_opening = service.snapshot(first_y.component_id)
    if y_opening.shared_axis_count != 2:
        raise SmokeError("sharey group was not exposed by the unified service.")
    y_result = service.apply(
        replace(
            y_opening,
            major=replace(
                y_opening.major,
                locator=index_locator,
                formatter=format_str,
            ),
        )
    )
    if not y_result.committed:
        raise SmokeError(f"Shared Y ticker commit failed: {y_result.message}")
    for controller in (first_y, second_y):
        if controller.state.properties["major_locator"] != index_locator:
            raise SmokeError("Index Locator did not synchronize across sharey.")
        if controller.state.properties["major_formatter"] != format_str:
            raise SmokeError("FormatStr Formatter did not synchronize across sharey.")

    canvas.redraw()
    harness.pump(60)
    harness.grab_canvas("axes-shared-tickers-v22-01-before-save")
    with tempfile.TemporaryDirectory(prefix="mygui-smoke-shared-tickers-") as tmpdir:
        save_path = Path(tmpdir) / "shared-tickers.mygui"
        save_project_snapshot(
            save_path,
            figure_window=harness.window.figure_window,
            canvas=canvas,
        )
        loaded = load_project_file(save_path)
        if loaded.get("schema_version") != PROJECT_SCHEMA_VERSION:
            raise SmokeError("Shared ticker project was not saved as schema v22.")

        project_id = canvas.project_id
        harness.window.figure_window.remove_project_by_id(project_id)
        harness.window.table.remove_project_table(project_id)
        restore_project_snapshot(
            save_path,
            table=harness.window.table,
            figure_window=harness.window.figure_window,
        )
        harness.pump(80)

    restored = harness.window.figure_window.current_canva
    restored_axes = restored.component_registry.query(kind=ComponentKind.AXES)
    if len(restored_axes) != 2:
        raise SmokeError("Shared ticker restore did not recreate two Axes.")
    restored_x = restored.component_registry.query(role=ComponentRole.X_AXIS)
    restored_y = restored.component_registry.query(role=ComponentRole.Y_AXIS)
    if any(c.state.properties["major_locator"] != fixed_locator for c in restored_x):
        raise SmokeError("Restored sharex Fixed Locators diverged.")
    if any(c.state.properties["major_formatter"] != fixed_formatter for c in restored_x):
        raise SmokeError("Restored sharex Fixed Formatters diverged.")
    if any(c.state.properties["major_locator"] != index_locator for c in restored_y):
        raise SmokeError("Restored sharey Index Locators diverged.")
    if any(c.state.properties["major_formatter"] != format_str for c in restored_y):
        raise SmokeError("Restored sharey FormatStr Formatters diverged.")
    first_axes, second_axes = (
        controller.resolve_target() for controller in restored_axes
    )
    if not first_axes.get_shared_x_axes().joined(first_axes, second_axes):
        raise SmokeError("Restored Axes lost sharex membership.")
    if not first_axes.get_shared_y_axes().joined(first_axes, second_axes):
        raise SmokeError("Restored Axes lost sharey membership.")
    restored.redraw()
    harness.pump(60)
    harness.grab_canvas("axes-shared-tickers-v22-02-restored")


def _scenario_undo_redo_validation(harness: SmokeHarness) -> None:
    """Test complete Undo and Redo transaction cycle across geometry modifications."""
    canvas, axes_id, ax = _setup_test_project(harness, "Smoke_Axes_UndoRedo")
    initial_p = harness.grab_canvas("axes-undoredo-00-initial")

    undo_stack = harness.window.repository.undo_stack(canvas.project_id)
    geom_service = canvas.axes_geometry_service

    # Step 1: Switch to Manual
    res1 = canvas.editor_context.perform(
        "Switch to Manual", lambda: geom_service.switch_to_manual(axes_id)
    )
    if not res1.ok:
        raise SmokeError("Failed to perform switch_to_manual under undo context")
    canvas.redraw()
    harness.pump(40)
    manual_p = _verify_canvas_changed(
        harness, initial_p, "axes-undoredo-01-manual", "Switched to manual"
    )

    # Step 2: Change Bounds
    res2 = canvas.editor_context.perform(
        "Set Bounds",
        lambda: geom_service.set_manual_bounds(axes_id, [0.20, 0.25, 0.50, 0.45]),
        merge_key=("axes_geometry", axes_id),
    )
    if not res2.ok:
        raise SmokeError("Failed to perform set_manual_bounds under undo context")
    canvas.redraw()
    harness.pump(40)
    bounds_p = _verify_canvas_changed(
        harness, manual_p, "axes-undoredo-02-bounds-changed", "Bounds changed"
    )

    # Step 3: Reset Position
    res3 = canvas.editor_context.perform(
        "Reset Position", lambda: geom_service.reset_to_grid_bounds(axes_id)
    )
    if not res3.ok:
        raise SmokeError("Failed to perform reset_to_grid_bounds under undo context")
    canvas.redraw()
    harness.pump(40)
    reset_p = _verify_canvas_changed(
        harness, bounds_p, "axes-undoredo-03-reset-position", "Position reset"
    )

    # Step 4: Return to Grid
    res4 = canvas.editor_context.perform(
        "Return to Grid", lambda: geom_service.return_to_grid(axes_id)
    )
    if not res4.ok:
        raise SmokeError("Failed to perform return_to_grid under undo context")
    canvas.redraw()
    harness.pump(40)
    grid_p = _verify_canvas_changed(
        harness, reset_p, "axes-undoredo-04-returned-grid", "Returned to grid"
    )

    # --- Step-by-Step UNDO ---
    # Undo 4 (Return to Grid -> Reset)
    undo_stack.undo()
    harness.pump(60)
    canvas.redraw()
    harness.pump(40)
    _verify_canvas_changed(harness, grid_p, "axes-undoredo-05-undo-return-grid", "Undo return to grid")

    # Undo 3 (Reset -> Bounds changed)
    undo_stack.undo()
    harness.pump(60)
    canvas.redraw()
    harness.pump(40)
    _verify_canvas_changed(harness, reset_p, "axes-undoredo-06-undo-reset", "Undo reset position")

    # Undo 2 (Bounds changed -> Manual initial)
    undo_stack.undo()
    harness.pump(60)
    canvas.redraw()
    harness.pump(40)
    _verify_canvas_changed(harness, bounds_p, "axes-undoredo-07-undo-bounds", "Undo bounds change")

    # Undo 1 (Manual initial -> Grid initial)
    undo_stack.undo()
    harness.pump(60)
    canvas.redraw()
    harness.pump(40)
    _verify_canvas_changed(harness, manual_p, "axes-undoredo-08-undo-manual", "Undo switch to manual")

    # --- Step-by-Step REDO ---
    for i in range(4):
        if not undo_stack.canRedo():
            raise SmokeError(f"Undo stack cannot redo at step {i+1}!")
        undo_stack.redo()
        harness.pump(60)
        canvas.redraw()
        harness.pump(40)

    _verify_canvas_changed(
        harness, initial_p, "axes-undoredo-09-full-redo", "Full redo restored final state"
    )
