import os
from dataclasses import replace
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from tests.axes_helpers import create_regular_axes

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QModelIndex, Qt
from PySide6.QtTest import QSignalSpy
from PySide6.QtWidgets import QApplication, QDialog, QMessageBox

from mygui.figuremodify.components import (
    ComponentKind,
    ComponentRole,
)
from mygui.widgets.component_tree import (
    COMPONENT_ID_ROLE,
    NODE_KEY_ROLE,
    VIRTUAL_GROUP_ROLE,
    ComponentNodeKey,
    GroupNodeKey,
    ComponentTreeModel,
    ComponentBatchDeleteDialog,
)
from mygui.widgets.left_column import ExplorerMode
from mygui.widgets.fig_control_window.component_editors import (
    EditorRegistry,
    TreePresentationSpec,
)
from mygui.widgets.fig_control_window.component_editors.profiles import (
    AXES_PROFILE,
    LINE_PROFILES,
    TEXT_PROFILE,
)
from mygui.project_io import restore_project_snapshot, save_project_snapshot
from main import MainWindow


class ComponentTreeTests(unittest.TestCase):
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
            canva_name="TreeProject",
        )
        self.canvas = self.window.figure_window.current_canva
        create_regular_axes(self.canvas)
        self.app.processEvents()

    def tearDown(self):
        self.window.close_without_prompt()
        self.app.processEvents()

    @staticmethod
    def _model_ids(model, parent=QModelIndex()):
        result = []
        for row in range(model.rowCount(parent)):
            index = model.index(row, 0, parent)
            component_id = index.data(COMPONENT_ID_ROLE)
            if component_id is not None:
                result.append(component_id)
            result.extend(ComponentTreeTests._model_ids(model, index))
        return result

    @staticmethod
    def _group_index(model, parent_id, label):
        parent = model.index_for_component(parent_id)
        for row in range(model.rowCount(parent)):
            index = model.index(row, 0, parent)
            if (
                index.data(VIRTUAL_GROUP_ROLE)
                and index.data(Qt.DisplayRole) == label
            ):
                return index
        return QModelIndex()

    def _editor_registry_with_overrides(self, overrides=None):
        overrides = overrides or {}
        editor_registry = EditorRegistry()
        keys = {
            (state.kind, state.role)
            for state in self.canvas.component_registry.states()
        }
        for key in keys:
            profile = overrides.get(
                key,
                self.canvas.editor_registry.profile_for(*key),
            )
            editor_registry.register_profile(
                key[0],
                profile,
                role=key[1],
            )
        return editor_registry

    @staticmethod
    def _menu_type(selected_text: str | None):
        class Action:
            def __init__(self, text):
                self._text = text

            def text(self):
                return self._text

        class Menu:
            def __init__(self, *_args, **_kwargs):
                self._actions = []

            def addAction(self, text):
                action = Action(text)
                self._actions.append(action)
                return action

            def isEmpty(self):
                return not self._actions

            def actions(self):
                return list(self._actions)

            def exec(self, _position):
                return next(
                    (
                        action
                        for action in self._actions
                        if action.text() == selected_text
                    ),
                    None,
                )

        return Menu

    def test_model_preserves_real_parent_ids_behind_ui_only_groups(self):
        registry = self.canvas.component_registry
        model = self.window.component_tree_host.model
        model_ids = self._model_ids(model)

        self.assertEqual(set(model_ids), {state.id for state in registry.states()})
        self.assertEqual(len(model_ids), len(registry))
        for state in registry.states():
            index = model.index_for_component(state.id)
            self.assertTrue(index.isValid())
            self.assertIsNone(index.data(Qt.DecorationRole))
            parent = model.parent(index)
            while (
                parent.isValid()
                and parent.data(COMPONENT_ID_ROLE) is None
            ):
                parent = model.parent(parent)
            actual_parent = parent.data(COMPONENT_ID_ROLE) if parent.isValid() else None
            self.assertEqual(actual_parent, state.parent_id)

        axes_id = self.canvas.current_axes_component_id
        group = self._group_index(model, axes_id, "Axes Components")
        self.assertTrue(group.isValid())
        self.assertIsNone(group.data(COMPONENT_ID_ROLE))
        self.assertTrue(group.data(VIRTUAL_GROUP_ROLE))
        self.assertIsNotNone(group.data(NODE_KEY_ROLE))
        self.assertFalse(model.flags(group) & Qt.ItemIsSelectable)
        self.assertFalse(
            self.window.component_tree_host.tree.select_component(
                group.data(NODE_KEY_ROLE)
            )
        )
        semantic_ids = {
            model.index(row, 0, group).data(COMPONENT_ID_ROLE)
            for row in range(model.rowCount(group))
        }
        self.assertIn(
            self.canvas.component_registry.query(
                role=ComponentRole.X_AXIS
            )[0].component_id,
            semantic_ids,
        )
        self.assertIn(
            self.canvas.component_registry.query(
                role=ComponentRole.LEGEND
            )[0].component_id,
            semantic_ids,
        )

    def test_reference_marks_tree_label_selection_and_element_placement(self):
        component_id = "tree-reference-marks"
        self.canvas.add_reference_marks(
            [15.2, 22.9],
            {"label": "YBCO"},
            object_id=component_id,
            announce=False,
        )
        self.app.processEvents()
        model = self.window.component_tree_host.model
        index = model.index_for_component(component_id)
        self.assertTrue(index.isValid())
        self.assertEqual(
            index.data(Qt.DisplayRole),
            "Reflection Positions — YBCO",
        )
        self.assertEqual(
            model.parent(index).data(COMPONENT_ID_ROLE),
            self.canvas.current_axes_component_id,
        )
        self.assertTrue(self.canvas.select_component(component_id))
        self.assertEqual(
            self.window.component_tree_host.tree.selected_component_id(),
            component_id,
        )
        self.assertIsNotNone(
            self.canvas.component_editor_manager.editor(component_id)
        )

    def test_real_id_cannot_collide_with_a_legacy_virtual_group_string(self):
        axes_id = self.canvas.current_axes_component_id
        component_id = f"@ui-group:{axes_id}:axes-components"
        self.canvas.add_curve(
            "x",
            0.0,
            1.0,
            "-",
            "#112233",
            "collision safe",
            object_id=component_id,
        )
        model = self.window.component_tree_host.model
        component_index = model.index_for_component(component_id)
        semantic_group = self._group_index(
            model, axes_id, "Axes Components"
        )

        self.assertTrue(component_index.isValid())
        self.assertIsInstance(
            component_index.data(NODE_KEY_ROLE), ComponentNodeKey
        )
        self.assertIsInstance(
            semantic_group.data(NODE_KEY_ROLE), GroupNodeKey
        )
        self.assertNotEqual(
            component_index.data(NODE_KEY_ROLE),
            semantic_group.data(NODE_KEY_ROLE),
        )
        self.assertEqual(
            self._model_ids(model).count(component_id), 1
        )
        self.assertIn(component_id, str(self.canvas.component_snapshot()))

    def test_repeated_dynamic_components_form_and_release_role_group(self):
        model = self.window.component_tree_host.model
        axes_id = self.canvas.current_axes_component_id
        self.canvas.add_curve(
            "x",
            0.0,
            1.0,
            "-",
            "#112233",
            "first",
            object_id="curve-a",
        )
        self.assertFalse(
            self._group_index(
                model,
                axes_id,
                "Function Curves",
            ).isValid()
        )
        self.assertIn("curve-a", model.visual_children_ids(axes_id))

        self.canvas.add_curve(
            "x**2",
            0.0,
            1.0,
            "--",
            "#445566",
            "second",
            object_id="curve-b",
        )
        group = self._group_index(model, axes_id, "Function Curves")
        self.assertTrue(group.isValid())
        group_id = group.data(NODE_KEY_ROLE)
        self.assertEqual(
            model.visual_children_ids(group_id),
            ("curve-a", "curve-b"),
        )
        self.assertEqual(
            [
                model.index(row, 0, group).data(Qt.DisplayRole)
                for row in range(model.rowCount(group))
            ],
            ["curve1 — first", "curve2 — second"],
        )
        host = self.window.component_tree_host
        host.search_input.setText("Function Curves")
        proxy_group = host.proxy_model.mapFromSource(group)
        self.assertTrue(proxy_group.isValid())
        self.assertEqual(host.proxy_model.rowCount(proxy_group), 2)
        host.search_input.clear()
        self.assertEqual(
            self.canvas.figure_inspector.current_component_id(),
            "curve-b",
        )

        self.assertTrue(
            self.canvas.delete_component_group(
                ("curve-b",),
                "function curve",
            )
        )
        self.app.processEvents()
        self.assertFalse(
            self._group_index(
                model,
                axes_id,
                "Function Curves",
            ).isValid()
        )
        self.assertIn("curve-a", model.visual_children_ids(axes_id))

    def test_labels_tooltips_semantic_sort_and_registry_changes_are_live(self):
        axes_id = self.canvas.current_axes_component_id
        self.canvas.add_global_text(
            0.1,
            0.2,
            "Initial global note",
            "DejaVu Sans",
            11,
            object_id="global-note",
        )
        self.canvas.select_component(axes_id)
        self.canvas.add_curve(
            "x",
            0.0,
            1.0,
            "-",
            "#112233",
            "Raw Data",
            object_id="raw-curve",
        )
        model = self.window.component_tree_host.model
        registry = self.canvas.component_registry
        axes_id = registry.get("raw-curve").state.parent_id

        root_children = model.children_ids(self.canvas.root_component_id)
        self.assertEqual(
            registry.get(root_children[0]).state.kind,
            ComponentKind.AXES,
        )
        axes_children = model.children_ids(axes_id)
        chart_position = axes_children.index("raw-curve")
        self.assertTrue(
            all(
                registry.get(component_id).state.kind
                not in {ComponentKind.LINE, ComponentKind.SCATTER}
                for component_id in axes_children[:chart_position]
            )
        )

        note_index = model.index_for_component("global-note")
        self.assertEqual(
            note_index.data(Qt.DisplayRole),
            "Text — Initial global note",
        )
        tooltip = note_index.data(Qt.ToolTipRole)
        self.assertIn("ID: global-note", tooltip)
        self.assertIn("Kind: text", tooltip)
        self.assertIn(f"Parent: {self.canvas.root_component_id}", tooltip)

        change = registry.get("global-note").set_property(
            "text",
            "Renamed note",
        )
        self.assertTrue(change.ok)
        self.assertEqual(
            model.index_for_component("global-note").data(Qt.DisplayRole),
            "Text — Renamed note",
        )

    def test_search_retains_only_matches_and_their_real_ancestors(self):
        self.canvas.add_global_text(
            0.1,
            0.2,
            "Needle phrase",
            "DejaVu Sans",
            11,
            object_id="search-note",
        )
        host = self.window.component_tree_host
        host.search_input.setText("needle")
        self.app.processEvents()

        self.assertEqual(
            set(self._model_ids(host.proxy_model)),
            {self.canvas.root_component_id, "search-note"},
        )
        host.search_input.setText("text")
        self.app.processEvents()
        self.assertIn("search-note", self._model_ids(host.proxy_model))

    def test_search_never_becomes_a_second_selection_model(self):
        title = self.canvas.component_registry.query(
            role=ComponentRole.TITLE
        )[0].component_id
        self.assertTrue(self.canvas.select_component(title))
        host = self.window.component_tree_host

        host.search_input.setText("no component can match this")
        self.app.processEvents()
        self.assertEqual(self.canvas.current_component_id, title)
        self.assertEqual(
            self.canvas.figure_inspector.current_component_id(), title
        )
        self.assertIsNone(host.tree.selected_component_id())

        host.search_input.clear()
        self.app.processEvents()
        self.assertEqual(host.tree.selected_component_id(), title)

        host.search_input.setText("title")
        self.canvas.add_curve(
            "x", 0.0, 1.0, "-", "#112233", "external",
            object_id="search-external-curve",
        )
        self.app.processEvents()
        self.assertEqual(host.search_input.text(), "")
        self.assertEqual(
            host.tree.selected_component_id(), "search-external-curve"
        )

    def test_failed_inspector_selection_restores_canvas_and_tree(self):
        self.canvas.add_curve(
            "x", 0.0, 1.0, "-", "#112233", "target",
            object_id="selection-failure-target",
        )
        title = self.canvas.component_registry.query(
            role=ComponentRole.TITLE
        )[0].component_id
        self.assertTrue(self.canvas.select_component(title))
        host = self.window.component_tree_host
        original_show = self.canvas.figure_inspector.show_component
        shown = QSignalSpy(self.canvas.figure_inspector.componentShown)

        def fail_target(component_id):
            if component_id == "selection-failure-target":
                raise RuntimeError("injected Inspector failure")
            return original_show(component_id)

        with mock.patch.object(
            self.canvas.figure_inspector,
            "show_component",
            side_effect=fail_target,
        ):
            host.tree.select_component("selection-failure-target")

        self.assertEqual(self.canvas.current_component_id, title)
        self.assertEqual(host.tree.selected_component_id(), title)
        self.assertEqual(
            self.canvas.figure_inspector.current_component_id(), title
        )
        self.app.processEvents()
        self.assertEqual(shown.count(), 0)

    def test_every_first_party_component_opens_its_exact_inspector(self):
        registry = self.canvas.component_registry
        panel = self.canvas.figure_inspector

        for state in registry.states():
            with self.subTest(component_id=state.id):
                self.assertTrue(self.canvas.select_component(state.id))
                self.assertEqual(self.canvas.current_component_id, state.id)
                self.assertEqual(panel.current_component_id(), state.id)
                self.assertIsNotNone(panel.inspector(state.id))
                expected_axes = self.canvas._axes_ancestor_id(state.id)
                if expected_axes is not None:
                    self.assertEqual(
                        self.canvas.current_axes_component_id,
                        expected_axes,
                    )

    def test_inspectors_are_created_lazily_and_cached_by_component_id(self):
        manager = self.canvas.component_editor_manager
        axes_id = self.canvas.current_axes_component_id
        self.assertEqual(
            set(manager._editors),
            {self.canvas.root_component_id, axes_id},
        )
        title = self.canvas.component_registry.query(
            role=ComponentRole.TITLE
        )[0].component_id
        self.assertIsNone(manager.editor(title))
        self.assertTrue(self.canvas.select_component(title))
        first = manager.editor(title)
        self.assertIsNotNone(first)
        self.assertTrue(self.canvas.select_component(title))
        self.assertIs(manager.editor(title), first)

    def test_creation_selects_component_without_changing_explorer_page(self):
        self.assertIs(self.window._explorer_mode, ExplorerMode.TABLE)
        self.assertTrue(self.window._explorer_visible)
        self.canvas.add_curve(
            "x",
            0.0,
            1.0,
            "-",
            "#112233",
            "new curve",
            object_id="new-curve",
        )
        self.assertEqual(self.canvas.current_component_id, "new-curve")
        self.assertIs(self.window._explorer_mode, ExplorerMode.TABLE)
        self.assertTrue(self.window._explorer_visible)

        self.window.left_column.table_button.click()
        self.assertFalse(self.window._explorer_visible)
        self.canvas.add_text(
            0.2,
            0.3,
            "new text",
            "DejaVu Sans",
            10,
            object_id="new-text",
        )
        self.assertEqual(self.canvas.current_component_id, "new-text")
        self.assertIs(self.window._explorer_mode, ExplorerMode.TABLE)
        self.assertFalse(self.window._explorer_visible)

    def test_project_switch_restores_session_selection_and_expansion(self):
        self.canvas.add_global_text(
            0.1,
            0.2,
            "First project note",
            "DejaVu Sans",
            11,
            object_id="first-note",
        )
        first_axes = self.canvas.component_registry.query(
            kind=ComponentKind.AXES
        )[0].component_id
        host = self.window.component_tree_host
        self.canvas.select_component("first-note")
        host.tree.expand_component_path(first_axes)
        semantic_group = self._group_index(
            host.model,
            first_axes,
            "Axes Components",
        )
        semantic_group_id = semantic_group.data(NODE_KEY_ROLE)
        host.tree.setExpanded(
            host.proxy_model.mapFromSource(semantic_group),
            True,
        )
        host.search_input.setText("First project note")

        self.window.figure_window.add_figure(
            width=4,
            height=3,
            dpi=100,
            style="default",
            canva_name="SecondTreeProject",
        )
        second = self.window.figure_window.current_canva
        create_regular_axes(second)
        self.window.figure_window.tabwindow.setCurrentIndex(0)
        self.app.processEvents()

        self.assertIs(self.window.figure_window.current_canva, self.canvas)
        self.assertEqual(host.search_input.text(), "")
        self.assertEqual(self.canvas.current_component_id, "first-note")
        self.assertEqual(host.tree.selected_component_id(), "first-note")
        axes_index = host.proxy_model.mapFromSource(
            host.model.index_for_component(first_axes)
        )
        self.assertTrue(host.tree.isExpanded(axes_index))
        restored_group = host.proxy_model.mapFromSource(
            host.model.index_for_node(semantic_group_id)
        )
        self.assertTrue(host.tree.isExpanded(restored_group))

    def test_selection_search_and_expansion_do_not_mutate_schema_v10(self):
        before = self.canvas.component_snapshot()
        host = self.window.component_tree_host
        title = self.canvas.component_registry.query(
            role=ComponentRole.TITLE
        )[0].component_id

        self.canvas.select_component(title)
        host.tree.expandAll()
        host.search_input.setText("title")
        self.app.processEvents()
        host.search_input.clear()
        self.app.processEvents()

        self.assertEqual(self.canvas.component_snapshot(), before)

    def test_saved_project_rebuilds_the_same_virtual_groups(self):
        axes_id = self.canvas.current_axes_component_id
        for component_id, expression, label in (
            ("saved-curve-a", "x", "first"),
            ("saved-curve-b", "x**2", "second"),
        ):
            self.canvas.add_curve(
                expression,
                0.0,
                1.0,
                "-",
                "#112233",
                label,
                object_id=component_id,
            )
        model = self.window.component_tree_host.model
        original_dynamic = self._group_index(
            model,
            axes_id,
            "Function Curves",
        )
        original_semantic = self._group_index(
            model,
            axes_id,
            "Axes Components",
        )
        original_group_ids = {
            original_dynamic.data(NODE_KEY_ROLE),
            original_semantic.data(NODE_KEY_ROLE),
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir, "component-groups.mygui.json")
            save_project_snapshot(path, self.window.figure_window)
            loaded = MainWindow()
            try:
                restore_project_snapshot(
                    path,
                    loaded.table,
                    loaded.figure_window,
                )
                restored = loaded.figure_window.current_canva
                restored_model = loaded.component_tree_host.model
                restored_axes_id = restored.component_registry.query(
                    kind=ComponentKind.AXES
                )[0].component_id
                dynamic = self._group_index(
                    restored_model,
                    restored_axes_id,
                    "Function Curves",
                )
                semantic = self._group_index(
                    restored_model,
                    restored_axes_id,
                    "Axes Components",
                )
                self.assertTrue(dynamic.isValid())
                self.assertTrue(semantic.isValid())
                self.assertEqual(
                    {
                        dynamic.data(NODE_KEY_ROLE),
                        semantic.data(NODE_KEY_ROLE),
                    },
                    original_group_ids,
                )
                self.assertEqual(
                    set(
                        restored_model.visual_children_ids(
                            dynamic.data(NODE_KEY_ROLE)
                        )
                    ),
                    {"saved-curve-a", "saved-curve-b"},
                )
                self.assertNotIn(
                    "@ui-group",
                    str(restored.component_snapshot()),
                )
            finally:
                loaded.close_without_prompt()
                self.app.processEvents()

    def test_model_dispose_releases_its_registry_subscription(self):
        registry = self.canvas.component_registry
        baseline = len(registry._batch_subscribers)
        model = ComponentTreeModel()
        model.set_registry(registry, self.canvas.editor_registry)
        self.assertEqual(len(registry._batch_subscribers), baseline + 1)
        model.dispose()
        self.assertEqual(len(registry._batch_subscribers), baseline)

    def test_missing_profile_rejects_candidate_and_keeps_previous_projection(self):
        registry = self.canvas.component_registry
        model = ComponentTreeModel()
        model.set_registry(registry, self.canvas.editor_registry)
        before_ids = self._model_ids(model)
        incomplete = EditorRegistry()
        incomplete.register_profile(
            ComponentKind.FIGURE,
            self.canvas.editor_registry.profile_for(
                ComponentKind.FIGURE,
                ComponentRole.FIGURE,
            ),
            role=ComponentRole.FIGURE,
        )
        with self.assertRaisesRegex(LookupError, "No exact tree"):
            model.set_registry(registry, incomplete)
        self.assertIs(model.editor_registry, self.canvas.editor_registry)
        self.assertEqual(self._model_ids(model), before_ids)
        model.dispose()

    def test_axes_creation_rebuilds_tree_once_per_registry_batch(self):
        refreshes = []
        self.window.component_tree_host.model.refreshed.connect(
            lambda: refreshes.append(True)
        )
        create_regular_axes(self.canvas)
        self.assertEqual(refreshes, [True])

    def test_property_driven_sort_rebuilds_from_projection_signature(self):
        self.canvas.add_curve(
            "x", 0.0, 1.0, "-", "#112233", "B",
            object_id="sort-b",
        )
        self.canvas.add_curve(
            "x**2", 0.0, 1.0, "-", "#445566", "A",
            object_id="sort-a",
        )
        profile = LINE_PROFILES[ComponentRole.FUNCTION_CURVE]
        editor_registry = self._editor_registry_with_overrides(
            {
                (ComponentKind.LINE, ComponentRole.FUNCTION_CURVE): replace(
                profile,
                tree=TreePresentationSpec(
                    "Function Curve",
                    sort_bucket=-10,
                    sort_key=lambda state: (
                        state.properties.get("label", ""),
                    ),
                ),
                )
            }
        )
        model = ComponentTreeModel()
        model.set_registry(self.canvas.component_registry, editor_registry)
        refreshes = []
        model.refreshed.connect(lambda: refreshes.append(True))
        try:
            self.assertLess(
                model.index_for_component("sort-a").row(),
                model.index_for_component("sort-b").row(),
            )
            change = self.canvas.component_registry.get(
                "sort-b"
            ).set_property("label", "0")
            self.assertTrue(change.ok)
            self.assertLess(
                model.index_for_component("sort-b").row(),
                model.index_for_component("sort-a").row(),
            )
            self.assertEqual(refreshes, [True])
        finally:
            model.dispose()

    def test_declared_cross_role_group_works_below_non_axes_parent(self):
        self.canvas.add_global_text(
            0.1,
            0.2,
            "Figure note",
            "DejaVu Sans",
            10,
            object_id="figure-note",
        )
        shared_group = {
            "group_title": "Figure Contents",
            "group_key": "figure_contents",
            "group_order": 0,
            "always_group": True,
        }
        editor_registry = self._editor_registry_with_overrides(
            {
                (ComponentKind.AXES, ComponentRole.AXES): replace(
                    AXES_PROFILE,
                    tree=TreePresentationSpec("Axes", **shared_group),
                ),
                (ComponentKind.TEXT, ComponentRole.TEXT): replace(
                    TEXT_PROFILE,
                    tree=TreePresentationSpec("Text", **shared_group),
                ),
            }
        )
        model = ComponentTreeModel()
        model.set_registry(self.canvas.component_registry, editor_registry)
        try:
            group = self._group_index(
                model,
                self.canvas.root_component_id,
                "Figure Contents",
            )
            self.assertTrue(group.isValid())
            self.assertEqual(
                set(model.visual_children_ids(group.data(NODE_KEY_ROLE))),
                {
                    self.canvas.current_axes_component_id,
                    "figure-note",
                },
            )
        finally:
            model.dispose()

    def test_batch_delete_fallback_is_computed_from_confirmed_selection(self):
        for component_id, expression in (
            ("fallback-a", "x"),
            ("fallback-b", "x**2"),
            ("fallback-c", "x**3"),
        ):
            self.canvas.add_curve(
                expression, 0.0, 1.0, "-", "#112233",
                component_id, object_id=component_id,
            )
        host = self.window.component_tree_host
        state = self.canvas.component_registry.get("fallback-a").state
        self.canvas.select_component("fallback-a")

        def accept_first_two(dialog):
            dialog._checkboxes[2].setChecked(False)
            return QDialog.Accepted

        with mock.patch.object(
            ComponentBatchDeleteDialog,
            "exec",
            new=accept_first_two,
        ):
            host._run_batch_delete(state)
        self.app.processEvents()

        self.assertNotIn("fallback-a", self.canvas.component_registry)
        self.assertNotIn("fallback-b", self.canvas.component_registry)
        self.assertEqual(self.canvas.current_component_id, "fallback-c")
        self.assertEqual(
            host.tree.selected_component_id(), "fallback-c"
        )

    def test_batch_candidates_are_limited_to_same_parent_and_role(self):
        self.canvas.add_curve(
            "x",
            0.0,
            1.0,
            "-",
            "#112233",
            "first",
            object_id="curve-a",
        )
        self.canvas.add_curve(
            "x**2",
            0.0,
            1.0,
            "--",
            "#445566",
            "second",
            object_id="curve-b",
        )
        first_axes_id = self.canvas.current_axes_component_id
        create_regular_axes(self.canvas)
        self.canvas.add_curve(
            "x**3",
            0.0,
            1.0,
            ":",
            "#778899",
            "other axes",
            object_id="curve-c",
        )
        self.assertNotEqual(
            first_axes_id,
            self.canvas.current_axes_component_id,
        )

        state = self.canvas.component_registry.get("curve-a").state
        self.assertEqual(
            {
                component_id
                for component_id, _label
                in self.window.component_tree_host._batch_candidates(state)
            },
            {"curve-a", "curve-b"},
        )

    def test_proxy_right_click_selects_and_deletes_exact_hit_component(self):
        for component_id, expression in (
            ("right-click-a", "x"),
            ("right-click-b", "x**2"),
        ):
            self.canvas.add_curve(
                expression, 0.0, 1.0, "-", "#112233",
                "same preview", object_id=component_id,
            )
        host = self.window.component_tree_host
        self.assertTrue(self.canvas.select_component("right-click-a"))
        host.tree.expand_component_path("right-click-b")
        host.show()
        self.app.processEvents()
        source_index = host.model.index_for_component("right-click-b")
        proxy_index = host.proxy_model.mapFromSource(source_index)
        position = host.tree.visualRect(proxy_index).center()

        with mock.patch(
            "mygui.widgets.component_tree.component_tree.QMenu",
            self._menu_type("Delete Function Curve"),
        ), mock.patch.object(
            host,
            "_confirm_single_delete",
            return_value=True,
        ):
            host.tree._context_menu_requested(position)
        self.app.processEvents()

        self.assertIn("right-click-a", self.canvas.component_registry)
        self.assertNotIn("right-click-b", self.canvas.component_registry)
        self.assertEqual(self.canvas.current_component_id, "right-click-a")

    def test_group_right_click_and_failed_inspector_never_open_menu(self):
        for component_id in ("menu-a", "menu-b"):
            self.canvas.add_curve(
                "x", 0.0, 1.0, "-", "#112233",
                "same", object_id=component_id,
            )
        host = self.window.component_tree_host
        axes_id = self.canvas.current_axes_component_id
        group = self._group_index(host.model, axes_id, "Function Curves")
        proxy_group = host.proxy_model.mapFromSource(group)
        host.tree.expand_component_path("menu-a")
        host.show()
        self.app.processEvents()
        with mock.patch(
            "mygui.widgets.component_tree.component_tree.QMenu",
            self._menu_type(None),
        ):
            host.tree._context_menu_requested(
                host.tree.visualRect(proxy_group).center()
            )

        self.assertTrue(self.canvas.select_component("menu-a"))
        self.assertTrue(
            self.canvas.figure_inspector.remove_component_inspector("menu-b")
        )
        original_show = self.canvas.figure_inspector.show_component

        def fail_target(component_id):
            if component_id == "menu-b":
                raise RuntimeError("injected Inspector open failure")
            return original_show(component_id)

        proxy_target = host.proxy_model.mapFromSource(
            host.model.index_for_component("menu-b")
        )
        with mock.patch.object(
            self.canvas.figure_inspector,
            "show_component",
            side_effect=fail_target,
        ), mock.patch(
            "mygui.widgets.component_tree.component_tree.QMenu",
            side_effect=AssertionError("menu must not be constructed"),
        ):
            host.tree._context_menu_requested(
                host.tree.visualRect(proxy_target).center()
            )
        self.assertEqual(self.canvas.current_component_id, "menu-a")
        self.assertEqual(host.tree.selected_component_id(), "menu-a")

    def test_filtered_batch_uses_full_cohort_and_precise_instance_labels(self):
        for component_id, expression in (
            ("filtered-a", "x"),
            ("filtered-b", "x**2"),
            ("filtered-c", "x**3"),
        ):
            self.canvas.add_curve(
                expression, 0.0, 1.0, "-", "#112233",
                "same", object_id=component_id,
            )
        host = self.window.component_tree_host
        host.search_input.setText("curve2")
        self.app.processEvents()
        candidates = host._batch_candidates(
            self.canvas.component_registry.get("filtered-b").state
        )
        self.assertEqual(
            [candidate.component_id for candidate in candidates],
            ["filtered-a", "filtered-b", "filtered-c"],
        )
        self.assertEqual(len({item.instance_label for item in candidates}), 3)
        self.assertTrue(all(item.parent_label for item in candidates))

        captured = []

        def reject_dialog(dialog):
            captured.extend(dialog.candidates)
            return QDialog.Rejected

        host.tree.expand_component_path("filtered-b")
        host.show()
        self.app.processEvents()
        with mock.patch(
            "mygui.widgets.component_tree.component_tree.QMenu",
            self._menu_type("Batch Delete Same Type..."),
        ), mock.patch.object(
            ComponentBatchDeleteDialog,
            "exec",
            new=reject_dialog,
        ):
            host._show_context_menu(
                host.model.index_for_component("filtered-b").data(
                    NODE_KEY_ROLE
                ),
                host.tree.mapToGlobal(host.tree.rect().center()),
            )
        self.assertEqual(
            [candidate.component_id for candidate in captured],
            ["filtered-a", "filtered-b", "filtered-c"],
        )
        self.assertEqual(host.proxy_model.query, "curve2")

    def test_single_delete_confirmation_names_instance_id_and_defaults_cancel(self):
        self.canvas.add_curve(
            "x", 0.0, 1.0, "-", "#112233",
            "confirm", object_id="confirm-curve",
        )
        host = self.window.component_tree_host

        def inspect_cancel(message):
            self.assertIn("confirm-curve", message.informativeText())
            self.assertEqual(message.defaultButton().text(), "Cancel")
            self.assertIn(
                host._source_label("confirm-curve"),
                message.text(),
            )
            return 0

        with mock.patch.object(QMessageBox, "exec", new=inspect_cancel):
            self.assertFalse(host._confirm_single_delete("confirm-curve"))

    def test_deletion_fallback_never_crosses_an_interleaved_role(self):
        self.canvas.add_curve(
            "x", 0.0, 1.0, "-", "#112233",
            "first", object_id="cohort-a",
        )
        self.canvas.add_text(
            0.2, 0.3, "other role", "DejaVu Sans", 10,
            object_id="cohort-text",
        )
        self.canvas.add_curve(
            "x**2", 0.0, 1.0, "--", "#445566",
            "second", object_id="cohort-b",
        )
        axes_id = self.canvas.current_axes_component_id

        self.assertTrue(self.canvas.select_component("cohort-a"))
        self.assertTrue(
            self.canvas.delete_component_group(("cohort-a",), "function curve")
        )
        self.assertEqual(self.canvas.current_component_id, "cohort-b")

        self.assertTrue(
            self.canvas.delete_component_group(("cohort-b",), "function curve")
        )
        self.assertEqual(self.canvas.current_component_id, axes_id)
        self.assertIn("cohort-text", self.canvas.component_registry)

    def test_batch_revalidation_rejects_changed_original_cohort(self):
        for component_id in ("revalidate-a", "revalidate-b"):
            self.canvas.add_curve(
                "x", 0.0, 1.0, "-", "#112233",
                component_id, object_id=component_id,
            )
        host = self.window.component_tree_host
        state = self.canvas.component_registry.get("revalidate-a").state
        original_candidates = host._batch_candidates(state)
        calls = 0

        def changing_candidates(_state):
            nonlocal calls
            calls += 1
            return original_candidates if calls == 1 else original_candidates[:1]

        with mock.patch.object(
            host,
            "_batch_candidates",
            side_effect=changing_candidates,
        ), mock.patch.object(
            ComponentBatchDeleteDialog,
            "exec",
            return_value=QDialog.Accepted,
        ):
            host._run_batch_delete(state)

        self.assertIn("revalidate-a", self.canvas.component_registry)
        self.assertIn("revalidate-b", self.canvas.component_registry)


if __name__ == "__main__":
    unittest.main()
