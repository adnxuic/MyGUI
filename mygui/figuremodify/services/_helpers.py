"""Shared Controller lookup and change helpers for domain services."""

from __future__ import annotations

from dataclasses import replace
from typing import Any


from mygui.database import (
    ColumnRef,
)
from mygui.figuremodify.components import (
    ChangeStatus,
    ComponentChange,
    ComponentNotice,
    ComponentRegistry,
    MessageLevel,
)

def _controller(
    registry: ComponentRegistry,
    value,
    expected_type=None,
):
    result = registry.get(value) if isinstance(value, str) else value
    if expected_type is not None and not isinstance(result, expected_type):
        raise TypeError(
            f"Expected {expected_type.__name__}, got {type(result).__name__}."
        )
    return result


def _rejected(controller, message: str) -> ComponentChange:
    state = controller.state
    return ComponentChange(
        controller.component_id,
        None,
        state,
        state,
        ChangeStatus.REJECTED,
        message=str(message),
    )


def _notices(
    change: ComponentChange,
    *notices: ComponentNotice,
) -> ComponentChange:
    return replace(
        change,
        notices=tuple(change.notices) + tuple(notices),
    )


def _warning(message: str) -> ComponentNotice:
    return ComponentNotice(MessageLevel.WARNING, message)


def _column_ref(value: ColumnRef | dict[str, Any]) -> ColumnRef:
    return value if isinstance(value, ColumnRef) else ColumnRef.from_dict(value)
