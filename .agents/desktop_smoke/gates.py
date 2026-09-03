"""Native desktop-smoke performance and leak gates for UI stabilization."""

from __future__ import annotations

from typing import Any

SWITCH_DISPATCH_P95_MS = 16.0
SWITCH_FIRST_PAINT_P95_MS = 100.0
SWITCH_SETTLE_P95_MS = 150.0
MAINWINDOW_CONSTRUCT_MS = 300.0
THEME_SETTLE_P95_MS = 1000.0
THEME_IMPROVEMENT = 0.30
PHASE0_THEME_PREVIEW_P95_MS = 1500.0
PHASE0_THEME_ROLLBACK_P95_MS = 2200.0
WARMUP_FRAMES = 3
SAMPLE_FRAMES = 20
SWITCH_LEAK_ITERS = 1000
THEME_LEAK_ITERS = 50


def require_p95(name: str, actual: float, limit: float) -> None:
    """Raise if a p95 sample exceeds the hard gate."""

    from desktop_smoke.harness import SmokeError

    if actual > limit:
        raise SmokeError(f"{name} p95 {actual:.1f}ms exceeds {limit:.1f}ms.")


def require_improvement(name: str, actual: float, baseline: float) -> None:
    """Raise unless ``actual`` is at least 30% faster than ``baseline``."""

    from desktop_smoke.harness import SmokeError

    limit = baseline * (1.0 - THEME_IMPROVEMENT)
    if actual > limit:
        raise SmokeError(
            f"{name} p95 {actual:.1f}ms did not improve 30% vs baseline "
            f"{baseline:.1f}ms (need ≤ {limit:.1f}ms)."
        )


def theme_census() -> dict[str, int]:
    """Count live theme windows, participants, and top-level widgets."""

    from PySide6.QtWidgets import QApplication

    from mygui.application_theme.windows import default_window_registry

    registry = default_window_registry()
    app = QApplication.instance()
    windows = list(registry.live_widgets())
    metrics = list(registry.live_metrics_participants())
    icons = list(registry.live_icon_participants())
    palettes = list(registry.live_palette_participants())
    widgets = app.allWidgets() if app is not None else []
    tops = [widget for widget in widgets if widget.isWindow()]
    return {
        "windows": len(windows),
        "metrics": len(metrics),
        "icons": len(icons),
        "palettes": len(palettes),
        "top_level": len(tops),
    }


def require_census_stable(before: dict[str, int], after: dict[str, int], label: str) -> None:
    """Raise if theme participant or window counts grew."""

    from desktop_smoke.harness import SmokeError

    growth = {
        key: after[key] - before[key]
        for key in before
        if after.get(key, 0) > before[key]
    }
    if growth:
        raise SmokeError(f"{label} leaked theme census {growth}: {before} -> {after}.")


def assert_construct_gate(timings: dict[str, Any]) -> None:
    """Raise unless native MainWindow construction stayed within 300 ms."""

    from desktop_smoke.harness import SmokeError

    actual = float(timings["mainwindow_construct_ms"])
    if actual > MAINWINDOW_CONSTRUCT_MS:
        raise SmokeError(
            f"native MainWindow construct {actual:.1f}ms exceeds "
            f"{MAINWINDOW_CONSTRUCT_MS:.1f}ms."
        )


def assert_switch_gates(timings: dict[str, Any]) -> None:
    require_p95(
        "cached component switch dispatch",
        float(timings["cached_component_switch_dispatch_p95_ms"]),
        SWITCH_DISPATCH_P95_MS,
    )
    require_p95(
        "cached component switch first paint",
        float(timings["cached_component_switch_first_paint_p95_ms"]),
        SWITCH_FIRST_PAINT_P95_MS,
    )
    require_p95(
        "cached component switch settle",
        float(timings["cached_component_switch_p95_ms"]),
        SWITCH_SETTLE_P95_MS,
    )
    if int(timings.get("component_state_clone_count") or 0):
        from desktop_smoke.harness import SmokeError

        raise SmokeError("Cached component switch cloned ComponentState.")
    if int(timings.get("matplotlib_redraw_count") or 0):
        from desktop_smoke.harness import SmokeError

        raise SmokeError("Cached component switch redrew Matplotlib.")
    if int(timings.get("window_polish_count") or 0):
        from desktop_smoke.harness import SmokeError

        raise SmokeError("Cached component switch polished the full window.")


def assert_theme_gates(timings: dict[str, Any]) -> None:
    preview = float(timings["appearance_dark_preview_p95_ms"])
    rollback = float(timings["appearance_dark_rollback_p95_ms"])
    require_p95("theme preview settle", preview, THEME_SETTLE_P95_MS)
    require_p95("theme rollback settle", rollback, THEME_SETTLE_P95_MS)
    require_improvement(
        "theme preview settle",
        preview,
        PHASE0_THEME_PREVIEW_P95_MS,
    )
    require_improvement(
        "theme rollback settle",
        rollback,
        PHASE0_THEME_ROLLBACK_P95_MS,
    )
