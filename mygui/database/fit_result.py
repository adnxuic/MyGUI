"""Normalize curve-fitting results and compute goodness-of-fit statistics."""

from __future__ import annotations

import json
import math
import re
from copy import deepcopy
from typing import Any

import numpy as np


CONFIDENCE_LEVEL = 0.95
GOODNESS_FIELDS = ("sse", "rsquare", "dfe", "adjrsquare", "rmse")
BOUND_FIELDS = ("Lower", "Upper")


def as_list(value: Any) -> list[Any]:
    """Normalize a scalar or sequence to a list."""

    if value is None:
        return []
    if isinstance(value, (str, bytes)):
        return [value]
    try:
        return list(value)
    except TypeError:
        return [value]


def to_float_or_none(value: Any) -> float | None:
    """Convert a finite scalar to float and undefined values to ``None``."""

    if value is None:
        return None
    if isinstance(value, (list, tuple)) and value:
        value = value[0]
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def coefficient_values(coeff_value: Any) -> list[float]:
    """Return fitted coefficient values in declaration order."""

    values = as_list(coeff_value)
    if values and not isinstance(values[0], (int, float, str, bytes)):
        values = as_list(values[0])
    converted = [float(value) for value in values]
    if not all(math.isfinite(value) for value in converted):
        raise ValueError("Fitted coefficients must all be finite numbers.")
    return converted


def _bound_value(value: Any, field_name: str) -> float | None:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(f"{field_name} bounds must contain numbers or null.") from exc
    if math.isnan(number):
        raise ValueError(f"{field_name} bounds must not contain NaN.")
    if math.isinf(number):
        if field_name == "Lower" and number < 0:
            return None
        if field_name == "Upper" and number > 0:
            return None
        raise ValueError(
            f"{field_name} may use only its outward infinity as an unbounded value."
        )
    return number


def _json_value(value: Any, path: str) -> Any:
    if value is None or isinstance(value, (str, bool)):
        return value
    if isinstance(value, (int, float, np.integer, np.floating)):
        number = float(value)
        if not math.isfinite(number):
            raise ValueError(f"{path} must be finite or null.")
        return int(value) if isinstance(value, (int, np.integer)) else number
    if isinstance(value, (list, tuple)):
        return [_json_value(item, f"{path}[{index}]") for index, item in enumerate(value)]
    if isinstance(value, dict):
        normalized = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise ValueError(f"{path} keys must be strings.")
            normalized[key] = _json_value(item, f"{path}.{key}")
        return normalized
    raise ValueError(f"{path} contains an unsupported value: {type(value).__name__}.")


def normalize_fit_options_for_storage(
    fit_options: dict[str, Any] | None,
) -> dict[str, Any] | None:
    """Return the canonical JSON-safe fitting options representation."""

    if fit_options is None:
        return None
    if not isinstance(fit_options, dict):
        raise ValueError("Fit options must be an object or null.")
    candidate = deepcopy(fit_options)
    for field_name in BOUND_FIELDS:
        if field_name not in fit_options:
            continue
        raw_values = fit_options[field_name]
        if not isinstance(raw_values, (list, tuple)):
            raise ValueError(f"{field_name} bounds must be an array.")
        candidate[field_name] = [
            _bound_value(value, field_name) for value in raw_values
        ]
    return _json_value(candidate, "fit_options")


def fit_options_for_execution(
    fit_options: dict[str, Any] | None,
) -> dict[str, Any]:
    """Expand persisted null bounds to runtime infinities for an adapter."""

    normalized = normalize_fit_options_for_storage(fit_options) or {}
    for field_name, unbounded in (("Lower", float("-inf")), ("Upper", float("inf"))):
        if field_name in normalized:
            normalized[field_name] = [
                unbounded if value is None else value
                for value in normalized[field_name]
            ]
    return normalized


