"""Render-sensitive Text verification service."""

from __future__ import annotations

from dataclasses import replace
import warnings
from collections.abc import Callable, Iterable
from typing import Any


from mygui import tex_config
from mygui.font_diagnostics import (
    capture_font_diagnostics,
    normalize_font_diagnostic,
)
from mygui.figuremodify.components import (
    ComponentBatchChange,
    ComponentChange,
    ComponentMutation,
    ComponentRegistry,
    TextController,
)
from ._helpers import (
    _controller,
    _notices,
    _rejected,
)

class TextRenderService:
    """Verify render-sensitive Text changes before publishing them."""

    def __init__(
        self,
        registry: ComponentRegistry,
        *,
        tex_enabled: Callable[[], bool] = tex_config.is_tex_enabled,
    ):
        self.registry = registry
        self.tex_enabled = tex_enabled
        self._tex_effective_overrides: set[str] = set()
        self._last_tex_availability: bool | None = None

    def effective_usetex(self, component_id: str) -> bool:
        """Return runtime TeX use without changing the persisted request."""

        controller = _controller(
            self.registry,
            component_id,
            TextController,
        )
        requested = bool(controller.state.properties.get("usetex"))
        return requested and component_id not in self._tex_effective_overrides

    def apply_tex_availability(
        self,
        enabled: bool,
        *,
        force: bool = False,
    ) -> ComponentBatchChange:
        """Apply a runtime-only effective TeX override to requested Text."""

        enabled = bool(enabled)
        if not force and self._last_tex_availability is enabled:
            return ComponentBatchChange((), True)
        self._last_tex_availability = enabled
        requested = [
            controller
            for controller in self.registry.query()
            if isinstance(controller, TextController)
            and bool(controller.state.properties.get("usetex"))
        ]
        if not requested:
            self._tex_effective_overrides.clear()
            return ComponentBatchChange((), True)
        targets = [controller.resolve_target() for controller in requested]
        figures = []
        seen: set[int] = set()
        for target in targets:
            figure = target.figure
            if id(figure) not in seen:
                seen.add(id(figure))
                figures.append(figure)
        try:
            for target in targets:
                target.set_usetex(enabled)
            if enabled:
                for figure in figures:
                    figure.canvas.draw()
            else:
                for figure in figures:
                    figure.canvas.draw_idle()
        except Exception as exc:
            # Enabling TeX failed its render probe. Keep every requested Text
            # on the known-safe Matplotlib renderer while preserving state.
            # A failed availability transition must still leave requested
            # Text on the known-safe non-TeX renderer.  Restoring ``True``
            # after a failed disable would contradict the global capability.
            safe_values = [False] * len(targets)
            for target, safe_value in zip(targets, safe_values):
                try:
                    target.set_usetex(safe_value)
                except Exception:
                    pass
            for figure in figures:
                try:
                    figure.canvas.draw_idle()
                except Exception:
                    pass
            self._tex_effective_overrides.update(
                controller.component_id for controller in requested
            )
            return ComponentBatchChange(
                (),
                False,
                message=(
                    "TeX availability changed, but the render probe failed; "
                    f"safe text rendering was kept: {exc}"
                ),
                rollback_complete=True,
            )
        if enabled:
            self._tex_effective_overrides.difference_update(
                controller.component_id for controller in requested
            )
        else:
            self._tex_effective_overrides.update(
                controller.component_id for controller in requested
            )
        return ComponentBatchChange((), True)

    def apply(
        self,
        component,
        properties: dict[str, Any],
    ) -> ComponentChange:
        """Apply the pending values through the component Controller."""

        controller = _controller(
            self.registry,
            component,
            TextController,
        )
        result = self.apply_many(((controller, properties),))
        if not result.changes:
            return _rejected(
                controller,
                result.message or "Text render failed.",
            )
        change = result.changes[-1] if not result.committed else result.changes[0]
        if not result.committed:
            return replace(
                change,
                message=result.message or (
                    "Text render failed; keeping the last valid text and "
                    "rendering settings."
                ),
            )
        return _notices(change, *result.notices)

    def apply_many(
        self,
        patches: Iterable[tuple[object, dict[str, Any]]],
    ) -> ComponentBatchChange:
        """Apply multiple Text patches in one transaction and render probe."""

        resolved: list[tuple[TextController, dict[str, Any]]] = []
        for component, properties in patches:
            controller = _controller(
                self.registry,
                component,
                TextController,
            )
            patch = dict(properties)
            if patch.get("usetex") and not self.tex_enabled():
                return ComponentBatchChange(
                    (
                        _rejected(
                            controller,
                            "Enable TeX before using TeX rendering for this text.",
                        ),
                    ),
                    False,
                    message=(
                        "Enable TeX before using TeX rendering for this text."
                    ),
                )
            resolved.append((controller, patch))

        if not resolved:
            return ComponentBatchChange((), True)

        glyph_messages: dict[str, str] = {}

        def verify() -> None:
            figures = []
            seen: set[int] = set()
            for controller, _properties in resolved:
                figure = controller.resolve_target().figure
                if id(figure) in seen:
                    continue
                seen.add(id(figure))
                figures.append(figure)
            for figure in figures:
                with (
                    capture_font_diagnostics() as captured,
                    warnings.catch_warnings(record=True) as caught,
                ):
                    warnings.simplefilter("always", UserWarning)
                    figure.canvas.draw()
                for warning in caught:
                    message = str(warning.message)
                    notice = normalize_font_diagnostic(message)
                    if (
                        notice is not None
                        and notice.key.startswith("matplotlib-glyph:")
                    ):
                        glyph_messages.setdefault(notice.key, notice.message)
                        tex_config.tex_logger().warning(
                            "Matplotlib text glyph warning action=component-render message=%s",
                            message,
                        )
                    else:
                        warnings.warn(
                            warning.message,
                            warning.category,
                            stacklevel=2,
                        )
                for notice in captured.notices:
                    if not notice.key.startswith("matplotlib-glyph:"):
                        continue
                    glyph_messages.setdefault(notice.key, notice.message)
                    tex_config.tex_logger().warning(
                        "Matplotlib text glyph warning action=component-render message=%s",
                        notice.message,
                    )
            if glyph_messages:
                codepoints = [
                    key.removeprefix("matplotlib-glyph:")
                    for key in glyph_messages
                    if key != "matplotlib-glyph:unknown"
                ]
                detail = (
                    "glyphs "
                    + ", ".join(f"U+{codepoint}" for codepoint in codepoints)
                    if codepoints
                    else "one or more glyphs"
                )
                raise ValueError(
                    f"The current text font cannot render {detail}; "
                    "the text was not updated."
                )

        result = self.registry.apply_transaction(
            tuple(
                ComponentMutation(
                    controller.component_id,
                    properties=properties,
                )
                for controller, properties in resolved
            ),
            verifier=verify,
        )
        if not result.committed:
            tex_config.tex_logger().warning(
                "Text render failed action=component-render error=%s",
                result.message,
            )
            detail = result.message.strip()
            message = (
                "Text render failed; keeping the last valid text and "
                "rendering settings."
            )
            if detail:
                message += f" {detail}"
            return replace(
                result,
                message=message,
            )
        return result
