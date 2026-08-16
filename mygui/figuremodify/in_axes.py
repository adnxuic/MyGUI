"""Create and refresh zoom/image child-Axes Elements."""

from __future__ import annotations

import base64
from contextlib import contextmanager
from copy import deepcopy
from dataclasses import dataclass, field
from io import BytesIO
from pathlib import Path
from typing import Any
import warnings

import numpy as np
from matplotlib.axes import Axes
from matplotlib.transforms import Bbox, TransformedBbox
from PIL import Image, UnidentifiedImageError

from mygui.figuremodify.components import (
    ComponentEvent,
    ComponentKind,
    ComponentMutation,
    ComponentRegistry,
    ComponentRole,
    ImageInAxesController,
    LineController,
    ScatterController,
    UpdateImpact,
    ZoomInAxesController,
    decode_in_axes_image,
)
from mygui.figuremodify.components.controllers import IN_AXES_IMAGE_MIMES
from mygui.figuremodify.components.property_values import (
    apply_line_pattern,
    marker_value,
    markevery_value,
    normalize_line_pattern,
)
from mygui.resource_limits import load_resource_limits


@dataclass(frozen=True, slots=True)
class ZoomInAxesCreateSpec:
    """Controller-free values collected for a zoom inset creation."""

    bounds: tuple[float, float, float, float]
    xlim: tuple[float, float]
    ylim: tuple[float, float]
    facecolor: str
    edgecolor: str
    linewidth: float
    indicator_color: str
    indicator_linestyle: str = "-"
    indicator_linewidth: float = 1.0
    indicator_alpha: float = 0.5
    visible: bool = True
    zorder: float = 5.0
    frameon: bool = True
    ticks_visible: bool = True
    region_visible: bool = True
    connectors_visible: bool = True

    def properties(self) -> dict[str, Any]:
        """Return the complete persistent Controller property mapping."""

        return {
            "bounds": self.bounds,
            "visible": self.visible,
            "zorder": self.zorder,
            "facecolor": self.facecolor,
            "frameon": self.frameon,
            "edgecolor": self.edgecolor,
            "linewidth": self.linewidth,
            "xlim": self.xlim,
            "ylim": self.ylim,
            "ticks_visible": self.ticks_visible,
            "region_visible": self.region_visible,
            "region_color": self.indicator_color,
            "region_linestyle": self.indicator_linestyle,
            "region_linewidth": self.indicator_linewidth,
            "region_alpha": self.indicator_alpha,
            "region_facecolor": "#00000000",
            "region_fill": False,
            "region_hatch": None,
            "region_zorder": self.zorder - 0.01,
            "connectors": tuple(
                {
                    "visible": self.connectors_visible,
                    "color": self.indicator_color,
                    "line_pattern": {"kind": "preset", "value": self.indicator_linestyle},
                    "linewidth": self.indicator_linewidth,
                    "alpha": self.indicator_alpha,
                    "zorder": self.zorder - 0.01,
                }
                for _index in range(4)
            ),
        }


@dataclass(frozen=True, slots=True)
class ImageInAxesCreateSpec:
    """Controller-free values collected for an embedded image inset."""

    bounds: tuple[float, float, float, float]
    filename: str
    mime_type: str
    payload_base64: str
    facecolor: str
    edgecolor: str
    linewidth: float
    opacity: float = 1.0
    fit_mode: str = "contain"
    interpolation: str = "antialiased"
    origin: str = "upper"
    extent: tuple[float, float, float, float] | None = None
    resample: bool = True
    filternorm: bool = True
    filterrad: float = 4.0
    interpolation_stage: str = "data"
    image_visible: bool = True
    image_zorder: float = 0.0
    image_clip_on: bool = True
    image_rasterized: bool = False
    image_in_layout: bool = True
    image_snap: bool | None = None
    image_gid: str | None = None
    image_url: str | None = None
    visible: bool = True
    zorder: float = 5.0
    frameon: bool = False

    def properties(self) -> dict[str, Any]:
        """Return the complete persistent Controller property mapping."""

        return {
            "bounds": self.bounds,
            "visible": self.visible,
            "zorder": self.zorder,
            "facecolor": self.facecolor,
            "frameon": self.frameon,
            "edgecolor": self.edgecolor,
            "linewidth": self.linewidth,
            "opacity": self.opacity,
            "fit_mode": self.fit_mode,
            "interpolation": self.interpolation,
            "origin": self.origin,
            "extent": self.extent,
            "resample": self.resample,
            "filternorm": self.filternorm,
            "filterrad": self.filterrad,
            "interpolation_stage": self.interpolation_stage,
            "image_visible": self.image_visible,
            "image_zorder": self.image_zorder,
            "image_clip_on": self.image_clip_on,
            "image_rasterized": self.image_rasterized,
            "image_in_layout": self.image_in_layout,
            "image_snap": self.image_snap,
            "image_gid": self.image_gid,
            "image_url": self.image_url,
        }

    def data(self) -> dict[str, str]:
        """Return the exact embedded image payload mapping."""

        return {
            "filename": self.filename,
            "mime_type": self.mime_type,
            "payload_base64": self.payload_base64,
        }


