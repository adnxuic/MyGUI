"""Unified Axis Tick / Tick Label Inspector dialog."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import replace

from PySide6.QtCore import QSignalBlocker, QTimer, Qt, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QDialogButtonBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from mygui import status_messages
from mygui.application_theme import bind_widget_qss
from mygui.figuremodify.component_services import (
    AxisTickPreviewRenderer,
    AxisTickSettingsDraft,
    TickLevelSettings,
)
from mygui.figuremodify.components import (
    TickGroupController,
    TickLabelGroupController,
)

from ..base import ComponentEditorBase
from ..context import perform_editor_action
from ..inspector import EditorSection
from ..spec_editors import AxisFormatterEditor, AxisLocatorEditor


_DIALOG_QSS = "mygui/widgets/title_bar/titlebar_dialog/dialog_style.qss"
_TICKER_KEYS = (
    "major_locator",
    "major_formatter",
    "minor_locator",
    "minor_formatter",
)
_TICK_COMMON = (
    "primary_visible",
    "secondary_visible",
    "direction",
    "length",
    "width",
    "color",
    "zorder",
)
_LABEL_COMMON = (
    "primary_visible",
    "secondary_visible",
    "color",
    "fontsize",
    "rotation",
    "fontfamily",
    "pad",
    "fontweight",
    "fontstyle",
    "fontstretch",
    "fontvariant",
    "alpha",
    "rotation_mode",
    "horizontalalignment",
    "verticalalignment",
    "multialignment",
    "wrap",
    "linespacing",
    "math_fontfamily",
    "parse_math",
    "usetex",
    "bbox",
    "zorder",
)


class _DraftPropertyForm(ComponentEditorBase):
    """PropertySpec controls backed only by the dialog's temporary draft."""

    draftChanged = Signal()

    def __init__(
        self,
        controller_type,
        properties,
        keys,
        *,
        color_library,
        parent=None,
    ) -> None:
        self._keys = tuple(keys)
        self._draft_values = {
            key: deepcopy(properties[key])
            for key in self._keys
            if key in properties
        }
        self._controller_type = controller_type
        specs = controller_type.property_specs()
        super().__init__(
            None,
            context=None,
            color_library=color_library,
            property_specs=tuple(specs[key] for key in self._keys),
            parent=parent,
        )

    def _state_properties(self):
        return self._draft_values

    def apply_property(self, key: str, value) -> bool:
        old = deepcopy(self._draft_values[key])
        try:
            normalized = self._controller_type.property_specs()[key].normalize(value)
        except Exception:
            self._set_editor_value(key, old)
            self.propertyRejected.emit(key, value)
            self.draftChanged.emit()
            return False
        self._draft_values[key] = deepcopy(normalized)
        self._set_editor_value(key, normalized)
        self.propertyChanged.emit(key, deepcopy(normalized))
        self.draftChanged.emit()
        return True

    def _set_controller_property(self, key: str, value):
        normalized = self._controller_type.property_specs()[key].normalize(value)
        self._draft_values[key] = deepcopy(normalized)
        self.draftChanged.emit()
        return True

    def values(self) -> dict:
        for binding in self._text_bindings.values():
            if not binding.flush():
                raise ValueError("One advanced text value is invalid.")
        return {
            key: deepcopy(self._draft_values[key])
            for key in self._keys
            if key in self._draft_values
        }

    def set_values(self, values) -> None:
        for key in self._keys:
            if key in values:
                self._draft_values[key] = deepcopy(values[key])
        self.sync_from_controller()

    def dispose(self) -> None:
        for binding in self._text_bindings.values():
            binding.cancel()


