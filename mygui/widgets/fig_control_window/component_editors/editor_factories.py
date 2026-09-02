"""Closed EditorKind to factory mapping for Inspector property controls.

Unknown, duplicate, or missing factories fail at import. ``EditorKind.JSON`` is
an explicit tests/tooling kind, never a silent fallback for an unknown kind.
``EditorKind.AUTO`` is resolved by ``ComponentEditorBase._editor_kind`` before
lookup; the AUTO factory exists so the closed table still covers every enum
member and fails if resolution is skipped.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFontComboBox,
    QWidget,
)

from mygui.figuremodify.components import ComponentValidationError
from mygui.figuremodify.components.models import EditorKind
from mygui.widgets.common_widget.min_widget.py_colorchoice_widgets import (
    ColorChoiceWidget,
)

from .inspector_layout import apply_expanding_field
from .common import (
    FocusAwareDoubleSpinBox,
    FocusAwareSpinBox,
    NullableDoubleEditor,
    NumericTupleEditor,
    SpinePositionEditor,
)
from .inline_spec_editors import (
    FONT_STRETCH_NAMES,
    FONT_WEIGHT_NAMES,
    AxesAnchorEditor,
    LegendAnchorEditor,
    LinePatternEditor,
    MarkerSpecEditor,
    NamedNumberEditor,
    NumberSequenceEditor,
    OptionalColorEditor,
    SecondaryAxisPlacementEditor,
    StringListEditor,
    UnitTransformEditor,
)
from .spec_editors import (
    AnnotationBoxEditor,
    AxisFormatterEditor,
    AxisLocatorEditor,
    AxisScaleEditor,
    ColorMapSpecEditor,
    ContourLabelSpecEditor,
    ContourLevelsSpecEditor,
    ErrorEveryEditor,
    FigureLayoutEditor,
    FontSpecEditor,
    GridEdgeSpecEditor,
    MarkEveryEditor,
    ScatterColorMapEditor,
    ScatterSizeMapEditor,
    TextBoxEditor,
    ZoomConnectorsEditor,
)


EditorFactory = Callable[[Any, str, Any, Any], QWidget]

_NAMED_NUMBER_CHOICES = {
    "fontweight": FONT_WEIGHT_NAMES,
    "fontstretch": FONT_STRETCH_NAMES,
}

_ENUM_DEFAULT_CHOICES: dict[EditorKind, Any] = {
    EditorKind.LINE_STYLE: {
        "Solid": "-",
        "Dashed": "--",
        "Dash-dot": "-.",
        "Dotted": ":",
        "None": "None",
    },
    EditorKind.MARKER: (
        "None",
        "o",
        "s",
        "D",
        "^",
        "v",
        "<",
        ">",
        "x",
        "+",
        "*",
        "P",
        "X",
    ),
    EditorKind.FONT_WEIGHT: (
        "normal",
        "light",
        "medium",
        "semibold",
        "bold",
        "heavy",
    ),
    EditorKind.LEGEND_POSITION: (
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
    ),
}

_TUPLE_LENGTHS = {
    EditorKind.TRIPLET: 3,
    EditorKind.RECTANGLE: 4,
}

_VALUE_SPEC_EDITORS: dict[EditorKind, type] = {
    EditorKind.SCALE_SPEC: AxisScaleEditor,
    EditorKind.LOCATOR_SPEC: AxisLocatorEditor,
    EditorKind.FORMATTER_SPEC: AxisFormatterEditor,
    EditorKind.LAYOUT_SPEC: FigureLayoutEditor,
    EditorKind.MARKEVERY: MarkEveryEditor,
    EditorKind.ERROR_EVERY: ErrorEveryEditor,
    EditorKind.SCATTER_SIZE_MAP: ScatterSizeMapEditor,
    EditorKind.CONTOUR_LEVELS_SPEC: ContourLevelsSpecEditor,
    EditorKind.LINE_PATTERN: LinePatternEditor,
    EditorKind.MARKER_SPEC: MarkerSpecEditor,
    EditorKind.LEGEND_ANCHOR: LegendAnchorEditor,
    EditorKind.AXES_ANCHOR: AxesAnchorEditor,
    EditorKind.UNIT_TRANSFORM_SPEC: UnitTransformEditor,
    EditorKind.SECONDARY_AXIS_PLACEMENT: SecondaryAxisPlacementEditor,
}

_COLOR_SPEC_EDITORS: dict[EditorKind, type] = {
    EditorKind.FONT_SPEC: FontSpecEditor,
    EditorKind.TEXT_BOX: TextBoxEditor,
    EditorKind.ANNOTATION_BOX: AnnotationBoxEditor,
    EditorKind.SCATTER_COLOR_MAP: ScatterColorMapEditor,
    EditorKind.COLOR_MAP_SPEC: ColorMapSpecEditor,
    EditorKind.GRID_EDGE_SPEC: GridEdgeSpecEditor,
    EditorKind.CONTOUR_LABEL_SPEC: ContourLabelSpecEditor,
    EditorKind.CONNECTORS: ZoomConnectorsEditor,
}


def _metadata(spec: Any, *names: str, default=None):
    from .base import _metadata as impl

    return impl(spec, *names, default=default)


def _metadata_default(spec: Any, *names: str, default):
    from .base import _metadata_default as impl

    return impl(spec, *names, default=default)


def _enum_text(value: Any) -> str:
    from .base import _enum_text as impl

    return impl(value)


def _allow_none(spec: Any) -> bool:
    return bool(_metadata(spec, "allow_none", default=False))


def _connect_value(host: Any, editor: Any, key: str) -> Any:
    editor.valueChanged.connect(
        lambda candidate, property_key=key: host.apply_property(
            property_key,
            candidate,
        )
    )
    return editor


def _create_auto_editor(host: Any, key: str, spec: Any, value: Any) -> QWidget:
    del host, spec, value
    raise RuntimeError(
        f"Property {key!r} cannot create an AUTO editor after kind resolution."
    )


def _create_bool_editor(host: Any, key: str, spec: Any, value: Any) -> QWidget:
    del spec
    editor = QCheckBox(host)
    editor.setChecked(bool(value))
    editor.toggled.connect(
        lambda candidate, property_key=key: host.apply_property(
            property_key,
            candidate,
        )
    )
    return editor


def _create_int_editor(host: Any, key: str, spec: Any, value: Any) -> QWidget:
    editor = FocusAwareSpinBox(host)
    minimum, maximum = host._bounds(spec, integer=True)
    editor.setRange(int(minimum), int(maximum))
    editor.setSingleStep(int(_metadata_default(spec, "step", "single_step", default=1)))
    editor.setValue(int(value or 0))
    editor.valueChanged.connect(
        lambda candidate, property_key=key: host.apply_property(
            property_key,
            candidate,
        )
    )
    return editor


def _create_number_editor(host: Any, key: str, spec: Any, value: Any) -> QWidget:
    minimum, maximum = host._bounds(spec, integer=False)
    if _allow_none(spec):
        fallback = _metadata(spec, "default", default=None)
        if fallback is None:
            fallback = 1.0
        editor = NullableDoubleEditor(
            value,
            fallback=float(fallback),
            bounds=(minimum, maximum),
            decimals=int(_metadata_default(spec, "decimals", default=6)),
            step=float(_metadata_default(spec, "step", "single_step", default=0.1)),
            parent=host,
        )
        host._nullable_number_editors[key] = editor
        return _connect_value(host, editor, key)
    editor = FocusAwareDoubleSpinBox(host)
    editor.setRange(minimum, maximum)
    editor.setDecimals(int(_metadata_default(spec, "decimals", default=6)))
    editor.setSingleStep(
        float(_metadata_default(spec, "step", "single_step", default=0.1))
    )
    editor.setValue(float(value or 0.0))
    editor.valueChanged.connect(
        lambda candidate, property_key=key: host.apply_property(
            property_key,
            candidate,
        )
    )
    return editor


def _create_enum_editor(host: Any, key: str, spec: Any, value: Any) -> QWidget:
    kind = host._editor_kind(spec, value, key=key)
    editor = QComboBox(host)
    choices = _metadata(spec, "choices", "options", "values", default=()) or ()
    if not choices:
        choices = _ENUM_DEFAULT_CHOICES.get(kind, ())
    iterable = (
        choices.items()
        if isinstance(choices, Mapping)
        else ((item, item) for item in choices)
    )
    for label, choice in iterable:
        editor.addItem(str(label), choice)
    index = editor.findData(value)
    if index < 0:
        index = editor.findData(_enum_text(value))
    editor.setCurrentIndex(max(0, index))
    apply_expanding_field(editor)
    editor.currentIndexChanged.connect(
        lambda _index, combo=editor, property_key=key: host.apply_property(
            property_key,
            combo.currentData(),
        )
    )
    return editor


def _create_color_editor(host: Any, key: str, spec: Any, value: Any) -> QWidget:
    host._require_color_library(key)
    initial_color = value
    if initial_color is None:
        initial_color = _metadata(spec, "default", default=None)
    if initial_color is None:
        initial_color = "#000000"
    editor = ColorChoiceWidget(
        initial_color,
        color_library=host.color_library,
        parent=host,
    )
    editor.colorChanged.connect(
        lambda candidate, property_key=key: host.apply_property(
            property_key,
            candidate,
        )
    )
    return editor


def _create_font_editor(host: Any, key: str, spec: Any, value: Any) -> QWidget:
    del spec
    editor = QFontComboBox(host)
    apply_expanding_field(editor)
    if value:
        editor.setCurrentFont(QFont(str(value)))
    editor.currentFontChanged.connect(
        lambda font, property_key=key: host.apply_property(
            property_key,
            font.family(),
        )
    )
    return editor


def _create_tuple_editor(host: Any, key: str, spec: Any, value: Any) -> QWidget:
    kind = host._editor_kind(spec, value, key=key)
    length = _TUPLE_LENGTHS.get(kind, 2)
    editor = NumericTupleEditor(
        value,
        length=length,
        nullable=_allow_none(spec),
        fallback=host._tuple_fallback(spec, length),
        decimals=int(_metadata_default(spec, "decimals", default=6)),
        step=float(_metadata_default(spec, "step", default=0.1)),
        parent=host,
    )
    host._tuple_editors[key] = editor
    if length == 2:
        host._position_inputs[key] = tuple(editor.inputs)
    return _connect_value(host, editor, key)


def _create_spine_position_editor(
    host: Any,
    key: str,
    spec: Any,
    value: Any,
) -> QWidget:
    del spec
    editor = SpinePositionEditor(value, parent=host)
    host._spine_position_editors[key] = editor
    return _connect_value(host, editor, key)


def _create_aspect_editor(host: Any, key: str, spec: Any, value: Any) -> QWidget:
    return host._create_text_editor(
        key,
        spec,
        value,
        parser=host._parse_aspect,
        formatter=lambda candidate: str(candidate),
    )


def _create_value_spec_editor(host: Any, key: str, spec: Any, value: Any) -> QWidget:
    kind = host._editor_kind(spec, value, key=key)
    editor = _VALUE_SPEC_EDITORS[kind](value, parent=host)
    return _connect_value(host, editor, key)


def _create_color_spec_editor(host: Any, key: str, spec: Any, value: Any) -> QWidget:
    kind = host._editor_kind(spec, value, key=key)
    editor = _COLOR_SPEC_EDITORS[kind](
        value,
        color_library=host._require_color_library(key),
        parent=host,
    )
    return _connect_value(host, editor, key)


def _create_optional_color_editor(
    host: Any,
    key: str,
    spec: Any,
    value: Any,
) -> QWidget:
    editor = OptionalColorEditor(
        value,
        color_library=host._require_color_library(key),
        unset_value=None if _allow_none(spec) else "none",
        parent=host,
    )
    return _connect_value(host, editor, key)


def _create_named_number_editor(host: Any, key: str, spec: Any, value: Any) -> QWidget:
    del spec
    editor = NamedNumberEditor(
        value,
        names=_NAMED_NUMBER_CHOICES.get(key, FONT_WEIGHT_NAMES),
        parent=host,
    )
    return _connect_value(host, editor, key)


def _create_number_sequence_editor(
    host: Any,
    key: str,
    spec: Any,
    value: Any,
) -> QWidget:
    del spec
    return _connect_value(host, NumberSequenceEditor(value, parent=host), key)


def _create_string_list_editor(host: Any, key: str, spec: Any, value: Any) -> QWidget:
    del spec
    return _connect_value(host, StringListEditor(value, parent=host), key)


def _create_json_editor(host: Any, key: str, spec: Any, value: Any) -> QWidget:
    import json

    nullable = _allow_none(spec)
    return host._create_text_editor(
        key,
        spec,
        value,
        parser=lambda candidate, allow_empty=nullable: (
            None
            if allow_empty and not candidate.strip()
            else json.loads(candidate)
        ),
        formatter=lambda candidate: (
            ""
            if candidate is None
            else json.dumps(candidate, ensure_ascii=False, sort_keys=True)
        ),
    )


def _create_text_kind_editor(host: Any, key: str, spec: Any, value: Any) -> QWidget:
    nullable = _allow_none(spec)
    return host._create_text_editor(
        key,
        spec,
        value,
        parser=lambda candidate, allow_empty=nullable: (
            None if allow_empty and not candidate else candidate
        ),
        formatter=lambda candidate: "" if candidate is None else str(candidate),
    )


def register_editor_factory(
    kind: EditorKind,
    factory: EditorFactory,
    registry: dict[EditorKind, EditorFactory],
) -> None:
    """Register one factory or fail if the EditorKind is already claimed."""

    if kind in registry:
        raise RuntimeError(f"Duplicate editor factory for {kind.value}.")
    if not callable(factory):
        raise RuntimeError(f"Editor factory for {kind.value} must be callable.")
    registry[kind] = factory


def validate_editor_factories(
    registry: Mapping[EditorKind, EditorFactory] | None = None,
) -> None:
    """Fail unless every EditorKind has exactly one callable factory."""

    table = EDITOR_FACTORIES if registry is None else registry
    expected = set(EditorKind)
    registered = set(table)
    if registered != expected:
        raise RuntimeError(
            "Editor factories must cover every EditorKind exactly; "
            f"missing={sorted(kind.value for kind in expected - registered)} "
            f"extra={sorted(kind.value for kind in registered - expected)}."
        )
    for kind, factory in table.items():
        if not callable(factory):
            raise RuntimeError(
                f"Editor factory for {kind.value} must be callable."
            )


def create_editor_widget(host: Any, key: str, spec: Any, value: Any) -> QWidget:
    """Resolve a concrete EditorKind, then create that kind's widget."""

    kind = host._editor_kind(spec, value, key=key)
    try:
        factory = EDITOR_FACTORIES[kind]
    except KeyError as exc:
        raise ComponentValidationError(
            f"Property {key!r} declares unsupported editor {kind.value!r}."
        ) from exc
    return factory(host, key, spec, value)


