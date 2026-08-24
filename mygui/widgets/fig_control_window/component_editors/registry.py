"""Resolve editor profiles and manage Inspector lifecycles."""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtWidgets import QWidget
from mygui.figuremodify.components import (
    ComponentKind,
    ComponentRole,
    CONTROLLER_TYPES,
    ROLES_BY_KIND,
)
from mygui.figuremodify.components.exposure_contract import (
    validate_matplotlib_exposure_contracts,
)
from mygui.figuremodify.components.models import EditorKind

from .base import ComponentEditorBase
from .inspector import ComponentInspector, EditorProfile


EditorKey = tuple[ComponentKind, ComponentRole]


EDITABLE_DATA_KEYS: dict[EditorKey, frozenset[str]] = {
    (ComponentKind.LINE, ComponentRole.LINE): frozenset({"x", "y"}),
    (ComponentKind.LINE, ComponentRole.FUNCTION_CURVE): frozenset(
        {"expression", "x_start", "x_stop", "samples"}
    ),
    (ComponentKind.LINE, ComponentRole.DATA_PLOT): frozenset(
        {"x_ref", "y_ref", "preprocess"}
    ),
    (ComponentKind.LINE, ComponentRole.FIT_CURVE): frozenset(
        {
            "x_ref", "y_ref", "preprocess", "engine", "fit_type",
            "fit_options", "fit_result", "expression", "x_start", "x_stop",
        }
    ),
    (ComponentKind.LINE, ComponentRole.INTERPOLATION): frozenset(
        {
            "x_ref", "y_ref", "preprocess", "method", "k", "samples",
            "lam", "lam_auto",
        }
    ),
    (ComponentKind.SCATTER, ComponentRole.SCATTER): frozenset(
        {"x_ref", "y_ref", "color_ref", "size_ref", "preprocess"}
    ),
    (ComponentKind.COLORBAR, ComponentRole.COLORBAR): frozenset(
        {"source_component_id"}
    ),
    (ComponentKind.IN_AXES, ComponentRole.IN_AXES_IMAGE): frozenset(
        {"filename", "mime_type", "payload_base64"}
    ),
    (
        ComponentKind.REFERENCE_MARKS,
        ComponentRole.REFLECTION_POSITIONS,
    ): frozenset({"positions", "position_ref", "placement"}),
}


PROXY_KEYS: dict[EditorKey, frozenset[str]] = {
    (ComponentKind.AXES, ComponentRole.AXES): frozenset(
        {"x_inverted", "y_inverted"}
    ),
}


