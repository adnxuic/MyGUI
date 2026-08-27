"""All 30 Component Inspector Profiles desktop smoke. Group id: inspectors."""

from __future__ import annotations

from typing import Any, Callable

from mygui.database import ColumnRef, scipy_fit_adapter
from mygui.figuremodify.axes_layout import AxesLayoutSpec
from mygui.figuremodify.components import ComponentKind, ComponentRole, ROLES_BY_KIND
from mygui.figuremodify.components.property_values import DEFAULT_COLOR_MAP
from mygui.figuremodify.style_base.color_models import ColorSelection

from desktop_smoke.harness import SmokeError, SmokeHarness

EXPECTED_PROFILES = frozenset(
    (kind, role) for kind, roles in ROLES_BY_KIND.items() for role in roles
)


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
    axes_id = str(axes_ids[0])
    harness.pump(50)

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

    canvas.add_component_line([0.0, 1.0, 2.0], [0.0, 1.0, 4.0], "-", "#111111", "line")
    canvas.add_curve("sin(x)", 0, 5, "-", "#1f77b4", "Curve")
    canvas.add_plots(
        x_ref,
        (y_refs[0],),
        style="-",
        size=6.0,
        linewidth=1.5,
        preprocess=None,
        color_selection=ColorSelection(color="#ff7f0e"),
    )
    canvas.add_scatters(
        x_ref,
        (y_refs[1],),
        size=30.0,
        marker="o",
        preprocess=None,
        color_selection=ColorSelection(color="#2ca02c"),
    )
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
    pair = harness.window.repository.line_pair(x_ref, y_refs[0])
    options = scipy_fit_adapter.default_fit_options("poly1")
    fit_result = scipy_fit_adapter.fit_curve(
        pair.x[pair.valid_mask],
        pair.y[pair.valid_mask],
        "poly1",
        options,
    )
    canvas.add_fit_curve(
        pair.x[pair.valid_mask],
        pair.y[pair.valid_mask],
        "#9467bd",
        "Fit",
        x_ref,
        y_refs[0],
        engine="Python",
        fit_type="poly1",
        fit_options=options,
        fit_result=fit_result,
        expression=fit_result["value_expression"],
        x_start=1.0,
        x_stop=5.0,
    )
    canvas.add_contour(
        x_2d, y_2d, z_2d, {"colormap": {**DEFAULT_COLOR_MAP, "cmap": "viridis"}}
    )
    canvas.add_heatmap(
        x_2d,
        y_2d,
        z_2d,
        {"colormap": {**DEFAULT_COLOR_MAP, "cmap": "coolwarm"}},
    )
    canvas.add_pseudocolor(
        x_2d, y_2d, z_2d, {"colormap": {**DEFAULT_COLOR_MAP, "cmap": "magma"}}
    )
    pcolors = canvas.component_registry.query(
        kind=ComponentKind.FIELD_2D, role=ComponentRole.PSEUDOCOLOR
    )
    if not pcolors:
        raise SmokeError("Pseudocolor was not created for the Inspector walk.")
    canvas.add_colorbar(pcolors[0].component_id, {})
    canvas.add_text(0.5, 0.5, "Inspector Walk Text", "sans-serif", 11.0)
    canvas.add_reference_marks([15.2, 22.9, 31.5])
    canvas.add_reference_line(
        {"orientation": "vertical", "value": 2.5, "linestyle": "--"}
    )
    canvas.add_reference_band(
        {"orientation": "horizontal", "lower": -0.5, "upper": 0.5}
    )
    canvas.add_in_axes(harness.zoom_in_axes_spec(canvas))
    canvas.add_in_axes(harness.image_in_axes_spec(canvas))
    canvas.axes_commands.ensure_legend(axes_id)

    harness.pump(80)
    canvas.redraw()
    harness.pump(50)
    harness.grab_canvas("inspector-all-components-canvas")

    visited_profiles: set[tuple[ComponentKind, ComponentRole]] = set()
    for ctrl in canvas.component_registry.query():
        profile_key = (ctrl.state.kind, ctrl.state.role)
        if profile_key in visited_profiles:
            continue
        visited_profiles.add(profile_key)
        harness.select_component(ctrl.component_id)
        harness.pump(60)
        kind_name = ctrl.state.kind.value.lower()
        role_name = ctrl.state.role.value.lower()
        harness.grab_inspector(f"inspector-{kind_name}-{role_name}")

    missing = EXPECTED_PROFILES - visited_profiles
    if missing:
        labels = ", ".join(
            f"{kind.value}:{role.value}"
            for kind, role in sorted(missing, key=lambda item: (item[0].value, item[1].value))
        )
        raise SmokeError(
            f"Inspector walk missed {len(missing)} profile(s): {labels}."
        )
    extra = visited_profiles - EXPECTED_PROFILES
    if extra:
        labels = ", ".join(
            f"{kind.value}:{role.value}"
            for kind, role in sorted(extra, key=lambda item: (item[0].value, item[1].value))
        )
        raise SmokeError(f"Inspector walk saw unexpected profile(s): {labels}.")
