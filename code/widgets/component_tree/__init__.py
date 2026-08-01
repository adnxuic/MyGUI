"""Expose the project-scoped Components tree widgets."""

from .component_tree import ComponentTreeHost
from .model import ComponentTreeFilterProxyModel, ComponentTreeModel
from .nodes import (
    COMPONENT_ID_ROLE,
    NODE_KEY_ROLE,
    VIRTUAL_GROUP_ROLE,
    ComponentNodeKey,
    GroupNodeKey,
    TreeNodeKey,
)
from .dialogs import ComponentBatchDeleteDialog
from .view import ComponentTreeView

__all__ = [
    "COMPONENT_ID_ROLE",
    "NODE_KEY_ROLE",
    "VIRTUAL_GROUP_ROLE",
    "ComponentNodeKey",
    "GroupNodeKey",
    "TreeNodeKey",
    "ComponentTreeFilterProxyModel",
    "ComponentTreeHost",
    "ComponentTreeModel",
    "ComponentTreeView",
    "ComponentBatchDeleteDialog",
]
