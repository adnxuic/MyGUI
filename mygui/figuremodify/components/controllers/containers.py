"""Figure and Axes container Controllers."""

from __future__ import annotations

from copy import deepcopy
import math
from typing import Any

from matplotlib.axes import Axes
from matplotlib.figure import Figure

from mygui.figuremodify.y_axis_reserve import (
    read_y_lower_reserve,
    write_y_lower_reserve,
)

from ..base import ComponentController
from ..errors import ComponentValidationError
from ..matplotlib_removal import (
    MATPLOTLIB_REMOVAL,
    AxesSubtreeRemovalHandle,
)
from ..models import (
    ComponentKind,
    ComponentRole,
    ComponentState,
    DeletionPolicy,
    PropertySpec,
    UpdateImpact,
)
from ..property_values import (
    apply_figure_layout,
    normalize_figure_layout,
)
from ._helpers import (
    _positive,
    _nonnegative,
    _ARTIST_EXPORT_PROPERTIES,
    _normalize_color,
    _read_color,
    _pair,
    _nondegenerate_pair,
    _positive_pair,
    _anchor,
    _rectangle,
    _aspect,
    _y_lower_reserve_value,
    _figure_style,
    _exact_data_fields,
)

class ContainerController(ComponentController[Any]):
    """Coordinate state changes for container components."""

    CAPABILITIES = frozenset({"container"})


