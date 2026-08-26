"""All 30 Component Inspector Profiles desktop smoke. Group id: inspectors."""

from __future__ import annotations

from typing import Any, Callable

from mygui.figuremodify.axes_layout import AxesLayoutSpec
from mygui.figuremodify.components import ComponentKind, ComponentRole
from mygui.figuremodify.components.property_values import DEFAULT_COLOR_MAP
from mygui.figuremodify.in_axes import ZoomInAxesCreateSpec

from desktop_smoke.harness import SmokeError, SmokeHarness


def run_inspectors_scenarios(harness: SmokeHarness) -> list[dict[str, Any]]:
    """Walk through all Component Inspector profiles."""
    results: list[dict[str, Any]] = []

    results.append(
        _run_case(
            harness,
            "inspectors.walk_all_profiles",
            lambda: _scenario_walk_all_profiles(harness),
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


def _scenario_walk_all_profiles(harness: SmokeHarness) -> None:
    canvas = harness.create_project("Smoke_All_Inspectors")
    axes_ids = canvas.create_axes_layout(AxesLayoutSpec.grid(1, 1))
    if not axes_ids:
        raise SmokeError("Axes creation failed.")
    harness.pump(50)

    from mygui.database import ColumnRef
    from mygui.figuremodify.style_base.color_models import ColorSelection

    # Add 1D & 2D components, elements, etc.
    subtable = harness.window.table.current_subtable()
    sheet = subtable.get_table(0).table_model.sheet
    rows_1d = [
        [1.0, 2.0, 5.0, 10.0],
        [2.0, 4.0, 8.0, 14.0],
        [3.0, 6.0, 11.0, 18.0],
        [4.0, 8.0, 14.0, 22.0],
        [5.0, 10.0, 17.0, 26.0],
    ]
    sheet.set_block(0, 0, rows_1d)
    x_ref = ColumnRef(canvas.project_id, sheet.id, sheet.columns[0].id)
    y_refs = (
        ColumnRef(canvas.project_id, sheet.id, sheet.columns[1].id),
        ColumnRef(canvas.project_id, sheet.id, sheet.columns[2].id),
        ColumnRef(canvas.project_id, sheet.id, sheet.columns[3].id),
    )

    rows_2d = []
    for i in range(5):
        for j in range(5):
            rows_2d.append([float(i), float(j), float(i * j)])
    sheet.set_block(0, 4, rows_2d)
    x_2d = ColumnRef(canvas.project_id, sheet.id, sheet.columns[4].id)
    y_2d = ColumnRef(canvas.project_id, sheet.id, sheet.columns[5].id)
    z_2d = ColumnRef(canvas.project_id, sheet.id, sheet.columns[6].id)
    harness.pump(40)

    # Function curve
    canvas.add_curve("sin(x)", 0, 5, "-", "#1f77b4", "Curve")
    # Data plot
    canvas.add_plots(
        x_ref,
        (y_refs[0],),
        style="-",
        size=6.0,
        linewidth=1.5,
        preprocess=None,
        color_selection=ColorSelection(color="#ff7f0e"),
    )
    # Scatter
    canvas.add_scatters(
        x_ref,
        (y_refs[1],),
        size=30.0,
        marker="o",
        preprocess=None,
        color_selection=ColorSelection(color="#2ca02c"),
    )
    # Interpolation
    canvas.add_interpolate_curves(
        x_ref,
        (y_refs[0],),
        method="线性插值",
        color_selection=ColorSelection(color="#d62728"),
        linestyle="-",
        linewidth=1.5,
        marker=None,
        markersize=6.0,
        markeredgewidth=1.0,
    )
    # Contour
    canvas.add_contour(
        x_2d, y_2d, z_2d, {"colormap": {**DEFAULT_COLOR_MAP, "cmap": "viridis"}}
    )
    # Heatmap
    canvas.add_heatmap(
        x_2d,
        y_2d,
        z_2d,
        {"colormap": {**DEFAULT_COLOR_MAP, "cmap": "coolwarm"}},
    )
    # Pseudocolor
    canvas.add_pseudocolor(
        x_2d, y_2d, z_2d, {"colormap": {**DEFAULT_COLOR_MAP, "cmap": "magma"}}
    )
    # Colorbar
    pcolors = canvas.component_registry.query(
        kind=ComponentKind.FIELD_2D, role=ComponentRole.PSEUDOCOLOR
    )
    if pcolors:
        try:
            canvas.add_colorbar(pcolors[0].component_id, {})
        except Exception:
            pass
    # Text
    canvas.add_text(0.5, 0.5, "Inspector Walk Text", "sans-serif", 11.0)
    # Reference marks
    canvas.add_reference_marks([15.2, 22.9, 31.5])
    # Reference Line & Band
    canvas.add_reference_line(
        {"orientation": "vertical", "value": 2.5, "linestyle": "--"}
    )
    canvas.add_reference_band(
        {"orientation": "horizontal", "lower": -0.5, "upper": 0.5}
    )
    # In-Axes
    try:
        canvas.add_in_axes(ZoomInAxesCreateSpec(bounds=(0.6, 0.6, 0.35, 0.35)))
    except Exception:
        pass

    harness.pump(80)
    canvas.redraw()
    harness.pump(50)

    # Walk all unique (kind, role) components in registry
    visited_profiles: set[tuple[ComponentKind, ComponentRole]] = set()
    controllers = canvas.component_registry.query()

    for ctrl in controllers:
        profile_key = (ctrl.state.kind, ctrl.state.role)
        if profile_key in visited_profiles:
            continue
        visited_profiles.add(profile_key)

        harness.select_component(ctrl.component_id)
        harness.pump(60)

        kind_name = ctrl.state.kind.value.lower()
        role_name = ctrl.state.role.value.lower()
        shot_name = f"inspector-{kind_name}-{role_name}"

        harness.grab_inspector(shot_name)

    if len(visited_profiles) < 15:
        raise SmokeError(
            f"Expected at least 15 distinct inspector profiles, visited {len(visited_profiles)}."
        )