InAxesCreateSpec = ZoomInAxesCreateSpec | ImageInAxesCreateSpec


class InAxesBoundsLocator:
    """Keep inset bounds relative to its parent Axes across layout changes."""

    def __init__(self, bounds, transform) -> None:
        self.bounds = tuple(float(value) for value in bounds)
        self.transform = transform

    def __call__(self, axes: Axes, renderer):
        del renderer
        return TransformedBbox(
            Bbox.from_bounds(*self.bounds),
            self.transform - axes.figure.transSubfigure,
        )


@dataclass
class InAxesRuntime:
    """Live Matplotlib objects owned by one in_axes Component."""

    parent_axes: Axes
    axes: Axes
    bounds_locator: InAxesBoundsLocator
    content_artists: list[Any] = field(default_factory=list)
    image_artist: Any | None = None
    indicator_rectangle: Any | None = None
    connectors: tuple[Any, ...] = ()
    connector_defaults: tuple[bool, ...] = ()
    region_visible: bool = True
    connectors_visible: bool = True
    connector_specs: tuple[dict[str, Any], ...] = ()
    region_line_pattern: dict[str, Any] = field(
        default_factory=lambda: {"kind": "preset", "value": "-"}
    )
    fit_mode: str = "contain"


def embedded_image_data(path: str | Path) -> dict[str, str]:
    """Read, identify, and validate one raster image for project embedding."""

    image_path = Path(path)
    limits = load_resource_limits()
    if not image_path.is_file():
        raise ValueError(f"Image file does not exist: {image_path}")
    if image_path.stat().st_size > limits.max_image_bytes:
        raise ValueError("The selected image exceeds the configured byte budget.")
    payload = image_path.read_bytes()
    if len(payload) > limits.max_image_bytes:
        raise ValueError("The selected image exceeds the configured byte budget.")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(payload)) as image:
                detected_format = str(image.format or "").upper()
    except (
        Image.DecompressionBombError,
        Image.DecompressionBombWarning,
        UnidentifiedImageError,
        OSError,
    ) as exc:
        raise ValueError("The selected image could not be decoded safely.") from exc
    mime_type = IN_AXES_IMAGE_MIMES.get(detected_format)
    if mime_type is None:
        raise ValueError("Images must be PNG, JPEG, BMP, or TIFF.")
    data = {
        "filename": image_path.name,
        "mime_type": mime_type,
        "payload_base64": base64.b64encode(payload).decode("ascii"),
    }
    decode_in_axes_image(data)
    return data


