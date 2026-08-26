"""Controller-free input for optional FullProf XRD refinement import."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from mygui.fullprof_prf import FullProfPrfResult, parse_fullprof_prf
from mygui.xrd_refinement import (
    XrdAppearanceConfig,
    XrdPlotAppearance,
    XrdRefinementImportRequest,
    XrdRefinementLegendSelection,
    XrdReflectionAppearance,
    XrdScatterAppearance,
    validate_prf_residual_display_gap,
)
from mygui.widgets.fig_control_window.component_editors.common import (
    ScatterStyleEditor,
)
from mygui.widgets.fig_control_window.component_editors.inputs import (
    LineAppearanceInput,
    ReferenceMarksInput,
)
from mygui.widgets.common_widget.min_widget.py_colorchoice_widgets import (
    ColorChoiceWidget,
)


FULLPROF_PRF_FILTER = "FullProf PRF (*.prf)"


class XrdRefinementInput(QWidget):
    """Parse and validate one transient PRF request without publishing state."""

    validity_changed = Signal(bool, str)

    def __init__(
        self,
        *,
        layout_mode: str = "main_residual",
        reflection_legend_supported: bool = True,
        color_library=None,
        style_defaults=None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        if layout_mode not in {"single", "main_residual"}:
            raise ValueError("XRD input layout_mode must be single or main_residual.")
        self._layout_mode = layout_mode
        self._parsed_result: FullProfPrfResult | None = None
        self._parsed_file = ""
        self._appearance = XrdAppearanceConfig()
        self._color_library = color_library
        self._style_defaults = style_defaults

        root = QVBoxLayout(self)
        self.import_checkbox = QCheckBox(
            "Import XRD refinement result",
            self,
        )
        self.import_checkbox.setObjectName("xrd_refinement_import_enabled")
        root.addWidget(self.import_checkbox)

        self.contents = QWidget(self)
        contents_layout = QVBoxLayout(self.contents)
        contents_layout.setContentsMargins(0, 0, 0, 0)

        file_group = QGroupBox("File", self.contents)
        file_layout = QHBoxLayout(file_group)
        self.file_input = QLineEdit(file_group)
        self.file_input.setObjectName("xrd_refinement_file")
        self.browse_button = QPushButton("Browse...", file_group)
        self.browse_button.setObjectName("xrd_refinement_browse")
        file_layout.addWidget(self.file_input, 1)
        file_layout.addWidget(self.browse_button)
        contents_layout.addWidget(file_group)

        summary_group = QGroupBox("Parsed summary", self.contents)
        summary_layout = QFormLayout(summary_group)
        self.title_value = QLabel("—", summary_group)
        self.chi2_value = QLabel("—", summary_group)
        self.profile_count_value = QLabel("—", summary_group)
        self.reflection_count_value = QLabel("—", summary_group)
        self.range_value = QLabel("—", summary_group)
        for label, value in (
            ("Title", self.title_value),
            ("χ²", self.chi2_value),
            ("Profile points", self.profile_count_value),
            ("Reflections", self.reflection_count_value),
            ("2θ range", self.range_value),
        ):
            summary_layout.addRow(label, value)
        contents_layout.addWidget(summary_group)

        self.draw_residual_checkbox = QCheckBox("Draw residual", self.contents)
        self.draw_residual_checkbox.setObjectName("xrd_refinement_draw_residual")
        self.draw_residual_checkbox.setChecked(True)
        if self._layout_mode == "single":
            contents_layout.addWidget(self.draw_residual_checkbox)
        else:
            self.draw_residual_checkbox.setVisible(False)

        legend_title = "Legend" if self._layout_mode == "single" else "Main legend"
        main_legend = QGroupBox(legend_title, self.contents)
        main_layout = QVBoxLayout(main_legend)
        self.observed_legend = QCheckBox("Observed", main_legend)
        self.calculated_legend = QCheckBox("Calculated", main_legend)
        self.reflection_legend = QCheckBox(
            "Reflection positions",
            main_legend,
        )
        single = self._layout_mode == "single"
        self.observed_legend.setChecked(not single)
        self.calculated_legend.setChecked(not single)
        self.reflection_legend.setChecked(False)
        main_layout.addWidget(self.observed_legend)
        main_layout.addWidget(self.calculated_legend)
        if reflection_legend_supported:
            main_layout.addWidget(self.reflection_legend)
        else:
            self.reflection_legend.setChecked(False)
            self.reflection_legend.setEnabled(False)
            self.reflection_legend.setVisible(False)
        self.residual_legend = QCheckBox("Residual", main_legend)
        self.residual_legend.setChecked(False)
        if single:
            main_layout.addWidget(self.residual_legend)
        contents_layout.addWidget(main_legend)

        residual_legend = QGroupBox("Residual legend", self.contents)
        residual_layout = QVBoxLayout(residual_legend)
        if not single:
            residual_layout.addWidget(self.residual_legend)
            contents_layout.addWidget(residual_legend)
        else:
            residual_legend.setVisible(False)

        property_group = QGroupBox("Component properties", self.contents)
        property_layout = QHBoxLayout(property_group)
        self.observed_property_button = QPushButton("Observed Scatter…", property_group)
        self.calculated_property_button = QPushButton("Calculated Plot…", property_group)
        self.reflection_property_button = QPushButton(
            "Reflection Positions…", property_group
        )
        self.residual_property_button = QPushButton("Residual Plot…", property_group)
        for button in (
            self.observed_property_button,
            self.calculated_property_button,
            self.reflection_property_button,
            self.residual_property_button,
        ):
            property_layout.addWidget(button)
        contents_layout.addWidget(property_group)
        self.observed_property_button.clicked.connect(self._edit_observed_appearance)
        self.calculated_property_button.clicked.connect(
            self._edit_calculated_appearance
        )
        self.reflection_property_button.clicked.connect(
            self._edit_reflection_appearance
        )
        self.residual_property_button.clicked.connect(self._edit_residual_appearance)

        self.validation_label = QLabel(self.contents)
        self.validation_label.setObjectName("xrd_refinement_validation")
        self.validation_label.setWordWrap(True)
        contents_layout.addWidget(self.validation_label)
        contents_layout.addStretch(1)
        root.addWidget(self.contents)

        self.import_checkbox.toggled.connect(self._import_toggled)
        self.browse_button.clicked.connect(self.browse)
        self.file_input.textChanged.connect(self._file_changed)
        self.file_input.editingFinished.connect(self.parse_selected_file)
        self.draw_residual_checkbox.toggled.connect(self._draw_residual_toggled)
        for checkbox in (
            self.observed_legend,
            self.calculated_legend,
            self.reflection_legend,
            self.residual_legend,
        ):
            checkbox.toggled.connect(self.refresh_validation)
        self._import_toggled(False)
        self._sync_residual_controls()

    @staticmethod
    def _path_key(value: str) -> str:
        text = str(value).strip()
        if not text:
            return ""
        return str(Path(text).resolve(strict=False))

    def _clear_summary(self) -> None:
        for value in (
            self.title_value,
            self.chi2_value,
            self.profile_count_value,
            self.reflection_count_value,
            self.range_value,
        ):
            value.setText("—")

    def _show_summary(self, result: FullProfPrfResult) -> None:
        profile = result.profile
        self.title_value.setText(result.metadata.title)
        self.chi2_value.setText(
            "—" if result.metadata.chi2 is None else f"{result.metadata.chi2:g}"
        )
        self.profile_count_value.setText(str(len(profile.two_theta)))
        self.reflection_count_value.setText(str(len(result.reflections)))
        self.range_value.setText(f"{min(profile.two_theta):g} – {max(profile.two_theta):g}°")

    def _sync_residual_controls(self) -> None:
        enabled = self._layout_mode != "single" or self.draw_residual_checkbox.isChecked()
        if not enabled:
            self.residual_legend.setChecked(False)
        self.residual_legend.setEnabled(enabled)
        self.residual_property_button.setEnabled(
            self.import_checkbox.isChecked() and enabled
        )

    def _draw_residual_toggled(self, _enabled: bool) -> None:
        self._sync_residual_controls()
        self.refresh_validation()

    def _import_toggled(self, enabled: bool) -> None:
        self.contents.setEnabled(bool(enabled))
        self._sync_residual_controls()
        if enabled and self.file_input.text().strip() and self._parsed_result is None:
            self.parse_selected_file()
            return
        self.refresh_validation()

    def _file_changed(self, _text: str) -> None:
        if self._path_key(self.file_input.text()) != self._parsed_file:
            self._parsed_result = None
            self._parsed_file = ""
            self._clear_summary()
        self.refresh_validation()

    def browse(self) -> None:
        """Choose and immediately parse one FullProf PRF file."""

        file_name, _selected_filter = QFileDialog.getOpenFileName(
            self,
            "Import XRD refinement result",
            self.file_input.text().strip(),
            FULLPROF_PRF_FILTER,
        )
        if not file_name:
            return
        self.file_input.setText(file_name)
        self.parse_selected_file()

    def set_file_path(self, file_name: str | Path) -> bool:
        """Set and immediately parse a path, primarily for deterministic callers."""

        self.file_input.setText(str(file_name))
        return self.parse_selected_file()

    def parse_selected_file(self) -> bool:
        """Parse the selected file now and publish inline validity."""

        if not self.import_checkbox.isChecked():
            self.refresh_validation()
            return True
        file_name = self.file_input.text().strip()
        if not file_name:
            self._parsed_result = None
            self._parsed_file = ""
            self._clear_summary()
            self.refresh_validation()
            return False
        try:
            result = parse_fullprof_prf(file_name)
        except Exception as exc:
            self._parsed_result = None
            self._parsed_file = ""
            self._clear_summary()
            self.validation_label.setText(str(exc))
            self.validation_label.setVisible(True)
            self.validity_changed.emit(False, str(exc))
            return False
        self._parsed_result = result
        self._parsed_file = self._path_key(file_name)
        self._show_summary(result)
        self.refresh_validation()
        return True

    def refresh_validation(self, *_args) -> tuple[bool, str]:
        """Return validity without parsing for the first time during Create."""

        if not self.import_checkbox.isChecked():
            valid, message = True, ""
        elif not self.file_input.text().strip():
            valid, message = False, "Select a FullProf .prf file."
        elif self._parsed_result is None or self._parsed_file != self._path_key(
            self.file_input.text()
        ):
            valid, message = False, "The selected FullProf .prf file is not valid."
        else:
            valid, message = True, ""
            if (
                self._layout_mode == "single"
                and self.draw_residual_checkbox.isChecked()
                and self._parsed_result is not None
            ):
                try:
                    validate_prf_residual_display_gap(self._parsed_result)
                except ValueError as exc:
                    valid, message = False, str(exc)
        self.validation_label.setText(message)
        self.validation_label.setVisible(not valid)
        self.validity_changed.emit(valid, message)
        return valid, message

    @property
    def parsed_result(self) -> FullProfPrfResult | None:
        """Return the current transient parsed value."""

        return self._parsed_result

    def request(self) -> XrdRefinementImportRequest | None:
        """Return a typed request only when optional import is enabled."""

        if not self.import_checkbox.isChecked():
            return None
        valid, message = self.refresh_validation()
        if not valid or self._parsed_result is None:
            raise ValueError(message or "Select a valid FullProf .prf file.")
        return XrdRefinementImportRequest(
            self._parsed_result,
            XrdRefinementLegendSelection(
                observed=self.observed_legend.isChecked(),
                calculated=self.calculated_legend.isChecked(),
                reflection_positions=self.reflection_legend.isChecked(),
                residual=self.residual_legend.isChecked(),
            ),
            appearance=self._appearance,
            draw_single_residual=(
                True
                if self._layout_mode != "single"
                else self.draw_residual_checkbox.isChecked()
            ),
        )

    def _edit_observed_appearance(self) -> None:
        if self._color_library is None:
            return
        dialog = QDialog(self)
        dialog.setWindowTitle("Observed Scatter")
        layout = QVBoxLayout(dialog)
        current = self._appearance.observed
        marker_editor = ScatterStyleEditor(
            current.marker, current.size, parent=dialog
        )
        color_editor = ColorChoiceWidget(
            current.color,
            color_library=self._color_library,
            auto_record_recent=False,
            parent=dialog,
        )
        layout.addWidget(marker_editor)
        layout.addWidget(QLabel("Color:", dialog))
        layout.addWidget(color_editor)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
            parent=dialog,
        )
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        self._appearance = XrdAppearanceConfig(
            observed=XrdScatterAppearance(
                color=color_editor.color(),
                edgecolor=color_editor.color(),
                marker=marker_editor.marker(),
                size=marker_editor.size(),
                linewidth=current.linewidth,
            ),
            calculated=self._appearance.calculated,
            residual=self._appearance.residual,
            reflection=self._appearance.reflection,
        )

    def _edit_plot_appearance(self, *, residual: bool) -> None:
        if self._color_library is None:
            return
        current = self._appearance.residual if residual else self._appearance.calculated
        title = "Residual Plot" if residual else "Calculated Plot"
        dialog = QDialog(self)
        dialog.setWindowTitle(title)
        layout = QVBoxLayout(dialog)
        editor = LineAppearanceInput(
            color_library=self._color_library,
            label="",
            style=current.linestyle,
            linewidth=current.linewidth,
            show_label=False,
            parent=dialog,
        )
        editor.color_input.set_color(current.color)
        layout.addWidget(editor)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
            parent=dialog,
        )
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        updated = XrdPlotAppearance(
            color=editor.color(),
            linewidth=editor.linewidth(),
            linestyle=editor.style(),
        )
        if residual:
            self._appearance = XrdAppearanceConfig(
                observed=self._appearance.observed,
                calculated=self._appearance.calculated,
                residual=updated,
                reflection=self._appearance.reflection,
            )
        else:
            self._appearance = XrdAppearanceConfig(
                observed=self._appearance.observed,
                calculated=updated,
                residual=self._appearance.residual,
                reflection=self._appearance.reflection,
            )

    def _edit_calculated_appearance(self) -> None:
        self._edit_plot_appearance(residual=False)

    def _edit_residual_appearance(self) -> None:
        self._edit_plot_appearance(residual=True)

    def _edit_reflection_appearance(self) -> None:
        if self._color_library is None:
            return
        defaults = self._style_defaults
        if defaults is None:
            return
        current = self._appearance.reflection
        automatic_baseline = (
            self._layout_mode == "single" and self.draw_residual_checkbox.isChecked()
        )
        dialog = QDialog(self)
        dialog.setWindowTitle("Reflection Positions")
        layout = QVBoxLayout(dialog)
        editor = ReferenceMarksInput(
            color_library=self._color_library,
            defaults=defaults.reference_marks,
            max_baseline_plus_height=None if automatic_baseline else 0.1,
            appearance_only=True,
            automatic_baseline=automatic_baseline,
            parent=dialog,
        )
        editor.label_input.setText(current.label)
        editor.baseline_input.setValue(current.baseline)
        editor.height_input.setValue(current.height)
        if current.color:
            editor.color_input.set_color(current.color)
        if current.linewidth is not None:
            editor.linewidth_input.setValue(current.linewidth)
        layout.addWidget(editor)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
            parent=dialog,
        )
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        try:
            editor.validate_geometry()
        except ValueError:
            return
        properties = editor.properties()
        self._appearance = XrdAppearanceConfig(
            observed=self._appearance.observed,
            calculated=self._appearance.calculated,
            residual=self._appearance.residual,
            reflection=XrdReflectionAppearance(
                label=str(properties["label"]),
                baseline=float(properties["baseline"]),
                height=float(properties["height"]),
                color=str(properties["color"]),
                linewidth=float(properties["linewidth"]),
            ),
        )


__all__ = ["FULLPROF_PRF_FILTER", "XrdRefinementInput"]
