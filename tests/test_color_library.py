import os
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from types import SimpleNamespace

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication

from mygui.application_settings.storage.types import DocumentHealth, StorageCommitResult
from mygui.figuremodify.style_base.color_models import ColorCycleState
from mygui.widgets.common_widget.min_widget.color_library import (
    ColorLibrary,
    ColorLibraryStoreError,
)


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

    def test_write_failure_leaves_memory_signal_and_color_cycle_unchanged(self):
        port = _FailingColorDocument()
        library = ColorLibrary(document=port)
        palette = library.create_custom_palette("Cycle", ["red", "blue"])
        cycle = ColorCycleState(palette)
        before_cycle = cycle.to_dict()
        emissions = []
        library.changed.connect(lambda: emissions.append(True))

        port.fail_commit = True
        port.fail_health = DocumentHealth.WRITE_UNCERTAIN
        library.record_recent("#00FF00")
        self.assertEqual(library.recent_colors, [])
        self.assertEqual(emissions, [])
        self.assertEqual(cycle.to_dict(), before_cycle)

        currently = library.toggle_favorite_color("#FF0000")
        self.assertFalse(currently)
        self.assertEqual(library.favorite_colors, [])
        self.assertEqual(emissions, [])

        with self.assertRaises(ColorLibraryStoreError):
            library.create_custom_palette("Other", ["black", "white"])
        self.assertEqual(list(library.custom_palettes), [palette.id])
        self.assertEqual(emissions, [])

        self.assertFalse(library.delete_custom_palette(palette.id))
        self.assertIn(palette.id, library.custom_palettes)
        self.assertEqual(cycle.to_dict(), before_cycle)
        self.assertEqual(emissions, [])

        port.fail_commit = False
        library.record_recent("#00FF00")
        self.assertEqual(library.recent_colors, ["#00FF00"])
        self.assertEqual(len(emissions), 1)
        self.assertEqual(cycle.to_dict(), before_cycle)

    def test_counts_clear_recent_and_reset_library(self):
        library = ColorLibrary(self.settings)
        library.record_recent("#FF0000")
        library.toggle_favorite_color("#00FF00")
        palette = library.create_custom_palette("Mine", ["red", "blue"])
        library.toggle_favorite_palette(palette.id)
        counts = library.counts()
        self.assertEqual(counts.recent_colors, 1)
        self.assertEqual(counts.favorite_colors, 1)
        self.assertEqual(counts.favorite_palettes, 1)
        self.assertEqual(counts.custom_palettes, 1)

        self.assertTrue(library.clear_recent_colors())
        self.assertEqual(library.recent_colors, [])
        self.assertEqual(library.favorite_colors, ["#00FF00"])
        self.assertIn(palette.id, library.custom_palettes)

        self.assertTrue(library.reset_library())
        self.assertEqual(library.recent_colors, [])
        self.assertEqual(library.favorite_colors, [])
        self.assertEqual(library.favorite_palette_ids, [])
        self.assertEqual(library.custom_palettes, {})
        reloaded = ColorLibrary(self.settings)
        self.assertEqual(reloaded.recent_colors, [])
        self.assertEqual(reloaded.custom_palettes, {})

    def test_clear_recent_and_reset_library_write_failure_leave_memory(self):
        port = _FailingColorDocument()
        library = ColorLibrary(document=port)
        library.record_recent("#112233")
        library.toggle_favorite_color("#445566")
        emissions = []
        library.changed.connect(lambda: emissions.append(True))
        port.fail_commit = True
        self.assertFalse(library.clear_recent_colors())
        self.assertEqual(library.recent_colors, ["#112233"])
        self.assertEqual(emissions, [])
        self.assertFalse(library.reset_library())
        self.assertEqual(library.recent_colors, ["#112233"])
        self.assertEqual(library.favorite_colors, ["#445566"])
        self.assertEqual(emissions, [])

    def test_recovery_payload_none_does_not_apply_empty_library(self):
        port = _FailingColorDocument()
        port.payload = None
        port.fail_health = DocumentHealth.RECOVERY_REQUIRED
        library = ColorLibrary(document=port)
        self.assertFalse(library.payload_applied())
        self.assertTrue(library.consume_load_warning())
        self.assertEqual(library.document_health(), DocumentHealth.RECOVERY_REQUIRED)
        self.assertFalse(library.writable())
        self.assertEqual(library.recent_colors, [])
        self.assertFalse(library.reset_library())
        self.assertFalse(library.payload_applied())

    def test_future_payload_none_does_not_apply_empty_library(self):
        port = _FailingColorDocument()
        port.payload = None
        port.fail_health = DocumentHealth.READ_ONLY_FUTURE
        library = ColorLibrary(document=port)
        self.assertFalse(library.payload_applied())
        self.assertEqual(library.document_health(), DocumentHealth.READ_ONLY_FUTURE)
        self.assertFalse(library.writable())


class _FailingColorDocument:
    def __init__(self):
        self.payload = {
            "recent_colors": [],
            "favorite_colors": [],
            "favorite_palette_ids": [],
            "custom_palettes": [],
        }
        self.fail_commit = False
        self.fail_health = DocumentHealth.NORMAL
        self.revision = 0

    def load(self):
        payload = None if self.payload is None else dict(self.payload)
        return SimpleNamespace(
            payload=payload,
            missing=self.payload is None,
            diagnostics=(),
            error=None,
            health=self.fail_health,
            revision=self.revision,
        )

    def commit(self, payload):
        if self.fail_commit:
            return StorageCommitResult(
                ok=False,
                health=self.fail_health,
                revision=self.revision,
                error="color library commit failed",
            )
        self.revision += 1
        self.payload = dict(payload)
        return StorageCommitResult(
            ok=True,
            health=DocumentHealth.NORMAL,
            revision=self.revision,
        )


if __name__ == "__main__":
    unittest.main()