class EditorRegistry:
    """Map exact kind/role pairs to immutable production profiles."""

    def __init__(self):
        self._editors: dict[
            tuple[str, str | None],
            type[QWidget] | Callable,
        ] = {}
        self._profiles: dict[EditorKey, EditorProfile] = {}
        self._frozen = False

    def _require_mutable(self) -> None:
        if self._frozen:
            raise RuntimeError("EditorRegistry is frozen.")

    def freeze(self) -> None:
        """Seal production registration after the complete startup gate.

        Canvas initialization registers profiles first, then calls freeze()
        once. Validation is never cached or skipped.
        """

        self.validate_production_profiles()
        self._frozen = True

    @property
    def frozen(self) -> bool:
        return self._frozen

    @staticmethod
    def _value_key(value) -> str:
        return str(getattr(value, "value", value or "")).casefold()

    @staticmethod
    def _kind_key(kind) -> str:
        return str(getattr(kind, "value", kind or "")).casefold()

    @staticmethod
    def component_kind(component) -> str:
        """Return the component kind."""

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
        """Return the component role."""

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
        """Register an editor for the explicit generic/tooling entry point."""

        self._require_mutable()

        key = (
            self._kind_key(kind),
            None if role is None else self._value_key(role),
        )

        def decorator(editor_type):
            self._require_mutable()
            self._editors[key] = editor_type
            return editor_type

        return decorator(editor) if editor is not None else decorator

    def unregister(self, kind: str, *, role=None) -> None:
        """Remove the supplied registration."""

        self._require_mutable()

        key = (
            self._kind_key(kind),
            None if role is None else self._value_key(role),
        )
        self._editors.pop(key, None)
        if role is not None:
            self._profiles.pop(
                (ComponentKind(kind), ComponentRole(role)),
                None,
            )

    def register_profile(
        self,
        kind: ComponentKind | str,
        profile: EditorProfile,
        *,
        role: ComponentRole | str,
    ) -> None:
        """Register one exact production ``(kind, role)`` profile."""

        self._require_mutable()
        key = (ComponentKind(kind), ComponentRole(role))
        if key in self._profiles:
            raise ValueError(
                "Duplicate Editor profile for "
                f"{key[0].value}/{key[1].value}."
            )
        self._profiles[key] = profile

    def profile_for(
        self,
        kind: ComponentKind | str,
        role: ComponentRole | str,
    ) -> EditorProfile | None:
        """Return an exact profile without creating an Inspector."""

        return self._profiles.get((ComponentKind(kind), ComponentRole(role)))

    def resolve_profile(self, component) -> EditorProfile | None:
        """Return the editor profile registered for a component."""

        try:
            kind = ComponentKind(self.component_kind(component))
            role = ComponentRole(self.component_role(component))
        except ValueError:
            return None
        return self._profiles.get((kind, role))

    def validate_production_profiles(self) -> None:
        """Fail fast unless every schema-v14 kind/role has one exact profile."""

        expected = {
            (kind, role)
            for kind, roles in ROLES_BY_KIND.items()
            for role in roles
        }
        missing = sorted(
            expected - set(self._profiles),
            key=lambda item: (item[0].value, item[1].value),
        )
        unexpected = sorted(
            set(self._profiles) - expected,
            key=lambda item: (item[0].value, item[1].value),
        )
        if missing or unexpected:
            details = []
            if missing:
                details.append(
                    "missing "
                    + ", ".join(
                        f"{kind.value}/{role.value}"
                        for kind, role in missing
                    )
                )
            if unexpected:
                details.append(
                    "unexpected "
                    + ", ".join(
                        f"{kind.value}/{role.value}"
                        for kind, role in unexpected
                    )
                )
            raise ValueError("Invalid production Editor profiles: " + "; ".join(details))
        for key in sorted(
            expected,
            key=lambda item: (item[0].value, item[1].value),
        ):
            controller_type = CONTROLLER_TYPES[key]
            specs = tuple(controller_type.PROPERTY_SPECS)
            persistent = {spec.key for spec in specs if spec.persistent}
            profile = self._profiles[key]
            exposed: list[str] = []
            hidden: list[str] = []
            data_keys: list[str] = []
            proxy_keys: list[str] = []
            for section in profile.sections:
                exposed.extend(section.property_keys)
                hidden.extend(section.intentionally_hidden)
                data_keys.extend(section.data_keys)
                proxy_keys.extend(section.proxy_keys)
            declared = exposed + hidden
            duplicates = sorted(
                name for name in set(declared) if declared.count(name) != 1
            )
            unknown = sorted(set(declared) - persistent)
            omitted = sorted(persistent - set(declared))
            if duplicates or unknown or omitted:
                details = []
                if duplicates:
                    details.append(f"duplicate properties {duplicates!r}")
                if unknown:
                    details.append(f"unknown properties {unknown!r}")
                if omitted:
                    details.append(f"unexposed properties {omitted!r}")
                raise ValueError(
                    "Invalid property exposure for "
                    f"{key[0].value}/{key[1].value}: "
                    + ", ".join(details)
                )
            for category, values in (
                ("data", data_keys),
                ("proxy", proxy_keys),
            ):
                duplicate_values = sorted(
                    name for name in set(values) if values.count(name) != 1
                )
                if duplicate_values:
                    raise ValueError(
                        f"Invalid {category} exposure for "
                        f"{key[0].value}/{key[1].value}: duplicate "
                        f"keys {duplicate_values!r}."
                    )
            expected_data = EDITABLE_DATA_KEYS.get(key, frozenset())
            actual_data = set(data_keys)
            if actual_data != expected_data:
                raise ValueError(
                    "Invalid data exposure for "
                    f"{key[0].value}/{key[1].value}: expected "
                    f"{sorted(expected_data)!r}, got {sorted(actual_data)!r}."
                )
            expected_proxies = PROXY_KEYS.get(key, frozenset())
            actual_proxies = set(proxy_keys)
            if actual_proxies != expected_proxies:
                raise ValueError(
                    "Invalid proxy exposure for "
                    f"{key[0].value}/{key[1].value}: expected "
                    f"{sorted(expected_proxies)!r}, got "
                    f"{sorted(actual_proxies)!r}."
                )
            overlap = sorted(set(proxy_keys) & persistent)
            if overlap:
                raise ValueError(
                    "Proxy keys must not create persistent state for "
                    f"{key[0].value}/{key[1].value}: {overlap!r}."
                )
            for spec in specs:
                if spec.editor is EditorKind.ENUM and not spec.choices:
                    raise ValueError(
                        f"Enum property {key[0].value}/{key[1].value}/"
                        f"{spec.key} has no choices."
                    )
        validate_matplotlib_exposure_contracts()

    def resolve(self, component):
        """Resolve an explicitly registered generic/tooling editor."""

        kind = self.component_kind(component)
        role = self.component_role(component)
        return self._editors.get(
            (kind, role),
            self._editors.get((kind, None)),
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
        """Create and return a new instance."""

        if context is not None:
            color_library = context.color_library
        if color_library is None:
            raise ValueError(
                "EditorRegistry requires the application ColorLibrary."
            )
        profile = self.resolve_profile(component)
        if profile is None:
            kind = self.component_kind(component) or "unknown"
            role = self.component_role(component) or "unknown"
            raise LookupError(
                f"No exact Editor profile for {kind}/{role}."
            )
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

    def create_generic(
        self,
        component,
        *,
        editor_type: type[QWidget] | Callable | None = None,
        context=None,
        color_library=None,
        parent=None,
        **kwargs,
    ):
        """Explicitly create a generic editor for tests and maintenance tools."""

        if context is not None:
            color_library = context.color_library
        if color_library is None:
            raise ValueError(
                "EditorRegistry requires the application ColorLibrary."
            )
        editor_type = editor_type or self.resolve(component) or ComponentEditorBase
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
