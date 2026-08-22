"""Static Matplotlib 3.9 property-exposure manifest.

The manifest is intentionally independent from Editor profiles.  It prevents
new upstream setters from becoming silently available or silently ignored and
records why object/callable/internal setters are not persisted by MyGUI.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Mapping

import matplotlib
from matplotlib.artist import ArtistInspector
from matplotlib.collections import LineCollection
from matplotlib.figure import Figure

from .errors import ComponentValidationError


class ExposureClass(StrEnum):
    CORE = "core"
    ADVANCED = "advanced"
    ALIAS = "alias"
    DERIVED = "derived/owned_elsewhere"
    UNSUPPORTED = "unsupported"


@dataclass(frozen=True, slots=True)
class ArtistExposureContract:
    core: frozenset[str]
    advanced: frozenset[str]
    aliases: frozenset[str]
    derived: frozenset[str]
    unsupported: Mapping[str, str]

    @property
    def classified(self) -> frozenset[str]:
        return frozenset(
            set(self.core)
            | set(self.advanced)
            | set(self.aliases)
            | set(self.derived)
            | set(self.unsupported)
        )


def _contract(
    *,
    core=(),
    advanced=(),
    aliases=(),
    derived=(),
    unsupported=(),
    unsupported_reason: str = "requires a runtime object or interaction state",
) -> ArtistExposureContract:
    return ArtistExposureContract(
        frozenset(core),
        frozenset(advanced),
        frozenset(aliases),
        frozenset(derived),
        {str(key): unsupported_reason for key in unsupported},
    )


MATPLOTLIB_39_EXPOSURE: dict[str, ArtistExposureContract] = {
    "Figure": _contract(
        core={"alpha", "dpi", "edgecolor", "facecolor", "frameon", "layout_engine", "linewidth", "size_inches"},
        advanced={"clip_on", "gid", "in_layout", "label", "rasterized", "sketch_params", "snap", "url", "visible", "zorder"},
        aliases={"constrained_layout", "constrained_layout_pads", "figheight", "figwidth", "tight_layout"},
        unsupported={"agg_filter", "animated", "canvas", "clip_box", "clip_path", "figure", "mouseover", "path_effects", "picker", "transform"},
    ),
    "Axes": _contract(
        core={"adjustable", "anchor", "aspect", "autoscale_on", "autoscalex_on", "autoscaley_on", "axisbelow", "box_aspect", "facecolor", "frame_on", "rasterization_zorder", "visible", "xlim", "xmargin", "ylim", "ymargin", "zorder"},
        advanced={"alpha", "clip_on", "gid", "in_layout", "label", "rasterized", "sketch_params", "snap", "url"},
        aliases={"xbound", "ybound"},
        derived={"position", "prop_cycle", "title", "xlabel", "xscale", "xticklabels", "xticks", "ylabel", "yscale", "yticklabels", "yticks"},
        unsupported={"agg_filter", "animated", "axes_locator", "clip_box", "clip_path", "figure", "forward_navigation_events", "mouseover", "navigate", "navigate_mode", "path_effects", "picker", "subplotspec", "transform"},
    ),
    "XAxis": _contract(
        core={"label_position", "major_formatter", "major_locator", "minor_formatter", "minor_locator", "remove_overlapping_locs", "visible", "zorder"},
        advanced={"alpha", "clip_on", "gid", "in_layout", "rasterized", "sketch_params", "snap", "url"},
        aliases={"label_coords", "label_text"},
        derived={"inverted", "tick_params", "ticklabels", "ticks", "ticks_position"},
        unsupported={"agg_filter", "animated", "clip_box", "clip_path", "data_interval", "figure", "label", "mouseover", "path_effects", "picker", "pickradius", "transform", "units", "view_interval"},
    ),
    "YAxis": _contract(
        core={"label_position", "major_formatter", "major_locator", "minor_formatter", "minor_locator", "offset_position", "remove_overlapping_locs", "visible", "zorder"},
        advanced={"alpha", "clip_on", "gid", "in_layout", "rasterized", "sketch_params", "snap", "url"},
        aliases={"label_coords", "label_text"},
        derived={"inverted", "tick_params", "ticklabels", "ticks", "ticks_position"},
        unsupported={"agg_filter", "animated", "clip_box", "clip_path", "data_interval", "figure", "label", "mouseover", "path_effects", "picker", "pickradius", "transform", "units", "view_interval"},
    ),
    "Spine": _contract(
        core={"alpha", "antialiased", "bounds", "capstyle", "color", "joinstyle", "linestyle", "linewidth", "position", "visible", "zorder"},
        advanced={"clip_on", "gid", "in_layout", "label", "rasterized", "sketch_params", "snap", "url"},
        aliases={"edgecolor"},
        derived={"facecolor", "fill", "hatch"},
        unsupported={"agg_filter", "animated", "clip_box", "clip_path", "figure", "mouseover", "patch_arc", "patch_circle", "path_effects", "picker", "transform"},
    ),
    "Text": _contract(
        core={"alpha", "antialiased", "bbox", "color", "fontfamily", "fontsize", "fontstretch", "fontstyle", "fontvariant", "fontweight", "horizontalalignment", "linespacing", "math_fontfamily", "multialignment", "parse_math", "position", "rotation", "rotation_mode", "text", "transform_rotates_text", "usetex", "verticalalignment", "visible", "wrap", "zorder"},
        advanced={"clip_on", "gid", "in_layout", "label", "rasterized", "sketch_params", "snap", "url"},
        aliases={"backgroundcolor", "fontproperties", "x", "y"},
        unsupported={"agg_filter", "animated", "clip_box", "clip_path", "figure", "mouseover", "path_effects", "picker", "transform"},
    ),
    "Legend": _contract(
        core={"alignment", "bbox_to_anchor", "draggable", "frame_on", "loc", "ncols", "title", "visible", "zorder"},
        advanced={"alpha", "clip_on", "gid", "in_layout", "label", "rasterized", "sketch_params", "snap", "url"},
        unsupported={"agg_filter", "animated", "clip_box", "clip_path", "figure", "mouseover", "path_effects", "picker", "transform"},
    ),
    "Line2D": _contract(
        core={"alpha", "antialiased", "color", "dash_capstyle", "dash_joinstyle", "dashes", "drawstyle", "fillstyle", "gapcolor", "label", "linestyle", "linewidth", "marker", "markeredgecolor", "markeredgewidth", "markerfacecolor", "markerfacecoloralt", "markersize", "markevery", "solid_capstyle", "solid_joinstyle", "visible", "zorder"},
        advanced={"clip_on", "gid", "in_layout", "rasterized", "sketch_params", "snap", "url"},
        aliases={"data", "xdata", "ydata"},
        unsupported={"agg_filter", "animated", "clip_box", "clip_path", "figure", "mouseover", "path_effects", "picker", "pickradius", "transform"},
    ),
    "PathCollection": _contract(
        core={"alpha", "antialiased", "capstyle", "color", "edgecolor", "facecolor", "hatch", "joinstyle", "label", "linestyle", "linewidth", "sizes", "visible", "zorder"},
        advanced={"clip_on", "gid", "in_layout", "rasterized", "sketch_params", "snap", "url", "urls"},
        derived={"array", "clim", "cmap", "norm", "offsets", "paths"},
        unsupported={"agg_filter", "animated", "clip_box", "clip_path", "figure", "mouseover", "offset_transform", "path_effects", "picker", "pickradius", "transform"},
    ),
    "LineCollection": _contract(
        core={"alpha", "clip_on", "color", "label", "linestyle", "linewidth", "visible", "zorder"},
        advanced={"gid", "in_layout", "rasterized", "sketch_params", "snap", "url"},
        aliases={"colors", "edgecolor", "facecolor", "verts"},
        derived={"paths", "segments", "transform"},
        unsupported={"agg_filter", "animated", "antialiased", "array", "capstyle", "clim", "clip_box", "clip_path", "cmap", "figure", "gapcolor", "hatch", "joinstyle", "mouseover", "norm", "offset_transform", "offsets", "path_effects", "picker", "pickradius", "urls"},
        unsupported_reason="excluded from the fixed reflection-mark collection contract",
    ),
    "AxesImage": _contract(
        core={"alpha", "extent", "filternorm", "filterrad", "interpolation", "interpolation_stage", "resample", "visible", "zorder"},
        advanced={"clip_on", "gid", "in_layout", "label", "rasterized", "sketch_params", "snap", "url"},
        aliases={"array", "data"},
        derived={"clim", "cmap", "norm"},
        unsupported={"agg_filter", "animated", "clip_box", "clip_path", "figure", "mouseover", "path_effects", "picker", "transform"},
    ),
    "Rectangle": _contract(
        core={"alpha", "edgecolor", "facecolor", "fill", "hatch", "linestyle", "linewidth", "visible", "zorder"},
        aliases={"color"},
        derived={"bounds", "height", "width", "x", "xy", "y"},
        unsupported={"agg_filter", "angle", "animated", "antialiased", "capstyle", "clip_box", "clip_on", "clip_path", "figure", "gid", "in_layout", "joinstyle", "label", "mouseover", "path_effects", "picker", "rasterized", "sketch_params", "snap", "transform", "url"},
        unsupported_reason="excluded from the safe Zoom-region state contract",
    ),
    "ConnectionPatch": _contract(
        core={"alpha", "edgecolor", "linestyle", "linewidth", "visible", "zorder"},
        aliases={"color"},
        derived={"annotation_clip", "patchA", "patchB", "positions"},
        unsupported={"agg_filter", "animated", "antialiased", "arrowstyle", "capstyle", "clip_box", "clip_on", "clip_path", "connectionstyle", "facecolor", "figure", "fill", "gid", "hatch", "in_layout", "joinstyle", "label", "mouseover", "mutation_aspect", "mutation_scale", "path_effects", "picker", "rasterized", "sketch_params", "snap", "transform", "url"},
        unsupported_reason="excluded from the safe four-connector state contract",
    ),
}


def _representative_artists() -> dict[str, object]:
    figure = Figure()
    axes = figure.subplots()
    return {
        "Figure": figure,
        "Axes": axes,
        "XAxis": axes.xaxis,
        "YAxis": axes.yaxis,
        "Spine": axes.spines["left"],
        "Text": axes.text(0.5, 0.5, "contract"),
        "Legend": axes.legend([], []),
        "Line2D": axes.plot([], [])[0],
        "PathCollection": axes.scatter([], []),
        "LineCollection": LineCollection([]),
        "AxesImage": axes.imshow([[0.0]]),
        "Rectangle": axes.indicate_inset_zoom(figure.add_axes([0.1, 0.1, 0.2, 0.2]))[0],
        "ConnectionPatch": axes.indicate_inset_zoom(figure.axes[-1])[1][0],
    }


def validate_matplotlib_exposure_contracts() -> None:
    """Fail unless every Matplotlib 3.9 setter is explicitly classified."""

    version = tuple(int(part) for part in matplotlib.__version__.split(".")[:2])
    if version != (3, 9):
        raise ComponentValidationError(
            "The component exposure contract targets Matplotlib 3.9; "
            f"found {matplotlib.__version__}."
        )
    artists = _representative_artists()
    if set(artists) != set(MATPLOTLIB_39_EXPOSURE):
        raise ComponentValidationError("Matplotlib exposure targets are incomplete.")
    for name, artist in artists.items():
        actual = frozenset(ArtistInspector(artist).get_setters())
        declared = MATPLOTLIB_39_EXPOSURE[name].classified
        missing = sorted(actual - declared)
        stale = sorted(declared - actual)
        if missing or stale:
            details = []
            if missing:
                details.append(f"unclassified {missing!r}")
            if stale:
                details.append(f"not present {stale!r}")
            raise ComponentValidationError(
                f"Invalid Matplotlib exposure contract for {name}: "
                + ", ".join(details)
            )
