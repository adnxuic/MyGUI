"""Adapt SciPy fitting models to MyGUI's common fit-result contract."""

from __future__ import annotations

from typing import Any

import numpy as np
from scipy.optimize import least_squares, lsq_linear

from code.database.fit_result import (
    CONFIDENCE_LEVEL,
    build_fit_result,
    compute_goodness,
    confidence_from_covariance,
    covariance_from_jacobian,
)
from code.database.scipy_fit_models import FitModelSpec, SCIPY_FIT_MODELS, get_model_spec


LINEAR_METHOD = "LinearLeastSquares"
NONLINEAR_METHOD = "NonlinearLeastSquares"
SCIPY_LOSSES = ("linear", "soft_l1", "huber", "cauchy", "arctan")
SCIPY_NONLINEAR_METHODS = ("trf", "dogbox", "lm")


def fit_type_groups() -> dict[str, list[str]]:
    """Fit type groups using the selected model and options."""

    groups: dict[str, list[str]] = {}
    for spec in SCIPY_FIT_MODELS.values():
        groups.setdefault(spec.group, []).append(spec.fit_type)
    return groups


FIT_TYPES = fit_type_groups()


def _as_float_array(values, field_name: str) -> np.ndarray:
    try:
        array = np.asarray(values, dtype=float).reshape(-1)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} must contain only numbers.") from exc
    return array


def _option(options: dict[str, Any], *names: str, default: Any = None) -> Any:
    for name in names:
        if name in options and options[name] not in ("", None):
            return options[name]
    return default


def _parse_float(value: Any, field_name: str, *, positive: bool = False) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} must be a number.") from exc
    if positive and not number > 0:
        raise ValueError(f"{field_name} must be greater than 0.")
    return number


def _parse_optional_float(value: Any, field_name: str, *, positive: bool = False) -> float | None:
    if value in ("", None):
        return None
    return _parse_float(value, field_name, positive=positive)


def _parse_optional_int(value: Any, field_name: str, *, positive: bool = False) -> int | None:
    if value in ("", None):
        return None
    try:
        number = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} must be an integer.") from exc
    if positive and number <= 0:
        raise ValueError(f"{field_name} must be greater than 0.")
    return number


def _parse_float_sequence(value: Any, length: int, field_name: str) -> np.ndarray:
    if value is None:
        raise ValueError(f"{field_name} must be specified.")
    if isinstance(value, str):
        values = [item.strip() for item in value.split(",")]
    else:
        try:
            values = list(value)
        except TypeError as exc:
            raise ValueError(f"{field_name} must contain {length} numbers.") from exc
    if len(values) != length:
        raise ValueError(f"{field_name} must contain {length} values.")
    return np.asarray([_parse_float(item, field_name) for item in values], dtype=float)


def _parse_optional_float_sequence(value: Any, length: int, field_name: str) -> np.ndarray | None:
    if value in ("", None):
        return None
    if isinstance(value, str):
        values = [item.strip() for item in value.split(",")]
    else:
        try:
            values = list(value)
        except TypeError as exc:
            raise ValueError(f"{field_name} must contain {length} numbers.") from exc
    if len(values) != length:
        raise ValueError(f"{field_name} must contain {length} values.")
    if any(item in ("", None) for item in values):
        if all(item in ("", None) for item in values):
            return None
        raise ValueError(f"{field_name} must be either fully specified or left blank.")
    return np.asarray([_parse_float(item, field_name) for item in values], dtype=float)


def _has_finite_bounds(lower: np.ndarray, upper: np.ndarray) -> bool:
    return bool(np.any(np.isfinite(lower)) or np.any(np.isfinite(upper)))


def _bounds(spec: FitModelSpec, x: np.ndarray, y: np.ndarray,
            fit_options: dict[str, Any]) -> tuple[np.ndarray, np.ndarray]:
    count = len(spec.coefficient_names)
    lower = spec.default_lower(x, y).astype(float)
    upper = spec.default_upper(x, y).astype(float)
    lower_option = _option(fit_options, "Lower", "lower")
    upper_option = _option(fit_options, "Upper", "upper")
    if lower_option is not None:
        lower = _parse_float_sequence(lower_option, count, "Lower")
    if upper_option is not None:
        upper = _parse_float_sequence(upper_option, count, "Upper")
    if np.any(lower > upper):
        raise ValueError("Lower bounds must be less than or equal to Upper bounds.")
    return lower, upper


