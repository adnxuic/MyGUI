"""Resolve serialized component states to live Matplotlib objects."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable
import weakref
from typing import Any

from matplotlib.axes import Axes
from matplotlib.axis import Axis
from matplotlib.figure import Figure

from .errors import ComponentNotFoundError
from .models import ComponentKind, ComponentRole, ComponentState


Resolver = Callable[[ComponentState, Any | None], Any | None]


class ComponentLocator:
    """Maps stable component IDs and semantic selectors to live targets.

    Stable artists (for example ``Line2D``) are normally weakly bound by ID.
    Dynamic elements (ticks, tick labels, grids and legends) are always
    resolved through their parent and selector so Matplotlib may recreate the
    underlying artists safely.
    """

    _DYNAMIC_KINDS = frozenset(
        {
            ComponentKind.TICK_GROUP,
            ComponentKind.TICK_LABEL_GROUP,
            ComponentKind.GRID,
            ComponentKind.LEGEND,
        }
    )

    def __init__(
        self,
        parent_resolver: Callable[[str], Any | None] | None = None,
    ) -> None:
        self._targets: weakref.WeakValueDictionary[str, Any] = (
            weakref.WeakValueDictionary()
        )
        self._strong_targets: dict[str, Any] = {}
        self._resolvers: dict[ComponentKind, list[Resolver]] = defaultdict(list)
        self._parent_resolver = parent_resolver

    def set_parent_resolver(
        self, resolver: Callable[[str], Any | None] | None
    ) -> None:
        """Set parent resolver."""

        self._parent_resolver = resolver

    def bind(self, component_id: str, target: Any) -> None:
        """Bind a component identifier to its live target."""

        self.unbind(component_id)
        try:
            self._targets[component_id] = target
        except TypeError:
            # A few extension objects do not expose weak-reference support.
            # Keeping these rare objects strongly is preferable to making the
            # locator unusable; unbind/registry deletion still releases them.
            self._strong_targets[component_id] = target

    def unbind(self, component_id: str) -> None:
        """Remove the live-target binding for a component."""

        self._targets.pop(component_id, None)
        self._strong_targets.pop(component_id, None)

    def bound_target(self, component_id: str) -> Any | None:
        """Return only an explicit ID binding, without semantic resolution."""

        return self._targets.get(
            component_id,
            self._strong_targets.get(component_id),
        )

    def register_resolver(
        self,
        kind: ComponentKind | str,
        resolver: Resolver,
        *,
        prepend: bool = False,
    ) -> None:
        """Register resolver."""

        kind = ComponentKind(kind)
        if prepend:
            self._resolvers[kind].insert(0, resolver)
        else:
            self._resolvers[kind].append(resolver)

    def resolve(self, state: ComponentState) -> Any | None:
        """Resolve the requested object, returning no value when it is unavailable."""

        direct = self._targets.get(state.id, self._strong_targets.get(state.id))
        parent = self._resolve_parent(state)

        if state.kind in self._DYNAMIC_KINDS:
            semantic = self._resolve_semantic(state, parent)
            if semantic is not None:
                return semantic

        if direct is not None:
            return direct

        for resolver in self._resolvers.get(state.kind, ()):
            target = resolver(state, parent)
            if target is not None:
                return target
        return self._resolve_semantic(state, parent)

    def require(self, state: ComponentState) -> Any:
        """Resolve the requested object or raise when it is unavailable."""

        target = self.resolve(state)
        if target is None:
            raise ComponentNotFoundError(
                f"Cannot resolve target for component {state.id!r} "
                f"({state.kind.value}/{state.role.value})."
            )
        return target

    def find_id(self, target: Any) -> str | None:
        """Return the component ID bound to a live Matplotlib target."""

        for component_id, candidate in self._targets.items():
            if candidate is target:
                return component_id
        for component_id, candidate in self._strong_targets.items():
            if candidate is target:
                return component_id
        return None

    def _resolve_parent(self, state: ComponentState) -> Any | None:
        if state.parent_id is None or self._parent_resolver is None:
            return None
        return self._parent_resolver(state.parent_id)

    @staticmethod
    def _axes_from_parent(parent: Any | None) -> Axes | None:
        if isinstance(parent, Axes):
            return parent
        if isinstance(parent, Axis):
            return parent.axes
        axes = getattr(parent, "axes", None)
        return axes if isinstance(axes, Axes) else None

    def _resolve_semantic(
        self, state: ComponentState, parent: Any | None
    ) -> Any | None:
        selector = state.selector
        if state.kind is ComponentKind.FIGURE:
            return parent if isinstance(parent, Figure) else None

        if state.kind is ComponentKind.AXES:
            if not isinstance(parent, Figure):
                return None
            index = selector.get("index")
            if isinstance(index, int) and 0 <= index < len(parent.axes):
                return parent.axes[index]
            return None

        axes = self._axes_from_parent(parent)
        if state.kind is ComponentKind.AXIS:
            if axes is None:
                return None
            axis_name = selector.get("axis")
            return axes.xaxis if axis_name == "x" else axes.yaxis if axis_name == "y" else None

        if state.kind is ComponentKind.SPINE:
            if axes is None:
                return None
            return axes.spines.get(selector.get("name"))

        if state.kind in {
            ComponentKind.TICK_GROUP,
            ComponentKind.TICK_LABEL_GROUP,
            ComponentKind.GRID,
        }:
            if isinstance(parent, Axis):
                return parent
            if axes is None:
                return None
            axis_name = selector.get("axis")
            return axes.xaxis if axis_name == "x" else axes.yaxis if axis_name == "y" else None

        if state.kind is ComponentKind.TEXT:
            if axes is not None:
                if state.role is ComponentRole.TITLE:
                    return axes.title
                if state.role is ComponentRole.X_LABEL:
                    return axes.xaxis.label
                if state.role is ComponentRole.Y_LABEL:
                    return axes.yaxis.label
            return None

        if state.kind is ComponentKind.LEGEND:
            return axes.get_legend() if axes is not None else None

        return None
