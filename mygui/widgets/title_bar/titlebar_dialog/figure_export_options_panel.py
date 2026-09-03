"""Shared Figure export options editor. No Controller or Registry state."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QRadioButton,
    QSpinBox,
    QStackedWidget,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

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
from mygui.figure_export import (
    DEFAULT_PAD_INCHES,
    ExportFormat,
    FigureExportOptions,
    JPEG_SUBSAMPLING_CHOICES,
    TIFF_COMPRESSION_CHOICES,
    options_from_export_settings,
)
from mygui.widgets.common_widget.min_widget.color_library import ColorLibrary
from mygui.widgets.common_widget.min_widget.py_colorchoice_widgets import (
    ColorChoiceWidget,
)
from mygui.widgets.ui_components import UiRole, apply_ui_style

_PANEL_WIDGET_NAMES = (
    "format_combo",
    "use_project_dpi",
    "custom_dpi",
    "dpi_spin",
    "dpi_hint",
    "size_label",
    "pixel_hint",
    "bbox_figure",
    "bbox_tight",
    "pad_numeric",
    "pad_layout",
    "pad_spin",
    "transparent",
    "face_current",
    "face_custom",
    "face_color",
    "edge_current",
    "edge_custom",
    "edge_color",
    "encoding_stack",
    "png_compress",
    "png_optimize",
    "jpeg_quality",
    "jpeg_optimize",
    "jpeg_progressive",
    "jpeg_subsampling",
    "tiff_compression",
    "webp_mode",
    "webp_quality",
    "webp_alpha_quality",
    "webp_method",
    "webp_exact",
    "metadata_stack",
)


class FigureExportOptionsPanel(QWidget):
    """Edit ``ExportSettings`` without Figure Controller or Registry state.

    Public API:
    ``export_settings()`` / ``set_export_settings()``, ``current_format()``,
    ``figure_export_options()`` (binds the current project DPI),
    ``set_document_metrics()``, and ``valuesChanged``.
    """

    valuesChanged = Signal()

    def __init__(
        self,
        color_library: ColorLibrary,
        *,
        document_dpi: float = 100.0,
        width_inches: float = 6.4,
        height_inches: float = 4.8,
        include_format_row: bool = True,
        show_size_preview: bool = True,
        persist_color_library: bool = True,
        show_project_dpi_value: bool = True,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        if color_library is None:
            raise ValueError(
                "FigureExportOptionsPanel requires the shared ColorLibrary."
            )
        self._color_library = color_library
        self._document_dpi = float(document_dpi)
        self._width_inches = float(width_inches)
        self._height_inches = float(height_inches)
        self._last_directory = ""
        self._persist_color_library = bool(persist_color_library)
        self._show_project_dpi_value = bool(show_project_dpi_value)
        self.setObjectName("figure_export_options_panel")

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        self.format_combo = QComboBox()
        self.format_combo.setObjectName("export_format_combo")
        self.format_combo.setAccessibleName("Export format")
        for fmt in ExportFormat:
            self.format_combo.addItem(fmt.display_name, fmt.value)
        if include_format_row:
            root.addWidget(self.format_combo)

        self.tabs = QTabWidget(self)
        self.tabs.setObjectName("export_tabs")
        apply_ui_style(self.tabs, role=UiRole.TABS)
        self.tabs.addTab(self._build_output_page(show_size_preview), "Output")
        self.tabs.addTab(self._build_encoding_page(), "Encoding")
        self.tabs.addTab(self._build_metadata_page(), "Metadata")
        root.addWidget(self.tabs, 1)

        self.format_combo.currentIndexChanged.connect(self._format_changed)
        self.set_export_settings(ExportSettings())
        self._sync_format_pages()
        self.refresh_enabled_state()

    def widget_aliases(self) -> dict[str, QWidget]:
        """Return the historical widget names used by the export dialog tests."""

        return {name: getattr(self, name) for name in _PANEL_WIDGET_NAMES}

    def current_format(self) -> ExportFormat:
        """Return the format combo as the authoritative export format."""

        return ExportFormat(self.format_combo.currentData())

    def set_document_metrics(
        self,
        *,
        document_dpi: float,
        width_inches: float,
        height_inches: float,
    ) -> None:
        """Update the live project size used for DPI binding and the preview."""

        self._document_dpi = float(document_dpi)
        self._width_inches = float(width_inches)
        self._height_inches = float(height_inches)
        self.use_project_dpi.setText(self._project_dpi_label())
        self.refresh_enabled_state()

    def set_last_directory(self, directory: str) -> None:
        """Store the last successful export directory without showing a path editor."""

        self._last_directory = str(directory or "")

    def export_settings(self) -> ExportSettings:
        """Return widget values aligned with ``ExportSettings`` (custom DPI kept)."""

        pad = (
            PadInchesValue(kind=PadInchesKind.LAYOUT, inches=None)
            if self.pad_layout.isChecked()
            else PadInchesValue(
                kind=PadInchesKind.NUMERIC,
                inches=float(self.pad_spin.value()),
            )
        )
        fmt = self.current_format()
        transparent = self.transparent.isChecked() and fmt.supports_transparency
        return ExportSettings(
            format=ExportFormatPreference(fmt.value),
            last_directory=self._last_directory,
            use_project_dpi=self.use_project_dpi.isChecked(),
            custom_dpi=float(self.dpi_spin.value()),
            transparent=transparent,
            facecolor=(
                "auto" if self.face_current.isChecked() else self.face_color.color()
            ),
            edgecolor=(
                "auto" if self.edge_current.isChecked() else self.edge_color.color()
            ),
            bbox_inches=(
                ExportBBoxInches.TIGHT
                if self.bbox_tight.isChecked()
                else ExportBBoxInches.FIGURE
            ),
            pad_inches=pad,
            png_compress_level=int(self.png_compress.value()),
            png_optimize=self.png_optimize.isChecked(),
            jpeg_quality=int(self.jpeg_quality.value()),
            jpeg_optimize=self.jpeg_optimize.isChecked(),
            jpeg_progressive=self.jpeg_progressive.isChecked(),
            jpeg_subsampling=JpegSubsampling(
                str(self.jpeg_subsampling.currentData())
            ),
            tiff_compression=TiffCompression(
                str(self.tiff_compression.currentData())
            ),
            webp_lossless=bool(self.webp_mode.currentData()),
            webp_quality=int(self.webp_quality.value()),
            webp_alpha_quality=int(self.webp_alpha_quality.value()),
            webp_method=int(self.webp_method.value()),
            webp_exact=self.webp_exact.isChecked(),
            metadata=ExportMetadata(fields=self._collect_all_metadata()),
        )

    def set_export_settings(self, settings: ExportSettings) -> None:
        """Apply ``ExportSettings`` without mutating a Figure Controller."""

        self._last_directory = settings.last_directory
        format_blocked = self.format_combo.blockSignals(True)
        try:
            index = self.format_combo.findData(settings.format.value)
            self.format_combo.setCurrentIndex(max(index, 0))
            self.use_project_dpi.setChecked(settings.use_project_dpi)
            self.custom_dpi.setChecked(not settings.use_project_dpi)
            self.dpi_spin.setValue(float(settings.custom_dpi))
            self.bbox_figure.setChecked(
                settings.bbox_inches is ExportBBoxInches.FIGURE
            )
            self.bbox_tight.setChecked(
                settings.bbox_inches is ExportBBoxInches.TIGHT
            )
            layout_pad = settings.pad_inches.kind is PadInchesKind.LAYOUT
            self.pad_layout.setChecked(layout_pad)
            self.pad_numeric.setChecked(not layout_pad)
            if layout_pad:
                self.pad_spin.setValue(DEFAULT_PAD_INCHES)
            else:
                inches = settings.pad_inches.inches
                self.pad_spin.setValue(
                    DEFAULT_PAD_INCHES if inches is None else float(inches)
                )
            self.transparent.setChecked(settings.transparent)
            self.face_current.setChecked(settings.facecolor == "auto")
            self.face_custom.setChecked(settings.facecolor != "auto")
            if settings.facecolor != "auto":
                self.face_color.set_color(settings.facecolor)
            self.edge_current.setChecked(settings.edgecolor == "auto")
            self.edge_custom.setChecked(settings.edgecolor != "auto")
            if settings.edgecolor != "auto":
                self.edge_color.set_color(settings.edgecolor)
            self.png_compress.setValue(settings.png_compress_level)
            self.png_optimize.setChecked(settings.png_optimize)
            self.jpeg_quality.setValue(settings.jpeg_quality)
            self.jpeg_optimize.setChecked(settings.jpeg_optimize)
            self.jpeg_progressive.setChecked(settings.jpeg_progressive)
            jpeg_index = self.jpeg_subsampling.findData(
                settings.jpeg_subsampling.value
            )
            self.jpeg_subsampling.setCurrentIndex(max(jpeg_index, 0))
            tiff_index = self.tiff_compression.findData(
                settings.tiff_compression.value
            )
            self.tiff_compression.setCurrentIndex(max(tiff_index, 0))
            self.webp_mode.setCurrentIndex(1 if settings.webp_lossless else 0)
            self.webp_quality.setValue(settings.webp_quality)
            self.webp_alpha_quality.setValue(settings.webp_alpha_quality)
            self.webp_method.setValue(settings.webp_method)
            self.webp_exact.setChecked(settings.webp_exact)
            for edits in self._metadata_edits.values():
                for edit in edits.values():
                    edit.setText("")
            for key, value in settings.metadata.fields.items():
                for edits in self._metadata_edits.values():
                    if key in edits:
                        edits[key].setText(value)
        finally:
            self.format_combo.blockSignals(format_blocked)
        self._sync_format_pages()
        self.refresh_enabled_state()

    def figure_export_options(self) -> FigureExportOptions:
        """Return savefig options with DPI bound to the current project."""

        return options_from_export_settings(
            self.export_settings(),
            document_dpi=self._document_dpi,
        )

    def effective_dpi(self) -> float:
        """Return the DPI that the next export would send to Matplotlib."""

        if self.use_project_dpi.isChecked():
            return float(self._document_dpi)
        return float(self.dpi_spin.value())

    def refresh_enabled_state(self) -> None:
        """Enable format-dependent controls and refresh the size preview."""

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
        self.face_color.setEnabled(
            colors_enabled and self.face_custom.isChecked()
        )
        self.edge_current.setEnabled(colors_enabled)
        self.edge_custom.setEnabled(colors_enabled)
        self.edge_color.setEnabled(
            colors_enabled and self.edge_custom.isChecked()
        )
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
        dpi = self.effective_dpi()
        width_px = round(self._width_inches * dpi)
        height_px = round(self._height_inches * dpi)
        self.size_label.setText(
            f"{self._width_inches:g} × {self._height_inches:g} in"
            f"  ({self._width_inches * 2.54:.2f} × "
            f"{self._height_inches * 2.54:.2f} cm)"
            f"  ·  {width_px} × {height_px} px at {dpi:g} DPI"
        )
        self.pixel_hint.setText(
            "Final pixel size is determined after rendering when Tight contents is selected."
            if tight
            else ""
        )

    def _emit_changed(self) -> None:
        self.refresh_enabled_state()
        self.valuesChanged.emit()

    def _project_dpi_label(self) -> str:
        if not self._show_project_dpi_value:
            return "Use project DPI"
        return f"Use project DPI ({self._document_dpi:g})"

    def _format_changed(self) -> None:
        self._sync_format_pages()
        self._emit_changed()

    def _sync_format_pages(self) -> None:
        fmt = self.current_format()
        index = list(ExportFormat).index(fmt)
        self.encoding_stack.setCurrentIndex(index)
        self.metadata_stack.setCurrentIndex(index)

    def _collect_all_metadata(self) -> dict[str, str]:
        fields: dict[str, str] = {}
        for edits in self._metadata_edits.values():
            for key, edit in edits.items():
                if edit.text().strip():
                    fields[key] = edit.text()
        return fields

    def _build_output_page(self, show_size_preview: bool) -> QWidget:
        page = QWidget(self)
        layout = QVBoxLayout(page)
        dpi_box = QGroupBox("Resolution", page)
        dpi_layout = QVBoxLayout(dpi_box)
        self.use_project_dpi = QRadioButton(
            self._project_dpi_label(),
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
        self.pixel_hint = QLabel(page)
        self.pixel_hint.setObjectName("export_hint_label")
        self.pixel_hint.setWordWrap(True)
        if show_size_preview:
            layout.addWidget(self.size_label)
            layout.addWidget(self.pixel_hint)
        else:
            self.size_label.hide()
            self.pixel_hint.hide()

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
            auto_record_recent=self._persist_color_library,
            allow_favorite=self._persist_color_library,
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
            auto_record_recent=self._persist_color_library,
            allow_favorite=self._persist_color_library,
        )
        self.edge_color.setObjectName("export_edge_color")
        color_layout.addWidget(self.edge_color)
        layout.addWidget(color_box)
        layout.addStretch(1)

        for widget in (
            self.use_project_dpi,
            self.custom_dpi,
            self.bbox_figure,
            self.bbox_tight,
            self.pad_numeric,
            self.pad_layout,
            self.transparent,
            self.face_current,
            self.face_custom,
            self.edge_current,
            self.edge_custom,
        ):
            widget.toggled.connect(lambda _checked: self._emit_changed())
        self.dpi_spin.valueChanged.connect(lambda _value: self._emit_changed())
        self.pad_spin.valueChanged.connect(lambda _value: self._emit_changed())
        self.face_color.colorChanged.connect(lambda _color: self._emit_changed())
        self.edge_color.colorChanged.connect(lambda _color: self._emit_changed())
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
        self.png_optimize.toggled.connect(lambda _checked: self._emit_changed())
        self.png_compress.valueChanged.connect(lambda _value: self._emit_changed())
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
        self.jpeg_quality.valueChanged.connect(lambda _value: self._emit_changed())
        self.jpeg_optimize.toggled.connect(lambda _checked: self._emit_changed())
        self.jpeg_progressive.toggled.connect(lambda _checked: self._emit_changed())
        self.jpeg_subsampling.currentIndexChanged.connect(
            lambda _index: self._emit_changed()
        )
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
        self.tiff_compression.currentIndexChanged.connect(
            lambda _index: self._emit_changed()
        )
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
        self.webp_mode.currentIndexChanged.connect(lambda _index: self._emit_changed())
        self.webp_quality.valueChanged.connect(lambda _value: self._emit_changed())
        self.webp_alpha_quality.valueChanged.connect(
            lambda _value: self._emit_changed()
        )
        self.webp_method.valueChanged.connect(lambda _value: self._emit_changed())
        self.webp_exact.toggled.connect(lambda _checked: self._emit_changed())
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
        self.metadata_stack.addWidget(self._unsupported_metadata_page("JPEG"))
        self.metadata_stack.addWidget(self._unsupported_metadata_page("TIFF"))
        self.metadata_stack.addWidget(self._unsupported_metadata_page("WebP"))
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
            edit.textChanged.connect(lambda _text: self._emit_changed())
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
