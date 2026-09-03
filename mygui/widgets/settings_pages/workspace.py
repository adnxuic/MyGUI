"""Workspace settings page. Remember is a draft; reset is an immediate command."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QFormLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from mygui.application_settings.keys import (
    PAGE_WORKSPACE,
    WORKSPACE_REMEMBER_LAYOUT,
)
from mygui.application_settings.models import DEFAULT_WORKSPACE_LAYOUT

from .page import (
    SettingsPageWidget,
    make_hint_label,
    make_intro_label,
)
from mygui.widgets.ui_components import UiRole, UiVariant, apply_ui_style, ask_confirmation

WORKSPACE_INTRO = (
    "Remember workspace layout saves splitter sizes, Explorer mode, and "
    "Explorer visibility when MyGUI closes."
)
WORKSPACE_HINT = (
    "Turn this off to keep the stored layout unchanged on exit. "
    "Reset workspace layout now applies the default layout immediately. "
    "It is not part of Apply."
)
RESET_BUTTON_TEXT = "Reset workspace layout now…"
RESET_DIALOG_TITLE = "Reset workspace layout"
RESET_DIALOG_TEXT = (
    "Reset splitter sizes, Explorer mode, and Explorer visibility to the "
    "default layout now?\n\n"
    "This command applies immediately. It is not part of Apply."
)


class WorkspaceSettingsPage(SettingsPageWidget):
    """Remember-layout draft plus a confirmed immediate reset command."""

    PAGE_ID = PAGE_WORKSPACE

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        session: Any | None = None,
        registry: Any | None = None,
        reset_layout_now: Callable[[], Any] | None = None,
        layout_port: Any | None = None,
        host: Any | None = None,
    ) -> None:
        super().__init__(parent, session=session, registry=registry, host=host)
        self._reset_layout_now = reset_layout_now
        self._layout_port = layout_port

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        if host is None:
            root.addWidget(make_intro_label(WORKSPACE_INTRO, self))

        form = QFormLayout()
        remember_spec = self._registry.spec(WORKSPACE_REMEMBER_LAYOUT)
        remember_label_text = remember_spec.label or "Remember workspace layout"
        self.remember_box = QCheckBox(remember_label_text, self)
        self.remember_box.setObjectName("workspace_remember_layout")
        self.remember_box.setAccessibleName(remember_label_text)
        self.remember_box.setChecked(bool(remember_spec.default))
        self.remember_box.setFocusPolicy(Qt.StrongFocus)
        apply_ui_style(self.remember_box, role=UiRole.CHECKBOX)
        remember_label = QLabel(remember_label_text, self)
        remember_label.setObjectName("settings_page_field_label")
        remember_label.setBuddy(self.remember_box)
        remember_label.hide()
        self._buddy_labels[WORKSPACE_REMEMBER_LAYOUT] = remember_label
        form.addRow(self.remember_box)
        root.addLayout(form)
        root.addWidget(make_hint_label(WORKSPACE_HINT, self))

        self.reset_button = QPushButton(RESET_BUTTON_TEXT, self)
        self.reset_button.setObjectName("workspace_reset_layout_now")
        self.reset_button.setAccessibleName(RESET_BUTTON_TEXT)
        self.reset_button.setAutoDefault(False)
        self.reset_button.setDefault(False)
        self.reset_button.setFocusPolicy(Qt.StrongFocus)
        apply_ui_style(
            self.reset_button,
            role=UiRole.BUTTON,
            variant=UiVariant.OUTLINE,
        )
        self.reset_button.clicked.connect(self.reset_workspace_layout_now)
        root.addWidget(self.reset_button, alignment=Qt.AlignLeft)
        root.addStretch(1)

        QWidget.setTabOrder(self.remember_box, self.reset_button)
        self.remember_box.toggled.connect(self._on_remember_changed)
        self.bind_host(host)
        self.load_values(self._initial_values())
        self.set_storage_writable(self._host_storage_writable())

    @classmethod
    def page_spec(cls):
        return page_spec(cls.make_factory())

    @classmethod
    def make_factory(
        cls,
        reset_layout_now: Callable[[], Any] | None = None,
        layout_port: Any | None = None,
    ):
        def factory(host: Any) -> WorkspaceSettingsPage:
            return cls(
                host=host,
                reset_layout_now=reset_layout_now,
                layout_port=layout_port,
            )

        return factory

    def bind_reset_layout_now(self, callback: Callable[[], Any] | None) -> None:
        """Inject the MainWindow immediate-reset command. Not an Apply draft."""

        self._reset_layout_now = callback

    def bind_layout_port(self, port: Any | None) -> None:
        self._layout_port = port

    def editors(self) -> dict[str, QWidget]:
        return {WORKSPACE_REMEMBER_LAYOUT: self.remember_box}

    def set_storage_writable(self, writable: bool) -> None:
        """Disable remember/reset when dual-slot storage cannot commit."""

        enabled = bool(writable)
        self.remember_box.setEnabled(enabled)
        self.reset_button.setEnabled(enabled)

    def keyboard_editors(self) -> tuple[QWidget, ...]:
        return (self.remember_box, self.reset_button)

    def draft_values(self) -> dict[str, Any]:
        return {WORKSPACE_REMEMBER_LAYOUT: bool(self.remember_box.isChecked())}

    def load_values(
        self,
        values: Mapping[str, Any],
        *,
        preview: bool = False,
    ) -> None:
        self._loading = True
        try:
            if WORKSPACE_REMEMBER_LAYOUT in values:
                remember = self._registry.spec(WORKSPACE_REMEMBER_LAYOUT).normalize(
                    values[WORKSPACE_REMEMBER_LAYOUT]
                )
                self.remember_box.setChecked(bool(remember))
        finally:
            self._loading = False
        if preview:
            self._on_remember_changed()

    def reset_workspace_layout_now(self) -> bool:
        """Confirm, then reset layout immediately. Does not stage Apply keys."""

        if self._host is not None:
            request = getattr(self._host, "request_immediate_command", None)
            if callable(request):
                request(
                    "workspace.reset_layout_now",
                    title=RESET_DIALOG_TITLE,
                    text=RESET_DIALOG_TEXT,
                    handler=self._execute_reset,
                    confirm=True,
                )
                return True
        if not self._confirm_reset():
            return False
        return self._execute_reset()

    def _execute_reset(self) -> bool:
        if self._reset_layout_now is not None:
            result = self._reset_layout_now()
            return result is not False
        if self._layout_port is not None:
            result = self._layout_port.save_layout(DEFAULT_WORKSPACE_LAYOUT)
            ok = getattr(result, "success", None)
            if ok is None:
                ok = getattr(result, "ok", True)
            return bool(ok)
        return False

    def _confirm_reset(self) -> bool:
        return ask_confirmation(
            self,
            RESET_DIALOG_TITLE,
            RESET_DIALOG_TEXT,
            destructive=True,
        )

    def _host_storage_writable(self) -> bool:
        host = self._host
        if host is None:
            return True
        glue = getattr(host, "glue", None)
        is_writable = getattr(glue, "is_writable", None)
        if callable(is_writable):
            return bool(is_writable())
        return True

    def _on_remember_changed(self, *_args: object) -> None:
        if self._loading or self._staging or not self.remember_box.isEnabled():
            return
        self._stage_and_emit(self.draft_values())


def make_workspace_factory(
    reset_layout_now: Callable[[], Any] | None = None,
    layout_port: Any | None = None,
):
    return WorkspaceSettingsPage.make_factory(
        reset_layout_now=reset_layout_now,
        layout_port=layout_port,
    )


def page_spec(factory=None):
    """Shell registration spec for the Workspace page."""

    from mygui.widgets.settings_center.pages import standard_page_spec

    return standard_page_spec(
        PAGE_WORKSPACE,
        factory if factory is not None else make_workspace_factory(),
        description=WORKSPACE_INTRO,
        keywords=(RESET_BUTTON_TEXT, "reset"),
    )
