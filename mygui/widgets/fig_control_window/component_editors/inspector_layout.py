"""Shared Inspector form wrapping, switch batching, and result-table policies."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
import weakref

from PySide6.QtCore import QEvent, QRect, QSize, Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QAbstractSpinBox,
    QComboBox,
    QFormLayout,
    QGroupBox,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QStyle,
    QStyleOptionGroupBox,
    QTableWidget,
    QTableWidgetItem,
    QWidget,
)

from mygui.application_theme import current_density_metrics, current_theme_snapshot
from mygui.widgets.ui_components import UiTextRole, apply_text_style

# Editors may shrink; field labels keep their natural single-line width.
SAFE_MIN_WIDTH = 1
INSPECTOR_MIN_PANEL_WIDTH = 240
_COMBO_MIN_CONTENTS = 6
FIT_RESULT_VISIBLE_ROWS = 6
_HOST_STACKS: dict[int, tuple[object, object]] = {}


def _alive_widget(widget: QWidget | None) -> QWidget | None:
    if widget is None:
        return None
    try:
        widget.objectName()
    except RuntimeError:
        return None
    return widget


def _qt_layout(widget: QWidget):
    layout_attr = getattr(widget, "layout", None)
    if callable(layout_attr):
        return layout_attr()
    from PySide6.QtWidgets import QLayout

    if isinstance(layout_attr, QLayout):
        return layout_attr
    return QWidget.layout(widget)


class InspectorFormLabel(QLabel):
    """Single-line field label. ``QFormLayout`` wraps the whole row when tight."""

    def __init__(self, text: str = "", parent: QWidget | None = None):
        super().__init__(text, parent)
        self._full_text = text
        self.setWordWrap(False)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)

    def setText(self, text: str) -> None:  # noqa: N802
        self._full_text = str(text)
        super().setText(self._full_text)
        self._apply_elide()

    def minimumSizeHint(self) -> QSize:
        hint = super().minimumSizeHint()
        natural = self.fontMetrics().horizontalAdvance(self._full_text)
        return QSize(min(natural, self._width_cap()), hint.height())

    def sizeHint(self) -> QSize:
        metrics = self.fontMetrics()
        natural = metrics.horizontalAdvance(self._full_text)
        return QSize(
            min(natural, self._width_cap()),
            super().sizeHint().height(),
        )

    def _width_cap(self) -> int:
        metrics = current_density_metrics()
        gutter = 4 * metrics.spacing_sm + 8
        widget = self.parentWidget()
        while widget is not None:
            maximum = widget.maximumWidth()
            if 0 < maximum < 16777215:
                usable = maximum
                if widget.width() > 1:
                    usable = min(widget.width(), maximum)
                return max(24, usable - gutter)
            widget = widget.parentWidget()
        return max(24, INSPECTOR_MIN_PANEL_WIDTH - gutter)

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self.apply_theme_metrics()

    def changeEvent(self, event) -> None:  # noqa: N802
        super().changeEvent(event)
        if event.type() in (QEvent.Type.FontChange, QEvent.Type.StyleChange):
            self.apply_theme_metrics()

    def apply_theme_metrics(self, metrics=None) -> None:
        """Recalculate the width cap after theme, density, or host resize."""

        del metrics
        cap = self._width_cap()
        if self.maximumWidth() != cap:
            self.setMaximumWidth(cap)
            self.updateGeometry()
        self._apply_elide()

    def _apply_elide(self) -> None:
        full = self._full_text
        natural = self.fontMetrics().horizontalAdvance(full)
        if self.width() < natural:
            self.setToolTip(full)
        if self.width() <= 1:
            if super().text() != full:
                super().setText(full)
            return
        elided = self.fontMetrics().elidedText(
            full,
            Qt.TextElideMode.ElideRight,
            max(1, self.width()),
        )
        if super().text() != elided:
            super().setText(elided)
        if elided != full:
            self.setToolTip(full)


class CurrentPageStackedWidget(QStackedWidget):
    """Size to the visible page instead of the widest hidden Inspector page."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._batch_depth = 0
        self._geometry_dirty = False
        self._flushing = False
        self._geometry_updates = 0
        self._inspector_scroll_ref: object | None = None
        self._tree_view_ref: object | None = None
        self._page_layout_cache: dict[int, tuple[object, ...]] = {}
        self.currentChanged.connect(self._page_changed)

    def setCurrentIndex(self, index: int) -> None:  # noqa: N802
        """Show a page without relayout when width and theme are unchanged."""

        self._switch_to_index(index, lambda: QStackedWidget.setCurrentIndex(self, index))

    def setCurrentWidget(self, widget: QWidget) -> None:  # noqa: N802
        """Python callers use this; C++ ``setCurrentIndex`` is not virtual."""

        if widget is None:
            QStackedWidget.setCurrentWidget(self, widget)
            return
        index = self.indexOf(widget)
        if index < 0:
            QStackedWidget.setCurrentWidget(self, widget)
            return
        self._switch_to_index(
            index,
            lambda: QStackedWidget.setCurrentWidget(self, widget),
        )

    def _switch_to_index(self, index: int, apply) -> None:
        incoming = self.widget(index)
        previous = self.currentWidget()
        generation = self._layout_generation()
        cached = (
            incoming is not None
            and self._page_layout_cache.get(id(incoming)) == generation
        )
        if previous is not None and previous is not incoming:
            self._set_page_layout_enabled(previous, False)
        if incoming is not None:
            self._set_page_layout_enabled(incoming, not cached)
        apply()
        if incoming is not None and cached:
            self._set_page_layout_enabled(incoming, True)

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        page = self.currentWidget()
        if page is None:
            return
        if self._page_layout_cache.get(id(page)) == self._layout_generation():
            return
        self._geometry_dirty = True
        self._set_page_layout_enabled(page, True)
        if self._batch_depth == 0:
            self.flush_switch()

    def _set_page_layout_enabled(self, page: QWidget | None, enabled: bool) -> None:
        target = _alive_widget(page)
        if target is None:
            return
        layout = _qt_layout(target)
        if layout is not None and layout.isEnabled() != enabled:
            layout.setEnabled(enabled)

    def attach_switch_host(self, host: QWidget) -> None:
        """Register ``host`` as the owner that starts page-switch batches."""

        if host is None:
            return
        key = id(host)
        host_ref = weakref.ref(host)
        stack_ref = weakref.ref(self)

        def _drop(*_args: object, host_id: int = key) -> None:
            _HOST_STACKS.pop(host_id, None)

        first = key not in _HOST_STACKS
        _HOST_STACKS[key] = (host_ref, stack_ref)
        if first:
            host.destroyed.connect(_drop)
            self.destroyed.connect(_drop)

    def register_switch_viewports(
        self,
        *,
        inspector_scroll: QScrollArea | None = None,
        tree_view: QAbstractItemView | None = None,
    ) -> None:
        """Record the viewports refreshed when this outermost stack flushes."""

        if inspector_scroll is not None:
            self._inspector_scroll_ref = weakref.ref(inspector_scroll)
        if tree_view is not None:
            self._tree_view_ref = weakref.ref(tree_view)

    def outermost(self) -> CurrentPageStackedWidget:
        """Return the highest ``CurrentPageStackedWidget`` ancestor, else self."""

        found = self
        current = self.parentWidget()
        while current is not None:
            if isinstance(current, CurrentPageStackedWidget):
                found = current
            current = current.parentWidget()
        return found

    @classmethod
    def for_host(cls, host: QWidget | None) -> CurrentPageStackedWidget | None:
        """Return the stack registered by ``attach_switch_host``."""

        target = _alive_widget(host)
        if target is None:
            return None
        entry = _HOST_STACKS.get(id(target))
        if entry is None:
            return None
        _host_ref, stack_ref = entry
        stack = stack_ref()
        return stack if isinstance(stack, cls) else None

    @classmethod
    def from_widget(cls, widget: QWidget | None) -> CurrentPageStackedWidget | None:
        """Return the outermost stacked ancestor of ``widget``."""

        current = _alive_widget(widget)
        found = None
        while current is not None:
            if isinstance(current, cls):
                found = current
            current = current.parentWidget()
        return found

    @contextmanager
    def switch_batch(self):
        """Collapse nested page switches into one outermost geometry flush."""

        outer = self.outermost()
        outer._batch_depth += 1
        if outer._batch_depth == 1:
            outer._batch_updates = outer.updatesEnabled()
            outer.setUpdatesEnabled(False)
        try:
            yield
        finally:
            outer._batch_depth -= 1
            if outer._batch_depth == 0:
                try:
                    outer.flush_switch()
                finally:
                    if getattr(outer, "_batch_updates", True):
                        outer.setUpdatesEnabled(True)

    def request_geometry_refresh(self) -> None:
        """Activate the current page once. Nested batches coalesce."""

        current: CurrentPageStackedWidget | None = self
        while current is not None:
            page = current.currentWidget()
            if page is not None:
                current._page_layout_cache.pop(id(page), None)
            current._geometry_dirty = True
            parent = current.parentWidget()
            nxt = None
            while parent is not None:
                if isinstance(parent, CurrentPageStackedWidget):
                    nxt = parent
                    break
                parent = parent.parentWidget()
            current = nxt
        outer = self.outermost()
        if outer._batch_depth > 0:
            return
        outer.flush_switch()

    def flush_switch(self) -> None:
        """Activate the current page, update this stack once, then viewports."""

        if self._flushing:
            return
        self._flushing = True
        try:
            page = self.currentWidget()
            generation = self._layout_generation()
            page_id = id(page) if page is not None else 0
            need_activate = (
                self._geometry_dirty
                or self._page_layout_cache.get(page_id) != generation
            )
            if need_activate and page is not None:
                self._set_page_layout_enabled(page, True)
                layout = _qt_layout(page)
                if layout is not None:
                    layout.activate()
                if page_id:
                    self._page_layout_cache[page_id] = generation
            if need_activate:
                self.updateGeometry()
                self._geometry_updates += 1
                self._refresh_registered_viewports()
            self._geometry_dirty = False
        finally:
            self._flushing = False

    def _layout_generation(self) -> tuple[object, ...]:
        snapshot = current_theme_snapshot()
        width = int(self.width())
        if snapshot is None:
            return (width,)
        prefs = snapshot.preferences
        return (width, prefs.font_pt, prefs.density, snapshot.scheme)

    def _refresh_registered_viewports(self) -> None:
        scroll = None
        if self._inspector_scroll_ref is not None:
            scroll = _alive_widget(self._inspector_scroll_ref())
        if isinstance(scroll, QScrollArea):
            scroll.updateGeometry()
            viewport = _alive_widget(scroll.viewport())
            if viewport is not None:
                viewport.updateGeometry()
            for bar in (scroll.horizontalScrollBar(), scroll.verticalScrollBar()):
                if bar is not None:
                    bar.updateGeometry()
        tree = None
        if self._tree_view_ref is not None:
            tree = _alive_widget(self._tree_view_ref())
        if isinstance(tree, QAbstractItemView):
            tree.updateGeometry()
            viewport = _alive_widget(tree.viewport())
            if viewport is not None:
                viewport.updateGeometry()
            for bar in (tree.horizontalScrollBar(), tree.verticalScrollBar()):
                if bar is not None:
                    bar.updateGeometry()

    def _page_changed(self, index: int) -> None:
        page = self.widget(index)
        generation = self._layout_generation()
        cache_hit = (
            page is not None
            and self._page_layout_cache.get(id(page)) == generation
        )
        outer = self.outermost()
        if not cache_hit:
            outer._geometry_dirty = True
        if outer._batch_depth > 0:
            return
        if cache_hit and not outer._geometry_dirty:
            return
        outer.flush_switch()

    def sizeHint(self) -> QSize:
        current = self.currentWidget()
        return current.sizeHint() if current is not None else super().sizeHint()

    def minimumSizeHint(self) -> QSize:
        current = self.currentWidget()
        if current is None:
            return super().minimumSizeHint()
        return current.minimumSizeHint()


