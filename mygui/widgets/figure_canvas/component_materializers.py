"""Register exact runtime materializers for persisted dynamic components."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass

from mygui.figuremodify.components import (
    ComponentKind,
    ComponentRegistrationTransaction,
    ComponentRole,
    ComponentState,
    ComponentValidationError,
)


MaterializerKey = tuple[ComponentKind, ComponentRole]
MaterializerHandler = Callable[
    [ComponentState, ComponentRegistrationTransaction],
    object,
]


@dataclass(frozen=True, slots=True)
class ComponentMaterializer:
    """Describe one exact persisted-component runtime materializer."""

    key: MaterializerKey
    handler: MaterializerHandler


class ComponentMaterializerRegistry:
    """Resolve dynamic component restoration without Canvas role branching."""

    def __init__(self) -> None:
        self._handlers: dict[MaterializerKey, MaterializerHandler] = {}

    def register(
        self,
        kind: ComponentKind,
        role: ComponentRole,
        handler: MaterializerHandler,
    ) -> None:
        key = (ComponentKind(kind), ComponentRole(role))
        if key in self._handlers:
            raise ComponentValidationError(
                f"Duplicate component materializer for {key!r}."
            )
        if not callable(handler):
            raise TypeError("Component materializer handler must be callable.")
        self._handlers[key] = handler

    def materialize(
        self,
        state: ComponentState,
        transaction: ComponentRegistrationTransaction,
    ) -> object:
        key = (state.kind, state.role)
        try:
            handler = self._handlers[key]
        except KeyError as exc:
            raise ComponentValidationError(
                "No runtime materializer is registered for "
                f"{state.kind.value}/{state.role.value}."
            ) from exc
        return handler(state, transaction)

    def validate_complete(self, keys: Iterable[MaterializerKey]) -> None:
        expected = set(keys)
        missing = expected - set(self._handlers)
        extra = set(self._handlers) - expected
        if missing or extra:
            detail = []
            if missing:
                detail.append(f"missing={sorted(missing, key=str)!r}")
            if extra:
                detail.append(f"extra={sorted(extra, key=str)!r}")
            raise ComponentValidationError(
                "Invalid component materializer registry: " + ", ".join(detail)
            )

    @property
    def keys(self) -> frozenset[MaterializerKey]:
        """Return the exact registered materializer keys."""

        return frozenset(self._handlers)