EDITOR_FACTORIES: dict[EditorKind, EditorFactory] = {}
_FACTORY_BINDINGS: tuple[tuple[EditorKind, EditorFactory], ...] = (
    (EditorKind.AUTO, _create_auto_editor),
    (EditorKind.BOOL, _create_bool_editor),
    (EditorKind.INT, _create_int_editor),
    (EditorKind.NUMBER, _create_number_editor),
    (EditorKind.ROTATION, _create_number_editor),
    (EditorKind.ENUM, _create_enum_editor),
    (EditorKind.LINE_STYLE, _create_enum_editor),
    (EditorKind.MARKER, _create_enum_editor),
    (EditorKind.FONT_WEIGHT, _create_enum_editor),
    (EditorKind.LEGEND_POSITION, _create_enum_editor),
    (EditorKind.COLOR, _create_color_editor),
    (EditorKind.FONT, _create_font_editor),
    (EditorKind.POSITION, _create_tuple_editor),
    (EditorKind.SIZE, _create_tuple_editor),
    (EditorKind.RANGE, _create_tuple_editor),
    (EditorKind.TRIPLET, _create_tuple_editor),
    (EditorKind.RECTANGLE, _create_tuple_editor),
    (EditorKind.SPINE_POSITION, _create_spine_position_editor),
    (EditorKind.ASPECT, _create_aspect_editor),
    (EditorKind.TEXT, _create_text_kind_editor),
    (EditorKind.JSON, _create_json_editor),
    (EditorKind.OPTIONAL_COLOR, _create_optional_color_editor),
    (EditorKind.NAMED_NUMBER, _create_named_number_editor),
    (EditorKind.NUMBER_SEQUENCE, _create_number_sequence_editor),
    (EditorKind.STRING_LIST, _create_string_list_editor),
    *tuple(
        (kind, _create_value_spec_editor) for kind in _VALUE_SPEC_EDITORS
    ),
    *tuple(
        (kind, _create_color_spec_editor) for kind in _COLOR_SPEC_EDITORS
    ),
)
for _kind, _factory in _FACTORY_BINDINGS:
    register_editor_factory(_kind, _factory, EDITOR_FACTORIES)
validate_editor_factories()
