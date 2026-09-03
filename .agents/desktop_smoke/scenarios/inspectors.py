"""All 34 Component Inspector Profiles desktop smoke. Group id: inspectors."""

from __future__ import annotations

from typing import Any, Callable
import json

from mygui.database import ColumnRef, scipy_fit_adapter
from mygui.figuremodify.axes_layout import AxesLayoutSpec
from mygui.figuremodify.component_services import SecondaryAxisCreateSpec
from mygui.figuremodify.components import ComponentKind, ComponentRole, ROLES_BY_KIND
from mygui.figuremodify.components.property_values import DEFAULT_COLOR_MAP
from mygui.figuremodify.style_base.color_models import ColorSelection

from desktop_smoke.frame_probe import measure_frame, p95_ms, staged_timing_payload, wait_settle
from desktop_smoke.gates import (
    SAMPLE_FRAMES,
    SWITCH_LEAK_ITERS,
    WARMUP_FRAMES,
    assert_switch_gates,
    require_census_stable,
    theme_census,
)
from desktop_smoke.harness import SmokeError, SmokeHarness
from desktop_smoke.inspector_geometry import (
    assert_inspector_geometry,
    collect_inspector_rects,
)

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


def _dump_inspector_rects(harness: SmokeHarness, name: str) -> None:
    host = harness.window.fig_control_window.figure_inspector_host
    payload = collect_inspector_rects(host)
    directory = harness.output_dir / "rects"
    directory.mkdir(parents=True, exist_ok=True)
    (directory / f"{name}.json").write_text(
        json.dumps(payload, indent=2),
        encoding="utf-8",
    )
    assert_inspector_geometry(host, name)


def _expand_inspector_groups(harness: SmokeHarness, shot_prefix: str) -> None:
    from mygui.widgets.fig_control_window.component_editors.inspector import (
        InspectorSectionGroup,
    )

    host = harness.window.fig_control_window.figure_inspector_host
    groups = [
        group
        for group in host.findChildren(InspectorSectionGroup)
        if group.isVisible() and group.isCheckable()
    ]
    originally_collapsed = [group for group in groups if not group.isChecked()]
    for index, group in enumerate(groups):
        if not group.isChecked():
            group.setChecked(True)
            harness.pump(20)
        harness.grab_inspector(f"{shot_prefix}-group-{index}")
        _dump_inspector_rects(harness, f"{shot_prefix}-group-{index}")
    if groups:
        harness.grab_inspector(f"{shot_prefix}-expanded")
        _dump_inspector_rects(harness, f"{shot_prefix}-expanded")
    for group in originally_collapsed:
        group.setChecked(False)
    if originally_collapsed:
        harness.pump(20)


def _capture_targeted_shots(harness: SmokeHarness, ctrl, kind_name: str, role_name: str) -> None:
    from mygui.widgets.fig_control_window.component_editors.inspector import (
        InspectorSectionGroup,
    )

    if kind_name == "line" and role_name == "function_curve":
        harness.grab_inspector("inspector-function-curve-expression-range")
        _dump_inspector_rects(harness, "inspector-function-curve-expression-range")
    if kind_name == "tick_label_group" and role_name == "major_tick_label":
        host = harness.window.fig_control_window.figure_inspector_host
        advanced = [
            group
            for group in host.findChildren(InspectorSectionGroup)
            if group.isVisible()
            and group.isCheckable()
            and "advanced" in group.full_title().lower()
        ]
        for group in advanced:
            group.setChecked(True)
        harness.pump(30)
        harness.grab_inspector("inspector-tick-label-advanced")
        _dump_inspector_rects(harness, "inspector-tick-label-advanced")
        for group in advanced:
            group.setChecked(False)


