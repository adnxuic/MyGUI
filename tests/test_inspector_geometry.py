"""Inspector geometry, fold refresh, accessibility, and switch isolation."""

from __future__ import annotations

import os
import tempfile
import unittest
from io import BytesIO
from pathlib import Path

from tests.axes_helpers import create_regular_axes

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPoint, QRect, QSettings, Qt
from PySide6.QtWidgets import (
    QApplication,
    QLabel,
    QLayout,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QTableWidget,
    QVBoxLayout,
    QWidget,
)

from main import MainWindow
from mygui.application_theme import (
    AppearancePreferences,
    COMPONENT_QSS_RESOURCE,
    Density,
    ThemeMode,
    contrast_ratio,
    current_qss_tokens,
    render_resource_stylesheet,
)
from mygui.database import ColumnRef
from mygui.database.interpolate_func import interpolate_dict
from mygui.figuremodify.component_services import SecondaryAxisCreateSpec
from mygui.figuremodify.components import ComponentKind, ComponentRole, ROLES_BY_KIND
from mygui.figuremodify.in_axes import ImageInAxesCreateSpec, ZoomInAxesCreateSpec
from mygui.widgets.fig_control_window.component_editors.inspector import (
    InspectorSectionGroup,
)
from mygui.widgets.fig_control_window.component_editors.inspector_layout import (
    CurrentPageStackedWidget,
    configure_inspector_result_table,
    inspector_switch_batch,
    labeled_form_row,
    section_group_subcontrol_rects,
    set_inspector_table_text,
    size_inspector_result_table,
)
from mygui.widgets.fig_control_window.component_editors.common import RangeEditor
from mygui.widgets.fig_control_window.component_editors.profiles import (
    register_production_profiles,
)
from mygui.widgets.fig_control_window.component_editors.registry import EditorRegistry
from mygui.widgets.ui_components import (
    UiRole,
    UiVariant,
    apply_ui_style,
    inspect_chrome,
)


WIDTHS = (240, 320, 480)
FONTS = (8, 9, 16)
DENSITIES = (Density.COMPACT, Density.STANDARD, Density.COMFORTABLE)
MODES = (ThemeMode.LIGHT, ThemeMode.DARK)
VIEWPORT_HEIGHT = 400


def _qapp() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def _coverage_tracing() -> bool:
    try:
        from coverage import Coverage
    except ImportError:
        return False
    current = getattr(Coverage, "current", None)
    return callable(current) and current() is not None


def _mapped_rect(widget: QWidget, origin: QWidget) -> QRect:
    return QRect(widget.mapTo(origin, QPoint(0, 0)), widget.size())


def _direct_children(widget: QWidget) -> list[QWidget]:
    return list(
        widget.findChildren(
            QWidget,
            options=Qt.FindChildOption.FindDirectChildrenOnly,
        )
    )


def _natural_label_width(label: QLabel) -> int:
    text = getattr(label, "_full_text", None) or label.text()
    return int(label.fontMetrics().horizontalAdvance(text))


def _assert_buddy_labels(test, inspector: QWidget, host: QWidget, label: str) -> None:
    for child in inspector.findChildren(QLabel):
        if not child.isVisible() or child.width() <= 0 or child.height() <= 0:
            continue
        buddy = child.buddy()
        if buddy is None:
            continue
        text = (getattr(child, "_full_text", None) or child.text()).strip()
        if not text:
            continue
        test.assertFalse(
            child.wordWrap(),
            msg=f"{label} field label {text!r} forces internal wrap",
        )
        mapped = _mapped_rect(child, host)
        natural = _natural_label_width(child)
        if mapped.width() + 1 < natural:
            tooltip = child.toolTip() or ""
            test.assertEqual(
                tooltip,
                text,
                msg=f"{label} truncated label {text!r} has no full tooltip",
            )
            floor = max(child.fontMetrics().averageCharWidth() * 2, 8)
            test.assertGreaterEqual(
                mapped.width(),
                min(natural, floor),
                msg=f"{label} label {text!r} is not readable ({mapped.width()}px)",
            )
        else:
            test.assertGreaterEqual(
                mapped.width(),
                natural - 1,
                msg=f"{label} label {text!r} width {mapped.width()} < natural {natural}",
            )
        if any(char.isalnum() for char in text):
            test.assertGreater(
                mapped.width(),
                2,
                msg=f"{label} label {text!r} collapsed to punctuation",
            )
        if not buddy.isVisible() or buddy.width() <= 0:
            continue
        buddy_rect = _mapped_rect(buddy, host)
        test.assertFalse(
            mapped.intersects(buddy_rect),
            msg=f"{label} label {text!r} overlaps buddy {type(buddy).__name__}",
        )
        host_rect = host.rect().adjusted(-2, -2, 2, 2)
        test.assertTrue(
            host_rect.contains(buddy_rect.topLeft())
            and buddy_rect.right() <= host_rect.right() + 2,
            msg=f"{label} buddy {type(buddy).__name__} overflows the Inspector",
        )


