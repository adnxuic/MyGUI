"""Tests for process-level font diagnostics shown in the Message Bar."""

from __future__ import annotations

import logging
import os
from pathlib import Path
import unittest
from unittest.mock import Mock, patch
import warnings

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from mygui import status_messages
from mygui.font_diagnostics import (
    FontDiagnosticBridge,
    capture_font_diagnostics,
    normalize_font_diagnostic,
)


ROOT = Path(__file__).resolve().parents[1]


class FontDiagnosticNormalizationTests(unittest.TestCase):
    def test_matplotlib_warning_and_log_share_one_glyph_key(self):
        warning_notice = normalize_font_diagnostic(
            "Glyph 65509 (\\N{FULLWIDTH YEN SIGN}) missing from font(s) DejaVu Sans."
        )
        log_notice = normalize_font_diagnostic(
            "Font 'default' does not have a glyph for '\\uffe5' "
            "[U+ffe5], substituting with a dummy symbol."
        )

        self.assertIsNotNone(warning_notice)
        self.assertIsNotNone(log_notice)
        self.assertEqual(warning_notice.key, log_notice.key)
        self.assertIn("U+FFE5", warning_notice.message)

    def test_directwrite_warning_names_the_fallback_font_family(self):
        notice = normalize_font_diagnostic(
            "DirectWrite: CreateFontFaceFromHDC() failed "
            "(localized system error) for QFontDef(Family=\"Small Fonts\", "
            "pointsize=13)"
        )

        self.assertIsNotNone(notice)
        self.assertEqual(notice.key, "directwrite-font:small fonts")
        self.assertIn('"Small Fonts"', notice.message)
        self.assertIn("fallback", notice.message)

    def test_unrelated_runtime_messages_are_ignored(self):
        self.assertIsNone(normalize_font_diagnostic("ordinary warning"))
        self.assertIsNone(normalize_font_diagnostic("Glyph 65 loaded."))


class FontDiagnosticBridgeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def tearDown(self):
        status_messages.clear_status_handler()

    def test_startup_buffer_combines_and_deduplicates_font_warnings(self):
        bridge = FontDiagnosticBridge()
        events = []

        bridge.report(
            "Glyph 65509 missing from font(s) DejaVu Sans."
        )
        bridge.report(
            "Font 'default' does not have a glyph for '\\uffe5' "
            "[U+ffe5], substituting with a dummy symbol."
        )
        bridge.report(
            "DirectWrite: CreateFontFaceFromHDC() failed for "
            "QFontDef(Family=\"System\", pointsize=13)"
        )
        status_messages.set_status_handler(
            lambda message, level: events.append((message, level))
        )

        self.assertTrue(bridge.flush_pending())
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0][1], "warning")
        self.assertEqual(events[0][0].count("U+FFE5"), 1)
        self.assertIn('"System"', events[0][0])

        bridge.report("Glyph 65509 missing from font(s) DejaVu Sans.")
        self.app.processEvents()
        self.assertEqual(len(events), 1)

    def test_scoped_capture_keeps_business_render_log_out_of_global_queue(self):
        bridge = FontDiagnosticBridge()
        events = []
        status_messages.set_status_handler(
            lambda message, level: events.append((message, level))
        )
        bridge.install()
        try:
            with capture_font_diagnostics() as captured:
                logging.getLogger("matplotlib.mathtext").warning(
                    "Font 'default' does not have a glyph for '\\u90fd' "
                    "[U+90FD], substituting with a dummy symbol."
                )
            self.app.processEvents()

            self.assertEqual(events, [])
            self.assertEqual(len(captured.notices), 1)
            self.assertEqual(captured.notices[0].key, "matplotlib-glyph:90FD")
        finally:
            bridge.uninstall()

    def test_hooks_preserve_existing_outputs_and_restore_cleanly(self):
        bridge = FontDiagnosticBridge()
        previous_qt_handler = Mock()
        previous_python_handler = Mock()

        with (
            patch.object(warnings, "showwarning", previous_python_handler),
            patch(
                "mygui.font_diagnostics.qInstallMessageHandler",
                side_effect=[previous_qt_handler, bridge._qt_message_handler],
            ) as install_qt_handler,
        ):
            bridge.install()
            self.assertIn(
                bridge._logging_handler,
                logging.getLogger("matplotlib").handlers,
            )

            warnings.showwarning(
                "Glyph 65509 missing from font(s) DejaVu Sans.",
                UserWarning,
                "main.py",
                1,
            )
            bridge._handle_qt_message(
                object(),
                object(),
                "DirectWrite: CreateFontFaceFromHDC() failed for "
                "QFontDef(Family=\"System\", pointsize=13)",
            )
            record = logging.LogRecord(
                "matplotlib._mathtext",
                logging.WARNING,
                "_mathtext.py",
                1,
                "Font 'default' does not have a glyph for '\\uffe5' "
                "[U+ffe5], substituting with a dummy symbol.",
                (),
                None,
            )
            bridge._logging_handler.emit(record)

            previous_python_handler.assert_called_once()
            previous_qt_handler.assert_called_once()
            bridge.uninstall()

            self.assertIs(warnings.showwarning, previous_python_handler)
            self.assertNotIn(
                bridge._logging_handler,
                logging.getLogger("matplotlib").handlers,
            )
            self.assertEqual(install_qt_handler.call_count, 2)

    def test_application_installs_bridge_before_font_and_widget_setup(self):
        source = (ROOT / "main.py").read_text(encoding="utf-8")
        startup = source[source.index('if __name__ == "__main__":'):]

        application_index = startup.index("app = QApplication(sys.argv)")
        bridge_index = startup.index("install_font_diagnostic_bridge()")
        theme_index = startup.index("compose_application_settings_and_theme(app)")
        window_index = startup.index("window = MainWindow")

        self.assertLess(application_index, bridge_index)
        self.assertLess(bridge_index, theme_index)
        self.assertLess(theme_index, window_index)
        self.assertNotIn("configure_application_font", startup)

    def test_main_window_flushes_buffered_startup_font_warning(self):
        import main
        from mygui import font_diagnostics

        bridge = FontDiagnosticBridge()
        previous_bridge = font_diagnostics._RUNTIME_BRIDGE
        font_diagnostics._RUNTIME_BRIDGE = bridge
        bridge.report(
            "DirectWrite: CreateFontFaceFromHDC() failed for "
            "QFontDef(Family=\"System\", pointsize=13)"
        )
        window = None
        try:
            window = main.MainWindow()
            self.assertEqual(
                window.bottom_bar.message_bar.property("level"),
                "warning",
            )
            self.assertIn(
                '"System"',
                window.bottom_bar.message_bar.message_label.toolTip(),
            )
            self.assertIn(
                '"System"',
                window.bottom_bar.message_bar.full_message,
            )
        finally:
            if window is not None:
                window.close_without_prompt()
                window.deleteLater()
                self.app.processEvents()
            font_diagnostics._RUNTIME_BRIDGE = previous_bridge


if __name__ == "__main__":
    unittest.main()