def normalize_fit_result_for_storage(fit_result: Any) -> dict[str, Any] | None:
    """Normalize undefined fit statistics while rejecting invalid coefficients."""

    if fit_result is None:
        return None
    if not isinstance(fit_result, dict):
        raise ValueError("Fit result must be an object or null.")
    candidate = deepcopy(fit_result)
    coefficients = fit_result.get("coefficients")
    if coefficients is not None:
        if not isinstance(coefficients, list):
            raise ValueError("fit_result.coefficients must be an array.")
        normalized_coefficients = []
        for index, coefficient in enumerate(coefficients):
            if not isinstance(coefficient, dict):
                raise ValueError(
                    f"fit_result.coefficients[{index}] must be an object."
                )
            item = deepcopy(coefficient)
            value = to_float_or_none(coefficient.get("value"))
            if value is None:
                raise ValueError(
                    f"fit_result.coefficients[{index}].value must be finite."
                )
            item["value"] = value
            for field_name in ("lower", "upper"):
                if field_name in coefficient:
                    item[field_name] = to_float_or_none(coefficient[field_name])
            normalized_coefficients.append(item)
        candidate["coefficients"] = normalized_coefficients
    goodness = fit_result.get("goodness")
    if goodness is not None:
        if not isinstance(goodness, dict):
            raise ValueError("fit_result.goodness must be an object.")
        candidate["goodness"] = {
            key: to_float_or_none(value)
            for key, value in goodness.items()
        }
    return _json_value(candidate, "fit_result")


def replace_coefficients(expression: str, coefficient_names, coefficient_values_) -> str:
    """Return fit results with replacement coefficient values."""

    result = expression
    pairs = sorted(
        ((str(name), value) for name, value in zip(coefficient_names, coefficient_values_)),
        key=lambda item: len(item[0]),
        reverse=True,
    )
    for name, value in pairs:
        pattern = rf"(?<![A-Za-z0-9_]){re.escape(name)}(?![A-Za-z0-9_])"
        result = re.sub(pattern, str(value), result)
    return result


def confidence_rows(confidence_bounds: Any, coefficient_count: int) -> tuple[list[float | None], list[float | None]]:
    """Normalize confidence-interval data into display rows."""

    rows = as_list(confidence_bounds)
    if len(rows) < 2:
        return [None] * coefficient_count, [None] * coefficient_count
    lower = [to_float_or_none(value) for value in as_list(rows[0])]
    upper = [to_float_or_none(value) for value in as_list(rows[1])]
    lower.extend([None] * max(0, coefficient_count - len(lower)))
    upper.extend([None] * max(0, coefficient_count - len(upper)))
    return lower[:coefficient_count], upper[:coefficient_count]


def loads_json_object(value: Any) -> dict[str, Any]:
    """Parse a JSON object while accepting already-decoded mappings."""

    if value is None:
        return {}
    if isinstance(value, dict):
        return dict(value)
    if isinstance(value, (list, tuple)) and value:
        value = value[0]
    if isinstance(value, bytes):
        value = value.decode("utf-8", errors="replace")
    text = str(value).strip()
    if not text:
        return {}
    parsed = json.loads(text)
    return parsed if isinstance(parsed, dict) else {}


def goodness_to_dict(gof_value: Any) -> dict[str, float | None]:
    """Convert fit goodness statistics to a serializable mapping."""

    if isinstance(gof_value, (str, bytes)):
        try:
            parsed = loads_json_object(gof_value)
        except (TypeError, ValueError, json.JSONDecodeError):
            parsed = {}
    elif isinstance(gof_value, dict):
        parsed = gof_value
    else:
        parsed = {field: getattr(gof_value, field, None) for field in GOODNESS_FIELDS}
    return {field: to_float_or_none(parsed.get(field)) for field in GOODNESS_FIELDS}


def compute_goodness(y_data, y_fit, parameter_count: int) -> dict[str, float | None]:
    """Compute goodness."""

    y = np.asarray(y_data, dtype=float)
    fitted = np.asarray(y_fit, dtype=float)
    residuals = y - fitted
    sse = float(np.sum(residuals ** 2))
    n = int(y.size)
    p = int(parameter_count)
    dfe = n - p
    mean_y = float(np.mean(y)) if n else float("nan")
    sst = float(np.sum((y - mean_y) ** 2)) if n else float("nan")

    if sst > 0:
        rsquare = 1.0 - sse / sst
    elif math.isfinite(sse) and sse <= np.finfo(float).eps:
        rsquare = 1.0
    else:
        rsquare = None

    if dfe > 0:
        rmse = float(math.sqrt(sse / dfe))
        if n > 1 and rsquare is not None:
            adjrsquare = 1.0 - (1.0 - rsquare) * (n - 1) / dfe
        else:
            adjrsquare = None
    else:
        rmse = None
        adjrsquare = None

    return {
        "sse": sse,
        "rsquare": rsquare,
        "dfe": float(dfe),
        "adjrsquare": adjrsquare,
        "rmse": rmse,
    }