class FigureController(ContainerController):
    """Coordinate state changes for figure components."""

    KIND = ComponentKind.FIGURE
    ROLES = frozenset({ComponentRole.FIGURE})
    DELETION_POLICY = DeletionPolicy.FORBID
    PROPERTY_SPECS = (
        PropertySpec(
            "name",
            str,
            "",
            editor="text",
            getter=lambda _figure: "",
            setter=lambda _figure, _value: None,
        ),
        PropertySpec(
            "style",
            str,
            "default",
            editor="text",
            normalizer=_figure_style,
            getter=lambda _figure: "default",
            setter=lambda _figure, _value: None,
        ),
        PropertySpec(
            "size_inches",
            tuple,
            (6.4, 4.8),
            validator=_positive_pair,
            editor="size",
            normalizer=_pair,
        ),
        PropertySpec(
            "dpi",
            float,
            100.0,
            validator=_positive,
            editor="double_spin",
        ),
        PropertySpec(
            "facecolor",
            str,
            "#ffffff",
            editor="color",
            normalizer=_normalize_color,
            getter=lambda figure: _read_color(figure.get_facecolor()),
        ),
        PropertySpec(
            "edgecolor",
            str,
            "#ffffff",
            editor="color",
            normalizer=_normalize_color,
            getter=lambda figure: _read_color(figure.get_edgecolor()),
        ),
        PropertySpec("frameon", bool, True, editor="check"),
        PropertySpec(
            "linewidth",
            float,
            0.0,
            editor="double_spin",
            validator=_nonnegative,
            minimum=0.0,
        ),
        PropertySpec(
            "alpha",
            float,
            None,
            editor="double_spin",
            allow_none=True,
            minimum=0.0,
            maximum=1.0,
        ),
        PropertySpec(
            "layout_engine",
            dict,
            {"kind": "none", "params": {}},
            editor="layout_spec",
            normalizer=normalize_figure_layout,
            setter=apply_figure_layout,
        ),
        PropertySpec("label", str, "", editor="text", advanced=True),
        PropertySpec("visible", bool, True, editor="check", advanced=True),
        PropertySpec("zorder", float, 0.0, editor="double_spin", advanced=True),
    ) + _ARTIST_EXPORT_PROPERTIES
    CAPABILITIES = ContainerController.CAPABILITIES | frozenset(
        {"figure_style"}
    )

    def __init__(self, state: ComponentState, **kwargs: Any) -> None:
        self._property_callback = None
        self._metadata = {
            "name": str(state.properties.get("name", "")),
            "style": str(state.properties.get("style", "default")),
            "dpi": float(state.properties.get("dpi", 100.0)),
        }
        super().__init__(state, **kwargs)

    def _validate_data(self, state: ComponentState) -> None:
        """Require the current persisted layout collection."""

        _exact_data_fields(state, {"layouts"})
        layouts = state.data.get("layouts")
        if not isinstance(layouts, list):
            raise ComponentValidationError("Figure layouts must be an array.")
        layout_ids: set[str] = set()
        for raw in layouts:
            if not isinstance(raw, dict):
                raise ComponentValidationError("Each Figure layout must be an object.")
            expected = {
                "id",
                "nrows",
                "ncols",
                "width_ratios",
                "height_ratios",
                "margins",
                "spacing",
            }
            if set(raw) != expected:
                raise ComponentValidationError(
                    f"Figure layout fields must be {sorted(expected)!r}."
                )
            layout_id = raw.get("id")
            if not isinstance(layout_id, str) or not layout_id.strip():
                raise ComponentValidationError("Figure layout id is invalid.")
            if layout_id in layout_ids:
                raise ComponentValidationError("Figure layout ids must be unique.")
            layout_ids.add(layout_id)
            nrows = raw.get("nrows")
            ncols = raw.get("ncols")
            if any(
                isinstance(value, bool)
                or not isinstance(value, int)
                or not 1 <= value <= 6
                for value in (nrows, ncols)
            ):
                raise ComponentValidationError(
                    "Figure layout rows and columns must be between 1 and 6."
                )
            width_ratios = raw.get("width_ratios")
            height_ratios = raw.get("height_ratios")
            if (
                not isinstance(width_ratios, list)
                or len(width_ratios) != ncols
                or not isinstance(height_ratios, list)
                or len(height_ratios) != nrows
            ):
                raise ComponentValidationError(
                    "Figure layout ratios must match its grid dimensions."
                )
            for value in (*width_ratios, *height_ratios):
                if (
                    isinstance(value, bool)
                    or not isinstance(value, (int, float))
                    or not math.isfinite(float(value))
                    or float(value) <= 0
                ):
                    raise ComponentValidationError(
                        "Figure layout ratios must be positive finite numbers."
                    )
            margins = raw.get("margins")
            spacing = raw.get("spacing")
            if not isinstance(margins, dict) or set(margins) != {
                "left",
                "right",
                "bottom",
                "top",
            }:
                raise ComponentValidationError("Figure layout margins are invalid.")
            if not isinstance(spacing, dict) or set(spacing) != {
                "wspace",
                "hspace",
            }:
                raise ComponentValidationError("Figure layout spacing is invalid.")
            try:
                left = float(margins["left"])
                right = float(margins["right"])
                bottom = float(margins["bottom"])
                top = float(margins["top"])
                wspace = float(spacing["wspace"])
                hspace = float(spacing["hspace"])
            except (TypeError, ValueError) as exc:
                raise ComponentValidationError(
                    "Figure layout geometry must contain numbers."
                ) from exc
            if not all(
                math.isfinite(value)
                for value in (left, right, bottom, top, wspace, hspace)
            ):
                raise ComponentValidationError(
                    "Figure layout geometry must be finite."
                )
            if not 0 <= left < right <= 1 or not 0 <= bottom < top <= 1:
                raise ComponentValidationError("Figure layout margins are invalid.")
            if wspace < 0 or hspace < 0:
                raise ComponentValidationError("Figure layout spacing is invalid.")

    def set_property_callback(self, callback) -> None:
        """Attach an optional host synchronizer without introducing Qt."""

        self._property_callback = callback

    def _read_property(self, target: Figure, spec: PropertySpec) -> Any:
        if spec.key in self._metadata:
            return self._metadata[spec.key]
        if spec.key == "layout_engine":
            engine = target.get_layout_engine()
            name = "none" if engine is None else type(engine).__name__.lower()
            if "tight" in name:
                kind = "tight"
            elif "constrained" in name:
                kind = "compressed" if bool(getattr(engine, "_compress", False)) else "constrained"
            else:
                kind = "none"
            saved = self._state.properties.get("layout_engine")
            if isinstance(saved, dict) and saved.get("kind") == kind:
                return deepcopy(saved)
            if kind == "tight":
                return normalize_figure_layout(
                    {"kind": kind, "params": {"pad": None, "w_pad": None, "h_pad": None, "rect": None}}
                )
            if kind in {"constrained", "compressed"}:
                return normalize_figure_layout(
                    {"kind": kind, "params": {"w_pad": None, "h_pad": None, "wspace": None, "hspace": None, "rect": None}}
                )
            return normalize_figure_layout({"kind": "none", "params": {}})
        return super()._read_property(target, spec)

    def _write_property(
        self, target: Figure, spec: PropertySpec, value: Any
    ) -> None:
        if spec.key in self._metadata:
            self._metadata[spec.key] = value
            if spec.key == "dpi":
                target.set_dpi(value)
        else:
            super()._write_property(target, spec, value)
        if self._property_callback is not None:
            self._property_callback(spec.key, deepcopy(value))

