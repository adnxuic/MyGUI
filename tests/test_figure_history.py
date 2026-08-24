"""Project-level Table/Figure Undo/Redo integration coverage."""

from __future__ import annotations

from copy import deepcopy
import base64
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeyEvent, QTextCursor
from PySide6.QtWidgets import (
    QApplication,
    QLineEdit,
    QPlainTextEdit,
    QSpinBox,
)

from main import MainWindow
from mygui import status_messages
from mygui.database import ColumnRef, TableChangeSet, TableMutationCommand
from mygui.database.interpolate_func import interpolate_dict
from mygui.figuremodify.components import ComponentKind, ComponentRole
from mygui.figuremodify.in_axes import (
    ImageInAxesCreateSpec,
    ZoomInAxesCreateSpec,
)
from mygui.figuremodify.style_base.color_models import (
    ColorSelection,
    PaletteDefinition,
)
from mygui.project_io import (
    PROJECT_SCHEMA_VERSION,
    load_project_file,
    restore_project_snapshot,
    save_project_snapshot,
)
from mygui.widgets.figure_canvas.py_figure_window import (
    _ProjectHistoryShortcutFilter,
)
from tests.axes_helpers import create_regular_axes
from tests.test_in_axes import image_payload


MAPPED_COLOR = {
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
}


