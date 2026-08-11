import os
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication

from mygui.widgets.common_widget.min_widget.color_library import ColorLibrary


class ColorLibraryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.path = Path(self.directory.name) / "colors.ini"
        self.settings = QSettings(str(self.path), QSettings.IniFormat)

    def tearDown(self):
        self.settings.clear()
        self.settings.sync()
        self.directory.cleanup()

    def test_recent_colors_are_deduplicated_and_limited(self):
        library = ColorLibrary(self.settings)
        for index in range(25):
            library.record_recent(f"#{index:02X}0000")
        library.record_recent("#180000")
        self.assertEqual(len(library.recent_colors), 20)
        self.assertEqual(library.recent_colors[0], "#180000")
        self.assertEqual(len(set(library.recent_colors)), 20)

    def test_batch_recent_colors_are_saved_once_in_application_order(self):
        library = ColorLibrary(self.settings)
        emissions = []
        library.changed.connect(lambda: emissions.append(True))
        library.record_recent_many(("red", "blue", "red"))
        self.assertEqual(library.recent_colors, ["#FF0000", "#0000FF"])
        self.assertEqual(len(emissions), 1)

    def test_custom_palette_crud_persists_stable_id(self):
        library = ColorLibrary(self.settings)
        created = library.create_custom_palette("My palette", ["red", "#00FF0080"])
        updated = library.update_custom_palette(created.id, "Renamed", ["blue", "white"])
        self.assertEqual(updated.id, created.id)
        reloaded = ColorLibrary(self.settings)
        self.assertEqual(reloaded.palette(created.id).name, "Renamed")
        self.assertTrue(reloaded.delete_custom_palette(created.id))
        self.assertIsNone(reloaded.palette(created.id))

    def test_custom_palette_rules_are_enforced(self):
        library = ColorLibrary(self.settings)
        library.create_custom_palette("Unique", ["red", "blue"])
        with self.assertRaises(ValueError):
            library.create_custom_palette("unique", ["black", "white"])
        with self.assertRaises(ValueError):
            library.create_custom_palette("Too short", ["black"])
        with self.assertRaises(ValueError):
            library.create_custom_palette("Too long", ["black"] * 13)

    def test_color_and_palette_favorites_persist(self):
        library = ColorLibrary(self.settings)
        palette = library.palettes()[0]
        library.toggle_favorite_color("tab:blue")
        library.toggle_favorite_palette(palette.id)
        reloaded = ColorLibrary(self.settings)
        self.assertTrue(reloaded.is_favorite_color("#1F77B4"))
        self.assertTrue(reloaded.is_favorite_palette(palette.id))

    def test_corrupt_settings_degrade_to_empty_library(self):
        self.settings.beginGroup("colorLibrary")
        self.settings.setValue("version", 1)
        self.settings.setValue("state", "not-json")
        self.settings.endGroup()
        library = ColorLibrary(self.settings)
        self.assertTrue(library.consume_load_warning())
        self.assertEqual(library.recent_colors, [])
        self.assertEqual(library.custom_palettes, {})


if __name__ == "__main__":
    unittest.main()
