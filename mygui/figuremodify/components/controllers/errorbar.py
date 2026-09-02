"""Error Bar Controller coordinating its composite Matplotlib runtime."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

import numpy as np

from ..base import ComponentController
from ..errors import ComponentValidationError
from ..models import (
    ChangeStatus,
    ComponentChange,
    ComponentKind,
    ComponentMutation,
    ComponentRole,
    ComponentState,
    DeletionPolicy,
    ErrorBarData,
    ErrorBarRuntimeSnapshot,
    PropertySpec,
    RestorePhase,
    UpdateImpact,
)
from ..property_values import (
    DEFAULT_ERROR_SPEC,
    error_spec_references,
    normalize_error_every,
    normalize_error_spec,
)
from ._helpers import (
    _column_reference,
    _exact_data_fields,
    _line_pattern,
    _marker_spec,
    _nonnegative,
    _normalize_color,
    _read_color,
    apply_data_component_mutation,
)
from mygui.database import DataPreprocessSpec

ERROR_BAR_DATA_FIELDS = frozenset(
    {"x_ref", "y_ref", "xerr", "yerr", "preprocess"}
)

# The exact schema-v20 Error Bar property set. The v20 validator pins this
# closed set so extended v21 records can never round-trip into v20 files.
ERROR_BAR_V20_PROPERTY_KEYS = frozenset(
    {
        "label",
        "color",
        "linestyle",
        "linewidth",
        "marker",
        "markersize",
        "markerfacecolor",
        "markeredgecolor",
        "ecolor",
        "elinewidth",
        "capsize",
        "capthick",
        "barsabove",
        "alpha",
        "visible",
        "zorder",
        "clip_on",
    }
)

# Deterministic values injected by the strict v20→v21 and template v4→v5
# migrations. They match the v21 PropertySpec defaults exactly.
ERROR_BAR_V21_DEFAULTS: dict[str, Any] = {
    "markeredgewidth": 1.0,
    "markerfacecoloralt": "none",
    "fillstyle": "full",
    "drawstyle": "default",
    "antialiased": True,
    "error_linestyle": {"kind": "preset", "value": "-"},
    "error_capstyle": None,
    "error_antialiased": True,
    "errorevery": {"kind": "all"},
    "lolims": False,
    "uplims": False,
    "xlolims": False,
    "xuplims": False,
}

# Properties that change which Matplotlib artists exist or how error
# segments are sampled; mutating one rebuilds the container transactionally.
ERROR_BAR_STRUCTURE_PROPERTY_KEYS = frozenset(
    {"errorevery", "lolims", "uplims", "xlolims", "xuplims"}
)


class ErrorBarController(ComponentController[Any]):
    """Coordinate state changes for Error Bar components.

    The Controller target is the stable :class:`ErrorBarRuntime`, never an
    individual child artist.  Style mutations fan out to the data line,
    caplines, and barline collections owned by the runtime; data mutations
    rebuild the whole container transactionally.
    """

    KIND = ComponentKind.ERRORBAR
    RESTORE_PHASE = RestorePhase.DYNAMIC
    DELETION_POLICY = DeletionPolicy.REMOVE
    ROLES = frozenset({ComponentRole.ERROR_BAR})
    PROPERTY_SPECS = (
        PropertySpec(
            "label",
            str,
            "",
            editor="text",
            impact=UpdateImpact.LEGEND | UpdateImpact.REDRAW,
        ),
        PropertySpec(
            "color",
            str,
            "#1f77b4",
            editor="color",
            normalizer=_normalize_color,
            getter=lambda runtime: _read_color(runtime.get_color()),
            impact=UpdateImpact.LEGEND | UpdateImpact.REDRAW,
        ),
        PropertySpec(
            "linestyle",
            dict,
            {"kind": "preset", "value": "-"},
            editor="line_pattern",
            normalizer=_line_pattern,
            impact=UpdateImpact.LEGEND | UpdateImpact.REDRAW,
        ),
        PropertySpec(
            "linewidth",
            float,
            1.5,
            validator=_nonnegative,
            editor="double_spin",
            impact=UpdateImpact.LEGEND | UpdateImpact.REDRAW,
        ),
        PropertySpec(
            "marker",
            dict,
            {"kind": "symbol", "value": "None"},
            editor="marker_spec",
            normalizer=_marker_spec,
            impact=UpdateImpact.LEGEND | UpdateImpact.REDRAW,
        ),
        PropertySpec(
            "markersize",
            float,
            6.0,
            validator=_nonnegative,
            editor="double_spin",
            impact=UpdateImpact.LEGEND | UpdateImpact.REDRAW,
        ),
        PropertySpec(
            "markerfacecolor",
            str,
            "#1f77b4",
            editor="color",
            normalizer=_normalize_color,
            getter=lambda runtime: _read_color(runtime.get_markerfacecolor()),
            impact=UpdateImpact.LEGEND | UpdateImpact.REDRAW,
        ),
        PropertySpec(
            "markeredgecolor",
            str,
            "#1f77b4",
            editor="color",
            normalizer=_normalize_color,
            getter=lambda runtime: _read_color(runtime.get_markeredgecolor()),
            impact=UpdateImpact.LEGEND | UpdateImpact.REDRAW,
        ),
        PropertySpec(
            "markeredgewidth",
            float,
            1.0,
            validator=_nonnegative,
            editor="double_spin",
            impact=UpdateImpact.LEGEND | UpdateImpact.REDRAW,
        ),
        PropertySpec(
            "markerfacecoloralt",
            str,
            "none",
            editor="optional_color",
            normalizer=lambda value: (
                str(value)
                if str(value).lower() == "none"
                else _normalize_color(value)
            ),
            impact=UpdateImpact.LEGEND | UpdateImpact.REDRAW,
        ),
        PropertySpec(
            "fillstyle",
            str,
            "full",
            editor="combo",
            choices=("full", "left", "right", "bottom", "top", "none"),
            impact=UpdateImpact.LEGEND | UpdateImpact.REDRAW,
        ),
        PropertySpec(
            "drawstyle",
            str,
            "default",
            editor="combo",
            choices=(
                "default",
                "steps",
                "steps-pre",
                "steps-mid",
                "steps-post",
            ),
            impact=UpdateImpact.REDRAW,
        ),
        PropertySpec(
            "antialiased",
            bool,
            True,
            editor="check",
            impact=UpdateImpact.REDRAW,
        ),
        PropertySpec(
            "ecolor",
            str,
            "#1f77b4",
            editor="color",
            normalizer=_normalize_color,
            getter=lambda runtime: _read_color(runtime.get_ecolor()),
            impact=UpdateImpact.REDRAW,
        ),
        PropertySpec(
            "elinewidth",
            float,
            1.5,
            validator=_nonnegative,
            editor="double_spin",
            impact=UpdateImpact.REDRAW,
        ),
        PropertySpec(
            "capsize",
            float,
            0.0,
            validator=_nonnegative,
            editor="double_spin",
            impact=UpdateImpact.REDRAW,
        ),
        PropertySpec(
            "capthick",
            float,
            1.0,
            validator=_nonnegative,
            editor="double_spin",
            impact=UpdateImpact.REDRAW,
        ),
        PropertySpec(
            "error_linestyle",
            dict,
            {"kind": "preset", "value": "-"},
            editor="line_pattern",
            normalizer=_line_pattern,
            impact=UpdateImpact.REDRAW,
        ),
        PropertySpec(
            "error_capstyle",
            str,
            None,
            editor="combo",
            choices=("butt", "projecting", "round"),
            allow_none=True,
            impact=UpdateImpact.REDRAW,
        ),
        PropertySpec(
            "error_antialiased",
            bool,
            True,
            editor="check",
            impact=UpdateImpact.REDRAW,
        ),
        PropertySpec(
            "errorevery",
            dict,
            {"kind": "all"},
            editor="error_every",
            normalizer=normalize_error_every,
            impact=(
                UpdateImpact.RELIM
                | UpdateImpact.AUTOSCALE
                | UpdateImpact.LEGEND
                | UpdateImpact.REDRAW
            ),
        ),
        PropertySpec(
            "lolims",
            bool,
            False,
            editor="check",
            impact=(
                UpdateImpact.RELIM
                | UpdateImpact.AUTOSCALE
                | UpdateImpact.LEGEND
                | UpdateImpact.REDRAW
            ),
            tooltip=(
                "Mark Y values as lower limits; Matplotlib then draws an "
                "upward-pointing arrow instead of the upper cap."
            ),
        ),
        PropertySpec(
            "uplims",
            bool,
            False,
            editor="check",
            impact=(
                UpdateImpact.RELIM
                | UpdateImpact.AUTOSCALE
                | UpdateImpact.LEGEND
                | UpdateImpact.REDRAW
            ),
            tooltip=(
                "Mark Y values as upper limits; Matplotlib then draws a "
                "downward-pointing arrow instead of the lower cap."
            ),
        ),
        PropertySpec(
            "xlolims",
            bool,
            False,
            editor="check",
            impact=(
                UpdateImpact.RELIM
                | UpdateImpact.AUTOSCALE
                | UpdateImpact.LEGEND
                | UpdateImpact.REDRAW
            ),
            tooltip=(
                "Mark X values as lower limits; Matplotlib then draws a "
                "right-pointing arrow instead of the upper X cap."
            ),
        ),
        PropertySpec(
            "xuplims",
            bool,
            False,
            editor="check",
            impact=(
                UpdateImpact.RELIM
                | UpdateImpact.AUTOSCALE
                | UpdateImpact.LEGEND
                | UpdateImpact.REDRAW
            ),
            tooltip=(
                "Mark X values as upper limits; Matplotlib then draws a "
                "left-pointing arrow instead of the lower X cap."
            ),
        ),
        PropertySpec(
            "barsabove",
            bool,
            False,
            editor="check",
            impact=UpdateImpact.REDRAW,
        ),
        PropertySpec(
            "alpha",
            float,
            None,
            validator=lambda value: 0 <= value <= 1,
            editor="double_spin",
            allow_none=True,
        ),
        PropertySpec("visible", bool, True, editor="check"),
        PropertySpec("zorder", float, 2.0, editor="double_spin"),
        PropertySpec("clip_on", bool, True, editor="check", advanced=True),
    )
    CAPABILITIES = frozenset(
        {"error_bar", "data_reference", "auto_refresh", "label", "color"}
    )
    DELETE_IMPACTS = (
        UpdateImpact.RELIM
        | UpdateImpact.AUTOSCALE
        | UpdateImpact.LEGEND
        | UpdateImpact.REDRAW
    )

    def __init__(self, state: ComponentState, **kwargs: Any) -> None:
        self._swap_memento: Any = None
        super().__init__(state, **kwargs)

    def set_property(self, key: str, value: Any) -> ComponentChange:
        """Route structural properties through the full mutation path.

        ``errorevery`` and the limit switches change which segments and cap
        artists exist, so they rebuild the container transactionally through
        :meth:`apply_mutation` instead of the plain property write.
        """

        if key in ERROR_BAR_STRUCTURE_PROPERTY_KEYS:
            return self.apply_mutation(
                ComponentMutation(self.component_id, properties={key: value})
            )
        return super().set_property(key, value)

    def _validate_data(self, state: ComponentState) -> None:
        _exact_data_fields(state, ERROR_BAR_DATA_FIELDS)
        _column_reference(state.data["x_ref"], "x_ref")
        _column_reference(state.data["y_ref"], "y_ref")
        normalize_error_spec(state.data["xerr"])
        normalize_error_spec(state.data["yerr"])
        DataPreprocessSpec.from_dict(state.data["preprocess"])

    def _validate_runtime_data(
        self,
        target: Any,
        runtime_data: Any,
        state: ComponentState,
    ) -> None:
        del target, state
        if not isinstance(runtime_data, ErrorBarData):
            raise ComponentValidationError(
                "Error Bar runtime data must be ErrorBarData."
            )
        self._validate_errorbar_values(runtime_data)

    @staticmethod
    def _validate_errorbar_values(data: ErrorBarData) -> None:
        x_values = np.asarray(data.x)
        y_values = np.asarray(data.y)
        if x_values.ndim != 1 or y_values.ndim != 1:
            raise ComponentValidationError(
                "Error Bar data must be one-dimensional."
            )
        if len(x_values) != len(y_values):
            raise ComponentValidationError(
                "Error Bar X and Y data must have the same length."
            )
        length = len(x_values)
        for name, values in (("xerr", data.xerr), ("yerr", data.yerr)):
            if values is None:
                continue
            array = np.asarray(values)
            if array.ndim == 1:
                if len(array) != length:
                    raise ComponentValidationError(
                        f"Error Bar {name} must match X/Y length."
                    )
            elif array.ndim == 2:
                if array.shape != (2, length):
                    raise ComponentValidationError(
                        f"Error Bar {name} must be 2 x N or N."
                    )
            else:
                raise ComponentValidationError(
                    f"Error Bar {name} must be one- or two-dimensional."
                )

    def _capture_runtime_data(self, target: Any) -> Any:
        return ErrorBarRuntimeSnapshot(
            data=target.data,
            properties=deepcopy(target._properties),
        )

    def _apply_runtime_data(
        self,
        target: Any,
        runtime_data: Any,
        state: ComponentState,
    ) -> None:
        self._validate_runtime_data(target, runtime_data, state)
        # Finalize the swap memento of any previously committed rebuild so
        # detached artists are never pinned longer than one mutation.
        self._swap_memento = None
        self._swap_memento = target.rebuild(
            data=runtime_data,
            properties=deepcopy(state.properties),
        )

    def _restore_runtime_data(
        self,
        target: Any,
        runtime_data: Any,
    ) -> None:
        memento, self._swap_memento = self._swap_memento, None
        if memento is not None:
            if target.container is not memento.old_container:
                target.restore_swap(memento)
            return
        if isinstance(runtime_data, ErrorBarRuntimeSnapshot):
            # The exact-identity memento was already consumed; restore an
            # equivalent live container from the captured snapshot.
            target.rebuild(
                data=runtime_data.data,
                properties=deepcopy(runtime_data.properties),
            )

    def _runtime_data_impacts(
        self,
        runtime_data: Any,
        state: ComponentState,
    ) -> UpdateImpact:
        del runtime_data, state
        return (
            UpdateImpact.RELIM
            | UpdateImpact.AUTOSCALE
            | UpdateImpact.LEGEND
            | UpdateImpact.REDRAW
        )

    def _request_updates(
        self, impacts: UpdateImpact, target: Any | None = None
    ) -> None:
        runtime = target if target is not None else self.resolve_target()
        axes = getattr(runtime, "axes", None)
        if UpdateImpact.RELIM in impacts and axes is not None:
            from mygui.figuremodify.matplotlib_adapter import (
                relim_with_errorbars,
            )

            relim_with_errorbars(axes)
            impacts &= ~UpdateImpact.RELIM
        super()._request_updates(impacts, runtime)

    def _publish_change(self, change: ComponentChange) -> None:
        """Publish first, then release the previous detached container."""

        super()._publish_change(change)
        self._swap_memento = None

    def _runtime_data_is_empty(
        self,
        target: Any,
        runtime_data: Any,
        state: ComponentState,
    ) -> bool:
        del target, state
        return len(np.asarray(runtime_data.x)) == 0

    def _is_empty(self, target: Any, state: ComponentState) -> bool:
        return target.is_empty

    def _data_impacts(
        self,
        before: ComponentState | None,
        after: ComponentState,
    ) -> UpdateImpact:
        return (
            UpdateImpact.RELIM
            | UpdateImpact.AUTOSCALE
            | UpdateImpact.LEGEND
            | UpdateImpact.REDRAW
        )

    def apply_role_data(
        self,
        data: dict[str, Any],
        *,
        drawable: ErrorBarData,
    ) -> ComponentChange:
        """Apply data and drawable arrays as one Controller transaction."""

        return apply_data_component_mutation(self, data, drawable=drawable)

    def _properties_require_data_apply(
        self, property_patch: dict[str, Any]
    ) -> bool:
        """Return whether a property patch must rebuild the container.

        ``errorevery`` resamples the drawn error segments and the four limit
        switches change which cap artists Matplotlib replaces with limit
        arrows, so both rebuild through the transactional container swap.
        """

        return bool(
            ERROR_BAR_STRUCTURE_PROPERTY_KEYS.intersection(property_patch)
        )

    def _apply_data(self, target: Any, state: ComponentState) -> None:
        """Rebuild the container from the live arrays and candidate style.

        The drawable arrays are owned by the runtime (data changes arrive via
        ``ErrorBarDataService`` with explicit runtime data), so this hook
        rebuilds with the candidate properties only — exactly the structural
        ``errorevery``/limit-arrow and full-state restore path.
        """

        memento = self._swap_memento
        if (
            memento is not None
            and target.container is not memento.old_container
            and all(
                state.properties.get(key) == memento.old_properties.get(key)
                for key in ERROR_BAR_STRUCTURE_PROPERTY_KEYS
            )
        ):
            # Base Controller rollback re-enters this hook with the pre-change
            # state. Restore the pinned container and artists instead of
            # materializing an equivalent third container.
            target.restore_swap(memento)
            self._swap_memento = None
            return

        self._swap_memento = None
        if all(
            target._properties.get(key) == state.properties.get(key)
            for key in ERROR_BAR_STRUCTURE_PROPERTY_KEYS
        ):
            # A candidate-construction failure leaves the original structure
            # live. The rollback call is therefore a true no-op and must keep
            # that original identity intact.
            return
        self._swap_memento = target.rebuild(
            data=target.data,
            properties=deepcopy(state.properties),
        )

    def refresh_limit_arrows(self) -> ComponentChange:
        """Rebuild limit arrows after the owning Axes direction changed."""

        target = self.resolve_target()
        if not target.limit_arrows_active or not target.direction_changed():
            return ComponentChange(
                self.component_id,
                None,
                self.state,
                self.state,
                ChangeStatus.NOOP,
            )
        before = self._safe_snapshot()
        try:
            self._swap_memento = None
            target.rebuild(
                data=target.data,
                properties=deepcopy(self._state.properties),
            )
        except Exception as exc:
            self._swap_memento = None
            return self._rejected(None, before, str(exc))
        return ComponentChange(
            self.component_id,
            None,
            before,
            self.state,
            ChangeStatus.APPLIED,
            UpdateImpact.REDRAW,
        )

    def prepare_remove(self) -> Any:
        """Pin the container and every owned artist for reversible removal."""

        from ..matplotlib_removal import MATPLOTLIB_REMOVAL

        if self.DELETION_POLICY is not DeletionPolicy.REMOVE:
            raise ComponentValidationError(
                f"{type(self).__name__} does not support physical removal."
            )
        return MATPLOTLIB_REMOVAL.prepare_errorbar(self.resolve_target())

    def set_error_data(
        self,
        x: Any,
        y: Any,
        *,
        xerr: Any = None,
        yerr: Any = None,
    ) -> ComponentChange:
        """Set validated drawable arrays without touching persisted refs."""

        drawable = ErrorBarData(
            np.asarray(x),
            np.asarray(y),
            None if xerr is None else np.asarray(xerr),
            None if yerr is None else np.asarray(yerr),
        )
        self._validate_errorbar_values(drawable)
        return self.apply_mutation(
            ComponentMutation(
                self.component_id,
                runtime_data=drawable,
            )
        )

    @staticmethod
    def error_spec_column_refs(data: dict[str, Any]) -> list[dict[str, str]]:
        """Return every column reference embedded in the persisted specs."""

        refs: list[dict[str, str]] = []
        for key in ("xerr", "yerr"):
            try:
                refs.extend(error_spec_references(data.get(key)))
            except ComponentValidationError:
                continue
        return refs

    @staticmethod
    def default_error_specs() -> dict[str, dict[str, Any]]:
        """Return the closed no-error defaults for both dimensions."""

        return {
            "xerr": deepcopy(DEFAULT_ERROR_SPEC),
            "yerr": deepcopy(DEFAULT_ERROR_SPEC),
        }