def covariance_from_jacobian(jacobian, residuals, dfe: int) -> np.ndarray:
    """Estimate parameter covariance from a fit Jacobian."""

    jac = np.asarray(jacobian, dtype=float)
    if jac.ndim != 2 or jac.size == 0 or dfe <= 0:
        return np.full((jac.shape[1] if jac.ndim == 2 else 0, jac.shape[1] if jac.ndim == 2 else 0), np.nan)
    _, singular_values, vt = np.linalg.svd(jac, full_matrices=False)
    threshold = np.finfo(float).eps * max(jac.shape) * singular_values[0] if singular_values.size else 0.0
    singular_values = singular_values[singular_values > threshold]
    vt = vt[:singular_values.size]
    if singular_values.size == 0:
        return np.full((jac.shape[1], jac.shape[1]), np.nan)
    covariance = (vt.T / singular_values ** 2) @ vt
    residual_array = np.asarray(residuals, dtype=float)
    s_sq = float(np.sum(residual_array ** 2) / dfe)
    return covariance * s_sq


def confidence_from_covariance(
    values,
    covariance,
    dfe: int,
    confidence_level: float = CONFIDENCE_LEVEL,
) -> tuple[list[float | None], list[float | None]]:
    """Compute confidence intervals from a covariance matrix."""

    coeff_values = np.asarray(values, dtype=float)
    covariance_array = np.asarray(covariance, dtype=float)
    undefined_bounds = [None] * int(coeff_values.size)
    if (
        covariance_array.ndim != 2
        or covariance_array.shape[0] != coeff_values.size
        or covariance_array.shape[1] != coeff_values.size
        or dfe <= 0
        or not np.all(np.isfinite(covariance_array))
    ):
        return undefined_bounds, undefined_bounds

    variance = np.diag(covariance_array)
    if np.any(variance < 0):
        return undefined_bounds, undefined_bounds
    stderr = np.sqrt(variance)
    try:
        from scipy.special import stdtrit

        critical = float(stdtrit(dfe, (1.0 + confidence_level) / 2.0))
    except Exception:
        critical = 1.959963984540054
    if not math.isfinite(critical):
        return undefined_bounds, undefined_bounds
    lower = coeff_values - critical * stderr
    upper = coeff_values + critical * stderr
    return lower.astype(float).tolist(), upper.astype(float).tolist()


def build_fit_result(
    fit_type: str,
    formula: Any,
    coefficient_names: Any,
    coefficient_values_: Any,
    gof_value: Any = None,
    confidence_bounds: Any = None,
    python_formula: str | None = None,
    confidence_level: float = CONFIDENCE_LEVEL,
    engine: str | None = None,
) -> dict[str, Any]:
    """Build fit result."""

    names = [str(name) for name in as_list(coefficient_names)]
    values = coefficient_values(coefficient_values_)
    if len(values) != len(names):
        raise ValueError("Fitted coefficient names and values must have equal length.")
    lower_bounds, upper_bounds = confidence_rows(confidence_bounds, len(names))
    formula_text = str(formula)
    expression_template = python_formula if python_formula is not None else formula_text
    value_exp = replace_coefficients(expression_template, names, values)
    coefficients = []
    for index, name in enumerate(names):
        coefficients.append({
            "name": name,
            "value": values[index],
            "lower": lower_bounds[index],
            "upper": upper_bounds[index],
        })
    result = {
        "value_expression": value_exp,
        "show_expression": value_exp,
        "formula": formula_text,
        "fit_type": fit_type,
        "coefficients": coefficients,
        "goodness": goodness_to_dict(gof_value),
        "confidence_level": confidence_level,
    }
    if engine is not None:
        result["engine"] = engine
    return normalize_fit_result_for_storage(result)
