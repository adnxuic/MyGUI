"""Line and derived curve Controllers."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

import numpy as np
from matplotlib.lines import Line2D

from mygui.database.interpolate_func import (
    MAX_INTERPOLATION_SAMPLES,
    MIN_INTERPOLATION_SAMPLES,
    SMOOTHING_SPLINE_METHOD,
    interpolate_dict,
)
from mygui.database import DataPreprocessSpec
from mygui.database.fit_result import (
    normalize_fit_options_for_storage,
    normalize_fit_result_for_storage,
)
from mygui.database.safe_expression import compile_math_expression

from ..base import ComponentController
from ..errors import ComponentValidationError
from ..models import (
    ComponentChange,
    ComponentKind,
    ComponentMutation,
    ComponentRole,
    ComponentState,
    DeletionPolicy,
    FitEngine,
    PropertySpec,
    RestorePhase,
    ScatterData,
    UpdateImpact,
    XYData,
)
from ..property_values import (
    apply_line_pattern,
    marker_value,
    markevery_value,
    normalize_markevery,
)
from ._helpers import (
    _nonnegative,
    _line_pattern,
    _marker_spec,
    _ARTIST_EXPORT_PROPERTIES,
    _normalize_color,
    _read_color,
    _column_reference,
    _finite_number,
    _exact_data_fields,
)

class LineController(ComponentController[Line2D]):
    """Coordinate state changes for line components."""

    KIND = ComponentKind.LINE
    RESTORE_PHASE = RestorePhase.DYNAMIC
    DELETION_POLICY = DeletionPolicy.REMOVE
    ROLES = frozenset(
        {
            ComponentRole.LINE,
            ComponentRole.FUNCTION_CURVE,
            ComponentRole.DATA_PLOT,
            ComponentRole.FIT_CURVE,
            ComponentRole.INTERPOLATION,
        }
    )
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
            getter=lambda line: _read_color(line.get_color()),
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
            getter=lambda line: _read_color(line.get_markerfacecolor()),
            impact=UpdateImpact.LEGEND | UpdateImpact.REDRAW,
        ),
        PropertySpec(
            "markeredgecolor",
            str,
            "#1f77b4",
            editor="color",
            normalizer=_normalize_color,
            getter=lambda line: _read_color(line.get_markeredgecolor()),
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
            "alpha",
            float,
            None,
            validator=lambda value: 0 <= value <= 1,
            editor="double_spin",
            allow_none=True,
        ),
        PropertySpec("visible", bool, True, editor="check"),
        PropertySpec("zorder", float, 2.0, editor="double_spin"),
        PropertySpec("drawstyle", str, "default", editor="combo", choices=("default", "steps", "steps-pre", "steps-mid", "steps-post")),
        PropertySpec("fillstyle", str, "full", editor="combo", choices=("full", "left", "right", "bottom", "top", "none")),
        PropertySpec(
            "markerfacecoloralt",
            str,
            "none",
            editor="optional_color",
            normalizer=lambda value: str(value) if str(value).lower() == "none" else _normalize_color(value),
            impact=UpdateImpact.LEGEND | UpdateImpact.REDRAW,
        ),
        PropertySpec("markevery", dict, {"kind": "all"}, editor="markevery", normalizer=normalize_markevery),
        PropertySpec(
            "gapcolor",
            str,
            None,
            editor="optional_color",
            allow_none=True,
            normalizer=lambda value: None if value is None else _normalize_color(value),
        ),
        PropertySpec("dash_capstyle", str, "butt", editor="combo", choices=("butt", "projecting", "round")),
        PropertySpec("dash_joinstyle", str, "round", editor="combo", choices=("miter", "round", "bevel")),
        PropertySpec("solid_capstyle", str, "projecting", editor="combo", choices=("butt", "projecting", "round")),
        PropertySpec("solid_joinstyle", str, "round", editor="combo", choices=("miter", "round", "bevel")),
        PropertySpec("antialiased", bool, True, editor="check", advanced=True),
    ) + _ARTIST_EXPORT_PROPERTIES
    CAPABILITIES = frozenset(
        {"line", "data", "label", "color", "line_style", "marker"}
    )
    DELETE_IMPACTS = (
        UpdateImpact.RELIM
        | UpdateImpact.AUTOSCALE
        | UpdateImpact.LEGEND
        | UpdateImpact.REDRAW
    )

    def __init__(self, state: ComponentState, **kwargs: Any) -> None:
        if (
            state.role
            in {
                ComponentRole.DATA_PLOT,
                ComponentRole.INTERPOLATION,
                ComponentRole.FIT_CURVE,
            }
            and "preprocess" not in state.data
        ):
            data = deepcopy(state.data)
            data["preprocess"] = DataPreprocessSpec().to_dict()
            state = state.clone(data=data)
        self._line_pattern_value = _line_pattern(
            state.properties.get("linestyle", {"kind": "preset", "value": "-"})
        )
        self._marker_spec_value = _marker_spec(
            state.properties.get("marker", {"kind": "symbol", "value": "None"})
        )
        self._markevery_spec_value = normalize_markevery(
            state.properties.get("markevery", {"kind": "all"})
        )
        super().__init__(state, **kwargs)

    def _read_property(self, target: Line2D, spec: PropertySpec) -> Any:
        if spec.key in {"linestyle", "marker", "markevery"}:
            return deepcopy(
                {
                    "linestyle": self._line_pattern_value,
                    "marker": self._marker_spec_value,
                    "markevery": self._markevery_spec_value,
                }[spec.key]
            )
        return super()._read_property(target, spec)

    def _write_property(self, target: Line2D, spec: PropertySpec, value: Any) -> None:
        if spec.key == "linestyle":
            apply_line_pattern(target, value)
            self._line_pattern_value = _line_pattern(value)
            return
        if spec.key == "marker":
            target.set_marker(marker_value(value))
            self._marker_spec_value = _marker_spec(value)
            return
        if spec.key == "markevery":
            target.set_markevery(markevery_value(value))
            self._markevery_spec_value = normalize_markevery(value)
            return
        super()._write_property(target, spec, value)

    def _validate_data(self, state: ComponentState) -> None:
        role = state.role
        if role is ComponentRole.LINE:
            _exact_data_fields(state, {"x", "y"})
            self._validate_xy_values(state.data["x"], state.data["y"])
            return
        if role is ComponentRole.FUNCTION_CURVE:
            _exact_data_fields(
                state, {"expression", "x_start", "x_stop"}
            )
            expression = state.data["expression"]
            if not isinstance(expression, str) or not expression.strip():
                raise ComponentValidationError(
                    "Function curve expression must be non-empty."
                )
            try:
                compile_math_expression(expression, {"x"})
            except ValueError as exc:
                raise ComponentValidationError(
                    f"Function curve expression is invalid: {exc}"
                ) from exc
            _finite_number(state.data["x_start"], "x_start")
            _finite_number(state.data["x_stop"], "x_stop")
            return
        if role is ComponentRole.DATA_PLOT:
            _exact_data_fields(state, {"x_ref", "y_ref", "preprocess"})
            _column_reference(state.data["x_ref"], "x_ref")
            _column_reference(state.data["y_ref"], "y_ref")
            DataPreprocessSpec.from_dict(state.data["preprocess"])
            return
        if role is ComponentRole.INTERPOLATION:
            expected = {
                "x_ref",
                "y_ref",
                "method",
                "k",
                "samples",
                "lam",
                "lam_auto",
                "preprocess",
            }
            _exact_data_fields(state, expected)
            _column_reference(state.data["x_ref"], "x_ref")
            _column_reference(state.data["y_ref"], "y_ref")
            DataPreprocessSpec.from_dict(state.data["preprocess"])
            method = state.data["method"]
            if method not in interpolate_dict:
                raise ComponentValidationError(
                    f"Unknown interpolation method: {method!r}."
                )
            k = state.data["k"]
            if isinstance(k, bool) or not isinstance(k, int) or not 1 <= k <= 5:
                raise ComponentValidationError(
                    "Interpolation order k must be between 1 and 5."
                )
            samples = state.data["samples"]
            if (
                isinstance(samples, bool)
                or not isinstance(samples, int)
                or not MIN_INTERPOLATION_SAMPLES
                <= samples
                <= MAX_INTERPOLATION_SAMPLES
            ):
                raise ComponentValidationError(
                    "Interpolation samples are outside the supported range."
                )
            lam_auto = state.data["lam_auto"]
            if not isinstance(lam_auto, bool):
                raise ComponentValidationError(
                    "Interpolation lam_auto must be boolean."
                )
            lam = state.data["lam"]
            if lam is not None and _finite_number(lam, "lam") < 0:
                raise ComponentValidationError(
                    "Interpolation lambda cannot be negative."
                )
            if (
                method == SMOOTHING_SPLINE_METHOD
                and not lam_auto
                and lam is None
            ):
                raise ComponentValidationError(
                    "Manual smoothing spline requires lambda."
                )
            return
        if role is ComponentRole.FIT_CURVE:
            expected = {
                "x_ref",
                "y_ref",
                "engine",
                "fit_type",
                "fit_options",
                "fit_result",
                "expression",
                "x_start",
                "x_stop",
                "preprocess",
            }
            _exact_data_fields(state, expected)
            _column_reference(state.data["x_ref"], "x_ref")
            _column_reference(state.data["y_ref"], "y_ref")
            DataPreprocessSpec.from_dict(state.data["preprocess"])
            try:
                FitEngine(state.data["engine"])
            except ValueError as exc:
                raise ComponentValidationError(
                    "Fitting engine must be Python or Matlab."
                ) from exc
            try:
                normalized_options = normalize_fit_options_for_storage(
                    state.data["fit_options"]
                )
                normalized_result = normalize_fit_result_for_storage(
                    state.data["fit_result"]
                )
            except ValueError as exc:
                raise ComponentValidationError(str(exc)) from exc
            if normalized_options != state.data["fit_options"]:
                raise ComponentValidationError(
                    "Fit options must use null for unbounded values."
                )
            if normalized_result != state.data["fit_result"]:
                raise ComponentValidationError(
                    "Fit result must use null for undefined statistics."
                )
            if not isinstance(state.data["expression"], str):
                raise ComponentValidationError(
                    "Fit expression must be a string."
                )
            if state.data["expression"].strip():
                try:
                    compile_math_expression(
                        state.data["expression"],
                        {"x"},
                    )
                except ValueError as exc:
                    raise ComponentValidationError(
                        f"Fit expression is invalid: {exc}"
                    ) from exc
            _finite_number(state.data["x_start"], "x_start")
            _finite_number(state.data["x_stop"], "x_stop")
            return
        raise ComponentValidationError(
            f"Unsupported line role: {role.value!r}."
        )

    @staticmethod
    def _validate_xy_values(
        x: Any,
        y: Any,
        *,
        allow_gaps: bool = False,
    ) -> tuple[np.ndarray, np.ndarray]:
        x_values = np.asarray(x)
        y_values = np.asarray(y)
        if x_values.ndim != 1 or y_values.ndim != 1:
            raise ComponentValidationError(
                "Line data must be one-dimensional."
            )
        if len(x_values) != len(y_values):
            raise ComponentValidationError(
                "Line X and Y data must have the same length."
            )
        try:
            numeric_y = y_values.astype(float)
            if np.issubdtype(x_values.dtype, np.datetime64):
                invalid_x = np.zeros(len(x_values), dtype=bool)
                missing_x = np.isnat(x_values.astype("datetime64[ns]"))
            else:
                numeric_x = x_values.astype(float)
                invalid_x = np.isinf(numeric_x)
                missing_x = np.isnan(numeric_x)
        except (TypeError, ValueError) as exc:
            raise ComponentValidationError(
                "Line data must contain numeric or datetime X values "
                "and numeric Y values."
            ) from exc
        if allow_gaps:
            if invalid_x.any() or np.isinf(numeric_y).any():
                raise ComponentValidationError(
                    "Line data must not contain infinity."
                )
            # A masked row may be represented by NaN/NaT in either axis.
            # Matplotlib uses these values to create intentional line gaps.
            del missing_x
        elif (
            invalid_x.any()
            or missing_x.any()
            or not np.isfinite(numeric_y).all()
        ):
            raise ComponentValidationError(
                "Line data must not contain NaN, NaT, or infinity."
            )
        return x_values, y_values

    def _validate_runtime_data(
        self,
        target: Line2D,
        runtime_data: Any,
        state: ComponentState,
    ) -> None:
        del target
        if not isinstance(runtime_data, XYData):
            raise ComponentValidationError(
                "Line runtime data must be XYData."
            )
        self._validate_xy_values(
            runtime_data.x,
            runtime_data.y,
            allow_gaps=state.role is ComponentRole.DATA_PLOT,
        )

    def _capture_runtime_data(self, target: Line2D) -> XYData:
        return XYData(
            np.asarray(target.get_xdata()).copy(),
            np.asarray(target.get_ydata()).copy(),
        )

    def _apply_runtime_data(
        self,
        target: Line2D,
        runtime_data: Any,
        state: ComponentState,
    ) -> None:
        self._validate_runtime_data(target, runtime_data, state)
        target.set_data(
            np.asarray(runtime_data.x),
            np.asarray(runtime_data.y),
        )

    def _restore_runtime_data(
        self,
        target: Line2D,
        runtime_data: Any,
    ) -> None:
        if isinstance(runtime_data, XYData):
            target.set_data(runtime_data.x, runtime_data.y)

    def _runtime_data_impacts(
        self,
        runtime_data: Any,
        state: ComponentState,
    ) -> UpdateImpact:
        del runtime_data, state
        return (
            UpdateImpact.RELIM
            | UpdateImpact.AUTOSCALE
            | UpdateImpact.REDRAW
        )

    def _runtime_data_is_empty(
        self,
        target: Line2D,
        runtime_data: Any,
        state: ComponentState,
    ) -> bool:
        del target, state
        x_values = np.asarray(runtime_data.x)
        y_values = np.asarray(runtime_data.y)
        if not len(x_values):
            return True
        if np.issubdtype(x_values.dtype, np.datetime64):
            x_valid = ~np.isnat(x_values.astype("datetime64[ns]"))
        else:
            try:
                x_valid = np.isfinite(x_values.astype(float))
            except (TypeError, ValueError):
                return False
        try:
            y_valid = np.isfinite(y_values.astype(float))
        except (TypeError, ValueError):
            return False
        return not bool((x_valid & y_valid).any())

    def apply_role_data(
        self,
        data: dict[str, Any],
        *,
        drawable: XYData | ScatterData,
    ) -> ComponentChange:
        """Apply role data."""

        return self.apply_mutation(
            ComponentMutation(
                self.component_id,
                data=data,
                runtime_data=drawable,
            )
        )

    def set_xy_data(
        self,
        x: Any,
        y: Any,
        *,
        persist: bool = False,
    ) -> ComponentChange:
        """Set xy data."""

        x_values = np.asarray(x)
        y_values = np.asarray(y)
        data = deepcopy(self._state.data)
        if persist or self._state.role is ComponentRole.LINE:
            data.update(
                x=x_values.tolist(),
                y=y_values.tolist(),
            )
        return self.apply_role_data(
            data,
            drawable=XYData(x_values, y_values),
        )

    def _apply_data(self, target: Line2D, state: ComponentState) -> None:
        if "x" in state.data or "y" in state.data:
            if "x" not in state.data or "y" not in state.data:
                raise ComponentValidationError(
                    "Persisted line data requires both x and y."
                )
            x_values = np.asarray(state.data["x"])
            y_values = np.asarray(state.data["y"])
            if x_values.ndim != 1 or y_values.ndim != 1 or len(x_values) != len(y_values):
                raise ComponentValidationError("Persisted line data is invalid.")
            target.set_data(x_values, y_values)

    def _is_empty(self, target: Line2D, state: ComponentState) -> bool:
        return len(target.get_xdata()) == 0

    def _data_impacts(
        self,
        before: ComponentState | None,
        after: ComponentState,
    ) -> UpdateImpact:
        if "x" in after.data or "y" in after.data:
            return (
                UpdateImpact.RELIM
                | UpdateImpact.AUTOSCALE
                | UpdateImpact.REDRAW
            )
        return UpdateImpact.NONE


class FunctionCurveController(LineController):
    """Coordinate state changes for function curve components."""

    ROLES = frozenset({ComponentRole.FUNCTION_CURVE})
    CAPABILITIES = LineController.CAPABILITIES | frozenset(
        {"function_curve"}
    )


class DataPlotController(LineController):
    """Coordinate state changes for data plot components."""

    ROLES = frozenset({ComponentRole.DATA_PLOT})
    CAPABILITIES = LineController.CAPABILITIES | frozenset(
        {"data_reference", "auto_refresh"}
    )


class FitCurveController(LineController):
    """Coordinate state changes for fit curve components."""

    ROLES = frozenset({ComponentRole.FIT_CURVE})
    CAPABILITIES = LineController.CAPABILITIES | frozenset(
        {"data_reference", "manual_refresh", "fit"}
    )


class InterpolationController(LineController):
    """Coordinate state changes for interpolation components."""

    ROLES = frozenset({ComponentRole.INTERPOLATION})
    CAPABILITIES = LineController.CAPABILITIES | frozenset(
        {"data_reference", "auto_refresh", "interpolation"}
    )
