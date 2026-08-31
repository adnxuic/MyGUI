"""Strict values and safe reversible mappings for Secondary Axis components."""

from __future__ import annotations

from copy import deepcopy
import math
from typing import Any, Callable, Mapping

import numpy as np

from mygui.database.safe_expression import (
    UnsafeExpressionError,
    compile_math_expression,
    evaluate_math_expression,
)

from .errors import ComponentValidationError


PRESET_UNIT_TRANSFORMS: dict[str, tuple[str, str]] = {
    "identity": ("x", "x"),
    "degrees_to_radians": ("x * pi / 180", "x * 180 / pi"),
    "radians_to_degrees": ("x * 180 / pi", "x * pi / 180"),
    "celsius_to_fahrenheit": ("x * 9 / 5 + 32", "(x - 32) * 5 / 9"),
    "fahrenheit_to_celsius": ("(x - 32) * 5 / 9", "x * 9 / 5 + 32"),
    "frequency_to_period": ("1 / x", "1 / x"),
}

DEFAULT_UNIT_TRANSFORM = {"kind": "preset", "name": "identity"}
DEFAULT_SECONDARY_X_PLACEMENT = {"kind": "edge", "side": "top"}
DEFAULT_SECONDARY_Y_PLACEMENT = {"kind": "edge", "side": "right"}


