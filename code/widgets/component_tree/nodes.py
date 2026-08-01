"""Typed node identities and Qt roles for the Components tree."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TypeAlias

from Qt_core import Qt

from code.figuremodify.components import ComponentKind, ComponentRole


COMPONENT_ID_ROLE = int(Qt.UserRole) + 1
COMPONENT_KIND_ROLE = COMPONENT_ID_ROLE + 1
COMPONENT_ROLE_ROLE = COMPONENT_KIND_ROLE + 1
COMPONENT_SEARCH_ROLE = COMPONENT_ROLE_ROLE + 1
NODE_KEY_ROLE = COMPONENT_SEARCH_ROLE + 1
VIRTUAL_GROUP_ROLE = NODE_KEY_ROLE + 1


@dataclass(frozen=True, slots=True)
class ComponentNodeKey:
    """Collision-proof tree key for one real Component."""

    component_id: str


@dataclass(frozen=True, slots=True)
class GroupNodeKey:
    """Collision-proof UI-only grouping key."""

    parent_id: str
    group_kind: str
    kind: ComponentKind | None = None
    role: ComponentRole | None = None


TreeNodeKey: TypeAlias = ComponentNodeKey | GroupNodeKey
