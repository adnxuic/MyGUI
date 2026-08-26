"""LIVE_REVERSIBLE appearance binder. Injected into SettingsRuntimeApplier."""

from __future__ import annotations

from collections.abc import Sequence

from mygui.application_settings.models import (
    AppearanceSettings,
    ApplicationSettingsSnapshot,
)
from mygui.application_settings.runtime import (
    SettingsRuntimeApplier,
    appearance_live_keys,
)

from .models import AppearancePreferences
from .service import ThemeService


def preferences_from_appearance(appearance: AppearanceSettings) -> AppearancePreferences:
    """Map settings appearance fields onto ThemeService preferences."""

    return AppearancePreferences(
        mode=appearance.theme_mode,
        font_pt=appearance.ui_font_point_size,
        density=appearance.density,
    )


def preferences_from_snapshot(
    snapshot: ApplicationSettingsSnapshot,
) -> AppearancePreferences:
    return preferences_from_appearance(snapshot.appearance)


class ThemeSettingsBinder:
    """Preview on apply, restore on rollback, confirm after a successful commit."""

    def __init__(self, theme: ThemeService) -> None:
        self._theme = theme
        self._armed = False
        self._preferences: AppearancePreferences | None = None

    def apply(
        self,
        snapshot: ApplicationSettingsSnapshot,
        changed_keys: frozenset[str],
    ) -> None:
        if not appearance_live_keys(changed_keys):
            self._armed = False
            self._preferences = None
            return
        preferences = preferences_from_snapshot(snapshot)
        self._theme.preview(preferences)
        self._preferences = preferences
        self._armed = True

    def rollback(self) -> None:
        if not self._armed:
            return
        try:
            self._theme.rollback()
        finally:
            self._armed = False
            self._preferences = None

    def confirm(self) -> None:
        if not self._armed:
            return
        preferences = self._preferences
        self._armed = False
        self._preferences = None
        if preferences is not None:
            self._theme.apply_committed(preferences)


def apply_committed_appearance(
    theme: ThemeService,
    snapshot: ApplicationSettingsSnapshot,
) -> None:
    """Apply settings appearance through ThemeService after the document load."""

    theme.apply_committed(preferences_from_snapshot(snapshot))


def compose_theme_runtime_applier(
    theme: ThemeService,
    extra: Sequence[object] = (),
) -> SettingsRuntimeApplier:
    """Return an applier with ThemeSettingsBinder first, then any extra binders.

    Existing tests that pass only ``RecordingRuntimeBinder`` are unchanged:
    they construct ``SettingsRuntimeApplier([binder])`` directly.
    """

    return SettingsRuntimeApplier((ThemeSettingsBinder(theme), *extra))


__all__ = [
    "ThemeSettingsBinder",
    "apply_committed_appearance",
    "compose_theme_runtime_applier",
    "preferences_from_appearance",
    "preferences_from_snapshot",
]