def _assert_sibling_overlap(test, inspector: QWidget, host: QWidget, label: str) -> None:
    parents = {inspector}
    for child in inspector.findChildren(QWidget):
        if child.isVisible():
            parents.add(child)
    for parent in parents:
        visible = []
        for sibling in _direct_children(parent):
            if not sibling.isVisible() or sibling.width() <= 0 or sibling.height() <= 0:
                continue
            visible.append(sibling)
        for index, left in enumerate(visible):
            left_rect = _mapped_rect(left, host)
            for right in visible[index + 1 :]:
                right_rect = _mapped_rect(right, host)
                overlap = left_rect.intersected(right_rect)
                if overlap.width() <= 1 or overlap.height() <= 1:
                    continue
                test.assertFalse(
                    True,
                    msg=(
                        f"{label} siblings overlap: "
                        f"{type(left).__name__}#{left.objectName()} "
                        f"{left_rect.getRect()} vs "
                        f"{type(right).__name__}#{right.objectName()} "
                        f"{right_rect.getRect()}"
                    ),
                )


def _assert_section_groups(test, inspector: QWidget, label: str) -> None:
    from mygui.application_theme import current_density_metrics

    metrics = current_density_metrics()
    gap = metrics.spacing_xs
    groups = [
        group
        for group in inspector.findChildren(InspectorSectionGroup)
        if group.isVisible()
    ]
    for group in groups:
        style_rects = section_group_subcontrol_rects(group)
        box = group.rect()
        padded = box.adjusted(-1, -1, 1, 1)
        title = style_rects["title"]
        indicator = style_rects["indicator"]
        test.assertTrue(
            padded.contains(title),
            msg=f"{label} section {group.title()!r} title {title.getRect()} leaves {box.getRect()}",
        )
        if group.isCheckable():
            test.assertTrue(
                padded.contains(indicator),
                msg=(
                    f"{label} section {group.title()!r} indicator "
                    f"{indicator.getRect()} leaves {box.getRect()}"
                ),
            )
        section = None
        for child in _direct_children(group):
            if child.isVisible() and child.width() > 0 and child.height() > 0:
                section = child
                break
        if section is None:
            continue
        section_rect = QRect(section.mapTo(group, QPoint(0, 0)), section.size())
        test.assertFalse(
            title.intersects(section_rect),
            msg=f"{label} section {group.title()!r} title covers contents",
        )
        if group.isCheckable():
            test.assertFalse(
                indicator.intersects(section_rect),
                msg=f"{label} section {group.title()!r} indicator covers contents",
            )
        title_bottom = title.bottom()
        if group.isCheckable():
            title_bottom = max(title_bottom, indicator.bottom())
        test.assertGreaterEqual(
            section_rect.top(),
            title_bottom + gap - 1,
            msg=(
                f"{label} section {group.title()!r} contents start at "
                f"{section_rect.top()} before title band {title_bottom}+{gap}"
            ),
        )


def _qt_layout(widget: QWidget):
    layout_attr = getattr(widget, "layout", None)
    if callable(layout_attr):
        return layout_attr()
    if isinstance(layout_attr, QLayout):
        return layout_attr
    return QWidget.layout(widget)


def _layout(app: QApplication, widget: QWidget) -> None:
    layout = _qt_layout(widget)
    if layout is not None:
        layout.activate()
    widget.updateGeometry()
    app.processEvents()


