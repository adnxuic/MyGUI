"""Comprehensive Axes & Axes-Structure desktop smoke test.

Group id: axes_smoke.
Covers:
- Axes root (limits, margin, facecolor, box_aspect, visibility)
- Axes Structure (Left/Right/Top/Bottom Spines, Title, Legend)
- X Axis (locators, formatters, major/minor ticks, tick labels, major/minor grids, x-label)
- Y Axis (locators, formatters, major/minor ticks, tick labels, major/minor grids, y-label)
- Undo/Redo & Canvas change verification
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from PIL import Image, ImageChops

from mygui.database import ColumnRef
from mygui.figuremodify.axes_layout import AxesLayoutSpec
from mygui.figuremodify.components import ComponentKind, ComponentRole
from mygui.figuremodify.style_base.color_models import ColorSelection

from desktop_smoke.harness import SmokeError, SmokeHarness


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


def _scenario_undo_redo_validation(harness: SmokeHarness) -> None:
    """Test Undo and Redo on Axes modifications."""
    canvas, axes_id, ax = _setup_test_project(harness, "Smoke_Axes_UndoRedo")
    initial_p = harness.grab_canvas("axes-undoredo-00-initial")

    axes_ctrl = canvas.component_registry.get(axes_id)
    # Apply facecolor change
    axes_ctrl.set_property("facecolor", "#E6F2FF")
    harness.pump(60)
    canvas.redraw()
    harness.pump(50)

    changed_p = _verify_canvas_changed(
        harness, initial_p, "axes-undoredo-01-changed", "Axes facecolor changed to #E6F2FF"
    )

    # Undo
    undo_stack = harness.window.repository.undo_stack(canvas.project_id)
    if undo_stack is None or not undo_stack.canUndo():
        raise SmokeError("Undo stack cannot undo after facecolor change!")
    undo_stack.undo()
    harness.pump(80)
    canvas.redraw()
    harness.pump(50)

    _verify_canvas_changed(
        harness, changed_p, "axes-undoredo-02-undone", "Undo reverted facecolor"
    )

    # Redo
    if not undo_stack.canRedo():
        raise SmokeError("Undo stack cannot redo!")
    undo_stack.redo()
    harness.pump(80)
    canvas.redraw()
    harness.pump(50)

    _verify_canvas_changed(
        harness, initial_p, "axes-undoredo-03-redone", "Redo re-applied facecolor"
    )
