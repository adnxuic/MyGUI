"""Annotation creation, coordinate conversion, and render planning."""

from __future__ import annotations

import math
from typing import TYPE_CHECKING, Any

from mygui.figuremodify.components import (
    AnnotationController,
    ComponentChange,
    ComponentMutation,
    ComponentRegistry,
    ComponentState,
)
from mygui.figuremodify.components.controllers.annotation import (
    ANNOTATION_ARROW_STYLES,
    ANNOTATION_CONNECTION_STYLES,
    _MPL_COORDINATE_SYSTEMS,
)
from mygui.figuremodify.components.property_values import (
    annotation_box_kwargs,
)
from ._helpers import (
    _controller,
    _rejected,
)

if TYPE_CHECKING:
    from .text_render import TextRenderService


def arrowprops_for(properties: dict[str, Any]) -> dict[str, Any]:
    """Return Matplotlib arrowprops for one Annotation property mapping.

    The arrow patch is always created so ``arrow_enabled=False`` can hide it
    without losing the ability to re-enable it later.
    """

    props = {
        "arrowstyle": ANNOTATION_ARROW_STYLES[
            properties.get("arrow_style", "arrow")
        ],
        "connectionstyle": ANNOTATION_CONNECTION_STYLES[
            properties.get("connection_style", "straight")
        ],
        "color": properties.get("arrow_color", "#000000"),
        "linewidth": properties.get("arrow_linewidth", 1.5),
        "visible": bool(properties.get("arrow_enabled", True)),
        "clip_on": bool(properties.get("clip_on", True)),
    }
    if properties.get("alpha") is not None:
        props["alpha"] = properties["alpha"]
    return props


def annotation_artist_kwargs(
    properties: dict[str, Any],
) -> dict[str, Any]:
    """Return ``Axes.annotate`` kwargs for one Annotation property mapping."""

    kwargs: dict[str, Any] = {
        "xy": tuple(properties.get("xy", (0.0, 0.0))),
        "xycoords": _MPL_COORDINATE_SYSTEMS[
            properties.get("xycoords", "data")
        ],
        "xytext": tuple(properties.get("xytext", (20.0, 20.0))),
        "textcoords": _MPL_COORDINATE_SYSTEMS[
            properties.get("textcoords", "offset_points")
        ],
        "family": properties.get("fontfamily", "sans-serif"),
        "fontsize": properties.get("fontsize", 10.0),
        "fontweight": properties.get("fontweight", "normal"),
        "fontstyle": properties.get("fontstyle", "normal"),
        "color": properties.get("color", "#000000"),
        "rotation": properties.get("rotation", 0.0),
        "horizontalalignment": properties.get("horizontalalignment", "left"),
        "verticalalignment": properties.get("verticalalignment", "baseline"),
        "visible": bool(properties.get("visible", True)),
        "label": properties.get("label", ""),
        "usetex": False,
        "zorder": properties.get("zorder", 3.0),
        "clip_on": bool(properties.get("clip_on", True)),
        "arrowprops": arrowprops_for(properties),
    }
    alpha = properties.get("alpha")
    if alpha is not None:
        kwargs["alpha"] = alpha
    box = annotation_box_kwargs(properties.get("bbox", {"enabled": False}))
    if box is not None:
        kwargs["bbox"] = box
    return kwargs


class AnnotationService:
    """Plan Annotation creation, edits, and coordinate conversions."""

    def __init__(
        self,
        registry: ComponentRegistry,
        *,
        text_render_service: TextRenderService | None = None,
    ):
        self.registry = registry
        self.text_render_service = text_render_service

    def annotation_controller(self, value) -> AnnotationController:
        """Resolve one Annotation Controller from an id or instance."""

        return _controller(self.registry, value, AnnotationController)

    def apply_properties(
        self,
        component,
        properties: dict[str, Any],
    ) -> ComponentChange:
        """Apply Annotation property edits through TextRenderService or transaction."""

        controller = self.annotation_controller(component)
        if self.text_render_service is not None:
            return self.text_render_service.apply(controller, properties)
        batch = self.registry.apply_transaction(
            (
                ComponentMutation(
                    controller.component_id,
                    properties=dict(properties),
                ),
            ),
        )
        if not batch.committed or not batch.changes:
            return _rejected(
                controller,
                batch.message or "Annotation update failed.",
            )
        return batch.changes[0]

    def apply_state(
        self,
        component,
        state: ComponentState,
    ) -> ComponentChange:
        """Apply complete component state to one Annotation."""

        return self.apply_properties(component, state.properties)

    @staticmethod
    def center_data_coordinates(axes) -> tuple[float, float]:
        """Return the data coordinates of one Axes' visible display center.

        Uses only public transform inversion, so linear, logarithmic, and
        inverted axes are all handled.
        """

        width, height = axes.figure.canvas.get_width_height()
        center = axes.transAxes.transform((0.5, 0.5))
        del width, height
        x, y = axes.transData.inverted().transform(center)
        if not (math.isfinite(x) and math.isfinite(y)):
            raise ValueError("The Axes center has no finite data coordinates.")
        return float(x), float(y)