class _TickLevelPage(QWidget):
    """Controller-free inputs for one major or minor tick level."""

    draftChanged = Signal()

    def __init__(self, level: TickLevelSettings, *, color_library, parent=None):
        super().__init__(parent)
        self._updating = False
        self._table_error: str | None = None
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)

        positions = QGroupBox("Positions", self)
        positions_layout = QVBoxLayout(positions)
        self.locator_editor = AxisLocatorEditor(level.locator, positions)
        positions_layout.addWidget(self.locator_editor)
        self.index_hint = QLabel(
            "Index Locator is intended for regularly spaced index data.",
            positions,
        )
        self.index_hint.setWordWrap(True)
        self.index_hint.setStyleSheet("color: gray; font-style: italic;")
        positions_layout.addWidget(self.index_hint)
        self.fixed_table = QTableWidget(0, 2, positions)
        self.fixed_table.setHorizontalHeaderLabels(("Position", "Label"))
        self.fixed_table.horizontalHeader().setStretchLastSection(True)
        self.fixed_table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        positions_layout.addWidget(self.fixed_table)
        table_buttons = QHBoxLayout()
        self.add_row_button = QPushButton("Add", positions)
        self.remove_row_button = QPushButton("Remove", positions)
        self.move_up_button = QPushButton("Move Up", positions)
        self.move_down_button = QPushButton("Move Down", positions)
        for button in (
            self.add_row_button,
            self.remove_row_button,
            self.move_up_button,
            self.move_down_button,
        ):
            table_buttons.addWidget(button)
        positions_layout.addLayout(table_buttons)
        root.addWidget(positions)

        formatting = QGroupBox("Label Format", self)
        formatting_layout = QVBoxLayout(formatting)
        self.formatter_editor = AxisFormatterEditor(level.formatter, formatting)
        formatting_layout.addWidget(self.formatter_editor)
        root.addWidget(formatting)

        tick_line = QGroupBox("Tick Line", self)
        tick_line_layout = QVBoxLayout(tick_line)
        self.tick_form = _DraftPropertyForm(
            TickGroupController,
            level.tick_properties,
            _TICK_COMMON,
            color_library=color_library,
            parent=tick_line,
        )
        tick_line_layout.addWidget(self.tick_form)
        root.addWidget(tick_line)

        typography = QGroupBox("Typography / Layout", self)
        typography_layout = QVBoxLayout(typography)
        self.label_form = _DraftPropertyForm(
            TickLabelGroupController,
            level.label_properties,
            _LABEL_COMMON,
            color_library=color_library,
            parent=typography,
        )
        typography_layout.addWidget(self.label_form)
        root.addWidget(typography)

        tick_specs = TickGroupController.property_specs()
        label_specs = TickLabelGroupController.property_specs()
        tick_advanced = tuple(key for key in tick_specs if key not in _TICK_COMMON)
        label_advanced = tuple(key for key in label_specs if key not in _LABEL_COMMON)
        self.advanced = QGroupBox("Advanced", self)
        self.advanced.setCheckable(True)
        self.advanced.setChecked(False)
        advanced_layout = QVBoxLayout(self.advanced)
        self.tick_advanced_form = _DraftPropertyForm(
            TickGroupController,
            level.tick_properties,
            tick_advanced,
            color_library=color_library,
            parent=self.advanced,
        )
        self.label_advanced_form = _DraftPropertyForm(
            TickLabelGroupController,
            level.label_properties,
            label_advanced,
            color_library=color_library,
            parent=self.advanced,
        )
        advanced_layout.addWidget(QLabel("Tick Line", self.advanced))
        advanced_layout.addWidget(self.tick_advanced_form)
        advanced_layout.addWidget(QLabel("Tick Label", self.advanced))
        advanced_layout.addWidget(self.label_advanced_form)
        root.addWidget(self.advanced)
        root.addStretch()

        self.locator_editor.valueChanged.connect(self._ticker_changed)
        self.formatter_editor.valueChanged.connect(self._ticker_changed)
        self.fixed_table.itemChanged.connect(self._table_changed)
        self.add_row_button.clicked.connect(self._add_row)
        self.remove_row_button.clicked.connect(self._remove_row)
        self.move_up_button.clicked.connect(lambda: self._move_row(-1))
        self.move_down_button.clicked.connect(lambda: self._move_row(1))
        for form in (
            self.tick_form,
            self.label_form,
            self.tick_advanced_form,
            self.label_advanced_form,
        ):
            form.draftChanged.connect(self.draftChanged)
        self.set_level(level)

    def _ticker_changed(self) -> None:
        if self._updating:
            return
        self._align_fixed_formatter_labels()
        self._sync_table()
        self.draftChanged.emit()

    def _align_fixed_formatter_labels(self) -> None:
        locator = self.locator_editor.value()
        formatter = self.formatter_editor.value()
        if locator["kind"] != "fixed" or formatter["kind"] != "fixed":
            return
        location_count = len(locator["params"]["locations"])
        labels = list(formatter["params"]["labels"])
        aligned = labels[:location_count]
        aligned.extend("" for _ in range(location_count - len(aligned)))
        if aligned != labels:
            formatter["params"]["labels"] = aligned
            self.formatter_editor.set_value(formatter)

    def _sync_table(self) -> None:
        self._table_error = None
        locator = self.locator_editor.value()
        formatter = self.formatter_editor.value()
        fixed_locator = locator["kind"] == "fixed"
        fixed_formatter = formatter["kind"] == "fixed"
        locations = (
            locator["params"]["locations"] if fixed_locator else []
        )
        labels = formatter["params"]["labels"] if fixed_formatter else []
        blocker = QSignalBlocker(self.fixed_table)
        self.fixed_table.setRowCount(len(locations))
        for row, location in enumerate(locations):
            self.fixed_table.setItem(row, 0, QTableWidgetItem(f"{location:g}"))
            label_item = QTableWidgetItem(
                labels[row] if row < len(labels) else ""
            )
            if not fixed_formatter:
                label_item.setFlags(
                    label_item.flags() & ~Qt.ItemFlag.ItemIsEditable
                )
            self.fixed_table.setItem(row, 1, label_item)
        del blocker
        self.fixed_table.setEnabled(fixed_locator)
        self.add_row_button.setEnabled(fixed_locator)
        for button in (
            self.remove_row_button,
            self.move_up_button,
            self.move_down_button,
        ):
            button.setEnabled(fixed_locator and bool(locations))
        self.fixed_table.horizontalHeaderItem(1).setToolTip(
            "Editable only when Label Format uses Fixed Formatter."
        )
        self.index_hint.setVisible(locator["kind"] == "index")

    def _table_changed(self) -> None:
        if self._updating:
            return
        try:
            positions = [
                float(self.fixed_table.item(row, 0).text())
                for row in range(self.fixed_table.rowCount())
            ]
        except (AttributeError, TypeError, ValueError):
            self._table_error = (
                "Fixed tick positions must contain valid numeric values."
            )
            self.draftChanged.emit()
            return
        self._table_error = None
        self._updating = True
        try:
            locator = self.locator_editor.value()
            locator["params"]["locations"] = positions
            self.locator_editor.set_value(locator)
            formatter = self.formatter_editor.value()
            if formatter["kind"] == "fixed":
                formatter["params"]["labels"] = [
                    ""
                    if self.fixed_table.item(row, 1) is None
                    else self.fixed_table.item(row, 1).text()
                    for row in range(self.fixed_table.rowCount())
                ]
                self.formatter_editor.set_value(formatter)
        finally:
            self._updating = False
        self.draftChanged.emit()

    def _add_row(self) -> None:
        row = self.fixed_table.rowCount()
        previous = 0.0
        if row:
            try:
                previous = float(self.fixed_table.item(row - 1, 0).text())
            except (AttributeError, TypeError, ValueError):
                pass
        blocker = QSignalBlocker(self.fixed_table)
        self.fixed_table.insertRow(row)
        self.fixed_table.setItem(row, 0, QTableWidgetItem(f"{previous + 1.0:g}"))
        label = QTableWidgetItem("")
        if self.formatter_editor.value()["kind"] != "fixed":
            label.setFlags(label.flags() & ~Qt.ItemFlag.ItemIsEditable)
        self.fixed_table.setItem(row, 1, label)
        del blocker
        self.fixed_table.selectRow(row)
        self._table_changed()

    def _remove_row(self) -> None:
        row = self.fixed_table.currentRow()
        if row < 0 and self.fixed_table.rowCount():
            row = self.fixed_table.rowCount() - 1
        if row >= 0:
            blocker = QSignalBlocker(self.fixed_table)
            self.fixed_table.removeRow(row)
            del blocker
            self._table_changed()

    def _move_row(self, delta: int) -> None:
        row = self.fixed_table.currentRow()
        target = row + delta
        if row < 0 or target < 0 or target >= self.fixed_table.rowCount():
            return
        values = [
            (
                self.fixed_table.item(index, 0).text(),
                self.fixed_table.item(index, 1).text(),
            )
            for index in range(self.fixed_table.rowCount())
        ]
        values[row], values[target] = values[target], values[row]
        blocker = QSignalBlocker(self.fixed_table)
        for index, (position, label) in enumerate(values):
            self.fixed_table.item(index, 0).setText(position)
            self.fixed_table.item(index, 1).setText(label)
        del blocker
        self.fixed_table.selectRow(target)
        self._table_changed()

    def level(self) -> TickLevelSettings:
        if self._table_error is not None:
            raise ValueError(self._table_error)
        tick = {
            **self.tick_form.values(),
            **self.tick_advanced_form.values(),
        }
        label = {
            **self.label_form.values(),
            **self.label_advanced_form.values(),
        }
        return TickLevelSettings(
            locator=self.locator_editor.value(),
            formatter=self.formatter_editor.value(),
            tick_properties=tick,
            label_properties=label,
        )

    def set_level(self, level: TickLevelSettings) -> None:
        self._updating = True
        try:
            self.locator_editor.set_value(level.locator)
            self.formatter_editor.set_value(level.formatter)
            self.tick_form.set_values(level.tick_properties)
            self.tick_advanced_form.set_values(level.tick_properties)
            self.label_form.set_values(level.label_properties)
            self.label_advanced_form.set_values(level.label_properties)
            self._sync_table()
        finally:
            self._updating = False

    def dispose(self) -> None:
        for form in (
            self.tick_form,
            self.label_form,
            self.tick_advanced_form,
            self.label_advanced_form,
        ):
            form.dispose()