def _capture_fold_band_shots(harness: SmokeHarness) -> None:
    host = harness.window.fig_control_window.figure_inspector_host
    scroll = harness.window.fig_control_window.figure_inspector_scroll_area
    vertical = scroll.verticalScrollBar()
    harness.grab_inspector("inspector-fold-top")
    _dump_inspector_rects(harness, "inspector-fold-top")
    if vertical.maximum() > 0:
        vertical.setValue(vertical.maximum() // 2)
        harness.pump(20)
        harness.grab_inspector("inspector-fold-middle")
        _dump_inspector_rects(harness, "inspector-fold-middle")
        vertical.setValue(vertical.maximum())
        harness.pump(20)
        harness.grab_inspector("inspector-fold-bottom")
        _dump_inspector_rects(harness, "inspector-fold-bottom")
        vertical.setValue(0)
        harness.pump(20)
    del host


def _walk_appearance_matrix(harness: SmokeHarness, canvas) -> None:
    from mygui.application_theme import AppearancePreferences, Density, ThemeMode

    theme = harness.window._resolve_theme_service()
    if theme is None:
        raise SmokeError("ThemeService is required for Inspector chrome matrix.")
    origin = theme.snapshot().preferences
    curve = next(
        (
            ctrl
            for ctrl in canvas.component_registry.query()
            if ctrl.state.kind.value.lower() == "line"
            and ctrl.state.role.value.lower() == "function_curve"
        ),
        None,
    )
    if curve is None:
        raise SmokeError("Function Curve is required for Inspector chrome matrix.")
    try:
        for mode in (ThemeMode.LIGHT, ThemeMode.DARK):
            for density in (Density.COMPACT, Density.STANDARD, Density.COMFORTABLE):
                for font_pt in (8, 9, 16):
                    theme.apply_committed(
                        AppearancePreferences(
                            mode=mode,
                            density=density,
                            font_pt=font_pt,
                        )
                    )
                    harness.pump(40)
                    harness.select_component(curve.component_id)
                    name = (
                        f"inspector-chrome-{mode.value}-{density.value}-{font_pt}pt"
                    )
                    harness.grab_inspector(name)
                    _dump_inspector_rects(harness, name)
    finally:
        theme.apply_committed(origin)
        harness.pump(40)


def _scenario_walk_all_profiles(harness: SmokeHarness) -> None:
    harness.grab_inspector("inspector-empty-state")
    _dump_inspector_rects(harness, "inspector-empty-state")
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
    canvas.add_errorbar(
        x_ref,
        y_refs[0],
        "Error Bar",
        xerr=None,
        yerr={
            "kind": "constant",
            "minus": 0.2,
            "plus": 0.4,
        },
        preprocess=None,
        color_selection=ColorSelection(color="#8c564b"),
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
    canvas.add_annotation(
        {
            "text": "Inspector Walk Annotation",
            "xy": [2.5, 2.5],
            "xycoords": "data",
            "xytext": [30.0, 30.0],
            "textcoords": "offset_points",
            "arrow_enabled": True,
        }
    )
    canvas.add_reference_marks([15.2, 22.9, 31.5])
    canvas.add_reference_line(
        {"orientation": "vertical", "value": 2.5, "linestyle": "--"}
    )
    canvas.add_reference_band(
        {"orientation": "horizontal", "lower": -0.5, "upper": 0.5}
    )
    canvas.add_in_axes(harness.zoom_in_axes_spec(canvas))
    canvas.add_in_axes(harness.image_in_axes_spec(canvas))
    canvas.add_secondary_axis(
        SecondaryAxisCreateSpec(
            "x",
            unit_transform={"kind": "affine", "scale": 2.0, "offset": 1.0},
            properties={"label": "Inspector Secondary X"},
        ),
        object_id="inspector-secondary-x",
        announce=False,
    )
    canvas.add_secondary_axis(
        SecondaryAxisCreateSpec(
            "y",
            unit_transform={"kind": "affine", "scale": 0.5, "offset": -1.0},
            properties={"label": "Inspector Secondary Y"},
        ),
        object_id="inspector-secondary-y",
        announce=False,
    )
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
        _dump_inspector_rects(harness, f"inspector-{kind_name}-{role_name}")
        _capture_targeted_shots(harness, ctrl, kind_name, role_name)
        _expand_inspector_groups(harness, f"inspector-{kind_name}-{role_name}")
        from PySide6.QtWidgets import QPushButton, QWidget

        host = harness.window.fig_control_window.figure_inspector_host
        disabled = [
            child
            for child in host.findChildren(QWidget)
            if child.isVisible() and not child.isEnabled()
        ]
        if disabled:
            harness.grab_inspector(f"inspector-{kind_name}-{role_name}-disabled")
        if "fit" in role_name:
            from mygui.widgets.ui_components import set_busy_state

            inspector = harness.window.fig_control_window.figure_inspector_host
            scipy_buttons = [
                child
                for child in inspector.findChildren(QPushButton)
                if child.text() == "SciPy" and child.isVisible()
            ]
            if scipy_buttons:
                set_busy_state(scipy_buttons[0], True, busy_text="Fitting…")
                harness.pump(30)
                harness.grab_inspector("feedback-fit-busy")
                set_busy_state(scipy_buttons[0], False)

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

    _capture_fold_band_shots(harness)
    _walk_appearance_matrix(harness, canvas)

    harness.require_no_negative_sizes("inspectors.walk_all_profiles")

    cached_ids = [
        ctrl.component_id for ctrl in canvas.component_registry.query()
    ][:8]
    host = harness.window.fig_control_window.figure_inspector_host
    from unittest.mock import patch

    from mygui.figuremodify.components.models import ComponentState

    clone_calls = {"count": 0}
    origin_clone = ComponentState.clone

    def _clone(self, **changes):
        clone_calls["count"] += 1
        return origin_clone(self, **changes)

    redraws = {"count": 0}
    polish = {"count": 0}

    def _polish(*_args, **_kwargs):
        polish["count"] += 1

    samples = []
    mpl_canvas = getattr(canvas, "canva", None)
    origin_draw = getattr(mpl_canvas, "draw", None) if mpl_canvas is not None else None
    origin_idle = getattr(mpl_canvas, "draw_idle", None) if mpl_canvas is not None else None

    def _canvas_draw(*args, **kwargs):
        redraws["count"] += 1
        if callable(origin_draw):
            return origin_draw(*args, **kwargs)
        return None

    def _canvas_idle(*args, **kwargs):
        redraws["count"] += 1
        if callable(origin_idle):
            return origin_idle(*args, **kwargs)
        return None

    if mpl_canvas is not None and origin_draw is not None:
        mpl_canvas.draw = _canvas_draw
    if mpl_canvas is not None and origin_idle is not None:
        mpl_canvas.draw_idle = _canvas_idle
    try:
        with (
            patch.object(ComponentState, "clone", _clone),
            patch("mygui.application_theme.windows.refresh_chrome_style", _polish),
        ):
            if cached_ids:
                for component_id in cached_ids:
                    canvas.select_component(component_id)
                    wait_settle(host, visible_only=True)
                for _ in range(WARMUP_FRAMES):
                    measure_frame(
                        host,
                        lambda: canvas.select_component(cached_ids[0]),
                        visible_only=True,
                    )
                for index in range(SAMPLE_FRAMES):
                    component_id = cached_ids[index % len(cached_ids)]
                    samples.append(
                        measure_frame(
                            host,
                            lambda current=component_id: canvas.select_component(current),
                            visible_only=True,
                        )
                    )
    finally:
        if mpl_canvas is not None and origin_draw is not None:
            mpl_canvas.draw = origin_draw
        if mpl_canvas is not None and origin_idle is not None:
            mpl_canvas.draw_idle = origin_idle
    if samples:
        measured = {
            "paintRegion": samples[0].paint_region,
            "dispatch_ms": {
                "samples": [item.dispatch_ms for item in samples],
                "median": sorted(item.dispatch_ms for item in samples)[len(samples) // 2],
                "p95": p95_ms([item.dispatch_ms for item in samples]),
            },
            "first_paint_ms": {
                "samples": [item.first_paint_ms for item in samples],
                "median": sorted(item.first_paint_ms for item in samples)[len(samples) // 2],
                "p95": p95_ms([item.first_paint_ms for item in samples]),
            },
            "settle_ms": {
                "samples": [item.settle_ms for item in samples],
                "median": sorted(item.settle_ms for item in samples)[len(samples) // 2],
                "p95": p95_ms([item.settle_ms for item in samples]),
            },
        }
        harness.timings.update(
            staged_timing_payload(
                "cached_component_switch",
                measured,
                alias_median_key="cached_component_switch_ms",
                alias_p95_key="cached_component_switch_p95_ms",
            )
        )
        harness.timings["cached_component_switch_dispatch_p95_ms"] = measured["dispatch_ms"]["p95"]
        harness.timings["cached_component_switch_first_paint_p95_ms"] = measured["first_paint_ms"]["p95"]
        harness.timings["component_state_clone_count"] = clone_calls["count"]
        harness.timings["matplotlib_redraw_count"] = redraws["count"]
        harness.timings["window_polish_count"] = polish["count"]
        if clone_calls["count"] or redraws["count"] or polish["count"]:
            raise SmokeError(
                "Cached component switch leaked clone/redraw/polish: "
                f"clone={clone_calls['count']} redraw={redraws['count']} "
                f"polish={polish['count']} region={samples[0].paint_region}."
            )
        assert_switch_gates(harness.timings)
        before = theme_census()
        for index in range(SWITCH_LEAK_ITERS):
            canvas.select_component(cached_ids[index % len(cached_ids)])
            if index % 100 == 0:
                harness.pump(0)
        require_census_stable(before, theme_census(), "1000 component switches")