@contextmanager
def inspector_page_switch_batch(host: QWidget | None = None) -> Iterator[None]:
    """Batch nested Inspector page switches onto one outermost stack flush."""

    stack = None
    if isinstance(host, CurrentPageStackedWidget):
        stack = host
    else:
        stack = CurrentPageStackedWidget.for_host(host)
        if stack is None:
            stack = CurrentPageStackedWidget.from_widget(host)
    if stack is None:
        yield
        return
    with stack.outermost().switch_batch():
        yield


def inspector_switch_batch(stack: QWidget | None = None) -> Iterator[None]:
    """Compatibility alias for ``inspector_page_switch_batch``."""

    return inspector_page_switch_batch(stack)


def remove_from_parent_stack(widget: QWidget | None) -> None:
    """Detach ``widget`` from its ``CurrentPageStackedWidget`` parent, if any."""

    target = _alive_widget(widget)
    if target is None:
        return
    parent = target.parentWidget()
    if isinstance(parent, CurrentPageStackedWidget) and parent.indexOf(target) >= 0:
        parent.removeWidget(target)


def present_inspector_page(stack: CurrentPageStackedWidget, page: QWidget) -> None:
    """Show ``page`` on ``stack`` without hiding unrelated owner containers."""

    target = _alive_widget(page)
    if target is None:
        return
    if stack.indexOf(target) < 0:
        stack.addWidget(target)
    stack.setCurrentWidget(target)