def _coerce_start_to_bounds(start: np.ndarray, lower: np.ndarray, upper: np.ndarray) -> np.ndarray:
    coerced = np.asarray(start, dtype=float).copy()
    for index, value in enumerate(coerced):
        low = lower[index]
        high = upper[index]
        if not np.isfinite(value):
            if np.isfinite(low) and np.isfinite(high):
                value = (low + high) / 2.0
            elif np.isfinite(low):
                value = low + max(abs(low), 1.0) * 1e-6
            elif np.isfinite(high):
                value = high - max(abs(high), 1.0) * 1e-6
            else:
                value = 1.0
        if np.isfinite(low) and value <= low:
            value = low + max(abs(low), 1.0) * 1e-6
        if np.isfinite(high) and value >= high:
            value = high - max(abs(high), 1.0) * 1e-6
        coerced[index] = value
    return coerced


def _start_point(spec: FitModelSpec, x: np.ndarray, y: np.ndarray,
                 fit_options: dict[str, Any], lower: np.ndarray, upper: np.ndarray) -> np.ndarray:
    start_option = _option(fit_options, "StartPoint", "start_point", "p0")
    parsed = _parse_optional_float_sequence(start_option, len(spec.coefficient_names), "StartPoint")
    if parsed is None:
        parsed = np.asarray(spec.default_start_point(x, y), dtype=float)
    if parsed.size != len(spec.coefficient_names):
        raise ValueError(f"StartPoint must contain {len(spec.coefficient_names)} values.")
    return _coerce_start_to_bounds(parsed, lower, upper)


def _x_scale(value: Any, count: int) -> float | str | np.ndarray:
    if value in ("", None):
        return 1.0
    if isinstance(value, str) and value.strip().lower() == "jac":
        return "jac"
    if isinstance(value, (list, tuple, np.ndarray)):
        return _parse_float_sequence(value, count, "XScale")
    return _parse_float(value, "XScale", positive=True)


def default_fit_options(fit_type: str) -> dict[str, Any]:
    """Return the default fit options."""

    spec = get_model_spec(fit_type)
    method = LINEAR_METHOD if spec.is_linear else NONLINEAR_METHOD
    options: dict[str, Any] = {
        "Method": method,
        "Lower": [float(value) for value in spec.default_lower(np.asarray([1.0]), np.asarray([1.0]))],
        "Upper": [float(value) for value in spec.default_upper(np.asarray([1.0]), np.asarray([1.0]))],
        "StartPoint": [None] * len(spec.coefficient_names) if not spec.is_linear else [],
    }
    if spec.is_linear:
        options.update({
            "LinearSolver": "lstsq",
            "Tol": 1e-10,
            "MaxIter": None,
        })
    else:
        options.update({
            "OptimizerMethod": "trf",
            "Loss": "linear",
            "FScale": 1.0,
            "MaxNfev": None,
            "FTol": 1e-8,
            "XTol": 1e-8,
            "GTol": 1e-8,
            "DiffStep": None,
            "XScale": 1.0,
        })
    return options


def get_func_info(fit_type: str) -> dict[str, Any]:
    """Return func info."""

    spec = get_model_spec(fit_type)
    return {
        "expression": spec.formula_template,
        "coefficients": list(spec.coefficient_names),
        "options": default_fit_options(fit_type),
    }


