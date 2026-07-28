from __future__ import annotations

from collections.abc import Callable

from Qt_core import QWidget

from .base import ComponentEditorBase
from .inspector import ComponentInspector, EditorProfile


class EditorRegistry:
    """Map ``(component kind, role)`` pairs to reusable editor classes.

    A kind-only registration remains the fallback for all roles of that kind.
    This lets line-like components share the generic property editor while
    fit/interpolation/data roles opt into specialized editors.
    """

    def __init__(self, fallback: type[ComponentEditorBase] = ComponentEditorBase):
        self.fallback = fallback
        self._editors: dict[
            tuple[str, str | None],
            type[QWidget] | Callable,
        ] = {}
        self._profiles: dict[
            tuple[str, str | None],
            EditorProfile,
        ] = {}

    @staticmethod
    def _value_key(value) -> str:
        return str(getattr(value, "value", value or "")).casefold()

    @staticmethod
    def _kind_key(kind) -> str:
        return str(getattr(kind, "value", kind or "")).casefold()

    @staticmethod
    def component_kind(component) -> str:
        kind = getattr(component, "kind", None)
        if kind is None:
            state = getattr(component, "state", None)
            kind = (
                state.get("kind")
                if isinstance(state, dict)
                else getattr(state, "kind", None)
            )
        if kind is None:
            reader = getattr(component, "read_state", None)
            state = reader() if callable(reader) else None
            if isinstance(state, dict):
                kind = state.get("kind")
            else:
                kind = getattr(state, "kind", None)
        return EditorRegistry._kind_key(kind)

    @staticmethod
    def component_role(component) -> str:
        role = getattr(component, "role", None)
        if role is None:
            state = getattr(component, "state", None)
            role = (
                state.get("role")
                if isinstance(state, dict)
                else getattr(state, "role", None)
            )
        if role is None:
            reader = getattr(component, "read_state", None)
            state = reader() if callable(reader) else None
            if isinstance(state, dict):
                role = state.get("role")
            else:
                role = getattr(state, "role", None)
        return EditorRegistry._value_key(role)

    def register(self, kind: str, editor=None, *, role=None):
        key = (
            self._kind_key(kind),
            None if role is None else self._value_key(role),
        )

        def decorator(editor_type):
            self._editors[key] = editor_type
            return editor_type

        return decorator(editor) if editor is not None else decorator

    def unregister(self, kind: str, *, role=None) -> None:
        key = (
            self._kind_key(kind),
            None if role is None else self._value_key(role),
        )
        self._editors.pop(key, None)
        self._profiles.pop(key, None)

    def register_profile(
        self,
        kind: str,
        profile: EditorProfile,
        *,
        role=None,
    ) -> None:
        key = (
            self._kind_key(kind),
            None if role is None else self._value_key(role),
        )
        self._profiles[key] = profile

    def resolve_profile(self, component) -> EditorProfile | None:
        kind = self.component_kind(component)
        role = self.component_role(component)
        return self._profiles.get(
            (kind, role),
            self._profiles.get((kind, None)),
        )

    def resolve(self, component):
        kind = self.component_kind(component)
        role = self.component_role(component)
        return self._editors.get(
            (kind, role),
            self._editors.get((kind, None), self.fallback),
        )

    def create(
        self,
        component,
        *,
        context=None,
        color_library=None,
        parent=None,
        **kwargs,
    ):
        if context is not None:
            color_library = context.color_library
        if color_library is None:
            raise ValueError(
                "EditorRegistry requires the application ColorLibrary."
            )
        profile = self.resolve_profile(component)
        if profile is not None:
            if context is None:
                raise ValueError(
                    "Profile-driven editors require an EditorContext."
                )
            return ComponentInspector(
                component,
                context=context,
                profile=profile,
                color_library=color_library,
                parent=parent,
            )
        editor_type = self.resolve(component)
        if context is not None:
            return editor_type(
                component,
                context=context,
                color_library=color_library,
                parent=parent,
                **kwargs,
            )
        return editor_type(
            component,
            color_library=color_library,
            parent=parent,
            **kwargs,
        )
