"""Runtime binding transaction. Production appearance uses ThemeSettingsBinder."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import Protocol, runtime_checkable

from .errors import RuntimeBindingError, RuntimeBindingRollbackError
from .keys import (
    APPEARANCE_DENSITY,
    APPEARANCE_THEME_MODE,
    APPEARANCE_UI_FONT_POINT_SIZE,
)
from .models import ApplicationSettingsSnapshot

APPEARANCE_LIVE_KEYS = frozenset(
    {
        APPEARANCE_THEME_MODE,
        APPEARANCE_UI_FONT_POINT_SIZE,
        APPEARANCE_DENSITY,
    }
)


def appearance_live_keys(changed_keys: Iterable[str]) -> frozenset[str]:
    """Return the LIVE appearance keys present in ``changed_keys``."""

    return frozenset(changed_keys) & APPEARANCE_LIVE_KEYS


@runtime_checkable
class SettingsRuntimeBinder(Protocol):
    """Apply or roll back LIVE_REVERSIBLE settings.

    Production appearance is ``ThemeSettingsBinder`` from
    ``mygui.application_theme``. Tests inject ``RecordingRuntimeBinder``.
    """

    def apply(
        self,
        snapshot: ApplicationSettingsSnapshot,
        changed_keys: frozenset[str],
    ) -> None:
        """Apply a preview. Must be reversible via ``rollback``."""

    def rollback(self) -> None:
        """Restore the pre-preview runtime state."""

    def confirm(self) -> None:
        """Drop mementos after a successful document commit."""


class RecordingRuntimeBinder:
    """Test double that records apply/rollback/confirm. Does not touch QSS/Theme."""

    def __init__(
        self,
        name: str = "binder",
        *,
        fail_apply: bool = False,
        fail_rollback: bool = False,
        fail_confirm: bool = False,
    ) -> None:
        self.name = name
        self.fail_apply = fail_apply
        self.fail_rollback = fail_rollback
        self.fail_confirm = fail_confirm
        self.actions: list[tuple[str, object]] = []
        self._memento: frozenset[str] | None = None

    def apply(
        self,
        snapshot: ApplicationSettingsSnapshot,
        changed_keys: frozenset[str],
    ) -> None:
        if self.fail_apply:
            raise RuntimeBindingError(f"{self.name} apply failed")
        self._memento = frozenset(changed_keys)
        self.actions.append(("apply", (snapshot.revision, frozenset(changed_keys))))

    def rollback(self) -> None:
        if self.fail_rollback:
            raise RuntimeError(f"{self.name} rollback failed")
        keys = self._memento
        self._memento = None
        self.actions.append(("rollback", keys))

    def confirm(self) -> None:
        if self.fail_confirm:
            raise RuntimeError(f"{self.name} confirm failed")
        self._memento = None
        self.actions.append(("confirm", None))


class RuntimeBindingTransaction:
    """Apply binders in order; roll them back in reverse on failure."""

    def __init__(self, binders: Sequence[SettingsRuntimeBinder]) -> None:
        self._binders = list(binders)
        self._applied: list[SettingsRuntimeBinder] = []
        self.state = "idle"

    def apply_preview(
        self,
        snapshot: ApplicationSettingsSnapshot,
        changed_keys: Iterable[str],
    ) -> None:
        keys = frozenset(changed_keys)
        if not keys or not self._binders:
            self.state = "previewed"
            return
        try:
            for binder in self._binders:
                binder.apply(snapshot, keys)
                self._applied.append(binder)
            self.state = "previewed"
        except Exception as exc:
            self.rollback(primary=exc)
            raise

    def rollback(self, primary: BaseException | None = None) -> None:
        errors: list[BaseException] = []
        while self._applied:
            binder = self._applied.pop()
            try:
                binder.rollback()
            except Exception as exc:  # noqa: BLE001 — collect then raise
                errors.append(exc)
        if errors:
            self.state = "uncertain"
            raise RuntimeBindingRollbackError(tuple(errors), primary=primary)
        self.state = "rolled_back"

    def confirm(self) -> None:
        errors: list[BaseException] = []
        for binder in list(self._applied):
            confirm = getattr(binder, "confirm", None)
            if confirm is None:
                continue
            try:
                confirm()
            except Exception as exc:  # noqa: BLE001
                errors.append(exc)
        self._applied.clear()
        if errors:
            self.state = "uncertain"
            raise RuntimeBindingRollbackError(tuple(errors))
        self.state = "committed"


class SettingsRuntimeApplier:
    """Factory for one commit's runtime binding transaction.

    Default construction stays empty so existing fake-binder tests are
    unchanged. Integrator injects ``ThemeSettingsBinder`` via ``with_binder``
    or ``compose_theme_runtime_applier``.
    """

    def __init__(
        self,
        binders: Sequence[SettingsRuntimeBinder] | None = None,
    ) -> None:
        self._binders = list(binders or ())

    def with_binder(self, binder: SettingsRuntimeBinder) -> SettingsRuntimeApplier:
        """Return a new applier that also runs ``binder``."""

        return SettingsRuntimeApplier([*self._binders, binder])

    def transaction(self) -> RuntimeBindingTransaction:
        return RuntimeBindingTransaction(self._binders)
