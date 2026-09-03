import os
import struct
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PIL import Image
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication, QLabel

from mygui import status_messages
from mygui.application_settings.models import (
    ExportBBoxInches,
    ExportFormatPreference,
    ExportMetadata,
    ExportSettings,
    JpegSubsampling,
    PadInchesKind,
    PadInchesValue,
    TiffCompression,
)
from mygui.application_settings import ApplicationSettingsService
from mygui.application_settings.ports import MemoryExportPreferences
from mygui.application_settings.storage import create_settings_backend
from mygui.figure_export import (
    ExportFormat,
    FigureExportContext,
    FigureExportOptions,
    FigureExportRequest,
    compatible_export_request,
    extension_error,
    options_from_export_settings,
    path_matches_format,
    publish_export_file,
    with_format_extension,
)
from mygui.widgets.common_widget.min_widget.color_library import ColorLibrary
from mygui.widgets.title_bar.titlebar_dialog.figure_export_dialog import (
    FigureExportDialog,
)
from mygui.widgets.title_bar.titlebar_dialog.figure_export_options_panel import (
    FigureExportOptionsPanel,
)
from main import MainWindow
from tests.axes_helpers import create_regular_axes


def _png_size(payload: bytes) -> tuple[int, int]:
    return struct.unpack(">II", payload[16:24])