def request_inspector_geometry_refresh(widget: QWidget | None) -> None:
    """Refresh the outermost Inspector stack after collapse or hide."""

    stack = CurrentPageStackedWidget.from_widget(widget)
    if stack is None:
        stack = CurrentPageStackedWidget.for_host(widget)
    if stack is None:
        target = _alive_widget(widget)
        if target is None:
            return
        layout = _qt_layout(target)
        if layout is not None:
            layout.activate()
        return
    stack.request_geometry_refresh()


def configure_inspector_form(form: QFormLayout) -> None:
    """Keep QFormLayout; wrap the whole label-editor row when space is tight."""

    form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
    form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
    form.setFormAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
    form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
    metrics = current_density_metrics()
    form.setHorizontalSpacing(metrics.spacing_sm)
    form.setVerticalSpacing(metrics.spacing_xs)
    form.setContentsMargins(0, 0, 0, 0)


def apply_expanding_field(widget: QWidget) -> None:
    """Allow Inspector editors to shrink to the panel width."""

    from mygui.widgets.common_widget.min_widget.py_colorchoice_widgets import (
        ColorChoiceWidget,
    )
    from mygui.widgets.fig_control_window.component_editors.inline_spec_editors import (
        OptionalColorEditor,
    )
    from mygui.widgets.ui_components import annotate_inspector_control

    annotate_inspector_control(widget)
    if isinstance(widget, (ColorChoiceWidget, OptionalColorEditor)):
        widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        return
    if isinstance(widget, QComboBox):
        widget.setSizeAdjustPolicy(
            QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon
        )
        widget.setMinimumContentsLength(_COMBO_MIN_CONTENTS)
        widget.setMinimumWidth(SAFE_MIN_WIDTH)
        widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        return
    if isinstance(widget, QPushButton):
        widget.setMinimumWidth(SAFE_MIN_WIDTH)
        widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        if widget.text() and not widget.toolTip():
            widget.setToolTip(widget.text())
        return
    if isinstance(widget, (QLineEdit, QAbstractSpinBox)):
        widget.setMinimumWidth(SAFE_MIN_WIDTH)
        widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        return
    policy = widget.sizePolicy()
    widget.setSizePolicy(QSizePolicy.Policy.Expanding, policy.verticalPolicy())


