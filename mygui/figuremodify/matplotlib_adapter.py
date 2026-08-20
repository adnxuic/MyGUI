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


def available_font_families() -> tuple[str, ...]:
    """Return the installed font families Matplotlib can identify."""

    paths = font_manager.findSystemFonts()
    families = {
        font_manager.FontProperties(fname=path).get_name()
        for path in paths
    }
    return tuple(sorted(families))
