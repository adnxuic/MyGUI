"""Settings → Components page. NEXT_USE creation defaults; not project state."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from PySide6.QtWidgets import (
    QFormLayout,
    QGroupBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from mygui.application_settings.keys import (
    GENERAL_COMPONENT_KEYS,
    COMPONENTS_LINE_COLOR,
    COMPONENTS_LINE_LINESTYLE,
    COMPONENTS_LINE_LINEWIDTH,
    COMPONENTS_LINE_MARKER,
    COMPONENTS_LINE_MARKEREDGEWIDTH,
    COMPONENTS_LINE_MARKERSIZE,
    COMPONENTS_SCATTER_COLOR,
    COMPONENTS_SCATTER_LINEWIDTH,
    COMPONENTS_SCATTER_MARKER,
    COMPONENTS_SCATTER_SIZE,
    COMPONENTS_TEXT_COLOR,
    COMPONENTS_TEXT_FONTFAMILY,
    COMPONENTS_TEXT_FONTSIZE,
    COMPONENTS_TEXT_FONTSTYLE,
    COMPONENTS_TEXT_FONTWEIGHT,
    PAGE_COMPONENTS,
)
from mygui.widgets.common_widget.min_widget.color_library import ColorLibrary
from mygui.widgets.settings_center.inheritable_editors import InheritableSettingRow
from mygui.widgets.settings_center.pages import standard_page_spec
from mygui.widgets.settings_pages.page import (
    SettingsPageWidget,
    add_buddy_row,
    make_hint_label,
    make_intro_label,
    make_tab_scroll,
)

COMPONENTS_INTRO = (
    "These defaults apply to components created after Apply. They do not "
    "change existing Artists, the current project, Undo/Redo, or schema-v23 "
    "files."
)
COMPONENTS_PRECEDENCE = (
    "Precedence: this creation dialog's explicit input > Components override > "
    "current Axes palette (Line/Scatter color) or Figure style (other "
    "fields) > Matplotlib 3.9 built-in fallbacks."
)
COMPONENTS_SCOPE = (
    "Line defaults cover Function Curve, Plot, Fit, and Interpolation. "
    "Scatter covers ordinary Scatter (mapped and XRD explicit fields still "
    "win). Text covers free axes/figure Text only, not Title or axis labels."
)

_LINE_KEYS = (
    COMPONENTS_LINE_COLOR,
    COMPONENTS_LINE_LINESTYLE,
    COMPONENTS_LINE_LINEWIDTH,
    COMPONENTS_LINE_MARKER,
    COMPONENTS_LINE_MARKERSIZE,
    COMPONENTS_LINE_MARKEREDGEWIDTH,
)
_SCATTER_KEYS = (
    COMPONENTS_SCATTER_COLOR,
    COMPONENTS_SCATTER_MARKER,
    COMPONENTS_SCATTER_SIZE,
    COMPONENTS_SCATTER_LINEWIDTH,
)
_TEXT_KEYS = (
    COMPONENTS_TEXT_FONTFAMILY,
    COMPONENTS_TEXT_FONTSIZE,
    COMPONENTS_TEXT_COLOR,
    COMPONENTS_TEXT_FONTWEIGHT,
    COMPONENTS_TEXT_FONTSTYLE,
)


class ComponentsSettingsPage(SettingsPageWidget):
    """Fifteen inheritable NEXT_USE creation defaults."""

    PAGE_ID = PAGE_COMPONENTS

    def __init__(
        self,
        color_library: ColorLibrary,
        parent: QWidget | None = None,
        *,
        session: Any | None = None,
        registry: Any | None = None,
        host: Any | None = None,
    ) -> None:
        super().__init__(parent, session=session, registry=registry, host=host)
        if color_library is None:
            raise ValueError("ComponentsSettingsPage requires the shared ColorLibrary.")
        self._color_library = color_library
        self._rows: dict[str, InheritableSettingRow] = {}

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        if host is None:
            root.addWidget(make_intro_label(COMPONENTS_INTRO, self))

        tabs = QTabWidget(self)
        tabs.setObjectName("settings_components_tabs")
        tabs.addTab(
            self._tab_page("Line", _LINE_KEYS, color_library),
            "Line",
        )
        tabs.addTab(
            self._tab_page("Scatter", _SCATTER_KEYS, color_library),
            "Scatter",
        )
        tabs.addTab(
            self._tab_page("Text", _TEXT_KEYS, color_library),
            "Text",
        )
        root.addWidget(tabs, 1)
        root.addWidget(make_hint_label(COMPONENTS_PRECEDENCE, self))
        root.addWidget(make_hint_label(COMPONENTS_SCOPE, self))

        previous: QWidget | None = None
        for key in GENERAL_COMPONENT_KEYS:
            row = self._rows[key]
            focus_target = self._row_focus_target(row)
            if previous is not None:
                QWidget.setTabOrder(previous, row.inherit_box)
            QWidget.setTabOrder(row.inherit_box, focus_target)
            previous = focus_target
            row.valueChanged.connect(lambda item=key: self._on_row_changed(item))
        self.bind_host(host)
        self.load_values(self._initial_values())

    def _tab_page(
        self,
        title: str,
        keys: tuple[str, ...],
        color_library: ColorLibrary,
    ) -> QWidget:
        page = QWidget(self)
        layout = QVBoxLayout(page)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.addWidget(self._group(title, keys, color_library))
        layout.addStretch(1)
        return make_tab_scroll(
            page, f"settings_components_tab_{title.casefold()}", self
        )

    def _group(
        self,
        title: str,
        keys: tuple[str, ...],
        color_library: ColorLibrary,
    ) -> QGroupBox:
        box = QGroupBox(title, self)
        box.setObjectName(f"settings_components_{title.casefold()}")
        form = QFormLayout(box)
        for key in keys:
            spec = self._registry.spec(key)
            row = InheritableSettingRow(spec, color_library=color_library, parent=box)
            self._rows[key] = row
            label = add_buddy_row(form, spec.label or key, row.inherit_box, field=row)
            self._buddy_labels[key] = label
        return box

    @staticmethod
    def _row_focus_target(row: InheritableSettingRow) -> QWidget:
        button = getattr(row.value_editor, "color_button", None)
        if isinstance(button, QWidget):
            return button
        return row.value_editor

    def editors(self) -> dict[str, QWidget]:
        return {key: row.value_editor for key, row in self._rows.items()}

    def keyboard_editors(self) -> tuple[QWidget, ...]:
        widgets: list[QWidget] = []
        for key in GENERAL_COMPONENT_KEYS:
            row = self._rows[key]
            widgets.append(row.inherit_box)
            widgets.append(self._row_focus_target(row))
        return tuple(widgets)

    def draft_values(self) -> dict[str, Any]:
        return {key: row.value() for key, row in self._rows.items()}

    def load_values(
        self,
        values: Mapping[str, Any],
        *,
        preview: bool = False,
    ) -> None:
        self._loading = True
        try:
            for key, row in self._rows.items():
                if key in values:
                    row.set_value(self._registry.spec(key).normalize(values[key]))
        finally:
            self._loading = False
        if preview:
            self._stage_and_emit(self.draft_values())

    def _on_row_changed(self, key: str) -> None:
        if self._loading or self._staging:
            return
        self._stage_and_emit({key: self._rows[key].value()})


def make_components_factory(color_library: ColorLibrary):
    def factory(host: Any) -> ComponentsSettingsPage:
        return ComponentsSettingsPage(color_library, host=host)

    return factory


def components_page_spec(factory=None, *, color_library: ColorLibrary | None = None):
    """Shell registration spec for the Components page."""

    resolved = factory
    if resolved is None:
        if color_library is None:
            raise ValueError("components_page_spec requires a ColorLibrary.")
        resolved = make_components_factory(color_library)
    return standard_page_spec(
        PAGE_COMPONENTS,
        resolved,
        description=COMPONENTS_INTRO,
    )
