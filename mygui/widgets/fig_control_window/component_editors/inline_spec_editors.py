"""Inline compound editors for the closed schema-v23 value contracts.

Each editor keeps a complete, already normalized value and emits it as one
``valueChanged`` signal.  Domain validation stays in
``mygui.figuremodify.components.property_values`` so an invalid entry produces
exactly one Controller rejection instead of a second UI validation path.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Iterable

from PySide6.QtCore import QSignalBlocker, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QVBoxLayout,
    QWidget,
)
from mygui.figuremodify.components.property_values import (
    normalize_legend_anchor,
    normalize_line_pattern,
    normalize_marker,
)
from mygui.figuremodify.components.secondary_axis_values import (
    PRESET_UNIT_TRANSFORMS,
    normalize_secondary_axis_placement,
    normalize_unit_transform,
)
from mygui.figuremodify.matplotlib_adapter import available_marker_definitions
from mygui.widgets.common_widget.min_widget.color_library import ColorLibrary
from mygui.widgets.common_widget.min_widget.py_colorchoice_widgets import (
    ColorChoiceWidget,
)

from .common import (
    FocusAwareDoubleSpinBox,
    FocusAwareSpinBox,
    format_number_sequence,
    parse_number_sequence,
)


FONT_WEIGHT_NAMES = (
    "ultralight",
    "light",
    "normal",
    "regular",
    "book",
    "medium",
    "roman",
    "semibold",
    "demibold",
    "demi",
    "bold",
    "heavy",
    "extra bold",
    "black",
)

FONT_STRETCH_NAMES = (
    "ultra-condensed",
    "extra-condensed",
    "condensed",
    "semi-condensed",
    "normal",
    "semi-expanded",
    "expanded",
    "extra-expanded",
    "ultra-expanded",
)

AXES_ANCHOR_CODES = ("C", "NW", "N", "NE", "W", "E", "SW", "S", "SE")

LINE_PATTERN_PRESETS = (
    ("Solid", "-"),
    ("Dashed", "--"),
    ("Dash-dot", "-."),
    ("Dotted", ":"),
    ("None", "None"),
)

_CUSTOM_DASHES = "__custom_dashes__"
_CUSTOM_POINT = "__custom_point__"
DEFAULT_DASHES = (6.0, 2.0)


class InlineValueEditor(QWidget):
    """Base class for inline editors of one complete component value."""

    valueChanged = Signal(object)

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._value: Any = None
        self._syncing = False

    def _inputs(self) -> tuple[QWidget, ...]:
        raise NotImplementedError

    def _normalize(self, value: Any) -> Any:
        return value

    def _read(self) -> Any:
        raise NotImplementedError

    def _write(self, value: Any) -> None:
        raise NotImplementedError

    def value(self) -> Any:
        """Return the current complete value."""

        return deepcopy(self._read())

    def set_value(self, value: Any, *, emit: bool = False) -> None:
        """Synchronize every control from one authoritative value."""

        self._syncing = True
        blockers = [QSignalBlocker(editor) for editor in self._inputs()]
        try:
            self._write(self._normalize(value))
        finally:
            del blockers
            self._syncing = False
        self._value = deepcopy(self._read())
        if emit:
            self.valueChanged.emit(deepcopy(self._value))

    def _emit(self, *_args) -> None:
        if self._syncing:
            return
        self._value = deepcopy(self._read())
        self.valueChanged.emit(deepcopy(self._value))


class LinePatternEditor(InlineValueEditor):
    """Edit a preset or custom dash pattern without exposing raw JSON."""

    def __init__(self, value: Any = None, parent: QWidget | None = None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.kind_input = QComboBox(self)
        for label, item in LINE_PATTERN_PRESETS:
            self.kind_input.addItem(label, item)
        self.kind_input.addItem("Custom dashes", _CUSTOM_DASHES)
        self.offset_label = QLabel("Offset:", self)
        self.offset_input = FocusAwareDoubleSpinBox(self)
        self.offset_input.setRange(-1e6, 1e6)
        self.offset_input.setDecimals(3)
        self.offset_input.setSingleStep(0.5)
        self.dashes_input = QLineEdit(self)
        self.dashes_input.setPlaceholderText("On/off lengths, e.g. 6, 2")
        self.dashes_input.setToolTip(
            "An even number of positive on/off dash lengths in points."
        )
        layout.addWidget(self.kind_input, 1)
        layout.addWidget(self.offset_label)
        layout.addWidget(self.offset_input)
        layout.addWidget(self.dashes_input, 1)
        self.set_value(value if value is not None else {"kind": "preset", "value": "-"})
        self.kind_input.currentIndexChanged.connect(self._kind_changed)
        self.offset_input.valueChanged.connect(self._emit)
        self.dashes_input.editingFinished.connect(self._emit)

    def _inputs(self) -> tuple[QWidget, ...]:
        return (self.kind_input, self.offset_input, self.dashes_input)

    def _normalize(self, value: Any) -> dict[str, Any]:
        if isinstance(value, str):
            value = {"kind": "preset", "value": value}
        elif isinstance(value, (tuple, list)) and len(value) == 2:
            value = {
                "kind": "custom",
                "offset": value[0],
                "dashes": list(value[1]),
            }
        return normalize_line_pattern(value)

    def _custom_selected(self) -> bool:
        return self.kind_input.currentData() == _CUSTOM_DASHES

    def _read(self) -> dict[str, Any]:
        if not self._custom_selected():
            return {"kind": "preset", "value": str(self.kind_input.currentData())}
        return {
            "kind": "custom",
            "offset": float(self.offset_input.value()),
            "dashes": parse_number_sequence(self.dashes_input.text()),
        }

    def _write(self, value: dict[str, Any]) -> None:
        if value["kind"] == "preset":
            index = self.kind_input.findData(value["value"])
            self.kind_input.setCurrentIndex(max(0, index))
        else:
            self.kind_input.setCurrentIndex(
                self.kind_input.findData(_CUSTOM_DASHES)
            )
            self.offset_input.setValue(float(value["offset"]))
            self.dashes_input.setText(format_number_sequence(value["dashes"]))
        self._update_visibility()

    def _update_visibility(self) -> None:
        custom = self._custom_selected()
        self.offset_label.setVisible(custom)
        self.offset_input.setVisible(custom)
        self.dashes_input.setVisible(custom)

    def _kind_changed(self, *_args) -> None:
        if self._custom_selected() and not self.dashes_input.text().strip():
            blocker = QSignalBlocker(self.dashes_input)
            self.dashes_input.setText(format_number_sequence(DEFAULT_DASHES))
            del blocker
        self._update_visibility()
        self._emit()


class MarkerSpecEditor(InlineValueEditor):
    """Edit a named/numbered marker or a regular-polygon marker."""

    POLYGON_STYLES = (("Polygon", 0), ("Star", 1), ("Asterisk", 2))

    def __init__(self, value: Any = None, parent: QWidget | None = None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.symbol_input = QComboBox(self)
        # Matplotlib uses both '4' and 4 as marker keys, so combo item data
        # cannot disambiguate them; keep the exact objects alongside.
        self._symbols: list[Any] = []
        for label, item in self._symbol_choices():
            self._symbols.append(item)
            self.symbol_input.addItem(label)
        self.symbol_input.addItem("Regular polygon")
        self.sides_input = FocusAwareSpinBox(self)
        self.sides_input.setRange(3, 100)
        self.sides_input.setPrefix("Sides ")
        self.style_input = QComboBox(self)
        for label, item in self.POLYGON_STYLES:
            self.style_input.addItem(label, item)
        self.angle_input = FocusAwareDoubleSpinBox(self)
        self.angle_input.setRange(-360.0, 360.0)
        self.angle_input.setDecimals(2)
        self.angle_input.setSuffix("\u00b0")
        layout.addWidget(self.symbol_input, 1)
        layout.addWidget(self.sides_input)
        layout.addWidget(self.style_input)
        layout.addWidget(self.angle_input)
        self.set_value(
            value if value is not None else {"kind": "symbol", "value": "None"}
        )
        self.symbol_input.currentIndexChanged.connect(self._symbol_changed)
        self.sides_input.valueChanged.connect(self._emit)
        self.style_input.currentIndexChanged.connect(self._emit)
        self.angle_input.valueChanged.connect(self._emit)

    @staticmethod
    def _symbol_choices() -> tuple[tuple[str, Any], ...]:
        choices: list[tuple[str, Any]] = [("None", "None")]
        for key, description in available_marker_definitions():
            choices.append((f"{key} \u00b7 {description}", key))
        return tuple(choices)

    def _inputs(self) -> tuple[QWidget, ...]:
        return (
            self.symbol_input,
            self.sides_input,
            self.style_input,
            self.angle_input,
        )

    def _normalize(self, value: Any) -> dict[str, Any]:
        if not isinstance(value, dict):
            if isinstance(value, (tuple, list)) and len(value) == 3:
                value = {
                    "kind": "regular_polygon",
                    "sides": value[0],
                    "style": value[1],
                    "angle": value[2],
                }
            else:
                value = {"kind": "symbol", "value": value}
        return normalize_marker(value)

    def _polygon_selected(self) -> bool:
        return self.symbol_input.currentIndex() >= len(self._symbols)

    def _symbol_index(self, value: Any) -> int:
        for index, item in enumerate(self._symbols):
            if type(item) is type(value) and item == value:
                return index
        return -1

    def _read(self) -> dict[str, Any]:
        if not self._polygon_selected():
            return {
                "kind": "symbol",
                "value": self._symbols[self.symbol_input.currentIndex()],
            }
        return {
            "kind": "regular_polygon",
            "sides": int(self.sides_input.value()),
            "style": int(self.style_input.currentData()),
            "angle": float(self.angle_input.value()),
        }

    def _write(self, value: dict[str, Any]) -> None:
        if value["kind"] == "symbol":
            index = self._symbol_index(value["value"])
            if index < 0:
                self._symbols.insert(0, value["value"])
                self.symbol_input.insertItem(0, str(value["value"]))
                index = 0
            self.symbol_input.setCurrentIndex(index)
        else:
            self.symbol_input.setCurrentIndex(self.symbol_input.count() - 1)
            self.sides_input.setValue(int(value["sides"]))
            self.style_input.setCurrentIndex(
                max(0, self.style_input.findData(int(value["style"])))
            )
            self.angle_input.setValue(float(value["angle"]))
        self._update_visibility()

    def _update_visibility(self) -> None:
        polygon = self._polygon_selected()
        for editor in (self.sides_input, self.style_input, self.angle_input):
            editor.setVisible(polygon)

    def _symbol_changed(self, *_args) -> None:
        self._update_visibility()
        self._emit()


class UnitTransformEditor(InlineValueEditor):
    """Edit preset, affine, or bounded custom unit transforms."""

    _PRESET_LABELS = {
        "identity": "Identity",
        "degrees_to_radians": "Degrees → radians",
        "radians_to_degrees": "Radians → degrees",
        "celsius_to_fahrenheit": "Celsius → Fahrenheit",
        "fahrenheit_to_celsius": "Fahrenheit → Celsius",
        "frequency_to_period": "Frequency ↔ period",
    }

    def __init__(self, value: Any = None, parent: QWidget | None = None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.kind_input = QComboBox(self)
        self.kind_input.addItem("Preset", "preset")
        self.kind_input.addItem("Affine", "affine")
        self.kind_input.addItem("Custom", "custom")
        self.preset_input = QComboBox(self)
        for name in PRESET_UNIT_TRANSFORMS:
            self.preset_input.addItem(self._PRESET_LABELS.get(name, name), name)
        self.scale_input = FocusAwareDoubleSpinBox(self)
        self.scale_input.setRange(-1e12, 1e12)
        self.scale_input.setDecimals(9)
        self.scale_input.setPrefix("Scale ")
        self.offset_input = FocusAwareDoubleSpinBox(self)
        self.offset_input.setRange(-1e12, 1e12)
        self.offset_input.setDecimals(9)
        self.offset_input.setPrefix("Offset ")
        self.forward_input = QLineEdit(self)
        self.forward_input.setPlaceholderText("Forward f(x)")
        self.inverse_input = QLineEdit(self)
        self.inverse_input.setPlaceholderText("Inverse f⁻¹(x)")
        layout.addWidget(self.kind_input)
        layout.addWidget(self.preset_input, 1)
        layout.addWidget(self.scale_input, 1)
        layout.addWidget(self.offset_input, 1)
        layout.addWidget(self.forward_input, 1)
        layout.addWidget(self.inverse_input, 1)
        self.set_value(value or {"kind": "preset", "name": "identity"})
        self.kind_input.currentIndexChanged.connect(self._kind_changed)
        self.preset_input.currentIndexChanged.connect(self._emit)
        self.scale_input.valueChanged.connect(self._emit)
        self.offset_input.valueChanged.connect(self._emit)
        self.forward_input.editingFinished.connect(self._emit)
        self.inverse_input.editingFinished.connect(self._emit)

    def _inputs(self) -> tuple[QWidget, ...]:
        return (
            self.kind_input, self.preset_input, self.scale_input,
            self.offset_input, self.forward_input, self.inverse_input,
        )

    def _normalize(self, value: Any) -> dict[str, Any]:
        return normalize_unit_transform(value)

    def _read(self) -> dict[str, Any]:
        kind = str(self.kind_input.currentData())
        if kind == "preset":
            return {"kind": kind, "name": str(self.preset_input.currentData())}
        if kind == "affine":
            return {
                "kind": kind,
                "scale": float(self.scale_input.value()),
                "offset": float(self.offset_input.value()),
            }
        return {
            "kind": kind,
            "forward": self.forward_input.text().strip(),
            "inverse": self.inverse_input.text().strip(),
        }

    def _write(self, value: dict[str, Any]) -> None:
        self.kind_input.setCurrentIndex(
            max(0, self.kind_input.findData(value["kind"]))
        )
        if value["kind"] == "preset":
            self.preset_input.setCurrentIndex(
                max(0, self.preset_input.findData(value["name"]))
            )
        elif value["kind"] == "affine":
            self.scale_input.setValue(float(value["scale"]))
            self.offset_input.setValue(float(value["offset"]))
        else:
            self.forward_input.setText(value["forward"])
            self.inverse_input.setText(value["inverse"])
        self._update_visibility()

    def _update_visibility(self) -> None:
        kind = self.kind_input.currentData()
        self.preset_input.setVisible(kind == "preset")
        self.scale_input.setVisible(kind == "affine")
        self.offset_input.setVisible(kind == "affine")
        self.forward_input.setVisible(kind == "custom")
        self.inverse_input.setVisible(kind == "custom")

    def _kind_changed(self, *_args) -> None:
        kind = self.kind_input.currentData()
        if kind == "affine" and self.scale_input.value() == 0.0:
            self.scale_input.setValue(1.0)
        if kind == "custom":
            if not self.forward_input.text().strip():
                self.forward_input.setText("x")
            if not self.inverse_input.text().strip():
                self.inverse_input.setText("x")
        self._update_visibility()
        self._emit()


class SecondaryAxisPlacementEditor(InlineValueEditor):
    """Edit edge, Axes-fraction, or data-coordinate placement."""

    def __init__(self, value: Any = None, parent: QWidget | None = None):
        super().__init__(parent)
        self._orientation: str | None = None
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.kind_input = QComboBox(self)
        self.kind_input.addItem("Edge", "edge")
        self.kind_input.addItem("Position", "position")
        self.side_input = QComboBox(self)
        for side in ("top", "bottom", "right", "left"):
            self.side_input.addItem(side.title(), side)
        self.coordinate_input = QComboBox(self)
        self.coordinate_input.addItem("Axes fraction", "axes_fraction")
        self.coordinate_input.addItem("Data coordinate", "data")
        self.value_input = FocusAwareDoubleSpinBox(self)
        self.value_input.setRange(-1e12, 1e12)
        self.value_input.setDecimals(9)
        layout.addWidget(self.kind_input)
        layout.addWidget(self.side_input, 1)
        layout.addWidget(self.coordinate_input, 1)
        layout.addWidget(self.value_input, 1)
        self.set_value(value or {"kind": "edge", "side": "top"})
        self.kind_input.currentIndexChanged.connect(self._kind_changed)
        self.side_input.currentIndexChanged.connect(self._emit)
        self.coordinate_input.currentIndexChanged.connect(self._emit)
        self.value_input.valueChanged.connect(self._emit)

    def _inputs(self) -> tuple[QWidget, ...]:
        return (
            self.kind_input, self.side_input,
            self.coordinate_input, self.value_input,
        )

    def _normalize(self, value: Any) -> dict[str, Any]:
        return normalize_secondary_axis_placement(
            value, orientation=self._orientation
        )

    def set_orientation(self, orientation: str) -> None:
        """Restrict edge choices to one immutable Secondary Axis orientation."""

        if orientation not in {"x", "y"}:
            raise ValueError("Secondary Axis orientation must be x or y.")
        current = self.value()
        allowed = ("top", "bottom") if orientation == "x" else ("right", "left")
        self._orientation = orientation
        blocker = QSignalBlocker(self.side_input)
        self.side_input.clear()
        for side in allowed:
            self.side_input.addItem(side.title(), side)
        del blocker
        if current["kind"] == "edge" and current["side"] not in allowed:
            current = {"kind": "edge", "side": allowed[0]}
        self.set_value(current)

    def _read(self) -> dict[str, Any]:
        kind = str(self.kind_input.currentData() or "edge")
        if kind == "edge":
            side = self.side_input.currentData()
            if not side:
                side = "top" if self._orientation == "x" else "right"
            return {"kind": kind, "side": str(side)}
        coordinate_system = self.coordinate_input.currentData() or "axes_fraction"
        return {
            "kind": kind,
            "coordinate_system": str(coordinate_system),
            "value": float(self.value_input.value()),
        }

    def _write(self, value: dict[str, Any]) -> None:
        self.kind_input.setCurrentIndex(
            max(0, self.kind_input.findData(value["kind"]))
        )
        if value["kind"] == "edge":
            self.side_input.setCurrentIndex(
                max(0, self.side_input.findData(value["side"]))
            )
        else:
            self.coordinate_input.setCurrentIndex(
                max(0, self.coordinate_input.findData(value["coordinate_system"]))
            )
            self.value_input.setValue(float(value["value"]))
        self._update_visibility()

    def _update_visibility(self) -> None:
        edge = self.kind_input.currentData() == "edge"
        self.side_input.setVisible(edge)
        self.coordinate_input.setVisible(not edge)
        self.value_input.setVisible(not edge)

    def _kind_changed(self, *_args) -> None:
        if self.kind_input.currentData() == "edge" and self.side_input.currentIndex() < 0:
            allowed = ("top", "bottom") if self._orientation == "x" else ("right", "left")
            self.side_input.setCurrentIndex(max(0, self.side_input.findData(allowed[0])))
        self._update_visibility()
        self._emit()


class OptionalColorEditor(InlineValueEditor):
    """Edit a color that may be explicitly unset."""

    def __init__(
        self,
        value: Any = None,
        *,
        color_library: ColorLibrary,
        unset_value: Any = None,
        fallback: str = "#000000",
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        if color_library is None:
            raise ValueError(
                "OptionalColorEditor requires the application ColorLibrary."
            )
        self._unset_value = unset_value
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        self.use_value_input = QCheckBox("Set", self)
        self.color_input = ColorChoiceWidget(
            fallback,
            color_library=color_library,
            parent=self,
        )
        layout.addWidget(self.use_value_input)
        layout.addWidget(self.color_input)
        self.set_value(value)
        self.use_value_input.toggled.connect(self._use_value_changed)
        self.color_input.colorChanged.connect(self._emit)

    def _inputs(self) -> tuple[QWidget, ...]:
        return (self.use_value_input, self.color_input)

    @staticmethod
    def _is_unset(value: Any) -> bool:
        if value is None:
            return True
        return isinstance(value, str) and value.strip().casefold() in {
            "",
            "none",
        }

    def _read(self) -> Any:
        if not self.use_value_input.isChecked():
            return deepcopy(self._unset_value)
        return str(self.color_input.color())

    def _write(self, value: Any) -> None:
        enabled = not self._is_unset(value)
        self.use_value_input.setChecked(enabled)
        if enabled:
            self.color_input.set_color(value, emit=False)
        self.color_input.setEnabled(enabled)

    def _use_value_changed(self, checked: bool) -> None:
        self.color_input.setEnabled(bool(checked))
        self._emit()


class NamedNumberEditor(InlineValueEditor):
    """Edit a Matplotlib property that accepts a keyword or a number."""

    def __init__(
        self,
        value: Any = None,
        *,
        names: Iterable[str] = (),
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.value_input = QComboBox(self)
        self.value_input.setEditable(True)
        self.value_input.setInsertPolicy(QComboBox.NoInsert)
        self.value_input.addItems([str(name) for name in names])
        self.value_input.setToolTip(
            "Choose a Matplotlib keyword or type a numeric value."
        )
        layout.addWidget(self.value_input, 1)
        self.set_value(value if value is not None else "normal")
        self.value_input.activated.connect(self._emit)
        self.value_input.lineEdit().editingFinished.connect(self._emit)

    def _inputs(self) -> tuple[QWidget, ...]:
        return (self.value_input,)

    def _read(self) -> Any:
        text = self.value_input.currentText().strip()
        try:
            number = float(text)
        except ValueError:
            return text
        return int(number) if number.is_integer() else number

    def _write(self, value: Any) -> None:
        self.value_input.setCurrentText("" if value is None else str(value))


class LegendAnchorEditor(InlineValueEditor):
    """Edit an unset, point, or four-value legend anchor."""

    KINDS = (("None", "none"), ("Point", "point"), ("Bounds", "bounds"))
    FIELDS = ("x", "y", "width", "height")

    def __init__(self, value: Any = None, parent: QWidget | None = None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.kind_input = QComboBox(self)
        for label, item in self.KINDS:
            self.kind_input.addItem(label, item)
        layout.addWidget(self.kind_input, 1)
        self.field_inputs: dict[str, FocusAwareDoubleSpinBox] = {}
        for name in self.FIELDS:
            editor = FocusAwareDoubleSpinBox(self)
            editor.setRange(-1e6, 1e6)
            editor.setDecimals(4)
            editor.setSingleStep(0.05)
            editor.setPrefix(f"{name[0].upper()} ")
            self.field_inputs[name] = editor
            layout.addWidget(editor)
        self.field_inputs["width"].setValue(1.0)
        self.field_inputs["height"].setValue(1.0)
        self.set_value(value if value is not None else {"kind": "none"})
        self.kind_input.currentIndexChanged.connect(self._kind_changed)
        for editor in self.field_inputs.values():
            editor.valueChanged.connect(self._emit)

    def _inputs(self) -> tuple[QWidget, ...]:
        return (self.kind_input, *self.field_inputs.values())

    def _normalize(self, value: Any) -> dict[str, Any]:
        return normalize_legend_anchor(value)

    def _read(self) -> dict[str, Any]:
        kind = str(self.kind_input.currentData())
        if kind == "none":
            return {"kind": "none"}
        names = ("x", "y") if kind == "point" else self.FIELDS
        result: dict[str, Any] = {"kind": kind}
        for name in names:
            result[name] = float(self.field_inputs[name].value())
        return result

    def _write(self, value: dict[str, Any]) -> None:
        kind = str(value["kind"])
        self.kind_input.setCurrentIndex(max(0, self.kind_input.findData(kind)))
        for name, editor in self.field_inputs.items():
            if name in value:
                editor.setValue(float(value[name]))
        self._update_visibility()

    def _update_visibility(self) -> None:
        kind = str(self.kind_input.currentData())
        visible = {"none": (), "point": ("x", "y"), "bounds": self.FIELDS}[kind]
        for name, editor in self.field_inputs.items():
            editor.setVisible(name in visible)

    def _kind_changed(self, *_args) -> None:
        self._update_visibility()
        self._emit()


class AxesAnchorEditor(InlineValueEditor):
    """Edit a compass anchor code or a normalized anchor point."""

    def __init__(self, value: Any = None, parent: QWidget | None = None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.kind_input = QComboBox(self)
        for code in AXES_ANCHOR_CODES:
            self.kind_input.addItem(code, code)
        self.kind_input.addItem("Custom point", _CUSTOM_POINT)
        self.x_input = FocusAwareDoubleSpinBox(self)
        self.y_input = FocusAwareDoubleSpinBox(self)
        for editor, prefix in ((self.x_input, "X "), (self.y_input, "Y ")):
            editor.setRange(0.0, 1.0)
            editor.setDecimals(4)
            editor.setSingleStep(0.05)
            editor.setPrefix(prefix)
        layout.addWidget(self.kind_input, 1)
        layout.addWidget(self.x_input)
        layout.addWidget(self.y_input)
        self.set_value(value if value is not None else "C")
        self.kind_input.currentIndexChanged.connect(self._kind_changed)
        self.x_input.valueChanged.connect(self._emit)
        self.y_input.valueChanged.connect(self._emit)

    def _inputs(self) -> tuple[QWidget, ...]:
        return (self.kind_input, self.x_input, self.y_input)

    def _custom_selected(self) -> bool:
        return self.kind_input.currentData() == _CUSTOM_POINT

    def _read(self) -> Any:
        if not self._custom_selected():
            return str(self.kind_input.currentData())
        return float(self.x_input.value()), float(self.y_input.value())

    def _write(self, value: Any) -> None:
        if isinstance(value, str):
            index = self.kind_input.findData(value.strip().upper())
            self.kind_input.setCurrentIndex(max(0, index))
        elif isinstance(value, (tuple, list)) and len(value) == 2:
            self.kind_input.setCurrentIndex(
                self.kind_input.findData(_CUSTOM_POINT)
            )
            self.x_input.setValue(float(value[0]))
            self.y_input.setValue(float(value[1]))
        else:
            self.kind_input.setCurrentIndex(0)
        self._update_visibility()

    def _update_visibility(self) -> None:
        custom = self._custom_selected()
        self.x_input.setVisible(custom)
        self.y_input.setVisible(custom)

    def _kind_changed(self, *_args) -> None:
        self._update_visibility()
        self._emit()


class NumberSequenceEditor(InlineValueEditor):
    """Edit a variable-length numeric sequence as readable text."""

    def __init__(
        self,
        value: Any = None,
        *,
        integer: bool = False,
        placeholder: str = "Comma-separated values",
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self._integer = bool(integer)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.value_input = QLineEdit(self)
        self.value_input.setPlaceholderText(placeholder)
        layout.addWidget(self.value_input, 1)
        self.set_value(value if value is not None else ())
        self.value_input.editingFinished.connect(self._emit)

    def _inputs(self) -> tuple[QWidget, ...]:
        return (self.value_input,)

    def _read(self) -> tuple[Any, ...]:
        return tuple(
            parse_number_sequence(
                self.value_input.text(),
                integer=self._integer,
            )
        )

    def _write(self, value: Any) -> None:
        self.value_input.setText(format_number_sequence(value))


class _LineListEdit(QPlainTextEdit):
    """Compact multi-line text input that reports completed edits."""

    editingFinished = Signal()

    def focusOutEvent(self, event) -> None:
        """Report the completed edit after the control loses focus."""

        super().focusOutEvent(event)
        self.editingFinished.emit()


class StringListEditor(InlineValueEditor):
    """Edit an ordered list of strings with one entry per line."""

    def __init__(
        self,
        value: Any = None,
        *,
        placeholder: str = "One value per line",
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.value_input = _LineListEdit(self)
        self.value_input.setPlaceholderText(placeholder)
        self.value_input.setMaximumHeight(72)
        layout.addWidget(self.value_input, 1)
        self.set_value(value if value is not None else ())
        self.value_input.editingFinished.connect(self._emit)

    def _inputs(self) -> tuple[QWidget, ...]:
        return (self.value_input,)

    def _read(self) -> tuple[str, ...]:
        return tuple(
            line.strip()
            for line in self.value_input.toPlainText().splitlines()
            if line.strip()
        )

    def _write(self, value: Any) -> None:
        items = () if value is None else value
        self.value_input.setPlainText(
            "\n".join("" if item is None else str(item) for item in items)
        )

    def set_plain_text(self, text: str) -> None:
        """Replace the visible text without emitting an intermediate value."""

        blocker = QSignalBlocker(self.value_input)
        self.value_input.setPlainText(str(text))
        del blocker


__all__ = [
    "AXES_ANCHOR_CODES",
    "AxesAnchorEditor",
    "FONT_STRETCH_NAMES",
    "FONT_WEIGHT_NAMES",
    "InlineValueEditor",
    "LegendAnchorEditor",
    "LinePatternEditor",
    "MarkerSpecEditor",
    "NamedNumberEditor",
    "NumberSequenceEditor",
    "OptionalColorEditor",
    "SecondaryAxisPlacementEditor",
    "StringListEditor",
    "UnitTransformEditor",
]