def _set_fold(inspector: QWidget, profile, mode: str) -> None:
    groups = inspector.findChildren(InspectorSectionGroup)
    if mode == "default":
        for spec, group in zip(profile.sections, groups, strict=True):
            if group.isCheckable():
                group.setChecked(not spec.collapsed)
        return
    for group in groups:
        if group.isCheckable():
            group.setChecked(True)


class InspectorSwitchIsolationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = _qapp()

    def test_batch_state_stays_on_each_stack(self) -> None:
        import mygui.widgets.fig_control_window.component_editors.inspector_layout as layout_mod

        self.assertFalse(hasattr(layout_mod, "_SWITCH_DEPTH"))
        self.assertFalse(hasattr(layout_mod, "_OUTER_HOST"))
        host_a = QWidget()
        host_b = QWidget()
        stack_a = CurrentPageStackedWidget()
        stack_b = CurrentPageStackedWidget()
        stack_a.attach_switch_host(host_a)
        stack_b.attach_switch_host(host_b)
        stack_a.addWidget(QWidget())
        stack_b.addWidget(QWidget())
        before_a = stack_a._geometry_updates
        before_b = stack_b._geometry_updates
        with inspector_switch_batch(host_a):
            self.assertEqual(stack_a._batch_depth, 1)
            self.assertEqual(stack_b._batch_depth, 0)
            with inspector_switch_batch(stack_a):
                stack_a.request_geometry_refresh()
                stack_a.request_geometry_refresh()
                self.assertEqual(stack_a._geometry_updates, before_a)
        self.assertEqual(stack_a._geometry_updates, before_a + 1)
        self.assertEqual(stack_b._geometry_updates, before_b)
        host_a.deleteLater()
        host_b.deleteLater()
        stack_a.deleteLater()
        stack_b.deleteLater()
        self.app.processEvents()

    def test_cached_page_switch_skips_geometry_flush(self) -> None:
        stack = CurrentPageStackedWidget()
        first = QWidget()
        second = QWidget()
        QVBoxLayout(first)
        QVBoxLayout(second)
        stack.addWidget(first)
        stack.addWidget(second)
        stack.setCurrentWidget(first)
        stack.flush_switch()
        stack.setCurrentWidget(second)
        stack.flush_switch()
        before = stack._geometry_updates
        stack.setCurrentWidget(first)
        stack.setCurrentWidget(second)
        self.assertEqual(stack._geometry_updates, before)
        stack.deleteLater()
        self.app.processEvents()

    def test_cached_switch_shows_leaf_without_axes_panel(self) -> None:
        from mygui.widgets.fig_control_window.figure_inspector import (
            AxesInspectorPanel,
        )

        with tempfile.TemporaryDirectory() as directory:
            qsettings = QSettings(
                str(Path(directory) / "settings.ini"),
                QSettings.IniFormat,
            )
            window = MainWindow(settings=qsettings)
            try:
                canvas = window.figure_window.add_figure(
                    width=4,
                    height=3,
                    dpi=100,
                    style="default",
                    canva_name="LeafSwitch",
                )
                create_regular_axes(canvas)
                canvas.add_component_line(
                    [0.0, 1.0],
                    [0.0, 1.0],
                    object_id="leaf-line",
                )
                self.app.processEvents()
                panel = canvas.figure_inspector
                line = canvas.component_registry.get("leaf-line")
                axes_id = canvas.current_axes_component_id
                self.assertTrue(canvas.select_component(line.component_id))
                self.app.processEvents()
                self.assertIsInstance(panel.current_panel(), AxesInspectorPanel)
                self.assertIsNot(
                    panel.current_panel(),
                    panel.inspector(line.component_id),
                )
                self.assertEqual(
                    panel.axes_inspector(axes_id).parentWidget().objectName(),
                    "inspector_owner_root",
                )
                self.assertTrue(canvas.select_component(canvas.root_component_id))
                self.app.processEvents()
                self.assertIs(panel.current_panel(), panel.root_inspector)
                self.assertEqual(
                    panel.axes_inspector(axes_id).parentWidget().objectName(),
                    "inspector_owner_root",
                )
            finally:
                closer = getattr(window, "close_without_prompt", None)
                if callable(closer):
                    closer()
                else:
                    window.close()
                window.deleteLater()
                self.app.processEvents()

    def test_form_labels_do_not_force_word_wrap(self) -> None:
        editor = QLineEdit()
        label = labeled_form_row("Background color", buddy=editor)
        self.assertFalse(label.wordWrap())
        self.assertFalse(label.hasHeightForWidth())
        self.assertGreater(label.sizeHint().width(), 1)
        self.assertGreaterEqual(
            label.sizeHint().width(),
            label.fontMetrics().horizontalAdvance("Background color"),
        )
        self.assertIs(label.buddy(), editor)
        self.assertEqual(editor.accessibleName(), "Background color")
        short = labeled_form_row("X", buddy=editor)
        self.assertFalse(short.wordWrap())
        self.assertFalse(short.hasHeightForWidth())
        self.assertFalse(hasattr(label, "_hfw_cache"))


class FitResultTablePolicyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = _qapp()

    def test_stretch_columns_and_internal_scroll_after_six_rows(self) -> None:
        table = QTableWidget(8, 3)
        table.setHorizontalHeaderLabels(["Name", "Value", "Unit"])
        configure_inspector_result_table(table)
        for row in range(8):
            for column in range(3):
                item = set_inspector_table_text(
                    table, row, column, f"field-{row}-{column}-long"
                )
                self.assertEqual(item.toolTip(), f"field-{row}-{column}-long")
        table.setFixedWidth(240)
        _layout(self.app, table)
        self.assertEqual(
            table.verticalScrollBarPolicy(),
            Qt.ScrollBarPolicy.ScrollBarAsNeeded,
        )
        self.assertEqual(
            table.horizontalScrollBarPolicy(),
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff,
        )
        self.assertLessEqual(table.width(), 240)
        table.setRowCount(6)
        size_inspector_result_table(table)
        self.assertEqual(
            table.verticalScrollBarPolicy(),
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff,
        )


class InspectorGeometryMatrixTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = _qapp()

    def _close(self, window) -> None:
        closer = getattr(window, "close_without_prompt", None)
        if callable(closer):
            closer()
        else:
            window.close()
        window.deleteLater()
        self.app.processEvents()

    def _prepare_canvas(self, window):
        canvas = window.figure_window.add_figure(
            width=4,
            height=3,
            dpi=100,
            style="default",
            canva_name="InspectorGeometry",
        )
        create_regular_axes(canvas)
        sheet = window.table.current_subtable().get_table(0).table_model.sheet
        sheet.set_block(
            0,
            0,
            [
                [0.0, 1.0, 0.0, 0.0, 1.0],
                [1.0, 2.0, 1.0, 0.0, 2.0],
                [2.0, 3.0, 0.0, 1.0, 3.0],
                [3.0, 4.0, 1.0, 1.0, 4.0],
            ],
        )
        project_id = canvas.project_id
        x_ref = ColumnRef(project_id, sheet.id, sheet.columns[0].id)
        y_ref = ColumnRef(project_id, sheet.id, sheet.columns[1].id)
        gx_ref = ColumnRef(project_id, sheet.id, sheet.columns[2].id)
        gy_ref = ColumnRef(project_id, sheet.id, sheet.columns[3].id)
        gz_ref = ColumnRef(project_id, sheet.id, sheet.columns[4].id)
        line_pair = window.repository.line_pair(x_ref, y_ref)
        valid_pair = window.repository.valid_pair(x_ref, y_ref)
        method = list(interpolate_dict)[2]
        canvas.add_component_line([0.0, 1.0], [0.0, 1.0], object_id="geo-line")
        canvas.add_curve("x", 0.0, 1.0, "-", "#112233", "curve", object_id="geo-curve")
        canvas.add_plot(
            line_pair.x,
            line_pair.y,
            "-",
            2.0,
            "#223344",
            "plot",
            x_ref,
            y_ref,
            object_id="geo-plot",
        )
        canvas.add_scatter(
            valid_pair.x,
            valid_pair.y,
            20.0,
            "#334455",
            "o",
            "scatter",
            x_ref,
            y_ref,
            object_id="geo-scatter",
        )
        canvas.add_fit_curve(
            valid_pair.x,
            valid_pair.y,
            "#445566",
            "fit",
            x_ref,
            y_ref,
            expression="x",
            x_start=0.0,
            x_stop=1.0,
            object_id="geo-fit",
        )
        canvas.add_interpolate_curve(
            valid_pair.x,
            valid_pair.y,
            x_ref,
            y_ref,
            method,
            color="#556677",
            label="interpolation",
            object_id="geo-interp",
        )
        canvas.add_errorbar(x_ref, y_ref, "error", object_id="geo-errorbar")
        canvas.add_text(0.2, 0.8, "note", "sans-serif", 10, object_id="geo-text")
        canvas.add_annotation({"text": "ann"}, object_id="geo-ann")
        canvas.axes_commands.ensure_legend(canvas.current_axes_component_id)
        canvas.add_reference_line(object_id="geo-refline")
        canvas.add_reference_band(object_id="geo-refband")
        canvas.add_reference_marks([0.2, 0.8], object_id="geo-refmarks", announce=False)
        canvas.add_secondary_axis(SecondaryAxisCreateSpec("x"), object_id="geo-sec-x")
        canvas.add_secondary_axis(SecondaryAxisCreateSpec("y"), object_id="geo-sec-y")
        defaults = canvas.component_creation_defaults().in_axes
        canvas.add_in_axes(
            ZoomInAxesCreateSpec(
                bounds=(0.55, 0.55, 0.3, 0.3),
                xlim=(0.0, 1.0),
                ylim=(0.0, 1.0),
                facecolor=defaults.facecolor,
                edgecolor=defaults.edgecolor,
                linewidth=defaults.linewidth,
                indicator_color=defaults.indicator_color,
                indicator_linestyle=defaults.indicator_linestyle,
                indicator_linewidth=defaults.indicator_linewidth,
            ),
            object_id="geo-zoom",
        )
        buffer = BytesIO()
        from PIL import Image
        import base64

        Image.new("RGBA", (4, 3), (20, 40, 80, 128)).save(buffer, format="PNG")
        canvas.add_in_axes(
            ImageInAxesCreateSpec(
                bounds=(0.05, 0.55, 0.3, 0.3),
                filename="sample.png",
                mime_type="image/png",
                payload_base64=base64.b64encode(buffer.getvalue()).decode("ascii"),
                facecolor=defaults.facecolor,
                edgecolor=defaults.edgecolor,
                linewidth=defaults.linewidth,
            ),
            object_id="geo-image",
        )
        canvas.add_pseudocolor(gx_ref, gy_ref, gz_ref, object_id="geo-pseudo")
        canvas.add_heatmap(gx_ref, gy_ref, gz_ref, object_id="geo-heat")
        canvas.add_contour(gx_ref, gy_ref, gz_ref, object_id="geo-contour")
        canvas.add_colorbar("geo-pseudo", object_id="geo-cbar")
        self.app.processEvents()
        return canvas

    def _assert_geometry(self, inspector: QWidget, scroll: QScrollArea, label: str) -> None:
        groups = [
            group
            for group in inspector.findChildren(InspectorSectionGroup)
            if group.isVisible()
        ]
        rects = [_mapped_rect(group, inspector) for group in groups]
        for index, left in enumerate(rects):
            for other in rects[index + 1 :]:
                self.assertFalse(
                    left.intersects(other),
                    msg=f"{label} overlapping section groups",
                )
        host = inspector.rect()
        for child in inspector.findChildren(QWidget):
            if not child.isVisible() or child.width() <= 0 or child.height() <= 0:
                continue
            try:
                if child.window() is not inspector.window():
                    continue
            except RuntimeError:
                continue
            mapped = _mapped_rect(child, inspector)
            self.assertLessEqual(
                mapped.right(),
                host.right() + 2,
                msg=f"{label} {type(child).__name__}#{child.objectName()} overflows width",
            )
            self.assertGreaterEqual(
                mapped.left(),
                host.left() - 2,
                msg=f"{label} {type(child).__name__} overflows left",
            )
        self.assertEqual(
            scroll.horizontalScrollBar().maximum(),
            0,
            msg=f"{label} horizontal scrollbar is active",
        )
        _assert_buddy_labels(self, inspector, inspector, label)
        _assert_sibling_overlap(self, inspector, inspector, label)
        _assert_section_groups(self, inspector, label)
        vertical = scroll.verticalScrollBar()
        if inspector.height() > scroll.viewport().height() + 2:
            self.assertGreater(
                vertical.maximum(),
                0,
                msg=f"{label} bottom content is not reachable",
            )
            vertical.setValue(vertical.maximum())
            self.assertEqual(vertical.value(), vertical.maximum())

    def _host(self, inspector: QWidget, width: int) -> QScrollArea:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll.setFixedSize(width, VIEWPORT_HEIGHT)
        scroll.setWidget(inspector)
        inspector.setMinimumWidth(0)
        inspector.setMaximumWidth(width)
        inspector.resize(width, max(inspector.height(), 1))
        from mygui.widgets.fig_control_window.component_editors.inspector_layout import (
            InspectorFormLabel,
        )

        for form_label in inspector.findChildren(InspectorFormLabel):
            form_label.apply_theme_metrics()
        scroll.show()
        return scroll

    def test_all_34_profiles_geometry_matrix(self) -> None:
        editor_registry = EditorRegistry()
        register_production_profiles(editor_registry)
        expected = {
            (kind, role) for kind, roles in ROLES_BY_KIND.items() for role in roles
        }
        self.assertEqual(len(expected), 34)
        with tempfile.TemporaryDirectory() as directory:
            qsettings = QSettings(
                str(Path(directory) / "settings.ini"),
                QSettings.IniFormat,
            )
            window = MainWindow(settings=qsettings)
            theme = window._resolve_theme_service()
            self.assertIsNotNone(theme)
            origin = theme.snapshot().preferences
            canvas = None
            inspectors: list[QWidget] = []
            hosted: dict[int, QScrollArea] = {}
            try:
                canvas = self._prepare_canvas(window)
                seen: dict[tuple[ComponentKind, ComponentRole], tuple[QWidget, object]] = {}
                for controller in canvas.component_registry.query():
                    key = (controller.state.kind, controller.state.role)
                    if key in seen:
                        continue
                    inspector = canvas.component_editor_manager.create(
                        controller,
                        context=canvas.editor_context,
                    )
                    inspectors.append(inspector)
                    profile = editor_registry.profile_for(*key)
                    seen[key] = (inspector, profile)
                self.assertEqual(set(seen), expected)
                for mode in MODES:
                    for density in DENSITIES:
                        for font_pt in FONTS:
                            theme.apply_committed(
                                AppearancePreferences(
                                    mode=mode,
                                    density=density,
                                    font_pt=font_pt,
                                )
                            )
                            self.app.processEvents()
                            for key, (inspector, profile) in seen.items():
                                kind, role = key
                                for width in WIDTHS:
                                    label = (
                                        f"{kind.value}/{role.value} {width}px "
                                        f"{font_pt}pt {density.value} {mode.value}"
                                    )
                                    with self.subTest(label=label):
                                        previous = hosted.pop(id(inspector), None)
                                        if previous is not None:
                                            previous.takeWidget()
                                            previous.deleteLater()
                                        scroll = self._host(inspector, width)
                                        hosted[id(inspector)] = scroll
                                        _set_fold(inspector, profile, "default")
                                        _layout(self.app, inspector)
                                        self._assert_geometry(
                                            inspector, scroll, f"{label} default"
                                        )
                                        groups = inspector.findChildren(
                                            InspectorSectionGroup
                                        )
                                        for group in groups:
                                            if group.isCheckable() and not group.isChecked():
                                                group.setChecked(True)
                                                _layout(self.app, inspector)
                                                self._assert_geometry(
                                                    inspector,
                                                    scroll,
                                                    f"{label} expand:{group.title()}",
                                                )
                                        _set_fold(inspector, profile, "all_expanded")
                                        _layout(self.app, inspector)
                                        self._assert_geometry(
                                            inspector, scroll, f"{label} all"
                                        )
                host = window.fig_control_window.figure_inspector_host
                host.setFixedWidth(240)
                _layout(self.app, host)
                self.assertEqual(
                    window.fig_control_window.figure_inspector_scroll_area.horizontalScrollBar().maximum(),
                    0,
                )
            finally:
                for scroll in hosted.values():
                    scroll.takeWidget()
                    scroll.deleteLater()
                for inspector in inspectors:
                    inspector.close()
                if canvas is not None:
                    canvas.component_editor_manager.close()
                theme.apply_committed(origin)
                self._close(window)

    def test_range_editor_labels_keep_natural_width(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            qsettings = QSettings(
                str(Path(directory) / "settings.ini"),
                QSettings.IniFormat,
            )
            window = MainWindow(settings=qsettings)
            theme = window._resolve_theme_service()
            origin = theme.snapshot().preferences
            hosted: dict[int, QScrollArea] = {}
            inspector = None
            try:
                canvas = window.figure_window.add_figure(
                    width=4,
                    height=3,
                    dpi=100,
                    style="default",
                    canva_name="RangeEditorLabels",
                )
                create_regular_axes(canvas)
                canvas.add_curve(
                    "x", 0.0, 1.0, "-", "#112233", "curve", object_id="range-curve"
                )
                self.app.processEvents()
                controller = canvas.component_registry.get("range-curve")
                inspector = canvas.component_editor_manager.create(
                    controller,
                    context=canvas.editor_context,
                )
                editors = inspector.findChildren(RangeEditor)
                self.assertTrue(editors)
                range_editor = editors[0]
                for mode in MODES:
                    for density in DENSITIES:
                        for font_pt in FONTS:
                            theme.apply_committed(
                                AppearancePreferences(
                                    mode=mode,
                                    density=density,
                                    font_pt=font_pt,
                                )
                            )
                            self.app.processEvents()
                            for width in WIDTHS:
                                label = (
                                    f"range {width}px {font_pt}pt "
                                    f"{density.value} {mode.value}"
                                )
                                with self.subTest(label=label):
                                    previous = hosted.pop(id(inspector), None)
                                    if previous is not None:
                                        previous.takeWidget()
                                        previous.deleteLater()
                                    scroll = self._host(inspector, width)
                                    hosted[id(inspector)] = scroll
                                    _layout(self.app, inspector)
                                    for field_label, spin in (
                                        (
                                            range_editor.lower_label,
                                            range_editor.minimum_input,
                                        ),
                                        (
                                            range_editor.upper_label,
                                            range_editor.maximum_input,
                                        ),
                                    ):
                                        natural = _natural_label_width(field_label)
                                        mapped = _mapped_rect(field_label, inspector)
                                        self.assertGreaterEqual(
                                            mapped.width(),
                                            natural - 1,
                                            msg=f"{label} {field_label.text()!r} width {mapped.width()} < {natural}",
                                        )
                                        self.assertGreater(
                                            mapped.width(),
                                            2,
                                            msg=f"{label} {field_label.text()!r} is punctuation-only",
                                        )
                                        self.assertIs(field_label.buddy(), spin)
                                        buddy_rect = _mapped_rect(spin, inspector)
                                        self.assertFalse(
                                            mapped.intersects(buddy_rect),
                                            msg=f"{label} {field_label.text()!r} overlaps spin",
                                        )
                                        self.assertLessEqual(
                                            buddy_rect.right(),
                                            inspector.rect().right() + 2,
                                        )
                _assert_section_groups(self, inspector, "range default")
            finally:
                for scroll in hosted.values():
                    scroll.takeWidget()
                    scroll.deleteLater()
                if inspector is not None:
                    inspector.close()
                theme.apply_committed(origin)
                self._close(window)

    def test_section_group_subcontrols_survive_fold_and_theme(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            qsettings = QSettings(
                str(Path(directory) / "settings.ini"),
                QSettings.IniFormat,
            )
            window = MainWindow(settings=qsettings)
            theme = window._resolve_theme_service()
            origin = theme.snapshot().preferences
            inspector = None
            scroll = None
            try:
                canvas = window.figure_window.add_figure(
                    width=4,
                    height=3,
                    dpi=100,
                    style="default",
                    canva_name="SectionGroupChrome",
                )
                create_regular_axes(canvas)
                canvas.add_text(0.2, 0.8, "note", "sans-serif", 10, object_id="sec-text")
                self.app.processEvents()
                controller = canvas.component_registry.get("sec-text")
                inspector = canvas.component_editor_manager.create(
                    controller,
                    context=canvas.editor_context,
                )
                scroll = self._host(inspector, 320)
                groups = inspector.findChildren(InspectorSectionGroup)
                self.assertTrue(groups)
                for mode in (ThemeMode.LIGHT, ThemeMode.DARK):
                    theme.apply_committed(AppearancePreferences(mode=mode, font_pt=9))
                    self.app.processEvents()
                    for group in groups:
                        if group.isCheckable():
                            group.setChecked(False)
                            _layout(self.app, inspector)
                            _assert_section_groups(self, inspector, f"{mode.value} collapsed")
                            group.setChecked(True)
                            _layout(self.app, inspector)
                            _assert_section_groups(self, inspector, f"{mode.value} expanded")
                        else:
                            _layout(self.app, inspector)
                            _assert_section_groups(self, inspector, f"{mode.value} open")
            finally:
                if scroll is not None:
                    scroll.takeWidget()
                    scroll.deleteLater()
                if inspector is not None:
                    inspector.close()
                theme.apply_committed(origin)
                self._close(window)


class InspectorAccessibilityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = _qapp()

    def test_focus_buddy_names_and_disabled_contrast(self) -> None:
        from mygui.application_theme import compose_theme_service

        theme = compose_theme_service(self.app)
        theme.apply_committed(AppearancePreferences(mode=ThemeMode.LIGHT))
        try:
            tokens = current_qss_tokens()
            sheet = render_resource_stylesheet(
                COMPONENT_QSS_RESOURCE,
                theme.snapshot(),
            )
            self.assertIn(":focus", sheet)
            self.assertIn(tokens["UI_RING"].lower(), sheet.lower())
            disabled = contrast_ratio(
                tokens["COLOR_TEXT_MUTED"],
                tokens["UI_MUTED"],
            )
            self.assertGreaterEqual(disabled, 3.0)
            theme.apply_committed(AppearancePreferences(mode=ThemeMode.DARK))
            tokens = current_qss_tokens()
            self.assertGreaterEqual(
                contrast_ratio(tokens["COLOR_TEXT_MUTED"], tokens["UI_MUTED"]),
                3.0,
            )
            theme.apply_committed(AppearancePreferences(mode=ThemeMode.LIGHT))
            editor = QLineEdit()
            editor.setDisabled(True)
            label = labeled_form_row("Long axis label text", buddy=editor)
            self.assertIs(label.buddy(), editor)
            icon = QPushButton()
            icon.setToolTip("Restore defaults")
            icon.setAccessibleName("Restore defaults")
            apply_ui_style(icon, role=UiRole.ICON_BUTTON, variant=UiVariant.GHOST)
            problems = inspect_chrome(icon)
            self.assertEqual(problems, ())
        finally:
            theme.shutdown()

    def test_tab_order_walks_focusable_inspector_controls(self) -> None:
        editor = QLineEdit()
        second = QLineEdit()
        host = QWidget()
        layout = QVBoxLayout(host)
        layout.addWidget(labeled_form_row("First", buddy=editor))
        layout.addWidget(editor)
        layout.addWidget(labeled_form_row("Second", buddy=second))
        layout.addWidget(second)
        host.setTabOrder(editor, second)
        chain = []
        current = editor
        for _ in range(4):
            chain.append(current)
            current = current.nextInFocusChain()
            if current is editor:
                break
        self.assertIn(second, chain)


class EarlyInspectorPerfSmokeTests(unittest.TestCase):
    """Keep this class name so default unittest order runs it before the matrix."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.app = _qapp()

    def test_offscreen_mainwindow_warm_median(self) -> None:
        import statistics
        import time

        if _coverage_tracing():
            self.skipTest(
                "Offscreen MainWindow warm median is gated without coverage tracing."
            )

        samples: list[float] = []
        import gc

        gc.collect()
        with tempfile.TemporaryDirectory() as directory:
            ini = str(Path(directory) / "settings.ini")
            for index in range(23):
                qsettings = QSettings(ini, QSettings.IniFormat)
                started = time.perf_counter()
                window = MainWindow(settings=qsettings)
                self.app.processEvents()
                elapsed = (time.perf_counter() - started) * 1000
                closer = getattr(window, "close_without_prompt", None)
                if callable(closer):
                    closer()
                else:
                    window.close()
                window.deleteLater()
                self.app.processEvents()
                if index >= 3:
                    samples.append(elapsed)
        median = statistics.median(samples)
        self.assertLessEqual(median, 150.0, msg=f"warm median {median:.1f}ms")


if __name__ == "__main__":
    unittest.main()