class InAxesService:
    """Own runtime insets and refresh live Zoom mirrors after Registry commits."""

    def __init__(
        self,
        registry: ComponentRegistry,
        *,
        warning_callback=None,
    ) -> None:
        self.registry = registry
        self.warning_callback = warning_callback
        self._runtimes: dict[str, InAxesRuntime] = {}
        self._cleanup_unsubscribes: dict[str, Any] = {}
        self._unsubscribe = registry.subscribe_batches(self._component_events)
        self._disposed = False
        self._refresh_suspensions = 0

    @contextmanager
    def suspend_refresh(self):
        """Temporarily suppress Registry-driven refresh during staged restore."""

        self._refresh_suspensions += 1
        try:
            yield
        finally:
            self._refresh_suspensions -= 1

    def create_runtime(
        self,
        parent_axes: Axes,
        bounds: tuple[float, float, float, float],
        *,
        zorder: float,
    ) -> InAxesRuntime:
        """Create an unregistered child Axes and its project-owned locator."""

        child = parent_axes.inset_axes(
            bounds,
            transform=parent_axes.transAxes,
            zorder=zorder,
        )
        locator = InAxesBoundsLocator(bounds, parent_axes.transAxes)
        child.set_axes_locator(locator)
        child.set_navigate(False)
        child.set_in_layout(False)
        return InAxesRuntime(parent_axes, child, locator)

    @staticmethod
    def add_zoom_indicator(
        runtime: InAxesRuntime,
        properties: dict[str, Any],
    ) -> None:
        """Attach the standard region rectangle and connectors to the parent."""

        raw_region_pattern = properties["region_linestyle"]
        if isinstance(raw_region_pattern, str):
            raw_region_pattern = {
                "kind": "preset",
                "value": raw_region_pattern,
            }
        region_pattern = normalize_line_pattern(raw_region_pattern)
        region_linestyle = (
            region_pattern["value"]
            if region_pattern["kind"] == "preset"
            else (region_pattern["offset"], region_pattern["dashes"])
        )
        rectangle, connectors = runtime.parent_axes.indicate_inset_zoom(
            runtime.axes,
            edgecolor=properties["region_color"],
            linestyle=region_linestyle,
            linewidth=properties["region_linewidth"],
            alpha=properties["region_alpha"],
        )
        runtime.indicator_rectangle = rectangle
        runtime.connectors = tuple(connectors)
        runtime.connector_defaults = tuple(
            bool(connector.get_visible()) for connector in connectors
        )
        runtime.region_visible = bool(properties["region_visible"])
        runtime.region_line_pattern = deepcopy(region_pattern)
        runtime.connector_specs = tuple(deepcopy(properties["connectors"]))
        rectangle.set_facecolor(properties["region_facecolor"])
        rectangle.set_fill(properties["region_fill"])
        rectangle.set_hatch(properties["region_hatch"])
        rectangle.set_zorder(properties["region_zorder"])
        for connector, spec in zip(connectors, runtime.connector_specs):
            connector.set_edgecolor(spec["color"])
            apply_line_pattern(connector, spec["line_pattern"])
            connector.set_linewidth(spec["linewidth"])
            connector.set_alpha(spec["alpha"])
            connector.set_zorder(spec["zorder"])
        ZoomInAxesController._sync_indicator_positions(runtime)
        ZoomInAxesController._sync_indicator_visibility(runtime)

    def register_runtime(
        self,
        component_id: str,
        runtime: InAxesRuntime,
    ) -> None:
        """Publish one live runtime after its Controller has been registered."""

        if component_id in self._runtimes:
            raise ValueError(f"Inset runtime already exists: {component_id}")
        self._runtimes[component_id] = runtime
        self._cleanup_unsubscribes[component_id] = (
            self.registry.add_cleanup_callback(
                component_id,
                lambda _state, target=component_id: self.unregister_runtime(target),
            )
        )

    @staticmethod
    def destroy_runtime(runtime: InAxesRuntime) -> None:
        """Remove every Matplotlib object owned by an uncommitted runtime."""

        for artist in (
            runtime.indicator_rectangle,
            *runtime.connectors,
        ):
            if artist is None:
                continue
            try:
                artist.remove()
            except (RuntimeError, ValueError):
                pass
        try:
            runtime.axes.remove()
        except (RuntimeError, ValueError):
            pass

    def unregister_runtime(self, component_id: str) -> None:
        """Forget one runtime and detach its Registry cleanup callback."""

        self._runtimes.pop(component_id, None)
        unsubscribe = self._cleanup_unsubscribes.pop(component_id, None)
        if unsubscribe is not None:
            unsubscribe()

    def runtime(self, component_id: str) -> InAxesRuntime:
        """Return the live runtime for one registered inset."""

        try:
            return self._runtimes[component_id]
        except KeyError as exc:
            raise ValueError(f"Inset runtime is unavailable: {component_id}") from exc

    @staticmethod
    def _line_candidate(axes: Axes, controller: LineController):
        source = controller.resolve_target()
        properties = controller.read_state().properties
        pattern = properties["linestyle"]
        linestyle = pattern["value"] if pattern["kind"] == "preset" else (pattern["offset"], pattern["dashes"])
        line, = axes.plot(
            np.asarray(source.get_xdata(orig=False)),
            np.asarray(source.get_ydata(orig=False)),
            label="_nolegend_",
            color=properties["color"],
            linestyle=linestyle,
            linewidth=properties["linewidth"],
            marker=marker_value(properties["marker"]),
            markersize=properties["markersize"],
            markerfacecolor=properties["markerfacecolor"],
            markeredgecolor=properties["markeredgecolor"],
            markeredgewidth=properties["markeredgewidth"],
            alpha=properties["alpha"],
            visible=True,
            zorder=properties["zorder"],
            drawstyle=properties["drawstyle"],
            fillstyle=properties["fillstyle"],
            markerfacecoloralt=properties["markerfacecoloralt"],
            gapcolor=properties["gapcolor"],
            dash_capstyle=properties["dash_capstyle"],
            dash_joinstyle=properties["dash_joinstyle"],
            solid_capstyle=properties["solid_capstyle"],
            solid_joinstyle=properties["solid_joinstyle"],
            antialiased=properties["antialiased"],
            markevery=markevery_value(properties["markevery"]),
            rasterized=properties["rasterized"],
            clip_on=properties["clip_on"],
        )
        return line

    @staticmethod
    def _scatter_candidate(axes: Axes, controller: ScatterController):
        source = controller.resolve_target()
        state = controller.read_state()
        offsets = np.asarray(source.get_offsets())
        x = offsets[:, 0] if offsets.size else np.asarray([])
        y = offsets[:, 1] if offsets.size else np.asarray([])
        properties = state.properties
        pattern = properties["linestyle"]
        linestyle = pattern["value"] if pattern["kind"] == "preset" else (pattern["offset"], pattern["dashes"])
        collection = axes.scatter(
            x,
            y,
            s=properties["size"],
            c=properties["color"],
            edgecolors=properties["edgecolor"],
            marker=marker_value(properties["marker"]),
            linewidths=properties["linewidth"],
            alpha=properties["alpha"],
            visible=True,
            zorder=properties["zorder"],
            label="_nolegend_",
            linestyle=linestyle,
            hatch=properties["hatch"],
            antialiased=properties["antialiased"],
            rasterized=properties["rasterized"],
        )
        if properties["capstyle"] is not None:
            collection.set_capstyle(properties["capstyle"])
        if properties["joinstyle"] is not None:
            collection.set_joinstyle(properties["joinstyle"])
        if properties["color_mapping"]["enabled"] and source.get_array() is not None:
            collection.set_array(np.asarray(source.get_array()).copy())
            collection.set_cmap(source.get_cmap())
            collection.set_norm(source.norm)
        if properties["size_mapping"]["enabled"]:
            collection.set_sizes(np.asarray(source.get_sizes()).copy())
        return collection

    def refresh_zoom(self, component_or_id) -> int:
        """Atomically rebuild one zoom mirror from its parent chart Components."""

        controller = (
            self.registry.get(component_or_id)
            if isinstance(component_or_id, str)
            else component_or_id
        )
        if controller.state.role is not ComponentRole.IN_AXES_ZOOM:
            raise ValueError("Zoom refresh requires an in_axes_zoom component.")
        runtime = self.runtime(controller.component_id)
        child = runtime.axes
        parent = runtime.parent_axes
        old_artists = list(runtime.content_artists)
        candidates: list[Any] = []
        old_xscale = child.get_xscale()
        old_yscale = child.get_yscale()
        old_xlim = child.get_xlim()
        old_ylim = child.get_ylim()
        try:
            child.set_xscale(parent.get_xscale())
            child.set_yscale(parent.get_yscale())
            sources = sorted(
                (
                    item
                    for item in self.registry.children(controller.state.parent_id)
                    if item.state.kind in {
                        ComponentKind.LINE,
                        ComponentKind.SCATTER,
                    }
                    and bool(item.state.properties.get("visible", True))
                ),
                key=lambda item: (item.state.order, item.component_id),
            )
            for source in sources:
                if isinstance(source, LineController):
                    candidates.append(self._line_candidate(child, source))
                elif isinstance(source, ScatterController):
                    candidates.append(self._scatter_candidate(child, source))
            state = controller.state
            xlim = tuple(state.properties["xlim"])
            ylim = tuple(state.properties["ylim"])
            if parent.xaxis_inverted() != (xlim[0] > xlim[1]):
                xlim = tuple(reversed(xlim))
            if parent.yaxis_inverted() != (ylim[0] > ylim[1]):
                ylim = tuple(reversed(ylim))
            child.set_xlim(*xlim)
            child.set_ylim(*ylim)
            for artist in old_artists:
                artist.remove()
            runtime.content_artists = candidates
            ZoomInAxesController._sync_indicator_positions(runtime)
        except Exception:
            for artist in candidates:
                try:
                    artist.remove()
                except Exception:
                    pass
            child.set_xscale(old_xscale)
            child.set_yscale(old_yscale)
            child.set_xlim(*old_xlim)
            child.set_ylim(*old_ylim)
            runtime.content_artists = old_artists
            raise
        self.registry.request_update(parent, UpdateImpact.REDRAW)
        return len(candidates)

    def refresh_all_zoom(self) -> None:
        """Refresh every registered Zoom inset once."""

        for controller in self.registry.query(
            kind=ComponentKind.IN_AXES,
            role=ComponentRole.IN_AXES_ZOOM,
        ):
            self.refresh_zoom(controller)

    def replace_image(self, component_or_id, data: dict[str, str]):
        """Validate and atomically replace an embedded image payload."""

        controller = (
            self.registry.get(component_or_id)
            if isinstance(component_or_id, str)
            else component_or_id
        )
        if not isinstance(controller, ImageInAxesController):
            raise ValueError("Image replacement requires an image inset.")
        decode_in_axes_image(data)
        return controller.apply_mutation(
            ComponentMutation(controller.component_id, data=data)
        )

    def _component_events(
        self,
        events: tuple[ComponentEvent, ...],
    ) -> None:
        if self._disposed or self._refresh_suspensions or not events:
            return
        parent_ids: set[str] = set()
        for event in events:
            state = event.after or event.before
            if state is None or state.kind not in {
                ComponentKind.LINE,
                ComponentKind.SCATTER,
                ComponentKind.AXES,
                ComponentKind.AXIS,
            }:
                continue
            if state.kind in {ComponentKind.LINE, ComponentKind.SCATTER}:
                if state.parent_id is not None:
                    parent_ids.add(state.parent_id)
                continue
            if state.kind is ComponentKind.AXES:
                parent_ids.add(state.id)
                continue
            controller = self.registry.ancestor(
                state.id,
                kind=ComponentKind.AXES,
            ) if state.id in self.registry else None
            if controller is not None:
                parent_ids.add(controller.component_id)

        failure = None
        for parent_id in parent_ids:
            if parent_id not in self.registry:
                continue
            for controller in self.registry.query(
                kind=ComponentKind.IN_AXES,
                role=ComponentRole.IN_AXES_ZOOM,
                parent_id=parent_id,
            ):
                try:
                    self.refresh_zoom(controller)
                except Exception as exc:
                    failure = failure or exc
        if failure is not None and callable(self.warning_callback):
            self.warning_callback(
                "A zoom inset could not be refreshed; its last valid "
                f"render was kept. {failure}"
            )

    def dispose(self) -> None:
        """Idempotently detach Registry listeners and runtime references."""

        if self._disposed:
            return
        self._disposed = True
        if self._unsubscribe is not None:
            self._unsubscribe()
            self._unsubscribe = None
        for component_id in tuple(self._runtimes):
            self.unregister_runtime(component_id)


__all__ = [
    "ImageInAxesCreateSpec",
    "InAxesBoundsLocator",
    "InAxesCreateSpec",
    "InAxesRuntime",
    "InAxesService",
    "ZoomInAxesCreateSpec",
    "embedded_image_data",
]