class AxisTickSettingsDialog(QDialog):
    """Edit one Axis tick subtree and commit it as one history command."""

    def __init__(self, opening: AxisTickSettingsDraft, *, context, parent=None):
        super().__init__(parent)
        bind_widget_qss(self, _DIALOG_QSS)
        self.setWindowTitle("Ticks & Labels")
        self.setModal(True)
        self.resize(780, 760)
        self.context = context
        self.service = context.axis_ticks
        self.opening = opening
        self.preview_renderer = AxisTickPreviewRenderer()
        self._disposed = False

        root = QVBoxLayout(self)
        shared = (
            "No shared-axis peers."
            if opening.shared_axis_count == 1
            else f"Ticker settings will synchronize across {opening.shared_axis_count} shared Axes; appearance stays on this Axes."
        )
        self.context_label = QLabel(
            f"{opening.axis.upper()} Axis · scale: {opening.scale['kind']} · "
            f"range: {opening.limits[0]:g} to {opening.limits[1]:g}\n{shared}",
            self,
        )
        self.context_label.setWordWrap(True)
        root.addWidget(self.context_label)

        self.preview_label = QLabel("Rendering preview…", self)
        self.preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_label.setMinimumHeight(180)
        root.addWidget(self.preview_label)
        self.preview_status = QLabel(self)
        self.preview_status.setWordWrap(True)
        self.preview_status.setStyleSheet("color: #b26a00;")
        self.preview_status.hide()
        root.addWidget(self.preview_status)

        self.tabs = QTabWidget(self)
        self.major_page = _TickLevelPage(
            opening.major,
            color_library=context.color_library,
            parent=self.tabs,
        )
        self.minor_page = _TickLevelPage(
            opening.minor,
            color_library=context.color_library,
            parent=self.tabs,
        )
        for title, page in (("Major", self.major_page), ("Minor", self.minor_page)):
            scroll = QScrollArea(self.tabs)
            scroll.setWidgetResizable(True)
            scroll.setWidget(page)
            self.tabs.addTab(scroll, title)
        root.addWidget(self.tabs, 1)

        actions = QHBoxLayout()
        self.copy_to_minor_button = QPushButton("Major → Minor", self)
        self.copy_to_major_button = QPushButton("Minor → Major", self)
        self.restore_button = QPushButton("Restore Opening Snapshot", self)
        self.defaults_button = QPushButton("Scale Defaults", self)
        for button in (
            self.copy_to_minor_button,
            self.copy_to_major_button,
            self.restore_button,
            self.defaults_button,
        ):
            actions.addWidget(button)
        root.addLayout(actions)

        self.error_label = QLabel(self)
        self.error_label.setObjectName("chrome_error_label")
        self.error_label.setWordWrap(True)
        self.error_label.hide()
        root.addWidget(self.error_label)
        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel,
            parent=self,
        )
        root.addWidget(self.buttons)

        self.preview_timer = QTimer(self)
        self.preview_timer.setSingleShot(True)
        self.preview_timer.setInterval(150)
        self.preview_timer.timeout.connect(self._render_preview)
        self.major_page.draftChanged.connect(self._draft_changed)
        self.minor_page.draftChanged.connect(self._draft_changed)
        self.copy_to_minor_button.clicked.connect(
            lambda: self._copy(self.major_page, self.minor_page)
        )
        self.copy_to_major_button.clicked.connect(
            lambda: self._copy(self.minor_page, self.major_page)
        )
        self.restore_button.clicked.connect(self._restore_opening)
        self.defaults_button.clicked.connect(self._restore_scale_defaults)
        self.buttons.accepted.connect(self._accept_settings)
        self.buttons.rejected.connect(self.reject)
        self._draft_changed()

    def current_draft(self) -> AxisTickSettingsDraft:
        return replace(
            self.opening,
            major=self.major_page.level(),
            minor=self.minor_page.level(),
        )

    def _draft_changed(self) -> None:
        try:
            self.service.validate(self.current_draft())
        except Exception as exc:
            self.error_label.setText(str(exc))
            self.error_label.show()
            self.buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(False)
            self.preview_timer.stop()
            return
        self.error_label.hide()
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(True)
        self.preview_timer.start()

    def _render_preview(self) -> None:
        try:
            preview = self.preview_renderer.render(self.current_draft())
            pixmap = QPixmap()
            if not pixmap.loadFromData(preview.png, "PNG"):
                raise ValueError("Preview image could not be decoded.")
            self.preview_label.setPixmap(pixmap)
            self.preview_status.hide()
        except Exception as exc:
            self.preview_status.setText(
                f"Preview was not updated: {exc}"
            )
            self.preview_status.show()

    def _copy(self, source: _TickLevelPage, target: _TickLevelPage) -> None:
        try:
            target.set_level(source.level())
        except Exception as exc:
            self.error_label.setText(str(exc))
            self.error_label.show()
            return
        self._draft_changed()

    def _restore_opening(self) -> None:
        self.major_page.set_level(self.opening.major)
        self.minor_page.set_level(self.opening.minor)
        self._draft_changed()

    def _restore_scale_defaults(self) -> None:
        try:
            defaults = self.service.scale_defaults(self.current_draft())
        except Exception as exc:
            self.error_label.setText(str(exc))
            self.error_label.show()
            return
        self.major_page.set_level(defaults.major)
        self.minor_page.set_level(defaults.minor)
        self._draft_changed()

    def _accept_settings(self) -> None:
        try:
            candidate = self.service.validate(self.current_draft())
        except Exception as exc:
            self.error_label.setText(str(exc))
            self.error_label.show()
            return
        if candidate.major == self.opening.major and candidate.minor == self.opening.minor:
            self.accept()
            return
        result = perform_editor_action(
            self.context,
            f"Change {candidate.axis.upper()} Axis Ticks & Labels",
            lambda: self.service.apply(candidate),
            scan_all=True,
        )
        messages = getattr(self.context, "messages", None)
        if callable(getattr(messages, "present", None)):
            succeeded = messages.present(
                result,
                success=f"{candidate.axis.upper()} axis ticks and labels updated.",
            )
        else:
            succeeded = getattr(result, "ok", False)
            if succeeded:
                status_messages.show_success(
                    getattr(result, "message", "")
                    or f"{candidate.axis.upper()} axis ticks and labels updated."
                )
            else:
                status_messages.show_error(
                    getattr(result, "message", "") or "Tick settings were rejected."
                )
        if not succeeded:
            self.error_label.setText(
                getattr(result, "message", "") or "Tick settings were rejected."
            )
            self.error_label.show()
            return
        self.accept()

    def dispose(self) -> None:
        if self._disposed:
            return
        self._disposed = True
        self.preview_timer.stop()
        self.major_page.dispose()
        self.minor_page.dispose()

    def done(self, result: int) -> None:
        self.dispose()
        super().done(result)


