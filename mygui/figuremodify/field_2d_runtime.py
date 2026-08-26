"""Runtime composite for Pseudocolor, Heatmap, and Contour artists."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
from matplotlib.axes import Axes
from matplotlib.cm import ScalarMappable
from matplotlib.collections import QuadMesh
from matplotlib.contour import QuadContourSet
from matplotlib.image import AxesImage
from matplotlib.text import Text

from mygui.figuremodify.components.models import ComponentRole
from mygui.figuremodify.components.property_values import (
    apply_color_map_spec,
    contour_label_fmt,
    contour_levels_value,
    grid_edge_value,
    normalize_color_map_spec,
    normalize_contour_label_spec,
    normalize_line_pattern,
)
from mygui.figuremodify.field_grid import (
    Field2DGrid,
    centers_to_edges,
    heatmap_extent,
)
from mygui.figuremodify.matplotlib_adapter import matplotlib_style_context


def _line_style(value: Any) -> Any:
    pattern = normalize_line_pattern(value)
    if pattern["kind"] == "preset":
        return pattern["value"]
    return (pattern["offset"], pattern["dashes"])


def _contour_artists(contour: Any) -> tuple[Any, ...]:
    """Return the QuadContourSet itself; do not use deprecated ``collections``."""

    return (contour,) if contour is not None else ()


@dataclass(slots=True)
class Field2DRuntime:
    """Locator target for one FIELD_2D component."""

    role: ComponentRole
    mappable: Any
    axes: Axes
    primary: Any = None
    filled: QuadContourSet | None = None
    lines: QuadContourSet | None = None
    labels: tuple[Text, ...] = ()
    empty: bool = False

    def iter_artists(self) -> tuple[Any, ...]:
        artists: list[Any] = []
        seen: set[int] = set()

        def add(item: Any) -> None:
            if item is None:
                return
            identity = id(item)
            if identity in seen:
                return
            seen.add(identity)
            artists.append(item)

        if isinstance(self.primary, QuadContourSet):
            for artist in _contour_artists(self.primary):
                add(artist)
        else:
            add(self.primary)
        if self.filled is not None and self.filled is not self.primary:
            for artist in _contour_artists(self.filled):
                add(artist)
        if self.lines is not None and self.lines is not self.primary:
            for artist in _contour_artists(self.lines):
                add(artist)
        for label in self.labels:
            add(label)
        return tuple(artists)

    @property
    def has_drawable(self) -> bool:
        if self.empty:
            return False
        array = getattr(self.mappable, "get_array", lambda: None)()
        if array is None:
            return False
        values = np.ma.asarray(array)
        if values.size == 0:
            return False
        return bool(np.ma.count(values))

    def set_gid(self, gid: str) -> None:
        for artist in self.iter_artists():
            setter = getattr(artist, "set_gid", None)
            if callable(setter):
                setter(gid)

    def set_alpha(self, value: float | None) -> None:
        for artist in self.iter_artists():
            setter = getattr(artist, "set_alpha", None)
            if callable(setter):
                setter(value)
        if not self.iter_artists():
            setter = getattr(self.mappable, "set_alpha", None)
            if callable(setter):
                setter(value)

    def set_visible(self, value: bool) -> None:
        for artist in self.iter_artists():
            setter = getattr(artist, "set_visible", None)
            if callable(setter):
                setter(value)

    def set_zorder(self, value: float) -> None:
        for artist in self.iter_artists():
            setter = getattr(artist, "set_zorder", None)
            if callable(setter):
                setter(value)

    def set_clip_on(self, value: bool) -> None:
        for artist in self.iter_artists():
            setter = getattr(artist, "set_clip_on", None)
            if callable(setter):
                setter(value)

    def set_rasterized(self, value: bool) -> None:
        for artist in self.iter_artists():
            setter = getattr(artist, "set_rasterized", None)
            if callable(setter):
                setter(value)

    def set_in_layout(self, value: bool) -> None:
        for artist in self.iter_artists():
            setter = getattr(artist, "set_in_layout", None)
            if callable(setter):
                setter(value)

    def set_snap(self, value: bool | None) -> None:
        for artist in self.iter_artists():
            setter = getattr(artist, "set_snap", None)
            if callable(setter):
                setter(value)

    def set_url(self, value: str | None) -> None:
        for artist in self.iter_artists():
            setter = getattr(artist, "set_url", None)
            if callable(setter):
                setter(value)

    def apply_colormap(self, value: Any) -> None:
        apply_color_map_spec(self.mappable, value)
        for item in (self.primary, self.filled, self.lines):
            if item is not None and item is not self.mappable:
                apply_color_map_spec(item, value)

    def remove(self) -> None:
        for artist in self.iter_artists():
            remover = getattr(artist, "remove", None)
            if callable(remover):
                try:
                    remover()
                except (NotImplementedError, RuntimeError, ValueError):
                    continue


def _placeholder_mappable(properties: dict[str, Any]) -> ScalarMappable:
    mappable = ScalarMappable()
    apply_color_map_spec(mappable, properties["colormap"])
    mappable.set_array(np.ma.masked_all((0, 0), dtype=float))
    return mappable


def _apply_common_artist(artist: Any, properties: dict[str, Any], gid: str | None) -> None:
    artist.set_alpha(properties["alpha"])
    artist.set_visible(properties["visible"])
    artist.set_zorder(properties["zorder"])
    artist.set_clip_on(properties["clip_on"])
    artist.set_rasterized(properties["rasterized"])
    artist.set_in_layout(properties["in_layout"])
    artist.set_snap(properties["snap"])
    artist.set_url(properties["url"])
    if gid:
        artist.set_gid(gid)
    if properties.get("gid"):
        artist.set_gid(properties["gid"])


def _label_contour(
    axes: Axes,
    contour: QuadContourSet,
    labels: dict[str, Any],
) -> tuple[Text, ...]:
    spec = normalize_contour_label_spec(labels)
    if not spec["enabled"] or contour is None:
        return ()
    kwargs: dict[str, Any] = {
        "fontsize": spec["fontsize"],
        "inline": spec["inline"],
        "inline_spacing": spec["inline_spacing"],
        "fmt": contour_label_fmt(spec),
    }
    if spec["color"] is not None:
        kwargs["colors"] = spec["color"]
    texts = axes.clabel(contour, **kwargs)
    return tuple(texts or ())


def create_field_2d_runtime(
    axes: Axes,
    role: ComponentRole,
    grid: Field2DGrid,
    properties: dict[str, Any],
    *,
    style: str | None = None,
    gid: str | None = None,
) -> Field2DRuntime:
    """Create one FIELD_2D runtime under the current Figure style context."""

    colormap = normalize_color_map_spec(properties["colormap"])
    if grid.empty:
        placeholder = _placeholder_mappable(properties)
        placeholder.axes = axes
        return Field2DRuntime(
            role=role,
            mappable=placeholder,
            axes=axes,
            empty=True,
        )

    with matplotlib_style_context(style):
        if role is ComponentRole.PSEUDOCOLOR:
            return _create_pseudocolor(axes, grid, properties, colormap, gid)
        if role is ComponentRole.HEATMAP:
            return _create_heatmap(axes, grid, properties, colormap, gid)
        if role is ComponentRole.CONTOUR:
            return _create_contour(axes, grid, properties, colormap, gid)
    raise ValueError(f"Unsupported FIELD_2D role {role!r}.")


def _create_pseudocolor(
    axes: Axes,
    grid: Field2DGrid,
    properties: dict[str, Any],
    colormap: dict[str, Any],
    gid: str | None,
) -> Field2DRuntime:
    shading = str(properties["shading"])
    if shading == "flat":
        x_edges = centers_to_edges(grid.x)
        y_edges = centers_to_edges(grid.y)
        x_mesh, y_mesh = np.meshgrid(x_edges, y_edges)
    else:
        x_mesh, y_mesh = np.meshgrid(grid.x, grid.y)
    mesh = axes.pcolormesh(
        x_mesh,
        y_mesh,
        grid.z,
        shading=shading,
        cmap=colormap["cmap"],
        norm=None,
        alpha=properties["alpha"],
        zorder=properties["zorder"],
        edgecolors=grid_edge_value(properties["edgecolor"]),
        linewidths=properties["linewidth"],
        antialiased=properties["antialiased"],
        rasterized=properties["rasterized"],
        snap=properties["snap"],
        clip_on=properties["clip_on"],
    )
    if not isinstance(mesh, QuadMesh):
        mesh.remove()
        raise RuntimeError("Matplotlib did not create a QuadMesh.")
    apply_color_map_spec(mesh, colormap)
    mesh.set_in_layout(properties["in_layout"])
    mesh.set_url(properties["url"])
    mesh.set_visible(properties["visible"])
    if gid:
        mesh.set_gid(gid)
    if properties.get("gid"):
        mesh.set_gid(properties["gid"])
    return Field2DRuntime(
        role=ComponentRole.PSEUDOCOLOR,
        mappable=mesh,
        axes=axes,
        primary=mesh,
        empty=False,
    )


def _create_heatmap(
    axes: Axes,
    grid: Field2DGrid,
    properties: dict[str, Any],
    colormap: dict[str, Any],
    gid: str | None,
) -> Field2DRuntime:
    image = axes.imshow(
        grid.z,
        origin="lower",
        extent=heatmap_extent(grid.x, grid.y),
        interpolation=properties["interpolation"],
        interpolation_stage=properties["interpolation_stage"],
        resample=properties["resample"],
        filternorm=properties["filternorm"],
        filterrad=properties["filterrad"],
        aspect="auto",
        cmap=colormap["cmap"],
        alpha=properties["alpha"],
        zorder=properties["zorder"],
        rasterized=properties["rasterized"],
        clip_on=properties["clip_on"],
        snap=properties["snap"],
        url=properties["url"] or "",
        visible=properties["visible"],
    )
    if not isinstance(image, AxesImage):
        image.remove()
        raise RuntimeError("Matplotlib did not create an AxesImage.")
    apply_color_map_spec(image, colormap)
    image.set_in_layout(properties["in_layout"])
    if gid:
        image.set_gid(gid)
    if properties.get("gid"):
        image.set_gid(properties["gid"])
    return Field2DRuntime(
        role=ComponentRole.HEATMAP,
        mappable=image,
        axes=axes,
        primary=image,
        empty=False,
    )


def _create_contour(
    axes: Axes,
    grid: Field2DGrid,
    properties: dict[str, Any],
    colormap: dict[str, Any],
    gid: str | None,
) -> Field2DRuntime:
    mode = str(properties["mode"])
    levels = contour_levels_value(properties["levels"])
    shared = {
        "levels": levels,
        "cmap": colormap["cmap"],
        "corner_mask": properties["corner_mask"],
        "extend": properties["extend"],
        "algorithm": properties["algorithm"],
        "nchunk": properties["nchunk"],
        "antialiased": properties["antialiased"],
        "zorder": properties["zorder"],
        "alpha": properties["alpha"],
    }
    filled = None
    lines = None
    if mode in {"filled", "overlay"}:
        filled = axes.contourf(
            grid.x,
            grid.y,
            grid.z,
            **shared,
        )
        apply_color_map_spec(filled, colormap)
    if mode in {"lines", "overlay"} or (
        mode == "filled" and properties["labels"]["enabled"]
    ):
        line_kwargs = dict(shared)
        line_kwargs.update(
            {
                "linewidths": properties["linewidth"],
                "linestyles": _line_style(properties["linestyle"]),
                "negative_linestyles": _line_style(
                    properties["negative_linestyle"]
                ),
            }
        )
        lines = axes.contour(
            grid.x,
            grid.y,
            grid.z,
            **line_kwargs,
        )
        apply_color_map_spec(lines, colormap)
        if mode == "filled":
            lines.set_visible(False)
    primary = filled if filled is not None else lines
    if primary is None:
        placeholder = _placeholder_mappable(properties)
        placeholder.axes = axes
        return Field2DRuntime(
            role=ComponentRole.CONTOUR,
            mappable=placeholder,
            axes=axes,
            empty=True,
        )
    apply_color_map_spec(primary, colormap)
    labels = _label_contour(
        axes,
        lines if lines is not None else filled,
        properties["labels"],
    )
    runtime = Field2DRuntime(
        role=ComponentRole.CONTOUR,
        mappable=primary,
        axes=axes,
        primary=primary,
        filled=filled,
        lines=lines,
        labels=labels,
        empty=False,
    )
    for artist in runtime.iter_artists():
        _apply_common_artist(artist, properties, gid)
        if isinstance(artist, Text):
            artist.set_visible(properties["visible"] and properties["labels"]["enabled"])
    if mode == "filled" and lines is not None:
        lines.set_visible(False)
    if gid:
        runtime.set_gid(gid)
    if properties.get("gid"):
        runtime.set_gid(properties["gid"])
    return runtime
