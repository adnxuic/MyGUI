import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tests.axes_helpers import create_regular_axes

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QEvent
from PySide6.QtWidgets import QApplication, QDialog, QFileDialog, QMessageBox

from mygui import status_messages, tex_config
from mygui.figuremodify.components import (
    ComponentEventKind,
    ComponentKind,
    ComponentRole,
)
from mygui.figuremodify.style_base.color_models import (
    ColorSelection,
    PaletteDefinition,
)
from mygui.project_io import (
    load_project_file,
    project_snapshot,
    restore_project_snapshot,
)
from mygui.widgets.component_tree.dialogs import (
    ComponentBatchDeleteDialog,
)
from mygui.widgets.component_tree.model import ComponentTreeModel
from mygui.widgets.figure_canvas.py_figure_canves import PyFigureCanvas
from main import MainWindow


class ComponentDeletionAndProjectCloseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.window = MainWindow()
        self.window.figure_window.add_figure(
            width=4,
            height=3,
            dpi=100,
            style="default",
            canva_name="DeleteProject",
        )
        self.canvas = self.window.figure_window.current_canva
        create_regular_axes(self.canvas)

    def tearDown(self):
        status_messages.clear_status_handler()
        self.window.close_without_prompt()
        self.app.processEvents()
        self.directory.cleanup()

    def _add_curves(self):
        self.canvas.add_curve(
            "x",
            0.0,
            1.0,
            "-",
            "#112233",
            "first",
            object_id="curve-first",
        )
        self.canvas.add_curve(
            "x**2",
            0.0,
            1.0,
            "--",
            "#445566",
            "second",
            object_id="curve-second",
        )
        inspector = self.canvas.figure_inspector.axes_inspector(
            self.canvas.current_axes_component_id
        )
        toolbox = inspector.component_toolbox(
            (ComponentKind.LINE, ComponentRole.FUNCTION_CURVE),
        )
        return inspector, toolbox

    def _replace_with_two_by_two_axes(self):
        existing = list(
            self.canvas.component_registry.query(kind=ComponentKind.AXES)
        )
        for controller in reversed(existing):
            self.assertTrue(self.canvas.delete_axes(controller.component_id))
        create_regular_axes(self.canvas, 2, 2)
        self.canvas.fig.canvas.draw()
        axes = sorted(
            self.canvas.component_registry.query(kind=ComponentKind.AXES),
            key=lambda item: item.state.selector["index"],
        )
        self.assertEqual(len(axes), 4)
        return axes

    def _assert_two_by_two_delete_preserves_layout(self, deleted_index):
        axes = self._replace_with_two_by_two_axes()

        def bounds(controller):
            return tuple(
                float(value)
                for value in controller.resolve_target().get_position().bounds
            )

        before = {}
        for controller in axes:
            target = controller.resolve_target()
            subplot_spec = target.get_subplotspec()
            target_bounds = bounds(controller)
            self.assertNotIn("position", controller.state.properties)
            before[controller.component_id] = {
                "bounds": target_bounds,
                "subplot": controller.state.data["subplot"].copy(),
                "spec": (
                    subplot_spec.get_geometry(),
                    subplot_spec.num1,
                    subplot_spec.num2,
                ),
            }

        deleted = axes[deleted_index]
        self.assertTrue(self.canvas.delete_axes(deleted.component_id))
        self.canvas.fig.canvas.draw()

        remaining = sorted(
            self.canvas.component_registry.query(kind=ComponentKind.AXES),
            key=lambda item: item.state.selector["index"],
        )
        expected_ids = [
            controller.component_id
            for controller in axes
            if controller.component_id != deleted.component_id
        ]
        self.assertEqual(
            [controller.component_id for controller in remaining],
            expected_ids,
        )
        self.assertEqual(
            [controller.state.selector["index"] for controller in remaining],
            [0, 1, 2],
        )
        self.assertEqual(
            [controller.state.order for controller in remaining],
            [0, 1, 2],
        )
        for controller in remaining:
            target = controller.resolve_target()
            subplot_spec = target.get_subplotspec()
            expected = before[controller.component_id]
            self.assertEqual(
                controller.state.data["subplot"],
                expected["subplot"],
            )
            self.assertEqual(
                (
                    subplot_spec.get_geometry(),
                    subplot_spec.num1,
                    subplot_spec.num2,
                ),
                expected["spec"],
            )
            for actual, original in zip(
                bounds(controller), expected["bounds"]
            ):
                self.assertAlmostEqual(actual, original, places=12)
            self.assertNotIn("position", controller.state.properties)
        self.assertEqual(
            len({bounds(controller) for controller in remaining}),
            len(remaining),
        )

    def test_batch_dialog_defaults_to_all_and_disables_empty_confirmation(self):
        dialog = ComponentBatchDeleteDialog(
            (("one", "curve0"), ("two", "curve1")),
            role_label="function curve",
        )
        try:
            self.assertEqual(dialog.selected_component_ids(), ["one", "two"])
            self.assertEqual(dialog.delete_button.text(), "Delete (2)")
            self.assertTrue(dialog.delete_button.isEnabled())

            dialog._set_all_checked(False)
            self.assertEqual(dialog.selected_component_ids(), [])
            self.assertEqual(dialog.delete_button.text(), "Delete (0)")
            self.assertFalse(dialog.delete_button.isEnabled())

            dialog._checkboxes[1].setChecked(True)
            self.assertEqual(dialog.selected_component_ids(), ["two"])
            self.assertEqual(dialog.delete_button.text(), "Delete (1)")
        finally:
            dialog.close()
            dialog.deleteLater()
            QApplication.sendPostedEvents(None, QEvent.DeferredDelete)
            self.app.processEvents()

    def test_tree_delete_flow_uses_the_explicit_component_once(self):
        _inspector, toolbox = self._add_curves()
        second = self.canvas.component_editor_manager.editor("curve-second")
        host = self.window.component_tree_host
        self.assertTrue(self.canvas.select_component("curve-first"))
        messages = []
        status_messages.set_status_handler(
            lambda text, level: messages.append((text, level))
        )

        self.assertTrue(
            self.canvas.delete_component_group(
                ("curve-first",),
                "function curve",
            )
        )
        self.app.processEvents()

        self.assertNotIn("curve-first", self.canvas.component_registry)
        self.assertIn("curve-second", self.canvas.component_registry)
        self.assertIs(toolbox.currentWidget(), second)
        self.assertEqual(self.canvas.current_component_id, "curve-second")
        self.assertEqual(host.tree.selected_component_id(), "curve-second")
        self.assertEqual(toolbox.count(), 1)
        self.assertEqual(len(messages), 1)

    def test_successful_delete_publishes_one_batch_refresh_draw_selection_message(self):
        self._add_curves()
        self.assertTrue(self.canvas.select_component("curve-first"))
        self.app.processEvents()
        registry_batches = []
        tree_refreshes = []
        selections = []
        messages = []
        unsubscribe = self.canvas.component_registry.subscribe_batches(
            registry_batches.append
        )
        self.window.component_tree_host.model.refreshed.connect(
            lambda: tree_refreshes.append(True)
        )
        self.canvas.componentSelectionChanged.connect(selections.append)
        status_messages.set_status_handler(
            lambda text, level: messages.append((text, level))
        )
        try:
            with mock.patch.object(
                self.canvas.canva,
                "draw_idle",
                wraps=self.canvas.canva.draw_idle,
            ) as draw_idle:
                self.assertTrue(
                    self.canvas.delete_component_group(
                        ("curve-first",),
                        "function curve",
                    )
                )
            self.app.processEvents()
        finally:
            unsubscribe()

        self.assertEqual(len(registry_batches), 1)
        self.assertEqual(tree_refreshes, [True])
        draw_idle.assert_called_once_with()
        self.assertEqual(selections, ["curve-second"])
        self.assertEqual(len(messages), 1)
        self.assertEqual(messages[0][1], "success")

    def test_post_commit_runtime_refresh_failure_keeps_selection_and_warns(self):
        self._add_curves()
        self.assertTrue(self.canvas.select_component("curve-first"))
        messages = []
        status_messages.set_status_handler(
            lambda text, level: messages.append((text, level))
        )

        with mock.patch.object(
            self.canvas.axes_layout_service,
            "restore_runtime_relationships",
            side_effect=RuntimeError("injected runtime refresh failure"),
        ):
            self.assertTrue(
                self.canvas.delete_component_group(
                    ("curve-first",),
                    "function curve",
                )
            )

        self.assertNotIn("curve-first", self.canvas.component_registry)
        self.assertEqual(self.canvas.current_component_id, "curve-second")
        self.assertEqual(len(messages), 1)
        self.assertEqual(messages[0][1], "warning")
        self.assertIn("runtime relationship", messages[0][0])

    def test_leaf_inspector_cleanup_failure_is_one_committed_warning(self):
        _panel, toolbox = self._add_curves()
        editor = self.canvas.component_editor_manager.editor("curve-first")
        self.assertIsNotNone(editor)
        messages = []
        status_messages.set_status_handler(
            lambda text, level: messages.append((text, level))
        )

        with mock.patch.object(
            editor,
            "dispose",
            side_effect=RuntimeError("injected leaf Inspector cleanup failure"),
        ):
            self.assertTrue(
                self.canvas.delete_component_group(
                    ("curve-first",),
                    "function curve",
                )
            )

        self.assertNotIn("curve-first", self.canvas.component_registry)
        self.assertIsNone(self.canvas.component_editor_manager.editor("curve-first"))
        self.assertEqual(toolbox.component_ids(), ("curve-second",))
        self.assertEqual(len(messages), 1)
        self.assertEqual(messages[0][1], "warning")
        self.assertIn("Inspector cleanup", messages[0][0])

    def test_role_dialog_partial_selection_deletes_only_checked_instance(self):
        _inspector, toolbox = self._add_curves()
        host = self.window.component_tree_host
        state = self.canvas.component_registry.get("curve-first").state
        self.canvas.select_component("curve-first")

        def accept_partial(dialog):
            dialog._checkboxes[1].setChecked(False)
            return QDialog.Accepted

        with mock.patch.object(
            ComponentBatchDeleteDialog,
            "exec",
            new=accept_partial,
        ):
            host._run_batch_delete(state)
        self.app.processEvents()

        self.assertNotIn("curve-first", self.canvas.component_registry)
        self.assertIn("curve-second", self.canvas.component_registry)
        self.assertEqual(toolbox.component_ids(), ("curve-second",))
        self.assertEqual(self.canvas.current_component_id, "curve-second")

    def test_batch_delete_rolls_back_artists_ids_and_inspectors_on_failure(self):
        inspector, toolbox = self._add_curves()
        registry = self.canvas.component_registry
        first_controller = registry.get("curve-first")
        second_controller = registry.get("curve-second")
        first_artist = first_controller.resolve_target()
        second_artist = second_controller.resolve_target()
        first_editor = self.canvas.component_editor_manager.editor(
            "curve-first"
        )
        second_editor = self.canvas.component_editor_manager.editor(
            "curve-second"
        )
        current = toolbox.currentWidget()
        original_lines = tuple(self.canvas.current_axes.lines)
        original_entries = toolbox.component_ids()
        self.canvas.select_component("curve-second")
        original_selection = self.canvas.current_component_id
        original_tree_selection = (
            self.window.component_tree_host.tree.selected_component_id()
        )
        original_project = project_snapshot(
            self.window.figure_window,
            canvas=self.canvas,
        )
        original_fingerprint = self.window.figure_window._snapshot_fingerprint(
            original_project
        )
        events = []
        cleanup = []
        registry.subscribe(events.append)
        registry.add_cleanup_callback(
            "curve-first",
            lambda state: cleanup.append(state.id),
        )

        messages = []
        status_messages.set_status_handler(
            lambda text, level: messages.append((text, level))
        )
        with mock.patch.object(
            second_controller,
            "commit_remove",
            side_effect=RuntimeError("injected batch failure"),
        ):
            self.assertFalse(
                self.canvas.delete_component_group(
                    ["curve-first", "curve-second"],
                    "function curve",
                )
            )
        self.app.processEvents()

        self.assertIn("curve-first", registry)
        self.assertIn("curve-second", registry)
        self.assertIs(registry.get("curve-first"), first_controller)
        self.assertIs(registry.get("curve-second"), second_controller)
        self.assertIs(first_controller.resolve_target(), first_artist)
        self.assertIs(second_controller.resolve_target(), second_artist)
        self.assertEqual(tuple(self.canvas.current_axes.lines), original_lines)
        self.assertIs(
            self.canvas.component_editor_manager.editor("curve-first"),
            first_editor,
        )
        self.assertIs(
            self.canvas.component_editor_manager.editor("curve-second"),
            second_editor,
        )
        self.assertIs(toolbox.currentWidget(), current)
        self.assertEqual(toolbox.component_ids(), original_entries)
        self.assertEqual(toolbox.count(), 2)
        self.assertEqual(self.canvas.current_component_id, original_selection)
        self.assertEqual(
            self.window.component_tree_host.tree.selected_component_id(),
            original_tree_selection,
        )
        self.assertIs(
            inspector.component_toolbox(
                (ComponentKind.LINE, ComponentRole.FUNCTION_CURVE),
            ),
            toolbox,
        )
        self.assertEqual(
            [
                event
                for event in events
                if event.kind is ComponentEventKind.REMOVED
            ],
            [],
        )
        self.assertEqual(cleanup, [])
        rolled_back_project = project_snapshot(
            self.window.figure_window,
            canvas=self.canvas,
        )
        self.assertEqual(rolled_back_project, original_project)
        self.assertEqual(
            self.window.figure_window._snapshot_fingerprint(
                rolled_back_project
            ),
            original_fingerprint,
        )
        self.assertEqual(len(messages), 1)
        self.assertEqual(messages[0][1], "error")

    def test_unknown_color_history_does_not_guess_a_palette_release(self):
        self._add_curves()
        self.canvas.add_curve(
            "x**3",
            0.0,
            1.0,
            ":",
            "#778899",
            "third",
            object_id="curve-third",
        )
        registry = self.canvas.component_registry
        axes_id = self.canvas.current_axes_component_id
        palette = PaletteDefinition(
            "test:delete-release",
            "Delete release",
            ("red", "green", "blue"),
        )
        self.assertTrue(
            self.canvas.axes_commands.apply_palette(
                axes_id,
                palette,
            ).ok
        )
        self.assertEqual(
            self.canvas.axes_commands.cycle_state(axes_id).next_index,
            0,
        )

        self.assertTrue(
            self.canvas.delete_component_group(
                ("curve-second",),
                "function curve",
            )
        )

        cycle = self.canvas.axes_commands.cycle_state(axes_id)
        self.assertEqual(cycle.active_palette, palette)
        self.assertEqual(cycle.next_index, 0)
        self.assertEqual(
            self.canvas.creation_color_cycle().peek().color,
            palette.colors[1],
        )
        self.assertEqual(
            registry.get("curve-first")
            .state.properties["color"]
            .casefold(),
            palette.colors[0].casefold(),
        )
        self.assertEqual(
            registry.get("curve-third")
            .state.properties["color"]
            .casefold(),
            palette.colors[2].casefold(),
        )

        cursor_before_failure = registry.get(axes_id).state.properties[
            "color_cycle"
        ]
        third = registry.get("curve-third")
        with mock.patch.object(
            third,
            "commit_remove",
            side_effect=RuntimeError("injected palette rollback failure"),
        ):
            self.assertFalse(
                self.canvas.delete_component_group(
                    ("curve-third",),
                    "function curve",
                )
            )
        self.assertIn("curve-third", registry)
        self.assertEqual(
            registry.get(axes_id).state.properties["color_cycle"],
            cursor_before_failure,
        )
        self.assertEqual(
            self.canvas.creation_color_cycle().peek().color,
            palette.colors[1],
        )

    def test_color_ledger_releases_only_confirmed_contiguous_tail(self):
        axes_id = self.canvas.current_axes_component_id
        palette = PaletteDefinition(
            "test:ledger-duplicates",
            "Ledger duplicates",
            ("red", "red", "blue"),
        )
        self.assertTrue(self.canvas.axes_commands.apply_palette(axes_id, palette).ok)

        for index in range(3):
            selection = ColorSelection(
                palette.colors[index],
                palette,
                index,
            )
            self.canvas.add_curve(
                "x",
                0.0,
                1.0,
                "-",
                selection.color,
                f"ledger-{index}",
                object_id=f"ledger-{index}",
                color_selection=selection,
            )

        self.assertEqual(
            self.canvas.axes_commands.cycle_state(axes_id).next_index,
            0,
        )
        self.assertTrue(
            self.canvas.component_registry.get("ledger-2")
            .set_property(
                "color",
                "#123456",
            )
            .ok
        )
        self.assertTrue(
            self.canvas.delete_component_group(("ledger-1",), "function curve")
        )
        self.assertEqual(
            self.canvas.axes_commands.cycle_state(axes_id).next_index,
            0,
        )
        self.assertTrue(
            self.canvas.delete_component_group(("ledger-2",), "function curve")
        )
        self.assertEqual(
            self.canvas.axes_commands.cycle_state(axes_id).next_index,
            1,
        )
        first = self.canvas.component_registry.get("ledger-0")
        with mock.patch.object(
            first,
            "commit_remove",
            side_effect=RuntimeError("injected ledger rollback failure"),
        ):
            self.assertFalse(
                self.canvas.delete_component_group(
                    ("ledger-0",),
                    "function curve",
                )
            )
        self.assertIn("ledger-0", self.canvas.component_registry)
        self.assertEqual(
            self.canvas.axes_commands.cycle_state(axes_id).next_index,
            1,
        )

    def test_inspector_add_failure_rolls_back_stack_and_manager_tracking(self):
        _inspector, toolbox = self._add_curves()
        registry = self.canvas.component_registry
        original_entries = toolbox.component_ids()
        original_current = toolbox.currentWidget()
        original_lines = tuple(self.canvas.current_axes.lines)
        original_snapshot = self.canvas.component_snapshot()
        original_selection = self.canvas.current_component_id
        original_pending = dict(registry._pending)
        events = []
        unsubscribe = registry.subscribe(events.append)
        original_add = toolbox.inspector_stack.addWidget

        def fail_stack_add(*args, **kwargs):
            original_add(*args, **kwargs)
            raise RuntimeError("injected stack insertion failure")

        try:
            with mock.patch.object(
                toolbox.inspector_stack,
                "addWidget",
                side_effect=fail_stack_add,
            ):
                with self.assertRaisesRegex(
                    RuntimeError,
                    "stack insertion",
                ):
                    self.canvas.add_curve(
                        "x**3",
                        0.0,
                        1.0,
                        ":",
                        "#778899",
                        "third",
                        object_id="curve-third",
                    )
        finally:
            unsubscribe()
        self.app.processEvents()

        self.assertEqual(toolbox.component_ids(), original_entries)
        self.assertIs(toolbox.currentWidget(), original_current)
        self.assertIsNone(
            self.canvas.component_editor_manager.editor("curve-third")
        )
        self.assertNotIn("curve-third", registry)
        self.assertEqual(tuple(self.canvas.current_axes.lines), original_lines)
        self.assertEqual(self.canvas.component_snapshot(), original_snapshot)
        self.assertEqual(self.canvas.current_component_id, original_selection)
        self.assertEqual(registry._pending, original_pending)
        self.assertEqual(events, [])

    def test_axes_inspector_failure_rolls_back_complete_axes_subtree(self):
        registry = self.canvas.component_registry
        original_snapshot = self.canvas.component_snapshot()
        original_axes = tuple(self.canvas.fig.axes)
        original_allocated = set(self.canvas._allocated_component_ids)
        original_selection = (
            self.canvas.current_axes_component_id,
            self.canvas.current_component_id,
        )
        original_panel_ids = set(
            self.canvas.figure_inspector._axes_panels
        )
        events = []
        unsubscribe = registry.subscribe(events.append)
        try:
            with mock.patch.object(
                self.canvas.figure_inspector,
                "add_axes_inspector",
                side_effect=RuntimeError("injected Axes Inspector failure"),
            ):
                with self.assertRaisesRegex(RuntimeError, "Axes Inspector"):
                    create_regular_axes(self.canvas)
        finally:
            unsubscribe()

        self.assertEqual(tuple(self.canvas.fig.axes), original_axes)
        registry.validate_axes_targets()
        self.assertEqual(
            self.canvas._allocated_component_ids, original_allocated
        )
        self.assertEqual(self.canvas.component_snapshot(), original_snapshot)
        self.assertEqual(
            (
                self.canvas.current_axes_component_id,
                self.canvas.current_component_id,
            ),
            original_selection,
        )
        self.assertEqual(
            set(self.canvas.figure_inspector._axes_panels),
            original_panel_ids,
        )
        self.assertEqual(events, [])

    def test_direct_panel_removal_recursively_disposes_cached_sections(self):
        baseline = len(tex_config._TEX_AVAILABILITY_LISTENERS)
        axes_id = self.canvas.current_axes_component_id
        self.canvas.add_text(
            0.2,
            0.3,
            "listener",
            "DejaVu Sans",
            10,
            object_id="listener-text",
        )
        self.assertEqual(
            len(tex_config._TEX_AVAILABILITY_LISTENERS),
            baseline + 1,
        )
        self.assertIsNotNone(
            self.canvas.component_editor_manager.editor("listener-text")
        )

        self.assertTrue(
            self.canvas.figure_inspector.remove_axes_inspector(axes_id)
        )
        self.assertFalse(
            self.canvas.figure_inspector.remove_axes_inspector(axes_id)
        )
        self.assertEqual(
            len(tex_config._TEX_AVAILABILITY_LISTENERS),
            baseline,
        )
        self.assertIsNone(
            self.canvas.component_editor_manager.editor("listener-text")
        )

    def test_full_role_delete_removes_empty_internal_toolbox(self):
        inspector, _toolbox = self._add_curves()

        self.assertTrue(
            self.canvas.delete_component_group(
                ["curve-first", "curve-second"],
                "function curve",
            )
        )
        self.app.processEvents()

        self.assertIsNone(
            inspector.component_toolbox(
                (ComponentKind.LINE, ComponentRole.FUNCTION_CURVE),
            )
        )
        self.assertEqual(
            self.canvas.component_registry.query(
                role=ComponentRole.FUNCTION_CURVE
            ),
            [],
        )

    def test_fixed_semantic_components_never_expose_physical_delete(self):
        fixed_roles = {
            ComponentRole.TITLE,
            ComponentRole.X_LABEL,
            ComponentRole.Y_LABEL,
            ComponentRole.LEGEND,
            ComponentRole.X_AXIS,
            ComponentRole.Y_AXIS,
            ComponentRole.SPINE,
            ComponentRole.MAJOR_TICK,
            ComponentRole.MINOR_TICK,
            ComponentRole.MAJOR_TICK_LABEL,
            ComponentRole.MINOR_TICK_LABEL,
            ComponentRole.GRID,
        }
        controllers = [
            controller
            for controller in self.canvas.component_registry.query()
            if controller.state.role in fixed_roles
        ]
        for controller in controllers:
            self.assertTrue(
                self.canvas.select_component(controller.component_id)
            )
        editors = [
            self.canvas.component_editor_manager.editor(
                controller.component_id
            )
            for controller in controllers
        ]

        self.assertTrue(editors)
        self.assertTrue(
            all(editor is not None and not editor.can_delete for editor in editors)
        )

    def test_axes_delete_cascades_reindexes_and_does_not_reuse_ids(self):
        create_regular_axes(self.canvas)
        create_regular_axes(self.canvas)
        axes = sorted(
            self.canvas.component_registry.query(kind=ComponentKind.AXES),
            key=lambda item: item.state.selector["index"],
        )
        deleted = axes[1]
        deleted_target = deleted.resolve_target()
        deleted_descendants = {
            item.component_id
            for item in self.canvas.component_registry.descendants(
                deleted.component_id
            )
        }
        surviving_ids = [axes[0].component_id, axes[2].component_id]
        surviving_subplots = [
            axes[0].state.data["subplot"].copy(),
            axes[2].state.data["subplot"].copy(),
        ]
        self.canvas.update_current_axes(deleted.component_id)

        axes_events = []
        observer_id = self.canvas.fig._axobservers.connect(
            "_axes_change_event",
            lambda figure: axes_events.append(figure),
        )
        try:
            with mock.patch.object(
                self.canvas.canva,
                "draw_idle",
                wraps=self.canvas.canva.draw_idle,
            ) as draw_idle:
                self.assertTrue(
                    self.canvas.delete_axes(deleted.component_id)
                )
            draw_idle.assert_called_once_with()
        finally:
            self.canvas.fig._axobservers.disconnect(observer_id)
        self.assertEqual(axes_events, [self.canvas.fig])

        self.assertNotIn(deleted_target, self.canvas.fig.axes)
        self.assertNotIn(deleted.component_id, self.canvas.component_registry)
        self.assertTrue(
            deleted_descendants.isdisjoint(
                {
                    item.component_id
                    for item in self.canvas.component_registry.query()
                }
            )
        )
        remaining = sorted(
            self.canvas.component_registry.query(kind=ComponentKind.AXES),
            key=lambda item: item.state.selector["index"],
        )
        self.assertEqual(
            [item.component_id for item in remaining],
            surviving_ids,
        )
        self.assertEqual(
            [item.state.selector["index"] for item in remaining],
            [0, 1],
        )
        self.assertEqual([item.state.order for item in remaining], [0, 1])
        self.assertEqual(
            [item.state.data["subplot"] for item in remaining],
            surviving_subplots,
        )
        self.assertEqual(
            self.canvas.current_axes_component_id,
            surviving_ids[1],
        )

        occupied = {
            item.component_id
            for item in self.canvas.component_registry.query()
        }
        create_regular_axes(self.canvas)
        added = max(
            self.canvas.component_registry.query(kind=ComponentKind.AXES),
            key=lambda item: item.state.selector["index"],
        )
        self.assertNotIn(added.component_id, occupied)
        self.canvas.component_registry.validate_tree()
        self.canvas.component_snapshot()

    def test_axes_delete_preserves_two_by_two_layout_after_first_slot(self):
        self._assert_two_by_two_delete_preserves_layout(0)

    def test_axes_delete_preserves_two_by_two_layout_after_middle_slot(self):
        self._assert_two_by_two_delete_preserves_layout(1)

    def test_axes_delete_preserves_two_by_two_layout_after_last_slot(self):
        self._assert_two_by_two_delete_preserves_layout(3)

    def test_axes_delete_failures_preserve_matplotlib_registry_and_ui_identity(self):
        create_regular_axes(self.canvas)
        registry = self.canvas.component_registry
        axes_controllers = sorted(
            registry.query(kind=ComponentKind.AXES),
            key=lambda item: item.state.selector["index"],
        )
        target, survivor = axes_controllers
        target_axes = target.resolve_target()
        survivor_axes = survivor.resolve_target()
        target_axes._shared_axes["x"].join(target_axes, survivor_axes)
        target_axes._twinned_axes.join(target_axes, survivor_axes)
        self.canvas.update_current_axes(target.component_id)
        self.canvas.canva.grab_mouse(target_axes)

        panel = self.canvas.figure_inspector.axes_inspector(
            target.component_id
        )
        self.assertTrue(self.canvas.select_component(target.component_id))
        tree_selection = self.window.component_tree_host.tree.selected_component_id()
        original_figure_axes = tuple(self.canvas.fig.axes)
        original_stack = dict(self.canvas.fig._axstack._axes)
        original_current_axes = self.canvas.fig._axstack.current()
        original_snapshot = self.canvas.component_snapshot()
        original_shared = tuple(
            target_axes._shared_axes["x"].get_siblings(target_axes)
        )
        original_twinned = tuple(
            target_axes._twinned_axes.get_siblings(target_axes)
        )
        major_formatter = survivor_axes.xaxis.get_major_formatter()
        major_locator = survivor_axes.xaxis.get_major_locator()
        formatter_axis = major_formatter.axis
        locator_axis = major_locator.axis
        component_events = []
        axes_events = []
        cleanup = []
        unsubscribe = registry.subscribe(component_events.append)
        observer_id = self.canvas.fig._axobservers.connect(
            "_axes_change_event",
            lambda figure: axes_events.append(figure),
        )
        registry.add_cleanup_callback(
            target.component_id,
            lambda state: cleanup.append(state.id),
        )

        def assert_unchanged():
            self.assertEqual(tuple(self.canvas.fig.axes), original_figure_axes)
            self.assertEqual(
                dict(self.canvas.fig._axstack._axes),
                original_stack,
            )
            self.assertIs(
                self.canvas.fig._axstack.current(),
                original_current_axes,
            )
            self.assertEqual(
                self.canvas.current_axes_component_id,
                target.component_id,
            )
            self.assertIs(registry.get(target.component_id), target)
            self.assertIs(target.resolve_target(), target_axes)
            self.assertEqual(
                tuple(
                    target_axes._shared_axes["x"].get_siblings(target_axes)
                ),
                original_shared,
            )
            self.assertEqual(
                tuple(target_axes._twinned_axes.get_siblings(target_axes)),
                original_twinned,
            )
            self.assertIs(major_formatter.axis, formatter_axis)
            self.assertIs(major_locator.axis, locator_axis)
            self.assertIs(self.canvas.canva.mouse_grabber, target_axes)
            self.assertIs(
                self.canvas.figure_inspector.axes_inspector(
                    target.component_id
                ),
                panel,
            )
            self.assertEqual(
                self.canvas.figure_inspector.current_component_id(),
                target.component_id,
            )
            self.assertEqual(
                self.window.component_tree_host.tree.selected_component_id(),
                tree_selection,
            )
            self.assertEqual(
                self.canvas.component_snapshot(),
                original_snapshot,
            )
            self.assertEqual(component_events, [])
            self.assertEqual(axes_events, [])
            self.assertEqual(cleanup, [])

        try:
            with mock.patch.object(
                survivor,
                "read_state",
                side_effect=RuntimeError("injected live state failure"),
            ):
                self.assertFalse(self.canvas.delete_axes(target.component_id))
            assert_unchanged()

            with mock.patch.object(
                survivor,
                "apply_state",
                side_effect=RuntimeError("injected survivor failure"),
            ):
                self.assertFalse(self.canvas.delete_axes(target.component_id))
            assert_unchanged()

            with mock.patch.object(
                target,
                "commit_remove",
                side_effect=RuntimeError("injected detach failure"),
            ):
                self.assertFalse(self.canvas.delete_axes(target.component_id))
            assert_unchanged()

            original_validate = registry.validate_tree
            calls = 0

            def fail_candidate_validation():
                nonlocal calls
                calls += 1
                original_validate()
                if calls == 2:
                    raise RuntimeError("injected tree validation failure")

            with mock.patch.object(
                registry,
                "validate_tree",
                side_effect=fail_candidate_validation,
            ):
                self.assertFalse(self.canvas.delete_axes(target.component_id))
            assert_unchanged()

            with mock.patch.object(
                self.canvas.figure_inspector,
                "ensure_component",
                side_effect=RuntimeError("injected fallback Inspector failure"),
            ):
                self.assertFalse(self.canvas.delete_axes(target.component_id))
            assert_unchanged()

            with mock.patch.object(
                self.canvas.figure_inspector,
                "take_axes_inspector",
                side_effect=RuntimeError("injected Panel detach failure"),
            ):
                self.assertFalse(self.canvas.delete_axes(target.component_id))
            assert_unchanged()

            with mock.patch.object(
                ComponentTreeModel,
                "validate_registry_projection",
                side_effect=RuntimeError("injected projection failure"),
            ):
                self.assertFalse(self.canvas.delete_axes(target.component_id))
            assert_unchanged()

            with mock.patch.object(
                registry,
                "validate_axes_targets",
                side_effect=RuntimeError("injected Axes target failure"),
            ):
                self.assertFalse(self.canvas.delete_axes(target.component_id))
            assert_unchanged()

            with mock.patch(
                "mygui.widgets.figure_canvas.deletion_coordinator.normalize_v10_figure",
                side_effect=RuntimeError("injected schema failure"),
            ):
                self.assertFalse(self.canvas.delete_axes(target.component_id))
            assert_unchanged()

            original_unbind = registry.locator.unbind
            unbind_calls = 0

            def fail_first_unbind(component_id):
                nonlocal unbind_calls
                unbind_calls += 1
                original_unbind(component_id)
                if unbind_calls == 1:
                    raise RuntimeError("injected Locator failure")

            with mock.patch.object(
                registry.locator,
                "unbind",
                side_effect=fail_first_unbind,
            ):
                self.assertFalse(self.canvas.delete_axes(target.component_id))
            assert_unchanged()
        finally:
            unsubscribe()
            self.canvas.fig._axobservers.disconnect(observer_id)
            self.canvas.canva.release_mouse(target_axes)

    def test_deleting_last_axes_selects_figure_root_inspector(self):
        axes_id = self.canvas.current_axes_component_id

        with mock.patch.object(
            self.canvas.canva,
            "draw_idle",
            wraps=self.canvas.canva.draw_idle,
        ) as draw_idle:
            self.assertTrue(self.canvas.delete_axes(axes_id))

        self.assertEqual(self.canvas.fig.axes, [])
        draw_idle.assert_called_once_with()
        self.assertIsNone(self.canvas.current_axes_component_id)
        self.assertIs(
            self.canvas.figure_inspector.current_panel(),
            self.canvas.figure_inspector.root_inspector,
        )
        self.assertEqual(
            self.canvas.current_component_id,
            self.canvas.root_component_id,
        )

    def test_deleting_last_axes_ignores_surviving_figure_text_for_fallback(self):
        axes_id = self.canvas.current_axes_component_id
        self.canvas.add_global_text(
            0.1,
            0.1,
            "survives",
            "DejaVu Sans",
            10,
            object_id="surviving-figure-text",
        )
        self.assertTrue(self.canvas.select_component(axes_id))

        self.assertTrue(self.canvas.delete_axes(axes_id))

        self.assertIn("surviving-figure-text", self.canvas.component_registry)
        self.assertEqual(
            self.canvas.current_component_id,
            self.canvas.root_component_id,
        )
        self.assertIsNone(self.canvas.current_axes_component_id)

    def test_axes_delete_round_trips_through_schema_v10(self):
        axes = self._replace_with_two_by_two_axes()
        self.assertTrue(self.canvas.delete_axes(axes[1].component_id))
        surviving = sorted(
            self.canvas.component_registry.query(kind=ComponentKind.AXES),
            key=lambda item: item.state.selector["index"],
        )
        surviving_ids = [item.component_id for item in surviving]
        surviving_subplots = [
            item.state.data["subplot"].copy() for item in surviving
        ]
        surviving_positions = [
            tuple(float(value) for value in item.resolve_target().get_position().bounds)
            for item in surviving
        ]
        path = Path(self.directory.name, "axes-delete.mygui.json")
        self.assertTrue(
            self.window.title_bar.menu_bar._save_project_to(
                str(path),
                canvas=self.canvas,
            )
        )
        loaded = MainWindow()
        try:
            restore_project_snapshot(
                path,
                loaded.table,
                loaded.figure_window,
            )
            restored = loaded.figure_window.current_canva
            restored_axes = restored.component_registry.query(
                kind=ComponentKind.AXES
            )
            restored_axes.sort(
                key=lambda item: item.state.selector["index"]
            )
            self.assertEqual(len(restored_axes), 3)
            self.assertEqual(
                [item.component_id for item in restored_axes],
                surviving_ids,
            )
            self.assertEqual(
                [item.state.selector["index"] for item in restored_axes],
                [0, 1, 2],
            )
            self.assertEqual(
                [item.state.data["subplot"] for item in restored_axes],
                surviving_subplots,
            )
            for controller, original_position in zip(
                restored_axes, surviving_positions
            ):
                restored_position = tuple(
                    float(value)
                    for value in controller.resolve_target().get_position().bounds
                )
                for actual, original in zip(
                    restored_position, original_position
                ):
                    self.assertAlmostEqual(actual, original, places=12)
            self.assertEqual(
                len(
                    {
                        tuple(
                            float(value)
                            for value in controller.resolve_target()
                            .get_position()
                            .bounds
                        )
                        for controller in restored_axes
                    }
                ),
                len(restored_axes),
            )
        finally:
            loaded.close_without_prompt()
            self.app.processEvents()

    def test_partial_component_delete_round_trips_survivor_identity_and_state(self):
        self._add_curves()
        survivor = self.canvas.component_registry.get("curve-second")
        self.assertTrue(
            survivor.set_property("linewidth", 3.25).ok
        )
        self.assertTrue(
            self.canvas.delete_component_group(
                ("curve-first",),
                "function curve",
            )
        )
        survivor_state = survivor.state
        path = Path(self.directory.name, "partial-delete.mygui.json")
        self.assertTrue(
            self.window.title_bar.menu_bar._save_project_to(
                str(path),
                canvas=self.canvas,
            )
        )

        loaded = MainWindow()
        try:
            restore_project_snapshot(
                path,
                loaded.table,
                loaded.figure_window,
            )
            registry = loaded.figure_window.current_canva.component_registry
            self.assertNotIn("curve-first", registry)
            restored = registry.get("curve-second").state
            self.assertEqual(restored.id, survivor_state.id)
            self.assertEqual(restored.order, survivor_state.order)
            self.assertEqual(
                restored.properties,
                survivor_state.properties,
            )
        finally:
            loaded.close_without_prompt()
            self.app.processEvents()

    def test_dirty_fingerprint_tracks_save_table_and_toolbar_view(self):
        figure_window = self.window.figure_window
        path = Path(self.directory.name, "dirty.mygui.json")
        self.assertTrue(figure_window.is_canvas_dirty(self.canvas))

        self.assertTrue(
            self.window.title_bar.menu_bar._save_project_to(
                str(path),
                canvas=self.canvas,
            )
        )
        self.assertFalse(figure_window.is_canvas_dirty(self.canvas))

        sheet = self.window.repository.project(
            self.canvas.project_id
        ).sheets.values()
        next(iter(sheet)).set_block(0, 0, [[1]])
        self.assertTrue(figure_window.is_canvas_dirty(self.canvas))

        figure_window.mark_canvas_clean(self.canvas)
        self.canvas.current_axes.set_xlim(2.0, 5.0)
        self.assertTrue(figure_window.is_canvas_dirty(self.canvas))

    def test_project_construction_failure_before_tab_publication_is_clean(self):
        figure_window = self.window.figure_window
        before_projects = set(self.window.repository.projects)
        before_subtables = set(self.window.table._subtables)
        before_canvases = dict(figure_window.canvas)
        before_tabs = figure_window.tabwindow.count()
        before_panels = figure_window.figure_inspector_host._figure_stack.count()
        created = []

        def construct(*args, **kwargs):
            canvas = PyFigureCanvas(*args, **kwargs)
            created.append(canvas)
            return canvas

        with (
            mock.patch(
                "mygui.widgets.figure_canvas.py_figure_window.PyFigureCanvas",
                side_effect=construct,
            ),
            mock.patch.object(
                figure_window.figure_inspector_host,
                "add_figure_inspector",
                side_effect=RuntimeError("injected Inspector panel failure"),
            ),
        ):
            with self.assertRaisesRegex(RuntimeError, "panel failure"):
                figure_window.add_figure(
                    width=4,
                    height=3,
                    dpi=100,
                    canva_name="FailedBeforeTab",
                    style="default",
                )

        self.assertEqual(set(self.window.repository.projects), before_projects)
        self.assertEqual(set(self.window.table._subtables), before_subtables)
        self.assertEqual(figure_window.canvas, before_canvases)
        self.assertEqual(figure_window.tabwindow.count(), before_tabs)
        self.assertEqual(
            figure_window.figure_inspector_host._figure_stack.count(),
            before_panels,
        )
        self.assertEqual(len(created), 1)
        self.assertTrue(created[0]._disposed)
        self.assertTrue(created[0].component_editor_manager._closed)

    def test_project_construction_failure_after_tab_insertion_is_clean(self):
        figure_window = self.window.figure_window
        before_projects = set(self.window.repository.projects)
        before_subtables = set(self.window.table._subtables)
        before_canvases = dict(figure_window.canvas)
        before_tabs = figure_window.tabwindow.count()
        before_panels = figure_window.figure_inspector_host._figure_stack.count()
        original_add_tab = figure_window.tabwindow.addTab

        def add_then_fail(*args, **kwargs):
            original_add_tab(*args, **kwargs)
            raise RuntimeError("injected tab publication failure")

        with mock.patch.object(
            figure_window.tabwindow,
            "addTab",
            side_effect=add_then_fail,
        ):
            with self.assertRaisesRegex(RuntimeError, "tab publication"):
                figure_window.add_figure(
                    width=4,
                    height=3,
                    dpi=100,
                    canva_name="FailedAfterTab",
                    style="default",
                )

        self.assertEqual(set(self.window.repository.projects), before_projects)
        self.assertEqual(set(self.window.table._subtables), before_subtables)
        self.assertEqual(figure_window.canvas, before_canvases)
        self.assertEqual(figure_window.tabwindow.count(), before_tabs)
        self.assertEqual(
            figure_window.figure_inspector_host._figure_stack.count(),
            before_panels,
        )
        self.assertIs(figure_window.current_canva, self.canvas)

    def test_project_post_tab_selection_failure_rolls_back_publication(self):
        figure_window = self.window.figure_window
        before_projects = set(self.window.repository.projects)
        before_subtables = set(self.window.table._subtables)
        before_canvases = dict(figure_window.canvas)
        before_tabs = figure_window.tabwindow.count()
        before_panels = figure_window.figure_inspector_host._figure_stack.count()
        original_change = figure_window.change_current_canvas
        calls = 0

        def fail_once():
            nonlocal calls
            calls += 1
            if calls == 1:
                raise RuntimeError("injected post-tab selection failure")
            return original_change()

        with mock.patch.object(
            figure_window,
            "change_current_canvas",
            side_effect=fail_once,
        ):
            with self.assertRaisesRegex(RuntimeError, "post-tab selection"):
                figure_window.add_figure(
                    width=4,
                    height=3,
                    dpi=100,
                    canva_name="FailedPostTabSelection",
                    style="default",
                )

        self.assertEqual(set(self.window.repository.projects), before_projects)
        self.assertEqual(set(self.window.table._subtables), before_subtables)
        self.assertEqual(figure_window.canvas, before_canvases)
        self.assertEqual(figure_window.tabwindow.count(), before_tabs)
        self.assertEqual(
            figure_window.figure_inspector_host._figure_stack.count(),
            before_panels,
        )
        self.assertIs(figure_window.current_canva, self.canvas)

    def test_targeted_background_save_writes_the_requested_project(self):
        first = self.canvas
        self.window.figure_window.add_figure(
            width=4,
            height=3,
            dpi=100,
            style="default",
            canva_name="ForegroundProject",
        )
        second = self.window.figure_window.current_canva
        create_regular_axes(second)
        target = Path(self.directory.name, "background.mygui.json")

        self.assertTrue(
            self.window.title_bar.menu_bar._save_project_to(
                str(target),
                canvas=first,
            )
        )

        self.assertIs(self.window.figure_window.current_canva, second)
        self.assertEqual(
            load_project_file(target)["project"]["id"],
            first.project_id,
        )
        self.assertFalse(self.window.figure_window.is_canvas_dirty(first))
        self.assertTrue(self.window.figure_window.is_canvas_dirty(second))

    def test_closing_background_tab_keeps_foreground_selection(self):
        first = self.canvas
        self.window.figure_window.add_figure(
            width=4,
            height=3,
            dpi=100,
            style="default",
            canva_name="ForegroundProject",
        )
        second = self.window.figure_window.current_canva
        create_regular_axes(second)

        with mock.patch.object(
            self.window,
            "_project_close_choice",
            return_value=QMessageBox.Discard,
        ):
            self.assertTrue(self.window.close_project_from_tab(0))

        self.assertIs(self.window.figure_window.current_canva, second)
        self.assertEqual(
            self.window.table.current_project_id,
            second.project_id,
        )
        self.assertNotIn(
            first.project_id,
            self.window.repository.projects,
        )

    def test_close_cancel_and_save_as_cancel_leave_exact_tab_intact(self):
        figure_window = self.window.figure_window
        project_id = self.canvas.project_id
        with mock.patch.object(
            self.window,
            "_project_close_choice",
            return_value=QMessageBox.Cancel,
        ):
            self.assertFalse(self.window.close_project_from_tab(0))
        self.assertIn(project_id, figure_window.canvas)
        self.assertIn(project_id, self.window.repository.projects)

        with (
            mock.patch.object(
                self.window,
                "_project_close_choice",
                return_value=QMessageBox.Save,
            ),
            mock.patch.object(
                QFileDialog,
                "getSaveFileName",
                return_value=("", ""),
            ),
        ):
            self.assertFalse(self.window.close_project_from_tab(0))
        self.assertEqual(figure_window.tabwindow.count(), 1)
        self.assertIn(project_id, self.window.repository.projects)

    def test_close_save_failure_preserves_file_and_open_project(self):
        path = Path(self.directory.name, "locked.mygui.json")
        self.assertTrue(
            self.window.title_bar.menu_bar._save_project_to(
                str(path),
                canvas=self.canvas,
            )
        )
        original = path.read_bytes()
        self.canvas.current_axes.set_xlim(4.0, 9.0)
        with (
            mock.patch.object(
                self.window,
                "_project_close_choice",
                return_value=QMessageBox.Save,
            ),
            mock.patch(
                "mygui.project_io.os.replace",
                side_effect=PermissionError("destination is locked"),
            ),
            mock.patch.object(QMessageBox, "warning"),
        ):
            self.assertFalse(self.window.close_project_from_tab(0))

        self.assertEqual(path.read_bytes(), original)
        self.assertEqual(self.window.figure_window.tabwindow.count(), 1)
        self.assertIn(
            self.canvas.project_id,
            self.window.repository.projects,
        )
        self.assertTrue(
            self.window.figure_window.is_canvas_dirty(self.canvas)
        )

    def test_discard_closes_project_and_cleans_all_runtime_maps(self):
        figure_window = self.window.figure_window
        project_id = self.canvas.project_id
        with mock.patch.object(
            self.window,
            "_project_close_choice",
            return_value=QMessageBox.Discard,
        ):
            self.assertTrue(self.window.close_project_from_tab(0))

        self.assertEqual(figure_window.tabwindow.count(), 0)
        self.assertNotIn(project_id, figure_window.canvas)
        self.assertNotIn(project_id, figure_window._clean_fingerprints)
        self.assertNotIn(project_id, self.window.repository.projects)
        self.assertNotIn(project_id, self.window.table._subtables)
        self.assertNotIn(
            project_id,
            self.window.component_tree_host._sessions,
        )
        self.assertIsNone(figure_window.current_canva)
        self.assertIsNone(self.window.table.current_project_id)

    def test_exit_cancel_keeps_all_projects_and_prior_save_is_clean(self):
        first = self.canvas
        first_path = Path(self.directory.name, "first.mygui.json")
        self.assertTrue(
            self.window.title_bar.menu_bar._save_project_to(
                str(first_path),
                canvas=first,
            )
        )
        first.current_axes.set_xlim(3.0, 7.0)
        self.window.figure_window.add_figure(
            width=4,
            height=3,
            dpi=100,
            style="default",
            canva_name="SecondProject",
        )
        second = self.window.figure_window.current_canva
        create_regular_axes(second)
        event = mock.Mock()

        with (
            mock.patch.object(
                self.window,
                "isVisible",
                return_value=True,
            ),
            mock.patch.object(
                self.window,
                "_project_close_choice",
                side_effect=(QMessageBox.Save, QMessageBox.Cancel),
            ),
        ):
            self.window.closeEvent(event)

        event.ignore.assert_called_once_with()
        self.assertEqual(self.window.figure_window.tabwindow.count(), 2)
        self.assertIn(first.project_id, self.window.repository.projects)
        self.assertIn(second.project_id, self.window.repository.projects)
        self.assertFalse(
            self.window.figure_window.is_canvas_dirty(first)
        )
        self.assertTrue(
            self.window.figure_window.is_canvas_dirty(second)
        )
        self.assertEqual(
            load_project_file(first_path)["project"]["id"],
            first.project_id,
        )


if __name__ == "__main__":
    unittest.main()
