"""Compose the custom application title bar."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QSizePolicy,
    QStackedLayout,
    QVBoxLayout,
    QWidget,
)

from mygui.widgets.table.py_table import PyTable
from mygui.widgets.title_bar.py_title_button import ChangeButton
from mygui.widgets.title_bar.py_title_menu import (
    MenuBar,
    SelectorChartMenuBar,
    SelectorElementMenuBar,
    SelectorLayoutMenuBar,
    SelectorMenuBar,
    SelectorStyleMenuBar,
)
from mygui.application_theme import (
    bind_widget_qss,
    current_density_metrics,
    subscribe_theme_window,
)


def _gallery_placeholder(name: str) -> QWidget:
    placeholder = QWidget()
    placeholder.setObjectName(name)
    placeholder.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
    return placeholder


class PyTitleBar(QFrame):
    """Full-width application command bar beneath the native title bar."""

    def __init__(
        self,
        parent=None,
        figure_window=None,
        table: PyTable | None = None,
        export_preferences=None,
        template_workflow=None,
    ):
        super().__init__(parent)
        self.parent = parent
        self.figure_window = figure_window
        self._template_workflow = template_workflow
        self.setObjectName("title_bar")
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setUpdatesEnabled(False)
        try:
            self.layout = QVBoxLayout(self)
            self.layout.setContentsMargins(0, 0, 0, 0)
            self.layout.setSpacing(0)

            self.sublayout = QHBoxLayout()
            self.sublayout.setContentsMargins(0, 0, 0, 0)
            self.sublayout.setSpacing(0)
            self.stacklayout_top = QStackedLayout()
            self.stacklayout_bottom = QStackedLayout()
            self.stacklayout_top.setContentsMargins(0, 0, 0, 0)
            self.stacklayout_bottom.setContentsMargins(0, 0, 0, 0)

            self.selector_style_bar = SelectorStyleMenuBar(
                figure_window=figure_window,
                template_workflow=template_workflow,
                parent=self,
            )
            self._selector_layout_bar = None
            self._selector_chart_bar = None
            self._selector_element_bar = None
            self.stacklayout_bottom.addWidget(self.selector_style_bar)
            self.stacklayout_bottom.addWidget(
                _gallery_placeholder("selector_layout_placeholder")
            )
            self.stacklayout_bottom.addWidget(
                _gallery_placeholder("selector_chart_placeholder")
            )
            self.stacklayout_bottom.addWidget(
                _gallery_placeholder("selector_element_placeholder")
            )

            self.selector_menu_bar = SelectorMenuBar(
                self.stacklayout_bottom,
                figure_window=figure_window,
                parent=self,
            )
            self.selector_menu_bar._ensure_gallery_at = self.ensure_gallery_at
            self.menu_bar = MenuBar(
                table,
                figure_window,
                export_preferences=export_preferences,
                template_workflow=template_workflow,
                parent=self,
            )
            self.stacklayout_top.addWidget(self.selector_menu_bar)
            self.stacklayout_top.addWidget(self.menu_bar)

            self.change_button = ChangeButton("change_button")
            self.change_button.toggled.connect(self.the_button_was_toggled)
            self.sublayout.addWidget(self.change_button)
            self.sublayout.addLayout(self.stacklayout_top)
            self.sublayout.addStretch(1)

            self.layout.addLayout(self.sublayout)
            self.layout.addLayout(self.stacklayout_bottom)
            bind_widget_qss(self, "mygui/widgets/title_bar/style.qss")
            for child in (
                self.selector_menu_bar,
                self.menu_bar,
                self.change_button,
                self.selector_style_bar,
            ):
                subscribe_theme_window(child)
            subscribe_theme_window(self)
            self.apply_theme_metrics(current_density_metrics())
        finally:
            self.setUpdatesEnabled(True)

    def _theme_children(self):
        return [
            child
            for child in (
                self.selector_menu_bar,
                self.menu_bar,
                self.change_button,
                self.selector_style_bar,
                self._selector_layout_bar,
                self._selector_chart_bar,
                self._selector_element_bar,
            )
            if child is not None
        ]

    def apply_theme_metrics(self, metrics) -> None:
        """Apply command+gallery height and forward density to chrome children."""

        self.setFixedHeight(metrics.command + metrics.gallery)
        for child in self._theme_children():
            apply = getattr(child, "apply_theme_metrics", None)
            if callable(apply):
                apply(metrics)

    def apply_theme_icons(self, snapshot, provider) -> None:
        """Forward icon refresh to command, menu, and gallery chrome."""

        for child in self._theme_children():
            apply = getattr(child, "apply_theme_icons", None)
            if callable(apply):
                apply(snapshot, provider)

    def the_button_was_toggled(self, checked):
        """Synchronize the button appearance after its checked state changes."""

        self.stacklayout_top.setCurrentIndex(1 if checked else 0)

    def show_style_selector(self):
        """Return focus to the existing Style project-creation workflow."""
        self.change_button.setChecked(False)
        self.selector_menu_bar.style_button.setChecked(True)
        self.stacklayout_top.setCurrentIndex(0)
        self.stacklayout_bottom.setCurrentIndex(0)
        self.selector_menu_bar.style_button.setFocus(Qt.OtherFocusReason)

    def ensure_gallery_at(self, index: int) -> QWidget | None:
        """Create the gallery at ``index`` once. Index 0 is the eager Style gallery."""

        if index == 1:
            return self._ensure_layout_gallery()
        if index == 2:
            return self._ensure_chart_gallery()
        if index == 3:
            return self._ensure_element_gallery()
        return self.selector_style_bar

    @property
    def selector_layout_bar(self) -> SelectorLayoutMenuBar:
        """Lazy Layout gallery. Access creates it once."""

        return self._ensure_layout_gallery()

    @property
    def selector_chart_bar(self) -> SelectorChartMenuBar:
        """Lazy Chart gallery. Access creates it once."""

        return self._ensure_chart_gallery()

    @property
    def selector_element_bar(self) -> SelectorElementMenuBar:
        """Lazy Element gallery. Access creates it once."""

        return self._ensure_element_gallery()

    def _ensure_layout_gallery(self) -> SelectorLayoutMenuBar:
        if self._selector_layout_bar is None:
            gallery = SelectorLayoutMenuBar(figure_window=self.figure_window, parent=self)
            self._install_gallery(1, gallery)
            self._selector_layout_bar = gallery
        return self._selector_layout_bar

    def _ensure_chart_gallery(self) -> SelectorChartMenuBar:
        if self._selector_chart_bar is None:
            gallery = SelectorChartMenuBar(figure_window=self.figure_window, parent=self)
            self._install_gallery(2, gallery)
            self._selector_chart_bar = gallery
        return self._selector_chart_bar

    def _ensure_element_gallery(self) -> SelectorElementMenuBar:
        if self._selector_element_bar is None:
            gallery = SelectorElementMenuBar(figure_window=self.figure_window, parent=self)
            self._install_gallery(3, gallery)
            self._selector_element_bar = gallery
        return self._selector_element_bar

    def _install_gallery(self, index: int, gallery: QWidget) -> None:
        gallery.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        old = self.stacklayout_bottom.widget(index)
        current = self.stacklayout_bottom.currentIndex()
        self.stacklayout_bottom.insertWidget(index, gallery)
        if old is not None and old is not gallery:
            self.stacklayout_bottom.removeWidget(old)
            old.setParent(None)
            old.deleteLater()
        if current == index:
            self.stacklayout_bottom.setCurrentIndex(index)
        subscribe_theme_window(gallery)