def labeled_form_row(
    text: str,
    *,
    tooltip: str = "",
    buddy: QWidget | None = None,
    parent: QWidget | None = None,
) -> InspectorFormLabel:
    """Return a single-line field label with buddy and natural text width."""

    label = InspectorFormLabel(text, parent)
    label.setAccessibleName(text)
    if tooltip:
        label.setToolTip(tooltip)
        label.setAccessibleDescription(tooltip)
    if buddy is not None:
        label.setBuddy(buddy)
        if not buddy.accessibleName():
            buddy.setAccessibleName(text)
        if tooltip and not buddy.accessibleDescription():
            buddy.setAccessibleDescription(tooltip)
    apply_text_style(label, UiTextRole.LABEL)
    return label


def add_labeled_form_row(
    form: QFormLayout,
    text: str,
    field: QWidget,
    *,
    tooltip: str = "",
) -> InspectorFormLabel:
    """Add a form row whose label keeps natural width and a buddy link."""

    label = labeled_form_row(text, tooltip=tooltip, buddy=field)
    form.addRow(label, field)
    return label


def section_group_option(group: QGroupBox) -> QStyleOptionGroupBox:
    """Build a style option for Inspector section GroupBox subcontrols."""

    option = QStyleOptionGroupBox()
    option.initFrom(group)
    option.rect = group.rect()
    option.text = group.title()
    option.lineWidth = 1
    option.midLineWidth = 0
    option.textAlignment = Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
    option.subControls = (
        QStyle.SubControl.SC_GroupBoxFrame
        | QStyle.SubControl.SC_GroupBoxLabel
        | QStyle.SubControl.SC_GroupBoxContents
    )
    if group.isCheckable():
        option.subControls |= QStyle.SubControl.SC_GroupBoxCheckBox
        if group.isChecked():
            option.state |= QStyle.StateFlag.State_On
            option.state |= QStyle.StateFlag.State_Sunken
        else:
            option.state |= QStyle.StateFlag.State_Off
    return option