class AxisTickSettingsSection(QWidget, EditorSection):
    """Axis Inspector entry point for unified tick and label editing."""

    PROPERTY_KEYS = _TICKER_KEYS

    def __init__(self, controller, *, context, parent=None):
        super().__init__(parent)
        self.controller = controller
        self.context = context
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.summary_label = QLabel(self)
        self.summary_label.setWordWrap(True)
        self.configure_button = QPushButton("Configure Ticks & Labels…", self)
        self.configure_button.clicked.connect(self.open_dialog)
        layout.addWidget(self.summary_label)
        layout.addWidget(self.configure_button)
        self.sync_from_controller()

    def editor(self, key: str):
        if key not in _TICKER_KEYS:
            raise KeyError(key)
        return self.configure_button

    def sync_from_controller(self) -> None:
        props = self.controller.state.properties
        self.summary_label.setText(
            "Major: "
            f"{props['major_locator']['kind']} / {props['major_formatter']['kind']} · "
            "Minor: "
            f"{props['minor_locator']['kind']} / {props['minor_formatter']['kind']}"
        )
        available = getattr(self.context, "axis_ticks", None) is not None
        self.configure_button.setEnabled(available)
        if not available:
            self.configure_button.setToolTip(
                "Axis tick settings service is unavailable in this context."
            )

    def open_dialog(self) -> bool:
        service = getattr(self.context, "axis_ticks", None)
        if service is None:
            return False
        try:
            opening = service.snapshot(self.controller.component_id)
        except Exception as exc:
            status_messages.show_error(str(exc))
            return False
        dialog = AxisTickSettingsDialog(opening, context=self.context, parent=self)
        try:
            accepted = dialog.exec() == QDialog.DialogCode.Accepted
        finally:
            dialog.deleteLater()
        if accepted:
            self.sync_from_controller()
        return accepted

    def dispose(self) -> None:
        try:
            self.configure_button.clicked.disconnect()
        except (RuntimeError, TypeError):
            pass


__all__ = ["AxisTickSettingsDialog", "AxisTickSettingsSection"]
