"""Axes Components creation: Canvas wiring, freeze, rollback, and UI."""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QLabel,
    QPushButton,
    QScrollArea,
    QTabWidget,
)

from matplotlib.colors import to_hex

from main import MainWindow
from mygui.application_settings import (
    AXES_COMPONENT_KEYS,
    COMPONENT_KEYS,
    ApplicationSettingsService,
    AxesComponentDefaults,
    ComponentDefaultsSettings,
    DefaultValueMode,
    InheritableValue,
    MemorySettingsDocumentPort,
)
from mygui.application_settings.document import flatten_snapshot
from mygui.application_settings.models import (
    axes_defaults_from_values,
    axes_defaults_to_values,
)
from mygui.database import ColumnRef
from mygui.figuremodify.axes_layout import (
    AxesCellSpec,
    AxesLayoutSpec,
    AxesViewSpec,
    ShareMode,
)
from mygui.figuremodify.components import (
    ComponentKind,
    ComponentRole,
    ComponentValidationError,
)
from mygui.figuremodify.in_axes import ZoomInAxesCreateSpec
from mygui.figuremodify.style_base.color_models import normalize_color
from mygui.figuremodify.style_base.creation_preferences import resolve_axes_appearance
from mygui.project_io import (
    PROJECT_SCHEMA_VERSION,
    restore_project_snapshot,
    save_project_snapshot,
)
from mygui.widgets.common_widget.min_widget.color_library import ColorLibrary
from mygui.widgets.settings_center.axes_components_page import (
    AxesComponentsSettingsPage,
)
from mygui.widgets.settings_center.inheritable_editors import font_family_item_model
from mygui.widgets.title_bar.titlebar_dialog.py_title_bar_dialog import (
    PyLayoutDialog,
)
from mygui.xrd_refinement import (
    XrdRefinementImportRequest,
    XrdRefinementImportService,
    XrdRefinementLegendSelection,
)
from tests.test_application_settings_component_creation import CountingComponentDefaults
from tests.test_xrd_refinement import small_result


def _override(**items) -> ComponentDefaultsSettings:
    values = axes_defaults_to_values(AxesComponentDefaults())
    for key, value in items.items():
        values[key] = InheritableValue(DefaultValueMode.OVERRIDE, value)
    return ComponentDefaultsSettings(axes=axes_defaults_from_values(values))


def _plain_grid(nrows=1, ncols=1, **kwargs) -> AxesLayoutSpec:
    return AxesLayoutSpec.grid(int(nrows), int(ncols), **kwargs)


class AxesComponentsCreationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.window = MainWindow()
        self.window.figure_window.add_figure(
            width=4,
            height=3,
            dpi=100,
            style="default",
            canva_name="AxesComponents",
        )
        self.canvas = self.window.figure_window.current_canva

    def tearDown(self):
        self.window.close()
        self.app.processEvents()

    def _inject(self, settings: ComponentDefaultsSettings):
        provider = CountingComponentDefaults(settings)
        self.window.figure_window.set_component_defaults_provider(provider)
        return provider

    def _target(self, axes_id: str):
        return self.canvas.component_registry.resolve_target(axes_id)

    def _create(self, spec: AxesLayoutSpec | None = None, **kwargs):
        return self.canvas.create_axes_layout(spec or _plain_grid(), **kwargs)

    def test_override_applies_to_new_axes_and_syncs_registry(self):
        self._inject(
            _override(
                **{
                    "components.axes.facecolor": "#FFCC00",
                    "components.axes.frameon": False,
                    "components.axes.spines.left.color": "#FF0000",
                    "components.axes.spines.left.linewidth": 2.5,
                    "components.axes.x.major.ticks.direction": "in",
                    "components.axes.x.major.grid.visible": True,
                    "components.axes.y.major.grid.visible": True,
                }
            )
        )
        (axes_id,) = self._create()
        target = self._target(axes_id)
        self.assertEqual(normalize_color(target.get_facecolor()), "#FFCC00")
        self.assertFalse(target.get_frame_on())
        self.assertEqual(
            normalize_color(target.spines["left"].get_edgecolor()), "#FF0000"
        )
        self.assertAlmostEqual(float(target.spines["left"].get_linewidth()), 2.5)
        self.assertTrue(any(line.get_visible() for line in target.get_xgridlines()))
        controller = self.canvas.component_registry.get(axes_id)
        self.assertEqual(
            normalize_color(controller.state.properties["facecolor"]), "#FFCC00"
        )
        self.assertFalse(controller.state.properties["frameon"])
        spine = self.canvas.component_registry.find_one(
            parent_id=axes_id,
            kind=ComponentKind.SPINE,
            role=ComponentRole.SPINE,
            selector={"name": "left"},
            recursive=False,
        )
        self.assertEqual(normalize_color(spine.state.properties["color"]), "#FF0000")
        ticks = self.canvas.component_registry.find_one(
            parent_id=axes_id,
            kind=ComponentKind.TICK_GROUP,
            role=ComponentRole.MAJOR_TICK,
            selector={"axis": "x"},
            recursive=True,
        )
        self.assertEqual(ticks.state.properties["direction"], "in")

    def test_apply_does_not_mutate_existing_axes(self):
        (axes_id,) = self._create()
        target = self._target(axes_id)
        before = (
            normalize_color(target.get_facecolor()),
            float(target.spines["left"].get_linewidth()),
        )
        service = ApplicationSettingsService(document=MemorySettingsDocumentPort())
        self.window.figure_window.set_component_defaults_provider(
            service.component_defaults_provider()
        )
        result = service.commit_patch(
            service.begin_session(),
            {
                "components.axes.facecolor": InheritableValue(
                    DefaultValueMode.OVERRIDE, "#00FFAA"
                ),
                "components.axes.spines.left.linewidth": InheritableValue(
                    DefaultValueMode.OVERRIDE, 8.0
                ),
            },
        )
        self.assertTrue(result.success)
        self.assertEqual(
            (
                normalize_color(target.get_facecolor()),
                float(target.spines["left"].get_linewidth()),
            ),
            before,
        )
        (next_id,) = self._create()
        nxt = self._target(next_id)
        self.assertEqual(normalize_color(nxt.get_facecolor()), "#00FFAA")
        self.assertAlmostEqual(float(nxt.spines["left"].get_linewidth()), 8.0)

    def test_explicit_view_beats_override(self):
        self._inject(
            _override(
                **{
                    "components.axes.facecolor": "#FF0000",
                    "components.axes.x.major.grid.visible": True,
                    "components.axes.y.major.grid.visible": True,
                }
            )
        )
        spec = _plain_grid(
            cell_view=AxesViewSpec(
                facecolor="#0000FF",
                x_major_grid=False,
                y_major_grid=False,
            )
        )
        (axes_id,) = self._create(spec)
        target = self._target(axes_id)
        self.assertEqual(normalize_color(target.get_facecolor()), "#0000FF")
        self.assertFalse(any(line.get_visible() for line in target.get_xgridlines()))

    def test_inherit_uses_current_figure_style(self):
        root = self.canvas.component_registry.get(self.canvas.root_component_id)
        self.assertTrue(root.set_property("style", "ggplot").ok)
        self._inject(ComponentDefaultsSettings())
        (axes_id,) = self._create()
        target = self._target(axes_id)
        self.assertTrue(any(line.get_visible() for line in target.get_xgridlines()))
        self.assertTrue(any(line.get_visible() for line in target.get_ygridlines()))

    def test_shared_layout_and_outer_labels_keep_structural_rules(self):
        self._inject(
            _override(
                **{
                    "components.axes.facecolor": "#E8F0FF",
                    "components.axes.x.major.tick_labels.primary_visible": True,
                    "components.axes.spines.bottom.color": "#00AA00",
                }
            )
        )
        spec = AxesLayoutSpec(
            2,
            1,
            (AxesCellSpec(0, 0), AxesCellSpec(1, 0)),
            share_x=ShareMode.ALL,
            outer_x_labels=True,
        )
        top_id, bottom_id = self._create(spec)
        top = self._target(top_id)
        bottom = self._target(bottom_id)
        self.assertEqual(normalize_color(top.get_facecolor()), "#E8F0FF")
        self.assertEqual(normalize_color(bottom.get_facecolor()), "#E8F0FF")
        self.assertEqual(
            normalize_color(top.spines["bottom"].get_edgecolor()), "#00AA00"
        )
        hidden = self.canvas.component_registry.find_one(
            parent_id=top_id,
            kind=ComponentKind.TICK_LABEL_GROUP,
            role=ComponentRole.MAJOR_TICK_LABEL,
            selector={"axis": "x"},
            recursive=True,
        )
        self.assertFalse(hidden.state.properties["primary_visible"])
        shown = self.canvas.component_registry.find_one(
            parent_id=bottom_id,
            kind=ComponentKind.TICK_LABEL_GROUP,
            role=ComponentRole.MAJOR_TICK_LABEL,
            selector={"axis": "x"},
            recursive=True,
        )
        self.assertTrue(shown.state.properties["primary_visible"])

    def test_right_y_structure_wins_over_settings(self):
        self._inject(
            _override(
                **{
                    "components.axes.facecolor": "#FFCC00",
                    "components.axes.spines.left.visible": True,
                    "components.axes.spines.right.visible": True,
                    "components.axes.x.major.ticks.primary_visible": True,
                    "components.axes.y.major.ticks.direction": "in",
                }
            )
        )
        spec = AxesLayoutSpec(
            1,
            1,
            (AxesCellSpec(0, 0, right_y=AxesViewSpec()),),
        )
        primary_id, right_id = self._create(spec)
        primary = self._target(primary_id)
        secondary = self._target(right_id)
        self.assertEqual(normalize_color(primary.get_facecolor()), "#FFCC00")
        self.assertEqual(to_hex(secondary.get_facecolor(), keep_alpha=True).lower(), "#00000000")
        self.assertFalse(secondary.patch.get_visible())
        self.assertFalse(secondary.xaxis.get_visible())
        self.assertFalse(primary.spines["right"].get_visible())
        self.assertFalse(secondary.spines["left"].get_visible())
        y_ticks = self.canvas.component_registry.find_one(
            parent_id=right_id,
            kind=ComponentKind.TICK_GROUP,
            role=ComponentRole.MAJOR_TICK,
            selector={"axis": "y"},
            recursive=True,
        )
        self.assertEqual(y_ticks.state.properties["direction"], "in")

    def test_programmatic_create_reads_provider_once(self):
        provider = self._inject(
            _override(**{"components.axes.facecolor": "#AABBCC"})
        )
        provider.calls = 0
        spec = AxesLayoutSpec(
            1,
            2,
            (AxesCellSpec(0, 0), AxesCellSpec(0, 1)),
        )
        self._create(spec)
        self.assertEqual(provider.calls, 1)

    def test_dialog_freezes_appearance_against_later_apply(self):
        first = _override(**{"components.axes.facecolor": "#112233"})
        self._inject(first)
        dialog = PyLayoutDialog(
            figure_window=self.window.figure_window,
            preset_key="single",
        )
        try:
            frozen = dialog._frozen_appearance
            self.assertEqual(frozen.facecolor, "#112233")
            self.assertEqual(
                normalize_color(dialog.input.facecolor_input.color()),
                "#112233",
            )
            later = _override(**{"components.axes.facecolor": "#FFFFFF"})
            self._inject(later)
            self.assertEqual(dialog._frozen_appearance.facecolor, "#112233")
            self.assertEqual(dialog._frozen_appearance, frozen)
            dialog.accept()
            self.app.processEvents()
            axes = self.canvas.component_registry.query(kind=ComponentKind.AXES)
            self.assertEqual(len(axes), 1)
            target = axes[0].resolve_target()
            self.assertEqual(normalize_color(target.get_facecolor()), "#112233")
        finally:
            dialog.close()
            dialog.deleteLater()

    def test_creation_failure_rolls_back_completely(self):
        self._inject(_override(**{"components.axes.facecolor": "#FF00FF"}))
        before_ids = set(self.canvas._allocated_component_ids)
        before_registry = len(self.canvas.component_registry)
        with mock.patch.object(
            self.canvas.component_registry,
            "validate_axes_targets",
            side_effect=ComponentValidationError("injected axes failure"),
        ):
            with self.assertRaisesRegex(ComponentValidationError, "injected axes failure"):
                self._create()
        self.assertEqual(list(self.canvas.fig.axes), [])
        self.assertEqual(len(self.canvas.component_registry), before_registry)
        self.assertEqual(self.canvas._allocated_component_ids, before_ids)

    def test_appearance_apply_failure_rolls_back(self):
        self._inject(_override(**{"components.axes.facecolor": "#010203"}))
        before_ids = set(self.canvas._allocated_component_ids)
        with mock.patch(
            "mygui.figuremodify.axes_layout_service.apply_resolved_axes_appearance",
            side_effect=RuntimeError("injected appearance failure"),
        ):
            with self.assertRaisesRegex(RuntimeError, "injected appearance failure"):
                self._create()
        self.assertEqual(list(self.canvas.fig.axes), [])
        self.assertEqual(self.canvas._allocated_component_ids, before_ids)

    def test_undo_redo_does_not_reread_settings(self):
        provider = self._inject(
            _override(**{"components.axes.facecolor": "#AA5500"})
        )
        (axes_id,) = self._create()
        original = normalize_color(self._target(axes_id).get_facecolor())
        self.assertEqual(original, "#AA5500")
        stack = self.window.repository.undo_stack(self.canvas.project_id)
        stack.undo()
        self.app.processEvents()
        provider.calls = 0
        self._inject(_override(**{"components.axes.facecolor": "#0000FF"}))
        stack.redo()
        self.app.processEvents()
        restored = self.canvas.component_registry.query(kind=ComponentKind.AXES)
        self.assertEqual(len(restored), 1)
        self.assertEqual(
            normalize_color(restored[0].resolve_target().get_facecolor()),
            "#AA5500",
        )
        self.assertEqual(provider.calls, 0)

    def test_save_open_keeps_created_state_out_of_schema(self):
        self._inject(_override(**{"components.axes.facecolor": "#CCDD11"}))
        (axes_id,) = self._create()
        snapshot = json.dumps(self.canvas.component_snapshot())
        for key in COMPONENT_KEYS:
            self.assertNotIn(key, snapshot)
        path = Path(tempfile.mkdtemp()) / "axes-defaults.mygui.json"
        save_project_snapshot(path, self.window.figure_window)
        payload = path.read_text(encoding="utf-8")
        self.assertIn(f'"schema_version": {PROJECT_SCHEMA_VERSION}', payload)
        for key in COMPONENT_KEYS:
            self.assertNotIn(key, payload)
        provider = CountingComponentDefaults(
            _override(**{"components.axes.facecolor": "#000000"})
        )
        loaded = MainWindow()
        try:
            loaded.figure_window.set_component_defaults_provider(provider)
            restore_project_snapshot(path, loaded.table, loaded.figure_window)
            self.assertEqual(provider.calls, 0)
            canvas = loaded.figure_window.current_canva
            axes = canvas.component_registry.get(axes_id)
            self.assertEqual(
                normalize_color(axes.resolve_target().get_facecolor()),
                "#CCDD11",
            )
        finally:
            loaded.close()
            self.app.processEvents()

    def test_forbidden_paths_do_not_read_provider(self):
        (axes_id,) = self._create()
        original_face = normalize_color(self._target(axes_id).get_facecolor())
        sheet = self.window.table.current_subtable().get_table(0).table_model.sheet
        sheet.set_block(
            0,
            0,
            [[0.0, 1.0, 10.0], [1.0, 2.0, 20.0], [2.0, 4.0, 30.0]],
        )
        x_ref = ColumnRef(self.canvas.project_id, sheet.id, sheet.columns[0].id)
        y_ref = ColumnRef(self.canvas.project_id, sheet.id, sheet.columns[1].id)
        color_ref = ColumnRef(self.canvas.project_id, sheet.id, sheet.columns[2].id)
        pair = self.window.repository.valid_pair(x_ref, y_ref)
        self.canvas.add_scatter(
            pair.x,
            pair.y,
            24.0,
            "#336699",
            "o",
            "temperature",
            x_ref,
            y_ref,
            object_id="mapped-scatter",
            color_ref=color_ref,
            color_mapping={
                "enabled": True,
                "cmap": "viridis",
                "norm": {
                    "kind": "linear",
                    "params": {"vmin": None, "vmax": None, "clip": False},
                },
                "bad": "#00000000",
                "under": None,
                "over": None,
                "nonfinite": "drop",
            },
        )
        provider = self._inject(
            _override(**{"components.axes.facecolor": "#ABCDEF"})
        )
        provider.calls = 0
        layout_id = self.canvas.component_registry.get(axes_id).state.data["subplot"][
            "layout_id"
        ]
        self.canvas.update_axes_layout(
            AxesLayoutSpec(
                1,
                1,
                (AxesCellSpec(0, 0),),
                layout_id=layout_id,
                left=0.15,
            )
        )
        defaults = self.canvas.component_creation_defaults().in_axes
        self.canvas.add_in_axes(
            ZoomInAxesCreateSpec(
                bounds=(0.55, 0.55, 0.35, 0.35),
                xlim=(0.0, 1.0),
                ylim=(0.0, 1.0),
                facecolor=defaults.facecolor,
                edgecolor=defaults.edgecolor,
                linewidth=defaults.linewidth,
                indicator_color=defaults.indicator_color,
                indicator_linestyle=defaults.indicator_linestyle,
                indicator_linewidth=defaults.indicator_linewidth,
            )
        )
        self.canvas.add_colorbar(
            "mapped-scatter",
            {"label": "Temperature", "location": "right"},
            object_id="mapped-colorbar",
        )
        path = Path(tempfile.mkdtemp()) / "no-provider.mygui.json"
        save_project_snapshot(path, self.window.figure_window)
        loaded = MainWindow()
        try:
            loaded.figure_window.set_component_defaults_provider(provider)
            restore_project_snapshot(path, loaded.table, loaded.figure_window)
        finally:
            loaded.close()
            self.app.processEvents()
        stack = self.window.repository.undo_stack(self.canvas.project_id)
        stack.undo()
        stack.redo()
        self.assertEqual(provider.calls, 0)
        self.assertEqual(
            normalize_color(self._target(axes_id).get_facecolor()),
            original_face,
        )

    def test_xrd_explicit_rules_still_win(self):
        self._inject(_override(**{"components.axes.facecolor": "#99AABB"}))
        frozen = resolve_axes_appearance(
            self.canvas.component_creation_defaults().axes,
            self.window.figure_window.snapshot_component_defaults(),
        )
        result = small_result()
        spec = AxesLayoutSpec.grid(1, 1)
        outcome = XrdRefinementImportService(
            canvas=self.canvas,
            table_view=self.window.table,
        ).execute(
            spec,
            XrdRefinementImportRequest(
                result,
                XrdRefinementLegendSelection(False, False, False, False),
                draw_single_residual=False,
            ),
            appearance=frozen,
        )
        target = self._target(outcome.main_axes_id)
        self.assertEqual(normalize_color(target.get_facecolor()), "#99AABB")
        controller = self.canvas.component_registry.get(outcome.main_axes_id)
        self.assertEqual(controller.state.properties["xmargin"], 0.0)
        self.assertTrue(controller.state.properties["autoscalex_on"])


class AxesComponentsSettingsPageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_page_has_ninety_nine_unique_editors_and_copy(self):
        library = ColorLibrary()
        page = AxesComponentsSettingsPage(library)
        self.addCleanup(page.deleteLater)
        editors = page.editors()
        self.assertEqual(set(editors), set(AXES_COMPONENT_KEYS))
        self.assertEqual(len(set(id(widget) for widget in editors.values())), 99)
        tabs = page.findChild(QTabWidget, "settings_axes_components_tabs")
        self.assertIsNotNone(tabs)
        for index in range(tabs.count()):
            self.assertIsInstance(tabs.widget(index), QScrollArea)
        self.assertEqual(len(page.findChildren(QLabel, "settings_page_intro")), 1)
        for key, label in page.buddy_labels().items():
            self.assertTrue(label.buddy() is not None, key)
        boxes = {box.text() for box in page.findChildren(QCheckBox)}
        self.assertIn("Use Figure style", boxes)
        values = page.draft_values()
        for key in AXES_COMPONENT_KEYS:
            self.assertEqual(values[key].mode, DefaultValueMode.INHERIT, key)
        source = "components.axes.x.major.ticks.direction"
        dest = "components.axes.y.major.ticks.direction"
        page._rows[source].inherit_box.setChecked(False)
        page._rows[source].set_value(
            InheritableValue(DefaultValueMode.OVERRIDE, "inout")
        )
        page._copy_prefix("components.axes.x.", "components.axes.y.")
        copied = page.draft_values()[dest]
        self.assertEqual(copied.mode, DefaultValueMode.OVERRIDE)
        self.assertEqual(copied.value, "inout")
        page._copy_prefix(
            "components.axes.x.major.", "components.axes.x.minor."
        )
        minor = page.draft_values()["components.axes.x.minor.ticks.direction"]
        self.assertEqual(minor.value, "inout")
        axisbelow = page._rows["components.axes.axisbelow"]
        axisbelow.inherit_box.setChecked(False)
        axisbelow.set_value(InheritableValue(DefaultValueMode.OVERRIDE, True))
        self.assertIs(axisbelow.value().value, True)
        axisbelow.set_value(InheritableValue(DefaultValueMode.OVERRIDE, "line"))
        self.assertEqual(axisbelow.value().value, "line")
        for editor in page.keyboard_editors():
            self.assertTrue(
                int(editor.focusPolicy()) & int(Qt.TabFocus),
                editor.objectName(),
            )
        copy_buttons = [
            button.text()
            for button in page.findChildren(QPushButton)
            if "Copy" in button.text()
        ]
        self.assertIn("Copy X → Y", copy_buttons)
        self.assertIn("Copy Y → X", copy_buttons)
        self.assertIn("Copy Major → Minor", copy_buttons)
        self.assertIn("Copy Minor → Major", copy_buttons)
        recents = list(library.recent_colors)
        color_row = page._rows["components.axes.facecolor"]
        color_row.inherit_box.setChecked(False)
        color_row.value_editor.set_color("#123456", emit=True, record_recent=False)
        self.assertEqual(library.recent_colors, recents)
        self.assertEqual(library.favorite_colors, [])
        alpha = page._rows["components.axes.x.major.grid.alpha"]
        self.assertFalse(alpha.value_editor.isEnabled())
        alpha.inherit_box.setChecked(False)
        self.assertTrue(alpha._optional_none.isChecked())
        self.assertFalse(alpha._optional_spin.isEnabled())
        self.assertIsNone(alpha.value().value)

    def test_keyboard_order_follows_the_ninety_nine_keys(self):
        page = AxesComponentsSettingsPage(ColorLibrary())
        self.addCleanup(page.deleteLater)
        widgets = page.keyboard_editors()
        inherit_boxes = [
            page._rows[key].inherit_box for key in AXES_COMPONENT_KEYS
        ]
        self.assertEqual(widgets[0], inherit_boxes[0])
        positions = [widgets.index(box) for box in inherit_boxes]
        self.assertEqual(positions, sorted(positions))

    def test_font_family_combos_share_one_catalog_model(self):
        page = AxesComponentsSettingsPage(ColorLibrary())
        self.addCleanup(page.deleteLater)
        combos = [
            row.value_editor
            for key, row in page._rows.items()
            if key.endswith(".fontfamily")
        ]
        self.assertGreaterEqual(len(combos), 2)
        self.assertTrue(all(isinstance(combo, QComboBox) for combo in combos))
        for combo in combos:
            combo.attach_catalog()
        models = {combo.model() for combo in combos}
        self.assertEqual(len(models), 1)
        self.assertIs(next(iter(models)), font_family_item_model())
        self.assertGreater(font_family_item_model().rowCount(), 5)

    def test_hosted_page_does_not_repeat_the_shell_intro(self):
        service = ApplicationSettingsService(document=MemorySettingsDocumentPort())
        session = service.begin_session()

        class _Host:
            def draft_value(self, key: str):
                values = flatten_snapshot(service.snapshot())
                values.update(session.dirty_patch())
                return values[key]

            def stage_value(self, key: str, value) -> None:
                session.stage(key, value)

            def bind_draft_reloaded(self, _callback) -> None:
                return

        page = AxesComponentsSettingsPage(ColorLibrary(), host=_Host())
        self.addCleanup(page.deleteLater)
        self.assertEqual(page.findChildren(QLabel, "settings_page_intro"), [])
        self.assertLess(len(page._rows), 99)
        page._ensure_all_tabs()
        self.assertEqual(len(page._rows), 99)


if __name__ == "__main__":
    unittest.main()
