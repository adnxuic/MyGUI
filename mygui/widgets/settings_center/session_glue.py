"""Bind a SettingsSession to ThemeService preview for one Settings Center opening."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from mygui.application_settings.document import flatten_snapshot
from mygui.application_settings.errors import SettingsValidationError
from mygui.application_settings.keys import (
    APPEARANCE_DENSITY,
    APPEARANCE_THEME_MODE,
    APPEARANCE_UI_FONT_POINT_SIZE,
    PAGE_APPEARANCE,
    PAGE_IDS,
)
from mygui.application_settings.models import (
    AppearanceSettings,
    ApplicationSettingsSnapshot,
    SettingsCommitResult,
    SettingsDraftResult,
    ThemeMode,
)
from mygui.application_settings.registry import SettingsRegistry, production_settings_registry
from mygui.application_settings.runtime import appearance_live_keys
from mygui.application_settings.service import ApplicationSettingsService
from mygui.application_settings.session import SettingsSession
from mygui.application_theme.binder import preferences_from_appearance
from mygui.application_theme.errors import ThemeApplyError, ThemeRollbackError
from mygui.application_theme.service import ThemeService


class SettingsCenterSession:
    """One open Settings Center: dirty patch plus reversible appearance preview.

    The session object itself stores only the dirty patch and base revision.
    This glue reads ``ApplicationSettingsService.snapshot()`` for committed
    values and never writes window geometry.
    """

    def __init__(
        self,
        service: ApplicationSettingsService,
        theme: ThemeService,
        *,
        registry: SettingsRegistry | None = None,
    ) -> None:
        self._service = service
        self._theme = theme
        self._registry = registry or production_settings_registry()
        self._session: SettingsSession | None = None
        self._shell_previewing = False

    @property
    def session(self) -> SettingsSession | None:
        return self._session

    def is_active(self) -> bool:
        return self._session is not None

    def is_dirty(self) -> bool:
        return self._session is not None and self._session.is_dirty()

    def is_writable(self) -> bool:
        return bool(self._service.writable())

    @property
    def service(self) -> ApplicationSettingsService:
        return self._service

    def start(self) -> SettingsSession:
        """Open ``begin_session()``. Discards any leftover handle without writing."""

        if self._session is not None:
            self.abandon()
        self._session = self._service.begin_session()
        self._shell_previewing = False
        return self._session

    def draft_values(self) -> dict[str, Any]:
        """Committed snapshot values with the dirty patch overlaid."""

        values = flatten_snapshot(self._service.snapshot())
        if self._session is not None:
            values.update(self._session.dirty_patch())
        return values

    def draft_value(self, key: str) -> Any:
        values = self.draft_values()
        if key not in values:
            raise SettingsValidationError(f"Unknown setting {key!r}.")
        return values[key]

    def stage_value(self, key: str, value: Any) -> None:
        """Normalize, stage, and preview LIVE_REVERSIBLE appearance keys."""

        session = self._require_session()
        normalized = self._registry.spec(key).normalize(value)
        current = flatten_snapshot(self._service.snapshot()).get(key)
        if current == normalized:
            session._drop_keys({key})
        else:
            session.stage(key, normalized)
        if appearance_live_keys((key,)):
            try:
                if appearance_live_keys(session.dirty_patch()):
                    self.preview_appearance()
                else:
                    self._theme.restore_pre_session_appearance()
                    self._shell_previewing = False
            except (ThemeApplyError, ThemeRollbackError):
                session._drop_keys({key})
                try:
                    self._theme.restore_pre_session_appearance()
                except (ThemeApplyError, ThemeRollbackError):
                    pass
                self._shell_previewing = False
                raise

    def preview_appearance(self) -> None:
        """Apply draft appearance through ThemeService without writing storage."""

        self._require_session()
        self._theme.preview(self._appearance_preferences())
        self._shell_previewing = True

    def reset_page(self, page_id: str) -> SettingsDraftResult:
        """``reset_section`` draft only. Immediate commands must not use this."""

        session = self._require_session()
        if page_id not in PAGE_IDS:
            return SettingsDraftResult(
                success=False,
                session_revision=session.base_revision,
                dirty=session.dirty_patch(),
                error=f"Page {page_id!r} has no restore-defaults draft.",
            )
        result = self._service.reset_section(session, page_id)
        live = appearance_live_keys(session.dirty_patch())
        if live:
            self.preview_appearance()
        elif page_id == PAGE_APPEARANCE:
            self._theme.restore_pre_session_appearance()
            self._shell_previewing = False
        return result

    def reset_all(self) -> SettingsDraftResult:
        """Stage built-in defaults once. Does not write storage."""

        session = self._require_session()
        result = self._service.reset_all_preferences(session)
        live = appearance_live_keys(session.dirty_patch())
        if live:
            self.preview_appearance()
        else:
            self._theme.restore_pre_session_appearance()
            self._shell_previewing = False
        return result

    def commit(self) -> SettingsCommitResult:
        """Preview-capable apply, then ``commit_patch``. Storage failure restores chrome."""

        session = self._require_session()
        live = appearance_live_keys(session.dirty_patch())
        if live:
            self.preview_appearance()
        result = self._service.commit_patch(session)
        if not result.success:
            try:
                self._theme.restore_pre_session_appearance()
            except (ThemeApplyError, ThemeRollbackError):
                self._shell_previewing = False
                raise
            self._shell_previewing = False
            return result
        self._confirm_preview(result.snapshot)
        return result

    def abandon(self) -> None:
        """Cancel/Esc/close: restore pre-window appearance and drop the session."""

        try:
            self._theme.restore_pre_session_appearance()
        except (ThemeApplyError, ThemeRollbackError):
            self._session = None
            self._shell_previewing = False
            raise
        appearance = self._service.snapshot().appearance
        if appearance.theme_mode is ThemeMode.SYSTEM:
            try:
                self._theme.apply_committed(preferences_from_appearance(appearance))
            except (ThemeApplyError, ThemeRollbackError):
                self._session = None
                self._shell_previewing = False
                raise
        self._session = None
        self._shell_previewing = False

    def release(self) -> None:
        """OK after a successful commit: drop the session without rolling back chrome."""

        if self._theme_is_previewing():
            self._theme.apply_committed(
                preferences_from_appearance(self._service.snapshot().appearance)
            )
        self._session = None
        self._shell_previewing = False

    def _confirm_preview(self, snapshot: ApplicationSettingsSnapshot) -> None:
        if self._theme_is_previewing():
            self._theme.apply_committed(preferences_from_appearance(snapshot.appearance))
        self._shell_previewing = False

    def _appearance_preferences(self):
        values = self.draft_values()
        appearance = AppearanceSettings(
            theme_mode=values[APPEARANCE_THEME_MODE],
            ui_font_point_size=int(values[APPEARANCE_UI_FONT_POINT_SIZE]),
            density=values[APPEARANCE_DENSITY],
        )
        return preferences_from_appearance(appearance)

    def _theme_is_previewing(self) -> bool:
        return bool(getattr(self._theme, "_in_preview", False))

    def _require_session(self) -> SettingsSession:
        if self._session is None:
            raise SettingsValidationError("Settings Center session is not open.")
        return self._session


MessageCallback = Callable[[str, str], None]
