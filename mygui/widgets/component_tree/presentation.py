"""Resolve declarative Editor profiles into Components tree presentation."""

from __future__ import annotations

import re
from typing import Any

from mygui.figuremodify.components import ComponentState
from mygui.widgets.fig_control_window.component_editors.inspector import (
    TreePresentationSpec,
)


_TEXT_LIMIT = 48
_WHITESPACE = re.compile(r"\s+")


def normalized_query(value: str) -> str:
    return _WHITESPACE.sub(" ", str(value or "")).strip().casefold()


def _preview(value: Any, *, limit: int = _TEXT_LIMIT) -> str:
    text = _WHITESPACE.sub(" ", str(value or "")).strip()
    if len(text) <= limit:
        return text
    return f"{text[: max(1, limit - 1)].rstrip()}…"


def _with_preview(prefix: str, value: Any) -> str:
    preview = _preview(value)
    return f"{prefix} — {preview}" if preview else prefix


class TreePresentationResolver:
    """Read UI-only tree rules from the authoritative Editor registry."""

    def __init__(self, editor_registry=None):
        self.editor_registry = editor_registry

    def profile(self, state: ComponentState):
        if self.editor_registry is None:
            return None
        return self.editor_registry.profile_for(state.kind, state.role)

    def spec(self, state: ComponentState) -> TreePresentationSpec:
        profile = self.profile(state)
        if profile is not None:
            return profile.tree
        return TreePresentationSpec(
            state.role.value.replace("_", " ").title(),
            sort_bucket=50,
        )

    def display_label(self, state: ComponentState) -> str:
        spec = self.spec(state)
        label = spec.label(state) if callable(spec.label) else spec.label
        value = spec.preview(state) if spec.preview is not None else None
        return _with_preview(label, value)

    def grouped_label(self, state: ComponentState, index: int) -> str:
        spec = self.spec(state)
        instance = f"{spec.instance_prefix or state.kind.value}{index + 1}"
        value = spec.preview(state) if spec.preview is not None else None
        return _with_preview(instance, value)

    def sort_key(self, state: ComponentState) -> tuple[Any, ...]:
        spec = self.spec(state)
        detail = (
            spec.sort_key(state)
            if spec.sort_key is not None
            else (state.order,)
        )
        return (spec.sort_bucket, *detail, state.id)

    def group_key(self, state: ComponentState) -> str | None:
        """Return a cross-role group key declared by the profile."""

        spec = self.spec(state)
        if not spec.group_title:
            return None
        return spec.group_key or f"{state.kind.value}:{state.role.value}"

    def delete_label(self, state: ComponentState) -> str:
        """Return the declared user-facing deletion noun."""

        spec = self.spec(state)
        if spec.delete_label:
            return spec.delete_label
        label = spec.label(state) if callable(spec.label) else spec.label
        return str(label)
