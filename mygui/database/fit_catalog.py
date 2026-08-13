"""Backend-independent canonical curve-fitting model catalog."""

from types import MappingProxyType


FIT_MODEL_GROUPS = MappingProxyType(
    {
        "poly": tuple(f"poly{order}" for order in range(1, 10)),
        "exp": ("exp1", "exp2"),
        "log": ("log",),
        "fourier": tuple(f"fourier{order}" for order in range(1, 9)),
        "gauss": tuple(f"gauss{order}" for order in range(1, 9)),
        "power": ("power1", "power2"),
        "rat": tuple(
            f"rat{numerator}{denominator}"
            for numerator in range(6)
            for denominator in range(1, 6)
        ),
        "sin": tuple(f"sin{order}" for order in range(1, 9)),
        "weibull": ("weibull",),
        "sigmoid": ("logistic", "logistic4", "gompertz"),
    }
)

FIT_MODEL_IDS = tuple(
    model
    for models in FIT_MODEL_GROUPS.values()
    for model in models
)


def fit_model_group(model_id: str) -> str:
    """Return the canonical group for one model identifier."""

    for group, models in FIT_MODEL_GROUPS.items():
        if model_id in models:
            return group
    raise KeyError(model_id)
