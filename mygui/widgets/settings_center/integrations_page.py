"""Read-only Integrations page. Opens existing TeX/MATLAB panels by signal."""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QFormLayout,
    QGroupBox,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from mygui.widgets.settings_center.integrations_status import (
    IntegrationStatus,
    matlab_integration_status,
    tex_integration_status,
)
from mygui.widgets.settings_center.pages import SettingsPageHost
from mygui.widgets.settings_center.specs import integrations_page_spec
from mygui.widgets.ui_components import UiTextRole, UiVariant, apply_text_style, style_button

TexStatusProvider = Callable[[], IntegrationStatus]
MatlabStatusProvider = Callable[[], IntegrationStatus]


class IntegrationsSettingsPage(QWidget):
    """Show TeX/MATLAB status and request the existing right-rail panels.

    This page never remounts the right-rail TeX or MATLAB widgets, never starts
    either runtime, and never persists enablement, preamble, or connection.
    MainWindow must connect ``openTexPanelRequested`` and
    ``openMatlabPanelRequested``.
    """

    openTexPanelRequested = Signal()
    openMatlabPanelRequested = Signal()

    def __init__(
        self,
        *,
        host: SettingsPageHost | None = None,
        tex_status: TexStatusProvider | IntegrationStatus | None = None,
        matlab_status: MatlabStatusProvider | IntegrationStatus | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("integrations_settings_page")
        self._host = host
        self._tex_status = tex_status
        self._matlab_status = matlab_status

        root = QVBoxLayout(self)
        intro = QLabel(
            "TeX and MATLAB are optional session integrations. Availability "
            "here is read-only. Use the buttons to open the existing right-hand "
            "panels. This page does not start either runtime and does not save "
            "TeX enablement, preamble, or MATLAB connection as application "
            "settings.",
            self,
        )
        intro.setObjectName("integrations_intro")
        intro.setWordWrap(True)
        apply_text_style(intro, UiTextRole.BODY)
        root.addWidget(intro)

        self.tex_group = self._build_tex_group()
        self.matlab_group = self._build_matlab_group()
        root.addWidget(self.tex_group)
        root.addWidget(self.matlab_group)
        root.addStretch(1)
        self.refresh_status()
        if host is not None:
            host.bind_draft_reloaded(self.refresh_status)

    @staticmethod
    def page_spec():
        """Return the Integrations ``SettingsCenterPageSpec``."""

        return integrations_page_spec()

    def refresh_status(self, *_args: object) -> None:
        """Refresh the read-only TeX and MATLAB summaries."""

        tex = self._resolve_status(self._tex_status, tex_integration_status)
        matlab = self._resolve_status(self._matlab_status, matlab_integration_status)
        self._apply_tex(tex)
        self._apply_matlab(matlab)

    def _build_tex_group(self) -> QGroupBox:
        group = QGroupBox("TeX", self)
        form = QFormLayout(group)
        self.tex_availability = QLabel(group)
        self.tex_availability.setObjectName("tex_availability_label")
        self.tex_availability.setAccessibleName("TeX availability")
        self.tex_session = QLabel(group)
        self.tex_session.setObjectName("tex_session_label")
        self.tex_session.setAccessibleName("TeX session")
        self.tex_diagnostics = QLabel(group)
        self.tex_diagnostics.setObjectName("tex_diagnostics_label")
        self.tex_diagnostics.setAccessibleName("TeX diagnostics")
        self.tex_diagnostics.setWordWrap(True)
        self.open_tex_panel_button = QPushButton("Open TeX panel…", group)
        self.open_tex_panel_button.setObjectName("open_tex_panel_button")
        self.open_tex_panel_button.setAccessibleName("Open TeX panel")
        self.open_tex_panel_button.setAutoDefault(False)
        self.open_tex_panel_button.setDefault(False)
        style_button(self.open_tex_panel_button, variant=UiVariant.OUTLINE)
        self.open_tex_panel_button.clicked.connect(self.openTexPanelRequested.emit)
        form.addRow("Availability", self.tex_availability)
        form.addRow("Session", self.tex_session)
        form.addRow("Diagnostics", self.tex_diagnostics)
        form.addRow(self.open_tex_panel_button)
        return group

    def _build_matlab_group(self) -> QGroupBox:
        group = QGroupBox("MATLAB", self)
        form = QFormLayout(group)
        self.matlab_availability = QLabel(group)
        self.matlab_availability.setObjectName("matlab_availability_label")
        self.matlab_availability.setAccessibleName("MATLAB availability")
        self.matlab_session = QLabel(group)
        self.matlab_session.setObjectName("matlab_session_label")
        self.matlab_session.setAccessibleName("MATLAB session")
        self.matlab_diagnostics = QLabel(group)
        self.matlab_diagnostics.setObjectName("matlab_diagnostics_label")
        self.matlab_diagnostics.setAccessibleName("MATLAB diagnostics")
        self.matlab_diagnostics.setWordWrap(True)
        self.open_matlab_panel_button = QPushButton("Open MATLAB panel…", group)
        self.open_matlab_panel_button.setObjectName("open_matlab_panel_button")
        self.open_matlab_panel_button.setAccessibleName("Open MATLAB panel")
        self.open_matlab_panel_button.setAutoDefault(False)
        self.open_matlab_panel_button.setDefault(False)
        style_button(self.open_matlab_panel_button, variant=UiVariant.OUTLINE)
        self.open_matlab_panel_button.clicked.connect(
            self.openMatlabPanelRequested.emit
        )
        form.addRow("Availability", self.matlab_availability)
        form.addRow("Session", self.matlab_session)
        form.addRow("Diagnostics", self.matlab_diagnostics)
        form.addRow(self.open_matlab_panel_button)
        return group

    def _apply_tex(self, status: IntegrationStatus) -> None:
        self.tex_availability.setText(
            "Available" if status.available else "Unavailable"
        )
        self.tex_session.setText(status.session_state)
        self.tex_diagnostics.setText(status.diagnostic_summary)

    def _apply_matlab(self, status: IntegrationStatus) -> None:
        self.matlab_availability.setText(
            "Available" if status.available else "Unavailable"
        )
        self.matlab_session.setText(status.session_state)
        self.matlab_diagnostics.setText(status.diagnostic_summary)

    @staticmethod
    def _resolve_status(
        provided: TexStatusProvider | IntegrationStatus | None,
        fallback: Callable[[], IntegrationStatus],
    ) -> IntegrationStatus:
        if provided is None:
            return fallback()
        if isinstance(provided, IntegrationStatus):
            return provided
        return provided()
