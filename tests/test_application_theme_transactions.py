"""Theme transaction fault injection: apply rollback and UNCERTAIN health."""

from __future__ import annotations

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtGui import QPalette
from PySide6.QtWidgets import QApplication

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
)


def _qapp() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


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


if __name__ == "__main__":
    unittest.main()
