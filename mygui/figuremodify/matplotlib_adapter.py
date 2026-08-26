"""Provide the authorized boundary for process-global Matplotlib facilities."""

from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Iterator

import matplotlib
from matplotlib import font_manager
from matplotlib import style as mpl_style
from matplotlib.lines import Line2D


@contextmanager
def matplotlib_style_context(style: str | None) -> Iterator[None]:
    """Apply one Figure style temporarily and restore global rcParams."""

    with mpl_style.context(str(style or "default")):
        yield


def available_style_names() -> tuple[str, ...]:
    """Return the immutable catalog of installed Matplotlib styles."""

    return tuple(mpl_style.available)


def available_colormap_names() -> tuple[str, ...]:
    """Return the immutable, sorted Matplotlib colormap catalog."""

    return tuple(sorted(matplotlib.colormaps))


def has_colormap(name: str) -> bool:
    """Return whether the named Matplotlib colormap is registered."""

    try:
        matplotlib.colormaps[str(name)]
    except KeyError:
        return False
    return True


def copy_colormap(name: str):
    """Return a mutable copy of one registered Matplotlib colormap."""

    return matplotlib.colormaps[str(name)].copy()


IMAGE_INTERPOLATION_CHOICES: tuple[str, ...] = (
    "none",
    "antialiased",
    "nearest",
    "bilinear",
    "bicubic",
    "spline16",
    "spline36",
    "hanning",
    "hamming",
    "hermite",
    "kaiser",
    "quadric",
    "catrom",
    "gaussian",
    "bessel",
    "mitchell",
    "sinc",
    "lanczos",
    "blackman",
)


PSEUDOCOLOR_SHADING_CHOICES: tuple[str, ...] = (
    "auto",
    "flat",
    "nearest",
    "gouraud",
)


CONTOUR_MODE_CHOICES: tuple[str, ...] = ("lines", "filled", "overlay")
CONTOUR_EXTEND_CHOICES: tuple[str, ...] = ("neither", "both", "min", "max")
CONTOUR_ALGORITHM_CHOICES: tuple[str, ...] = ("mpl2014", "serial", "threaded")
CONTOUR_LABEL_FORMAT_CHOICES: tuple[str, ...] = (
    "general",
    "scientific",
    "fixed",
    "integer",
)
INTERPOLATION_STAGE_CHOICES: tuple[str, ...] = ("data", "rgba")


def available_marker_definitions() -> tuple[tuple[Any, str], ...]:
    """Return supported marker values paired with Matplotlib descriptions."""

    definitions: list[tuple[Any, str]] = []
    for key, description in Line2D.markers.items():
        if key is None or (isinstance(key, str) and not key.strip()):
            continue
        if str(description) == "nothing":
            continue
        definitions.append((key, str(description)))
    return tuple(definitions)


_FONT_FAMILY_CATALOG: tuple[str, ...] | None = None


def available_font_families() -> tuple[str, ...]:
    """Return installed font families Matplotlib 3.9 can identify.

    The catalog is deduplicated, sorted, immutable, and cached for the
    process so Settings pages do not rescan system fonts.
    """

    global _FONT_FAMILY_CATALOG
    cached = _FONT_FAMILY_CATALOG
    if cached is not None:
        return cached
    names = font_manager.fontManager.get_font_names()
    catalog = tuple(
        sorted({str(name).strip() for name in names if str(name).strip()})
    )
    _FONT_FAMILY_CATALOG = catalog
    return catalog