class AxesController(ContainerController):
    """Coordinate state changes for axes components."""

    KIND = ComponentKind.AXES
    ROLES = frozenset({ComponentRole.AXES})
    DELETION_POLICY = DeletionPolicy.REMOVE
    PROPERTY_SPECS = (
        PropertySpec(
            "position",
            tuple,
            (0.125, 0.11, 0.775, 0.77),
            editor="rectangle",
            persistent=False,
            normalizer=_rectangle,
            getter=lambda axes: tuple(axes.get_position().bounds),
        ),
        PropertySpec(
            "xlim",
            tuple,
            (0.0, 1.0),
            validator=_nondegenerate_pair,
            editor="range",
            normalizer=_pair,
        ),
        PropertySpec(
            "ylim",
            tuple,
            (0.0, 1.0),
            validator=_nondegenerate_pair,
            editor="range",
            normalizer=_pair,
        ),
        PropertySpec(
            "aspect",
            (str, float),
            "auto",
            editor="aspect",
            normalizer=_aspect,
        ),
        PropertySpec(
            "facecolor",
            str,
            "#ffffff",
            editor="color",
            normalizer=_normalize_color,
            getter=lambda axes: _read_color(axes.get_facecolor()),
        ),
        PropertySpec("visible", bool, True, editor="check"),
        PropertySpec(
            "autoscalex_on",
            bool,
            True,
            editor="check",
            impact=(
                UpdateImpact.RELIM
                | UpdateImpact.AUTOSCALE
                | UpdateImpact.REDRAW
            ),
            getter="get_autoscalex_on",
            setter="set_autoscalex_on",
        ),
        PropertySpec(
            "autoscaley_on",
            bool,
            True,
            editor="check",
            impact=(
                UpdateImpact.RELIM
                | UpdateImpact.AUTOSCALE
                | UpdateImpact.REDRAW
            ),
            getter="get_autoscaley_on",
            setter="set_autoscaley_on",
        ),
        PropertySpec(
            "y_lower_reserve",
            float,
            0.0,
            editor="double_spin",
            minimum=0.0,
            maximum=0.8999,
            step=0.01,
            decimals=4,
            validator=_y_lower_reserve_value,
            getter=read_y_lower_reserve,
            setter=write_y_lower_reserve,
            impact=(
                UpdateImpact.RELIM
                | UpdateImpact.AUTOSCALE
                | UpdateImpact.REDRAW
            ),
        ),
        PropertySpec(
            "color_cycle",
            dict,
            None,
            editor="auto",
            allow_none=True,
            getter=lambda _axes: None,
            setter=lambda _axes, _value: None,
        ),
        PropertySpec("xmargin", float, 0.05, editor="double_spin", minimum=-0.5, maximum=10.0),
        PropertySpec("ymargin", float, 0.05, editor="double_spin", minimum=-0.5, maximum=10.0),
        PropertySpec("adjustable", str, "box", editor="combo", choices=("box", "datalim")),
        PropertySpec(
            "anchor",
            (str, tuple),
            "C",
            editor="axes_anchor",
            normalizer=_anchor,
        ),
        PropertySpec(
            "box_aspect",
            float,
            None,
            editor="double_spin",
            allow_none=True,
            minimum=0.0,
        ),
        PropertySpec(
            "axisbelow",
            (bool, str),
            "line",
            editor="combo",
            choices=(True, False, "line"),
        ),
        PropertySpec(
            "frameon",
            bool,
            True,
            editor="check",
            getter="get_frame_on",
            setter="set_frame_on",
        ),
        PropertySpec("zorder", float, 0.0, editor="double_spin"),
        PropertySpec(
            "rasterization_zorder",
            float,
            None,
            editor="double_spin",
            allow_none=True,
            advanced=True,
        ),
        PropertySpec(
            "alpha",
            float,
            None,
            editor="double_spin",
            allow_none=True,
            minimum=0.0,
            maximum=1.0,
            advanced=True,
        ),
        PropertySpec("label", str, "", editor="text", advanced=True),
    ) + _ARTIST_EXPORT_PROPERTIES
    CAPABILITIES = ContainerController.CAPABILITIES | frozenset(
        {"axes_style", "range"}
    )

    def __init__(self, state: ComponentState, **kwargs: Any) -> None:
        self._color_cycle = deepcopy(state.properties.get("color_cycle"))
        super().__init__(state, **kwargs)

    def _validate_data(self, state: ComponentState) -> None:
        _exact_data_fields(state, {"subplot"})
        subplot = state.data["subplot"]
        if not isinstance(subplot, dict):
            raise ComponentValidationError(
                "Axes subplot data must be an object."
            )
        expected = {
            "layout_id",
            "row",
            "column",
            "layer",
            "share_x_group",
            "share_y_group",
        }
        if set(subplot) != expected:
            raise ComponentValidationError(
                f"Axes subplot fields must be {sorted(expected)!r}."
            )
        if not isinstance(subplot["layout_id"], str) or not subplot[
            "layout_id"
        ].strip():
            raise ComponentValidationError("Axes layout id is invalid.")
        for key in ("row", "column"):
            value = subplot[key]
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ComponentValidationError(f"Axes subplot {key} is invalid.")
        if subplot["layer"] not in {"primary", "right_y"}:
            raise ComponentValidationError("Axes subplot layer is invalid.")
        for key in ("share_x_group", "share_y_group"):
            value = subplot[key]
            if value is not None and (
                not isinstance(value, str) or not value.strip()
            ):
                raise ComponentValidationError(
                    f"Axes subplot {key} is invalid."
                )
        if subplot["layer"] == "right_y" and subplot["share_y_group"] is not None:
            raise ComponentValidationError(
                "A right Y Axes cannot join a shared Y group."
            )

    def _read_property(self, target: Axes, spec: PropertySpec) -> Any:
        if spec.key == "color_cycle":
            return deepcopy(self._color_cycle)
        return super()._read_property(target, spec)

    def _write_property(
        self, target: Axes, spec: PropertySpec, value: Any
    ) -> None:
        if spec.key == "color_cycle":
            self._color_cycle = deepcopy(value)
            return
        super()._write_property(target, spec, value)

    def _replacement_impacts(
        self,
        impacts: UpdateImpact,
        state: ComponentState,
    ) -> UpdateImpact:
        # A complete Axes state carries authoritative limits.  Applying xlim
        # and ylim temporarily disables Matplotlib autoscaling before the
        # persisted flags are restored; relim/autoscale here would overwrite
        # those explicit limits.  Property-only mutations retain the normal
        # immediate autoscale impact.
        del state
        return impacts & ~(UpdateImpact.RELIM | UpdateImpact.AUTOSCALE)

    def _restore_transaction_snapshot(self, snapshot) -> None:
        super()._restore_transaction_snapshot(snapshot)
        target_properties = snapshot[2]
        specs = self.property_specs()
        # Margins and box/aspect setters may invoke autoscale_view.  Restore
        # ordered limits after those side effects, then restore autoscale flags.
        for key in ("xlim", "ylim", "autoscalex_on", "autoscaley_on"):
            if key in target_properties:
                self._write_property(
                    self.resolve_target(),
                    specs[key],
                    deepcopy(target_properties[key]),
                )

    def prepare_remove(self) -> AxesSubtreeRemovalHandle:
        """Capture the Axes plus Colorbar-owned auxiliary Axes atomically."""

        colorbars = ()
        if self._registry is not None:
            colorbars = tuple(
                controller.resolve_target()
                for controller in self._registry.query(
                    kind=ComponentKind.COLORBAR,
                    parent_id=self.component_id,
                )
            )
        return MATPLOTLIB_REMOVAL.prepare_axes_subtree(
            self.resolve_target(),
            colorbars,
        )

    def commit_remove(self, handle: AxesSubtreeRemovalHandle) -> None:
        """Temporarily detach an Axes without notifying Matplotlib observers."""

        MATPLOTLIB_REMOVAL.commit(handle)

    def rollback_remove(self, handle: AxesSubtreeRemovalHandle) -> None:
        """Restore the exact Axes containers and current-Axes stack."""

        MATPLOTLIB_REMOVAL.rollback(handle)

    def _finalize_remove(self, handle: AxesSubtreeRemovalHandle) -> None:
        """Publish Matplotlib's Axes removal only after Registry commit."""

        MATPLOTLIB_REMOVAL.finalize(handle)
