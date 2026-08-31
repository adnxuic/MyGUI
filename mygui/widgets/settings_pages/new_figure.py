"""New Figure defaults page. NEXT_USE; does not overwrite opened projects."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from PySide6.QtWidgets import QFormLayout, QVBoxLayout, QWidget

from mygui.application_settings.keys import (
    NEW_FIGURE_DOCUMENT_DPI,
    NEW_FIGURE_HEIGHT_IN,
    NEW_FIGURE_WIDTH_IN,
    PAGE_NEW_FIGURE,
)

from .page import (
    FocusDoubleSpinBox,
    SettingsPageWidget,
    add_buddy_row,
    configure_number_editor,
    make_hint_label,
    make_intro_label,
)

NEW_FIGURE_INTRO = (
    "These defaults apply to the Style creation window and to Figures created "
    "by a first-time text or Excel import."
)
NEW_FIGURE_PRECEDENCE = (
    "Precedence: this session's explicit input > application defaults > "
    "built-in defaults (6.4 in × 4.8 in, 100 DPI)."
)
NEW_FIGURE_PROJECT = (
    "Opening a project uses the persisted schema-v23 Figure size and document "
    "DPI. These application defaults do not overwrite an opened Figure."
)


class NewFigureSettingsPage(SettingsPageWidget):
    """Width, height, and document DPI for first-time Figure creation."""

    PAGE_ID = PAGE_NEW_FIGURE

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        session: Any | None = None,
        registry: Any | None = None,
        host: Any | None = None,
    ) -> None:
        super().__init__(parent, session=session, registry=registry, host=host)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        if host is None:
            root.addWidget(make_intro_label(NEW_FIGURE_INTRO, self))

        form = QFormLayout()
        width_spec = self._registry.spec(NEW_FIGURE_WIDTH_IN)
        self.width_spin = FocusDoubleSpinBox(self)
        self.width_spin.setObjectName("new_figure_width_in")
        configure_number_editor(
            self.width_spin, width_spec, decimals=2, step=0.1, suffix=" in"
        )
        width_label = add_buddy_row(
            form,
            width_spec.label or "Default Figure width (in)",
            self.width_spin,
        )
        self._buddy_labels[NEW_FIGURE_WIDTH_IN] = width_label

        height_spec = self._registry.spec(NEW_FIGURE_HEIGHT_IN)
        self.height_spin = FocusDoubleSpinBox(self)
        self.height_spin.setObjectName("new_figure_height_in")
        configure_number_editor(
            self.height_spin, height_spec, decimals=2, step=0.1, suffix=" in"
        )
        height_label = add_buddy_row(
            form,
            height_spec.label or "Default Figure height (in)",
            self.height_spin,
        )
        self._buddy_labels[NEW_FIGURE_HEIGHT_IN] = height_label

        dpi_spec = self._registry.spec(NEW_FIGURE_DOCUMENT_DPI)
        self.dpi_spin = FocusDoubleSpinBox(self)
        self.dpi_spin.setObjectName("new_figure_document_dpi")
        configure_number_editor(
            self.dpi_spin, dpi_spec, decimals=1, step=1.0, suffix=" dpi"
        )
        dpi_label = add_buddy_row(
            form,
            dpi_spec.label or "Default document DPI",
            self.dpi_spin,
        )
        self._buddy_labels[NEW_FIGURE_DOCUMENT_DPI] = dpi_label
        root.addLayout(form)
        root.addWidget(make_hint_label(NEW_FIGURE_PRECEDENCE, self))
        root.addWidget(make_hint_label(NEW_FIGURE_PROJECT, self))
        root.addStretch(1)

        QWidget.setTabOrder(self.width_spin, self.height_spin)
        QWidget.setTabOrder(self.height_spin, self.dpi_spin)
        self.width_spin.valueChanged.connect(self._on_changed)
        self.height_spin.valueChanged.connect(self._on_changed)
        self.dpi_spin.valueChanged.connect(self._on_changed)
        self.bind_host(host)
        self.load_values(self._initial_values())

    @classmethod
    def page_spec(cls):
        return page_spec(cls.make_factory())

    @classmethod
    def make_factory(cls):
        def factory(host: Any) -> NewFigureSettingsPage:
            return cls(host=host)

        return factory

    def editors(self) -> dict[str, QWidget]:
        return {
            NEW_FIGURE_WIDTH_IN: self.width_spin,
            NEW_FIGURE_HEIGHT_IN: self.height_spin,
            NEW_FIGURE_DOCUMENT_DPI: self.dpi_spin,
        }

    def draft_values(self) -> dict[str, Any]:
        return {
            NEW_FIGURE_WIDTH_IN: float(self.width_spin.value()),
            NEW_FIGURE_HEIGHT_IN: float(self.height_spin.value()),
            NEW_FIGURE_DOCUMENT_DPI: float(self.dpi_spin.value()),
        }

    def load_values(
        self,
        values: Mapping[str, Any],
        *,
        preview: bool = False,
    ) -> None:
        self._loading = True
        try:
            if NEW_FIGURE_WIDTH_IN in values:
                width = self._registry.spec(NEW_FIGURE_WIDTH_IN).normalize(
                    values[NEW_FIGURE_WIDTH_IN]
                )
                self.width_spin.setValue(float(width))
            if NEW_FIGURE_HEIGHT_IN in values:
                height = self._registry.spec(NEW_FIGURE_HEIGHT_IN).normalize(
                    values[NEW_FIGURE_HEIGHT_IN]
                )
                self.height_spin.setValue(float(height))
            if NEW_FIGURE_DOCUMENT_DPI in values:
                dpi = self._registry.spec(NEW_FIGURE_DOCUMENT_DPI).normalize(
                    values[NEW_FIGURE_DOCUMENT_DPI]
                )
                self.dpi_spin.setValue(float(dpi))
        finally:
            self._loading = False
        if preview:
            self._on_changed()

    def _on_changed(self, *_args: object) -> None:
        if self._loading or self._staging:
            return
        self._stage_and_emit(self.draft_values())


def make_new_figure_factory():
    return NewFigureSettingsPage.make_factory()


def page_spec(factory=None):
    """Shell registration spec for the New Figure page."""

    from mygui.widgets.settings_center.pages import standard_page_spec

    return standard_page_spec(
        PAGE_NEW_FIGURE,
        factory if factory is not None else make_new_figure_factory(),
        description=NEW_FIGURE_INTRO,
    )
