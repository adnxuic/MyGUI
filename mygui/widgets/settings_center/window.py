"""Cached modal Settings Center window: navigation, search, draft, footer."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from types import MappingProxyType
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from mygui.application_settings.errors import SettingsValidationError
from mygui.application_settings.keys import PAGE_WORKSPACE
from mygui.application_settings.registry import SettingsRegistry, production_settings_registry
from mygui.application_settings.service import ApplicationSettingsService
from mygui.application_theme import bind_widget_qss, subscribe_theme_window
from mygui.application_theme.binder import apply_committed_appearance
from mygui.application_theme.errors import ThemeApplyError, ThemeRollbackError
from mygui.application_theme.service import ThemeService
from mygui.resources import icon_path

from .geometry import (
    INITIAL_HEIGHT,
    INITIAL_WIDTH,
    MINIMUM_HEIGHT,
    MINIMUM_WIDTH,
    NAV_PANE_WIDTH,
    SCREEN_FRACTION,
    AvailableGeometryProvider,
    constrain_to_available,
    current_available_geometry,
)
from .pages import (
    SettingsCenterPageSpec,
    SettingsPageRegistry,
    empty_page_factory,
    page_matches,
    persisted_page_ids,
)
from .session_glue import MessageCallback, SettingsCenterSession

SETTINGS_CENTER_QSS_RESOURCE = "mygui/widgets/settings_center/style.qss"
READ_ONLY_STATUS = (
    "Settings storage is read-only. Open Maintenance to reset incompatible storage."
)

ImmediateConfirm = Callable[[str, str], bool]


class SettingsCenterWindow(QDialog):
    """Resizable modal Settings Center. Lazy page widgets; one cached instance."""

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        settings_service: ApplicationSettingsService,
        theme_service: ThemeService,
        page_registry: SettingsPageRegistry | None = None,
        settings_registry: SettingsRegistry | None = None,
        on_message: MessageCallback | None = None,
        available_geometry: AvailableGeometryProvider | None = None,
        confirm_immediate: ImmediateConfirm | None = None,
    ) -> None:
        super().__init__(parent)
        self._pages = page_registry if page_registry is not None else SettingsPageRegistry()
        self._settings_registry = settings_registry or production_settings_registry()
        self._on_message = on_message
        self._geometry_provider = available_geometry
        self._confirm_immediate = confirm_immediate
        self._theme_service = theme_service
        self._glue = SettingsCenterSession(
            settings_service,
            theme_service,
            registry=self._settings_registry,
        )
        self._page_widgets: dict[str, QWidget] = {}
        self._page_scrolls: dict[str, QScrollArea] = {}
        self._reload_hooks: dict[str, list[Callable[[Mapping[str, Any]], None]]] = {}
        self._building_page_id: str | None = None
        self._current_page_id: str | None = None
        self._message_emitted = False
        self._syncing_nav = False
        self._session_closed = True

        self.setObjectName("setting_dialog")
        self.setWindowTitle("Settings")
        self.setWindowIcon(QIcon(icon_path("setting.svg")))
        self.setProperty("themeChromeWindowIcon", icon_path("setting.svg"))
        self.setModal(True)
        self.setWindowModality(Qt.ApplicationModal)
        self.setSizeGripEnabled(True)
        self.resize(INITIAL_WIDTH, INITIAL_HEIGHT)
        self.setMinimumSize(MINIMUM_WIDTH, MINIMUM_HEIGHT)

        bind_widget_qss(self, SETTINGS_CENTER_QSS_RESOURCE)
        self._build_chrome()
        self._connect_chrome()
        subscribe_theme_window(self)
        self._rebuild_nav()

    @property
    def search_edit(self) -> QLineEdit:
        return self._search

    @property
    def nav_list(self) -> QListWidget:
        return self._nav

    @property
    def restore_defaults_button(self) -> QPushButton:
        return self._restore_button

    @property
    def cancel_button(self) -> QPushButton:
        return self._cancel_button

    @property
    def apply_button(self) -> QPushButton:
        return self._apply_button

    @property
    def ok_button(self) -> QPushButton:
        return self._ok_button

    @property
    def status_label(self) -> QLabel:
        return self._status

    @property
    def glue(self) -> SettingsCenterSession:
        return self._glue

    @property
    def theme_service(self) -> ThemeService:
        """ThemeService used for LIVE_REVERSIBLE Appearance preview."""

        return self._theme_service

    def created_page_ids(self) -> frozenset[str]:
        return frozenset(self._page_widgets)

    def prepare_session(self, page_id: str | None = None) -> None:
        """Begin a settings session if needed and reload created pages from draft."""

        self._session_closed = False
        started = self._glue.session is None
        if started:
            self._glue.start()
            self._search.blockSignals(True)
            self._search.clear()
            self._search.blockSignals(False)
            self._syncing_nav = True
            try:
                self._apply_search("", select=False)
            finally:
                self._syncing_nav = False
        values = MappingProxyType(self._glue.draft_values())
        self._reload_all_created_pages(values)
        target = page_id or self._current_page_id
        if target and target in self._pages:
            self._select_page(target, reload_created=False)
        else:
            self._select_first_visible(reload_created=False)
        self._update_footer()

    def on_pages_changed(self) -> None:
        """Rebuild navigation after ``register_page``. Existing widgets are kept."""

        self._rebuild_nav(prefer=self._current_page_id)
        if self._glue.is_active():
            self._update_footer()

    def apply_screen_geometry(self) -> None:
        """Center on the current screen and clamp to 90% of availableGeometry."""

        available = current_available_geometry(self, self._geometry_provider)
        geo = constrain_to_available(available)
        max_w = max(1, int(available.width() * SCREEN_FRACTION))
        max_h = max(1, int(available.height() * SCREEN_FRACTION))
        self.setMinimumWidth(min(MINIMUM_WIDTH, geo.width()))
        self.setMinimumHeight(min(MINIMUM_HEIGHT, geo.height()))
        self.setMaximumWidth(max_w)
        self.setMaximumHeight(max_h)
        self.setGeometry(geo)

    def draft_value(self, key: str) -> Any:
        return self._glue.draft_value(key)

    def draft_values(self, keys: Iterable[str] | None = None) -> Mapping[str, Any]:
        return self._glue.draft_values(keys)

    def stage_value(self, key: str, value: Any) -> None:
        self.stage_values({key: value})

    def stage_values(self, mapping: Mapping[str, Any]) -> None:
        self._begin_action()
        try:
            self._glue.stage_values(mapping)
        except SettingsValidationError as exc:
            self.emit_message(str(exc), "error")
            self._reload_all_created_pages()
            self._update_footer()
            return
        except (ThemeApplyError, ThemeRollbackError) as exc:
            self.emit_message(str(exc), "error")
            self._reload_all_created_pages()
            self._update_footer()
            return
        self._update_footer()

    def request_immediate_command(
        self,
        command_id: str,
        *,
        title: str,
        text: str,
        handler: Callable[[], None],
        confirm: bool = True,
    ) -> None:
        """Confirmed immediate command. Never merged into the Apply/OK patch."""

        self._begin_action()
        _ = command_id
        if confirm and not self.confirm_immediate_command(title, text):
            return
        try:
            handler()
        except Exception as exc:  # noqa: BLE001 — surface one Message Bar error
            self.emit_message(str(exc), "error")

    def reset_all_preferences(self) -> None:
        """Stage built-in defaults once and reload every created page from draft."""

        self._begin_action()
        try:
            result = self._glue.reset_all()
        except (ThemeApplyError, ThemeRollbackError) as exc:
            self.emit_message(str(exc), "error")
            self._reload_all_created_pages()
            self._update_footer()
            return
        if not result.success:
            self.emit_message(
                result.error or "Application preferences could not be staged.",
                "error",
            )
            self._update_footer()
            return
        self._reload_all_created_pages()
        self.emit_message(
            "Application preference defaults are staged. Choose Apply to save. "
            "The color library was not changed.",
            "info",
        )
        self._status.setText("Page defaults restored in the draft.")
        self._update_footer(status_already_set=True)

    def apply_storage_reset(self) -> None:
        """Re-apply committed appearance and reload every created page after storage reset."""

        apply_committed_appearance(
            self._theme_service,
            self._glue.service.snapshot(),
        )
        self._glue.start()
        self._reload_all_created_pages()
        self._update_footer()

    def confirm_immediate_command(self, title: str, text: str) -> bool:
        if self._confirm_immediate is not None:
            return bool(self._confirm_immediate(title, text))
        reply = QMessageBox.question(
            self,
            title,
            text,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        return reply == QMessageBox.StandardButton.Yes

    def emit_message(self, text: str, level: str = "info") -> None:
        """Forward one Message Bar result. Later calls in the same action are dropped."""

        if self._message_emitted:
            return
        message = str(text).strip()
        if not message:
            return
        self._message_emitted = True
        if self._on_message is not None:
            self._on_message(message, str(level))

    def bind_draft_reloaded(self, callback: Callable[[Mapping[str, Any]], None]) -> None:
        page_id = self._building_page_id or self._current_page_id
        if page_id is None:
            return
        self._reload_hooks.setdefault(page_id, []).append(callback)

    def showEvent(self, event) -> None:  # noqa: N802 — Qt
        super().showEvent(event)
        if event.spontaneous():
            return
        self.apply_screen_geometry()
        self._search.setFocus(Qt.OtherFocusReason)

    def closeEvent(self, event) -> None:  # noqa: N802 — Qt
        accepted = int(self.result()) == int(QDialog.Accepted)
        if not self._complete_session(accepted):
            event.ignore()
            return
        super().closeEvent(event)

    def done(self, result: int) -> None:  # noqa: N802 — Qt
        accepted = int(result) == int(QDialog.Accepted)
        if not self._complete_session(accepted):
            return
        super().done(result)

    def reject(self) -> None:
        super().reject()

    def accept(self) -> None:
        super().accept()

    def _complete_session(self, accepted: bool) -> bool:
        """Finish Accept/Reject/X/Esc once. Return False to keep the window open."""

        if self._session_closed:
            return True
        try:
            if accepted:
                self._glue.release()
            else:
                self._glue.abandon()
        except (ThemeApplyError, ThemeRollbackError) as exc:
            self._begin_action()
            self.emit_message(str(exc), "error")
            return False
        self._session_closed = True
        return True

    def keyPressEvent(self, event) -> None:  # noqa: N802 — Qt
        if event.key() == Qt.Key_Escape:
            self.reject()
            return
        if event.key() in (Qt.Key_Return, Qt.Key_Enter) and self._search.hasFocus():
            event.accept()
            return
        super().keyPressEvent(event)

    def _build_chrome(self) -> None:
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        nav_pane = QFrame()
        nav_pane.setObjectName("settings_nav_pane")
        nav_pane.setFixedWidth(NAV_PANE_WIDTH)
        nav_layout = QVBoxLayout(nav_pane)
        nav_layout.setContentsMargins(12, 12, 12, 12)
        nav_layout.setSpacing(8)

        self._search = QLineEdit()
        self._search.setObjectName("settings_search")
        self._search.setPlaceholderText("Search settings")
        self._search.setClearButtonEnabled(True)
        self._search.setAccessibleName("Search settings")
        nav_layout.addWidget(self._search)

        self._nav = QListWidget()
        self._nav.setObjectName("settings_nav")
        self._nav.setAccessibleName("Settings pages")
        self._nav.setSelectionMode(QAbstractItemView.SingleSelection)
        self._nav.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        nav_layout.addWidget(self._nav, 1)
        root.addWidget(nav_pane)

        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(16, 16, 16, 0)
        right_layout.setSpacing(8)

        self._title = QLabel()
        self._title.setObjectName("settings_page_title")
        self._description = QLabel()
        self._description.setObjectName("settings_page_description")
        self._description.setWordWrap(True)
        right_layout.addWidget(self._title)
        right_layout.addWidget(self._description)

        self._stack = QStackedWidget()
        self._stack.setObjectName("settings_page_stack")
        right_layout.addWidget(self._stack, 1)

        footer = QFrame()
        footer.setObjectName("settings_footer")
        footer_layout = QHBoxLayout(footer)
        footer_layout.setContentsMargins(16, 10, 16, 12)
        footer_layout.setSpacing(8)

        self._restore_button = QPushButton("Restore page defaults")
        self._restore_button.setObjectName("settings_restore_defaults")
        self._restore_button.setAccessibleName("Restore page defaults")
        self._restore_button.setAutoDefault(False)
        footer_layout.addWidget(self._restore_button)

        self._status = QLabel()
        self._status.setObjectName("settings_status")
        self._status.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        footer_layout.addWidget(self._status, 1)

        self._cancel_button = QPushButton("Cancel")
        self._cancel_button.setObjectName("settings_cancel")
        self._cancel_button.setAccessibleName("Cancel")
        self._cancel_button.setAutoDefault(False)
        self._apply_button = QPushButton("Apply")
        self._apply_button.setObjectName("settings_apply")
        self._apply_button.setAccessibleName("Apply")
        self._apply_button.setAutoDefault(False)
        self._ok_button = QPushButton("OK")
        self._ok_button.setObjectName("settings_ok")
        self._ok_button.setAccessibleName("OK")
        self._ok_button.setDefault(False)
        self._ok_button.setAutoDefault(False)
        footer_layout.addWidget(self._cancel_button)
        footer_layout.addWidget(self._apply_button)
        footer_layout.addWidget(self._ok_button)
        right_layout.addWidget(footer)
        root.addWidget(right, 1)

        self._relink_tab_order(None)

    def _connect_chrome(self) -> None:
        self._search.textChanged.connect(self._apply_search)
        self._search.returnPressed.connect(self._on_search_return)
        self._nav.currentItemChanged.connect(self._on_nav_item_changed)
        self._restore_button.clicked.connect(self._on_restore_defaults)
        self._cancel_button.clicked.connect(self.reject)
        self._apply_button.clicked.connect(self._on_apply)
        self._ok_button.clicked.connect(self._on_ok)

    def _rebuild_nav(self, *, prefer: str | None = None) -> None:
        self._syncing_nav = True
        self._nav.blockSignals(True)
        self._nav.clear()
        for spec in self._pages.pages():
            item = QListWidgetItem(spec.title)
            item.setData(Qt.UserRole, spec.page_id)
            item.setToolTip(spec.description)
            self._nav.addItem(item)
        self._nav.blockSignals(False)
        self._syncing_nav = False
        self._apply_search(self._search.text(), select=False)
        if prefer and prefer in self._pages:
            self._select_page(prefer)

    def _apply_search(self, text: str, *, select: bool = True) -> None:
        query = str(text)
        first_visible: QListWidgetItem | None = None
        was_syncing = self._syncing_nav
        self._syncing_nav = True
        try:
            for index in range(self._nav.count()):
                item = self._nav.item(index)
                page_id = item.data(Qt.UserRole)
                spec = self._pages.get(page_id)
                visible = page_matches(spec, query, self._settings_registry)
                item.setHidden(not visible)
                if visible and first_visible is None:
                    first_visible = item
            current = self._nav.currentItem()
        finally:
            self._syncing_nav = was_syncing
        if first_visible is None:
            self._show_empty_filter()
            return
        self._stack.setVisible(True)
        if not select:
            return
        if current is None or current.isHidden():
            self._nav.setCurrentItem(first_visible)

    def _show_empty_filter(self) -> None:
        self._current_page_id = None
        self._title.setText("No matching settings")
        self._description.setText("Try a different search term.")
        self._restore_button.setEnabled(False)
        self._stack.setVisible(False)
        current = self._stack.currentWidget()
        if current is not None:
            current.setEnabled(False)

    def _on_search_return(self) -> None:
        """Swallow Enter in the search box so it cannot activate OK."""

        return

    def _on_nav_item_changed(
        self,
        current: QListWidgetItem | None,
        _previous: QListWidgetItem | None,
    ) -> None:
        if self._syncing_nav or current is None:
            return
        page_id = current.data(Qt.UserRole)
        if page_id:
            self._select_page(str(page_id))

    def _select_first_visible(self, *, reload_created: bool = True) -> None:
        for index in range(self._nav.count()):
            item = self._nav.item(index)
            if item is not None and not item.isHidden():
                page_id = item.data(Qt.UserRole)
                if page_id:
                    self._select_page(str(page_id), reload_created=reload_created)
                    return
                self._nav.setCurrentItem(item)
                return
        self._show_empty_filter()

    def _select_page(self, page_id: str, *, reload_created: bool = True) -> None:
        if page_id not in self._pages:
            return
        spec = self._pages.get(page_id)
        created = page_id in self._page_widgets
        widget = self._ensure_page(spec)
        scroll = self._page_scrolls.get(page_id, widget)
        scroll.setEnabled(True)
        self._stack.setVisible(True)
        self._current_page_id = page_id
        self._title.setText(spec.title)
        self._description.setText(spec.description)
        self._stack.setCurrentWidget(scroll)
        if created:
            self._adopt_application_font(scroll)
        self._restore_button.setEnabled(page_id in persisted_page_ids())
        self._relink_tab_order(widget)
        self._syncing_nav = True
        for index in range(self._nav.count()):
            item = self._nav.item(index)
            if item.data(Qt.UserRole) == page_id:
                self._nav.setCurrentItem(item)
                break
        self._syncing_nav = False
        if created and reload_created:
            self._notify_reload(page_id)
        self._update_footer()

    def _ensure_page(self, spec: SettingsCenterPageSpec) -> QWidget:
        existing = self._page_widgets.get(spec.page_id)
        if existing is not None:
            return existing
        self._building_page_id = spec.page_id
        try:
            factory = spec.factory or empty_page_factory
            widget = factory(self)
            if widget is None:
                widget = empty_page_factory(self)
            self._page_widgets[spec.page_id] = widget
            scroll = QScrollArea()
            scroll.setObjectName(f"settings_page_scroll_{spec.page_id}")
            scroll.setWidgetResizable(True)
            scroll.setFrameShape(QFrame.NoFrame)
            scroll.setWidget(widget)
            self._page_scrolls[spec.page_id] = scroll
            self._stack.addWidget(scroll)
            return widget
        finally:
            self._building_page_id = None

    def _adopt_application_font(self, widget: QWidget) -> None:
        """Apply the live app font to a page that skipped hidden FontChange."""

        app_font = QApplication.font()
        if widget.font().pointSize() == app_font.pointSize():
            return
        widget.setFont(app_font)

    def _on_restore_defaults(self) -> None:
        self._begin_action()
        page_id = self._current_page_id
        if page_id is None:
            return
        try:
            result = self._glue.reset_page(page_id)
        except (ThemeApplyError, ThemeRollbackError) as exc:
            self.emit_message(str(exc), "error")
            self._reload_all_created_pages()
            self._update_footer()
            return
        if not result.success:
            self.emit_message(result.error or "Could not restore page defaults.", "error")
            return
        self._notify_reload(page_id)
        self._status.setText("Page defaults restored in the draft.")
        self._update_footer(status_already_set=True)

    def _on_apply(self) -> None:
        self._submit(close_after=False)

    def _on_ok(self) -> None:
        if self._submit(close_after=True):
            self.accept()

    def _submit(self, *, close_after: bool) -> bool:
        self._begin_action()
        if self._glue.session is None:
            self._glue.start()
        had_dirty = self._glue.is_dirty()
        try:
            result = self._glue.commit()
        except SettingsValidationError as exc:
            self.emit_message(str(exc), "error")
            self._update_footer()
            return False
        except (ThemeApplyError, ThemeRollbackError) as exc:
            self.emit_message(str(exc), "error")
            self._reload_all_created_pages()
            self._update_footer()
            return False
        if not result.success:
            self.emit_message(result.error or "Could not save settings.", "error")
            self._update_footer()
            return False
        self._notify_reload(self._current_page_id)
        if result.warning:
            self.emit_message(result.warning, "warning")
        elif had_dirty:
            self.emit_message("Settings applied.", "success")
        if not close_after:
            self._status.setText("Settings applied.")
        self._update_footer(status_already_set=not close_after and had_dirty)
        return True

    def _notify_reload(
        self,
        page_id: str | None,
        values: Mapping[str, Any] | None = None,
    ) -> None:
        if page_id is None:
            return
        if values is None:
            values = MappingProxyType(self._glue.draft_values())
        for callback in list(self._reload_hooks.get(page_id, ())):
            try:
                callback(values)
            except TypeError:
                callback()
            except Exception:
                continue

    def _reload_all_created_pages(
        self,
        values: Mapping[str, Any] | None = None,
    ) -> None:
        if values is None:
            values = MappingProxyType(self._glue.draft_values())
        for page_id in list(self._page_widgets):
            self._notify_reload(page_id, values)

    def _update_footer(self, *, status_already_set: bool = False) -> None:
        dirty = self._glue.is_dirty()
        writable = self._glue.is_writable()
        self._apply_button.setEnabled(dirty and writable)
        self._ok_button.setEnabled(writable)
        workspace = self._page_widgets.get(PAGE_WORKSPACE)
        set_writable = getattr(workspace, "set_storage_writable", None)
        if callable(set_writable):
            set_writable(writable)
        if not status_already_set:
            if not writable:
                self._status.setText(READ_ONLY_STATUS)
            else:
                self._status.setText("Unsaved changes" if dirty else "")

    def _begin_action(self) -> None:
        self._message_emitted = False

    def _relink_tab_order(self, page: QWidget | None) -> None:
        """Keep page editors between the nav list and the footer."""

        QWidget.setTabOrder(self._search, self._nav)
        previous = self._nav
        if page is not None:
            for child in page.findChildren(QWidget):
                if not int(child.focusPolicy()) & int(Qt.TabFocus):
                    continue
                if not child.isEnabled():
                    continue
                if child.window() != self.window():
                    continue
                QWidget.setTabOrder(previous, child)
                previous = child
        QWidget.setTabOrder(previous, self._restore_button)
        QWidget.setTabOrder(self._restore_button, self._cancel_button)
        QWidget.setTabOrder(self._cancel_button, self._apply_button)
        QWidget.setTabOrder(self._apply_button, self._ok_button)