class FigureHistoryIntegrationTests(unittest.TestCase):
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
            canva_name="HistoryProject",
        )
        self.canvas = self.window.figure_window.current_canva
        self.stack = self.window.repository.undo_stack(self.canvas.project_id)
        self.stack.clear()

    def tearDown(self):
        status_messages.clear_status_handler()
        self.window.close_without_prompt()
        self.app.processEvents()

    def _create_axes_baseline(self):
        axes_id = create_regular_axes(self.canvas)[0]
        self.stack.clear()
        return axes_id

    def _add_text_inspector(
        self,
        *,
        object_id: str,
        text: str = "before",
        x: float = 0.25,
        y: float = 0.75,
    ):
        self.canvas.add_text(
            x,
            y,
            text,
            "DejaVu Sans",
            12,
            usetex=False,
            object_id=object_id,
        )
        controller = self.canvas.component_registry.get(object_id)
        inspector = self.canvas.create_component_editor(object_id)
        return controller, inspector

    def _create_text_inspector(
        self,
        *,
        object_id: str = "history-inspector-text",
        text: str = "before",
    ):
        self._create_axes_baseline()
        controller, inspector = self._add_text_inspector(
            object_id=object_id,
            text=text,
        )
        self.stack.clear()
        return controller, inspector

    def test_property_edits_merge_and_noop_does_not_pollute_history(self):
        controller = self.canvas.component_registry.get(
            self.canvas.root_component_id
        )
        before = controller.read_state().properties["facecolor"]

        result = self.canvas.editor_context.perform(
            "Change Figure Facecolor",
            lambda: controller.set_property("facecolor", before),
            merge_key=("property", controller.component_id, "facecolor"),
        )
        self.assertTrue(result.ok)
        self.assertEqual(self.stack.count(), 0)

        for color in ("#112233", "#445566"):
            result = self.canvas.editor_context.perform(
                "Change Figure Facecolor",
                lambda value=color: controller.set_property(
                    "facecolor", value
                ),
                merge_key=("property", controller.component_id, "facecolor"),
            )
            self.assertTrue(result.ok)

        self.assertEqual(self.stack.count(), 1)
        self.assertIn("Facecolor", self.stack.undoText())
        self.stack.undo()
        self.assertEqual(controller.state.properties["facecolor"], before)
        self.stack.redo()
        self.assertEqual(
            controller.state.properties["facecolor"], "#445566"
        )

    def test_text_content_inspector_edit_enters_history_and_replays_service(self):
        controller, inspector = self._create_text_inspector()
        content = inspector.section("content")
        editor = content.text_content
        editor.setPlainText("afte")
        editor.moveCursor(QTextCursor.End)
        editor.insertPlainText("r")

        self.assertTrue(content.set_text_content())

        self.assertEqual(controller.resolve_target().get_text(), "after")
        self.assertEqual(controller.read_state().properties["text"], "after")
        self.assertEqual(editor.toPlainText(), "after")
        self.assertEqual(editor.textCursor().position(), len("after"))
        self.assertEqual(self.stack.count(), 1)
        self.assertEqual(self.stack.undoText(), "Change Text Content")

        original_apply = self.canvas.text_render_service.apply
        with mock.patch.object(
            self.canvas.text_render_service,
            "apply",
            wraps=original_apply,
        ) as apply_spy:
            self.stack.undo()
            self.assertGreaterEqual(apply_spy.call_count, 1)
            self.assertEqual(controller.resolve_target().get_text(), "before")
            self.assertEqual(
                controller.read_state().properties["text"],
                "before",
            )
            self.assertEqual(editor.toPlainText(), "before")

            apply_spy.reset_mock()
            self.stack.redo()
            self.assertGreaterEqual(apply_spy.call_count, 1)

        self.assertEqual(controller.resolve_target().get_text(), "after")
        self.assertEqual(controller.read_state().properties["text"], "after")
        self.assertEqual(editor.toPlainText(), "after")

    def test_text_content_debounced_inspector_edits_merge(self):
        controller, inspector = self._create_text_inspector()
        content = inspector.section("content")
        editor = content.text_content

        for value in ("one", "two", "final"):
            editor.setPlainText(value)
            self.assertTrue(content.set_text_content())

        self.assertEqual(self.stack.count(), 1)
        self.assertEqual(self.stack.undoText(), "Change Text Content")
        self.assertEqual(controller.read_state().properties["text"], "final")
        self.stack.undo()
        self.assertEqual(controller.resolve_target().get_text(), "before")
        self.assertEqual(controller.read_state().properties["text"], "before")
        self.assertEqual(editor.toPlainText(), "before")
        self.stack.redo()
        self.assertEqual(controller.resolve_target().get_text(), "final")
        self.assertEqual(controller.read_state().properties["text"], "final")
        self.assertEqual(editor.toPlainText(), "final")

    def test_repeated_text_typography_property_edits_merge(self):
        controller, inspector = self._create_text_inspector()
        typography = inspector.section("typography")
        before_size = float(controller.read_state().properties["fontsize"])

        for size in (before_size + 1.0, before_size + 2.0, before_size + 3.0):
            self.assertTrue(typography.apply_property("fontsize", size))

        self.assertEqual(self.stack.count(), 1)
        self.assertEqual(self.stack.undoText(), "Change Text Font Size")
        self.stack.undo()
        self.assertEqual(
            float(controller.read_state().properties["fontsize"]),
            before_size,
        )
        self.stack.redo()
        self.assertEqual(
            float(controller.read_state().properties["fontsize"]),
            before_size + 3.0,
        )

    def test_different_text_inspector_properties_do_not_merge(self):
        controller, inspector = self._create_text_inspector()
        content = inspector.section("content")
        typography = inspector.section("typography")
        before_size = float(controller.read_state().properties["fontsize"])

        content.text_content.setPlainText("after")
        self.assertTrue(content.set_text_content())
        self.assertTrue(
            typography.apply_property("fontsize", before_size + 6.0)
        )

        self.assertEqual(self.stack.count(), 2)
        self.assertEqual(self.stack.undoText(), "Change Text Font Size")
        self.stack.undo()
        self.assertEqual(controller.read_state().properties["text"], "after")
        self.assertEqual(
            float(controller.read_state().properties["fontsize"]),
            before_size,
        )
        self.assertEqual(content.text_content.toPlainText(), "after")
        self.stack.undo()
        self.assertEqual(controller.read_state().properties["text"], "before")
        self.stack.redo()
        self.assertEqual(controller.read_state().properties["text"], "after")
        self.stack.redo()
        self.assertEqual(
            float(controller.read_state().properties["fontsize"]),
            before_size + 6.0,
        )

    def test_same_text_property_on_different_components_does_not_merge(self):
        self._create_axes_baseline()
        first, first_inspector = self._add_text_inspector(
            object_id="history-text-a",
            text="A",
        )
        second, second_inspector = self._add_text_inspector(
            object_id="history-text-b",
            text="B",
        )
        first_before = first.read_state().properties["color"]
        second_before = second.read_state().properties["color"]
        self.stack.clear()

        self.assertTrue(
            first_inspector.section("typography").apply_property(
                "color",
                "#112233",
            )
        )
        self.assertTrue(
            second_inspector.section("typography").apply_property(
                "color",
                "#445566",
            )
        )

        self.assertEqual(self.stack.count(), 2)
        self.stack.undo()
        self.assertEqual(first.read_state().properties["color"], "#112233")
        self.assertEqual(second.read_state().properties["color"], second_before)
        self.stack.undo()
        self.assertEqual(first.read_state().properties["color"], first_before)
        self.stack.redo()
        self.stack.redo()
        self.assertEqual(first.read_state().properties["color"], "#112233")
        self.assertEqual(second.read_state().properties["color"], "#445566")

    def test_noop_text_inspector_property_does_not_create_history(self):
        controller, inspector = self._create_text_inspector()
        typography = inspector.section("typography")
        before = controller.read_state()

        self.assertTrue(
            typography.apply_property(
                "fontsize",
                before.properties["fontsize"],
            )
        )

        self.assertEqual(controller.read_state(), before)
        self.assertEqual(self.stack.count(), 0)
        self.assertFalse(self.stack.canUndo())
        self.assertFalse(self.stack.canRedo())

    def test_failed_text_inspector_render_creates_no_history(self):
        controller, inspector = self._create_text_inspector()
        content = inspector.section("content")
        before = controller.state.clone()
        content.text_content.setPlainText("broken")

        with mock.patch.object(
            controller.resolve_target().figure.canvas,
            "draw",
            side_effect=RuntimeError("synthetic text render failure"),
        ):
            self.assertFalse(content.set_text_content())

        self.assertEqual(controller.state, before)
        self.assertEqual(controller.resolve_target().get_text(), "before")
        self.assertEqual(content.text_content.toPlainText(), "before")
        self.assertEqual(self.stack.count(), 0)
        self.assertFalse(self.stack.canUndo())
        self.assertFalse(self.stack.canRedo())

    def test_all_text_property_sections_enter_project_history(self):
        controller, inspector = self._create_text_inspector()
        before = controller.read_state().properties
        changes = (
            ("typography", "fontsize", float(before["fontsize"]) + 3.0),
            ("transform", "rotation", 35.0),
            ("position", "position", (0.4, 0.6)),
            ("advanced", "clip_on", not bool(before["clip_on"])),
        )

        for section_key, property_key, value in changes:
            self.assertTrue(
                inspector.section(section_key).apply_property(
                    property_key,
                    value,
                )
            )

        final = controller.read_state().properties
        self.assertEqual(self.stack.count(), len(changes))
        self.assertEqual(self.stack.undoText(), "Change Text Clip On")
        target = controller.resolve_target()
        self.assertEqual(float(target.get_fontsize()), final["fontsize"])
        self.assertEqual(float(target.get_rotation()), final["rotation"])
        self.assertEqual(tuple(target.get_position()), final["position"])
        self.assertEqual(bool(target.get_clip_on()), final["clip_on"])

        for _section_key, _property_key, _value in changes:
            self.stack.undo()
        restored = controller.read_state().properties
        for _section_key, property_key, _value in changes:
            self.assertEqual(restored[property_key], before[property_key])

        for _section_key, _property_key, _value in changes:
            self.stack.redo()
        replayed = controller.read_state().properties
        for _section_key, property_key, value in changes:
            self.assertEqual(replayed[property_key], value)

    def test_multi_property_text_patch_is_one_atomic_unmerged_command(self):
        controller, inspector = self._create_text_inspector()
        typography = inspector.section("typography")
        before = controller.read_state().properties
        patch = {
            "fontsize": float(before["fontsize"]) + 2.0,
            "color": "#224466",
        }
        original_apply = self.canvas.text_render_service.apply

        with mock.patch.object(
            self.canvas.text_render_service,
            "apply",
            wraps=original_apply,
        ) as apply_spy:
            result = typography._apply_properties(patch)

        self.assertTrue(result.ok)
        self.assertEqual(apply_spy.call_count, 1)
        self.assertEqual(self.stack.count(), 1)
        self.assertEqual(self.stack.undoText(), "Change Text Properties")

        second_patch = {
            "fontsize": patch["fontsize"] + 1.0,
            "color": "#446688",
        }
        second_result = typography._apply_properties(second_patch)
        self.assertTrue(second_result.ok)
        self.assertEqual(self.stack.count(), 2)

        self.stack.undo()
        intermediate = controller.read_state().properties
        self.assertEqual(intermediate["fontsize"], patch["fontsize"])
        self.assertEqual(intermediate["color"], patch["color"])
        self.stack.undo()
        restored = controller.read_state().properties
        self.assertEqual(restored["fontsize"], before["fontsize"])
        self.assertEqual(restored["color"], before["color"])
        self.stack.redo()
        replayed = controller.read_state().properties
        self.assertEqual(replayed["fontsize"], patch["fontsize"])
        self.assertEqual(replayed["color"], patch["color"])
        self.stack.redo()
        final = controller.read_state().properties
        self.assertEqual(final["fontsize"], second_patch["fontsize"])
        self.assertEqual(final["color"], second_patch["color"])

    def test_text_render_section_creates_exactly_one_history_command(self):
        self._create_axes_baseline()
        controller, _inspector = self._add_text_inspector(
            object_id="history-render-text",
        )
        target = controller.resolve_target()
        self.canvas.text_render_service.tex_enabled = lambda: True

        with (
            mock.patch(
                "mygui.widgets.fig_control_window.component_editors."
                "sections.tex_config.is_tex_enabled",
                return_value=True,
            ),
            mock.patch.object(target.figure.canvas, "draw", return_value=None),
        ):
            inspector = self.canvas.create_component_editor(
                controller.component_id
            )
            render = inspector.section("render")
            self.stack.clear()

            self.assertTrue(render.set_tex_render(True))
            self.assertEqual(self.stack.count(), 1)
            self.assertEqual(
                self.stack.undoText(),
                "Enable Text TeX Rendering",
            )
            self.assertTrue(controller.read_state().properties["usetex"])
            self.stack.undo()
            self.assertFalse(controller.read_state().properties["usetex"])
            self.stack.redo()
            self.assertTrue(controller.read_state().properties["usetex"])

    def test_axes_creation_undo_redo_restores_exact_stable_tree(self):
        before = deepcopy(self.canvas.component_snapshot())
        axes_ids = create_regular_axes(self.canvas, 1, 2)
        after = deepcopy(self.canvas.component_snapshot())
        self.assertEqual(self.stack.count(), 1)
        self.assertEqual(
            self.canvas.current_component_id,
            axes_ids[0],
        )

        self.stack.undo()
        self.assertEqual(self.canvas.component_snapshot(), before)
        self.assertFalse(
            self.canvas.component_registry.query(kind=ComponentKind.AXES)
        )

        self.stack.redo()
        self.assertEqual(self.canvas.component_snapshot(), after)
        self.assertEqual(
            tuple(
                controller.component_id
                for controller in self.canvas.component_registry.query(
                    kind=ComponentKind.AXES
                )
            ),
            axes_ids,
        )

    def test_component_create_delete_branch_and_selection_are_reversible(self):
        axes_id = self._create_axes_baseline()
        self.canvas.add_component_line(
            [0.0, 1.0],
            [1.0, 2.0],
            color="#123456",
            label="history-line",
            object_id="history-line-id",
        )
        created = deepcopy(self.canvas.component_snapshot())
        self.assertEqual(self.stack.count(), 1)

        self.stack.undo()
        self.assertNotIn("history-line-id", self.canvas.component_registry)
        self.stack.redo()
        self.assertEqual(self.canvas.component_snapshot(), created)
        self.assertIn("history-line-id", self.canvas.component_registry)

        self.canvas.select_component("history-line-id")
        self.stack.clear()
        before_delete = deepcopy(self.canvas.component_snapshot())
        self.assertTrue(
            self.canvas.delete_component_group(
                ("history-line-id",),
                "line",
            )
        )
        after_selection = self.canvas.current_component_id
        self.assertNotIn("history-line-id", self.canvas.component_registry)

        self.stack.undo()
        self.assertEqual(self.canvas.component_snapshot(), before_delete)
        self.assertEqual(self.canvas.current_component_id, "history-line-id")
        self.assertEqual(self.canvas.current_axes_component_id, axes_id)

        self.stack.redo()
        self.assertNotIn("history-line-id", self.canvas.component_registry)
        self.assertEqual(self.canvas.current_component_id, after_selection)

        self.stack.undo()
        controller = self.canvas.component_registry.get("history-line-id")
        result = self.canvas.editor_context.perform(
            "Change Line Label",
            lambda: controller.set_property("label", "new branch"),
        )
        self.assertTrue(result.ok)
        self.assertFalse(self.stack.canRedo())

    def test_reference_marks_create_edit_delete_undo_redo_and_dirty_state(self):
        self._create_axes_baseline()
        self.canvas.add_reference_marks(
            [15.2, 22.9],
            {"label": "YBCO"},
            object_id="history-reference-marks",
            announce=False,
        )
        self.assertEqual(self.stack.count(), 1)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "reference-history.mygui.json"
            save_project_snapshot(path, self.window.figure_window)
            self.assertFalse(
                self.window.figure_window.is_canvas_dirty(self.canvas)
            )

            controller = self.canvas.component_registry.get(
                "history-reference-marks"
            )
            original_artist = controller.resolve_target()
            self.assertTrue(
                self.canvas.editor_context.perform(
                    "Change Reflection Positions Data",
                    lambda: self.canvas.reference_marks_service.update_positions(
                        controller,
                        [22.9, 15.2, 15.2],
                    ),
                ).ok
            )
            self.assertTrue(
                self.window.figure_window.is_canvas_dirty(self.canvas)
            )
            self.assertEqual(self.stack.count(), 2)
            self.stack.undo()
            self.assertEqual(controller.state.data["positions"], [15.2, 22.9])
            self.assertFalse(
                self.window.figure_window.is_canvas_dirty(self.canvas)
            )
            self.stack.redo()
            self.assertEqual(
                controller.state.data["positions"],
                [22.9, 15.2, 15.2],
            )
            self.assertTrue(
                self.window.figure_window.is_canvas_dirty(self.canvas)
            )

        self.assertTrue(
            self.canvas.editor_context.perform(
                "Change Reflection Positions Style",
                lambda: self.canvas.reference_marks_service.apply_properties(
                    controller,
                    {"baseline": 0.2, "height": 0.3, "color": "#123456"},
                ),
            ).ok
        )
        edited = deepcopy(controller.state)
        self.assertIs(controller.resolve_target(), original_artist)
        self.canvas.select_component(controller.component_id)
        self.assertTrue(
            self.canvas.delete_component_group(
                (controller.component_id,),
                "Reflection Positions",
            )
        )
        post_delete_selection = self.canvas.current_component_id
        self.assertNotIn(controller.component_id, self.canvas.component_registry)
        self.assertNotIn(original_artist, self.canvas.current_axes.collections)

        self.stack.undo()
        restored = self.canvas.component_registry.get(
            "history-reference-marks"
        )
        self.assertEqual(restored.state, edited)
        self.assertEqual(
            self.canvas.current_component_id,
            "history-reference-marks",
        )
        self.assertEqual(len(restored.resolve_target().get_segments()), 3)
        self.stack.redo()
        self.assertNotIn(
            "history-reference-marks",
            self.canvas.component_registry,
        )
        self.assertEqual(self.canvas.current_component_id, post_delete_selection)

    def test_all_dynamic_materializers_replay_one_project_timeline(self):
        self._create_axes_baseline()
        sheet = (
            self.window.table.current_subtable()
            .get_table(0)
            .table_model.sheet
        )
        sheet.set_block(
            0,
            0,
            [[0.0, 1.0], [1.0, 2.0], [2.0, 4.0], [3.0, 8.0]],
        )
        x_ref = ColumnRef(
            self.canvas.project_id,
            sheet.id,
            sheet.columns[0].id,
        )
        y_ref = ColumnRef(
            self.canvas.project_id,
            sheet.id,
            sheet.columns[1].id,
        )
        line_pair = self.window.repository.line_pair(x_ref, y_ref)
        valid_pair = self.window.repository.valid_pair(x_ref, y_ref)
        baseline = deepcopy(self.canvas.component_snapshot())

        self.canvas.add_plot(
            line_pair.x,
            line_pair.y,
            "-",
            2.0,
            "#112233",
            "plot",
            x_ref,
            y_ref,
            object_id="history-plot",
        )
        self.canvas.add_scatter(
            valid_pair.x,
            valid_pair.y,
            20.0,
            "#223344",
            "o",
            "scatter",
            x_ref,
            y_ref,
            object_id="history-scatter",
            color_ref=y_ref,
            color_mapping=deepcopy(MAPPED_COLOR),
        )
        self.canvas.add_colorbar(
            "history-scatter",
            {"label": "Mapped"},
            object_id="history-colorbar",
        )
        self.canvas.add_curve(
            "x**2",
            0.0,
            3.0,
            "-",
            "#334455",
            "function",
            object_id="history-function",
        )
        self.canvas.add_component_line(
            [0.0, 1.0],
            [2.0, 3.0],
            color="#445566",
            label="line",
            object_id="history-generic-line",
        )
        self.canvas.add_reference_marks(
            [15.2, 15.2, 22.9],
            {"label": "YBCO"},
            object_id="history-reference-marks",
            announce=False,
        )
        self.canvas.add_interpolate_curve(
            valid_pair.x,
            valid_pair.y,
            x_ref,
            y_ref,
            list(interpolate_dict)[2],
            samples=32,
            color="#556677",
            object_id="history-interpolation",
        )
        self.canvas.add_fit_curve(
            valid_pair.x,
            valid_pair.y,
            "#667788",
            "fit",
            x_ref,
            y_ref,
            fit_type="poly2",
            fit_result={
                "formula": "x**2",
                "coefficients": [],
                "goodness": {},
            },
            expression="x**2",
            x_start=0.0,
            x_stop=3.0,
            object_id="history-fit",
        )
        self.canvas.add_text(
            0.25,
            0.75,
            "axes text",
            "DejaVu Sans",
            12,
            object_id="history-axes-text",
        )
        self.canvas.add_global_text(
            0.5,
            0.5,
            "figure text",
            "DejaVu Sans",
            14,
            object_id="history-figure-text",
        )
        defaults = self.canvas.component_creation_defaults().in_axes
        self.canvas.add_in_axes(
            ZoomInAxesCreateSpec(
                bounds=(0.55, 0.55, 0.35, 0.35),
                xlim=(0.0, 1.0),
                ylim=(0.0, 2.0),
                facecolor=defaults.facecolor,
                edgecolor=defaults.edgecolor,
                linewidth=defaults.linewidth,
                indicator_color=defaults.indicator_color,
            ),
            object_id="history-zoom",
        )
        self.canvas.add_in_axes(
            ImageInAxesCreateSpec(
                bounds=(0.05, 0.55, 0.35, 0.35),
                filename="embedded.png",
                mime_type="image/png",
                payload_base64=base64.b64encode(image_payload()).decode(
                    "ascii"
                ),
                facecolor=defaults.facecolor,
                edgecolor=defaults.edgecolor,
                linewidth=defaults.linewidth,
            ),
            object_id="history-image",
        )
        final = deepcopy(self.canvas.component_snapshot())
        command_count = self.stack.count()
        self.assertEqual(command_count, 12)

        while self.stack.canUndo():
            self.stack.undo()
        self.assertEqual(self.canvas.component_snapshot(), baseline)

        while self.stack.canRedo():
            self.stack.redo()
        self.assertEqual(self.canvas.component_snapshot(), final)
        expected_ids = {
            "history-plot",
            "history-scatter",
            "history-colorbar",
            "history-function",
            "history-generic-line",
            "history-reference-marks",
            "history-interpolation",
            "history-fit",
            "history-axes-text",
            "history-figure-text",
            "history-zoom",
            "history-image",
        }
        self.assertTrue(
            expected_ids.issubset(
                {
                    controller.component_id
                    for controller in self.canvas.component_registry.query()
                }
            )
        )

    def test_palette_cursor_and_runtime_ledger_are_reversible(self):
        axes_id = self._create_axes_baseline()
        palette = PaletteDefinition(
            "history:palette",
            "History Palette",
            ("#112233", "#445566", "#778899"),
        )
        self.canvas.figure_history.perform(
            "Change Axes Palette",
            lambda: self.canvas.axes_commands.apply_palette(
                axes_id,
                palette,
            ),
        )
        self.stack.clear()
        selection = self.canvas.creation_color_cycle().peek()
        self.assertIsInstance(selection, ColorSelection)
        self.canvas.add_curve(
            "x",
            0.0,
            1.0,
            "-",
            selection.color,
            "palette curve",
            object_id="history-palette-curve",
            color_selection=selection,
        )
        after_creation = (
            self.canvas.axes_commands.cycle_state(axes_id).next_index,
            self.canvas.color_consumption_ledger.history_snapshot(),
        )
        self.assertEqual(after_creation[0], 1)

        self.stack.undo()
        self.assertEqual(
            self.canvas.axes_commands.cycle_state(axes_id).next_index,
            0,
        )
        self.assertEqual(
            self.canvas.color_consumption_ledger.history_snapshot(),
            {},
        )
        self.stack.redo()
        self.assertEqual(
            (
                self.canvas.axes_commands.cycle_state(axes_id).next_index,
                self.canvas.color_consumption_ledger.history_snapshot(),
            ),
            after_creation,
        )

        self.stack.clear()
        self.canvas.select_component("history-palette-curve")
        self.assertTrue(
            self.canvas.delete_component_group(
                ("history-palette-curve",),
                "function curve",
            )
        )
        self.assertEqual(
            self.canvas.axes_commands.cycle_state(axes_id).next_index,
            0,
        )
        self.stack.undo()
        self.assertEqual(
            self.canvas.axes_commands.cycle_state(axes_id).next_index,
            1,
        )
        self.assertEqual(
            self.canvas.color_consumption_ledger.history_snapshot(),
            after_creation[1],
        )

    def test_specialized_text_legend_and_function_services_replay(self):
        axes_id = self._create_axes_baseline()
        self.canvas.add_curve(
            "x",
            0.0,
            1.0,
            "-",
            "#112233",
            "function",
            object_id="service-function",
        )
        self.canvas.add_text(
            0.25,
            0.75,
            "before",
            "DejaVu Sans",
            12,
            object_id="service-text",
        )
        self.canvas.axes_commands.ensure_legend(axes_id)
        function = self.canvas.component_registry.get("service-function")
        text = self.canvas.component_registry.get("service-text")
        legend = self.canvas.component_registry.find_one(
            parent_id=axes_id,
            kind=ComponentKind.LEGEND,
            role=ComponentRole.LEGEND,
            recursive=False,
        )
        self.stack.clear()
        baseline = deepcopy(self.canvas.component_snapshot())

        self.canvas.figure_history.perform(
            "Change Function Curve Expression",
            lambda: self.canvas.function_curve_service.update(
                function,
                "x**2 + 1",
                0.0,
                2.0,
            ),
        )
        self.canvas.figure_history.perform(
            "Change Text Content",
            lambda: self.canvas.text_render_service.apply(
                text,
                {"text": "after"},
            ),
        )
        self.canvas.figure_history.perform(
            "Change Legend Location",
            lambda: self.canvas.axes_commands.apply_legend_properties(
                legend,
                {
                    "location": {
                        "kind": "preset",
                        "value": "upper left",
                    }
                },
            ),
        )
        final = deepcopy(self.canvas.component_snapshot())
        self.assertEqual(self.stack.count(), 3)

        while self.stack.canUndo():
            self.stack.undo()
        self.assertEqual(self.canvas.component_snapshot(), baseline)
        while self.stack.canRedo():
            self.stack.redo()
        self.assertEqual(self.canvas.component_snapshot(), final)

    def test_specialized_data_fit_interpolation_and_colorbar_replay(self):
        self._create_axes_baseline()
        sheet = (
            self.window.table.current_subtable()
            .get_table(0)
            .table_model.sheet
        )
        sheet.set_block(
            0,
            0,
            [[0.0, 1.0], [1.0, 2.0], [2.0, 4.0], [3.0, 8.0]],
        )
        x_ref = ColumnRef(
            self.canvas.project_id,
            sheet.id,
            sheet.columns[0].id,
        )
        y_ref = ColumnRef(
            self.canvas.project_id,
            sheet.id,
            sheet.columns[1].id,
        )
        pair = self.window.repository.valid_pair(x_ref, y_ref)
        self.canvas.add_scatter(
            pair.x,
            pair.y,
            20.0,
            "#223344",
            "o",
            "scatter",
            x_ref,
            y_ref,
            object_id="service-scatter",
            color_ref=y_ref,
            color_mapping=deepcopy(MAPPED_COLOR),
        )
        self.canvas.add_colorbar(
            "service-scatter",
            {"label": "Mapped"},
            object_id="service-colorbar",
        )
        self.canvas.add_interpolate_curve(
            pair.x,
            pair.y,
            x_ref,
            y_ref,
            list(interpolate_dict)[2],
            samples=32,
            object_id="service-interpolation",
        )
        self.canvas.add_fit_curve(
            pair.x,
            pair.y,
            "#334455",
            "fit",
            x_ref,
            y_ref,
            fit_type="poly2",
            expression="x**2",
            x_start=0.0,
            x_stop=3.0,
            object_id="service-fit",
        )
        scatter = self.canvas.component_registry.get("service-scatter")
        colorbar = self.canvas.component_registry.get("service-colorbar")
        interpolation = self.canvas.component_registry.get(
            "service-interpolation"
        )
        fit = self.canvas.component_registry.get("service-fit")
        self.stack.clear()
        baseline = deepcopy(self.canvas.component_snapshot())

        mapping = deepcopy(scatter.state.properties["color_mapping"])
        mapping["cmap"] = "plasma"
        self.canvas.figure_history.perform(
            "Change Scatter Mapping",
            lambda: self.canvas.chart_data_service.configure_scatter_mapping(
                scatter,
                color_ref=y_ref,
                size_ref=None,
                color_mapping=mapping,
                size_mapping=scatter.state.properties["size_mapping"],
            ),
        )
        self.canvas.figure_history.perform(
            "Change Colorbar Location",
            lambda: self.canvas.colorbar_service.apply_properties(
                colorbar,
                {"location": "left"},
            ),
        )
        interpolation_data = interpolation.state.data
        self.canvas.figure_history.perform(
            "Change Interpolation Configuration",
            lambda: self.canvas.interpolation_service.configure(
                interpolation,
                x_ref=interpolation_data["x_ref"],
                y_ref=interpolation_data["y_ref"],
                preprocess=interpolation_data["preprocess"],
                method=interpolation_data["method"],
                k=interpolation_data["k"],
                samples=64,
                lam=interpolation_data["lam"],
                lam_auto=interpolation_data["lam_auto"],
            ),
        )
        fit_data = fit.state.data
        self.canvas.figure_history.perform(
            "Apply Fit Result",
            lambda: self.canvas.fit_service.apply_result(
                fit,
                engine=fit_data["engine"],
                fit_type=fit_data["fit_type"],
                fit_options=fit_data["fit_options"],
                fit_result={
                    "formula": "2*x",
                    "coefficients": [],
                    "goodness": {},
                },
                expression="2*x",
                x_start=0.0,
                x_stop=3.0,
            ),
        )
        final = deepcopy(self.canvas.component_snapshot())
        self.assertEqual(self.stack.count(), 4)

        while self.stack.canUndo():
            self.stack.undo()
        self.assertEqual(self.canvas.component_snapshot(), baseline)
        while self.stack.canRedo():
            self.stack.redo()
        self.assertEqual(self.canvas.component_snapshot(), final)

    def test_axes_deletion_restores_ids_layout_and_sibling_order(self):
        axes_ids = create_regular_axes(self.canvas, 1, 2)
        self.stack.clear()
        self.canvas.select_component(axes_ids[1])
        baseline = deepcopy(self.canvas.component_snapshot())

        self.assertTrue(self.canvas.delete_axes(axes_ids[0]))
        deleted = deepcopy(self.canvas.component_snapshot())
        self.assertNotIn(axes_ids[0], self.canvas.component_registry)

        self.stack.undo()
        self.assertEqual(self.canvas.component_snapshot(), baseline)
        self.assertEqual(self.canvas.current_component_id, axes_ids[1])
        self.stack.redo()
        self.assertEqual(self.canvas.component_snapshot(), deleted)
        self.assertNotIn(axes_ids[0], self.canvas.component_registry)

    def test_multi_series_creation_and_batch_delete_are_atomic_commands(self):
        axes_id = self._create_axes_baseline()
        sheet = (
            self.window.table.current_subtable()
            .get_table(0)
            .table_model.sheet
        )
        sheet.set_block(
            0,
            0,
            [[0.0, 1.0, 2.0], [1.0, 2.0, 3.0], [2.0, 4.0, 6.0]],
        )
        refs = [
            ColumnRef(self.canvas.project_id, sheet.id, column.id)
            for column in sheet.columns[:3]
        ]
        palette = PaletteDefinition(
            "history:batch",
            "History Batch",
            ("#112233", "#445566", "#778899"),
        )
        self.canvas.figure_history.perform(
            "Change Axes Palette",
            lambda: self.canvas.axes_commands.apply_palette(
                axes_id,
                palette,
            ),
        )
        self.stack.clear()
        baseline = deepcopy(self.canvas.component_snapshot())

        result = self.canvas.add_plots(
            refs[0],
            refs[1:],
            style="-",
            size=6.0,
            linewidth=1.5,
            preprocess=None,
            color_selection=ColorSelection(
                palette.colors[0],
                palette,
                0,
            ),
        )
        self.assertEqual(len(result.component_ids), 2)
        created = deepcopy(self.canvas.component_snapshot())
        self.assertEqual(self.stack.count(), 1)
        self.assertEqual(self.stack.undoText(), "Create Plots")

        self.stack.undo()
        self.assertEqual(self.canvas.component_snapshot(), baseline)
        self.stack.redo()
        self.assertEqual(self.canvas.component_snapshot(), created)

        self.stack.clear()
        self.assertTrue(
            self.canvas.delete_component_group(
                result.component_ids,
                "data plot",
            )
        )
        self.assertEqual(self.stack.count(), 1)
        for component_id in result.component_ids:
            self.assertNotIn(component_id, self.canvas.component_registry)
        self.stack.undo()
        self.assertEqual(self.canvas.component_snapshot(), created)

    def test_project_stacks_are_isolated_when_switching_tabs(self):
        first = self.canvas
        first_root = first.component_registry.get(first.root_component_id)
        first.figure_history.perform(
            "Change First Figure",
            lambda: first_root.set_property("facecolor", "#112233"),
        )
        first_stack = self.window.repository.undo_stack(first.project_id)

        self.window.figure_window.add_figure(
            width=4,
            height=3,
            dpi=100,
            style="default",
            canva_name="SecondHistoryProject",
        )
        second = self.window.figure_window.current_canva
        second_stack = self.window.repository.undo_stack(second.project_id)
        second_stack.clear()
        second_root = second.component_registry.get(second.root_component_id)
        second.figure_history.perform(
            "Change Second Figure",
            lambda: second_root.set_property("edgecolor", "#445566"),
        )

        self.assertEqual(first_stack.count(), 1)
        self.assertEqual(second_stack.count(), 1)
        second.figure_history.undo()
        self.assertNotEqual(
            first_root.state.properties["facecolor"],
            "#ffffff",
        )
        self.assertEqual(
            second_root.state.properties["edgecolor"],
            "#ffffff",
        )

        self.window.figure_window.tabwindow.setCurrentWidget(first)
        first.figure_history.undo()
        self.assertEqual(
            first_root.state.properties["facecolor"],
            "#ffffff",
        )
        self.assertEqual(second_stack.index(), 0)

    def test_history_is_runtime_only_and_reopen_starts_empty(self):
        self._create_axes_baseline()
        self.canvas.add_component_line(
            [0, 1],
            [1, 2],
            object_id="runtime-only-history-line",
        )
        self.assertEqual(self.stack.count(), 1)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "history-runtime-only.mygui.json"
            save_project_snapshot(path, self.window.figure_window)
            raw = load_project_file(path)
            self.assertEqual(PROJECT_SCHEMA_VERSION, 13)
            self.assertEqual(
                set(raw["figure"]),
                {"root_component_id", "components"},
            )
            self.assertEqual(self.stack.count(), 1)

            loaded = MainWindow()
            try:
                restore_project_snapshot(
                    path,
                    loaded.table,
                    loaded.figure_window,
                )
                restored = loaded.figure_window.current_canva
                restored_stack = loaded.repository.undo_stack(
                    restored.project_id
                )
                self.assertEqual(restored_stack.count(), 0)
                self.assertFalse(restored_stack.canUndo())
                self.assertFalse(restored_stack.canRedo())
            finally:
                loaded.close_without_prompt()
                self.app.processEvents()

    def test_table_and_figure_commands_share_one_chronological_stack(self):
        self._create_axes_baseline()
        root = self.canvas.component_registry.get(self.canvas.root_component_id)
        original_color = root.state.properties["facecolor"]
        changed_color = "#334455"
        self.canvas.figure_history.perform(
            "Change Figure Facecolor",
            lambda: root.set_property("facecolor", changed_color),
        )

        project = self.window.repository.project(self.canvas.project_id)
        sheet = next(iter(project.sheets.values()))
        column = sheet.columns[0]
        ref = ColumnRef(project.id, sheet.id, column.id)
        self.window.repository.push(
            project.id,
            TableMutationCommand(
                "Edit cell",
                self.window.repository,
                project.id,
                lambda: sheet.set_cell(0, column.id, "17"),
                lambda: sheet.set_cell(0, column.id, ""),
                TableChangeSet(project.id, {ref}, reason="cell-edit"),
            ),
        )
        self.canvas.add_component_line(
            [0, 1],
            [2, 3],
            object_id="timeline-line",
        )
        self.assertEqual(self.stack.count(), 3)

        self.stack.undo()
        self.assertNotIn("timeline-line", self.canvas.component_registry)
        self.assertEqual(sheet.frame.at[0, column.id], 17.0)
        self.stack.undo()
        self.assertTrue(sheet.frame.at[0, column.id] is None or bool(
            getattr(sheet.frame.at[0, column.id], "isna", False)
        ) or str(sheet.frame.at[0, column.id]) == "<NA>")
        self.assertEqual(root.state.properties["facecolor"], changed_color)
        self.stack.undo()
        self.assertEqual(root.state.properties["facecolor"], original_color)

        self.stack.redo()
        self.stack.redo()
        self.stack.redo()
        self.assertEqual(root.state.properties["facecolor"], changed_color)
        self.assertEqual(sheet.frame.at[0, column.id], 17.0)
        self.assertIn("timeline-line", self.canvas.component_registry)

    def test_undo_back_to_save_baseline_clears_dirty_state(self):
        root = self.canvas.component_registry.get(self.canvas.root_component_id)
        self.window.figure_window.mark_canvas_clean(self.canvas)
        self.assertFalse(self.window.figure_window.is_canvas_dirty(self.canvas))

        self.canvas.figure_history.perform(
            "Change Figure Edgecolor",
            lambda: root.set_property("edgecolor", "#112233"),
        )
        self.assertTrue(self.window.figure_window.is_canvas_dirty(self.canvas))
        self.stack.undo()
        self.assertFalse(self.window.figure_window.is_canvas_dirty(self.canvas))
        self.stack.redo()
        self.assertTrue(self.window.figure_window.is_canvas_dirty(self.canvas))

    def test_save_baseline_prevents_property_merge_across_clean_index(self):
        root = self.canvas.component_registry.get(self.canvas.root_component_id)
        merge_key = ("property", root.component_id, "facecolor")
        self.canvas.figure_history.perform(
            "Change Figure Facecolor",
            lambda: root.set_property("facecolor", "#112233"),
            merge_key=merge_key,
        )
        self.window.figure_window.mark_canvas_clean(self.canvas)
        self.assertTrue(self.stack.isClean())

        self.canvas.figure_history.perform(
            "Change Figure Facecolor",
            lambda: root.set_property("facecolor", "#445566"),
            merge_key=merge_key,
        )
        self.assertEqual(self.stack.count(), 2)
        self.stack.undo()
        self.assertEqual(root.state.properties["facecolor"], "#112233")
        self.assertTrue(self.stack.isClean())
        self.assertFalse(self.window.figure_window.is_canvas_dirty(self.canvas))

    def test_project_rename_replays_repository_tab_and_controller(self):
        original = self.canvas.project_name
        self.window.figure_window.rename_project(
            self.canvas.project_id,
            "RenamedHistoryProject",
        )
        self.assertEqual(self.canvas.project_name, "RenamedHistoryProject")
        self.assertEqual(
            self.window.figure_window.tabwindow.tabText(0),
            "RenamedHistoryProject",
        )

        self.stack.undo()
        self.assertEqual(self.canvas.project_name, original)
        self.assertEqual(self.window.figure_window.tabwindow.tabText(0), original)
        self.stack.redo()
        self.assertEqual(self.canvas.project_name, "RenamedHistoryProject")

    def test_failed_replay_reports_once_and_invalidates_history(self):
        controller = self.canvas.component_registry.get(
            self.canvas.root_component_id
        )
        self.canvas.figure_history.perform(
            "Change Figure Facecolor",
            lambda: controller.set_property("facecolor", "#224466"),
        )
        self.canvas.message_presenter.discard_pending()
        messages = []
        status_messages.set_status_handler(
            lambda text, level: messages.append((text, level))
        )
        original_apply = controller.apply_state
        calls = 0

        def fail_once(state):
            nonlocal calls
            calls += 1
            if calls == 1:
                raise RuntimeError("synthetic history replay failure")
            return original_apply(state)

        with mock.patch.object(controller, "apply_state", side_effect=fail_once):
            self.stack.undo()
        self.app.processEvents()

        self.assertEqual(self.stack.count(), 0)
        errors = [item for item in messages if item[1] == "error"]
        self.assertEqual(len(errors), 1)
        self.assertIn("synthetic history replay failure", errors[0][0])

    def test_actions_and_native_text_routing_contract(self):
        axes_id = self._create_axes_baseline()
        self.canvas.add_component_line(
            [0, 1],
            [0, 1],
            object_id="action-line",
        )
        self.assertTrue(self.canvas.undo_action.isEnabled())
        self.assertIn("Create Line", self.canvas.undo_action.text())

        key = QKeyEvent(
            QKeyEvent.Type.KeyPress,
            Qt.Key.Key_Z,
            Qt.KeyboardModifier.ControlModifier,
        )
        self.window.figure_window._history_shortcut_filter.eventFilter(
            self.window,
            key,
        )
        self.assertNotIn("action-line", self.canvas.component_registry)
        self.assertTrue(self.canvas.redo_action.isEnabled())

        self.stack.clear()
        axes = self.canvas.component_registry.get(axes_id)
        before_limits = tuple(axes.read_state().properties["xlim"])
        self.assertTrue(
            self.canvas.figure_history.begin_interaction("Pan Figure View")
        )
        axes.resolve_target().set_xlim(2.0, 5.0)
        self.canvas.figure_history.end_interaction()
        self.assertEqual(self.stack.count(), 1)
        self.stack.undo()
        self.assertEqual(
            tuple(axes.read_state().properties["xlim"]),
            before_limits,
        )
        self.stack.redo()
        self.assertEqual(
            tuple(axes.read_state().properties["xlim"]),
            (2.0, 5.0),
        )

        line = QLineEdit()
        line.setText("before")
        line.setModified(False)
        line.insert("-pending")
        self.assertTrue(
            _ProjectHistoryShortcutFilter._native_text_history_available(
                line,
                redo=False,
            )
        )
        line.setModified(False)
        self.assertFalse(
            _ProjectHistoryShortcutFilter._native_text_history_available(
                line,
                redo=False,
            )
        )

        plain = QPlainTextEdit()
        plain.setPlainText("before")
        plain.document().setModified(False)
        plain.insertPlainText(" pending")
        self.assertTrue(
            _ProjectHistoryShortcutFilter._native_text_history_available(
                plain,
                redo=False,
            )
        )

        spin = QSpinBox()
        spin_line = spin.findChild(QLineEdit)
        spin_line.setModified(True)
        self.assertFalse(
            _ProjectHistoryShortcutFilter._native_text_history_available(
                spin_line,
                redo=False,
            )
        )


if __name__ == "__main__":
    unittest.main()