def _linear_fit(spec: FitModelSpec, x: np.ndarray, y: np.ndarray,
                fit_options: dict[str, Any], lower: np.ndarray, upper: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    if spec.design_matrix is None:
        raise ValueError(f"{spec.fit_type} does not provide a linear design matrix.")
    matrix = spec.design_matrix(x)
    if _has_finite_bounds(lower, upper):
        tol = _parse_float(_option(fit_options, "Tol", "tol", default=1e-10), "Tol", positive=True)
        max_iter = _parse_optional_int(_option(fit_options, "MaxIter", "max_iter"), "MaxIter", positive=True)
        result = lsq_linear(matrix, y, bounds=(lower, upper), tol=tol, max_iter=max_iter)
        if not result.success:
            raise RuntimeError(f"SciPy linear fitting failed: {result.message}")
        params = np.asarray(result.x, dtype=float)
    else:
        try:
            params, *_ = np.linalg.lstsq(matrix, y, rcond=None)
        except np.linalg.LinAlgError as exc:
            raise RuntimeError(f"SciPy linear fitting failed: {exc}") from exc
        params = np.asarray(params, dtype=float)
    residuals = spec.model_func(x, *params) - y
    covariance = covariance_from_jacobian(matrix, residuals, int(y.size - params.size))
    return params, covariance


def _nonlinear_fit(spec: FitModelSpec, x: np.ndarray, y: np.ndarray,
                   fit_options: dict[str, Any], lower: np.ndarray, upper: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    params0 = _start_point(spec, x, y, fit_options, lower, upper)
    method = str(_option(fit_options, "OptimizerMethod", "optimizer_method", default="trf")).strip().lower()
    if method not in SCIPY_NONLINEAR_METHODS:
        raise ValueError(f"OptimizerMethod must be one of: {', '.join(SCIPY_NONLINEAR_METHODS)}.")
    loss = str(_option(fit_options, "Loss", "loss", default="linear")).strip().lower()
    if loss not in SCIPY_LOSSES:
        raise ValueError(f"Loss must be one of: {', '.join(SCIPY_LOSSES)}.")
    if method == "lm" and _has_finite_bounds(lower, upper):
        raise ValueError("OptimizerMethod 'lm' cannot be used with bounds.")
    if method == "lm" and loss != "linear":
        raise ValueError("OptimizerMethod 'lm' only supports linear loss.")

    def residuals(params):
        with np.errstate(divide="ignore", invalid="ignore", over="ignore"):
            values = np.asarray(spec.model_func(x, *params), dtype=float)
        if values.shape != y.shape:
            return np.full_like(y, 1e12, dtype=float)
        residual = values - y
        return np.where(np.isfinite(residual), residual, 1e12)

    kwargs = {
        "method": method,
        "loss": loss,
        "f_scale": _parse_float(_option(fit_options, "FScale", "f_scale", default=1.0), "FScale", positive=True),
        "ftol": _parse_optional_float(_option(fit_options, "FTol", "ftol", default=1e-8), "FTol", positive=True),
        "xtol": _parse_optional_float(_option(fit_options, "XTol", "xtol", default=1e-8), "XTol", positive=True),
        "gtol": _parse_optional_float(_option(fit_options, "GTol", "gtol", default=1e-8), "GTol", positive=True),
        "max_nfev": _parse_optional_int(_option(fit_options, "MaxNfev", "max_nfev"), "MaxNfev", positive=True),
        "diff_step": _parse_optional_float(_option(fit_options, "DiffStep", "diff_step"), "DiffStep", positive=True),
        "x_scale": _x_scale(_option(fit_options, "XScale", "x_scale", default=1.0), params0.size),
    }
    if method == "lm":
        kwargs.pop("bounds", None)
        result = least_squares(residuals, params0, **kwargs)
    else:
        result = least_squares(residuals, params0, bounds=(lower, upper), **kwargs)
    if not result.success:
        raise RuntimeError(f"SciPy fitting failed: {result.message}")
    params = np.asarray(result.x, dtype=float)
    covariance = covariance_from_jacobian(result.jac, result.fun, int(y.size - params.size))
    return params, covariance


def fit_curve(
    x,
    y,
    fit_type: str,
    fit_options: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Fit curve using the selected model and options."""

    spec = get_model_spec(fit_type)
    x_data = _as_float_array(x, "X Data")
    y_data = _as_float_array(y, "Y Data")
    message = spec.domain_validator(x_data, y_data)
    if message is not None:
        raise ValueError(message)

    options = dict(fit_options or {})
    lower, upper = _bounds(spec, x_data, y_data, options)
    if spec.is_linear:
        params, covariance = _linear_fit(spec, x_data, y_data, options, lower, upper)
    else:
        params, covariance = _nonlinear_fit(spec, x_data, y_data, options, lower, upper)

    with np.errstate(divide="ignore", invalid="ignore", over="ignore"):
        fitted = np.asarray(spec.model_func(x_data, *params), dtype=float)
    if fitted.shape != y_data.shape or not np.all(np.isfinite(fitted)):
        raise RuntimeError("SciPy fitting failed: fitted curve contains non-finite values.")

    goodness = compute_goodness(y_data, fitted, params.size)
    lower_conf, upper_conf = confidence_from_covariance(
        params,
        covariance,
        int(goodness["dfe"]),
        CONFIDENCE_LEVEL,
    )
    result = build_fit_result(
        spec.fit_type,
        spec.formula_template,
        spec.coefficient_names,
        params.tolist(),
        goodness,
        [lower_conf, upper_conf],
        python_formula=spec.python_expression_template,
        confidence_level=CONFIDENCE_LEVEL,
        engine="Python",
    )
    return result
