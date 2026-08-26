"""Closed, JSON-safe value contracts for advanced Matplotlib properties.

Matplotlib accepts Python objects and callables for many setters.  Project
files deliberately use the narrower tagged mappings in this module so a
saved component can be validated, reconstructed, and rolled back without
deserializing executable objects.
"""

from __future__ import annotations

from copy import deepcopy
import math
import string
from typing import Any, Iterable, Mapping

import numpy as np
from matplotlib import colors as mcolors
from matplotlib import ticker

from mygui.figuremodify.matplotlib_adapter import copy_colormap, has_colormap

from .errors import ComponentValidationError


def _mapping(value: Any, name: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ComponentValidationError(f"{name} must be an object.")
    if not all(isinstance(key, str) for key in value):
        raise ComponentValidationError(f"{name} keys must be strings.")
    return dict(value)


def _exact(value: Mapping[str, Any], expected: set[str], name: str) -> None:
    if set(value) != expected:
        raise ComponentValidationError(
            f"{name} fields must be exactly {sorted(expected)!r}."
        )


def _finite(value: Any, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ComponentValidationError(f"{name} must be a number.")
    result = float(value)
    if not math.isfinite(result):
        raise ComponentValidationError(f"{name} must be finite.")
    return result


def _positive(value: Any, name: str, *, allow_zero: bool = False) -> float:
    result = _finite(value, name)
    if result < 0 if allow_zero else result <= 0:
        qualifier = "non-negative" if allow_zero else "positive"
        raise ComponentValidationError(f"{name} must be {qualifier}.")
    return result


def _optional_finite(value: Any, name: str) -> float | None:
    return None if value is None else _finite(value, name)


def _finite_sequence(
    value: Any,
    name: str,
    *,
    minimum_length: int = 0,
    positive: bool = False,
) -> list[float]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Iterable):
        raise ComponentValidationError(f"{name} must be an array.")
    result = [_finite(item, f"{name}[]") for item in value]
    if len(result) < minimum_length:
        raise ComponentValidationError(
            f"{name} must contain at least {minimum_length} values."
        )
    if positive and any(item <= 0 for item in result):
        raise ComponentValidationError(f"{name} values must be positive.")
    return result


def _color(value: Any, name: str, *, allow_none: bool = False) -> str | None:
    if value is None and allow_none:
        return None
    if not mcolors.is_color_like(value):
        raise ComponentValidationError(f"{name} is not a Matplotlib color.")
    rgba = mcolors.to_rgba(value)
    return mcolors.to_hex(rgba, keep_alpha=rgba[3] < 1)


def normalize_figure_layout(value: Any) -> dict[str, Any]:
    """Normalize a safe Figure layout-engine description."""

    spec = _mapping(value, "Figure layout")
    _exact(spec, {"kind", "params"}, "Figure layout")
    kind = spec["kind"]
    params = _mapping(spec["params"], "Figure layout params")
    if kind == "none":
        _exact(params, set(), "Figure layout params")
        return {"kind": "none", "params": {}}
    if kind == "tight":
        expected = {"pad", "w_pad", "h_pad", "rect"}
        _exact(params, expected, "Tight layout params")
        rect = params["rect"]
        if rect is not None:
            rect = _finite_sequence(rect, "Tight layout rect", minimum_length=4)
            if len(rect) != 4:
                raise ComponentValidationError("Tight layout rect requires four values.")
        return {
            "kind": kind,
            "params": {
                "pad": _optional_finite(params["pad"], "Tight layout pad"),
                "w_pad": _optional_finite(params["w_pad"], "Tight layout w_pad"),
                "h_pad": _optional_finite(params["h_pad"], "Tight layout h_pad"),
                "rect": rect,
            },
        }
    if kind in {"constrained", "compressed"}:
        expected = {"w_pad", "h_pad", "wspace", "hspace", "rect"}
        _exact(params, expected, "Constrained layout params")
        rect = params["rect"]
        if rect is not None:
            rect = _finite_sequence(rect, "Constrained layout rect", minimum_length=4)
            if len(rect) != 4:
                raise ComponentValidationError(
                    "Constrained layout rect requires four values."
                )
        return {
            "kind": kind,
            "params": {
                "w_pad": _optional_finite(params["w_pad"], "Layout w_pad"),
                "h_pad": _optional_finite(params["h_pad"], "Layout h_pad"),
                "wspace": _optional_finite(params["wspace"], "Layout wspace"),
                "hspace": _optional_finite(params["hspace"], "Layout hspace"),
                "rect": rect,
            },
        }
    raise ComponentValidationError(f"Unsupported Figure layout kind {kind!r}.")


def apply_figure_layout(figure: Any, value: Any) -> None:
    spec = normalize_figure_layout(value)
    params = {key: item for key, item in spec["params"].items() if item is not None}
    figure.set_layout_engine(spec["kind"], **params)


def normalize_scale(value: Any) -> dict[str, Any]:
    """Normalize the supported, callable-free scale definitions."""

    spec = _mapping(value, "Scale")
    _exact(spec, {"kind", "params"}, "Scale")
    kind = spec["kind"]
    params = _mapping(spec["params"], "Scale params")
    expected_by_kind = {
        "linear": set(),
        "log": {"base", "subs", "nonpositive"},
        "symlog": {"base", "linthresh", "linscale", "subs"},
        "logit": {"nonpositive", "one_half", "use_overline"},
        "asinh": {"linear_width", "base", "subs"},
    }
    if kind not in expected_by_kind:
        raise ComponentValidationError(f"Unsupported scale kind {kind!r}.")
    _exact(params, expected_by_kind[kind], "Scale params")
    if kind == "linear":
        normalized = {}
    elif kind == "log":
        normalized = {
            "base": _positive(params["base"], "Log base"),
            "subs": None if params["subs"] is None else _finite_sequence(params["subs"], "Log subs", positive=True),
            "nonpositive": str(params["nonpositive"]),
        }
        if normalized["base"] == 1 or normalized["nonpositive"] not in {"clip", "mask"}:
            raise ComponentValidationError("Invalid logarithmic scale parameters.")
    elif kind == "symlog":
        normalized = {
            "base": _positive(params["base"], "Symlog base"),
            "linthresh": _positive(params["linthresh"], "Symlog linthresh"),
            "linscale": _positive(params["linscale"], "Symlog linscale"),
            "subs": None if params["subs"] is None else _finite_sequence(params["subs"], "Symlog subs", positive=True),
        }
        if normalized["base"] == 1:
            raise ComponentValidationError("Symlog base must not equal one.")
    elif kind == "logit":
        normalized = {
            "nonpositive": str(params["nonpositive"]),
            "one_half": str(params["one_half"]),
            "use_overline": bool(params["use_overline"]),
        }
        if normalized["nonpositive"] not in {"clip", "mask"}:
            raise ComponentValidationError("Invalid logit nonpositive policy.")
    else:
        normalized = {
            "linear_width": _positive(params["linear_width"], "Asinh linear width"),
            "base": _positive(params["base"], "Asinh base"),
            "subs": _finite_sequence(params["subs"], "Asinh subs", minimum_length=1),
        }
    return {"kind": kind, "params": normalized}


DEFAULT_SCALE = {"kind": "linear", "params": {}}


def default_scale_for_name(name: str) -> dict[str, Any]:
    """Return the explicit persisted defaults for one supported scale name."""

    defaults = {
        "linear": DEFAULT_SCALE,
        "log": {"kind": "log", "params": {"base": 10.0, "subs": None, "nonpositive": "clip"}},
        "symlog": {"kind": "symlog", "params": {"base": 10.0, "linthresh": 2.0, "linscale": 1.0, "subs": None}},
        "logit": {"kind": "logit", "params": {"nonpositive": "mask", "one_half": r"\frac{1}{2}", "use_overline": False}},
        "asinh": {"kind": "asinh", "params": {"linear_width": 1.0, "base": 10.0, "subs": [2.0, 5.0]}},
    }
    try:
        return normalize_scale(deepcopy(defaults[str(name)]))
    except KeyError as exc:
        raise ComponentValidationError(f"Unsupported scale kind {name!r}.") from exc


def default_minor_locator_for_scale(value: Any) -> dict[str, Any]:
    """Return Matplotlib 3.9's scale-appropriate default minor locator."""

    scale = normalize_scale(value)
    kind = scale["kind"]
    params = scale["params"]
    if kind == "linear":
        locator = {"kind": "auto_minor", "params": {"n": None}}
    elif kind == "log":
        locator = {
            "kind": "log",
            "params": {
                "base": params["base"],
                "subs": params["subs"],
                "numticks": None,
            },
        }
    elif kind == "symlog":
        locator = {
            "kind": "symlog",
            "params": {
                "transform": {
                    "base": params["base"],
                    "linthresh": params["linthresh"],
                    "linscale": params["linscale"],
                },
                "subs": params["subs"],
            },
        }
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
    else:
        locator = {
            "kind": "logit",
            "params": {"minor": True, "nbins": "auto"},
        }
    return normalize_locator(locator)


def apply_scale(axes: Any, axis_name: str, value: Any) -> None:
    spec = normalize_scale(value)
    setter = axes.set_xscale if axis_name == "x" else axes.set_yscale
    setter(spec["kind"], **deepcopy(spec["params"]))


def scale_from_axis(axis: Any, previous: Any = None) -> dict[str, Any]:
    """Read a scale without exposing Matplotlib's private ScaleBase object."""

    kind = str(axis.get_scale())
    if isinstance(previous, Mapping) and previous.get("kind") == kind:
        try:
            return normalize_scale(previous)
        except ComponentValidationError:
            pass
    try:
        return default_scale_for_name(kind)
    except ComponentValidationError:
        return normalize_scale(DEFAULT_SCALE)


def normalize_locator(value: Any) -> dict[str, Any]:
    spec = _mapping(value, "Locator")
    _exact(spec, {"kind", "params"}, "Locator")
    kind = str(spec["kind"])
    params = _mapping(spec["params"], "Locator params")
    expected = {
        "auto": set(),
        "auto_minor": {"n"},
        "max_n": {"nbins", "steps", "integer", "symmetric", "prune", "min_n_ticks"},
        "multiple": {"base", "offset"},
        "linear": {"numticks"},
        "fixed": {"locations", "nbins"},
        "log": {"base", "subs", "numticks"},
        "symlog": {"transform", "subs"},
        "asinh": {"linear_width", "numticks", "symthresh", "base", "subs"},
        "logit": {"minor", "nbins"},
        "null": set(),
    }
    if kind not in expected:
        raise ComponentValidationError(f"Unsupported locator kind {kind!r}.")
    _exact(params, expected[kind], "Locator params")
    result = deepcopy(params)
    if kind == "auto_minor":
        if result["n"] not in {None, 4, 5}:
            raise ComponentValidationError("AutoMinor locator n must be null, 4, or 5.")
    elif kind == "max_n":
        if result["nbins"] != "auto":
            result["nbins"] = int(_positive(result["nbins"], "MaxN nbins"))
        result["steps"] = None if result["steps"] is None else _finite_sequence(result["steps"], "MaxN steps", positive=True)
        result["integer"] = bool(result["integer"])
        result["symmetric"] = bool(result["symmetric"])
        if result["prune"] not in {None, "lower", "upper", "both"}:
            raise ComponentValidationError("Invalid MaxN prune value.")
        result["min_n_ticks"] = int(_positive(result["min_n_ticks"], "MaxN min_n_ticks"))
    elif kind == "multiple":
        result = {"base": _positive(result["base"], "Multiple base"), "offset": _finite(result["offset"], "Multiple offset")}
    elif kind == "linear":
        result["numticks"] = int(_positive(result["numticks"], "Linear numticks"))
    elif kind == "fixed":
        result["locations"] = _finite_sequence(result["locations"], "Fixed locations")
        result["nbins"] = None if result["nbins"] is None else int(_positive(result["nbins"], "Fixed nbins"))
    elif kind == "log":
        result["base"] = _positive(result["base"], "Log locator base")
        result["subs"] = None if result["subs"] is None else _finite_sequence(result["subs"], "Log locator subs", positive=True)
        result["numticks"] = None if result["numticks"] is None else int(_positive(result["numticks"], "Log numticks"))
    elif kind == "symlog":
        transform = _mapping(result["transform"], "SymLog locator transform")
        _exact(transform, {"base", "linthresh", "linscale"}, "SymLog transform")
        result["transform"] = {
            "base": _positive(transform["base"], "SymLog base"),
            "linthresh": _positive(transform["linthresh"], "SymLog linthresh"),
            "linscale": _positive(transform["linscale"], "SymLog linscale"),
        }
        result["subs"] = None if result["subs"] is None else _finite_sequence(result["subs"], "SymLog locator subs", positive=True)
    elif kind == "asinh":
        result["linear_width"] = _positive(result["linear_width"], "Asinh linear width")
        result["numticks"] = int(_positive(result["numticks"], "Asinh numticks"))
        result["symthresh"] = _positive(result["symthresh"], "Asinh symthresh", allow_zero=True)
        result["base"] = _positive(result["base"], "Asinh base")
        result["subs"] = _finite_sequence(result["subs"], "Asinh subs", minimum_length=1)
    elif kind == "logit":
        nbins = result["nbins"]
        if nbins != "auto":
            nbins = int(_positive(nbins, "Logit nbins"))
        result = {"minor": bool(result["minor"]), "nbins": nbins}
    return {"kind": kind, "params": result}


DEFAULT_MAJOR_LOCATOR = {"kind": "auto", "params": {}}
DEFAULT_MINOR_LOCATOR = {"kind": "null", "params": {}}


def build_locator(value: Any) -> ticker.Locator:
    spec = normalize_locator(value)
    kind, params = spec["kind"], deepcopy(spec["params"])
    factories = {
        "auto": ticker.AutoLocator,
        "auto_minor": ticker.AutoMinorLocator,
        "max_n": ticker.MaxNLocator,
        "multiple": ticker.MultipleLocator,
        "linear": ticker.LinearLocator,
        "fixed": ticker.FixedLocator,
        "log": ticker.LogLocator,
        "asinh": ticker.AsinhLocator,
        "logit": ticker.LogitLocator,
        "null": ticker.NullLocator,
    }
    if kind == "symlog":
        transform = params.pop("transform")
        from matplotlib.scale import SymmetricalLogTransform
        params["transform"] = SymmetricalLogTransform(**transform)
        return ticker.SymmetricalLogLocator(**params)
    if kind == "fixed":
        locations = params.pop("locations")
        return ticker.FixedLocator(locations, **params)
    return factories[kind](**params)


_LOCATOR_CLASSES = {
    "auto": ticker.AutoLocator,
    "auto_minor": ticker.AutoMinorLocator,
    "max_n": ticker.MaxNLocator,
    "multiple": ticker.MultipleLocator,
    "linear": ticker.LinearLocator,
    "fixed": ticker.FixedLocator,
    "log": ticker.LogLocator,
    "symlog": ticker.SymmetricalLogLocator,
    "asinh": ticker.AsinhLocator,
    "logit": ticker.LogitLocator,
    "null": ticker.NullLocator,
}


def locator_from_axis(
    locator: ticker.Locator,
    previous: Any,
    *,
    minor: bool,
    scale: Any = None,
) -> dict[str, Any]:
    """Return a stable locator spec, retaining explicit parameters when valid."""

    try:
        saved = normalize_locator(previous)
        if isinstance(locator, _LOCATOR_CLASSES[saved["kind"]]):
            return saved
    except (ComponentValidationError, KeyError, TypeError):
        pass
    if isinstance(locator, ticker.NullLocator):
        return normalize_locator(DEFAULT_MINOR_LOCATOR)
    if isinstance(locator, ticker.AutoMinorLocator):
        divisions = getattr(locator, "ndivs", None)
        if divisions == "auto":
            divisions = None
        return normalize_locator(
            {"kind": "auto_minor", "params": {"n": divisions}}
        )
    if minor and scale is not None:
        default = default_minor_locator_for_scale(scale)
        expected = _LOCATOR_CLASSES[default["kind"]]
        if isinstance(locator, expected):
            return default
    if isinstance(locator, ticker.FixedLocator):
        return normalize_locator({"kind": "fixed", "params": {"locations": list(np.asarray(locator.locs, dtype=float)), "nbins": getattr(locator, "nbins", None)}})
    if isinstance(locator, ticker.LinearLocator):
        return normalize_locator({"kind": "linear", "params": {"numticks": int(locator.numticks)}})
    if isinstance(locator, ticker.MultipleLocator):
        edge = getattr(locator, "_edge", None)
        return normalize_locator({"kind": "multiple", "params": {"base": float(getattr(edge, "step", 1.0)), "offset": float(getattr(locator, "_offset", 0.0))}})
    return normalize_locator(DEFAULT_MINOR_LOCATOR if minor else DEFAULT_MAJOR_LOCATOR)


def normalize_formatter(value: Any) -> dict[str, Any]:
    spec = _mapping(value, "Formatter")
    _exact(spec, {"kind", "params"}, "Formatter")
    kind = str(spec["kind"])
    params = _mapping(spec["params"], "Formatter params")
    expected = {
        "scalar": {"use_offset", "use_math_text", "use_locale", "scientific", "powerlimits"},
        "engineering": {"unit", "places", "sep", "usetex", "use_math_text"},
        "percent": {"xmax", "decimals", "symbol", "is_latex"},
        "str_method": {"format"},
        "fixed": {"labels"},
        "log": {"base", "label_only_base", "minor_thresholds", "linthresh"},
        "log_exponent": {"base", "label_only_base", "minor_thresholds", "linthresh"},
        "log_mathtext": {"base", "label_only_base", "minor_thresholds", "linthresh"},
        "log_sci": {"base", "label_only_base", "minor_thresholds", "linthresh"},
        "logit": {"use_overline", "one_half", "minor", "minor_threshold"},
        "null": set(),
    }
    if kind not in expected:
        raise ComponentValidationError(f"Unsupported formatter kind {kind!r}.")
    _exact(params, expected[kind], "Formatter params")
    result = deepcopy(params)
    if kind == "scalar":
        result["use_offset"] = bool(result["use_offset"])
        result["use_math_text"] = bool(result["use_math_text"])
        result["use_locale"] = bool(result["use_locale"])
        result["scientific"] = bool(result["scientific"])
        limits = _finite_sequence(result["powerlimits"], "Scalar powerlimits", minimum_length=2)
        if len(limits) != 2:
            raise ComponentValidationError("Scalar powerlimits require two values.")
        result["powerlimits"] = [int(item) for item in limits]
    elif kind == "engineering":
        result["unit"] = str(result["unit"])
        result["places"] = None if result["places"] is None else int(_positive(result["places"], "Engineering places", allow_zero=True))
        result["sep"] = str(result["sep"])
        result["usetex"] = bool(result["usetex"])
        result["use_math_text"] = bool(result["use_math_text"])
    elif kind == "percent":
        result["xmax"] = _positive(result["xmax"], "Percent xmax")
        result["decimals"] = None if result["decimals"] is None else int(_positive(result["decimals"], "Percent decimals", allow_zero=True))
        result["symbol"] = str(result["symbol"])
        result["is_latex"] = bool(result["is_latex"])
    elif kind == "str_method":
        template = str(result["format"])
        fields = {field for _, field, _, _ in string.Formatter().parse(template) if field}
        if not fields or not fields.issubset({"x", "pos"}):
            raise ComponentValidationError("StrMethod format may reference only x and pos.")
        result["format"] = template
    elif kind == "fixed":
        if not isinstance(result["labels"], list) or not all(isinstance(item, str) for item in result["labels"]):
            raise ComponentValidationError("Fixed formatter labels must be strings.")
    elif kind.startswith("log") and kind != "logit":
        result["base"] = _positive(result["base"], "Log formatter base")
        result["label_only_base"] = bool(result["label_only_base"])
        thresholds = result["minor_thresholds"]
        if thresholds is not None:
            thresholds = _finite_sequence(thresholds, "Minor thresholds", minimum_length=2)
            if len(thresholds) != 2:
                raise ComponentValidationError("Minor thresholds require two values.")
        result["minor_thresholds"] = thresholds
        result["linthresh"] = _optional_finite(result["linthresh"], "Formatter linthresh")
    elif kind == "logit":
        result["use_overline"] = bool(result["use_overline"])
        result["one_half"] = str(result["one_half"])
        result["minor"] = bool(result["minor"])
        result["minor_threshold"] = int(_positive(result["minor_threshold"], "Logit minor threshold"))
    return {"kind": kind, "params": result}


DEFAULT_FORMATTER = {
    "kind": "scalar",
    "params": {
        "use_offset": True,
        "use_math_text": False,
        "use_locale": False,
        "scientific": True,
        "powerlimits": [-5, 6],
    },
}
DEFAULT_MINOR_FORMATTER = {"kind": "null", "params": {}}


def build_formatter(value: Any) -> ticker.Formatter:
    spec = normalize_formatter(value)
    kind, params = spec["kind"], deepcopy(spec["params"])
    if kind == "scalar":
        result = ticker.ScalarFormatter(
            useOffset=params.pop("use_offset"),
            useMathText=params.pop("use_math_text"),
            useLocale=params.pop("use_locale"),
        )
        result.set_scientific(params["scientific"])
        result.set_powerlimits(tuple(params["powerlimits"]))
        return result
    factories = {
        "engineering": ticker.EngFormatter,
        "percent": ticker.PercentFormatter,
        "str_method": ticker.StrMethodFormatter,
        "fixed": ticker.FixedFormatter,
        "log": ticker.LogFormatter,
        "log_exponent": ticker.LogFormatterExponent,
        "log_mathtext": ticker.LogFormatterMathtext,
        "log_sci": ticker.LogFormatterSciNotation,
        "logit": ticker.LogitFormatter,
        "null": ticker.NullFormatter,
    }
    if kind == "str_method":
        return factories[kind](params["format"])
    if kind == "fixed":
        return factories[kind](params["labels"])
    return factories[kind](**params)


_FORMATTER_CLASSES = {
    "scalar": ticker.ScalarFormatter,
    "engineering": ticker.EngFormatter,
    "percent": ticker.PercentFormatter,
    "str_method": ticker.StrMethodFormatter,
    "fixed": ticker.FixedFormatter,
    "log": ticker.LogFormatter,
    "log_exponent": ticker.LogFormatterExponent,
    "log_mathtext": ticker.LogFormatterMathtext,
    "log_sci": ticker.LogFormatterSciNotation,
    "logit": ticker.LogitFormatter,
    "null": ticker.NullFormatter,
}


def formatter_from_axis(formatter: ticker.Formatter, previous: Any, *, minor: bool) -> dict[str, Any]:
    """Return a stable formatter spec, retaining explicit safe parameters."""

    try:
        saved = normalize_formatter(previous)
        if isinstance(formatter, _FORMATTER_CLASSES[saved["kind"]]):
            return saved
    except (ComponentValidationError, KeyError, TypeError):
        pass
    if isinstance(formatter, ticker.NullFormatter):
        return normalize_formatter(DEFAULT_MINOR_FORMATTER)
    if isinstance(formatter, ticker.FixedFormatter):
        return normalize_formatter({"kind": "fixed", "params": {"labels": list(formatter.seq)}})
    if isinstance(formatter, ticker.StrMethodFormatter):
        return normalize_formatter({"kind": "str_method", "params": {"format": str(formatter.fmt)}})
    return normalize_formatter(DEFAULT_MINOR_FORMATTER if minor else DEFAULT_FORMATTER)


def normalize_line_pattern(value: Any) -> dict[str, Any]:
    spec = _mapping(value, "Line pattern")
    kind = spec.get("kind")
    if kind == "preset":
        _exact(spec, {"kind", "value"}, "Line pattern")
        candidate = str(spec["value"])
        aliases = {"solid": "-", "dashed": "--", "dashdot": "-.", "dotted": ":", "none": "None", "": "None"}
        candidate = aliases.get(candidate.lower(), candidate)
        if candidate not in {"-", "--", "-.", ":", "None"}:
            raise ComponentValidationError("Unsupported preset line pattern.")
        return {"kind": "preset", "value": candidate}
    if kind == "custom":
        _exact(spec, {"kind", "offset", "dashes"}, "Line pattern")
        dashes = _finite_sequence(spec["dashes"], "Dash sequence", minimum_length=2, positive=True)
        if len(dashes) % 2:
            raise ComponentValidationError("Dash sequence length must be even.")
        return {"kind": "custom", "offset": _finite(spec["offset"], "Dash offset"), "dashes": dashes}
    raise ComponentValidationError("Line pattern kind must be preset or custom.")


def apply_line_pattern(line: Any, value: Any) -> None:
    spec = normalize_line_pattern(value)
    if spec["kind"] == "preset":
        line.set_linestyle(spec["value"])
    else:
        line.set_linestyle((spec["offset"], tuple(spec["dashes"])))


def normalize_marker(value: Any) -> dict[str, Any]:
    spec = _mapping(value, "Marker")
    kind = spec.get("kind")
    if kind == "symbol":
        _exact(spec, {"kind", "value"}, "Marker")
        candidate = spec["value"]
        if not isinstance(candidate, (str, int)) or isinstance(candidate, bool):
            raise ComponentValidationError("Marker symbol must be text or an integer.")
        return {"kind": kind, "value": candidate}
    if kind == "regular_polygon":
        _exact(spec, {"kind", "sides", "style", "angle"}, "Marker")
        sides = int(spec["sides"])
        style = int(spec["style"])
        if sides < 3 or style not in {0, 1, 2}:
            raise ComponentValidationError("Invalid regular-polygon marker.")
        return {"kind": kind, "sides": sides, "style": style, "angle": _finite(spec["angle"], "Marker angle")}
    raise ComponentValidationError("Unsupported marker kind.")


def marker_value(value: Any) -> Any:
    spec = normalize_marker(value)
    if spec["kind"] == "symbol":
        return spec["value"]
    return (spec["sides"], spec["style"], spec["angle"])


def normalize_markevery(value: Any) -> dict[str, Any]:
    spec = _mapping(value, "Markevery")
    kind = spec.get("kind")
    fields = {
        "all": {"kind"},
        "stride": {"kind", "start", "step"},
        "slice": {"kind", "start", "stop", "step"},
        "indices": {"kind", "values"},
        "spacing": {"kind", "start", "distance"},
    }
    if kind not in fields:
        raise ComponentValidationError("Unsupported markevery kind.")
    _exact(spec, fields[kind], "Markevery")
    if kind == "all":
        return {"kind": kind}
    if kind == "stride":
        start = None if spec["start"] is None else int(spec["start"])
        step = int(spec["step"])
        if step <= 0:
            raise ComponentValidationError("Markevery step must be positive.")
        return {"kind": kind, "start": start, "step": step}
    if kind == "slice":
        step = None if spec["step"] is None else int(spec["step"])
        if step == 0:
            raise ComponentValidationError("Markevery slice step cannot be zero.")
        return {"kind": kind, "start": None if spec["start"] is None else int(spec["start"]), "stop": None if spec["stop"] is None else int(spec["stop"]), "step": step}
    if kind == "indices":
        if not isinstance(spec["values"], list) or not all(isinstance(item, int) and not isinstance(item, bool) for item in spec["values"]):
            raise ComponentValidationError("Markevery indices must be integers.")
        return {"kind": kind, "values": list(spec["values"])}
    start = _positive(spec["start"], "Markevery spacing start", allow_zero=True)
    distance = _positive(spec["distance"], "Markevery display distance")
    return {"kind": kind, "start": start, "distance": distance}


def markevery_value(value: Any) -> Any:
    spec = normalize_markevery(value)
    if spec["kind"] == "all":
        return None
    if spec["kind"] == "stride":
        return spec["step"] if spec["start"] is None else (spec["start"], spec["step"])
    if spec["kind"] == "slice":
        return slice(spec["start"], spec["stop"], spec["step"])
    if spec["kind"] == "indices":
        return spec["values"]
    return spec["distance"] if spec["start"] == 0 else (spec["start"], spec["distance"])


def normalize_font(value: Any) -> dict[str, Any]:
    spec = _mapping(value, "Font")
    expected = {"family", "size", "weight", "style", "stretch", "variant", "color"}
    _exact(spec, expected, "Font")
    family = spec["family"]
    if isinstance(family, str):
        family = [family]
    if not isinstance(family, list) or not family or not all(isinstance(item, str) and item for item in family):
        raise ComponentValidationError("Font family must contain names.")
    weight = spec["weight"]
    if not isinstance(weight, (str, int, float)) or isinstance(weight, bool):
        raise ComponentValidationError("Font weight is invalid.")
    return {
        "family": family,
        "size": _positive(spec["size"], "Font size"),
        "weight": weight,
        "style": str(spec["style"]),
        "stretch": spec["stretch"],
        "variant": str(spec["variant"]),
        "color": _color(spec["color"], "Font color"),
    }


def normalize_text_box(value: Any) -> dict[str, Any]:
    spec = _mapping(value, "Text box")
    if spec.get("enabled") is False:
        _exact(spec, {"enabled"}, "Text box")
        return {"enabled": False}
    expected = {"enabled", "boxstyle", "facecolor", "edgecolor", "linewidth", "line_pattern", "alpha", "fill", "hatch", "pad"}
    _exact(spec, expected, "Text box")
    if spec["enabled"] is not True:
        raise ComponentValidationError("Text box enabled must be boolean.")
    return {
        "enabled": True,
        "boxstyle": str(spec["boxstyle"]),
        "facecolor": _color(spec["facecolor"], "Text box face color"),
        "edgecolor": _color(spec["edgecolor"], "Text box edge color"),
        "linewidth": _positive(spec["linewidth"], "Text box linewidth", allow_zero=True),
        "line_pattern": normalize_line_pattern(spec["line_pattern"]),
        "alpha": None if spec["alpha"] is None else min(1.0, max(0.0, _finite(spec["alpha"], "Text box alpha"))),
        "fill": bool(spec["fill"]),
        "hatch": None if spec["hatch"] is None else str(spec["hatch"]),
        "pad": _positive(spec["pad"], "Text box pad", allow_zero=True),
    }


def text_box_kwargs(value: Any) -> dict[str, Any] | None:
    spec = normalize_text_box(value)
    if not spec["enabled"]:
        return None
    pattern = spec["line_pattern"]
    linestyle: Any = pattern["value"] if pattern["kind"] == "preset" else (pattern["offset"], pattern["dashes"])
    return {
        "boxstyle": f"{spec['boxstyle']},pad={spec['pad']}",
        "facecolor": spec["facecolor"],
        "edgecolor": spec["edgecolor"],
        "linewidth": spec["linewidth"],
        "linestyle": linestyle,
        "alpha": spec["alpha"],
        "fill": spec["fill"],
        "hatch": spec["hatch"],
    }


_LEGEND_LOCATIONS = frozenset(
    {
        "best",
        "upper right",
        "upper left",
        "lower left",
        "lower right",
        "right",
        "center left",
        "center right",
        "lower center",
        "upper center",
        "center",
        "outside right upper",
        "outside right lower",
        "outside left upper",
        "outside left lower",
        "outside upper right",
        "outside upper left",
        "outside lower right",
        "outside lower left",
    }
)


def normalize_legend_location(value: Any) -> dict[str, Any]:
    """Normalize a legend location without persisting Matplotlib internals."""

    if isinstance(value, str):
        value = {"kind": "preset", "value": value}
    elif isinstance(value, int) and not isinstance(value, bool):
        value = {"kind": "code", "value": value}
    elif isinstance(value, (tuple, list)):
        value = {"kind": "point", "x": value[0], "y": value[1]} if len(value) == 2 else value
    spec = _mapping(value, "Legend location")
    kind = spec.get("kind")
    if kind == "preset":
        _exact(spec, {"kind", "value"}, "Legend location")
        location = str(spec["value"])
        if location not in _LEGEND_LOCATIONS:
            raise ComponentValidationError(f"Unsupported legend location {location!r}.")
        return {"kind": "preset", "value": location}
    if kind == "code":
        _exact(spec, {"kind", "value"}, "Legend location")
        code = spec["value"]
        if isinstance(code, bool) or not isinstance(code, int) or code not in range(0, 11):
            raise ComponentValidationError("Legend location code must be an integer from 0 through 10.")
        return {"kind": "code", "value": code}
    if kind == "point":
        _exact(spec, {"kind", "x", "y"}, "Legend location")
        return {
            "kind": "point",
            "x": _finite(spec["x"], "Legend location x"),
            "y": _finite(spec["y"], "Legend location y"),
        }
    raise ComponentValidationError(f"Unsupported legend location kind {kind!r}.")


def legend_location_value(value: Any) -> Any:
    spec = normalize_legend_location(value)
    if spec["kind"] in {"preset", "code"}:
        return spec["value"]
    return spec["x"], spec["y"]


def normalize_legend_anchor(value: Any) -> dict[str, Any]:
    """Normalize an optional 2- or 4-coordinate legend anchor."""

    if value is None:
        value = {"kind": "none"}
    elif isinstance(value, (tuple, list)):
        if len(value) == 2:
            value = {"kind": "point", "x": value[0], "y": value[1]}
        elif len(value) == 4:
            value = {
                "kind": "bounds",
                "x": value[0],
                "y": value[1],
                "width": value[2],
                "height": value[3],
            }
    spec = _mapping(value, "Legend anchor")
    kind = spec.get("kind")
    expected = {
        "none": {"kind"},
        "point": {"kind", "x", "y"},
        "bounds": {"kind", "x", "y", "width", "height"},
    }
    if kind not in expected:
        raise ComponentValidationError(f"Unsupported legend anchor kind {kind!r}.")
    _exact(spec, expected[kind], "Legend anchor")
    result = {"kind": kind}
    for key in expected[kind] - {"kind"}:
        result[key] = _finite(spec[key], f"Legend anchor {key}")
    return result


def legend_anchor_value(value: Any) -> tuple[float, ...] | None:
    spec = normalize_legend_anchor(value)
    if spec["kind"] == "none":
        return None
    if spec["kind"] == "point":
        return spec["x"], spec["y"]
    return spec["x"], spec["y"], spec["width"], spec["height"]


def normalize_norm(value: Any) -> dict[str, Any]:
    spec = _mapping(value, "Norm")
    _exact(spec, {"kind", "params"}, "Norm")
    kind = str(spec["kind"])
    params = _mapping(spec["params"], "Norm params")
    expected = {
        "linear": {"vmin", "vmax", "clip"},
        "log": {"vmin", "vmax", "clip"},
        "symlog": {"linthresh", "linscale", "vmin", "vmax", "clip", "base"},
        "power": {"gamma", "vmin", "vmax", "clip"},
        "two_slope": {"vcenter", "vmin", "vmax"},
        "centered": {"vcenter", "halfrange", "clip"},
        "boundary": {"boundaries", "ncolors", "clip", "extend"},
        "asinh": {"linear_width", "vmin", "vmax", "clip"},
        "none": set(),
    }
    if kind not in expected:
        raise ComponentValidationError(f"Unsupported norm kind {kind!r}.")
    _exact(params, expected[kind], "Norm params")
    result = deepcopy(params)
    for key in ("vmin", "vmax"):
        if key in result:
            result[key] = _optional_finite(result[key], f"Norm {key}")
    if "clip" in result:
        result["clip"] = bool(result["clip"])
    if kind == "log" and result["vmin"] is not None and result["vmin"] <= 0:
        raise ComponentValidationError("Log norm vmin must be positive.")
    if kind == "symlog":
        result["linthresh"] = _positive(result["linthresh"], "Norm linthresh")
        result["linscale"] = _positive(result["linscale"], "Norm linscale")
        result["base"] = _positive(result["base"], "Norm base")
    elif kind == "power":
        result["gamma"] = _positive(result["gamma"], "Norm gamma")
    elif kind == "two_slope":
        result["vcenter"] = _finite(result["vcenter"], "Norm center")
    elif kind == "centered":
        result["vcenter"] = _finite(result["vcenter"], "Norm center")
        result["halfrange"] = None if result["halfrange"] is None else _positive(result["halfrange"], "Norm half range")
    elif kind == "boundary":
        result["boundaries"] = _finite_sequence(result["boundaries"], "Norm boundaries", minimum_length=2)
        if any(right <= left for left, right in zip(result["boundaries"], result["boundaries"][1:])):
            raise ComponentValidationError("Norm boundaries must increase.")
        result["ncolors"] = int(_positive(result["ncolors"], "Norm color count"))
        if result["extend"] not in {"neither", "both", "min", "max"}:
            raise ComponentValidationError("Invalid boundary norm extend value.")
    elif kind == "asinh":
        result["linear_width"] = _positive(result["linear_width"], "Norm linear width")
    return {"kind": kind, "params": result}


def build_norm(value: Any) -> mcolors.Normalize:
    spec = normalize_norm(value)
    factories = {
        "linear": mcolors.Normalize,
        "log": mcolors.LogNorm,
        "symlog": mcolors.SymLogNorm,
        "power": mcolors.PowerNorm,
        "two_slope": mcolors.TwoSlopeNorm,
        "centered": mcolors.CenteredNorm,
        "boundary": mcolors.BoundaryNorm,
        "asinh": mcolors.AsinhNorm,
        "none": mcolors.NoNorm,
    }
    return factories[spec["kind"]](**deepcopy(spec["params"]))


DEFAULT_NORM = {"kind": "linear", "params": {"vmin": None, "vmax": None, "clip": False}}


DEFAULT_COLOR_MAP = {
    "cmap": "viridis",
    "norm": deepcopy(DEFAULT_NORM),
    "bad": "#00000000",
    "under": None,
    "over": None,
}


DEFAULT_GRID_EDGE = {"kind": "none"}
DEFAULT_CONTOUR_LEVELS = {"kind": "count", "count": 8}
DEFAULT_CONTOUR_LABELS = {
    "enabled": False,
    "fmt": "general",
    "fontsize": 10.0,
    "color": None,
    "inline": True,
    "inline_spacing": 5.0,
}


def normalize_color_map_spec(value: Any) -> dict[str, Any]:
    """Normalize a closed colormap, norm, and out-of-range color contract."""

    spec = _mapping(value, "Color map")
    expected = {"cmap", "norm", "bad", "under", "over"}
    _exact(spec, expected, "Color map")
    cmap = str(spec["cmap"])
    if not has_colormap(cmap):
        raise ComponentValidationError(f"Unknown colormap {cmap!r}.")
    return {
        "cmap": cmap,
        "norm": normalize_norm(spec["norm"]),
        "bad": _color(spec["bad"], "Bad color"),
        "under": _color(spec["under"], "Under color", allow_none=True),
        "over": _color(spec["over"], "Over color", allow_none=True),
    }


def apply_color_map_spec(mappable: Any, value: Any) -> None:
    """Write a closed colormap specification onto a ScalarMappable."""

    spec = normalize_color_map_spec(value)
    cmap = copy_colormap(spec["cmap"])
    cmap.set_bad(spec["bad"])
    if spec["under"] is not None:
        cmap.set_under(spec["under"])
    if spec["over"] is not None:
        cmap.set_over(spec["over"])
    mappable.set_cmap(cmap)
    mappable.set_norm(build_norm(spec["norm"]))


def normalize_grid_edge_spec(value: Any) -> dict[str, Any]:
    """Normalize pcolormesh edgecolor mode: none, face, or an explicit color."""

    spec = _mapping(value, "Grid edge")
    kind = str(spec.get("kind", ""))
    if kind == "none":
        _exact(spec, {"kind"}, "Grid edge")
        return {"kind": "none"}
    if kind == "face":
        _exact(spec, {"kind"}, "Grid edge")
        return {"kind": "face"}
    if kind == "color":
        _exact(spec, {"kind", "value"}, "Grid edge")
        return {"kind": "color", "value": _color(spec["value"], "Grid edge color")}
    raise ComponentValidationError("Grid edge kind must be none, face, or color.")


def grid_edge_value(value: Any) -> Any:
    spec = normalize_grid_edge_spec(value)
    if spec["kind"] == "none":
        return "none"
    if spec["kind"] == "face":
        return "face"
    return spec["value"]


def normalize_contour_levels_spec(value: Any) -> dict[str, Any]:
    """Normalize automatic count or strictly increasing explicit contour levels."""

    spec = _mapping(value, "Contour levels")
    kind = str(spec.get("kind", ""))
    if kind == "count":
        _exact(spec, {"kind", "count"}, "Contour levels")
        count = spec["count"]
        if isinstance(count, bool) or not isinstance(count, int):
            raise ComponentValidationError("Contour level count must be an integer.")
        if count < 2 or count > 256:
            raise ComponentValidationError(
                "Automatic contour levels must be between 2 and 256."
            )
        return {"kind": "count", "count": int(count)}
    if kind == "values":
        _exact(spec, {"kind", "values"}, "Contour levels")
        values = _finite_sequence(spec["values"], "Contour levels", minimum_length=2)
        if any(right <= left for left, right in zip(values, values[1:])):
            raise ComponentValidationError(
                "Explicit contour levels must be strictly increasing."
            )
        if len(values) > 256:
            raise ComponentValidationError(
                "Explicit contour levels must contain at most 256 values."
            )
        return {"kind": "values", "values": values}
    raise ComponentValidationError("Contour levels kind must be count or values.")


def contour_levels_value(value: Any) -> Any:
    spec = normalize_contour_levels_spec(value)
    if spec["kind"] == "count":
        return int(spec["count"])
    return spec["values"]


def normalize_contour_label_spec(value: Any) -> dict[str, Any]:
    """Normalize closed contour-label formatting and placement."""

    from mygui.figuremodify.matplotlib_adapter import CONTOUR_LABEL_FORMAT_CHOICES

    spec = _mapping(value, "Contour labels")
    expected = {"enabled", "fmt", "fontsize", "color", "inline", "inline_spacing"}
    _exact(spec, expected, "Contour labels")
    fmt = str(spec["fmt"])
    if fmt not in CONTOUR_LABEL_FORMAT_CHOICES:
        raise ComponentValidationError(f"Unsupported contour label format {fmt!r}.")
    fontsize = _positive(spec["fontsize"], "Contour label fontsize")
    spacing = _positive(spec["inline_spacing"], "Contour label spacing", allow_zero=True)
    return {
        "enabled": bool(spec["enabled"]),
        "fmt": fmt,
        "fontsize": fontsize,
        "color": _color(spec["color"], "Contour label color", allow_none=True),
        "inline": bool(spec["inline"]),
        "inline_spacing": spacing,
    }


CONTOUR_LABEL_FORMATTERS = {
    "general": "%g",
    "scientific": "%.3e",
    "fixed": "%.2f",
    "integer": "%d",
}


def contour_label_fmt(value: Any) -> str:
    spec = normalize_contour_label_spec(value)
    return CONTOUR_LABEL_FORMATTERS[spec["fmt"]]


def normalize_scatter_color_map(value: Any) -> dict[str, Any]:
    spec = _mapping(value, "Scatter color map")
    expected = {"enabled", "cmap", "norm", "bad", "under", "over", "nonfinite"}
    _exact(spec, expected, "Scatter color map")
    cmap = str(spec["cmap"])
    if not has_colormap(cmap):
        raise ComponentValidationError(f"Unknown colormap {cmap!r}.")
    if spec["nonfinite"] not in {"drop", "bad"}:
        raise ComponentValidationError("Scatter nonfinite policy is invalid.")
    return {
        "enabled": bool(spec["enabled"]),
        "cmap": cmap,
        "norm": normalize_norm(spec["norm"]),
        "bad": _color(spec["bad"], "Bad color"),
        "under": _color(spec["under"], "Under color", allow_none=True),
        "over": _color(spec["over"], "Over color", allow_none=True),
        "nonfinite": spec["nonfinite"],
    }


def normalize_scatter_size_map(value: Any) -> dict[str, Any]:
    spec = _mapping(value, "Scatter size map")
    expected = {"enabled", "input", "output", "clamp"}
    _exact(spec, expected, "Scatter size map")
    input_range = spec["input"]
    if input_range is not None:
        input_range = _finite_sequence(input_range, "Size input range", minimum_length=2)
        if len(input_range) != 2 or input_range[0] == input_range[1]:
            raise ComponentValidationError("Size input range requires two distinct values.")
    output = _finite_sequence(spec["output"], "Size output range", minimum_length=2)
    if len(output) != 2 or any(item < 0 for item in output):
        raise ComponentValidationError("Size output range must contain two non-negative values.")
    return {"enabled": bool(spec["enabled"]), "input": input_range, "output": output, "clamp": bool(spec["clamp"])}


def map_scatter_sizes(values: Any, spec_value: Any) -> np.ndarray:
    spec = normalize_scatter_size_map(spec_value)
    array = np.asarray(values, dtype=float)
    if not spec["enabled"]:
        return array
    source = spec["input"]
    if source is None:
        finite = array[np.isfinite(array)]
        if not len(finite):
            return np.full_like(array, np.nan)
        source = [float(finite.min()), float(finite.max())]
        if source[0] == source[1]:
            return np.full_like(array, float(sum(spec["output"]) / 2.0))
    mapped = np.interp(array, source, spec["output"])
    if not spec["clamp"]:
        scale = (spec["output"][1] - spec["output"][0]) / (source[1] - source[0])
        mapped = spec["output"][0] + (array - source[0]) * scale
    return np.maximum(mapped, 0.0)


def normalize_connector(value: Any) -> dict[str, Any]:
    spec = _mapping(value, "Connector")
    expected = {"visible", "color", "line_pattern", "linewidth", "alpha", "zorder"}
    _exact(spec, expected, "Connector")
    alpha = _finite(spec["alpha"], "Connector alpha")
    if not 0 <= alpha <= 1:
        raise ComponentValidationError("Connector alpha must be between zero and one.")
    return {
        "visible": bool(spec["visible"]),
        "color": _color(spec["color"], "Connector color"),
        "line_pattern": normalize_line_pattern(spec["line_pattern"]),
        "linewidth": _positive(spec["linewidth"], "Connector linewidth", allow_zero=True),
        "alpha": alpha,
        "zorder": _finite(spec["zorder"], "Connector zorder"),
    }


def validate_fixed_ticker_pair(locator: Any, formatter: Any) -> None:
    locator_spec = normalize_locator(locator)
    formatter_spec = normalize_formatter(formatter)
    if formatter_spec["kind"] != "fixed":
        return
    if locator_spec["kind"] != "fixed":
        raise ComponentValidationError("FixedFormatter requires FixedLocator.")
    if len(locator_spec["params"]["locations"]) != len(formatter_spec["params"]["labels"]):
        raise ComponentValidationError("Fixed locator and formatter lengths must match.")
