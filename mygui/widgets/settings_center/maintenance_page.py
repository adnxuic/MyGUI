"""Maintenance page: dual-slot health, draft reset-all, and color-library commands."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QGroupBox,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from mygui.application_settings.service import ApplicationSettingsService
from mygui.application_settings.session import SettingsSession
from mygui.application_settings.storage.types import (
    DocumentHealth,
    StorageCommitResult,
    allows_draft_preference_reset,
    document_health_label,
    requires_immediate_storage_reset,
)
from mygui.widgets.common_widget.min_widget.color_library import ColorLibrary
from mygui.widgets.settings_center.pages import SettingsPageHost
from mygui.widgets.settings_center.specs import maintenance_page_spec

ConfirmFn = Callable[[str, str], bool]
HealthProvider = Callable[[], DocumentHealth]


RESET_ALL_TITLE = "Reset all application preferences"
RESET_ALL_TEXT = (
    "Stage the built-in application preference defaults? Choose Apply to save "
    "them. The color library is not changed."
)
IMMEDIATE_RESET_TITLE = "Reset incompatible storage"
IMMEDIATE_RESET_TEXT = (
    "Clear the application dual-slot document and leftover legacy keys, then "
    "restore writable defaults now? This does not wait for Apply. The color "
    "library is not deleted."
)
CLEAR_RECENT_TITLE = "Clear recent colors"
CLEAR_RECENT_TEXT = (
    "Clear recent colors now? Favorite colors, favorite palettes, and custom "
    "palettes are kept."
)
RESET_LIBRARY_TITLE = "Reset color library"
RESET_LIBRARY_TEXT = (
    "Reset the color library now? Recent colors, favorites, and custom palettes "
    "will be deleted. Built-in palettes remain."
)
RESET_COLOR_STORAGE_TITLE = "Reset color library storage"
RESET_COLOR_STORAGE_TEXT = (
    "Clear the color-library dual-slot document now and restore an empty writable "
    "library? Application preferences are not changed. This does not wait for Apply."
)
WRITE_UNCERTAIN_COLOR_HINT = (
    "Color library writes are disabled until storage health is Normal or Degraded."
)
FUTURE_COLOR_HINT = (
    "Color library storage is a future schema and is read-only. "
    "Clear and Reset are disabled."
)


class MaintenanceSettingsPage(QWidget):
    """Show dual-slot health and run draft or immediate recovery commands."""

    commandFinished = Signal(str, str)
    storageReset = Signal()

    def __init__(
        self,
        *,
        host: SettingsPageHost | None = None,
        service: ApplicationSettingsService | None = None,
        session: SettingsSession | None = None,
        backend: Any | None = None,
        color_library: ColorLibrary | None = None,
        application_health: HealthProvider | DocumentHealth | None = None,
        color_health: HealthProvider | DocumentHealth | None = None,
        confirm: ConfirmFn | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("maintenance_settings_page")
        self._host = host
        self._service = service
        self._session = session
        self._backend = backend
        self._color_library = color_library
        self._application_health = application_health
        self._color_health = color_health
        self._confirm = confirm

        root = QVBoxLayout(self)
        health_box = QGroupBox("Storage health", self)
        health_layout = QVBoxLayout(health_box)
        self.application_health_label = QLabel(health_box)
        self.application_health_label.setObjectName("application_health_label")
        self.application_health_label.setAccessibleName(
            "Application preferences health"
        )
        self.application_health_label.setWordWrap(True)
        self.color_health_label = QLabel(health_box)
        self.color_health_label.setObjectName("color_library_health_label")
        self.color_health_label.setAccessibleName("Color library health")
        self.color_health_label.setWordWrap(True)
        health_layout.addWidget(self.application_health_label)
        health_layout.addWidget(self.color_health_label)
        root.addWidget(health_box)

        prefs_box = QGroupBox("Application preferences", self)
        prefs_layout = QVBoxLayout(prefs_box)
        self.reset_all_button = QPushButton(
            "Reset all application preferences…",
            prefs_box,
        )
        self.reset_all_button.setObjectName("reset_all_preferences_button")
        self.reset_all_button.setAccessibleName("Reset all application preferences")
        self.reset_all_button.setAutoDefault(False)
        self.reset_all_button.setDefault(False)
        self.reset_all_button.clicked.connect(self.reset_all_preferences)
        self.reset_incompatible_button = QPushButton(
            "Reset incompatible storage now…",
            prefs_box,
        )
        self.reset_incompatible_button.setObjectName(
            "reset_incompatible_storage_button"
        )
        self.reset_incompatible_button.setAccessibleName(
            "Reset incompatible storage now"
        )
        self.reset_incompatible_button.setAutoDefault(False)
        self.reset_incompatible_button.setDefault(False)
        self.reset_incompatible_button.clicked.connect(
            self.reset_incompatible_storage
        )
        prefs_layout.addWidget(self.reset_all_button)
        prefs_layout.addWidget(self.reset_incompatible_button)
        root.addWidget(prefs_box)

        color_box = QGroupBox("Color library", self)
        color_layout = QVBoxLayout(color_box)
        self.color_counts_label = QLabel(color_box)
        self.color_counts_label.setObjectName("color_library_counts_label")
        self.color_counts_label.setAccessibleName("Color library counts")
        self.color_counts_label.setWordWrap(True)
        self.clear_recent_button = QPushButton("Clear recent colors…", color_box)
        self.clear_recent_button.setObjectName("clear_recent_colors_button")
        self.clear_recent_button.setAccessibleName("Clear recent colors")
        self.clear_recent_button.setAutoDefault(False)
        self.clear_recent_button.setDefault(False)
        self.clear_recent_button.clicked.connect(self.clear_recent_colors)
        self.reset_library_button = QPushButton("Reset color library…", color_box)
        self.reset_library_button.setObjectName("reset_color_library_button")
        self.reset_library_button.setAccessibleName("Reset color library")
        self.reset_library_button.setAutoDefault(False)
        self.reset_library_button.setDefault(False)
        self.reset_library_button.clicked.connect(self.reset_color_library)
        self.reset_color_storage_button = QPushButton(
            "Reset color library storage now…",
            color_box,
        )
        self.reset_color_storage_button.setObjectName(
            "reset_color_library_storage_button"
        )
        self.reset_color_storage_button.setAccessibleName(
            "Reset color library storage now"
        )
        self.reset_color_storage_button.setAutoDefault(False)
        self.reset_color_storage_button.setDefault(False)
        self.reset_color_storage_button.clicked.connect(
            self.reset_color_library_storage
        )
        self.color_diagnostics_label = QLabel(color_box)
        self.color_diagnostics_label.setObjectName("color_library_diagnostics_label")
        self.color_diagnostics_label.setAccessibleName("Color library diagnostics")
        self.color_diagnostics_label.setWordWrap(True)
        color_layout.addWidget(self.color_counts_label)
        color_layout.addWidget(self.color_diagnostics_label)
        color_layout.addWidget(self.clear_recent_button)
        color_layout.addWidget(self.reset_library_button)
        color_layout.addWidget(self.reset_color_storage_button)
        root.addWidget(color_box)
        root.addStretch(1)
        self.refresh()
        if host is not None:
            host.bind_draft_reloaded(self.refresh)

    @staticmethod
    def page_spec():
        """Return the Maintenance ``SettingsCenterPageSpec``."""

        return maintenance_page_spec()

    def bind_session(self, session: SettingsSession | None) -> None:
        """Attach or detach the Settings Center draft session."""

        self._session = session

    def refresh(self) -> None:
        """Refresh health labels, command enablement, and color counts."""

        app_health = self._resolve_application_health()
        color_health = self._resolve_color_health()
        self.application_health_label.setText(
            f"Application preferences: {document_health_label(app_health)}"
        )
        self.color_health_label.setText(
            f"Color library: {document_health_label(color_health)}"
        )
        draft_ok = allows_draft_preference_reset(app_health)
        immediate = requires_immediate_storage_reset(app_health)
        can_draft = draft_ok and (self._service is not None or self._host is not None)
        self.reset_all_button.setEnabled(can_draft)
        self.reset_all_button.setVisible(not immediate)
        self.reset_incompatible_button.setEnabled(
            immediate and self._backend is not None
        )
        self.reset_incompatible_button.setVisible(immediate)
        self._refresh_color_counts()

    def reset_all_preferences(self) -> bool:
        """Stage built-in defaults. Color library is excluded. Apply commits."""

        if requires_immediate_storage_reset(self._resolve_application_health()):
            return False
        if self._host is not None:
            self._host.request_immediate_command(
                "reset_all_preferences",
                title=RESET_ALL_TITLE,
                text=RESET_ALL_TEXT,
                handler=self._host.reset_all_preferences,
            )
            return True
        if not self._ask(RESET_ALL_TITLE, RESET_ALL_TEXT):
            return False
        if self._service is not None:
            session = self._session
            if session is None:
                session = self._service.begin_session()
                self._session = session
            result = self._service.reset_all_preferences(session)
            if not result.success:
                self._emit(
                    result.error or "Application preferences could not be staged.",
                    "error",
                )
                return False
        else:
            return False
        self._emit(
            "Application preference defaults are staged. Choose Apply to save. "
            "The color library was not changed.",
            "info",
        )
        return True

    def reset_incompatible_storage(self) -> bool:
        """Immediate dual-slot recovery. Not an Apply draft."""

        if self._backend is None:
            return False
        if not requires_immediate_storage_reset(self._resolve_application_health()):
            return False
        if self._host is not None:
            self._host.request_immediate_command(
                "reset_incompatible_storage",
                title=IMMEDIATE_RESET_TITLE,
                text=IMMEDIATE_RESET_TEXT,
                handler=self._run_incompatible_reset,
            )
            return True
        if not self._ask(IMMEDIATE_RESET_TITLE, IMMEDIATE_RESET_TEXT):
            return False
        return self._run_incompatible_reset()

    def clear_recent_colors(self) -> bool:
        """Immediate confirmed command. Does not ride the Apply patch."""

        if self._color_library is None:
            return False
        if not self._color_library_writable():
            self._emit(WRITE_UNCERTAIN_COLOR_HINT, "error")
            return False
        if self._host is not None:
            self._host.request_immediate_command(
                "clear_recent_colors",
                title=CLEAR_RECENT_TITLE,
                text=CLEAR_RECENT_TEXT,
                handler=self._run_clear_recent,
            )
            return True
        if not self._ask(CLEAR_RECENT_TITLE, CLEAR_RECENT_TEXT):
            return False
        return self._run_clear_recent()

    def reset_color_library(self) -> bool:
        """Immediate confirmed command. Does not ride the Apply patch."""

        if self._color_library is None:
            return False
        if not self._color_library_writable():
            self._emit(WRITE_UNCERTAIN_COLOR_HINT, "error")
            return False
        if self._host is not None:
            self._host.request_immediate_command(
                "reset_color_library",
                title=RESET_LIBRARY_TITLE,
                text=RESET_LIBRARY_TEXT,
                handler=self._run_reset_library,
            )
            return True
        if not self._ask(RESET_LIBRARY_TITLE, RESET_LIBRARY_TEXT):
            return False
        return self._run_reset_library()

    def _run_incompatible_reset(self) -> bool:
        reset = getattr(self._backend, "reset_incompatible_documents", None)
        if not callable(reset):
            self._emit("Incompatible storage reset is not available.", "error")
            return False
        stored: StorageCommitResult | Any = reset()
        ok = bool(getattr(stored, "ok", None) or getattr(stored, "success", False))
        if not ok:
            self._emit(
                getattr(stored, "error", None)
                or "Incompatible storage could not be reset.",
                "error",
            )
            self.refresh()
            return False
        if self._service is not None:
            self._service.reload()
        apply = getattr(self._host, "apply_storage_reset", None)
        if callable(apply):
            apply()
        elif self._session is not None:
            self._session._clear_dirty()
            if self._service is not None:
                self._session.base_revision = self._service.snapshot().revision
        self.refresh()
        self.storageReset.emit()
        self._emit(
            "Application settings storage was reset and is writable again.",
            "success",
        )
        return True

    def _run_clear_recent(self) -> bool:
        library = self._color_library
        if library is None:
            return False
        if not library.clear_recent_colors():
            self._emit("Recent colors could not be cleared.", "error")
            return False
        self._refresh_color_counts()
        self._emit("Recent colors cleared.", "success")
        return True

    def _run_reset_library(self) -> bool:
        library = self._color_library
        if library is None:
            return False
        if not library.reset_library():
            self._emit("Color library could not be reset.", "error")
            return False
        self._refresh_color_counts()
        self._emit("Color library reset.", "success")
        return True

    def reset_color_library_storage(self) -> bool:
        """Immediate confirmed clear of the color dual-slot document."""

        if self._backend is None:
            return False
        if self._host is not None:
            self._host.request_immediate_command(
                "reset_color_library_storage",
                title=RESET_COLOR_STORAGE_TITLE,
                text=RESET_COLOR_STORAGE_TEXT,
                handler=self._run_reset_color_storage,
            )
            return True
        if not self._ask(RESET_COLOR_STORAGE_TITLE, RESET_COLOR_STORAGE_TEXT):
            return False
        return self._run_reset_color_storage()

    def _run_reset_color_storage(self) -> bool:
        reset = getattr(self._backend, "reset_color_library_document", None)
        if not callable(reset):
            self._emit("Color library storage reset is not available.", "error")
            return False
        stored: StorageCommitResult | Any = reset()
        ok = bool(getattr(stored, "ok", None) or getattr(stored, "success", False))
        if not ok:
            self._emit(
                getattr(stored, "error", None)
                or "Color library storage could not be reset.",
                "error",
            )
            self._refresh_color_counts()
            return False
        library = self._color_library
        if library is not None and hasattr(library, "reload"):
            library.reload()
        self._refresh_color_counts()
        self._emit("Color library storage was reset and is writable again.", "success")
        return True

    def _refresh_color_counts(self) -> None:
        library = self._color_library
        color_health = self._resolve_color_health()
        writable = color_health in {
            DocumentHealth.NORMAL,
            DocumentHealth.DEGRADED,
        }
        recovery = color_health is DocumentHealth.RECOVERY_REQUIRED
        future = color_health is DocumentHealth.READ_ONLY_FUTURE
        uncertain = color_health is DocumentHealth.WRITE_UNCERTAIN
        storage_button = getattr(self, "reset_color_storage_button", None)
        diagnostics = getattr(self, "color_diagnostics_label", None)
        if library is None:
            self.color_counts_label.setText("Color library is not available.")
            self.clear_recent_button.setEnabled(False)
            self.reset_library_button.setEnabled(False)
            if storage_button is not None:
                storage_button.setEnabled(False)
                storage_button.setVisible(False)
            if diagnostics is not None:
                diagnostics.setText("")
            return
        applied = True
        payload_applied = getattr(library, "payload_applied", None)
        if callable(payload_applied):
            applied = bool(payload_applied())
        if applied:
            counts = library.counts()
            self.color_counts_label.setText(
                f"Recent colors: {counts.recent_colors}  ·  "
                f"Favorite colors: {counts.favorite_colors}  ·  "
                f"Favorite palettes: {counts.favorite_palettes}  ·  "
                f"Custom palettes: {counts.custom_palettes}"
            )
        else:
            self.color_counts_label.setText(
                "Color library data was not loaded from storage."
            )
        notes = []
        lib_notes = getattr(library, "diagnostics", None)
        if callable(lib_notes):
            notes = [str(item) for item in lib_notes() if item]
        if future:
            notes.append(FUTURE_COLOR_HINT)
        elif uncertain:
            notes.append(WRITE_UNCERTAIN_COLOR_HINT)
        elif recovery:
            notes.append(
                "Recovery required. Use Reset color library storage now… to "
                "clear the color dual-slot. Disk data is not shown as empty."
            )
        if diagnostics is not None:
            diagnostics.setText(" ".join(notes))
            diagnostics.setVisible(bool(notes))
        self.clear_recent_button.setEnabled(writable)
        self.reset_library_button.setEnabled(writable)
        if storage_button is not None:
            storage_button.setVisible(recovery)
            storage_button.setEnabled(recovery and self._backend is not None)

    def _resolve_application_health(self) -> DocumentHealth:
        provided = self._application_health
        if isinstance(provided, DocumentHealth):
            return provided
        if callable(provided):
            return provided()
        backend = self._backend
        if backend is not None:
            return backend.application_settings_port().load().health
        return DocumentHealth.NORMAL

    def _resolve_color_health(self) -> DocumentHealth:
        provided = self._color_health
        if isinstance(provided, DocumentHealth):
            return provided
        if callable(provided):
            return provided()
        library = self._color_library
        if library is not None:
            health_fn = getattr(library, "document_health", None)
            if callable(health_fn):
                return health_fn()
        backend = self._backend
        if backend is not None:
            return backend.color_library_settings_port().load().health
        return DocumentHealth.NORMAL

    def _color_library_writable(self) -> bool:
        return self._resolve_color_health() in {
            DocumentHealth.NORMAL,
            DocumentHealth.DEGRADED,
        }

    def _emit(self, text: str, level: str) -> None:
        if self._host is not None:
            self._host.emit_message(text, level)
        self.commandFinished.emit(text, level)

    def _ask(self, title: str, text: str) -> bool:
        if self._confirm is not None:
            return bool(self._confirm(title, text))
        answer = QMessageBox.question(
            self,
            title,
            text,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        return answer == QMessageBox.StandardButton.Yes
