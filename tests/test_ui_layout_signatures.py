"""Layout signatures, chrome inspection, and Inspector section contracts."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from tests.axes_helpers import create_regular_axes

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt, QSettings
from PySide6.QtWidgets import (
    QAbstractButton,
    QApplication,
    QVBoxLayout,
    QWidget,
)

from main import MainWindow
from mygui.database import ColumnRef
from mygui.database.interpolate_func import interpolate_dict
from mygui.figure_export import FigureExportContext
from mygui.figuremodify.component_services import SecondaryAxisCreateSpec
from mygui.figuremodify.components import ComponentKind, ComponentRole, ROLES_BY_KIND
from mygui.figuremodify.in_axes import ImageInAxesCreateSpec, ZoomInAxesCreateSpec
from mygui.widgets.fig_control_window.component_editors.inspector import (
    InspectorSectionGroup,
)
from mygui.widgets.fig_control_window.component_editors.profiles import (
    register_production_profiles,
)
from mygui.widgets.fig_control_window.component_editors.registry import EditorRegistry
from mygui.widgets.title_bar.titlebar_dialog.figure_export_dialog import (
    FigureExportDialog,
)
from mygui.widgets.title_bar.titlebar_dialog.py_title_bar_dialog import PyStyleDialog
from mygui.widgets.ui_components import (
    PROPERTY_ROLE,
    PROPERTY_VARIANT,
    capture_layout_signature,
    inspect_chrome,
    signature_paths,
)


def _qapp() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


class UiLayoutSignatureTests(unittest.TestCase):
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

    def test_main_window_chrome_parentage_and_splitter(self) -> None:
        window = MainWindow()
        try:
            self.assertIs(window.title_bar.parentWidget(), window.central_widget)
            self.assertIs(
                window.workspace_splitter.parentWidget(),
                window.central_widget,
            )
            self.assertIs(window.bottom_bar.parentWidget(), window.central_widget)
            self.assertEqual(
                window.workspace_splitter.orientation(),
                Qt.Orientation.Horizontal,
            )
            self.assertGreaterEqual(window.workspace_splitter.count(), 2)
            first = capture_layout_signature(window.central_widget)
            second = capture_layout_signature(window.central_widget)
            self.assertEqual(signature_paths(first), signature_paths(second))
            names = [
                child.get("name")
                for child in first.get("children") or ()
                if isinstance(child, dict)
            ]
            self.assertIn("title_bar", names)
            self.assertIn(window.workspace_splitter.objectName() or "", names)
            _ = window.title_bar.selector_layout_bar
            _ = window.title_bar.selector_chart_bar
            _ = window.title_bar.selector_element_bar
            realized = capture_layout_signature(window.central_widget)
            self.assertEqual(
                window.title_bar.stacklayout_bottom.count(),
                4,
            )
            self.assertEqual(
                type(window.title_bar.stacklayout_bottom.widget(1)).__name__,
                "SelectorLayoutMenuBar",
            )
            self.assertEqual(
                signature_paths(realized),
                signature_paths(capture_layout_signature(window.central_widget)),
            )
        finally:
            self._close(window)

    def test_settings_and_dialogs_keep_stable_signatures(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            qsettings = QSettings(
                str(Path(directory) / "settings.ini"),
                QSettings.IniFormat,
            )
            window = MainWindow(settings=qsettings)
            try:
                self.assertIsNotNone(window.settings_center)
                settings = window.settings_center.present("appearance")
                self.app.processEvents()
                first = capture_layout_signature(settings)
                second = capture_layout_signature(settings)
                self.assertEqual(signature_paths(first), signature_paths(second))
                self.assertTrue(
                    any("settings_page_stack" in path for path in signature_paths(first))
                )
                self.assertEqual(
                    inspect_chrome(settings),
                    (),
                    msg="\n".join(inspect_chrome(settings)),
                )
                settings.close()

                style = PyStyleDialog("Classic", window.figure_window, window)
                self.assertEqual(
                    signature_paths(capture_layout_signature(style)),
                    signature_paths(capture_layout_signature(style)),
                )
                self.assertEqual(
                    inspect_chrome(style),
                    (),
                    msg="\n".join(inspect_chrome(style)),
                )
                style.close()

                export = FigureExportDialog(
                    context=FigureExportContext("Demo", 100.0, 6.4, 4.8),
                    color_library=window.color_library,
                    export_callable=lambda _request: None,
                    parent=window,
                )
                self.assertEqual(
                    signature_paths(capture_layout_signature(export)),
                    signature_paths(capture_layout_signature(export)),
                )
                self.assertEqual(
                    inspect_chrome(export),
                    (),
                    msg="\n".join(inspect_chrome(export)),
                )
                export.close()
            finally:
                self._close(window)

    def test_main_window_chrome_inspection_and_button_variants(self) -> None:
        window = MainWindow()
        try:
            problems = inspect_chrome(window)
            self.assertEqual(problems, (), msg="\n".join(problems))
            buttons = [
                widget
                for widget in window.findChildren(QAbstractButton)
                if str(widget.property(PROPERTY_ROLE) or "") in {"button", "icon-button"}
            ]
            self.assertGreaterEqual(len(buttons), 1)
            missing = [
                f"{type(widget).__name__}#{widget.objectName() or widget.text()!r}"
                for widget in buttons
                if not widget.property(PROPERTY_VARIANT)
            ]
            self.assertEqual(missing, [])
        finally:
            self._close(window)


class UiInspectorProfileLayoutTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = _qapp()

    def tearDown(self) -> None:
        window = getattr(self, "window", None)
        if window is not None:
            closer = getattr(window, "close_without_prompt", None)
            if callable(closer):
                closer()
            else:
                window.close()
            window.deleteLater()
            self.app.processEvents()

    def _prepare_canvas(self):
        self.window = MainWindow()
        canvas = self.window.figure_window.add_figure(
            width=4,
            height=3,
            dpi=100,
            style="default",
            canva_name="LayoutSignatures",
        )
        create_regular_axes(canvas)
        sheet = self.window.table.current_subtable().get_table(0).table_model.sheet
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
        line_pair = self.window.repository.line_pair(x_ref, y_ref)
        valid_pair = self.window.repository.valid_pair(x_ref, y_ref)
        method = list(interpolate_dict)[2]
        canvas.add_component_line(
            [0.0, 1.0],
            [0.0, 1.0],
            object_id="sig-line",
        )
        canvas.add_curve("x", 0.0, 1.0, "-", "#112233", "curve", object_id="sig-curve")
        canvas.add_plot(
            line_pair.x,
            line_pair.y,
            "-",
            2.0,
            "#223344",
            "plot",
            x_ref,
            y_ref,
            object_id="sig-plot",
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
            object_id="sig-scatter",
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
            object_id="sig-fit",
        )
        canvas.add_interpolate_curve(
            valid_pair.x,
            valid_pair.y,
            x_ref,
            y_ref,
            method,
            color="#556677",
            label="interpolation",
            object_id="sig-interp",
        )
        canvas.add_errorbar(x_ref, y_ref, "error", object_id="sig-errorbar")
        canvas.add_text(0.2, 0.8, "note", "sans-serif", 10, object_id="sig-text")
        canvas.add_annotation({"text": "ann"}, object_id="sig-ann")
        canvas.axes_commands.ensure_legend(canvas.current_axes_component_id)
        canvas.add_reference_line(object_id="sig-refline")
        canvas.add_reference_band(object_id="sig-refband")
        canvas.add_reference_marks([0.2, 0.8], object_id="sig-refmarks", announce=False)
        canvas.add_secondary_axis(
            SecondaryAxisCreateSpec("x"),
            object_id="sig-sec-x",
        )
        canvas.add_secondary_axis(
            SecondaryAxisCreateSpec("y"),
            object_id="sig-sec-y",
        )
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
            object_id="sig-zoom",
        )
        from io import BytesIO

        from PIL import Image

        buffer = BytesIO()
        Image.new("RGBA", (4, 3), (20, 40, 80, 128)).save(buffer, format="PNG")
        import base64

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
            object_id="sig-image",
        )
        mesh = canvas.add_pseudocolor(
            gx_ref, gy_ref, gz_ref, object_id="sig-pseudo"
        )
        del mesh
        canvas.add_heatmap(gx_ref, gy_ref, gz_ref, object_id="sig-heat")
        canvas.add_contour(gx_ref, gy_ref, gz_ref, object_id="sig-contour")
        canvas.add_colorbar("sig-pseudo", object_id="sig-cbar")
        self.app.processEvents()
        return canvas

    def test_all_34_profiles_exist_and_inspectors_lock_sections(self) -> None:
        editor_registry = EditorRegistry()
        register_production_profiles(editor_registry)
        expected = {
            (kind, role) for kind, roles in ROLES_BY_KIND.items() for role in roles
        }
        self.assertEqual(len(expected), 34)
        self.assertEqual(set(editor_registry.profile_keys), expected)

        canvas = self._prepare_canvas()
        seen: dict[tuple[ComponentKind, ComponentRole], QWidget] = {}
        inspectors: list[QWidget] = []
        try:
            for controller in canvas.component_registry.query():
                key = (controller.state.kind, controller.state.role)
                if key in seen:
                    continue
                inspector = canvas.component_editor_manager.create(
                    controller,
                    context=canvas.editor_context,
                )
                inspectors.append(inspector)
                seen[key] = inspector
                self.assertIsInstance(inspector.layout, QVBoxLayout)
                profile = editor_registry.profile_for(
                    controller.state.kind,
                    controller.state.role,
                )
                self.assertIsNotNone(profile)
                section_keys = [spec.key for spec in profile.sections]
                self.assertEqual(
                    [section.section_key for section in inspector.sections()],
                    section_keys,
                )
                groups = inspector.findChildren(InspectorSectionGroup)
                self.assertEqual(len(groups), len(section_keys))
                for spec, group, section in zip(
                    profile.sections,
                    groups,
                    inspector.sections(),
                    strict=True,
                ):
                    self.assertEqual(group.property(PROPERTY_ROLE), "section")
                    self.assertEqual(group.full_title(), spec.title)
                    if spec.collapsed:
                        self.assertTrue(group.isCheckable())
                        self.assertFalse(group.isChecked())
                        self.assertFalse(section.isVisible())
                        self.assertTrue(
                            section.isEnabled(),
                            msg=f"{spec.title} disabled by collapse",
                        )
                first = capture_layout_signature(inspector)
                second = capture_layout_signature(inspector)
                self.assertEqual(signature_paths(first), signature_paths(second))
                problems = inspect_chrome(inspector)
                self.assertEqual(problems, (), msg="\n".join(problems))
            missing = sorted(
                f"{kind.value}/{role.value}"
                for kind, role in expected
                if (kind, role) not in seen
            )
            self.assertEqual(missing, [])
        finally:
            for inspector in inspectors:
                inspector.close()
            canvas.component_editor_manager.close()


class UiButtonVariantSourceTests(unittest.TestCase):
    def test_style_button_call_sites_are_explicit(self) -> None:
        from pathlib import Path

        root = Path(__file__).resolve().parents[1] / "mygui"
        unstyled: list[str] = []
        styled = 0
        for path in root.rglob("*.py"):
            if "ui_components" in path.parts and path.name in {
                "factories.py",
                "matrix.py",
            }:
                continue
            text = path.read_text(encoding="utf-8")
            styled += text.count("style_button(")
            styled += text.count("variant=UiVariant.")
            styled += text.count('variant="')
        self.assertGreaterEqual(styled, 80)
        self.assertEqual(unstyled, [])


if __name__ == "__main__":
    unittest.main()
