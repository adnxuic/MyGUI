"""Read-only completeness audit for first-party component contracts.

The audit composes Controller, EditorProfile, restore-phase, materializer, and
deletion-handler declarations. It is for startup verification and tests only
and must not become a second business-state store.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from .controllers.registry_bridge import CONTROLLER_TYPES, validate_controller_contracts
from .errors import ComponentValidationError
from .models import (
    ComponentKind,
    ComponentRole,
    DeletionPolicy,
    ROLES_BY_KIND,
    RestorePhase,
)


@dataclass(frozen=True, slots=True)
class ComponentContractAuditRow:
    """One kind/role completeness row derived from existing authorities."""

    kind: ComponentKind
    role: ComponentRole
    controller_type: str
    has_editor_profile: bool
    restore_phase: RestorePhase | None
    has_materializer: bool
    deletion_policy: DeletionPolicy
    has_deletion_handler: bool
    complete: bool


def _complete_row(
    *,
    has_editor_profile: bool,
    restore_phase: RestorePhase | None,
    has_materializer: bool,
    deletion_policy: DeletionPolicy,
    has_deletion_handler: bool,
) -> bool:
    if not has_editor_profile:
        return False
    if restore_phase is None:
        if has_materializer:
            return False
    elif not has_materializer:
        return False
    if deletion_policy is DeletionPolicy.REMOVE:
        return has_deletion_handler
    return not has_deletion_handler


def audit_component_contracts(
    *,
    editor_profile_keys: Iterable[tuple[ComponentKind, ComponentRole]] | None = None,
    materializer_keys: Iterable[tuple[ComponentKind, ComponentRole]] | None = None,
    deletion_handler_keys: Iterable[tuple[ComponentKind, ComponentRole]] | None = None,
) -> tuple[ComponentContractAuditRow, ...]:
    """Return one audit row for every registered Controller key.

    Omitted key sets default to the production expectations: every
    ``ROLES_BY_KIND`` pair, every Controller-declared restore phase, and
    every ``DeletionPolicy.REMOVE`` Controller. Callers that have live
    registries should pass the actual keys so extra or missing declarations
    fail completeness.
    """

    expected_editor = (
        frozenset(editor_profile_keys)
        if editor_profile_keys is not None
        else frozenset(
            (kind, role)
            for kind, roles in ROLES_BY_KIND.items()
            for role in roles
        )
    )
    declared_phases = validate_controller_contracts()
    expected_materializers = (
        frozenset(materializer_keys)
        if materializer_keys is not None
        else frozenset(declared_phases)
    )
    expected_deletion = (
        frozenset(deletion_handler_keys)
        if deletion_handler_keys is not None
        else frozenset(
            key
            for key, controller_type in CONTROLLER_TYPES.items()
            if controller_type.DELETION_POLICY is DeletionPolicy.REMOVE
        )
    )
    rows: list[ComponentContractAuditRow] = []
    for key in sorted(
        CONTROLLER_TYPES,
        key=lambda item: (item[0].value, item[1].value),
    ):
        kind, role = key
        controller_type = CONTROLLER_TYPES[key]
        restore_phase = controller_type.RESTORE_PHASE
        deletion_policy = controller_type.DELETION_POLICY
        has_editor_profile = key in expected_editor
        has_materializer = key in expected_materializers
        has_deletion_handler = key in expected_deletion
        rows.append(
            ComponentContractAuditRow(
                kind=kind,
                role=role,
                controller_type=controller_type.__name__,
                has_editor_profile=has_editor_profile,
                restore_phase=restore_phase,
                has_materializer=has_materializer,
                deletion_policy=deletion_policy,
                has_deletion_handler=has_deletion_handler,
                complete=_complete_row(
                    has_editor_profile=has_editor_profile,
                    restore_phase=restore_phase,
                    has_materializer=has_materializer,
                    deletion_policy=deletion_policy,
                    has_deletion_handler=has_deletion_handler,
                ),
            )
        )
    return tuple(rows)


def require_complete_component_contracts(
    *,
    editor_profile_keys: Iterable[tuple[ComponentKind, ComponentRole]] | None = None,
    materializer_keys: Iterable[tuple[ComponentKind, ComponentRole]] | None = None,
    deletion_handler_keys: Iterable[tuple[ComponentKind, ComponentRole]] | None = None,
) -> tuple[ComponentContractAuditRow, ...]:
    """Fail fast when any Controller key is missing a required declaration."""

    rows = audit_component_contracts(
        editor_profile_keys=editor_profile_keys,
        materializer_keys=materializer_keys,
        deletion_handler_keys=deletion_handler_keys,
    )
    incomplete = [
        f"{row.kind.value}/{row.role.value}"
        for row in rows
        if not row.complete
    ]
    if incomplete:
        raise ComponentValidationError(
            "Incomplete component contracts: " + ", ".join(incomplete)
        )
    return rows
