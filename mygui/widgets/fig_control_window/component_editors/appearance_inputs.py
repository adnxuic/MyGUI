"""Line, In-Axes, and interpolation creation inputs."""

from __future__ import annotations

from PySide6.QtCore import QByteArray, QSignalBlocker, Qt, Signal
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)
from mygui.database.interpolate_func import (
    DEFAULT_INTERPOLATION_SAMPLES,
    MAX_INTERPOLATION_SAMPLES,
    MIN_INTERPOLATION_SAMPLES,
    interpolate_dict,
    interpolation_uses_lambda,
    interpolation_uses_order,
)
from mygui.widgets.common_widget.min_widget.color_library import ColorLibrary
from mygui.widgets.common_widget.min_widget.py_colorchoice_widgets import (
    ColorChoiceWidget,
)
from mygui.figuremodify.in_axes import (
    ImageInAxesCreateSpec,
    InAxesCreateSpec,
    ZoomInAxesCreateSpec,
    embedded_image_data,
)

from .common import (
    FocusAwareDoubleSpinBox,
    FocusAwareSpinBox,
    LineStyleEditor,
)

class LineAppearanceInput(QFrame):
    """Unbound line appearance input for chart creation dialogs."""

    def __init__(
        self,
        *,
        color_library: ColorLibrary,
        colorselector=None,
        label: str = "",
        style: str = "-",
        linewidth: float = 2.0,
        show_label: bool = True,
        show_style: bool = True,
        show_linewidth: bool = True,
        parent=None,
        color_selection=None,
    ):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.line_style_editor = LineStyleEditor(
            style,
            linewidth,
            show_size=show_linewidth,
            size_label="Line width:",
            parent=self,
        )
        self.style_input = self.line_style_editor.style_combo
        self.linewidth_input = self.line_style_editor.size_input
        self.line_style_editor.setVisible(show_style or show_linewidth)
        self.style_input.setVisible(show_style)
        for label_widget in self.line_style_editor.findChildren(QLabel):
            if label_widget.text() == "Line style:":
                label_widget.setVisible(show_style)
        layout.addWidget(self.line_style_editor)

        self.color_input = ColorChoiceWidget(
            colorselector=colorselector,
            color_library=color_library,
            auto_record_recent=False,
            selection=color_selection,
            parent=self,
        )
        layout.addWidget(QLabel("Color:", self))
        layout.addWidget(self.color_input)

        self.label_widget = QWidget(self)
        label_layout = QVBoxLayout(self.label_widget)
        label_layout.setContentsMargins(0, 0, 0, 0)
        label_layout.addWidget(QLabel("Label:", self.label_widget))
        self.label_input = QLineEdit(str(label), self.label_widget)
        label_layout.addWidget(self.label_input)
        self.label_widget.setVisible(show_label)
        layout.addWidget(self.label_widget)

    def style(self) -> str:
        """Return the selected style."""

        return self.line_style_editor.style()

    def linewidth(self) -> float:
        """Return the linewidth."""

        return self.line_style_editor.size()

    def color(self) -> str:
        """Return the selected color."""

        return self.color_input.color()

    def label(self) -> str:
        """Return the current display label."""

        return self.label_input.text()


