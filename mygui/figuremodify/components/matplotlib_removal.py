"""Isolate reversible Matplotlib artist and Axes removal internals."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from matplotlib.axes import Axes
from matplotlib.figure import Figure

from .errors import ComponentValidationError


@dataclass(slots=True)
class RemovalHandle:
    """Pinned state for one ordinary Matplotlib artist."""

    target: Any
    owner: list[Any]
    index: int
    subject: Axes | Figure | None
    stale_callback: Any
    axes: Axes | None
    figure: Figure | None
    axes_stale: bool | None
    figure_stale: bool | None
    mouseover: bool
    detached: bool = False


@dataclass(slots=True)
class AxesRemovalHandle:
    """Pinned Matplotlib Axes structures required for exact rollback."""

    target: Axes
    figure: Figure
    subject: Figure
    child_axes: tuple[Axes, ...]
    localaxes: tuple[Axes, ...]
    stack_axes: dict[Axes, int]
    stale: bool
    target_stale: bool
    stale_callback: Any
    mouse_grabber: Any
    detached: bool


@dataclass(slots=True)
class AuxiliaryRemovalState:
    """Pinned location for one inset indicator artist."""

    target: Any
    owner: list[Any]
    index: int
    stale_callback: Any
    axes: Axes | None
    figure: Figure | None


@dataclass(slots=True)
class InAxesRemovalHandle:
    """Pinned child-Axes and indicator state for atomic inset deletion."""

    target: Axes
    owner: list[Any]
    index: int
    subject: Axes
    stale_callback: Any
    axes: Axes
    figure: Figure
    axes_stale: bool | None
    figure_stale: bool | None
    mouseover: bool
    target_stale: bool
    runtime: Any
    auxiliary_handles: tuple[AuxiliaryRemovalState, ...]
    detached: bool = False


class MatplotlibRemovalAdapter:
    """Single version-sensitive boundary for reversible removals."""

    @staticmethod
    def prepare_artist(
        target: Any,
        *,
        subject: Axes | Figure | None,
    ) -> RemovalHandle:
        remove_method = getattr(target, "_remove_method", None)
        owner = getattr(remove_method, "__self__", None)
        if not isinstance(owner, list) or target not in owner:
            raise ComponentValidationError(
                f"{type(target).__name__} has no reversible list container."
            )
        axes = getattr(target, "axes", None)
        if not isinstance(axes, Axes):
            axes = None
        figure = getattr(target, "figure", None)
        if not isinstance(figure, Figure):
            figure = axes.figure if axes is not None else None
        return RemovalHandle(
            target=target,
            owner=owner,
            index=owner.index(target),
            subject=subject,
            stale_callback=getattr(target, "stale_callback", None),
            axes=axes,
            figure=figure,
            axes_stale=getattr(axes, "stale", None),
            figure_stale=getattr(figure, "stale", None),
            mouseover=bool(getattr(target, "mouseover", False)),
        )

    @staticmethod
    def prepare_axes(target: Axes) -> AxesRemovalHandle:
        figure = target.figure
        localaxes = getattr(figure, "_localaxes", None)
        stack = getattr(figure, "_axstack", None)
        stack_axes = getattr(stack, "_axes", None)
        if (
            not isinstance(figure, Figure)
            or not isinstance(localaxes, list)
            or target not in localaxes
        ):
            raise ComponentValidationError(
                "Axes is not attached to its registered Figure."
            )
        if not isinstance(stack_axes, dict) or target not in stack_axes:
            raise ComponentValidationError(
                "Axes is missing from the Figure Axes stack."
            )
        if not callable(getattr(figure, "_remove_axes", None)):
            raise ComponentValidationError(
                "The installed Matplotlib Axes removal contract is unsupported."
            )
        canvas = figure.canvas
        return AxesRemovalHandle(
            target=target,
            figure=figure,
            subject=figure,
            child_axes=tuple(target.child_axes),
            localaxes=tuple(localaxes),
            stack_axes=dict(stack_axes),
            stale=figure.stale,
            target_stale=target.stale,
            stale_callback=target.stale_callback,
            mouse_grabber=getattr(canvas, "mouse_grabber", None),
            detached=False,
        )

    @staticmethod
    def prepare_in_axes(runtime: Any) -> InAxesRemovalHandle:
        child = getattr(runtime, "axes", None)
        parent = getattr(runtime, "parent_axes", None)
        if not isinstance(child, Axes) or not isinstance(parent, Axes):
            raise ComponentValidationError(
                "Inset runtime does not contain registered parent/child Axes."
            )
        owner = parent.child_axes
        if child not in owner:
            raise ComponentValidationError(
                "Inset Axes is not attached to its registered parent Axes."
            )
        artist_owner = getattr(parent, "_children", None)
        if not isinstance(artist_owner, list):
            raise ComponentValidationError(
                "The installed Matplotlib child-artist contract is unsupported."
            )
        auxiliary = []
        for artist in (
            getattr(runtime, "indicator_rectangle", None),
            *tuple(getattr(runtime, "connectors", ())),
        ):
            if artist is None:
                continue
            if artist not in artist_owner:
                raise ComponentValidationError(
                    "Inset indicator is detached from its parent Axes."
                )
            auxiliary.append(
                AuxiliaryRemovalState(
                    artist,
                    artist_owner,
                    artist_owner.index(artist),
                    getattr(artist, "stale_callback", None),
                    getattr(artist, "axes", None),
                    getattr(artist, "figure", None),
                )
            )
        figure = child.figure
        if not isinstance(figure, Figure):
            raise ComponentValidationError("Inset Axes has no Figure.")
        return InAxesRemovalHandle(
            target=child,
            owner=owner,
            index=owner.index(child),
            subject=parent,
            stale_callback=child.stale_callback,
            axes=parent,
            figure=figure,
            axes_stale=parent.stale,
            figure_stale=figure.stale,
            mouseover=False,
            target_stale=child.stale,
            runtime=runtime,
            auxiliary_handles=tuple(auxiliary),
        )

    def commit(self, handle) -> None:
        if handle.detached:
            return
        handle.detached = True
        try:
            if isinstance(handle, AxesRemovalHandle):
                handle.figure._localaxes.remove(handle.target)
                handle.figure._axstack.remove(handle.target)
            elif isinstance(handle, InAxesRemovalHandle):
                for auxiliary in handle.auxiliary_handles:
                    auxiliary.owner.remove(auxiliary.target)
                handle.owner.remove(handle.target)
            else:
                handle.owner.remove(handle.target)
        except (KeyError, ValueError) as exc:
            self.force_restore(handle)
            raise ComponentValidationError(
                "Prepared Matplotlib component changed before deletion."
            ) from exc

    def rollback(self, handle) -> None:
        if not handle.detached:
            return
        self.force_restore(handle)

    @staticmethod
    def force_restore(handle) -> None:
        if isinstance(handle, AxesRemovalHandle):
            figure = handle.figure
            target = handle.target
            figure._localaxes[:] = handle.localaxes
            figure._axstack._axes = dict(handle.stack_axes)
            figure.stale = handle.stale
            target.stale = handle.target_stale
            target.stale_callback = handle.stale_callback
            target.figure = figure
            target.axes = target
            canvas = figure.canvas
            if canvas is not None and hasattr(canvas, "mouse_grabber"):
                canvas.mouse_grabber = handle.mouse_grabber
            handle.detached = False
            return
        if handle.target not in handle.owner:
            handle.owner.insert(min(handle.index, len(handle.owner)), handle.target)
        handle.target.stale_callback = handle.stale_callback
        if handle.axes is not None:
            handle.target.axes = handle.axes
            if handle.axes_stale is not None:
                handle.axes.stale = handle.axes_stale
        if handle.figure is not None:
            handle.target.figure = handle.figure
            if handle.figure_stale is not None:
                handle.figure.stale = handle.figure_stale
        for auxiliary in sorted(
            getattr(handle, "auxiliary_handles", ()),
            key=lambda item: item.index,
        ):
            if auxiliary.target not in auxiliary.owner:
                auxiliary.owner.insert(
                    min(auxiliary.index, len(auxiliary.owner)),
                    auxiliary.target,
                )
            auxiliary.target.stale_callback = auxiliary.stale_callback
            auxiliary.target.axes = auxiliary.axes
            auxiliary.target.figure = auxiliary.figure
        handle.detached = False

    @staticmethod
    def finalize(handle) -> None:
        if isinstance(handle, AxesRemovalHandle):
            figure = handle.figure
            target = handle.target
            figure._remove_axes(target, owners=())
            for child_axes in handle.child_axes:
                try:
                    child_axes.remove()
                except (RuntimeError, ValueError):
                    pass
            target.stale_callback = None
            target.axes = None
            target.figure = None
            return
        if isinstance(handle, InAxesRemovalHandle):
            for auxiliary in sorted(
                handle.auxiliary_handles,
                key=lambda item: item.index,
            ):
                if auxiliary.target not in auxiliary.owner:
                    auxiliary.owner.insert(
                        min(auxiliary.index, len(auxiliary.owner)),
                        auxiliary.target,
                    )
                auxiliary.target.remove()
            if handle.target not in handle.owner:
                handle.owner.insert(
                    min(handle.index, len(handle.owner)),
                    handle.target,
                )
            handle.target.remove()
            return
        target = handle.target
        if handle.axes is not None:
            mouseover_set = getattr(handle.axes, "_mouseover_set", None)
            if mouseover_set is not None:
                mouseover_set.discard(target)
            handle.axes.stale = True
            target.axes = None
        if handle.figure is not None:
            handle.figure.stale = True
            target.figure = None
        target.stale_callback = None


MATPLOTLIB_REMOVAL = MatplotlibRemovalAdapter()