def section_group_subcontrol_rects(group: QGroupBox) -> dict[str, QRect]:
    """Return title, indicator, contents, and frame rects in GroupBox coords."""

    option = section_group_option(group)
    style = group.style()
    control = QStyle.ComplexControl.CC_GroupBox
    return {
        "title": style.subControlRect(
            control, option, QStyle.SubControl.SC_GroupBoxLabel, group
        ),
        "indicator": style.subControlRect(
            control, option, QStyle.SubControl.SC_GroupBoxCheckBox, group
        ),
        "contents": style.subControlRect(
            control, option, QStyle.SubControl.SC_GroupBoxContents, group
        ),
        "frame": style.subControlRect(
            control, option, QStyle.SubControl.SC_GroupBoxFrame, group
        ),
    }


def inspector_formula_height() -> int:
    """Return a density-derived height for short read-only formula editors."""

    metrics = current_density_metrics()
    return metrics.control * 2 + metrics.spacing_xs


def configure_inspector_result_table(table: QTableWidget) -> None:
    """Stretch every column and keep the table inside a 240px Inspector."""

    from mygui.widgets.ui_components import UiRole, apply_ui_style

    apply_ui_style(table, role=UiRole.TABLE)
    header = table.horizontalHeader()
    header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
    header.setStretchLastSection(True)
    table.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
    table.setWordWrap(False)
    table.setTextElideMode(Qt.TextElideMode.ElideRight)
    table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    table.verticalHeader().setVisible(False)
    table.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
    size_inspector_result_table(table)


def set_inspector_table_text(
    table: QTableWidget,
    row: int,
    column: int,
    text: str,
    *,
    flags: Qt.ItemFlag | None = None,
) -> QTableWidgetItem:
    """Set cell text with tooltip and accessible text for truncated values."""

    value = str(text)
    item = table.item(row, column)
    if item is None:
        item = QTableWidgetItem(value)
        table.setItem(row, column, item)
    else:
        item.setText(value)
    item.setToolTip(value)
    item.setData(Qt.ItemDataRole.AccessibleTextRole, value)
    item.setData(Qt.ItemDataRole.AccessibleDescriptionRole, value)
    if flags is None:
        flags = Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable
    item.setFlags(flags)
    return item


def size_inspector_result_table(table: QTableWidget) -> None:
    """Fit up to six content rows; scroll internally only after that."""

    metrics = current_density_metrics()
    rows = max(table.rowCount(), 0)
    header_h = table.horizontalHeader().sizeHint().height() or metrics.table_header
    row_h = table.verticalHeader().defaultSectionSize() or metrics.table_row
    visible = min(max(rows, 1), FIT_RESULT_VISIBLE_ROWS)
    frame = table.frameWidth() * 2
    height = header_h + visible * row_h + frame
    table.setFixedHeight(height)
    if rows > FIT_RESULT_VISIBLE_ROWS:
        table.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
    else:
        table.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
