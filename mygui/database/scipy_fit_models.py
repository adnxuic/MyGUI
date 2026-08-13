"""Define the built-in SciPy curve-fitting model catalog."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import numpy as np

from mygui.database.fit_catalog import FIT_MODEL_GROUPS


Array = np.ndarray


@dataclass(frozen=True)
class FitModelSpec:
    """Describe fit model spec values shared across application layers."""

    fit_type: str
    group: str
    coefficient_names: tuple[str, ...]
    formula_template: str
    python_expression_template: str
    model_func: Callable[..., Array]
    default_start_point: Callable[[Array, Array], Array]
    default_lower: Callable[[Array, Array], Array]
    default_upper: Callable[[Array, Array], Array]
    domain_validator: Callable[[Array, Array], str | None]
    is_linear: bool = False
    design_matrix: Callable[[Array], Array] | None = None


def _finite_domain(x: Array, y: Array) -> str | None:
    if x.size == 0 or y.size == 0:
        return "X Data and Y Data must not be empty."
    if x.size != y.size:
        return "X Data and Y Data must have the same length."
    if not np.all(np.isfinite(x)) or not np.all(np.isfinite(y)):
        return "X Data and Y Data must contain only finite numbers."
    return None


def _positive_x_domain(x: Array, y: Array) -> str | None:
    message = _finite_domain(x, y)
    if message is not None:
        return message
    if np.any(x <= 0):
        return "This fit type requires X values greater than 0."
    return None


def _nonnegative_x_domain(x: Array, y: Array) -> str | None:
    message = _finite_domain(x, y)
    if message is not None:
        return message
    if np.any(x < 0):
        return "This fit type requires X values greater than or equal to 0."
    return None


def _span(x: Array) -> float:
    if x.size < 2:
        return 1.0
    value = float(np.max(x) - np.min(x))
    return value if value > np.finfo(float).eps else 1.0


def _safe_scale(y: Array) -> float:
    if y.size == 0:
        return 1.0
    value = float(np.nanmax(y) - np.nanmin(y))
    if not np.isfinite(value) or abs(value) <= np.finfo(float).eps:
        value = float(np.nanmax(np.abs(y))) if y.size else 1.0
    return value if np.isfinite(value) and abs(value) > np.finfo(float).eps else 1.0


def _safe_exp(value):
    return np.exp(np.clip(value, -700.0, 700.0))


def _linear_start(design_matrix: Callable[[Array], Array]) -> Callable[[Array, Array], Array]:
    def start(x: Array, y: Array) -> Array:
        matrix = design_matrix(x)
        try:
            values, *_ = np.linalg.lstsq(matrix, y, rcond=None)
        except np.linalg.LinAlgError:
            values = np.zeros(matrix.shape[1], dtype=float)
        return np.asarray(values, dtype=float)

    return start


def _unbounded_lower(names: tuple[str, ...]) -> Callable[[Array, Array], Array]:
    return lambda _x, _y: np.full(len(names), -np.inf, dtype=float)


def _unbounded_upper(names: tuple[str, ...]) -> Callable[[Array, Array], Array]:
    return lambda _x, _y: np.full(len(names), np.inf, dtype=float)


def _positive_lower(names: tuple[str, ...], positive_names: set[str]) -> Callable[[Array, Array], Array]:
    def lower(_x: Array, _y: Array) -> Array:
        values = np.full(len(names), -np.inf, dtype=float)
        for index, name in enumerate(names):
            if name in positive_names:
                values[index] = np.finfo(float).tiny
        return values

    return lower


def _poly_expression(order: int, coefficient_names: tuple[str, ...], power_operator: str) -> str:
    terms = []
    for index, coefficient in enumerate(coefficient_names):
        power = order - index
        if power > 1:
            terms.append(f"{coefficient}*x{power_operator}{power}")
        elif power == 1:
            terms.append(f"{coefficient}*x")
        else:
            terms.append(coefficient)
    return " + ".join(terms)


def _poly_design(order: int) -> Callable[[Array], Array]:
    return lambda x: np.vander(x, order + 1)


def _poly_model(_order: int) -> Callable[..., Array]:
    return lambda x, *params: np.polyval(np.asarray(params, dtype=float), x)


def _exp_start(order: int) -> Callable[[Array, Array], Array]:
    def start(x: Array, y: Array) -> Array:
        span = _span(x)
        scale = _safe_scale(y)
        baseline = float(np.nanmin(y)) if y.size else 0.0
        if order == 1:
            return np.asarray([scale, 1.0 / span], dtype=float)
        return np.asarray([scale, -1.0 / span, max(baseline, scale / 2.0), -0.1 / span], dtype=float)

    return start


def _exp_model(order: int) -> Callable[..., Array]:
    def model(x: Array, *params) -> Array:
        if order == 1:
            a, b = params
            return a * _safe_exp(b * x)
        a, b, c, d = params
        return a * _safe_exp(b * x) + c * _safe_exp(d * x)

    return model


def _gauss_names(order: int) -> tuple[str, ...]:
    names: list[str] = []
    for index in range(1, order + 1):
        names.extend([f"a{index}", f"b{index}", f"c{index}"])
    return tuple(names)


def _gauss_formula(order: int, power_operator: str) -> str:
    parts = []
    for index in range(1, order + 1):
        parts.append(f"a{index}*exp(-((x-b{index})/c{index}){power_operator}2)")
    return " + ".join(parts)


def _gauss_start(order: int) -> Callable[[Array, Array], Array]:
    def start(x: Array, y: Array) -> Array:
        span = _span(x)
        width = max(span / (2.0 * max(order, 1)), np.finfo(float).eps)
        values: list[float] = []
        if order == 1:
            peak_index = int(np.nanargmax(np.abs(y)))
            return np.asarray([float(y[peak_index]), float(x[peak_index]), width], dtype=float)

        boundaries = np.linspace(float(np.min(x)), float(np.max(x)), order + 1)
        for index in range(order):
            mask = (x >= boundaries[index]) & (x <= boundaries[index + 1])
            segment_x = x[mask] if np.any(mask) else x
            segment_y = y[mask] if np.any(mask) else y
            peak_index = int(np.nanargmax(np.abs(segment_y)))
            values.extend([float(segment_y[peak_index]), float(segment_x[peak_index]), width])
        return np.asarray(values, dtype=float)

    return start


def _gauss_model(order: int) -> Callable[..., Array]:
    def model(x: Array, *params) -> Array:
        result = np.zeros_like(x, dtype=float)
        for index in range(order):
            a, b, c = params[index * 3:index * 3 + 3]
            result = result + a * _safe_exp(-((x - b) / c) ** 2)
        return result

    return model


def _fourier_names(order: int) -> tuple[str, ...]:
    names = ["a0"]
    for index in range(1, order + 1):
        names.extend([f"a{index}", f"b{index}"])
    names.append("w")
    return tuple(names)


def _fourier_formula(order: int) -> str:
    parts = ["a0"]
    for index in range(1, order + 1):
        parts.append(f"a{index}*cos({index}*w*x)")
        parts.append(f"b{index}*sin({index}*w*x)")
    return " + ".join(parts)


def _fourier_start(order: int) -> Callable[[Array, Array], Array]:
    def start(x: Array, y: Array) -> Array:
        w = 2.0 * np.pi / _span(x)
        cols = [np.ones_like(x, dtype=float)]
        for index in range(1, order + 1):
            cols.append(np.cos(index * w * x))
            cols.append(np.sin(index * w * x))
        matrix = np.column_stack(cols)
        try:
            coeffs, *_ = np.linalg.lstsq(matrix, y, rcond=None)
        except np.linalg.LinAlgError:
            coeffs = np.zeros(1 + 2 * order, dtype=float)
            coeffs[0] = float(np.mean(y))
        return np.asarray([*coeffs, w], dtype=float)

    return start


def _fourier_model(order: int) -> Callable[..., Array]:
    def model(x: Array, *params) -> Array:
        w = params[-1]
        result = np.full_like(x, params[0], dtype=float)
        offset = 1
        for index in range(1, order + 1):
            a = params[offset]
            b = params[offset + 1]
            result = result + a * np.cos(index * w * x) + b * np.sin(index * w * x)
            offset += 2
        return result

    return model


def _sin_names(order: int) -> tuple[str, ...]:
    names: list[str] = []
    for index in range(1, order + 1):
        names.extend([f"a{index}", f"b{index}", f"c{index}"])
    return tuple(names)


def _sin_formula(order: int) -> str:
    return " + ".join(f"a{index}*sin(b{index}*x+c{index})" for index in range(1, order + 1))


def _sin_start(order: int) -> Callable[[Array, Array], Array]:
    def start(x: Array, y: Array) -> Array:
        amplitude = _safe_scale(y) / max(2.0 * order, 1.0)
        frequency = 2.0 * np.pi / _span(x)
        values = []
        for index in range(1, order + 1):
            values.extend([amplitude, index * frequency, 0.0])
        return np.asarray(values, dtype=float)

    return start


def _sin_model(order: int) -> Callable[..., Array]:
    def model(x: Array, *params) -> Array:
        result = np.zeros_like(x, dtype=float)
        for index in range(order):
            a, b, c = params[index * 3:index * 3 + 3]
            result = result + a * np.sin(b * x + c)
        return result

    return model


def _power_start(with_offset: bool) -> Callable[[Array, Array], Array]:
    def start(_x: Array, y: Array) -> Array:
        scale = _safe_scale(y)
        if with_offset:
            return np.asarray([scale, 1.0, float(np.nanmin(y))], dtype=float)
        return np.asarray([scale, 1.0], dtype=float)

    return start


def _power_model(with_offset: bool) -> Callable[..., Array]:
    def model(x: Array, *params) -> Array:
        if with_offset:
            a, b, c = params
            return a * x ** b + c
        a, b = params
        return a * x ** b

    return model


def _rat_names(numerator_order: int, denominator_order: int) -> tuple[str, ...]:
    p_names = [f"p{i}" for i in range(1, numerator_order + 2)]
    q_names = [f"q{i}" for i in range(1, denominator_order + 1)]
    return tuple(p_names + q_names)


def _rat_formula(numerator_order: int, denominator_order: int, power_operator: str) -> str:
    p_names = [f"p{i}" for i in range(1, numerator_order + 2)]
    numerator_terms = []
    for index, coefficient in enumerate(p_names):
        power = numerator_order - index
        if power > 1:
            numerator_terms.append(f"{coefficient}*x{power_operator}{power}")
        elif power == 1:
            numerator_terms.append(f"{coefficient}*x")
        else:
            numerator_terms.append(coefficient)

    denominator_terms = []
    for index in range(denominator_order + 1):
        power = denominator_order - index
        if index == 0 and power > 1:
            denominator_terms.append(f"x{power_operator}{power}")
        elif index == 0 and power == 1:
            denominator_terms.append("x")
        else:
            coefficient = f"q{index}"
            if power > 1:
                denominator_terms.append(f"{coefficient}*x{power_operator}{power}")
            elif power == 1:
                denominator_terms.append(f"{coefficient}*x")
            else:
                denominator_terms.append(coefficient)
    return f"({' + '.join(numerator_terms)})/({' + '.join(denominator_terms)})"


def _rat_start(numerator_order: int, denominator_order: int) -> Callable[[Array, Array], Array]:
    def start(x: Array, y: Array) -> Array:
        columns = []
        for power in range(numerator_order, -1, -1):
            columns.append(x ** power)
        for power in range(denominator_order - 1, -1, -1):
            columns.append(-y * x ** power)
        matrix = np.column_stack(columns)
        target = y * x ** denominator_order
        try:
            values, *_ = np.linalg.lstsq(matrix, target, rcond=None)
        except np.linalg.LinAlgError:
            values = np.zeros(numerator_order + denominator_order + 1, dtype=float)
        return np.asarray(values, dtype=float)

    return start


def _rat_model(numerator_order: int, denominator_order: int) -> Callable[..., Array]:
    def model(x: Array, *params) -> Array:
        params_array = np.asarray(params, dtype=float)
        p_values = params_array[:numerator_order + 1]
        q_values = params_array[numerator_order + 1:]
        numerator = np.polyval(p_values, x)
        denominator = x ** denominator_order
        for index, coefficient in enumerate(q_values, start=1):
            denominator = denominator + coefficient * x ** (denominator_order - index)
        with np.errstate(divide="ignore", invalid="ignore", over="ignore"):
            values = numerator / denominator
        values = np.asarray(values, dtype=float)
        values[np.abs(denominator) < 1e-12] = np.nan
        return values

    return model


def _weibull_model(x: Array, a: float, b: float) -> Array:
    with np.errstate(divide="ignore", invalid="ignore", over="ignore"):
        return a * b * x ** (b - 1.0) * _safe_exp(-a * x ** b)


def _logistic_model(x: Array, a: float, b: float, c: float) -> Array:
    return a / (1.0 + _safe_exp(-b * (x - c)))


def _logistic4_model(x: Array, a: float, b: float, c: float, d: float) -> Array:
    with np.errstate(divide="ignore", invalid="ignore", over="ignore"):
        return d + (a - d) / (1.0 + (x / c) ** b)


def _gompertz_model(x: Array, a: float, b: float, c: float) -> Array:
    return a * _safe_exp(-b * _safe_exp(-c * x))


def _register_poly(registry: dict[str, FitModelSpec]) -> None:
    for order in range(1, 10):
        names = tuple(f"p{i}" for i in range(1, order + 2))
        design = _poly_design(order)
        registry[f"poly{order}"] = FitModelSpec(
            fit_type=f"poly{order}",
            group="poly",
            coefficient_names=names,
            formula_template=_poly_expression(order, names, "^"),
            python_expression_template=_poly_expression(order, names, "**"),
            model_func=_poly_model(order),
            default_start_point=_linear_start(design),
            default_lower=_unbounded_lower(names),
            default_upper=_unbounded_upper(names),
            domain_validator=_finite_domain,
            is_linear=True,
            design_matrix=design,
        )


def _register_exp(registry: dict[str, FitModelSpec]) -> None:
    for order, names, formula in (
        (1, ("a", "b"), "a*exp(b*x)"),
        (2, ("a", "b", "c", "d"), "a*exp(b*x) + c*exp(d*x)"),
    ):
        registry[f"exp{order}"] = FitModelSpec(
            fit_type=f"exp{order}",
            group="exp",
            coefficient_names=names,
            formula_template=formula,
            python_expression_template=formula,
            model_func=_exp_model(order),
            default_start_point=_exp_start(order),
            default_lower=_unbounded_lower(names),
            default_upper=_unbounded_upper(names),
            domain_validator=_finite_domain,
        )


def _register_log(registry: dict[str, FitModelSpec]) -> None:
    names = ("a", "b")

    def design(x):
        return np.column_stack([np.log(x), np.ones_like(x, dtype=float)])

    registry["log"] = FitModelSpec(
        fit_type="log",
        group="log",
        coefficient_names=names,
        formula_template="a*log(x) + b",
        python_expression_template="a*log(x) + b",
        model_func=lambda x, a, b: a * np.log(x) + b,
        default_start_point=_linear_start(design),
        default_lower=_unbounded_lower(names),
        default_upper=_unbounded_upper(names),
        domain_validator=_positive_x_domain,
        is_linear=True,
        design_matrix=design,
    )


def _register_gauss(registry: dict[str, FitModelSpec]) -> None:
    for order in range(1, 9):
        names = _gauss_names(order)
        positive_names = {name for name in names if name.startswith("c")}
        registry[f"gauss{order}"] = FitModelSpec(
            fit_type=f"gauss{order}",
            group="gauss",
            coefficient_names=names,
            formula_template=_gauss_formula(order, "^"),
            python_expression_template=_gauss_formula(order, "**"),
            model_func=_gauss_model(order),
            default_start_point=_gauss_start(order),
            default_lower=_positive_lower(names, positive_names),
            default_upper=_unbounded_upper(names),
            domain_validator=_finite_domain,
        )


def _register_power(registry: dict[str, FitModelSpec]) -> None:
    specs = (
        ("power1", ("a", "b"), "a*x^b", "a*x**b", False),
        ("power2", ("a", "b", "c"), "a*x^b + c", "a*x**b + c", True),
    )
    for fit_type, names, formula, python_formula, with_offset in specs:
        registry[fit_type] = FitModelSpec(
            fit_type=fit_type,
            group="power",
            coefficient_names=names,
            formula_template=formula,
            python_expression_template=python_formula,
            model_func=_power_model(with_offset),
            default_start_point=_power_start(with_offset),
            default_lower=_unbounded_lower(names),
            default_upper=_unbounded_upper(names),
            domain_validator=_positive_x_domain,
        )


def _register_fourier(registry: dict[str, FitModelSpec]) -> None:
    for order in range(1, 9):
        names = _fourier_names(order)
        registry[f"fourier{order}"] = FitModelSpec(
            fit_type=f"fourier{order}",
            group="fourier",
            coefficient_names=names,
            formula_template=_fourier_formula(order),
            python_expression_template=_fourier_formula(order),
            model_func=_fourier_model(order),
            default_start_point=_fourier_start(order),
            default_lower=_unbounded_lower(names),
            default_upper=_unbounded_upper(names),
            domain_validator=_finite_domain,
        )


def _register_sin(registry: dict[str, FitModelSpec]) -> None:
    for order in range(1, 9):
        names = _sin_names(order)
        registry[f"sin{order}"] = FitModelSpec(
            fit_type=f"sin{order}",
            group="sin",
            coefficient_names=names,
            formula_template=_sin_formula(order),
            python_expression_template=_sin_formula(order),
            model_func=_sin_model(order),
            default_start_point=_sin_start(order),
            default_lower=_unbounded_lower(names),
            default_upper=_unbounded_upper(names),
            domain_validator=_finite_domain,
        )


def _register_rat(registry: dict[str, FitModelSpec]) -> None:
    for numerator_order in range(0, 6):
        for denominator_order in range(1, 6):
            fit_type = f"rat{numerator_order}{denominator_order}"
            names = _rat_names(numerator_order, denominator_order)
            registry[fit_type] = FitModelSpec(
                fit_type=fit_type,
                group="rat",
                coefficient_names=names,
                formula_template=_rat_formula(numerator_order, denominator_order, "^"),
                python_expression_template=_rat_formula(numerator_order, denominator_order, "**"),
                model_func=_rat_model(numerator_order, denominator_order),
                default_start_point=_rat_start(numerator_order, denominator_order),
                default_lower=_unbounded_lower(names),
                default_upper=_unbounded_upper(names),
                domain_validator=_finite_domain,
            )


def _register_distribution_and_sigmoid(registry: dict[str, FitModelSpec]) -> None:
    registry["weibull"] = FitModelSpec(
        fit_type="weibull",
        group="weibull",
        coefficient_names=("a", "b"),
        formula_template="a*b*x^(b-1)*exp(-a*x^b)",
        python_expression_template="a*b*x**(b-1)*exp(-a*x**b)",
        model_func=_weibull_model,
        default_start_point=lambda x, _y: np.asarray([1.0 / max(float(np.mean(x)), 1.0), 1.5], dtype=float),
        default_lower=_positive_lower(("a", "b"), {"a", "b"}),
        default_upper=_unbounded_upper(("a", "b")),
        domain_validator=_positive_x_domain,
    )
    registry["logistic"] = FitModelSpec(
        fit_type="logistic",
        group="sigmoid",
        coefficient_names=("a", "b", "c"),
        formula_template="a/(1+exp(-b*(x-c)))",
        python_expression_template="a/(1+exp(-b*(x-c)))",
        model_func=_logistic_model,
        default_start_point=lambda x, y: np.asarray([float(np.nanmax(y)), 1.0 / _span(x), float(np.median(x))]),
        default_lower=_unbounded_lower(("a", "b", "c")),
        default_upper=_unbounded_upper(("a", "b", "c")),
        domain_validator=_finite_domain,
    )
    registry["logistic4"] = FitModelSpec(
        fit_type="logistic4",
        group="sigmoid",
        coefficient_names=("a", "b", "c", "d"),
        formula_template="d + (a-d)/(1+(x/c)^b)",
        python_expression_template="d + (a-d)/(1+(x/c)**b)",
        model_func=_logistic4_model,
        default_start_point=lambda x, y: np.asarray([
            float(np.nanmax(y)),
            1.0,
            max(float(np.median(x)), np.finfo(float).eps),
            float(np.nanmin(y)),
        ]),
        default_lower=_positive_lower(("a", "b", "c", "d"), {"c"}),
        default_upper=_unbounded_upper(("a", "b", "c", "d")),
        domain_validator=_positive_x_domain,
    )
    registry["gompertz"] = FitModelSpec(
        fit_type="gompertz",
        group="sigmoid",
        coefficient_names=("a", "b", "c"),
        formula_template="a*exp(-b*exp(-c*x))",
        python_expression_template="a*exp(-b*exp(-c*x))",
        model_func=_gompertz_model,
        default_start_point=lambda x, y: np.asarray([float(np.nanmax(y)), 1.0, 1.0 / _span(x)]),
        default_lower=_positive_lower(("a", "b", "c"), {"a", "b", "c"}),
        default_upper=_unbounded_upper(("a", "b", "c")),
        domain_validator=_finite_domain,
    )


def _build_registry() -> dict[str, FitModelSpec]:
    registry: dict[str, FitModelSpec] = {}
    _register_poly(registry)
    _register_exp(registry)
    _register_log(registry)
    _register_fourier(registry)
    _register_gauss(registry)
    _register_power(registry)
    _register_rat(registry)
    _register_sin(registry)
    _register_distribution_and_sigmoid(registry)
    return registry


SCIPY_FIT_MODELS = _build_registry()

_expected_fit_models = {
    model
    for models in FIT_MODEL_GROUPS.values()
    for model in models
}
if set(SCIPY_FIT_MODELS) != _expected_fit_models:
    missing = sorted(_expected_fit_models - set(SCIPY_FIT_MODELS))
    extra = sorted(set(SCIPY_FIT_MODELS) - _expected_fit_models)
    raise RuntimeError(
        "SciPy fitting registry does not match the canonical catalog: "
        f"missing={missing!r}, extra={extra!r}."
    )
for _model_id, _model_spec in SCIPY_FIT_MODELS.items():
    if _model_id not in FIT_MODEL_GROUPS.get(_model_spec.group, ()):
        raise RuntimeError(
            f"SciPy fitting model {_model_id!r} declares non-canonical group "
            f"{_model_spec.group!r}."
        )


def get_model_spec(fit_type: str) -> FitModelSpec:
    """Return model spec."""

    try:
        return SCIPY_FIT_MODELS[fit_type]
    except KeyError as exc:
        raise ValueError(f"Unsupported SciPy fit type: {fit_type}") from exc
