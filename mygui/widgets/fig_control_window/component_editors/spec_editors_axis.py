"""Axis scale, locator, formatter, and Figure layout spec editors."""

from __future__ import annotations

from typing import Any

from mygui.figuremodify.components.property_values import (
    normalize_figure_layout,
    normalize_formatter,
    normalize_locator,
    normalize_scale,
)

from .spec_editor_base import (
    _FORMATTER_FIELDS,
    _LAYOUT_FIELDS,
    _LOCATOR_FIELDS,
    _SCALE_FIELDS,
    _StructuredValueEditor,
    _TaggedSpecDialog,
)

class AxisScaleEditor(_StructuredValueEditor):
    def __init__(self, value: Any, parent=None):
        super().__init__(value, title="axis scale", normalizer=normalize_scale, parent=parent)

    def _dialog(self) -> _TaggedSpecDialog:
        return _TaggedSpecDialog("Axis scale", self.value(), _SCALE_FIELDS, normalize_scale, self)

    def _summary_text(self, value: Any) -> str:
        return str(value["kind"]).replace("_", " ").title()


class AxisLocatorEditor(_StructuredValueEditor):
    def __init__(self, value: Any, parent=None):
        super().__init__(value, title="tick locator", normalizer=normalize_locator, parent=parent)

    def _dialog(self) -> _TaggedSpecDialog:
        return _TaggedSpecDialog("Tick locator", self.value(), _LOCATOR_FIELDS, normalize_locator, self)

    def _summary_text(self, value: Any) -> str:
        names = {"max_n": "Maximum N", "auto_minor": "Automatic minor", "null": "None"}
        return names.get(value["kind"], str(value["kind"]).replace("_", " ").title())


class AxisFormatterEditor(_StructuredValueEditor):
    def __init__(self, value: Any, parent=None):
        super().__init__(value, title="tick formatter", normalizer=normalize_formatter, parent=parent)

    def _dialog(self) -> _TaggedSpecDialog:
        return _TaggedSpecDialog("Tick formatter", self.value(), _FORMATTER_FIELDS, normalize_formatter, self)

    def _summary_text(self, value: Any) -> str:
        names = {
            "format_str": "Percent format",
            "str_method": "String format",
            "log_exponent": "Log exponent",
            "log_mathtext": "Log math text",
            "log_sci": "Log scientific",
            "null": "None",
        }
        return names.get(value["kind"], str(value["kind"]).replace("_", " ").title())


class FigureLayoutEditor(_StructuredValueEditor):
    """Edit the tagged Figure layout engine and its parameters."""

    def __init__(self, value: Any, parent=None):
        super().__init__(
            value,
            title="layout engine",
            normalizer=normalize_figure_layout,
            parent=parent,
        )

    def _dialog(self) -> _TaggedSpecDialog:
        return _TaggedSpecDialog(
            "Layout engine",
            self.value(),
            _LAYOUT_FIELDS,
            normalize_figure_layout,
            self,
        )

    def _summary_text(self, value: Any) -> str:
        names = {"none": "None"}
        kind = str(value["kind"])
        return names.get(kind, kind.title())


