"""Value objects shared by all Matplotlib component controllers.

This module deliberately contains no Qt imports.  The dataclasses are suitable
for both runtime use and project-file serialization.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from enum import Enum, IntEnum, IntFlag, StrEnum
import math
from typing import Any, Callable, Mapping

from .errors import ComponentValidationError


class ComponentKind(str, Enum):
    """Enumerate the supported component kind values."""

    FIGURE = "figure"
    AXES = "axes"
    AXIS = "axis"
    SPINE = "spine"
    TICK_GROUP = "tick_group"
    TICK_LABEL_GROUP = "tick_label_group"
    GRID = "grid"
    TEXT = "text"
    ANNOTATION = "annotation"
    LEGEND = "legend"
    LINE = "line"
    SCATTER = "scatter"
    ERRORBAR = "errorbar"
    FIELD_2D = "field_2d"
    COLORBAR = "colorbar"
    IN_AXES = "in_axes"
    REFERENCE_MARKS = "reference_marks"
    REFERENCE_GUIDE = "reference_guide"
    SECONDARY_AXIS = "secondary_axis"


class ComponentRole(str, Enum):
    """Enumerate the supported component role values."""

    FIGURE = "figure"
    AXES = "axes"
    X_AXIS = "x_axis"
    Y_AXIS = "y_axis"
    SPINE = "spine"
    MAJOR_TICK = "major_tick"
    MINOR_TICK = "minor_tick"
    MAJOR_TICK_LABEL = "major_tick_label"
    MINOR_TICK_LABEL = "minor_tick_label"
    GRID = "grid"
    TITLE = "title"
    X_LABEL = "x_label"
    Y_LABEL = "y_label"
    TEXT = "text"
    ANNOTATION = "annotation"
    LEGEND = "legend"
    LINE = "line"
    FUNCTION_CURVE = "function_curve"
    DATA_PLOT = "data_plot"
    FIT_CURVE = "fit_curve"
    INTERPOLATION = "interpolation"
    SCATTER = "scatter"
    ERROR_BAR = "error_bar"
    PSEUDOCOLOR = "pseudocolor"
    HEATMAP = "heatmap"
    CONTOUR = "contour"
    COLORBAR = "colorbar"
    IN_AXES_ZOOM = "in_axes_zoom"
    IN_AXES_IMAGE = "in_axes_image"
    REFLECTION_POSITIONS = "reflection_positions"
    REFERENCE_LINE = "reference_line"
    REFERENCE_BAND = "reference_band"
    SECONDARY_X_AXIS = "secondary_x_axis"
    SECONDARY_Y_AXIS = "secondary_y_axis"


class FitEngine(StrEnum):
    """Stable project-schema wire values for supported fitting engines."""

    PYTHON = "Python"
    MATLAB = "Matlab"


class CoordinateSystem(StrEnum):
    """Enumerate coordinate systems supported by component geometries."""

    DATA = "data"
    AXES_FRACTION = "axes_fraction"
    FIGURE_FRACTION = "figure_fraction"
    OFFSET_POINTS = "offset_points"


class AnnotationArrowStyle(StrEnum):
    """Enumerate stable wire values for Annotation arrow styles."""

    LINE = "line"
    ARROW = "arrow"
    FILLED_ARROW = "filled_arrow"
    DOUBLE_ARROW = "double_arrow"


class AnnotationConnectionStyle(StrEnum):
    """Enumerate stable wire values for Annotation connection styles."""

    STRAIGHT = "straight"
    ANGLE = "angle"
    ARC = "arc"


class EditorKind(StrEnum):
    """Closed set of UI editor contracts used by ``PropertySpec``.

    The enum values intentionally match the existing first-party declarations
    so loading the controller module normalizes every declaration to this
    closed type.  Unknown or misspelled editor hints therefore fail during
    startup instead of silently becoming text inputs.
    """

    AUTO = "auto"
    BOOL = "bool"
    INT = "int"
    NUMBER = "number"
    ENUM = "enum"
    TEXT = "text"
    COLOR = "color"
    FONT = "font"
    POSITION = "position"
    SIZE = "size"
    RANGE = "range"
    RECTANGLE = "rectangle"
    SPINE_POSITION = "spine_position"
    ASPECT = "aspect"
    ROTATION = "rotation"
    LINE_STYLE = "line_style"
    FONT_WEIGHT = "font_weight"
    LEGEND_POSITION = "legend_position"
    MARKER = "marker"
    SCALE_SPEC = "scale_spec"
    LOCATOR_SPEC = "locator_spec"
    FORMATTER_SPEC = "formatter_spec"
    FONT_SPEC = "font_spec"
    LINE_PATTERN = "line_pattern"
    MARKER_SPEC = "marker_spec"
    MARKEVERY = "markevery"
    ERROR_EVERY = "error_every"
    OPTIONAL_COLOR = "optional_color"
    NAMED_NUMBER = "named_number"
    TEXT_BOX = "text_box"
    ANNOTATION_BOX = "annotation_box"
    LEGEND_ANCHOR = "legend_anchor"
    LAYOUT_SPEC = "layout_spec"
    AXES_ANCHOR = "axes_anchor"
    TRIPLET = "triplet"
    NUMBER_SEQUENCE = "number_sequence"
    STRING_LIST = "string_list"
    CONNECTORS = "connectors"
    SCATTER_COLOR_MAP = "scatter_color_map"
    SCATTER_SIZE_MAP = "scatter_size_map"
    COLOR_MAP_SPEC = "color_map_spec"
    GRID_EDGE_SPEC = "grid_edge_spec"
    CONTOUR_LEVELS_SPEC = "contour_levels_spec"
    CONTOUR_LABEL_SPEC = "contour_label_spec"
    UNIT_TRANSFORM_SPEC = "unit_transform_spec"
    SECONDARY_AXIS_PLACEMENT = "secondary_axis_placement"
    JSON = "json"

    @classmethod
    def _missing_(cls, value):
        migrations = {
            "check": cls.BOOL,
            "spin": cls.INT,
            "double_spin": cls.NUMBER,
            "combo": cls.ENUM,
        }
        return migrations.get(value)


class RestorePhase(IntEnum):
    """Ordered runtime materialization phases for persisted components."""

    DYNAMIC = 10
    IN_AXES = 20
    COLORBAR = 30
    SECONDARY_AXIS = 40


ROLES_BY_KIND: dict[ComponentKind, frozenset[ComponentRole]] = {
    ComponentKind.FIGURE: frozenset({ComponentRole.FIGURE}),
    ComponentKind.AXES: frozenset({ComponentRole.AXES}),
    ComponentKind.AXIS: frozenset(
        {ComponentRole.X_AXIS, ComponentRole.Y_AXIS}
    ),
    ComponentKind.SPINE: frozenset({ComponentRole.SPINE}),
    ComponentKind.TICK_GROUP: frozenset(
        {ComponentRole.MAJOR_TICK, ComponentRole.MINOR_TICK}
    ),
    ComponentKind.TICK_LABEL_GROUP: frozenset(
        {
            ComponentRole.MAJOR_TICK_LABEL,
            ComponentRole.MINOR_TICK_LABEL,
        }
    ),
    ComponentKind.GRID: frozenset({ComponentRole.GRID}),
    ComponentKind.TEXT: frozenset(
        {
            ComponentRole.TITLE,
            ComponentRole.X_LABEL,
            ComponentRole.Y_LABEL,
            ComponentRole.TEXT,
        }
    ),
    ComponentKind.LEGEND: frozenset({ComponentRole.LEGEND}),
    ComponentKind.ANNOTATION: frozenset({ComponentRole.ANNOTATION}),
    ComponentKind.LINE: frozenset(
        {
            ComponentRole.LINE,
            ComponentRole.FUNCTION_CURVE,
            ComponentRole.DATA_PLOT,
            ComponentRole.FIT_CURVE,
            ComponentRole.INTERPOLATION,
        }
    ),
    ComponentKind.SCATTER: frozenset({ComponentRole.SCATTER}),
    ComponentKind.ERRORBAR: frozenset({ComponentRole.ERROR_BAR}),
    ComponentKind.FIELD_2D: frozenset(
        {
            ComponentRole.PSEUDOCOLOR,
            ComponentRole.HEATMAP,
            ComponentRole.CONTOUR,
        }
    ),
    ComponentKind.COLORBAR: frozenset({ComponentRole.COLORBAR}),
    ComponentKind.IN_AXES: frozenset(
        {
            ComponentRole.IN_AXES_ZOOM,
            ComponentRole.IN_AXES_IMAGE,
        }
    ),
    ComponentKind.REFERENCE_MARKS: frozenset(
        {ComponentRole.REFLECTION_POSITIONS}
    ),
    ComponentKind.REFERENCE_GUIDE: frozenset(
        {
            ComponentRole.REFERENCE_LINE,
            ComponentRole.REFERENCE_BAND,
        }
    ),
    ComponentKind.SECONDARY_AXIS: frozenset(
        {
            ComponentRole.SECONDARY_X_AXIS,
            ComponentRole.SECONDARY_Y_AXIS,
        }
    ),
}


class UpdateImpact(IntFlag):
    """Work that must be performed after a successful component change."""

    NONE = 0
    RELIM = 1
    AUTOSCALE = 2
    LEGEND = 4
    REDRAW = 8

    def to_names(self) -> list[str]:
        """Convert this object to names."""

        return [
            member.name.lower()
            for member in type(self)
            if member is not type(self).NONE and member in self
        ]


class ChangeStatus(str, Enum):
    """Enumerate the supported change status values."""

    APPLIED = "applied"
    EMPTY = "empty"
    REJECTED = "rejected"
    DELETED = "deleted"
    NOOP = "noop"


class DeletionPolicy(str, Enum):
    """Runtime business policy for removing a Figure component."""

    REMOVE = "remove"
    HIDE = "hide"
    FORBID = "forbid"


class MessageLevel(str, Enum):
    """User-facing severity carried without importing the GUI message bar."""

    INFO = "info"
    SUCCESS = "success"
    WARNING = "warning"
    ERROR = "error"


class ComponentEventKind(str, Enum):
    """Lifecycle event emitted by :class:`ComponentRegistry`."""

    ADDED = "added"
    CHANGED = "changed"
    REMOVED = "removed"


class _KeepRuntimeData:
    __slots__ = ()

    def __repr__(self) -> str:
        return "KEEP_RUNTIME_DATA"


KEEP_RUNTIME_DATA = _KeepRuntimeData()


@dataclass(frozen=True, slots=True)
class XYData:
    """Transient drawable data used by Line and Scatter transactions."""

    x: Any
    y: Any


@dataclass(frozen=True, slots=True)
class ScatterData:
    """Transient aligned Scatter arrays; never serialized directly."""

    x: Any
    y: Any
    colors: Any = None
    sizes: Any = None


@dataclass(frozen=True, slots=True)
class ErrorBarData:
    """Transient Error Bar arrays in post-preprocessing coordinates.

    ``xerr``/``yerr`` follow Matplotlib errorbar shapes: ``None`` when that
    dimension carries no error, a one-dimensional symmetric array, or a
    ``2 x N`` minus/plus array.  Values are absolute magnitudes and are never
    preprocessed mathematically.
    """

    x: Any
    y: Any
    xerr: Any = None
    yerr: Any = None


@dataclass(frozen=True, slots=True)
class ErrorBarRuntimeSnapshot:
    """Deep-copied Error Bar drawable data plus style values for rollback."""

    data: ErrorBarData
    properties: dict[str, Any]


@dataclass(frozen=True, slots=True)
class Field2DData:
    """Transient gridded Z values used by FIELD_2D transactions."""

    x: Any
    y: Any
    z: Any
    empty: bool = False


@dataclass(frozen=True, slots=True)
class ComponentNotice:
    """A non-exception message produced by a component operation."""

    level: MessageLevel
    message: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "level", MessageLevel(self.level))
        if not isinstance(self.message, str) or not self.message.strip():
            raise ComponentValidationError(
                "Component notice message must be non-empty."
            )


@dataclass(frozen=True, slots=True)
class ComponentMutation:
    """One atomic Controller mutation.

    ``properties`` is merged with the current persistent properties.
    ``data`` is a complete replacement of the role-specific data mapping.
    ``runtime_data`` is deliberately transient and never serialized.
    """

    component_id: str
    properties: Mapping[str, Any] | None = None
    data: Mapping[str, Any] | None = None
    runtime_data: Any = KEEP_RUNTIME_DATA

    def __post_init__(self) -> None:
        if not isinstance(self.component_id, str) or not self.component_id:
            raise ComponentValidationError(
                "Component mutation requires a component id."
            )
        if self.properties is not None:
            object.__setattr__(
                self,
                "properties",
                deepcopy(dict(self.properties)),
            )
        if self.data is not None:
            object.__setattr__(self, "data", deepcopy(dict(self.data)))


_STATE_FIELDS = frozenset(
    {
        "id",
        "kind",
        "role",
        "parent_id",
        "order",
        "selector",
        "properties",
        "data",
    }
)


def _json_copy(value: Any) -> Any:
    """Return a deep, JSON-friendly copy without importing NumPy."""

    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Mapping):
        return {str(key): _json_copy(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_copy(item) for item in value]
    tolist = getattr(value, "tolist", None)
    if callable(tolist):
        try:
            return _json_copy(tolist())
        except (TypeError, ValueError):
            pass
    item = getattr(value, "item", None)
    if callable(item):
        try:
            return _json_copy(item())
        except (TypeError, ValueError):
            pass
    return deepcopy(value)


@dataclass(slots=True)
class ComponentState:
    """Serializable state for one node in the Figure component tree."""

    id: str
    kind: ComponentKind
    role: ComponentRole
    parent_id: str | None = None
    order: int = 0
    selector: dict[str, Any] = field(default_factory=dict)
    properties: dict[str, Any] = field(default_factory=dict)
    data: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        try:
            self.kind = ComponentKind(self.kind)
        except (TypeError, ValueError) as exc:
            raise ComponentValidationError(
                f"Unknown component kind: {self.kind!r}"
            ) from exc
        try:
            self.role = ComponentRole(self.role)
        except (TypeError, ValueError) as exc:
            raise ComponentValidationError(
                f"Unknown component role: {self.role!r}"
            ) from exc

        if not isinstance(self.id, str) or not self.id.strip():
            raise ComponentValidationError("Component id must be a non-empty string.")
        if self.parent_id is not None and (
            not isinstance(self.parent_id, str) or not self.parent_id.strip()
        ):
            raise ComponentValidationError(
                "Component parent_id must be null or a non-empty string."
            )
        if self.parent_id == self.id:
            raise ComponentValidationError("A component cannot be its own parent.")
        if isinstance(self.order, bool) or not isinstance(self.order, int):
            raise ComponentValidationError("Component order must be an integer.")
        if self.order < 0:
            raise ComponentValidationError("Component order cannot be negative.")

        for name in ("selector", "properties", "data"):
            value = getattr(self, name)
            if not isinstance(value, dict):
                raise ComponentValidationError(
                    f"Component {name} must be a dictionary."
                )
            setattr(self, name, deepcopy(value))

        allowed_roles = ROLES_BY_KIND[self.kind]
        if self.role not in allowed_roles:
            raise ComponentValidationError(
                f"Role {self.role.value!r} is not valid for kind "
                f"{self.kind.value!r}."
            )

    def clone(self, **changes: Any) -> "ComponentState":
        """Return an independent copy of this component state."""

        values = self.to_dict()
        values.update(changes)
        return type(self).from_dict(values)

    def to_dict(self) -> dict[str, Any]:
        """Convert this object to dict."""

        return {
            "id": self.id,
            "kind": self.kind.value,
            "role": self.role.value,
            "parent_id": self.parent_id,
            "order": self.order,
            "selector": _json_copy(self.selector),
            "properties": _json_copy(self.properties),
            "data": _json_copy(self.data),
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "ComponentState":
        """Build an instance from dict."""

        if not isinstance(value, Mapping):
            raise ComponentValidationError("Component state must be an object.")
        fields = set(value)
        missing = _STATE_FIELDS - fields
        unknown = fields - _STATE_FIELDS
        if missing:
            raise ComponentValidationError(
                f"Component state is missing fields: {sorted(missing)!r}."
            )
        if unknown:
            raise ComponentValidationError(
                f"Component state has unknown fields: {sorted(unknown)!r}."
            )
        return cls(
            id=value["id"],
            kind=value["kind"],
            role=value["role"],
            parent_id=value["parent_id"],
            order=value["order"],
            selector=value["selector"],
            properties=value["properties"],
            data=value["data"],
        )


Getter = str | Callable[[Any], Any]
Setter = str | Callable[[Any, Any], None]
Validator = Callable[[Any], bool | None]
Normalizer = Callable[[Any], Any]


@dataclass(frozen=True, slots=True)
class PropertySpec:
    """Description of one editable property.

    ``getter`` and ``setter`` may be method names or callables.  If omitted,
    controllers use Matplotlib's conventional ``get_<key>``/``set_<key>``
    methods.  UI code can use ``editor`` and ``choices`` without importing a
    concrete controller class.
    """

    key: str
    value_type: type | tuple[type, ...]
    default: Any = None
    validator: Validator | None = None
    editor: EditorKind = EditorKind.AUTO
    persistent: bool = True
    impact: UpdateImpact = UpdateImpact.REDRAW
    choices: tuple[Any, ...] | None = None
    getter: Getter | None = None
    setter: Setter | None = None
    normalizer: Normalizer | None = None
    allow_none: bool = False
    label: str | None = None
    tooltip: str | None = None
    minimum: float | int | None = None
    maximum: float | int | None = None
    step: float | int | None = None
    decimals: int | None = None
    advanced: bool = False

    def __post_init__(self) -> None:
        if not self.key or not isinstance(self.key, str):
            raise ComponentValidationError(
                "PropertySpec key must be a non-empty string."
            )
        if not isinstance(self.impact, UpdateImpact):
            object.__setattr__(self, "impact", UpdateImpact(self.impact))
        if not isinstance(self.editor, EditorKind):
            try:
                object.__setattr__(self, "editor", EditorKind(self.editor))
            except (TypeError, ValueError) as exc:
                raise ComponentValidationError(
                    f"Property {self.key!r} declares unknown editor "
                    f"{self.editor!r}."
                ) from exc
        if self.choices is not None:
            object.__setattr__(self, "choices", tuple(self.choices))
        if self.label is not None and not str(self.label).strip():
            raise ComponentValidationError(
                f"Property {self.key!r} label must not be empty."
            )
        if self.tooltip is not None and not str(self.tooltip).strip():
            raise ComponentValidationError(
                f"Property {self.key!r} tooltip must not be empty."
            )
        if (
            self.minimum is not None
            and self.maximum is not None
            and self.minimum > self.maximum
        ):
            raise ComponentValidationError(
                f"Property {self.key!r} minimum exceeds maximum."
            )
        if self.step is not None and self.step <= 0:
            raise ComponentValidationError(
                f"Property {self.key!r} step must be positive."
            )
        if self.decimals is not None and self.decimals < 0:
            raise ComponentValidationError(
                f"Property {self.key!r} decimals cannot be negative."
            )

    def normalize(self, value: Any) -> Any:
        """Return the value normalized by this property specification."""

        if value is None:
            if self.allow_none:
                return None
            raise ComponentValidationError(
                f"Property {self.key!r} cannot be null."
            )

        normalized = self.normalizer(value) if self.normalizer else value
        expected = self.value_type
        expected_types = expected if isinstance(expected, tuple) else (expected,)

        if bool not in expected_types and isinstance(normalized, bool):
            raise ComponentValidationError(
                f"Property {self.key!r} has the wrong type."
            )
        if float in expected_types and isinstance(normalized, (int, float)):
            normalized = float(normalized)
            if not math.isfinite(normalized):
                raise ComponentValidationError(
                    f"Property {self.key!r} must be finite."
                )
        elif int in expected_types and isinstance(normalized, int):
            normalized = int(normalized)

        if not isinstance(normalized, expected_types):
            expected_names = ", ".join(item.__name__ for item in expected_types)
            raise ComponentValidationError(
                f"Property {self.key!r} must be {expected_names}; "
                f"got {type(normalized).__name__}."
            )
        if self.choices is not None and normalized not in self.choices:
            raise ComponentValidationError(
                f"Property {self.key!r} must be one of {self.choices!r}."
            )
        if (
            self.minimum is not None
            and isinstance(normalized, (int, float))
            and normalized < self.minimum
        ):
            raise ComponentValidationError(
                f"Property {self.key!r} must be at least {self.minimum}."
            )
        if (
            self.maximum is not None
            and isinstance(normalized, (int, float))
            and normalized > self.maximum
        ):
            raise ComponentValidationError(
                f"Property {self.key!r} must be at most {self.maximum}."
            )
        if self.validator is not None:
            try:
                result = self.validator(normalized)
            except ComponentValidationError:
                raise
            except Exception as exc:
                raise ComponentValidationError(
                    f"Property {self.key!r} is invalid: {exc}"
                ) from exc
            if result is False:
                raise ComponentValidationError(
                    f"Property {self.key!r} failed validation."
                )
        return normalized

    def metadata(self) -> dict[str, Any]:
        """Return serializable metadata for this property specification."""

        return {
            "key": self.key,
            "editor": self.editor.value,
            "default": deepcopy(self.default),
            "persistent": self.persistent,
            "impact": self.impact.to_names(),
            "choices": deepcopy(self.choices),
            "allow_none": self.allow_none,
        }


@dataclass(frozen=True, slots=True)
class ComponentChange:
    """Result of one controller operation."""

    component_id: str
    property_key: str | None
    before: ComponentState | None
    after: ComponentState | None
    status: ChangeStatus
    impacts: UpdateImpact = UpdateImpact.NONE
    message: str = ""
    notices: tuple[ComponentNotice, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "notices",
            tuple(self.notices),
        )

    @property
    def ok(self) -> bool:
        """Return whether the operation completed successfully."""

        return self.status is not ChangeStatus.REJECTED

    @property
    def changed(self) -> bool:
        """Report whether the current value differs from its initial value."""

        return self.status in {
            ChangeStatus.APPLIED,
            ChangeStatus.EMPTY,
            ChangeStatus.DELETED,
        }


@dataclass(frozen=True, slots=True)
class ComponentBatchChange:
    """Committed or rolled-back result of a Registry transaction."""

    changes: tuple[ComponentChange, ...]
    committed: bool
    notices: tuple[ComponentNotice, ...] = ()
    message: str = ""
    rollback_complete: bool = True

    @property
    def ok(self) -> bool:
        """Return whether the operation completed successfully."""

        return self.committed and all(change.ok for change in self.changes)

    @property
    def changed(self) -> bool:
        """Report whether the current value differs from its initial value."""

        return self.committed and any(change.changed for change in self.changes)


@dataclass(frozen=True, slots=True)
class ComponentEvent:
    """Post-commit event consumed by runtime/editor managers."""

    kind: ComponentEventKind
    component_id: str
    before: ComponentState | None
    after: ComponentState | None
    change: ComponentChange | None = None


@dataclass(frozen=True, slots=True)
class ObserverFailure:
    """Describe an isolated post-commit observer or refresh failure."""

    source: str
    phase: str
    error: BaseException
    component_id: str | None = None
    reference: object | None = None
