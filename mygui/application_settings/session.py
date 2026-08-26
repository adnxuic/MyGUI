"""Settings session: dirty patch plus base revision only."""

from __future__ import annotations

from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Mapping
from uuid import uuid4


@dataclass(slots=True)
class SettingsSession:
    """Draft handle. Stores only dirty keys and the revision they were based on."""

    base_revision: int
    service_id: int
    session_id: str = field(default_factory=lambda: uuid4().hex)
    _dirty: dict[str, Any] = field(default_factory=dict, repr=False)

    def dirty_patch(self) -> Mapping[str, Any]:
        """Return an immutable view of staged key/value changes."""

        return MappingProxyType(dict(self._dirty))

    def is_dirty(self) -> bool:
        """Return whether any keys are staged."""

        return bool(self._dirty)

    def stage(self, key: str, value: Any) -> None:
        """Record one dirty key. Validation runs at commit time."""

        self._dirty[str(key)] = value

    def stage_many(self, values: Mapping[str, Any]) -> None:
        """Merge several dirty keys into this session."""

        for key, value in values.items():
            self.stage(key, value)

    def _replace_dirty(self, values: Mapping[str, Any]) -> None:
        self._dirty = {str(key): value for key, value in values.items()}

    def _clear_dirty(self) -> None:
        self._dirty.clear()

    def _drop_keys(self, keys: set[str]) -> None:
        for key in keys:
            self._dirty.pop(key, None)
