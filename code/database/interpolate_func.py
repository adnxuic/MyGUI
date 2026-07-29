"""Provide interpolation algorithms used by data-backed chart components."""

from collections.abc import Callable

import numpy as np
from scipy.interpolate import Akima1DInterpolator, CubicSpline, PchipInterpolator, make_interp_spline
from scipy.interpolate import make_smoothing_spline


DEFAULT_INTERPOLATION_SAMPLES = 1000
MIN_INTERPOLATION_SAMPLES = 2
MAX_INTERPOLATION_SAMPLES = 100000

B_SPLINE_METHOD = "B样条插值"
SMOOTHING_SPLINE_METHOD = "平滑样条"


def _coerce_samples(samples: int = DEFAULT_INTERPOLATION_SAMPLES) -> int:
    try:
        sample_count = int(samples)
    except (TypeError, ValueError) as exc:
        raise ValueError("Interpolation samples must be an integer.") from exc
    if sample_count < MIN_INTERPOLATION_SAMPLES or sample_count > MAX_INTERPOLATION_SAMPLES:
        raise ValueError(
            f"Interpolation samples must be between {MIN_INTERPOLATION_SAMPLES} "
            f"and {MAX_INTERPOLATION_SAMPLES}."
        )
    return sample_count


def _prepare_xy(x: np.ndarray, y: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    x_array = np.asarray(x)
    y_array = np.asarray(y)
    if x_array.ndim != 1 or y_array.ndim != 1:
        raise ValueError("Interpolation data must be one-dimensional.")
    if len(x_array) != len(y_array):
        raise ValueError("X Data and Y Data must have the same length.")
    if len(x_array) < 2:
        raise ValueError("Interpolation requires at least 2 data points.")

    try:
        x_values = x_array.astype(float)
        y_values = y_array.astype(float)
    except (TypeError, ValueError) as exc:
        raise ValueError("X Data and Y Data must contain only numbers.") from exc

    if not np.isfinite(x_values).all() or not np.isfinite(y_values).all():
        raise ValueError("X Data and Y Data must not contain NaN or infinity.")

    order = np.argsort(x_values, kind="mergesort")
    x_values = x_values[order]
    y_values = y_values[order]
    if np.any(np.diff(x_values) == 0):
        raise ValueError("X Data values must be unique for interpolation.")

    return x_values, y_values


def _new_domain(x_values: np.ndarray, samples: int) -> np.ndarray:
    return np.linspace(float(x_values[0]), float(x_values[-1]), _coerce_samples(samples))


def _evaluate_interpolator(
        x: np.ndarray,
        y: np.ndarray,
        factory: Callable[[np.ndarray, np.ndarray], Callable[[np.ndarray], np.ndarray]],
        samples: int = DEFAULT_INTERPOLATION_SAMPLES,
) -> tuple[np.ndarray, np.ndarray]:
    x_values, y_values = _prepare_xy(x, y)
    x_new = _new_domain(x_values, samples)
    interpolator = factory(x_values, y_values)
    return x_new, np.asarray(interpolator(x_new), dtype=float)


def _validate_b_spline_order(k: int, point_count: int) -> int:
    try:
        order = int(k)
    except (TypeError, ValueError) as exc:
        raise ValueError("B-spline order k must be an integer.") from exc
    if order < 1 or order > 5:
        raise ValueError("B-spline order k must be between 1 and 5.")
    if order >= point_count:
        raise ValueError("B-spline order k must be smaller than the number of data points.")
    return order


def _coerce_lambda(lam: float | None, lam_auto: bool) -> float | None:
    if lam_auto:
        return None
    if lam is None:
        raise ValueError("Smoothing spline lambda is required when automatic lambda is disabled.")
    try:
        value = float(lam)
    except (TypeError, ValueError) as exc:
        raise ValueError("Smoothing spline lambda must be a number.") from exc
    if not np.isfinite(value) or value < 0:
        raise ValueError("Smoothing spline lambda must be a finite number greater than or equal to 0.")
    return value


def linear_interpolate(x: np.ndarray, y: np.ndarray,
                       samples: int = DEFAULT_INTERPOLATION_SAMPLES, **_kwargs):
    """Interpolate values with the linear method."""

    x_values, y_values = _prepare_xy(x, y)
    x_new = _new_domain(x_values, samples)
    return x_new, np.interp(x_new, x_values, y_values)


def nearest_interpolate(x: np.ndarray, y: np.ndarray,
                        samples: int = DEFAULT_INTERPOLATION_SAMPLES, **_kwargs):
    """Interpolate values with the nearest method."""

    x_values, y_values = _prepare_xy(x, y)
    x_new = _new_domain(x_values, samples)
    right = np.searchsorted(x_values, x_new, side="left")
    right = np.clip(right, 0, len(x_values) - 1)
    left = np.clip(right - 1, 0, len(x_values) - 1)
    choose_right = np.abs(x_values[right] - x_new) < np.abs(x_new - x_values[left])
    indexes = np.where(choose_right, right, left)
    return x_new, y_values[indexes]


def previous_interpolate(x: np.ndarray, y: np.ndarray,
                         samples: int = DEFAULT_INTERPOLATION_SAMPLES, **_kwargs):
    """Interpolate values with the previous method."""

    x_values, y_values = _prepare_xy(x, y)
    x_new = _new_domain(x_values, samples)
    indexes = np.searchsorted(x_values, x_new, side="right") - 1
    indexes = np.clip(indexes, 0, len(x_values) - 1)
    return x_new, y_values[indexes]


def next_interpolate(x: np.ndarray, y: np.ndarray,
                     samples: int = DEFAULT_INTERPOLATION_SAMPLES, **_kwargs):
    """Interpolate values with the next method."""

    x_values, y_values = _prepare_xy(x, y)
    x_new = _new_domain(x_values, samples)
    indexes = np.searchsorted(x_values, x_new, side="left")
    indexes = np.clip(indexes, 0, len(x_values) - 1)
    return x_new, y_values[indexes]


def CubicSpline_interpolate(x: np.ndarray, y: np.ndarray,
                            samples: int = DEFAULT_INTERPOLATION_SAMPLES, **_kwargs):
    """Interpolate values with the cubic spline method."""

    return _evaluate_interpolator(x, y, lambda x_values, y_values: CubicSpline(x_values, y_values), samples)


def b_spline_interpolate(x: np.ndarray, y: np.ndarray, k=3,
                         samples: int = DEFAULT_INTERPOLATION_SAMPLES, **_kwargs):
    """Interpolate values with the b spline method."""

    x_values, y_values = _prepare_xy(x, y)
    order = _validate_b_spline_order(k, len(x_values))
    x_new = _new_domain(x_values, samples)
    bspl = make_interp_spline(x_values, y_values, k=order)
    return x_new, np.asarray(bspl(x_new), dtype=float)


def b_spline_splrep_interpolate(x: np.ndarray, y: np.ndarray, k=3,
                                samples: int = DEFAULT_INTERPOLATION_SAMPLES, **kwargs):
    """Interpolate values with the b spline splrep method."""

    return b_spline_interpolate(x, y, k=k, samples=samples, **kwargs)


def pchip_interpolate(x: np.ndarray, y: np.ndarray,
                      samples: int = DEFAULT_INTERPOLATION_SAMPLES, **_kwargs):
    """Interpolate values with the pchip method."""

    return _evaluate_interpolator(x, y, lambda x_values, y_values: PchipInterpolator(x_values, y_values), samples)


def akima_interpolate(x: np.ndarray, y: np.ndarray,
                      samples: int = DEFAULT_INTERPOLATION_SAMPLES, **_kwargs):
    """Interpolate values with the akima method."""

    return _evaluate_interpolator(
        x,
        y,
        lambda x_values, y_values: Akima1DInterpolator(x_values, y_values, method="akima"),
        samples,
    )


def makima_interpolate(x: np.ndarray, y: np.ndarray,
                       samples: int = DEFAULT_INTERPOLATION_SAMPLES, **_kwargs):
    """Interpolate values with the makima method."""

    return _evaluate_interpolator(
        x,
        y,
        lambda x_values, y_values: Akima1DInterpolator(x_values, y_values, method="makima"),
        samples,
    )


def smoothing_spline_interpolate(x: np.ndarray, y: np.ndarray,
                                 samples: int = DEFAULT_INTERPOLATION_SAMPLES,
                                 lam: float | None = None, lam_auto: bool = True, **_kwargs):
    """Interpolate values with the smoothing spline method."""

    x_values, y_values = _prepare_xy(x, y)
    if len(x_values) < 5:
        raise ValueError("Smoothing spline requires at least 5 data points.")
    lambda_value = _coerce_lambda(lam, bool(lam_auto))
    x_new = _new_domain(x_values, samples)
    spline = make_smoothing_spline(x_values, y_values, lam=lambda_value)
    return x_new, np.asarray(spline(x_new), dtype=float)


interpolate_dict = {
    "三次样条插值": CubicSpline_interpolate,
    B_SPLINE_METHOD: b_spline_interpolate,
    "线性插值": linear_interpolate,
    "最近邻插值": nearest_interpolate,
    "前值阶梯插值": previous_interpolate,
    "后值阶梯插值": next_interpolate,
    "PCHIP保形插值": pchip_interpolate,
    "Akima插值": akima_interpolate,
    "Makima插值": makima_interpolate,
    SMOOTHING_SPLINE_METHOD: smoothing_spline_interpolate,
}


def interpolation_uses_order(method: str) -> bool:
    """Return whether the method accepts an interpolation order."""

    return method == B_SPLINE_METHOD


def interpolation_uses_lambda(method: str) -> bool:
    """Return whether the method accepts a smoothing parameter."""

    return method == SMOOTHING_SPLINE_METHOD


def interpolate_curve(x: np.ndarray, y: np.ndarray, method: str, k: int = 3,
                      samples: int = DEFAULT_INTERPOLATION_SAMPLES,
                      lam: float | None = None, lam_auto: bool = True):
    """Interpolate the supplied curve with the selected method."""

    if method not in interpolate_dict:
        raise ValueError(f"Unknown interpolation method: {method}")
    return interpolate_dict[method](
        x,
        y,
        k=k,
        samples=samples,
        lam=lam,
        lam_auto=lam_auto,
    )
