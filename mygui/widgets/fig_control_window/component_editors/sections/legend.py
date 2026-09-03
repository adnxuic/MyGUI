"""Legend location Inspector section."""

from __future__ import annotations


from PySide6.QtCore import QSignalBlocker
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from mygui.figuremodify.components import ComponentKind
from mygui.figuremodify.components.property_values import (
    normalize_legend_location,
)

from ..common import (
    FocusAwareDoubleSpinBox,
    FocusAwareSpinBox,
)
from ..context import perform_editor_action
from ..inspector import EditorSection
from ..inspector_layout import labeled_form_row

class LegendLocationSection(QWidget, EditorSection):
    """Provide the legend location section Qt widget."""

    PRESETS = (
        "best",
        "upper right",
        "upper left",
        "lower left",
        "lower right",
        "right",
        "center left",
        "center right",
        "lower center",
        "upper center",
        "center",
    )

    def __init__(self, controller, *, context, parent=None):
        super().__init__(parent)
        self.controller = controller
        self.context = context
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)

        self.visible_input = QCheckBox("Visible", self)
        self.legend_position_combobox = QComboBox(self)
        self.legend_position_combobox.addItems(self.PRESETS)
        self.legend_position_combobox.addItem("Custom coordinates")
        self.entry_scope_input = QComboBox(self)
        self.entry_scope_input.addItem("This Axes", "axes")
        self.entry_scope_input.addItem("Primary + right Y", "twin_pair")

        row = QHBoxLayout()
        self.legend_x_pos = FocusAwareDoubleSpinBox(self)
        self.legend_y_pos = FocusAwareDoubleSpinBox(self)
        for editor in (self.legend_x_pos, self.legend_y_pos):
            editor.setRange(-1e6, 1e6)
            editor.setDecimals(6)
            editor.setSingleStep(0.01)
        row.addWidget(labeled_form_row("X:", buddy=self.legend_x_pos, parent=self))
        row.addWidget(self.legend_x_pos)
        row.addWidget(labeled_form_row("Y:", buddy=self.legend_y_pos, parent=self))
        row.addWidget(self.legend_y_pos)

        ncols_row = QHBoxLayout()
        self.ncols_input = FocusAwareSpinBox(self)
        self.ncols_input.setRange(1, 1000)
        ncols_row.addWidget(
            labeled_form_row("Columns:", buddy=self.ncols_input, parent=self)
        )
        ncols_row.addWidget(self.ncols_input)

        self.layout.addWidget(self.visible_input)
        self.layout.addWidget(QLabel("Legend entries", self))
        self.layout.addWidget(self.entry_scope_input)
        self.layout.addWidget(self.legend_position_combobox)
        self.layout.addLayout(row)
        self.layout.addLayout(ncols_row)

        self.visible_input.toggled.connect(
            lambda value: self._apply("visible", bool(value))
        )
        self.ncols_input.valueChanged.connect(
            lambda value: self._apply("ncols", int(value))
        )
        self.entry_scope_input.currentIndexChanged.connect(
            lambda _index: self._apply(
                "entry_scope",
                self.entry_scope_input.currentData(),
            )
        )
        self.legend_position_combobox.currentTextChanged.connect(
            self.set_legend_position
        )
        self.legend_x_pos.valueChanged.connect(
            self.set_legend_xy_position
        )
        self.legend_y_pos.valueChanged.connect(
            self.set_legend_xy_position
        )
        self.sync_from_controller()

    def _ensure_target(self) -> None:
        self.context.axes_commands.ensure_legend(
            self.controller.state.parent_id
        )

    def _apply(self, key: str, value):
        self._ensure_target()
        def operation():
            if key == "entry_scope":
                return self.context.axes_layout.set_legend_scope(
                    self.controller.state.parent_id,
                    str(value),
                )
            return self.context.axes_commands.apply_legend_properties(
                self.controller,
                {key: value},
            )

        result = perform_editor_action(self.context,
            f"Change Legend {key.replace('_', ' ').title()}",
            operation,
            merge_key=("property", self.controller.component_id, key),
        )
        if not self.context.messages.present(
            result,
            success="Legend layout updated.",
        ):
            self.sync_from_controller()
            return False
        return True

    def _custom_selected(self) -> bool:
        return (
            self.legend_position_combobox.currentText()
            == "Custom coordinates"
        )

    def set_legend_position(self, *_args):
        """Set legend position."""

        custom = self._custom_selected()
        self.legend_x_pos.setEnabled(custom)
        self.legend_y_pos.setEnabled(custom)
        if custom:
            return self.set_legend_xy_position()
        return self._apply(
            "location",
            self.legend_position_combobox.currentText(),
        )

    def set_legend_xy_position(self, *_args):
        """Set legend xy position."""

        if not self._custom_selected():
            return True
        return self._apply(
            "location",
            (self.legend_x_pos.value(), self.legend_y_pos.value()),
        )

    def sync_from_controller(self) -> None:
        """Refresh controls from authoritative Controller state."""

        properties = self.controller.read_state().properties
        controls = (
            self.visible_input,
            self.legend_position_combobox,
            self.legend_x_pos,
            self.legend_y_pos,
            self.ncols_input,
            self.entry_scope_input,
        )
        blockers = [QSignalBlocker(control) for control in controls]
        try:
            self.visible_input.setChecked(
                bool(properties.get("visible", False))
            )
            self.ncols_input.setValue(int(properties.get("ncols", 1)))
            scope = str(properties.get("entry_scope", "axes"))
            self.entry_scope_input.setCurrentIndex(
                max(0, self.entry_scope_input.findData(scope))
            )
            axes = self.context.registry.get(self.controller.state.parent_id)
            subplot = axes.state.data.get("subplot", {})
            twin_available = False
            if subplot.get("layer") == "primary" and subplot.get("layout_id"):
                twin_available = any(
                    candidate.state.data.get("subplot", {}).get("layout_id")
                    == subplot.get("layout_id")
                    and candidate.state.data.get("subplot", {}).get("row")
                    == subplot.get("row")
                    and candidate.state.data.get("subplot", {}).get("column")
                    == subplot.get("column")
                    and candidate.state.data.get("subplot", {}).get("layer")
                    == "right_y"
                    for candidate in self.context.registry.query(
                        kind=ComponentKind.AXES
                    )
                )
            self.entry_scope_input.setEnabled(twin_available)
            location = normalize_legend_location(
                properties.get(
                    "location",
                    {"kind": "preset", "value": "best"},
                )
            )
            if location["kind"] == "point":
                self.legend_position_combobox.setCurrentText(
                    "Custom coordinates"
                )
                self.legend_x_pos.setValue(float(location["x"]))
                self.legend_y_pos.setValue(float(location["y"]))
                custom = True
            else:
                text = (
                    str(location["value"])
                    if location["kind"] == "preset"
                    else self.PRESETS[int(location["value"])]
                )
                if text not in self.PRESETS:
                    text = "best"
                self.legend_position_combobox.setCurrentText(text)
                custom = False
            self.legend_x_pos.setEnabled(custom)
            self.legend_y_pos.setEnabled(custom)
        finally:
            del blockers