def _mapping(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ComponentValidationError(f"{label} must be an object.")
    return dict(value)


def _exact(value: Mapping[str, Any], keys: set[str], label: str) -> None:
    if set(value) != keys:
        raise ComponentValidationError(f"{label} requires exactly {sorted(keys)!r}.")


def _finite(value: Any, label: str) -> float:
    if isinstance(value, bool):
        raise ComponentValidationError(f"{label} must be a finite number.")
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ComponentValidationError(f"{label} must be a finite number.") from exc
    if not math.isfinite(result):
        raise ComponentValidationError(f"{label} must be a finite number.")
    return result


def normalize_unit_transform(value: Any) -> dict[str, Any]:
    """Return the strict tagged unit-transform wire record."""

    record = _mapping(value, "Unit transform")
    kind = str(record.get("kind", ""))
    if kind == "preset":
        _exact(record, {"kind", "name"}, "Preset unit transform")
        name = str(record["name"])
        if name not in PRESET_UNIT_TRANSFORMS:
            raise ComponentValidationError(f"Unsupported unit-transform preset {name!r}.")
        return {"kind": kind, "name": name}
    if kind == "affine":
        _exact(record, {"kind", "scale", "offset"}, "Affine unit transform")
        scale = _finite(record["scale"], "Affine scale")
        if scale == 0.0:
            raise ComponentValidationError("Affine scale must not be zero.")
        return {
            "kind": kind,
            "scale": scale,
            "offset": _finite(record["offset"], "Affine offset"),
        }
    if kind == "custom":
        _exact(record, {"kind", "forward", "inverse"}, "Custom unit transform")
        forward = str(record["forward"]).strip()
        inverse = str(record["inverse"]).strip()
        try:
            compile_math_expression(forward, {"x"})
            compile_math_expression(inverse, {"x"})
        except UnsafeExpressionError as exc:
            raise ComponentValidationError(f"Invalid custom unit transform: {exc}") from exc
        return {"kind": kind, "forward": forward, "inverse": inverse}
    raise ComponentValidationError("Unit transform kind must be preset, affine, or custom.")


def normalize_secondary_axis_placement(
    value: Any,
    *,
    orientation: str | None = None,
) -> dict[str, Any]:
    """Return one strict edge, Axes-fraction, or data placement record."""

    record = _mapping(value, "Secondary Axis placement")
    kind = str(record.get("kind", ""))
    if kind == "edge":
        _exact(record, {"kind", "side"}, "Secondary Axis edge placement")
        side = str(record["side"])
        allowed = (
            {"top", "bottom"}
            if orientation == "x"
            else {"left", "right"}
            if orientation == "y"
            else {"top", "bottom", "left", "right"}
        )
        if side not in allowed:
            raise ComponentValidationError(
                f"Edge {side!r} is incompatible with a secondary {orientation or ''} axis."
            )
        return {"kind": kind, "side": side}
    if kind == "position":
        _exact(
            record,
            {"kind", "coordinate_system", "value"},
            "Secondary Axis position placement",
        )
        coordinate_system = str(record["coordinate_system"])
        if coordinate_system not in {"axes_fraction", "data"}:
            raise ComponentValidationError(
                "Secondary Axis position coordinates must be axes_fraction or data."
            )
        return {
            "kind": kind,
            "coordinate_system": coordinate_system,
            "value": _finite(record["value"], "Secondary Axis position"),
        }
    raise ComponentValidationError("Secondary Axis placement kind must be edge or position.")


def secondary_axis_placement_key(value: Any, *, orientation: str) -> tuple[str, float]:
    """Return a normalized uniqueness key for one parent/orientation."""

    placement = normalize_secondary_axis_placement(value, orientation=orientation)
    if placement["kind"] == "edge":
        fraction = 1.0 if placement["side"] in {"top", "right"} else 0.0
        return ("axes_fraction", fraction)
    return (placement["coordinate_system"], placement["value"])


def _expression_function(expression: str) -> Callable[[Any], np.ndarray | float]:
    def evaluate(values: Any):
        source = np.asarray(values, dtype=float)
        scalar = source.ndim == 0
        flat = source.reshape(-1)
        result = evaluate_math_expression(expression, {"x": flat})
        if np.isscalar(result):
            output = np.full(flat.shape, result, dtype=float)
        else:
            output = np.asarray(result)
        if output.shape != flat.shape or np.iscomplexobj(output):
            raise ValueError("Unit transform must return real values matching its input shape.")
        output = output.astype(float, copy=False).reshape(source.shape)
        return float(output) if scalar else output

    return evaluate


def build_unit_transform_functions(
    value: Any,
) -> tuple[Callable[[Any], Any], Callable[[Any], Any]]:
    """Build bounded forward and inverse callables from a persisted record."""

    transform = normalize_unit_transform(value)
    kind = transform["kind"]
    if kind == "preset":
        forward, inverse = PRESET_UNIT_TRANSFORMS[transform["name"]]
    elif kind == "affine":
        scale = transform["scale"]
        offset = transform["offset"]
        forward = f"x * ({scale!r}) + ({offset!r})"
        inverse = f"(x - ({offset!r})) / ({scale!r})"
    else:
        forward, inverse = transform["forward"], transform["inverse"]
    return _expression_function(forward), _expression_function(inverse)


def validate_unit_transform_domain(
    value: Any,
    lower: float,
    upper: float,
    *,
    samples: int = 257,
    source_values: Any | None = None,
) -> None:
    """Validate finite monotonic output and both round trips over a domain."""

    transform = normalize_unit_transform(value)
    forward, inverse = build_unit_transform_functions(transform)
    low, high = sorted((_finite(lower, "Domain lower bound"), _finite(upper, "Domain upper bound")))
    if source_values is None:
        source = np.linspace(low, high, samples, dtype=float)
    else:
        source = np.asarray(source_values, dtype=float)
        if source.shape != (samples,) or not np.all(np.isfinite(source)):
            raise ComponentValidationError(
                "Parent-scale domain samples must be finite and one-dimensional."
            )
    try:
        mapped = np.asarray(forward(source), dtype=float)
        restored = np.asarray(inverse(mapped), dtype=float)
        remapped = np.asarray(forward(inverse(mapped)), dtype=float)
    except (ArithmeticError, TypeError, ValueError, UnsafeExpressionError) as exc:
        raise ComponentValidationError(
            f"Unit transform is invalid on the current parent domain: {exc}"
        ) from exc
    if mapped.shape != source.shape or not np.all(np.isfinite(mapped)):
        raise ComponentValidationError(
            "Unit transform must return finite values across the current parent domain."
        )
    difference = np.diff(mapped)
    if not (np.all(difference > 0.0) or np.all(difference < 0.0)):
        raise ComponentValidationError(
            "Unit transform must be strictly monotonic on the current parent domain."
        )
    if not np.allclose(restored, source, rtol=1e-9, atol=1e-12):
        raise ComponentValidationError(
            "Forward and inverse unit transforms do not round-trip the parent domain."
        )
    if not np.allclose(remapped, mapped, rtol=1e-9, atol=1e-12):
        raise ComponentValidationError(
            "Inverse and forward unit transforms do not round-trip mapped values."
        )


def parent_scale_domain_samples(
    parent_axes: Any,
    orientation: str,
    *,
    samples: int = 257,
) -> np.ndarray:
    """Sample visible limits uniformly in the parent Axis scale space."""

    axis = parent_axes.xaxis if orientation == "x" else parent_axes.yaxis
    limits = parent_axes.get_xlim() if orientation == "x" else parent_axes.get_ylim()
    low, high = sorted(float(value) for value in limits)
    transform = axis.get_transform()
    try:
        transformed = np.asarray(transform.transform([low, high]), dtype=float)
        if transformed.shape != (2,) or not np.all(np.isfinite(transformed)):
            raise ValueError("non-finite transformed limits")
        scaled = np.linspace(transformed[0], transformed[1], samples, dtype=float)
        source = np.asarray(transform.inverted().transform(scaled), dtype=float)
    except Exception as exc:
        raise ComponentValidationError(
            "The current parent Axis scale cannot provide a finite validation domain."
        ) from exc
    if source.shape != (samples,) or not np.all(np.isfinite(source)):
        raise ComponentValidationError(
            "The current parent Axis scale cannot provide a finite validation domain."
        )
    return source


def clone_unit_transform(value: Any) -> dict[str, Any]:
    return deepcopy(normalize_unit_transform(value))
