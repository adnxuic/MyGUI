"""Theme transaction fault injection: apply rollback and UNCERTAIN health."""

from __future__ import annotations

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from unittest.mock import patch

from PySide6.QtCore import QEvent, QObject, Qt
from PySide6.QtGui import QFont, QPalette
from PySide6.QtWidgets import QApplication, QWidget

from mygui.application_theme import (
    APPLY_STEPS,
    AppearancePreferences,
    Density,
    EffectiveScheme,
    FakeStyleHints,
    ThemeApplyError,
    ThemeFaultHooks,
    ThemeHealth,
    ThemeMode,
    ThemeRollbackError,
    ThemeService,
    ThemeValidationError,
)
from mygui.application_theme.ports import NullThemeIconProvider


def _qapp() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


class _RecordingIcons:
    def __init__(self) -> None:
        self.prerender_calls = 0
        self.apply_calls = 0
        self._inner = NullThemeIconProvider()

    def prerender(self, snapshot):
        self.prerender_calls += 1
        return self._inner.prerender(snapshot)

    def apply(self, rendered: object) -> None:
        self.apply_calls += 1
        self._inner.apply(rendered)

    def capture(self) -> object:
        return self._inner.capture()

    def restore(self, memento: object) -> None:
        self._inner.restore(memento)


class _RecordingQssRenderer:
    def __init__(self) -> None:
        self.render_calls = 0

    def render_application(self, snapshot) -> str:
        self.render_calls += 1
        return ""

    def render_resource(self, resource: str, snapshot) -> str:
        self.render_calls += 1
        return str(resource)


class ThemeTransactionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = _qapp()
        cls._origin_font = cls.app.font()
        cls._origin_palette = QPalette(cls.app.palette())
        cls._origin_stylesheet = cls.app.styleSheet()

    def tearDown(self) -> None:
        theme = getattr(self, "theme", None)
        if theme is not None:
            theme.shutdown()
        self.app.setFont(self._origin_font)
        self.app.setPalette(self._origin_palette)
        self.app.setStyleSheet(self._origin_stylesheet)

    def _service(self, **kwargs) -> ThemeService:
        hints = kwargs.pop("style_hints", None) or FakeStyleHints(Qt.ColorScheme.Light)
        self.theme = ThemeService(self.app, style_hints=hints, **kwargs)
        self.events: list[object] = []
        self.theme.subscribe(lambda _old, new: self.events.append(new))
        return self.theme

    def _prefs(self, **kwargs) -> AppearancePreferences:
        values = {"mode": ThemeMode.DARK, "font_pt": 12, "density": Density.COMPACT}
        values.update(kwargs)
        return AppearancePreferences(**values)

    def test_each_apply_step_failure_rolls_back_without_event(self) -> None:
        for step in APPLY_STEPS:
            with self.subTest(step=step):
                theme = self._service(
                    fault_hooks=ThemeFaultHooks(fail_apply_step=step)
                )
                origin = theme.snapshot()
                origin_font = self.app.font().pointSize()
                origin_sheet = self.app.styleSheet()
                with self.assertRaises(ThemeApplyError):
                    theme.apply_committed(self._prefs())
                self.assertIs(theme.snapshot(), origin)
                self.assertEqual(theme.health(), ThemeHealth.OK)
                self.assertEqual(self.events, [])
                self.assertEqual(self.app.font().pointSize(), origin_font)
                self.assertEqual(self.app.styleSheet(), origin_sheet)
                self.assertNotEqual(origin.scheme, EffectiveScheme.DARK)
                theme.shutdown()

    def test_prerender_failure_does_not_mutate_snapshot(self) -> None:
        theme = self._service(fault_hooks=ThemeFaultHooks(fail_prerender=True))
        origin = theme.snapshot()
        with self.assertRaises(ThemeApplyError):
            theme.preview(self._prefs())
        self.assertIs(theme.snapshot(), origin)
        self.assertEqual(self.events, [])
        self.assertEqual(theme.health(), ThemeHealth.OK)

    def test_preview_failure_keeps_previous_preview(self) -> None:
        theme = self._service()
        theme.preview(self._prefs(mode=ThemeMode.DARK, font_pt=10))
        after_first = theme.snapshot()
        theme._fault_hooks = ThemeFaultHooks(fail_apply_step="qss")
        with self.assertRaises(ThemeApplyError):
            theme.preview(self._prefs(mode=ThemeMode.LIGHT, font_pt=16))
        self.assertIs(theme.snapshot(), after_first)
        self.assertEqual(theme.snapshot().preferences.font_pt, 10)
        self.assertEqual(self.events, [])

    def test_rollback_failure_is_uncertain_and_not_success(self) -> None:
        theme = self._service(
            fault_hooks=ThemeFaultHooks(
                fail_apply_step="qss",
                fail_rollback_step="palette",
            )
        )
        origin = theme.snapshot()
        with self.assertRaises(ThemeRollbackError) as ctx:
            theme.apply_committed(self._prefs())
        error = ctx.exception
        self.assertFalse(error.rollback_complete)
        self.assertEqual(theme.health(), ThemeHealth.UNCERTAIN)
        self.assertIs(theme.snapshot(), origin)
        self.assertEqual(self.events, [])
        self.assertNotEqual(theme.health().value, "ok")

    def test_cancel_preview_rollback_failure_is_uncertain(self) -> None:
        theme = self._service()
        origin = theme.snapshot()
        theme.preview(self._prefs())
        previewed = theme.snapshot()
        original_restore = theme._restore_step

        def _boom(step: str, memento) -> None:
            if step == "font":
                raise RuntimeError("theme font rollback failed")
            original_restore(step, memento)

        theme._restore_step = _boom  # type: ignore[method-assign]
        with self.assertRaises(ThemeRollbackError) as ctx:
            theme.cancel_preview()
        self.assertFalse(ctx.exception.rollback_complete)
        self.assertEqual(theme.health(), ThemeHealth.UNCERTAIN)
        self.assertEqual(self.events, [])
        self.assertIs(theme.snapshot(), previewed)
        self.assertIsNot(theme.snapshot(), origin)

    def test_metrics_and_icons_ports_may_noop(self) -> None:
        theme = self._service()
        theme.apply_committed(self._prefs(density=Density.COMFORTABLE, font_pt=16))
        self.assertEqual(theme.snapshot().preferences.density, Density.COMFORTABLE)
        self.assertGreaterEqual(theme.snapshot().metrics.rail, 52)
        self.assertEqual(len(self.events), 1)

    def test_small_font_change_skips_qss_palette_and_icons(self) -> None:
        theme = self._service()
        theme.apply_committed(
            AppearancePreferences(mode=ThemeMode.LIGHT, font_pt=9, density=Density.STANDARD)
        )
        theme.preview(
            AppearancePreferences(mode=ThemeMode.LIGHT, font_pt=10, density=Density.STANDARD)
        )
        self.assertEqual(theme.last_applied_steps, ("font",))
        theme.cancel_preview()
        self.assertEqual(theme.snapshot().preferences.font_pt, 9)

    def test_small_font_change_skips_icon_and_qss_prerender(self) -> None:
        icons = _RecordingIcons()
        renderer = _RecordingQssRenderer()
        theme = self._service(icon_provider=icons, qss_renderer=renderer)
        theme.apply_committed(
            AppearancePreferences(mode=ThemeMode.LIGHT, font_pt=9, density=Density.STANDARD)
        )
        icons.prerender_calls = 0
        icons.apply_calls = 0
        renderer.render_calls = 0
        theme.preview(
            AppearancePreferences(mode=ThemeMode.LIGHT, font_pt=10, density=Density.STANDARD)
        )
        self.assertEqual(theme.last_applied_steps, ("font",))
        self.assertEqual(icons.prerender_calls, 0)
        self.assertEqual(icons.apply_calls, 0)
        self.assertEqual(renderer.render_calls, 0)
        theme.cancel_preview()

    def test_font_floor_theme_and_density_run_expected_steps(self) -> None:
        theme = self._service()
        theme.apply_committed(
            AppearancePreferences(mode=ThemeMode.LIGHT, font_pt=9, density=Density.STANDARD)
        )
        theme.preview(
            AppearancePreferences(mode=ThemeMode.LIGHT, font_pt=16, density=Density.STANDARD)
        )
        self.assertIn("font", theme.last_applied_steps)
        self.assertIn("metrics", theme.last_applied_steps)
        self.assertNotIn("palette", theme.last_applied_steps)
        self.assertNotIn("icons", theme.last_applied_steps)
        theme.cancel_preview()

        theme.preview(
            AppearancePreferences(mode=ThemeMode.DARK, font_pt=9, density=Density.STANDARD)
        )
        self.assertEqual(theme.last_applied_steps, ("palette", "qss", "icons"))
        theme.cancel_preview()

        theme.preview(
            AppearancePreferences(
                mode=ThemeMode.LIGHT, font_pt=9, density=Density.COMPACT
            )
        )
        self.assertEqual(theme.last_applied_steps, ("qss", "metrics", "icons"))
        theme.cancel_preview()

    def test_ensure_committed_is_noop_until_system_scheme_changes(self) -> None:
        theme = self._service()
        prefs = AppearancePreferences(mode=ThemeMode.SYSTEM, font_pt=9)
        theme.apply_committed(prefs)
        steps_before = theme.last_applied_steps
        self.events.clear()
        self.assertFalse(theme.ensure_committed(prefs))
        self.assertEqual(self.events, [])
        self.assertEqual(theme.last_applied_steps, steps_before)

        prepare_calls: list[int] = []
        original_prepare = theme._prepare

        def _record_prepare(*args, **kwargs):
            prepare_calls.append(1)
            return original_prepare(*args, **kwargs)

        theme._prepare = _record_prepare  # type: ignore[method-assign]
        self.assertFalse(theme.ensure_committed(prefs))
        self.assertEqual(prepare_calls, [])

        theme.shutdown()
        theme._hints.set_color_scheme(Qt.ColorScheme.Dark)
        self.events.clear()
        self.assertTrue(theme.ensure_committed(prefs))
        self.assertEqual(len(self.events), 1)
        self.assertEqual(theme.snapshot().scheme, EffectiveScheme.DARK)

    def test_guard_paths_preview_exceptions_and_event_filter(self) -> None:
        with self.assertRaisesRegex(ThemeValidationError, "QApplication"):
            ThemeService(None, parent=self.app)
        theme = self._service()
        unsub = theme.subscribe(lambda *_args: None)
        unsub()
        unsub()
        with self.assertRaises(ThemeValidationError):
            theme._prepare(object())
        prepared = theme._prepare(self._prefs())
        with self.assertRaisesRegex(ThemeApplyError, "Unknown theme apply step"):
            theme._run_apply_step("not-a-step", prepared)
        from mygui.application_theme.service import _ChromeMemento

        with self.assertRaisesRegex(ThemeApplyError, "Unknown theme restore step"):
            theme._restore_step(
                "not-a-step",
                _ChromeMemento(font=QFont(), palette=QPalette(), stylesheet=""),
            )
        theme._health = ThemeHealth.UNCERTAIN
        self.assertFalse(theme.ensure_committed(self._prefs()))
        theme._in_transaction = True
        theme._on_system_scheme_changed()
        theme._in_transaction = False
        theme._health = ThemeHealth.OK

        entering = self._service()
        with patch.object(
            entering,
            "_apply_prepared",
            side_effect=RuntimeError("preview boom"),
        ):
            with self.assertRaises(ThemeApplyError):
                entering.preview(self._prefs())
        self.assertFalse(entering._in_preview)

        rolling = self._service()
        with patch.object(
            rolling,
            "_apply_prepared",
            side_effect=ThemeRollbackError((RuntimeError("preview rollback"),)),
        ):
            with self.assertRaises(ThemeRollbackError):
                rolling.preview(self._prefs())
        self.assertFalse(rolling._in_preview)

        from mygui.application_theme.service import _SkipHiddenFontFilter

        filt = _SkipHiddenFontFilter(self.app)
        other = QEvent(QEvent.Type.MouseMove)
        self.assertFalse(filt.eventFilter(self.app, other))
        font_event = QEvent(QEvent.Type.FontChange)
        self.assertFalse(filt.eventFilter(QObject(), font_event))
        hidden = QWidget()
        hidden.hide()
        self.assertTrue(filt.eventFilter(hidden, font_event))
        with patch.object(hidden, "isVisible", side_effect=RuntimeError("deleted")):
            self.assertTrue(filt.eventFilter(hidden, font_event))
        hidden.deleteLater()


if __name__ == "__main__":
    unittest.main()