class InAxesInput(QFrame):
    """Controller-free combined Zoom/Image inset creation input."""

    IMAGE_FILTER = (
        "Raster images (*.png *.jpg *.jpeg *.bmp *.tif *.tiff);;"
        "All files (*)"
    )

    def __init__(
        self,
        *,
        color_library: ColorLibrary,
        defaults,
        parent=None,
    ):
        super().__init__(parent)
        self._image_data: dict[str, str] | None = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        layout.addWidget(QLabel("Position in parent Axes (normalized):", self))
        bounds_row = QHBoxLayout()
        self.bounds_inputs = []
        for label, value in zip(
            ("X", "Y", "Width", "Height"),
            (0.60, 0.60, 0.35, 0.35), strict=True,
        ):
            bounds_row.addWidget(QLabel(f"{label}:", self))
            editor = FocusAwareDoubleSpinBox(self)
            editor.setRange(-10.0, 10.0)
            editor.setDecimals(4)
            editor.setSingleStep(0.01)
            editor.setValue(value)
            bounds_row.addWidget(editor)
            self.bounds_inputs.append(editor)
        layout.addLayout(bounds_row)

        common_row = QHBoxLayout()
        self.visible_input = QCheckBox("Visible", self)
        self.visible_input.setChecked(True)
        self.frame_input = QCheckBox("Frame", self)
        self.frame_input.setChecked(True)
        self.zorder_input = FocusAwareDoubleSpinBox(self)
        self.zorder_input.setRange(-1e6, 1e6)
        self.zorder_input.setValue(5.0)
        common_row.addWidget(self.visible_input)
        common_row.addWidget(self.frame_input)
        common_row.addWidget(QLabel("Z order:", self))
        common_row.addWidget(self.zorder_input)
        layout.addLayout(common_row)

        frame_row = QHBoxLayout()
        self.facecolor_input = ColorChoiceWidget(
            defaults.facecolor,
            color_library=color_library,
            auto_record_recent=False,
            parent=self,
        )
        self.edgecolor_input = ColorChoiceWidget(
            defaults.edgecolor,
            color_library=color_library,
            auto_record_recent=False,
            parent=self,
        )
        self.linewidth_input = FocusAwareDoubleSpinBox(self)
        self.linewidth_input.setRange(0.0, 1e6)
        self.linewidth_input.setDecimals(3)
        self.linewidth_input.setValue(float(defaults.linewidth))
        frame_row.addWidget(QLabel("Background:", self))
        frame_row.addWidget(self.facecolor_input)
        frame_row.addWidget(QLabel("Border:", self))
        frame_row.addWidget(self.edgecolor_input)
        frame_row.addWidget(QLabel("Width:", self))
        frame_row.addWidget(self.linewidth_input)
        layout.addLayout(frame_row)

        self.mode_tabs = QTabWidget(self)
        self.zoom_page = QWidget(self.mode_tabs)
        self.image_page = QWidget(self.mode_tabs)
        self.mode_tabs.addTab(self.zoom_page, "Zoom")
        self.mode_tabs.addTab(self.image_page, "Image")
        layout.addWidget(self.mode_tabs)
        self._build_zoom_page(defaults, color_library)
        self._build_image_page(defaults)

    @staticmethod
    def _range_row(parent, label: str, values=(0.0, 1.0)):
        row = QHBoxLayout()
        row.addWidget(QLabel(label, parent))
        inputs = []
        for value in values:
            editor = FocusAwareDoubleSpinBox(parent)
            editor.setRange(-1e300, 1e300)
            editor.setDecimals(6)
            editor.setSingleStep(0.1)
            editor.setValue(value)
            row.addWidget(editor)
            inputs.append(editor)
        return row, tuple(inputs)

    def _build_zoom_page(self, defaults, color_library) -> None:
        layout = QVBoxLayout(self.zoom_page)
        x_row, self.xlim_inputs = self._range_row(
            self.zoom_page,
            "X range:",
        )
        y_row, self.ylim_inputs = self._range_row(
            self.zoom_page,
            "Y range:",
        )
        layout.addLayout(x_row)
        layout.addLayout(y_row)
        flags = QHBoxLayout()
        self.ticks_input = QCheckBox("Show ticks", self.zoom_page)
        self.region_input = QCheckBox("Show region", self.zoom_page)
        self.connectors_input = QCheckBox("Show connectors", self.zoom_page)
        for widget in (
            self.ticks_input,
            self.region_input,
            self.connectors_input,
        ):
            widget.setChecked(True)
            flags.addWidget(widget)
        layout.addLayout(flags)
        indicator_row = QHBoxLayout()
        self.indicator_color_input = ColorChoiceWidget(
            defaults.indicator_color,
            color_library=color_library,
            auto_record_recent=False,
            parent=self.zoom_page,
        )
        self.indicator_style_input = LineStyleEditor(
            defaults.indicator_linestyle,
            defaults.indicator_linewidth,
            parent=self.zoom_page,
        )
        self.indicator_alpha_input = FocusAwareDoubleSpinBox(self.zoom_page)
        self.indicator_alpha_input.setRange(0.0, 1.0)
        self.indicator_alpha_input.setSingleStep(0.05)
        self.indicator_alpha_input.setValue(0.5)
        indicator_row.addWidget(QLabel("Indicator:", self.zoom_page))
        indicator_row.addWidget(self.indicator_color_input)
        indicator_row.addWidget(self.indicator_style_input, 1)
        indicator_row.addWidget(QLabel("Opacity:", self.zoom_page))
        indicator_row.addWidget(self.indicator_alpha_input)
        layout.addLayout(indicator_row)

    def _build_image_page(self, defaults) -> None:
        layout = QVBoxLayout(self.image_page)
        source_row = QHBoxLayout()
        self.image_path_input = QLineEdit(self.image_page)
        self.image_path_input.setReadOnly(True)
        self.image_button = QPushButton("Choose image…", self.image_page)
        self.image_button.clicked.connect(self.choose_image)
        source_row.addWidget(self.image_path_input, 1)
        source_row.addWidget(self.image_button)
        layout.addLayout(source_row)
        self.image_preview = QLabel("No image selected", self.image_page)
        self.image_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_preview.setMinimumHeight(120)
        layout.addWidget(self.image_preview)
        display_row = QHBoxLayout()
        self.opacity_input = FocusAwareDoubleSpinBox(self.image_page)
        self.opacity_input.setRange(0.0, 1.0)
        self.opacity_input.setSingleStep(0.05)
        self.opacity_input.setValue(1.0)
        self.fit_mode_input = QComboBox(self.image_page)
        self.fit_mode_input.addItems(("contain", "stretch"))
        self.interpolation_input = QComboBox(self.image_page)
        self.interpolation_input.addItems(("nearest", "bilinear", "bicubic"))
        self.interpolation_input.setCurrentText(defaults.image_interpolation)
        display_row.addWidget(QLabel("Opacity:", self.image_page))
        display_row.addWidget(self.opacity_input)
        display_row.addWidget(QLabel("Fit:", self.image_page))
        display_row.addWidget(self.fit_mode_input)
        display_row.addWidget(QLabel("Interpolation:", self.image_page))
        display_row.addWidget(self.interpolation_input)
        layout.addLayout(display_row)

    def choose_image(self) -> bool:
        """Choose and preflight an embedded raster image."""

        filename, _selected_filter = QFileDialog.getOpenFileName(
            self,
            "Choose inset image",
            "",
            self.IMAGE_FILTER,
        )
        if not filename:
            return False
        try:
            data = embedded_image_data(filename)
            image = QImage.fromData(
                QByteArray.fromBase64(
                    data["payload_base64"].encode("ascii")
                )
            )
            if image.isNull():
                raise ValueError("The selected image could not be previewed.")
        except Exception as exc:
            QMessageBox.warning(self, "Invalid image", str(exc))
            return False
        self._image_data = data
        self.image_path_input.setText(filename)
        pixmap = QPixmap.fromImage(image)
        self.image_preview.setPixmap(
            pixmap.scaled(
                320,
                180,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )
        return True

    def bounds(self) -> tuple[float, float, float, float]:
        """Return normalized parent-Axes bounds."""

        return tuple(float(editor.value()) for editor in self.bounds_inputs)

    def spec(self) -> InAxesCreateSpec:
        """Build the selected mode's immutable creation specification."""

        common = {
            "bounds": self.bounds(),
            "facecolor": self.facecolor_input.color(),
            "edgecolor": self.edgecolor_input.color(),
            "linewidth": float(self.linewidth_input.value()),
            "visible": self.visible_input.isChecked(),
            "zorder": float(self.zorder_input.value()),
            "frameon": self.frame_input.isChecked(),
        }
        if self.mode_tabs.currentWidget() is self.zoom_page:
            return ZoomInAxesCreateSpec(
                xlim=tuple(editor.value() for editor in self.xlim_inputs),
                ylim=tuple(editor.value() for editor in self.ylim_inputs),
                ticks_visible=self.ticks_input.isChecked(),
                region_visible=self.region_input.isChecked(),
                connectors_visible=self.connectors_input.isChecked(),
                indicator_color=self.indicator_color_input.color(),
                indicator_linestyle=self.indicator_style_input.style(),
                indicator_linewidth=self.indicator_style_input.size(),
                indicator_alpha=float(self.indicator_alpha_input.value()),
                **common,
            )
        if self._image_data is None:
            raise ValueError("Choose a PNG, JPEG, BMP, or TIFF image first.")
        return ImageInAxesCreateSpec(
            filename=self._image_data["filename"],
            mime_type=self._image_data["mime_type"],
            payload_base64=self._image_data["payload_base64"],
            opacity=float(self.opacity_input.value()),
            fit_mode=self.fit_mode_input.currentText(),
            interpolation=self.interpolation_input.currentText(),
            **common,
        )


class InterpolationOptionsInput(QFrame):
    """Controller-free interpolation parameters with signal-safe syncing."""

    optionsChanged = Signal()

    def __init__(
        self,
        *,
        method: str | None = None,
        samples: int = DEFAULT_INTERPOLATION_SAMPLES,
        k: int = 3,
        lam: float | None = None,
        lam_auto: bool = True,
        parent=None,
    ):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.method_input = QComboBox(self)
        self.method_input.addItems(interpolate_dict.keys())
        layout.addWidget(QLabel("Interpolation Method:", self))
        layout.addWidget(self.method_input)

        samples_row = QHBoxLayout()
        samples_row.addWidget(QLabel("Samples:", self))
        self.samples_input = FocusAwareSpinBox(self)
        self.samples_input.setRange(
            MIN_INTERPOLATION_SAMPLES,
            MAX_INTERPOLATION_SAMPLES,
        )
        samples_row.addWidget(self.samples_input)
        layout.addLayout(samples_row)

        self.k_widget = QFrame(self)
        k_layout = QHBoxLayout(self.k_widget)
        k_layout.setContentsMargins(0, 0, 0, 0)
        k_layout.addWidget(QLabel("Order k:", self.k_widget))
        self.k_input = FocusAwareSpinBox(self.k_widget)
        self.k_input.setRange(1, 5)
        k_layout.addWidget(self.k_input)
        layout.addWidget(self.k_widget)

        self.lambda_widget = QFrame(self)
        lambda_layout = QVBoxLayout(self.lambda_widget)
        lambda_layout.setContentsMargins(0, 0, 0, 0)
        self.lambda_auto_input = QCheckBox(
            "Auto lambda",
            self.lambda_widget,
        )
        lambda_layout.addWidget(self.lambda_auto_input)
        lambda_row = QHBoxLayout()
        lambda_row.addWidget(QLabel("Lambda:", self.lambda_widget))
        self.lambda_value_input = FocusAwareDoubleSpinBox(self.lambda_widget)
        self.lambda_value_input.setRange(0.0, 1e12)
        self.lambda_value_input.setDecimals(6)
        self.lambda_value_input.setSingleStep(0.1)
        lambda_row.addWidget(self.lambda_value_input)
        lambda_layout.addLayout(lambda_row)
        layout.addWidget(self.lambda_widget)

        self.method_input.currentTextChanged.connect(self._method_changed)
        self.samples_input.valueChanged.connect(self.optionsChanged)
        self.k_input.valueChanged.connect(self.optionsChanged)
        self.lambda_auto_input.toggled.connect(self._lambda_auto_changed)
        self.lambda_value_input.valueChanged.connect(self.optionsChanged)
        self.set_options(
            method=method or next(iter(interpolate_dict)),
            samples=samples,
            k=k,
            lam=lam,
            lam_auto=lam_auto,
        )

    def _method_changed(self, *_args) -> None:
        self.update_option_visibility()
        self.optionsChanged.emit()

    def _lambda_auto_changed(self, checked: bool) -> None:
        self.lambda_value_input.setEnabled(not bool(checked))
        self.optionsChanged.emit()

    def update_option_visibility(self) -> None:
        """Update option visibility."""

        method = self.method()
        self.k_widget.setVisible(interpolation_uses_order(method))
        self.lambda_widget.setVisible(interpolation_uses_lambda(method))

    def method(self) -> str:
        """Return the method."""

        return self.method_input.currentText()

    def lambda_options(self) -> tuple[float | None, bool]:
        """Return the lambda options."""

        if not interpolation_uses_lambda(self.method()):
            return None, True
        if self.lambda_auto_input.isChecked():
            return None, True
        return float(self.lambda_value_input.value()), False

    def options(self) -> dict:
        """Return the options."""

        lam, lam_auto = self.lambda_options()
        return {
            "method": self.method(),
            "samples": int(self.samples_input.value()),
            "k": int(self.k_input.value()),
            "lam": lam,
            "lam_auto": lam_auto,
        }

    def set_options(
        self,
        *,
        method: str,
        samples: int,
        k: int,
        lam: float | None,
        lam_auto: bool,
    ) -> None:
        """Set options."""

        controls = (
            self.method_input,
            self.samples_input,
            self.k_input,
            self.lambda_auto_input,
            self.lambda_value_input,
        )
        blockers = [QSignalBlocker(control) for control in controls]
        self.method_input.setCurrentText(str(method))
        self.samples_input.setValue(int(samples))
        self.k_input.setValue(int(k))
        self.lambda_auto_input.setChecked(bool(lam_auto))
        self.lambda_value_input.setValue(
            1.0 if lam is None else float(lam)
        )
        self.lambda_value_input.setEnabled(not bool(lam_auto))
        self.update_option_visibility()
        del blockers
