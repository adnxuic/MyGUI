"""Register exact runtime materializers for persisted dynamic components."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass

from mygui.figuremodify.components import (
    ComponentKind,
    ComponentRegistrationTransaction,
    ComponentRole,
    ComponentState,
    ComponentValidationError,
    RestorePhase,
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
    restore_phase: RestorePhase

    def __post_init__(self) -> None:
        kind, role = self.key
        object.__setattr__(
            self,
            "key",
            (ComponentKind(kind), ComponentRole(role)),
        )
        if not callable(self.handler):
            raise ComponentValidationError(
                "Component materializer handler must be callable."
            )
        if not isinstance(self.restore_phase, RestorePhase):
            try:
                object.__setattr__(
                    self,
                    "restore_phase",
                    RestorePhase(self.restore_phase),
                )
            except (TypeError, ValueError) as exc:
                raise ComponentValidationError(
                    "Component materializer restore phase is invalid."
                ) from exc


class ComponentMaterializerRegistry:
    """Resolve dynamic component restoration without Canvas role branching."""

    def __init__(self) -> None:
        self._declarations: dict[MaterializerKey, ComponentMaterializer] = {}

    def register(self, declaration: ComponentMaterializer) -> None:
        if not isinstance(declaration, ComponentMaterializer):
            raise TypeError(
                "Component materializer registry requires a declaration."
            )
        key = declaration.key
        if key in self._declarations:
            raise ComponentValidationError(
                f"Duplicate component materializer for {key!r}."
            )
        self._declarations[key] = declaration

    def materialize(
        self,
        state: ComponentState,
        transaction: ComponentRegistrationTransaction,
    ) -> object:
        key = (state.kind, state.role)
        try:
            declaration = self._declarations[key]
        except KeyError as exc:
            raise ComponentValidationError(
                "No runtime materializer is registered for "
                f"{state.kind.value}/{state.role.value}."
            ) from exc
        return declaration.handler(state, transaction)

    def validate_complete(
        self,
        expected_phases: Mapping[MaterializerKey, RestorePhase],
    ) -> None:
        expected = dict(expected_phases)
        missing = set(expected) - set(self._declarations)
        extra = set(self._declarations) - set(expected)
        phase_mismatches = {
            key: (expected[key], self._declarations[key].restore_phase)
            for key in set(expected).intersection(self._declarations)
            if expected[key] is not self._declarations[key].restore_phase
        }
        if missing or extra or phase_mismatches:
            detail = []
            if missing:
                detail.append(f"missing={sorted(missing, key=str)!r}")
            if extra:
                detail.append(f"extra={sorted(extra, key=str)!r}")
            if phase_mismatches:
                detail.append(
                    "phase_mismatches="
                    f"{sorted(phase_mismatches.items(), key=str)!r}"
                )
            raise ComponentValidationError(
                "Invalid component materializer registry: " + ", ".join(detail)
            )

    @property
    def keys(self) -> frozenset[MaterializerKey]:
        """Return the exact registered materializer keys."""

        return frozenset(self._declarations)

    @property
    def phases(self) -> tuple[RestorePhase, ...]:
        """Return the declared restore phases in execution order."""

        return tuple(
            sorted(
                {item.restore_phase for item in self._declarations.values()}
            )
        )

    def states_for_phase(
        self,
        states: Iterable[ComponentState],
        phase: RestorePhase,
    ) -> tuple[ComponentState, ...]:
        """Return deterministic states declared for one restore phase."""

        selected = [
            state
            for state in states
            if (
                declaration := self._declarations.get(
                    (state.kind, state.role)
                )
            )
            is not None
            and declaration.restore_phase is phase
        ]
        return tuple(
            sorted(
                selected,
                key=lambda item: (
                    item.parent_id or "",
                    item.order,
                    item.id,
                ),
            )
        )
