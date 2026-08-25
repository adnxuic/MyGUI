"""Shared Section callback aliases."""

from __future__ import annotations

from collections.abc import Callable

from mygui.database import ColumnRef

ApplyProperties = Callable[[dict[str, object]], object]
ApplyReferences = Callable[
    [object, ColumnRef, ColumnRef, dict[str, str], str],
    object,
]