class ExportModelTests(unittest.TestCase):
    def test_extension_aliases_resolve_closed_formats(self):
        self.assertEqual(ExportFormat.from_extension(".jpg"), ExportFormat.JPEG)
        self.assertEqual(ExportFormat.from_extension("JPEG"), ExportFormat.JPEG)
        self.assertEqual(ExportFormat.from_path("a.tif"), ExportFormat.TIFF)
        self.assertEqual(ExportFormat.from_path("a.tiff"), ExportFormat.TIFF)
        self.assertTrue(path_matches_format("shot.jpeg", ExportFormat.JPEG))
        self.assertFalse(path_matches_format("shot.png", ExportFormat.JPEG))
        self.assertIsNone(extension_error("shot.jpg", ExportFormat.JPEG))
        self.assertIn(".png", extension_error("shot.jpg", ExportFormat.PNG) or "")
        self.assertEqual(
            with_format_extension("shot.jpg", ExportFormat.PNG).name,
            "shot.png",
        )
        self.assertEqual(
            with_format_extension("shot.jpeg", ExportFormat.JPEG).name,
            "shot.jpeg",
        )

    def test_request_rejects_mismatched_extension_and_jpeg_transparency(self):
        options = FigureExportOptions.defaults(dpi=100)
        with self.assertRaisesRegex(ValueError, r"\.png"):
            FigureExportRequest(
                path=Path("figure.jpg"),
                format=ExportFormat.PNG,
                options=options,
            )
        with self.assertRaisesRegex(ValueError, "JPEG"):
            FigureExportRequest(
                path=Path("figure.jpg"),
                format=ExportFormat.JPEG,
                options=FigureExportOptions(dpi=100, transparent=True),
            )

    def test_png_metadata_requires_latin1_and_omits_empty_fields(self):
        with self.assertRaisesRegex(ValueError, "Latin-1"):
            FigureExportRequest(
                path=Path("figure.png"),
                format=ExportFormat.PNG,
                options=FigureExportOptions(
                    dpi=100,
                    metadata={"Title": "标题"},
                ),
            )
        request = FigureExportRequest(
            path=Path("figure.png"),
            format=ExportFormat.PNG,
            options=FigureExportOptions(
                dpi=120,
                metadata={"Title": "Chart", "Author": "  ", "Comment": "ok"},
            ),
        )
        kwargs = request.savefig_kwargs()
        self.assertEqual(kwargs["format"], "png")
        self.assertEqual(kwargs["dpi"], 120)
        self.assertEqual(kwargs["metadata"], {"Title": "Chart", "Comment": "ok"})
        self.assertEqual(kwargs["pil_kwargs"], {"compress_level": 6})

    def test_encoding_kwargs_follow_format_capabilities(self):
        png = FigureExportRequest(
            path=Path("a.png"),
            format=ExportFormat.PNG,
            options=FigureExportOptions(dpi=100, png_optimize=True),
        )
        self.assertEqual(png.pil_kwargs(), {"optimize": True})
        jpeg = FigureExportRequest(
            path=Path("a.jpg"),
            format=ExportFormat.JPEG,
            options=FigureExportOptions(
                dpi=100,
                jpeg_quality=40,
                jpeg_optimize=True,
                jpeg_progressive=True,
                jpeg_subsampling="4:2:0",
            ),
        )
        self.assertEqual(
            jpeg.pil_kwargs(),
            {
                "quality": 40,
                "optimize": True,
                "progressive": True,
                "subsampling": 2,
            },
        )
        tiff = FigureExportRequest(
            path=Path("a.tif"),
            format=ExportFormat.TIFF,
            options=FigureExportOptions(dpi=100, tiff_compression="lzw"),
        )
        self.assertEqual(tiff.pil_kwargs(), {"compression": "tiff_lzw"})
        webp = FigureExportRequest(
            path=Path("a.webp"),
            format=ExportFormat.WEBP,
            options=FigureExportOptions(
                dpi=100,
                webp_lossless=True,
                webp_quality=90,
                webp_alpha_quality=70,
                webp_method=2,
                webp_exact=True,
            ),
        )
        self.assertEqual(
            webp.pil_kwargs(),
            {
                "lossless": True,
                "quality": 90,
                "alpha_quality": 70,
                "method": 2,
                "exact": True,
            },
        )
        pdf = FigureExportRequest(
            path=Path("a.pdf"),
            format=ExportFormat.PDF,
            options=FigureExportOptions(
                dpi=200,
                bbox_inches="tight",
                pad_inches="layout",
                metadata={"Title": "Doc"},
            ),
        )
        kwargs = pdf.savefig_kwargs()
        self.assertIsNone(pdf.pil_kwargs())
        self.assertEqual(kwargs["bbox_inches"], "tight")
        self.assertEqual(kwargs["pad_inches"], "layout")
        self.assertEqual(kwargs["metadata"], {"Title": "Doc"})

    def test_compatible_save_request_uses_document_dpi_defaults(self):
        request = compatible_export_request("out.jpeg", dpi=175.5)
        self.assertEqual(request.format, ExportFormat.JPEG)
        self.assertEqual(request.options.dpi, 175.5)
        self.assertFalse(request.options.transparent)
        self.assertEqual(request.options.jpeg_quality, 75)
        self.assertIsNone(request.options.bbox_inches)

    def test_use_project_dpi_binds_live_project_dpi_not_custom(self):
        settings = ExportSettings(
            use_project_dpi=True,
            custom_dpi=220.0,
            format=ExportFormatPreference.PNG,
        )
        options = options_from_export_settings(settings, document_dpi=100.0)
        self.assertTrue(options.use_project_dpi)
        self.assertEqual(options.dpi, 100.0)
        custom = options_from_export_settings(
            ExportSettings(use_project_dpi=False, custom_dpi=180.0),
            document_dpi=100.0,
        )
        self.assertFalse(custom.use_project_dpi)
        self.assertEqual(custom.dpi, 180.0)

    def test_production_export_modules_do_not_import_qsettings(self):
        import ast

        root = Path(__file__).resolve().parents[1]
        files = [
            root / "mygui" / "figure_export.py",
            root / "mygui" / "text_io.py",
            root / "mygui" / "excel_io.py",
            root / "mygui" / "widgets" / "title_bar" / "py_title_bar.py",
            root / "mygui" / "widgets" / "title_bar" / "py_title_menu.py",
            root / "mygui" / "widgets" / "title_bar" / "titlebar_dialog" / "figure_export_dialog.py",
            root / "mygui" / "widgets" / "title_bar" / "titlebar_dialog" / "figure_export_options_panel.py",
            root / "mygui" / "widgets" / "title_bar" / "titlebar_dialog" / "py_title_bar_dialog.py",
            root / "mygui" / "widgets" / "common_widget" / "min_widget" / "color_library.py",
        ]
        for path in files:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            imported = []
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imported.extend(alias.name for alias in node.names)
                elif isinstance(node, ast.ImportFrom):
                    imported.append(node.module or "")
                    imported.extend(
                        f"{node.module}.{alias.name}" if node.module else alias.name
                        for alias in node.names
                    )
            self.assertFalse(
                any("QSettings" in name for name in imported),
                f"{path.name} still imports QSettings: {imported}",
            )


class FigureExportDialogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.settings_path = Path(self.directory.name) / "prefs.ini"
        self.settings = QSettings(str(self.settings_path), QSettings.IniFormat)
        self.library = ColorLibrary()
        self.export_port = MemoryExportPreferences()
        self.context = FigureExportContext(
            project_name="ProjectA",
            document_dpi=100.0,
            width_inches=6.4,
            height_inches=4.8,
        )
        self.exported: list[FigureExportRequest] = []

    def tearDown(self):
        self.settings.clear()
        self.settings.sync()
        self.directory.cleanup()

    def _dialog(self, export_callable=None, export_preferences=None):
        dialog = FigureExportDialog(
            context=self.context,
            color_library=self.library,
            export_preferences=export_preferences or self.export_port,
            export_callable=export_callable or self.exported.append,
        )
        self.addCleanup(dialog.deleteLater)
        return dialog

    def test_format_switches_encoding_and_metadata_pages(self):
        dialog = self._dialog()
        dialog.format_combo.setCurrentIndex(dialog.format_combo.findData("png"))
        self.assertTrue(dialog.transparent.isEnabled())
        self.assertEqual(dialog.encoding_stack.currentIndex(), 0)
        self.assertEqual(dialog.metadata_stack.currentIndex(), 0)
        dialog.png_optimize.setChecked(True)
        self.assertFalse(dialog.png_compress.isEnabled())

        dialog.format_combo.setCurrentIndex(dialog.format_combo.findData("jpeg"))
        self.assertFalse(dialog.transparent.isEnabled())
        self.assertFalse(dialog.transparent.isChecked())
        self.assertEqual(dialog.encoding_stack.currentIndex(), 1)
        jpeg_notes = [
            label.text()
            for label in dialog.metadata_stack.currentWidget().findChildren(QLabel)
        ]
        self.assertTrue(any("does not support Matplotlib metadata" in text for text in jpeg_notes))
        self.assertEqual(dialog.metadata_stack.currentIndex(), 1)
        self.assertTrue(dialog.path_edit.text().endswith(".jpg"))

        dialog.format_combo.setCurrentIndex(dialog.format_combo.findData("pdf"))
        self.assertEqual(dialog.encoding_stack.currentIndex(), 4)
        pdf_notes = [
            label.text()
            for label in dialog.encoding_stack.currentWidget().findChildren(QLabel)
        ]
        self.assertTrue(any("vector format" in text for text in pdf_notes))
        self.assertTrue(dialog.path_edit.text().endswith(".pdf"))
        self.assertIn("embedded or rasterized", dialog.dpi_hint.text())

        dialog.path_edit.setFocus()
        dialog.path_edit.setText(str(Path(self.directory.name) / "hand.txt"))
        self.assertFalse(dialog.export_button.isEnabled())
        self.assertIn(".pdf", dialog.error_label.text())

    def test_preferences_are_written_only_after_success(self):
        target = Path(self.directory.name) / "ok.png"

        def fail(_request):
            raise RuntimeError("export failed")

        failing = self._dialog(fail)
        failing.path_edit.setText(str(target))
        failing._export()
        failing.close()
        self.assertFalse(target.exists())
        self.assertEqual(self.export_port.commit_calls, 0)
        self.assertEqual(self.export_port.current().format, ExportFormatPreference.PNG)

        dialog = self._dialog()
        dialog.format_combo.setCurrentIndex(dialog.format_combo.findData("jpeg"))
        jpeg_path = Path(self.directory.name) / "ok.jpg"
        dialog.path_edit.setText(str(jpeg_path))
        dialog._export()
        self.assertEqual(len(self.exported), 1)
        self.assertEqual(self.exported[0].format, ExportFormat.JPEG)
        loaded = self.export_port.current()
        self.assertEqual(loaded.format, ExportFormatPreference.JPEG)
        self.assertEqual(loaded.last_directory, str(jpeg_path.parent.resolve()))

    def test_preference_write_failure_keeps_exported_file(self):
        target = Path(self.directory.name) / "kept.png"
        port = MemoryExportPreferences()
        port.fail_commit = True

        def write_ok(request):
            request.path.write_bytes(b"PNG-BYTES")
            self.exported.append(request)

        dialog = self._dialog(write_ok, export_preferences=port)
        dialog.path_edit.setText(str(target))
        with patch.object(status_messages, "show_warning") as warning:
            with patch.object(status_messages, "show_success") as success:
                dialog._export()
        self.assertTrue(target.exists())
        self.assertEqual(target.read_bytes(), b"PNG-BYTES")
        self.assertEqual(len(self.exported), 1)
        self.assertEqual(port.commit_calls, 1)
        self.assertEqual(port.current().format, ExportFormatPreference.PNG)
        warning.assert_called_once()
        self.assertIn("could not be saved", warning.call_args[0][0])
        success.assert_not_called()
        self.settings.sync()
        self.settings.beginGroup("figureExport")
        try:
            stored_version = self.settings.value("version")
        finally:
            self.settings.endGroup()
        self.assertIn(stored_version, (None, "", 0, "0"))

    def test_declined_overwrite_does_not_write(self):
        target = Path(self.directory.name) / "exists.png"
        target.write_bytes(b"original-bytes")
        dialog = self._dialog()
        dialog.path_edit.setText(str(target))
        with patch(
            "mygui.widgets.title_bar.titlebar_dialog.figure_export_dialog.ask_confirmation",
            return_value=False,
        ):
            dialog._export()
        self.assertEqual(target.read_bytes(), b"original-bytes")
        self.assertEqual(self.exported, [])
        self.assertEqual(self.export_port.commit_calls, 0)

    def test_export_port_does_not_write_legacy_figure_export(self):
        target = Path(self.directory.name) / "legacy.png"
        backend = create_settings_backend(settings=self.settings)
        service = ApplicationSettingsService(
            document=backend.application_settings_port()
        )

        def write_ok(request):
            request.path.write_bytes(b"PNG")

        dialog = FigureExportDialog(
            context=self.context,
            color_library=self.library,
            export_preferences=service.export_preferences_port(),
            export_callable=write_ok,
        )
        self.addCleanup(dialog.deleteLater)
        dialog._generated_path = False
        dialog.path_edit.setText(str(target))
        dialog.format_combo.setCurrentIndex(dialog.format_combo.findData("webp"))
        dialog._export()
        self.settings.sync()
        self.settings.beginGroup("figureExport")
        try:
            self.assertIn(self.settings.value("version"), (None, "", 0, "0"))
            self.assertIn(self.settings.value("format"), (None, "", 0, "0"))
        finally:
            self.settings.endGroup()
        self.settings.beginGroup("applicationSettings")
        try:
            self.assertTrue(
                list(self.settings.childKeys()) or list(self.settings.childGroups())
            )
        finally:
            self.settings.endGroup()


class FigureExportExecutionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.window = MainWindow()
        self.canvas = self.window.figure_window.add_figure(
            width=6.4,
            height=4.8,
            dpi=100,
            style="default",
            canva_name="ExportProject",
        )
        create_regular_axes(self.canvas)
        self.app.processEvents()

    def tearDown(self):
        self.window.close()
        self.app.processEvents()
        self.directory.cleanup()

    def _identity(self):
        figure = self.canvas.fig
        stack = self.canvas.repository.undo_stack(self.canvas.project_id)
        return {
            "size": [float(value) for value in figure.get_size_inches()],
            "runtime_dpi": float(figure.dpi),
            "document_dpi": self.canvas.document_dpi,
            "snapshot": self.canvas.component_snapshot(),
            "selection": self.canvas.current_component_id,
            "undo_index": stack.index(),
            "undo_count": stack.count(),
            "project_path": self.canvas.project_path,
            "dirty": self.window.figure_window.is_canvas_dirty(self.canvas),
            "fingerprint": self.window.figure_window._clean_fingerprints.get(
                self.canvas.project_id
            ),
        }

    def _request(self, name, fmt, **option_updates):
        options = replace(FigureExportOptions.defaults(dpi=100), **option_updates)
        return FigureExportRequest(
            path=Path(self.directory.name) / name,
            format=fmt,
            options=options,
        )

    def test_six_formats_write_signatures_and_leave_figure_unchanged(self):
        before = self._identity()
        png = self._request(
            "chart.png",
            ExportFormat.PNG,
            dpi=200,
            metadata={"Title": "Chart", "Author": "MyGUI"},
        )
        self.canvas.export_figure(png)
        png_bytes = png.path.read_bytes()
        self.assertTrue(png_bytes.startswith(b"\x89PNG"))
        self.assertEqual(_png_size(png_bytes), (1280, 960))
        with Image.open(png.path) as image:
            self.assertEqual(image.info.get("Title"), "Chart")
            self.assertEqual(image.info.get("Author"), "MyGUI")

        jpeg = self._request(
            "chart.jpg",
            ExportFormat.JPEG,
            jpeg_quality=40,
            jpeg_subsampling="4:4:4",
        )
        self.canvas.export_figure(jpeg)
        self.assertTrue(jpeg.path.read_bytes().startswith(b"\xff\xd8"))
        with Image.open(jpeg.path) as image:
            self.assertEqual(image.size, (640, 480))

        tiff = self._request(
            "chart.tif",
            ExportFormat.TIFF,
            tiff_compression="lzw",
        )
        self.canvas.export_figure(tiff)
        tiff_bytes = tiff.path.read_bytes()
        self.assertTrue(tiff_bytes[:4] in {b"II*\x00", b"MM\x00*"})
        with Image.open(tiff.path) as image:
            self.assertEqual(image.info.get("compression"), "tiff_lzw")

        webp = self._request(
            "chart.webp",
            ExportFormat.WEBP,
            webp_quality=50,
            webp_method=2,
        )
        self.canvas.export_figure(webp)
        webp_bytes = webp.path.read_bytes()
        self.assertEqual(webp_bytes[:4], b"RIFF")
        self.assertEqual(webp_bytes[8:12], b"WEBP")

        pdf = self._request(
            "chart.pdf",
            ExportFormat.PDF,
            metadata={"Title": "Vector", "Author": "Docs"},
        )
        self.canvas.export_figure(pdf)
        pdf_bytes = pdf.path.read_bytes()
        self.assertTrue(pdf_bytes.startswith(b"%PDF"))
        self.assertIn(b"Vector", pdf_bytes)
        self.assertIn(b"Docs", pdf_bytes)

        svg = self._request(
            "chart.svg",
            ExportFormat.SVG,
            metadata={"Title": "Lines", "Description": "demo"},
        )
        self.canvas.export_figure(svg)
        svg_text = svg.path.read_text(encoding="utf-8")
        self.assertIn("<svg", svg_text)
        self.assertIn("<title>Lines</title>", svg_text)
        self.assertIn("demo", svg_text)
        self.assertEqual(self._identity(), before)
        leftovers = [
            path
            for path in Path(self.directory.name).iterdir()
            if path.suffix == ".tmp" or path.name.startswith(".")
        ]
        self.assertEqual(leftovers, [])

    def test_savefig_and_publish_failures_preserve_original_bytes(self):
        target = Path(self.directory.name) / "keep.png"
        original = b"keep-me"
        target.write_bytes(original)
        request = self._request("keep.png", ExportFormat.PNG)
        before = self._identity()

        with patch.object(self.canvas.fig, "savefig", side_effect=OSError("boom")):
            with self.assertRaises(OSError):
                self.canvas.export_figure(request)
        self.assertEqual(target.read_bytes(), original)

        def write_empty(path, **_kwargs):
            Path(path).write_bytes(b"")

        with patch.object(self.canvas.fig, "savefig", side_effect=write_empty):
            with self.assertRaisesRegex(RuntimeError, "empty"):
                self.canvas.export_figure(request)
        self.assertEqual(target.read_bytes(), original)

        with patch("mygui.figure_export.os.replace", side_effect=OSError("busy")):
            with self.assertRaises(OSError):
                self.canvas.export_figure(request)
        self.assertEqual(target.read_bytes(), original)
        self.assertEqual(self._identity(), before)
        leftovers = [
            path
            for path in Path(self.directory.name).iterdir()
            if path.suffix == ".tmp" or ".keep.png." in path.name
        ]
        self.assertEqual(leftovers, [])

    def test_publish_helper_removes_temp_when_writer_fails(self):
        target = Path(self.directory.name) / "missing.png"

        def writer(_path):
            raise RuntimeError("no write")

        with self.assertRaisesRegex(RuntimeError, "no write"):
            publish_export_file(target, writer)
        self.assertFalse(target.exists())
        leftovers = list(Path(self.directory.name).glob("*.tmp"))
        self.assertEqual(leftovers, [])


class FigureExportDialogControlTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_tight_crop_enables_padding_and_pixel_note(self):
        dialog = FigureExportDialog(
            context=FigureExportContext("Demo", 100.0, 6.4, 4.8),
            color_library=ColorLibrary(),
            export_callable=lambda _request: None,
        )
        self.addCleanup(dialog.deleteLater)
        self.assertFalse(dialog.pad_spin.isEnabled())
        dialog.bbox_tight.setChecked(True)
        self.assertTrue(dialog.pad_numeric.isEnabled())
        self.assertIn("after rendering", dialog.pixel_hint.text())
        dialog.pad_layout.setChecked(True)
        self.assertFalse(dialog.pad_spin.isEnabled())
        self.assertIn("640 × 480 px at 100 DPI", dialog.size_label.text())


class FigureExportOptionsPanelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_export_settings_round_trip_keeps_custom_dpi_strategy(self):
        panel = FigureExportOptionsPanel(
            ColorLibrary(),
            document_dpi=150.0,
            width_inches=6.4,
            height_inches=4.8,
        )
        self.addCleanup(panel.deleteLater)
        original = ExportSettings(
            format=ExportFormatPreference.PDF,
            last_directory=str(Path.cwd()),
            use_project_dpi=True,
            custom_dpi=220.0,
            transparent=True,
            facecolor="#112233",
            edgecolor="auto",
            bbox_inches=ExportBBoxInches.TIGHT,
            pad_inches=PadInchesValue(kind=PadInchesKind.LAYOUT, inches=None),
            png_compress_level=3,
            png_optimize=True,
            jpeg_quality=40,
            jpeg_optimize=True,
            jpeg_progressive=True,
            jpeg_subsampling=JpegSubsampling.FOUR_TWO_ZERO,
            tiff_compression=TiffCompression.LZW,
            webp_lossless=True,
            webp_quality=70,
            webp_alpha_quality=80,
            webp_method=2,
            webp_exact=True,
            metadata=ExportMetadata(fields={"Title": "Chart", "Creator": "MyGUI"}),
        )
        panel.set_export_settings(original)
        loaded = panel.export_settings()
        self.assertEqual(loaded.format, original.format)
        self.assertEqual(loaded.last_directory, original.last_directory)
        self.assertTrue(loaded.use_project_dpi)
        self.assertEqual(loaded.custom_dpi, 220.0)
        self.assertTrue(loaded.transparent)
        self.assertEqual(loaded.facecolor, "#112233")
        self.assertEqual(loaded.edgecolor, "auto")
        self.assertEqual(loaded.bbox_inches, ExportBBoxInches.TIGHT)
        self.assertEqual(loaded.pad_inches.kind, PadInchesKind.LAYOUT)
        self.assertEqual(loaded.png_compress_level, 3)
        self.assertTrue(loaded.png_optimize)
        self.assertEqual(loaded.jpeg_quality, 40)
        self.assertEqual(loaded.jpeg_subsampling, JpegSubsampling.FOUR_TWO_ZERO)
        self.assertEqual(loaded.tiff_compression, TiffCompression.LZW)
        self.assertTrue(loaded.webp_lossless)
        self.assertEqual(loaded.webp_method, 2)
        self.assertEqual(loaded.metadata.fields["Title"], "Chart")
        self.assertEqual(loaded.metadata.fields["Creator"], "MyGUI")
        options = panel.figure_export_options()
        self.assertEqual(options.dpi, 150.0)
        self.assertTrue(options.use_project_dpi)
        self.assertEqual(options.pad_inches, "layout")
        self.assertEqual(options.bbox_inches, "tight")
