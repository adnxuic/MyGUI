"""Atomic Axis tick settings and isolated Agg previews."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, replace
from io import BytesIO
from math import isfinite
from typing import Any, Callable

from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure

from mygui.figuremodify.components import (
    AxisController,
    AxesController,
    ComponentBatchChange,
    ComponentKind,
    ComponentMutation,
    ComponentNotFoundError,
    ComponentRegistry,
    ComponentRole,
    ComponentState,
    TickGroupController,
    TickLabelGroupController,
)
from mygui.figuremodify.components.property_values import (
    DEFAULT_FORMATTER,
    DEFAULT_MAJOR_LOCATOR,
    DEFAULT_MINOR_FORMATTER,
    DEFAULT_MINOR_LOCATOR,
    apply_scale,
    build_formatter,
    build_locator,
    default_minor_locator_for_scale,
    normalize_formatter,
    normalize_locator,
    normalize_scale,
    text_box_kwargs,
    validate_fixed_ticker_pair,
)


@dataclass(frozen=True, slots=True)
class TickLevelSettings:
    """Complete persisted settings for one major or minor tick level."""

    locator: dict[str, Any]
    formatter: dict[str, Any]
    tick_properties: dict[str, Any]
    label_properties: dict[str, Any]


@dataclass(frozen=True, slots=True)
class AxisTickSettingsDraft:
    """Controller-free draft shown by the unified tick settings dialog."""

    axis_component_id: str
    axis: str
    scale: dict[str, Any]
    limits: tuple[float, float]
    major: TickLevelSettings
    minor: TickLevelSettings
    shared_axis_count: int
    expected_states: tuple[ComponentState, ...]


@dataclass(frozen=True, slots=True)
class AxisTickPreview:
    """PNG result from an isolated, non-project Agg render."""

    png: bytes
    width: int
    height: int


def _log_formatter(base: float) -> dict[str, Any]:
    return {
        "kind": "log_sci",
        "params": {
            "base": base,
            "label_only_base": False,
            "minor_thresholds": [1.0, 0.4],
            "linthresh": None,
        },
    }


def _logit_formatter(scale: dict[str, Any], *, minor: bool) -> dict[str, Any]:
    params = scale["params"]
    return {
        "kind": "logit",
        "params": {
            "use_overline": params["use_overline"],
            "one_half": params["one_half"],
            "minor": minor,
            "minor_threshold": 25,
        },
    }


def _scale_ticker_defaults(
    scale_value: Any,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    """Return Matplotlib-3.9-compatible major/minor ticker specifications."""

    scale = normalize_scale(scale_value)
    kind = scale["kind"]
    params = scale["params"]
    if kind == "linear":
        values = (
            DEFAULT_MAJOR_LOCATOR,
            DEFAULT_FORMATTER,
            DEFAULT_MINOR_LOCATOR,
            DEFAULT_MINOR_FORMATTER,
        )
    elif kind == "log":
        major_locator = {
            "kind": "log",
            "params": {
                "base": params["base"],
                "subs": [1.0],
                "numticks": None,
            },
        }
        minor_locator = {
            "kind": "log",
            "params": {
                "base": params["base"],
                "subs": params["subs"],
                "numticks": None,
            },
        }
        values = (
            major_locator,
            _log_formatter(params["base"]),
            minor_locator,
            _log_formatter(params["base"]),
        )
    elif kind == "symlog":
        major_locator = {
            "kind": "symlog",
            "params": {
                "transform": {
                    "base": params["base"],
                    "linthresh": params["linthresh"],
                    "linscale": params["linscale"],
                },
                "subs": params["subs"] or [1.0],
            },
        }
        minor_locator = default_minor_locator_for_scale(scale)
        values = (
            major_locator,
            _log_formatter(params["base"]),
            minor_locator,
            DEFAULT_MINOR_FORMATTER,
        )
    elif kind == "asinh":
        locator = {
            "kind": "asinh",
            "params": {
                "linear_width": params["linear_width"],
                "numticks": 11,
                "symthresh": 0.2,
                "base": params["base"],
                "subs": params["subs"],
            },
        }
        values = (
            locator,
            _log_formatter(params["base"]),
            locator,
            DEFAULT_MINOR_FORMATTER,
        )
    else:
        values = (
            {"kind": "logit", "params": {"minor": False, "nbins": "auto"}},
            _logit_formatter(scale, minor=False),
            {"kind": "logit", "params": {"minor": True, "nbins": "auto"}},
            _logit_formatter(scale, minor=True),
        )
    major_locator, major_formatter, minor_locator, minor_formatter = values
    return (
        normalize_locator(deepcopy(major_locator)),
        normalize_formatter(deepcopy(major_formatter)),
        normalize_locator(deepcopy(minor_locator)),
        normalize_formatter(deepcopy(minor_formatter)),
    )


class AxisTickSettingsService:
    """Own one atomic edit spanning Axis, Tick and Tick Label Controllers."""

    def __init__(
        self,
        registry: ComponentRegistry,
        *,
        linked_axes: Callable[[str, str], tuple[AxesController, ...]],
    ) -> None:
        self.registry = registry
        self._linked_axes = linked_axes

    def reapply_runtime_styles(self) -> None:
        """Replay tick styles before drawing dynamically recreated Tick objects."""

        for kind, controller_type in (
            (ComponentKind.TICK_GROUP, TickGroupController),
            (ComponentKind.TICK_LABEL_GROUP, TickLabelGroupController),
        ):
            for controller in self.registry.query(kind=kind):
                if isinstance(controller, controller_type):
                    controller.reapply_runtime_style()

    def _axis(self, axis_component_id: str) -> AxisController:
        controller = self.registry.get(axis_component_id)
        if not isinstance(controller, AxisController):
            raise ValueError("Tick settings require an X or Y Axis component.")
        axis = str(controller.state.selector.get("axis", ""))
        if axis not in {"x", "y"}:
            raise ValueError("Axis tick settings require an x or y selector.")
        return controller

    def _appearance(
        self, axis_id: str, level: str
    ) -> tuple[TickGroupController, TickLabelGroupController]:
        tick_role = (
            ComponentRole.MAJOR_TICK
            if level == "major"
            else ComponentRole.MINOR_TICK
        )
        label_role = (
            ComponentRole.MAJOR_TICK_LABEL
            if level == "major"
            else ComponentRole.MINOR_TICK_LABEL
        )
        try:
            tick = self.registry.find_one(
                parent_id=axis_id,
                kind=ComponentKind.TICK_GROUP,
                role=tick_role,
                recursive=False,
            )
        except ComponentNotFoundError as exc:
            raise ValueError(
                "Axis tick component subtree is incomplete."
            ) from exc
        if not isinstance(tick, TickGroupController):
            raise ValueError("Axis tick component subtree is incomplete.")
        try:
            label = self.registry.find_one(
                parent_id=tick.component_id,
                kind=ComponentKind.TICK_LABEL_GROUP,
                role=label_role,
                recursive=False,
            )
        except ComponentNotFoundError as exc:
            raise ValueError(
                "Axis tick component subtree is incomplete."
            ) from exc
        if not isinstance(label, TickLabelGroupController):
            raise ValueError("Axis tick component subtree is incomplete.")
        return tick, label

    def _linked_axis_controllers(
        self, axis: AxisController
    ) -> tuple[AxisController, ...]:
        dimension = str(axis.state.selector["axis"])
        role = (
            ComponentRole.X_AXIS
            if dimension == "x"
            else ComponentRole.Y_AXIS
        )
        result = []
        for axes in self._linked_axes(axis.state.parent_id, dimension):
            linked = self.registry.find_one(
                parent_id=axes.component_id,
                kind=ComponentKind.AXIS,
                role=role,
                recursive=False,
            )
            if not isinstance(linked, AxisController):
                raise ValueError("Shared Axes is missing its semantic Axis.")
            result.append(linked)
        return tuple(result)

    @staticmethod
    def _level(
        axis_state: ComponentState,
        tick: TickGroupController,
        label: TickLabelGroupController,
        level: str,
    ) -> TickLevelSettings:
        return TickLevelSettings(
            locator=deepcopy(axis_state.properties[f"{level}_locator"]),
            formatter=deepcopy(axis_state.properties[f"{level}_formatter"]),
            tick_properties=deepcopy(tick.state.properties),
            label_properties=deepcopy(label.state.properties),
        )

    def snapshot(self, axis_component_id: str) -> AxisTickSettingsDraft:
        """Capture the authoritative opening state for one unified dialog."""

        axis = self._axis(axis_component_id)
        axis_state = axis.state
        dimension = str(axis_state.selector["axis"])
        axes = self.registry.get(axis_state.parent_id)
        if not isinstance(axes, AxesController):
            raise ValueError("Axis owner must be an Axes component.")
        major_tick, major_label = self._appearance(axis.component_id, "major")
        minor_tick, minor_label = self._appearance(axis.component_id, "minor")
        linked = self._linked_axis_controllers(axis)
        expected_by_id = {
            item.component_id: item.state
            for item in (
                *linked,
                major_tick,
                major_label,
                minor_tick,
                minor_label,
            )
        }
        limits_key = "xlim" if dimension == "x" else "ylim"
        return AxisTickSettingsDraft(
            axis_component_id=axis.component_id,
            axis=dimension,
            scale=deepcopy(axis_state.properties["scale"]),
            limits=tuple(float(value) for value in axes.state.properties[limits_key]),
            major=self._level(axis_state, major_tick, major_label, "major"),
            minor=self._level(axis_state, minor_tick, minor_label, "minor"),
            shared_axis_count=len(linked),
            expected_states=tuple(expected_by_id.values()),
        )

    @staticmethod
    def _normalize_properties(
        controller_type: type,
        properties: dict[str, Any],
        label: str,
    ) -> dict[str, Any]:
        specs = controller_type.property_specs()
        expected = {
            key for key, spec in specs.items() if spec.persistent
        }
        actual = set(properties)
        if actual != expected:
            raise ValueError(
                f"{label} properties must be exactly {sorted(expected)!r}."
            )
        return {
            key: specs[key].normalize(deepcopy(properties[key]))
            for key in sorted(expected)
        }

    @classmethod
    def _normalize_level(
        cls, value: TickLevelSettings, level: str
    ) -> TickLevelSettings:
        if not isinstance(value, TickLevelSettings):
            raise ValueError(f"{level.title()} settings are invalid.")
        locator = normalize_locator(value.locator)
        formatter = normalize_formatter(value.formatter)
        validate_fixed_ticker_pair(locator, formatter)
        return TickLevelSettings(
            locator=locator,
            formatter=formatter,
            tick_properties=cls._normalize_properties(
                TickGroupController, value.tick_properties, f"{level} Tick"
            ),
            label_properties=cls._normalize_properties(
                TickLabelGroupController,
                value.label_properties,
                f"{level} Tick Label",
            ),
        )

    @classmethod
    def validate(cls, draft: AxisTickSettingsDraft) -> AxisTickSettingsDraft:
        """Normalize a draft without touching project or runtime state."""

        if not isinstance(draft, AxisTickSettingsDraft):
            raise ValueError("Axis tick settings draft is invalid.")
        if draft.axis not in {"x", "y"}:
            raise ValueError("Axis tick settings direction must be x or y.")
        limits = tuple(float(value) for value in draft.limits)
        if len(limits) != 2:
            raise ValueError("Axis tick preview range requires two values.")
        if not all(isfinite(value) for value in limits):
            raise ValueError("Axis tick preview range values must be finite.")
        return replace(
            draft,
            scale=normalize_scale(draft.scale),
            limits=limits,
            major=cls._normalize_level(draft.major, "major"),
            minor=cls._normalize_level(draft.minor, "minor"),
        )

    def scale_defaults(
        self, draft: AxisTickSettingsDraft
    ) -> AxisTickSettingsDraft:
        """Return a draft with only ticker specs reset for its current scale."""

        candidate = self.validate(draft)
        major_locator, major_formatter, minor_locator, minor_formatter = (
            _scale_ticker_defaults(candidate.scale)
        )
        return replace(
            candidate,
            major=replace(
                candidate.major,
                locator=major_locator,
                formatter=major_formatter,
            ),
            minor=replace(
                candidate.minor,
                locator=minor_locator,
                formatter=minor_formatter,
            ),
        )

    def _stale_message(
        self,
        axis: AxisController,
        expected_states: tuple[ComponentState, ...],
    ) -> str | None:
        expected = {state.id: state for state in expected_states}
        current_linked = {
            item.component_id for item in self._linked_axis_controllers(axis)
        }
        expected_linked = {
            component_id
            for component_id, state in expected.items()
            if state.kind is ComponentKind.AXIS
        }
        if current_linked != expected_linked:
            return "Shared-axis membership changed; reopen Tick settings."
        for component_id, opening in expected.items():
            try:
                current = self.registry.get(component_id).state
            except Exception:
                return "Tick component state changed; reopen Tick settings."
            if current != opening:
                return "Tick component state changed; reopen Tick settings."
        return None

    def apply(self, draft: AxisTickSettingsDraft) -> ComponentBatchChange:
        """Validate and atomically commit one complete tick-settings draft."""

        try:
            candidate = self.validate(draft)
            axis = self._axis(candidate.axis_component_id)
            if str(axis.state.selector["axis"]) != candidate.axis:
                raise ValueError("Axis direction changed; reopen Tick settings.")
            stale = self._stale_message(axis, candidate.expected_states)
            if stale:
                return ComponentBatchChange((), False, message=stale)
            major_tick, major_label = self._appearance(axis.component_id, "major")
            minor_tick, minor_label = self._appearance(axis.component_id, "minor")
            ticker_patch = {
                "major_locator": candidate.major.locator,
                "major_formatter": candidate.major.formatter,
                "minor_locator": candidate.minor.locator,
                "minor_formatter": candidate.minor.formatter,
            }
            mutations = [
                ComponentMutation(item.component_id, properties=ticker_patch)
                for item in self._linked_axis_controllers(axis)
            ]
            mutations.extend(
                (
                    ComponentMutation(
                        major_tick.component_id,
                        properties=candidate.major.tick_properties,
                    ),
                    ComponentMutation(
                        major_label.component_id,
                        properties=candidate.major.label_properties,
                    ),
                    ComponentMutation(
                        minor_tick.component_id,
                        properties=candidate.minor.tick_properties,
                    ),
                    ComponentMutation(
                        minor_label.component_id,
                        properties=candidate.minor.label_properties,
                    ),
                )
            )

            def verify() -> None:
                target = self.registry.resolve_target(axis.component_id)
                figure = target.axes.figure
                if figure.canvas is not None:
                    figure.canvas.draw()

            return self.registry.apply_transaction(mutations, verifier=verify)
        except Exception as exc:
            return ComponentBatchChange((), False, message=str(exc))


class AxisTickPreviewRenderer:
    """Render draft tick settings without using a project Figure or Artist."""

    def render(self, draft: AxisTickSettingsDraft) -> AxisTickPreview:
        """Return a PNG preview or raise a validation/rendering error."""

        candidate = AxisTickSettingsService.validate(draft)
        width, height = ((520, 190) if candidate.axis == "x" else (260, 380))
        figure = Figure(figsize=(width / 100.0, height / 100.0), dpi=100.0)
        canvas = FigureCanvasAgg(figure)
        axes = figure.add_subplot(111)
        axis = axes.xaxis if candidate.axis == "x" else axes.yaxis
        apply_scale(axes, candidate.axis, candidate.scale)
        if candidate.axis == "x":
            axes.set_xlim(candidate.limits)
            axes.set_ylim(0.0, 1.0)
            axes.yaxis.set_visible(False)
            axes.spines["left"].set_visible(False)
            axes.spines["right"].set_visible(False)
            axes.spines["top"].set_visible(False)
        else:
            axes.set_ylim(candidate.limits)
            axes.set_xlim(0.0, 1.0)
            axes.xaxis.set_visible(False)
            axes.spines["bottom"].set_visible(False)
            axes.spines["right"].set_visible(False)
            axes.spines["top"].set_visible(False)
        axis.set_major_locator(build_locator(candidate.major.locator))
        axis.set_major_formatter(build_formatter(candidate.major.formatter))
        axis.set_minor_locator(build_locator(candidate.minor.locator))
        axis.set_minor_formatter(build_formatter(candidate.minor.formatter))
        for level, settings in (
            ("major", candidate.major),
            ("minor", candidate.minor),
        ):
            tick = settings.tick_properties
            label = settings.label_properties
            primary, secondary = (
                ("bottom", "top")
                if candidate.axis == "x"
                else ("left", "right")
            )
            label_primary, label_secondary = (
                ("labelbottom", "labeltop")
                if candidate.axis == "x"
                else ("labelleft", "labelright")
            )
            axis.set_tick_params(
                which=level,
                **{
                    primary: tick["primary_visible"],
                    secondary: tick["secondary_visible"],
                    label_primary: label["primary_visible"],
                    label_secondary: label["secondary_visible"],
                    "direction": tick["direction"],
                    "length": tick["length"],
                    "width": tick["width"],
                    "color": tick["color"],
                    "labelcolor": label["color"],
                    "labelsize": label["fontsize"],
                    "labelrotation": label["rotation"],
                    "labelfontfamily": label["fontfamily"],
                    "pad": label["pad"],
                },
            )
        canvas.draw()
        for level, settings in (
            ("major", candidate.major),
            ("minor", candidate.minor),
        ):
            ticks = axis.get_major_ticks() if level == "major" else axis.get_minor_ticks()
            for item in ticks:
                for line in (item.tick1line, item.tick2line):
                    line.set_zorder(settings.tick_properties["zorder"])
                    line.set_antialiased(settings.tick_properties["antialiased"])
                for label in (item.label1, item.label2):
                    props = settings.label_properties
                    label.set_fontweight(props["fontweight"])
                    label.set_fontstyle(props["fontstyle"])
                    label.set_fontstretch(props["fontstretch"])
                    label.set_fontvariant(props["fontvariant"])
                    label.set_alpha(props["alpha"])
                    label.set_rotation_mode(props["rotation_mode"])
                    label.set_horizontalalignment(props["horizontalalignment"])
                    label.set_verticalalignment(props["verticalalignment"])
                    if props["multialignment"] is None:
                        label._multialignment = None
                        label.stale = True
                    else:
                        label.set_multialignment(props["multialignment"])
                    label.set_wrap(props["wrap"])
                    label.set_linespacing(props["linespacing"])
                    label.set_math_fontfamily(props["math_fontfamily"])
                    label.set_parse_math(props["parse_math"])
                    label.set_usetex(props["usetex"])
                    label.set_bbox(text_box_kwargs(props["bbox"]))
                    label.set_zorder(props["zorder"])
                    label.set_antialiased(props["antialiased"])
                    label.set_transform_rotates_text(props["transform_rotates_text"])
        canvas.draw()
        stream = BytesIO()
        canvas.print_png(stream)
        return AxisTickPreview(stream.getvalue(), width, height)


__all__ = [
    "AxisTickPreview",
    "AxisTickPreviewRenderer",
    "AxisTickSettingsDraft",
    "AxisTickSettingsService",
    "TickLevelSettings",
]
