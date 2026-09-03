"""Matplotlib Style Dialog walk. Group id: styles.

Runs after other performance scenarios so cached Style dialogs cannot pollute
theme benchmarks. Default coverage is three representative styles;
``--all-styles`` walks every visible Matplotlib Style Action.
"""

from __future__ import annotations

from typing import Any, Callable

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QDialog

from mygui.widgets.title_bar.style_gallery import (
    APPLY_TEMPLATE_ACTION,
    DEFAULT_STYLE_DIALOG_NAMES,
    HIDDEN_STYLE_NAMES,
    visible_matplotlib_style_names,
)

from desktop_smoke.harness import SmokeError, SmokeHarness


def run_styles_scenarios(
    harness: SmokeHarness,
    *,
    all_styles: bool = False,
) -> list[dict[str, Any]]:
    """Open, screenshot, and Reject Style dialogs without applying Figure style."""

    results: list[dict[str, Any]] = []
    results.append(
        _run_case(
            harness,
            "styles.walk_style_dialogs",
            lambda: _scenario_walk_style_dialogs(harness, all_styles=all_styles),
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
            if harness.window is not None:
                harness.grab_main(f"{scenario_id.replace('.', '-')}-failure")
        except Exception:
            pass
        return {
            "id": scenario_id,
            "status": "failed",
            "error": f"{type(exc).__name__}: {exc}",
            "screenshotCount": len(harness.screenshots) - before,
        }


def _project_fingerprint(harness: SmokeHarness) -> tuple[object, ...]:
    window = harness.window
    canvas = window.figure_window.current_canva if window is not None else None
    if canvas is None:
        return (None, None, None, None)
    registry = canvas.component_registry
    component_ids = tuple(state.id for state in registry.states())
    undo_key = None
    repository = getattr(window, "repository", None)
    if repository is not None:
        try:
            stack = repository.undo_stack(canvas.project_id)
        except Exception:
            stack = None
        if stack is not None:
            undo_key = (stack.count(), stack.index())
    settings_key = None
    if window.settings_service is not None:
        appearance = window.settings_service.snapshot().appearance
        settings_key = (
            appearance.theme_mode,
            appearance.ui_font_point_size,
            appearance.density,
        )
    return (
        canvas.current_component_id,
        component_ids,
        undo_key,
        settings_key,
    )


def _style_dialog(harness: SmokeHarness) -> QDialog | None:
    app = harness.app
    if app is None:
        return None
    for widget in app.topLevelWidgets():
        try:
            if widget.objectName() == "style_dialog" and widget.isVisible():
                return widget  # type: ignore[return-value]
        except RuntimeError:
            continue
    for widget in app.topLevelWidgets():
        if isinstance(widget, QDialog) and widget.isVisible():
            name = widget.objectName()
            if name not in {"setting_dialog"}:
                return widget
    return None


def _scenario_walk_style_dialogs(harness: SmokeHarness, *, all_styles: bool) -> None:
    if harness.window is None:
        raise SmokeError("MainWindow is not started.")
    if harness.window.figure_window.current_canva is None:
        harness.seed_default_project()
    expected = (
        list(visible_matplotlib_style_names())
        if all_styles
        else list(DEFAULT_STYLE_DIALOG_NAMES)
    )
    if APPLY_TEMPLATE_ACTION in expected:
        raise SmokeError("Apply Template must not be part of the Style Dialog walk.")
    hidden = [name for name in expected if name in HIDDEN_STYLE_NAMES]
    if hidden:
        raise SmokeError(f"Hidden styles were scheduled: {hidden}.")

    bar = harness.window.title_bar.selector_style_bar
    missing_actions = [name for name in expected if name not in bar.action_dict]
    if missing_actions:
        raise SmokeError(
            "Style gallery is missing visible actions: " + ", ".join(missing_actions)
        )
    if APPLY_TEMPLATE_ACTION not in bar.action_dict:
        raise SmokeError("Apply Template action is missing from the Style gallery.")

    before = _project_fingerprint(harness)
    visited: list[str] = []
    for style_name in expected:
        action = bar.action_dict[style_name]
        error: list[BaseException] = []

        def while_open(name: str = style_name) -> None:
            try:
                dialog = _style_dialog(harness)
                if dialog is None:
                    raise SmokeError(f"Style dialog for {name!r} did not open.")
                slug = name.replace(".", "_")
                harness.grab(dialog, f"style-dialog-{slug}")
                dialog.reject()
            except BaseException as exc:  # noqa: BLE001
                error.append(exc)
                dialog = _style_dialog(harness)
                if dialog is not None:
                    try:
                        dialog.reject()
                    except RuntimeError:
                        pass

        QTimer.singleShot(0, while_open)
        action.trigger()
        harness.pump(40)
        if error:
            raise error[0]
        visited.append(style_name)

    missing = [name for name in expected if name not in visited]
    extra = [name for name in visited if name not in expected]
    harness.all_styles = bool(all_styles)
    harness.expected_style_dialogs = list(expected)
    harness.visited_style_dialogs = list(visited)
    harness.missing_style_dialogs = list(missing)
    if missing or extra or len(visited) != len(expected):
        raise SmokeError(
            "Style Dialog walk mismatch: "
            f"expected={len(expected)} visited={len(visited)} "
            f"missing={missing} extra={extra}."
        )
    after = _project_fingerprint(harness)
    if after != before:
        raise SmokeError(
            "Rejecting Style dialogs changed Figure, selection, Settings, or history."
        )
    leftover = _style_dialog(harness)
    if leftover is not None:
        raise SmokeError("A Style dialog remained visible after Reject.")
