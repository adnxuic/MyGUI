"""Settings → Axes Components page. NEXT_USE Axes creation defaults."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from PySide6.QtWidgets import (
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QPushButton,
    QScrollArea,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from mygui.application_settings.keys import (
    AXES_COMPONENT_KEYS,
    AXES_GRID_FIELDS,
    AXES_SPINE_FIELDS,
    AXES_SPINE_SIDES,
    AXES_TICK_FIELDS,
    AXES_TICK_LABEL_FIELDS,
    PAGE_AXES_COMPONENTS,
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

AXES_COMPONENTS_INTRO = (
    "These defaults apply to ordinary Axes created after Apply. They do not "
    "change existing Artists, Colorbar auxiliary Axes, In-Axes, project "
    "restore, Undo/Redo, or schema-v23 files."
)
AXES_COMPONENTS_PRECEDENCE = (
    "Precedence: this layout dialog's explicit values > Axes Components "
    "override > current Figure style > Matplotlib 3.9 built-in fallbacks. "
    "Right-Y topology, shared outer labels, and XRD scientific rules still win."
)
AXES_COMPONENTS_SCOPE = (
    "Title, Axis Label, Legend, limits, scale, locator, formatter, aspect, "
    "and margins are not stored here. Copy actions update this draft only."
)

_GENERAL_KEYS = (
    "components.axes.facecolor",
    "components.axes.frameon",
    "components.axes.axisbelow",
)


class AxesComponentsSettingsPage(SettingsPageWidget):
    """Ninety-nine inheritable NEXT_USE Axes creation defaults."""

    PAGE_ID = PAGE_AXES_COMPONENTS

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
            raise ValueError(
                "AxesComponentsSettingsPage requires the shared ColorLibrary."
            )
        self._color_library = color_library
        self._rows: dict[str, InheritableSettingRow] = {}

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        if host is None:
            root.addWidget(make_intro_label(AXES_COMPONENTS_INTRO, self))

        tabs = QTabWidget(self)
        tabs.setObjectName("settings_axes_components_tabs")
        self._tabs = tabs
        self._pending_tab_builders: dict[int, Callable[[], QWidget]] = {}
        self._connected_keys: set[str] = set()
        tabs.addTab(
            make_tab_scroll(
                self._general_tab(color_library),
                "settings_axes_tab_general",
                self,
            ),
            "General",
        )
        if host is None:
            tabs.addTab(
                make_tab_scroll(
                    self._spines_tab(color_library),
                    "settings_axes_tab_spines",
                    self,
                ),
                "Spines",
            )
            tabs.addTab(
                make_tab_scroll(
                    self._axis_tab("x", color_library),
                    "settings_axes_tab_x",
                    self,
                ),
                "X Axis",
            )
            tabs.addTab(
                make_tab_scroll(
                    self._axis_tab("y", color_library),
                    "settings_axes_tab_y",
                    self,
                ),
                "Y Axis",
            )
        else:
            self._pending_tab_builders = {
                1: lambda: self._spines_tab(color_library),
                2: lambda: self._axis_tab("x", color_library),
                3: lambda: self._axis_tab("y", color_library),
            }
            tabs.addTab(
                make_tab_scroll(QWidget(self), "settings_axes_tab_spines", self),
                "Spines",
            )
            tabs.addTab(
                make_tab_scroll(QWidget(self), "settings_axes_tab_x", self),
                "X Axis",
            )
            tabs.addTab(
                make_tab_scroll(QWidget(self), "settings_axes_tab_y", self),
                "Y Axis",
            )
            tabs.currentChanged.connect(self._on_axes_tab_changed)
        root.addWidget(tabs, 1)
        root.addWidget(make_hint_label(AXES_COMPONENTS_PRECEDENCE, self))
        root.addWidget(make_hint_label(AXES_COMPONENTS_SCOPE, self))
        self._connect_new_rows()
        self.bind_host(host)
        self.load_values(self._initial_values(), realize_missing=False)

    def _general_tab(self, color_library: ColorLibrary) -> QWidget:
        page = QWidget(self)
        layout = QVBoxLayout(page)
        layout.addWidget(self._group(page, "General", _GENERAL_KEYS, color_library))
        layout.addStretch(1)
        return page

    def _on_axes_tab_changed(self, index: int) -> None:
        self._realize_tab(index)

    def _ensure_all_tabs(self) -> None:
        for index in tuple(self._pending_tab_builders):
            self._realize_tab(index)

    def _realize_tab(self, index: int) -> None:
        builder = self._pending_tab_builders.pop(index, None)
        if builder is None:
            return
        body = builder()
        scroll = self._tabs.widget(index)
        if isinstance(scroll, QScrollArea):
            previous = scroll.takeWidget()
            scroll.setWidget(body)
            if previous is not None:
                previous.deleteLater()
        self._connect_new_rows()
        self.load_values(self._initial_values(), realize_missing=False)

    def _connect_new_rows(self) -> None:
        previous: QWidget | None = None
        for key in AXES_COMPONENT_KEYS:
            row = self._rows.get(key)
            if row is None or key in self._connected_keys:
                continue
            focus_widgets = (
                row.inherit_box,
                *row.extra_focus_widgets(),
                self._row_focus_target(row),
            )
            for widget in focus_widgets:
                if previous is not None:
                    QWidget.setTabOrder(previous, widget)
                previous = widget
            row.valueChanged.connect(lambda item=key: self._on_row_changed(item))
            self._connected_keys.add(key)

    def _spines_tab(self, color_library: ColorLibrary) -> QWidget:
        page = QWidget(self)
        layout = QVBoxLayout(page)
        for side in AXES_SPINE_SIDES:
            keys = tuple(
                f"components.axes.spines.{side}.{field}"
                for field in AXES_SPINE_FIELDS
            )
            layout.addWidget(
                self._group(page, f"{side.title()} spine", keys, color_library)
            )
        layout.addStretch(1)
        return page

    def _axis_tab(self, axis: str, color_library: ColorLibrary) -> QWidget:
        page = QWidget(self)
        layout = QVBoxLayout(page)
        layout.addWidget(self._copy_bar(page, axis))
        for level in ("major", "minor"):
            title = f"{level.title()}"
            box = QGroupBox(title, page)
            box.setObjectName(f"settings_axes_{axis}_{level}")
            box_layout = QVBoxLayout(box)
            box_layout.addWidget(
                self._group(
                    box,
                    "Ticks",
                    tuple(
                        f"components.axes.{axis}.{level}.ticks.{field}"
                        for field in AXES_TICK_FIELDS
                    ),
                    color_library,
                )
            )
            box_layout.addWidget(
                self._group(
                    box,
                    "Tick labels",
                    tuple(
                        f"components.axes.{axis}.{level}.tick_labels.{field}"
                        for field in AXES_TICK_LABEL_FIELDS
                    ),
                    color_library,
                )
            )
            box_layout.addWidget(
                self._group(
                    box,
                    "Grid",
                    tuple(
                        f"components.axes.{axis}.{level}.grid.{field}"
                        for field in AXES_GRID_FIELDS
                    ),
                    color_library,
                )
            )
            layout.addWidget(box)
        layout.addStretch(1)
        return page

    def _copy_bar(self, parent: QWidget, axis: str) -> QWidget:
        bar = QWidget(parent)
        row = QHBoxLayout(bar)
        row.setContentsMargins(0, 0, 0, 0)
        other = "y" if axis == "x" else "x"
        copy_axis = QPushButton(
            f"Copy {axis.upper()} → {other.upper()}", bar
        )
        copy_axis.setObjectName(f"settings_axes_copy_{axis}_to_{other}")
        copy_axis.setAccessibleName(copy_axis.text())
        copy_axis.clicked.connect(
            lambda: self._copy_prefix(
                f"components.axes.{axis}.",
                f"components.axes.{other}.",
            )
        )
        copy_major = QPushButton("Copy Major → Minor", bar)
        copy_major.setObjectName(f"settings_axes_copy_{axis}_major_to_minor")
        copy_major.setAccessibleName(copy_major.text())
        copy_major.clicked.connect(
            lambda: self._copy_prefix(
                f"components.axes.{axis}.major.",
                f"components.axes.{axis}.minor.",
            )
        )
        copy_minor = QPushButton("Copy Minor → Major", bar)
        copy_minor.setObjectName(f"settings_axes_copy_{axis}_minor_to_major")
        copy_minor.setAccessibleName(copy_minor.text())
        copy_minor.clicked.connect(
            lambda: self._copy_prefix(
                f"components.axes.{axis}.minor.",
                f"components.axes.{axis}.major.",
            )
        )
        row.addWidget(copy_axis)
        row.addWidget(copy_major)
        row.addWidget(copy_minor)
        row.addStretch(1)
        return bar

    def _copy_prefix(self, source_prefix: str, dest_prefix: str) -> None:
        self._ensure_all_tabs()
        staged: dict[str, Any] = {}
        for key in AXES_COMPONENT_KEYS:
            if not key.startswith(source_prefix):
                continue
            dest = dest_prefix + key[len(source_prefix):]
            if dest not in self._rows:
                continue
            value = self._rows[key].value()
            self._rows[dest].set_value(value)
            staged[dest] = self._rows[dest].value()
        if staged:
            self._stage_and_emit(staged)

    def _group(
        self,
        parent: QWidget,
        title: str,
        keys: tuple[str, ...],
        color_library: ColorLibrary,
    ) -> QGroupBox:
        box = QGroupBox(title, parent)
        slug = title.casefold().replace(" ", "_")
        box.setObjectName(f"settings_axes_{slug}")
        form = QFormLayout(box)
        for key in keys:
            spec = self._registry.spec(key)
            row = InheritableSettingRow(
                spec, color_library=color_library, parent=box
            )
            self._rows[key] = row
            label = add_buddy_row(form, spec.label or key, row.inherit_box, field=row)
            self._buddy_labels[key] = label
        return box

    @staticmethod
    def _row_focus_target(row: InheritableSettingRow) -> QWidget:
        button = getattr(row.value_editor, "color_button", None)
        if isinstance(button, QWidget):
            return button
        spin = getattr(row, "_optional_spin", None)
        if isinstance(spin, QWidget):
            return spin
        return row.value_editor

    def hosted_draft_keys(self) -> tuple[str, ...]:
        return AXES_COMPONENT_KEYS

    def editors(self) -> dict[str, QWidget]:
        self._ensure_all_tabs()
        return {key: row.value_editor for key, row in self._rows.items()}

    def keyboard_editors(self) -> tuple[QWidget, ...]:
        self._ensure_all_tabs()
        widgets: list[QWidget] = []
        for key in AXES_COMPONENT_KEYS:
            row = self._rows[key]
            widgets.append(row.inherit_box)
            widgets.extend(row.extra_focus_widgets())
            widgets.append(self._row_focus_target(row))
        return tuple(widgets)

    def draft_values(self) -> dict[str, Any]:
        self._ensure_all_tabs()
        return {key: row.value() for key, row in self._rows.items()}

    def load_values(
        self,
        values: Mapping[str, Any],
        *,
        preview: bool = False,
        realize_missing: bool = False,
    ) -> None:
        if realize_missing and any(key not in self._rows for key in AXES_COMPONENT_KEYS):
            self._ensure_all_tabs()
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


def make_axes_components_factory(color_library: ColorLibrary):
    def factory(host: Any) -> AxesComponentsSettingsPage:
        return AxesComponentsSettingsPage(color_library, host=host)

    return factory


def axes_components_page_spec(
    factory=None, *, color_library: ColorLibrary | None = None
):
    """Shell registration spec for the Axes Components page."""

    resolved = factory
    if resolved is None:
        if color_library is None:
            raise ValueError("axes_components_page_spec requires a ColorLibrary.")
        resolved = make_axes_components_factory(color_library)
    return standard_page_spec(
        PAGE_AXES_COMPONENTS,
        resolved,
        description=AXES_COMPONENTS_INTRO,
        keywords=("Axes", "spine", "tick", "grid", "Copy"),
    )
