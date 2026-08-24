"""Modal Figure export window shared by the File menu and canvas Save."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import QSettings, Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QSpinBox,
    QStackedWidget,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from mygui import status_messages
from mygui.figure_export import (
    DEFAULT_PAD_INCHES,
    ExportFormat,
    FigureExportContext,
    FigureExportOptions,
    FigureExportPreferences,
    FigureExportRequest,
    JPEG_SUBSAMPLING_CHOICES,
    TIFF_COMPRESSION_CHOICES,
    extension_error,
    load_figure_export_preferences,
    save_figure_export_preferences,
    with_format_extension,
)
from mygui.resources import icon_path, load_qss_resource
from mygui.widgets.common_widget.min_widget.color_library import ColorLibrary
from mygui.widgets.common_widget.min_widget.py_colorchoice_widgets import (
    ColorChoiceWidget,
)


class FigureExportDialog(QDialog):
    """Collect one-shot export options without changing the live Figure."""

    def __init__(
        self,
        *,
        context: FigureExportContext,
        color_library: ColorLibrary,
        settings: QSettings | None = None,
        export_callable: Callable[[FigureExportRequest], None],
        parent=None,
    ):
        super().__init__(parent)
        if color_library is None:
            raise ValueError("FigureExportDialog requires the shared ColorLibrary.")
        if export_callable is None:
            raise ValueError("FigureExportDialog requires an export callable.")
        self._context = context
        self._color_library = color_library
        self._settings = settings
        self._export_callable = export_callable
        self._generated_path = True
        self.setObjectName("figure_export_dialog")
        self.setModal(True)
        self.setWindowTitle("导出当前图片")
        self.setWindowIcon(QIcon(icon_path("save.svg")))
        self.setStyleSheet(
            load_qss_resource(
                "mygui/widgets/title_bar/titlebar_dialog/dialog_style.qss"
            )
        )
        self.resize(640, 620)

        preferences = load_figure_export_preferences(
            settings, document_dpi=context.document_dpi
        )
        self._last_directory = preferences.last_directory

        root = QVBoxLayout(self)
        destination = QHBoxLayout()
        self.path_edit = QLineEdit(self)
        self.path_edit.setObjectName("export_path_edit")
        self.path_edit.setAccessibleName("Export path")
        self.format_combo = QComboBox(self)
        self.format_combo.setObjectName("export_format_combo")
        self.format_combo.setAccessibleName("Export format")
        for fmt in ExportFormat:
            self.format_combo.addItem(fmt.display_name, fmt.value)
        self.browse_button = QPushButton("Browse…", self)
        self.browse_button.setObjectName("export_browse_button")
        destination.addWidget(self.path_edit, 1)
        destination.addWidget(self.format_combo)
        destination.addWidget(self.browse_button)
        root.addLayout(destination)

        self.error_label = QLabel(self)
        self.error_label.setObjectName("export_error_label")
        self.error_label.setWordWrap(True)
        root.addWidget(self.error_label)

        self.tabs = QTabWidget(self)
        self.tabs.setObjectName("export_tabs")
        self.tabs.addTab(self._build_output_page(), "Output")
        self.tabs.addTab(self._build_encoding_page(), "Encoding")
        self.tabs.addTab(self._build_metadata_page(), "Metadata")
        root.addWidget(self.tabs, 1)

        self.summary_label = QLabel(self)
        self.summary_label.setObjectName("export_summary_label")
        self.summary_label.setWordWrap(True)
        root.addWidget(self.summary_label)

        buttons = QHBoxLayout()
        self.restore_button = QPushButton("Restore defaults", self)
        self.restore_button.setObjectName("export_restore_button")
        self.export_button = QPushButton("Export", self)
        self.export_button.setObjectName("export_button")
        self.export_button.setDefault(True)
        self.cancel_button = QPushButton("Cancel", self)
        self.cancel_button.setObjectName("export_cancel_button")
        buttons.addWidget(self.restore_button)
        buttons.addStretch(1)
        buttons.addWidget(self.export_button)
        buttons.addWidget(self.cancel_button)
        root.addLayout(buttons)

        self.path_edit.textChanged.connect(self._path_edited)
        self.format_combo.currentIndexChanged.connect(self._format_changed)
        self.browse_button.clicked.connect(self._browse)
        self.restore_button.clicked.connect(self._restore_defaults)
        self.export_button.clicked.connect(self._export)
        self.cancel_button.clicked.connect(self.reject)
        self._apply_preferences(preferences, generated=True)
        self._sync_format_pages()
        self._refresh_state()

    def current_format(self) -> ExportFormat:
        """Return the format combo as the authoritative export format."""

        return ExportFormat(self.format_combo.currentData())

    def _build_output_page(self) -> QWidget:
        page = QWidget(self)
        layout = QVBoxLayout(page)
        dpi_box = QGroupBox("Resolution", page)
        dpi_layout = QVBoxLayout(dpi_box)
        self.use_project_dpi = QRadioButton(
            f"Use project DPI ({self._context.document_dpi:g})",
            dpi_box,
        )
        self.use_project_dpi.setObjectName("export_use_project_dpi")
        self.custom_dpi = QRadioButton("Custom DPI", dpi_box)
        self.custom_dpi.setObjectName("export_custom_dpi")
        self.dpi_group = QButtonGroup(dpi_box)
        self.dpi_group.addButton(self.use_project_dpi)
        self.dpi_group.addButton(self.custom_dpi)
        self.dpi_spin = QDoubleSpinBox(dpi_box)
        self.dpi_spin.setObjectName("export_dpi_spin")
        self.dpi_spin.setAccessibleName("Custom DPI")
        self.dpi_spin.setRange(1.0, 2400.0)
        self.dpi_spin.setDecimals(1)
        self.dpi_spin.setSingleStep(1.0)
        dpi_row = QHBoxLayout()
        dpi_row.addWidget(self.use_project_dpi)
        dpi_row.addWidget(self.custom_dpi)
        dpi_row.addWidget(self.dpi_spin, 1)
        dpi_layout.addLayout(dpi_row)
        self.dpi_hint = QLabel(dpi_box)
        self.dpi_hint.setObjectName("export_hint_label")
        self.dpi_hint.setWordWrap(True)
        dpi_layout.addWidget(self.dpi_hint)
        layout.addWidget(dpi_box)

        self.size_label = QLabel(page)
        self.size_label.setObjectName("export_size_label")
        self.size_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        layout.addWidget(self.size_label)
        self.pixel_hint = QLabel(page)
        self.pixel_hint.setObjectName("export_hint_label")
        self.pixel_hint.setWordWrap(True)
        layout.addWidget(self.pixel_hint)

        crop_box = QGroupBox("Cropping", page)
        crop_layout = QVBoxLayout(crop_box)
        self.bbox_figure = QRadioButton("Figure bounds", crop_box)
        self.bbox_figure.setObjectName("export_bbox_figure")
        self.bbox_tight = QRadioButton("Tight contents", crop_box)
        self.bbox_tight.setObjectName("export_bbox_tight")
        self.bbox_group = QButtonGroup(crop_box)
        self.bbox_group.addButton(self.bbox_figure)
        self.bbox_group.addButton(self.bbox_tight)
        crop_layout.addWidget(self.bbox_figure)
        crop_layout.addWidget(self.bbox_tight)
        pad_row = QHBoxLayout()
        self.pad_numeric = QRadioButton("Numeric padding (in)", crop_box)
        self.pad_numeric.setObjectName("export_pad_numeric")
        self.pad_layout = QRadioButton("Layout padding", crop_box)
        self.pad_layout.setObjectName("export_pad_layout")
        self.pad_group = QButtonGroup(crop_box)
        self.pad_group.addButton(self.pad_numeric)
        self.pad_group.addButton(self.pad_layout)
        self.pad_spin = QDoubleSpinBox(crop_box)
        self.pad_spin.setObjectName("export_pad_spin")
        self.pad_spin.setRange(0.0, 5.0)
        self.pad_spin.setDecimals(3)
        self.pad_spin.setSingleStep(0.05)
        pad_row.addWidget(self.pad_numeric)
        pad_row.addWidget(self.pad_spin)
        pad_row.addWidget(self.pad_layout)
        crop_layout.addLayout(pad_row)
        layout.addWidget(crop_box)

        color_box = QGroupBox("Background", page)
        color_layout = QVBoxLayout(color_box)
        self.transparent = QCheckBox("Transparent background", color_box)
        self.transparent.setObjectName("export_transparent")
        color_layout.addWidget(self.transparent)
        self.face_current = QRadioButton("Current Figure background", color_box)
        self.face_custom = QRadioButton("Custom background", color_box)
        self.face_group = QButtonGroup(color_box)
        self.face_group.addButton(self.face_current)
        self.face_group.addButton(self.face_custom)
        color_layout.addWidget(self.face_current)
        color_layout.addWidget(self.face_custom)
        self.face_color = ColorChoiceWidget(
            "#FFFFFF",
            color_library=self._color_library,
            parent=color_box,
            auto_record_recent=True,
        )
        self.face_color.setObjectName("export_face_color")
        color_layout.addWidget(self.face_color)
        self.edge_current = QRadioButton("Current Figure border", color_box)
        self.edge_custom = QRadioButton("Custom border", color_box)
        self.edge_group = QButtonGroup(color_box)
        self.edge_group.addButton(self.edge_current)
        self.edge_group.addButton(self.edge_custom)
        color_layout.addWidget(self.edge_current)
        color_layout.addWidget(self.edge_custom)
        self.edge_color = ColorChoiceWidget(
            "#FFFFFF",
            color_library=self._color_library,
            parent=color_box,
            auto_record_recent=True,
        )
        self.edge_color.setObjectName("export_edge_color")
        color_layout.addWidget(self.edge_color)
        layout.addWidget(color_box)
        layout.addStretch(1)

        self.use_project_dpi.toggled.connect(self._refresh_state)
        self.custom_dpi.toggled.connect(self._refresh_state)
        self.dpi_spin.valueChanged.connect(self._refresh_state)
        self.bbox_figure.toggled.connect(self._refresh_state)
        self.bbox_tight.toggled.connect(self._refresh_state)
        self.pad_numeric.toggled.connect(self._refresh_state)
        self.pad_layout.toggled.connect(self._refresh_state)
        self.pad_spin.valueChanged.connect(self._refresh_state)
        self.transparent.toggled.connect(self._refresh_state)
        self.face_current.toggled.connect(self._refresh_state)
        self.face_custom.toggled.connect(self._refresh_state)
        self.edge_current.toggled.connect(self._refresh_state)
        self.edge_custom.toggled.connect(self._refresh_state)
        self.face_color.colorChanged.connect(lambda _color: self._refresh_state())
        self.edge_color.colorChanged.connect(lambda _color: self._refresh_state())
        return page

    def _build_encoding_page(self) -> QWidget:
        page = QWidget(self)
        layout = QVBoxLayout(page)
        self.encoding_stack = QStackedWidget(page)
        self.encoding_stack.setObjectName("export_encoding_stack")
        self.encoding_stack.addWidget(self._png_encoding_page())
        self.encoding_stack.addWidget(self._jpeg_encoding_page())
        self.encoding_stack.addWidget(self._tiff_encoding_page())
        self.encoding_stack.addWidget(self._webp_encoding_page())
        self.encoding_stack.addWidget(self._vector_encoding_page("PDF"))
        self.encoding_stack.addWidget(self._vector_encoding_page("SVG"))
        layout.addWidget(self.encoding_stack)
        layout.addStretch(1)
        return page

    def _png_encoding_page(self) -> QWidget:
        page = QWidget(self)
        form = QFormLayout(page)
        self.png_compress = QSpinBox(page)
        self.png_compress.setObjectName("export_png_compress")
        self.png_compress.setRange(0, 9)
        self.png_optimize = QCheckBox("Optimize", page)
        self.png_optimize.setObjectName("export_png_optimize")
        form.addRow("Compression level", self.png_compress)
        form.addRow(self.png_optimize)
        self.png_optimize.toggled.connect(self._refresh_state)
        self.png_compress.valueChanged.connect(self._refresh_state)
        return page

    def _jpeg_encoding_page(self) -> QWidget:
        page = QWidget(self)
        form = QFormLayout(page)
        self.jpeg_quality = QSpinBox(page)
        self.jpeg_quality.setObjectName("export_jpeg_quality")
        self.jpeg_quality.setRange(0, 95)
        self.jpeg_optimize = QCheckBox("Optimize", page)
        self.jpeg_optimize.setObjectName("export_jpeg_optimize")
        self.jpeg_progressive = QCheckBox("Progressive", page)
        self.jpeg_progressive.setObjectName("export_jpeg_progressive")
        self.jpeg_subsampling = QComboBox(page)
        self.jpeg_subsampling.setObjectName("export_jpeg_subsampling")
        for choice in JPEG_SUBSAMPLING_CHOICES:
            label = "Automatic" if choice == "auto" else choice
            self.jpeg_subsampling.addItem(label, choice)
        form.addRow("Quality", self.jpeg_quality)
        form.addRow(self.jpeg_optimize)
        form.addRow(self.jpeg_progressive)
        form.addRow("Chroma subsampling", self.jpeg_subsampling)
        self.jpeg_quality.valueChanged.connect(self._refresh_state)
        self.jpeg_optimize.toggled.connect(self._refresh_state)
        self.jpeg_progressive.toggled.connect(self._refresh_state)
        self.jpeg_subsampling.currentIndexChanged.connect(self._refresh_state)
        return page

    def _tiff_encoding_page(self) -> QWidget:
        page = QWidget(self)
        form = QFormLayout(page)
        self.tiff_compression = QComboBox(page)
        self.tiff_compression.setObjectName("export_tiff_compression")
        labels = {
            "none": "None",
            "packbits": "PackBits",
            "lzw": "LZW",
            "adobe_deflate": "Adobe Deflate",
        }
        for choice in TIFF_COMPRESSION_CHOICES:
            self.tiff_compression.addItem(labels[choice], choice)
        form.addRow("Compression", self.tiff_compression)
        self.tiff_compression.currentIndexChanged.connect(self._refresh_state)
        return page

    def _webp_encoding_page(self) -> QWidget:
        page = QWidget(self)
        form = QFormLayout(page)
        self.webp_mode = QComboBox(page)
        self.webp_mode.setObjectName("export_webp_mode")
        self.webp_mode.addItem("Lossy", False)
        self.webp_mode.addItem("Lossless", True)
        self.webp_quality = QSpinBox(page)
        self.webp_quality.setObjectName("export_webp_quality")
        self.webp_quality.setRange(0, 100)
        self.webp_alpha_quality = QSpinBox(page)
        self.webp_alpha_quality.setObjectName("export_webp_alpha_quality")
        self.webp_alpha_quality.setRange(0, 100)
        self.webp_method = QSpinBox(page)
        self.webp_method.setObjectName("export_webp_method")
        self.webp_method.setRange(0, 6)
        self.webp_exact = QCheckBox("Exact transparency", page)
        self.webp_exact.setObjectName("export_webp_exact")
        form.addRow("Mode", self.webp_mode)
        form.addRow("Quality", self.webp_quality)
        form.addRow("Alpha quality", self.webp_alpha_quality)
        form.addRow("Method", self.webp_method)
        form.addRow(self.webp_exact)
        self.webp_mode.currentIndexChanged.connect(self._refresh_state)
        self.webp_quality.valueChanged.connect(self._refresh_state)
        self.webp_alpha_quality.valueChanged.connect(self._refresh_state)
        self.webp_method.valueChanged.connect(self._refresh_state)
        self.webp_exact.toggled.connect(self._refresh_state)
        return page

    def _vector_encoding_page(self, name: str) -> QWidget:
        page = QWidget(self)
        layout = QVBoxLayout(page)
        label = QLabel(
            f"{name} is a vector format. Encoding options such as PNG "
            "compression or JPEG quality do not apply. DPI only affects "
            "embedded or rasterized content.",
            page,
        )
        label.setObjectName("export_hint_label")
        label.setWordWrap(True)
        layout.addWidget(label)
        layout.addStretch(1)
        return page

    def _build_metadata_page(self) -> QWidget:
        page = QWidget(self)
        layout = QVBoxLayout(page)
        self.metadata_stack = QStackedWidget(page)
        self.metadata_stack.setObjectName("export_metadata_stack")
        self._metadata_edits: dict[ExportFormat, dict[str, QLineEdit]] = {}
        self.metadata_stack.addWidget(self._metadata_form(ExportFormat.PNG))
        self.metadata_stack.addWidget(
            self._unsupported_metadata_page("JPEG")
        )
        self.metadata_stack.addWidget(
            self._unsupported_metadata_page("TIFF")
        )
        self.metadata_stack.addWidget(
            self._unsupported_metadata_page("WebP")
        )
        self.metadata_stack.addWidget(self._metadata_form(ExportFormat.PDF))
        self.metadata_stack.addWidget(self._metadata_form(ExportFormat.SVG))
        layout.addWidget(self.metadata_stack)
        layout.addStretch(1)
        return page

    def _metadata_form(self, fmt: ExportFormat) -> QWidget:
        page = QWidget(self)
        form = QFormLayout(page)
        edits: dict[str, QLineEdit] = {}
        for key in fmt.metadata_keys:
            edit = QLineEdit(page)
            edit.setObjectName(f"export_metadata_{fmt.value}_{key.lower()}")
            edit.setAccessibleName(f"{fmt.display_name} {key}")
            edit.textChanged.connect(self._refresh_state)
            form.addRow(key, edit)
            edits[key] = edit
        hint = QLabel(
            "Empty fields are omitted so Matplotlib can keep its automatic "
            "date and Creator or Producer values.",
            page,
        )
        hint.setObjectName("export_hint_label")
        hint.setWordWrap(True)
        form.addRow(hint)
        self._metadata_edits[fmt] = edits
        return page

    def _unsupported_metadata_page(self, name: str) -> QWidget:
        page = QWidget(self)
        layout = QVBoxLayout(page)
        label = QLabel(
            f"{name} does not support Matplotlib metadata in 3.9.0.",
            page,
        )
        label.setObjectName("export_hint_label")
        label.setWordWrap(True)
        layout.addWidget(label)
        layout.addStretch(1)
        return page

    def _apply_preferences(
        self,
        preferences: FigureExportPreferences,
        *,
        generated: bool,
    ) -> None:
        options = preferences.options
        self._last_directory = preferences.last_directory
        if generated:
            self._generated_path = True
        format_blocked = self.format_combo.blockSignals(True)
        path_blocked = self.path_edit.blockSignals(True)
        try:
            index = self.format_combo.findData(preferences.format.value)
            self.format_combo.setCurrentIndex(max(index, 0))
            self.use_project_dpi.setChecked(options.use_project_dpi)
            self.custom_dpi.setChecked(not options.use_project_dpi)
            self.dpi_spin.setValue(float(options.dpi))
            self.bbox_figure.setChecked(options.bbox_inches is None)
            self.bbox_tight.setChecked(options.bbox_inches == "tight")
            self.pad_layout.setChecked(options.pad_inches == "layout")
            self.pad_numeric.setChecked(options.pad_inches != "layout")
            if options.pad_inches != "layout":
                self.pad_spin.setValue(float(options.pad_inches))
            else:
                self.pad_spin.setValue(DEFAULT_PAD_INCHES)
            self.transparent.setChecked(options.transparent)
            self.face_current.setChecked(options.facecolor == "auto")
            self.face_custom.setChecked(options.facecolor != "auto")
            if options.facecolor != "auto":
                self.face_color.set_color(options.facecolor)
            self.edge_current.setChecked(options.edgecolor == "auto")
            self.edge_custom.setChecked(options.edgecolor != "auto")
            if options.edgecolor != "auto":
                self.edge_color.set_color(options.edgecolor)
            self.png_compress.setValue(options.png_compress_level)
            self.png_optimize.setChecked(options.png_optimize)
            self.jpeg_quality.setValue(options.jpeg_quality)
            self.jpeg_optimize.setChecked(options.jpeg_optimize)
            self.jpeg_progressive.setChecked(options.jpeg_progressive)
            jpeg_index = self.jpeg_subsampling.findData(options.jpeg_subsampling)
            self.jpeg_subsampling.setCurrentIndex(max(jpeg_index, 0))
            tiff_index = self.tiff_compression.findData(options.tiff_compression)
            self.tiff_compression.setCurrentIndex(max(tiff_index, 0))
            self.webp_mode.setCurrentIndex(1 if options.webp_lossless else 0)
            self.webp_quality.setValue(options.webp_quality)
            self.webp_alpha_quality.setValue(options.webp_alpha_quality)
            self.webp_method.setValue(options.webp_method)
            self.webp_exact.setChecked(options.webp_exact)
            for edits in self._metadata_edits.values():
                for edit in edits.values():
                    edit.setText("")
            for key, value in options.metadata.items():
                for edits in self._metadata_edits.values():
                    if key in edits:
                        edits[key].setText(value)
            if generated:
                self._generated_path = True
                self.path_edit.setText(
                    str(
                        self._context.default_path(
                            preferences.format, self._last_directory
                        )
                    )
                )
        finally:
            self.format_combo.blockSignals(format_blocked)
            self.path_edit.blockSignals(path_blocked)

    def _restore_defaults(self) -> None:
        self._apply_preferences(
            FigureExportPreferences.defaults(dpi=self._context.document_dpi),
            generated=True,
        )
        self._sync_format_pages()
        self._refresh_state()

    def _path_edited(self, _text: str) -> None:
        if self.path_edit.hasFocus():
            self._generated_path = False
        self._refresh_state()

    def _format_changed(self) -> None:
        fmt = self.current_format()
        current = Path(self.path_edit.text().strip() or ".")
        if self._generated_path:
            updated = self._context.default_path(fmt, self._last_directory)
        else:
            updated = with_format_extension(current, fmt)
        blocked = self.path_edit.blockSignals(True)
        self.path_edit.setText(str(updated))
        self.path_edit.blockSignals(blocked)
        self._sync_format_pages()
        self._refresh_state()

    def _browse(self) -> None:
        fmt = self.current_format()
        start = self.path_edit.text().strip() or str(
            self._context.default_path(fmt, self._last_directory)
        )
        patterns = " ".join(f"*{ext}" for ext in fmt.extensions)
        selected, _filter = QFileDialog.getSaveFileName(
            self,
            "导出当前图片",
            start,
            f"{fmt.display_name} ({patterns})",
            options=QFileDialog.Option.DontConfirmOverwrite,
        )
        if not selected:
            return
        self._generated_path = False
        self._last_directory = str(Path(selected).parent)
        self.path_edit.setText(str(with_format_extension(selected, fmt)))
        self._refresh_state()

    def _sync_format_pages(self) -> None:
        fmt = self.current_format()
        index = list(ExportFormat).index(fmt)
        self.encoding_stack.setCurrentIndex(index)
        self.metadata_stack.setCurrentIndex(index)

    def _effective_dpi(self) -> float:
        if self.use_project_dpi.isChecked():
            return float(self._context.document_dpi)
        return float(self.dpi_spin.value())

    def _collect_metadata(self, fmt: ExportFormat) -> dict[str, str]:
        edits = self._metadata_edits.get(fmt, {})
        return {
            key: edit.text()
            for key, edit in edits.items()
            if edit.text().strip()
        }

    def _collect_options(self) -> FigureExportOptions:
        fmt = self.current_format()
        pad: float | str
        if self.pad_layout.isChecked():
            pad = "layout"
        else:
            pad = float(self.pad_spin.value())
        transparent = self.transparent.isChecked() and fmt.supports_transparency
        return FigureExportOptions(
            dpi=self._effective_dpi(),
            use_project_dpi=self.use_project_dpi.isChecked(),
            transparent=transparent,
            facecolor=(
                "auto"
                if self.face_current.isChecked()
                else self.face_color.color()
            ),
            edgecolor=(
                "auto"
                if self.edge_current.isChecked()
                else self.edge_color.color()
            ),
            bbox_inches="tight" if self.bbox_tight.isChecked() else None,
            pad_inches=pad,
            png_compress_level=int(self.png_compress.value()),
            png_optimize=self.png_optimize.isChecked(),
            jpeg_quality=int(self.jpeg_quality.value()),
            jpeg_optimize=self.jpeg_optimize.isChecked(),
            jpeg_progressive=self.jpeg_progressive.isChecked(),
            jpeg_subsampling=str(self.jpeg_subsampling.currentData()),
            tiff_compression=str(self.tiff_compression.currentData()),
            webp_lossless=bool(self.webp_mode.currentData()),
            webp_quality=int(self.webp_quality.value()),
            webp_alpha_quality=int(self.webp_alpha_quality.value()),
            webp_method=int(self.webp_method.value()),
            webp_exact=self.webp_exact.isChecked(),
            metadata=self._collect_metadata(fmt),
        )

    def _build_request(self) -> FigureExportRequest:
        return FigureExportRequest(
            path=Path(self.path_edit.text().strip()),
            format=self.current_format(),
            options=self._collect_options(),
        )

    def _validation_message(self) -> str | None:
        fmt = self.current_format()
        path_error = extension_error(self.path_edit.text().strip(), fmt)
        if path_error:
            return path_error
        try:
            self._build_request()
        except ValueError as exc:
            return str(exc)
        return None

    def _refresh_state(self) -> None:
        fmt = self.current_format()
        jpeg = fmt is ExportFormat.JPEG
        self.transparent.setEnabled(not jpeg)
        if jpeg:
            blocked = self.transparent.blockSignals(True)
            self.transparent.setChecked(False)
            self.transparent.blockSignals(blocked)
        colors_enabled = not self.transparent.isChecked()
        self.face_current.setEnabled(colors_enabled)
        self.face_custom.setEnabled(colors_enabled)
        self.face_color.setEnabled(colors_enabled and self.face_custom.isChecked())
        self.edge_current.setEnabled(colors_enabled)
        self.edge_custom.setEnabled(colors_enabled)
        self.edge_color.setEnabled(colors_enabled and self.edge_custom.isChecked())
        self.dpi_spin.setEnabled(self.custom_dpi.isChecked())
        tight = self.bbox_tight.isChecked()
        self.pad_numeric.setEnabled(tight)
        self.pad_layout.setEnabled(tight)
        self.pad_spin.setEnabled(tight and self.pad_numeric.isChecked())
        self.png_compress.setEnabled(not self.png_optimize.isChecked())
        self.dpi_hint.setText(
            "DPI only affects embedded or rasterized content."
            if fmt.is_vector
            else ""
        )
        dpi = self._effective_dpi()
        width_px, height_px = self._context.nominal_pixels(dpi)
        self.size_label.setText(
            f"{self._context.width_inches:g} × {self._context.height_inches:g} in"
            f"  ({self._context.width_cm:.2f} × {self._context.height_cm:.2f} cm)"
            f"  ·  {width_px} × {height_px} px at {dpi:g} DPI"
        )
        self.pixel_hint.setText(
            "Final pixel size is determined after rendering when Tight contents is selected."
            if tight
            else ""
        )
        error = self._validation_message()
        self.error_label.setText(error or "")
        self.export_button.setEnabled(error is None)
        self.summary_label.setText(self._summary_text(fmt, dpi, tight))

    def _summary_text(self, fmt: ExportFormat, dpi: float, tight: bool) -> str:
        parts = [
            f"{fmt.display_name} at {dpi:g} DPI",
            "transparent" if self.transparent.isChecked() else "opaque",
            "tight crop" if tight else "figure bounds",
        ]
        if fmt is ExportFormat.PNG:
            if self.png_optimize.isChecked():
                parts.append("PNG optimize")
            else:
                parts.append(f"PNG compression {self.png_compress.value()}")
        elif fmt is ExportFormat.JPEG:
            parts.append(f"JPEG quality {self.jpeg_quality.value()}")
        elif fmt is ExportFormat.TIFF:
            parts.append(f"TIFF {self.tiff_compression.currentText()}")
        elif fmt is ExportFormat.WEBP:
            mode = "lossless" if self.webp_mode.currentData() else "lossy"
            parts.append(f"WebP {mode}")
        return " · ".join(parts)

    def _export(self) -> None:
        error = self._validation_message()
        if error:
            self.error_label.setText(error)
            self.export_button.setEnabled(False)
            return
        request = self._build_request()
        if request.path.exists():
            answer = QMessageBox.question(
                self,
                "导出当前图片",
                f"Overwrite existing file?\n{request.path}",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
        try:
            self._export_callable(request)
        except Exception as exc:
            status_messages.show_error(str(exc))
            return
        save_figure_export_preferences(
            self._settings,
            FigureExportPreferences(
                last_directory=str(request.path.parent.resolve()),
                format=request.format,
                options=request.options,
            ),
        )
        status_messages.show_success(f"Figure exported: {request.path.name}")
        self.accept()
