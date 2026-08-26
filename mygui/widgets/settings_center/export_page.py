"""Settings Center Export page. Reuses FigureExportOptionsPanel."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from mygui.application_settings.document import (
    export_settings_to_patch,
    snapshot_from_values,
)
from mygui.application_settings.keys import KEYS_BY_PAGE, PAGE_EXPORT
from mygui.application_settings.models import ExportSettings
from mygui.application_settings.registry import production_settings_registry
from mygui.application_settings.session import SettingsSession
from mygui.widgets.common_widget.min_widget.color_library import ColorLibrary
from mygui.widgets.settings_center.pages import SettingsPageHost
from mygui.widgets.settings_center.specs import export_page_spec
from mygui.widgets.title_bar.titlebar_dialog.figure_export_options_panel import (
    FigureExportOptionsPanel,
)

EXPORT_DPI_STRATEGY_HINT = (
    "Use project DPI stores a strategy only. Custom DPI is stored separately "
    "and is kept when the strategy is selected. A live export binds the current "
    "project's document DPI. Each export window can still override these "
    "defaults for that one export."
)


class ExportSettingsPage(QWidget):
    """Edit default ``ExportSettings`` without Figure Controller state."""

    def __init__(
        self,
        color_library: ColorLibrary,
        *,
        host: SettingsPageHost | None = None,
        session: SettingsSession | None = None,
        export: ExportSettings | None = None,
        document_dpi: float = 100.0,
        width_inches: float = 6.4,
        height_inches: float = 4.8,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        if color_library is None:
            raise ValueError("ExportSettingsPage requires the shared ColorLibrary.")
        self.setObjectName("export_settings_page")
        self._host = host
        self._session = session
        self._staging = False
        self._last_host_patch: dict[str, Any] | None = None

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        self.dpi_strategy_hint = QLabel(EXPORT_DPI_STRATEGY_HINT, self)
        self.dpi_strategy_hint.setObjectName("export_settings_dpi_hint")
        self.dpi_strategy_hint.setWordWrap(True)
        root.addWidget(self.dpi_strategy_hint)

        self.panel = FigureExportOptionsPanel(
            color_library,
            document_dpi=document_dpi,
            width_inches=width_inches,
            height_inches=height_inches,
            include_format_row=True,
            show_size_preview=False,
            persist_color_library=False,
            show_project_dpi_value=False,
            parent=self,
        )
        self.panel.setObjectName("export_settings_options_panel")
        root.addWidget(self.panel, 1)

        if export is not None:
            self.panel.set_export_settings(export)
        elif host is not None:
            self._reload_from_host()
        self.panel.valuesChanged.connect(self._stage_from_panel)
        if host is not None:
            host.bind_draft_reloaded(self._reload_from_host)

    @staticmethod
    def page_spec():
        """Return the Export ``SettingsCenterPageSpec``."""

        return export_page_spec()

    def bind_session(self, session: SettingsSession | None) -> None:
        """Attach or detach a draft session when the shell host is absent."""

        self._session = session

    def set_export_settings(self, settings: ExportSettings) -> None:
        """Load ``ExportSettings`` without staging a draft."""

        blocked = self._staging
        self._staging = True
        try:
            self.panel.set_export_settings(settings)
            self._last_host_patch = self.collect_patch()
        finally:
            self._staging = blocked

    def export_settings(self) -> ExportSettings:
        """Return the current panel values as ``ExportSettings``."""

        return self.panel.export_settings()

    def collect_patch(self) -> dict[str, Any]:
        """Return the persisted export-key patch for Apply/OK."""

        return export_settings_to_patch(self.export_settings())

    def stage_into_session(
        self,
        session: SettingsSession | None = None,
    ) -> Mapping[str, Any]:
        """Write the current export values into the session or shell host."""

        patch = self.collect_patch()
        self._last_host_patch = dict(patch)
        self._apply_patch(patch)
        target = self._session if session is None else session
        if self._host is None and target is not None:
            target.stage_many(patch)
        return patch

    def _stage_from_panel(self) -> None:
        if self._staging:
            return
        patch = self.collect_patch()
        if patch == self._last_host_patch:
            return
        self._last_host_patch = dict(patch)
        self._apply_patch(patch)
        if self._host is None and self._session is not None:
            self._session.stage_many(patch)

    def _apply_patch(self, patch: Mapping[str, Any]) -> None:
        host = self._host
        if host is None:
            return
        stage_values = getattr(host, "stage_values", None)
        if callable(stage_values):
            stage_values(patch)
            return
        for key, value in patch.items():
            host.stage_value(key, value)

    def _reload_from_host(self, values: Mapping[str, Any] | None = None) -> None:
        host = self._host
        if host is None:
            return
        self.set_export_settings(_export_from_host(host, values))


def _export_from_host(
    host: SettingsPageHost,
    values: Mapping[str, Any] | None = None,
) -> ExportSettings:
    registry = production_settings_registry()
    merged = dict(registry.defaults())
    keys = KEYS_BY_PAGE[PAGE_EXPORT]
    if values is None:
        draft_values = getattr(host, "draft_values", None)
        if callable(draft_values):
            try:
                merged.update(dict(draft_values(keys)))
            except TypeError:
                for key in keys:
                    merged[key] = host.draft_value(key)
        else:
            for key in keys:
                merged[key] = host.draft_value(key)
    else:
        for key in keys:
            if key in values:
                merged[key] = values[key]
    return snapshot_from_values(merged, revision=0).export
