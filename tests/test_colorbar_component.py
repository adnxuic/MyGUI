import json
import os
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path
from unittest import mock

from tests.axes_helpers import create_regular_axes

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
from matplotlib.colorbar import Colorbar
from matplotlib.figure import Figure
from PySide6.QtWidgets import QApplication

from main import MainWindow
from mygui import status_messages
from mygui.database import ColumnRef
from mygui.figuremodify.axes_layout import AxesLayoutSpec
from mygui.figuremodify.components import (
    ChangeStatus,
    ColorbarController,
    ComponentKind,
    ComponentRole,
    DeletionPolicy,
    RestorePhase,
    register_figure_components,
)
from mygui.figuremodify.component_services import DeletionRequest
from mygui.project_io import (
    load_project_file,
    restore_project_snapshot,
    save_project_snapshot,
    validate_project_snapshot,
)
from mygui.widgets.fig_control_window.component_editors import EditorPlacement
from mygui.widgets.figure_canvas.py_figure_canves import PyFigureCanvas
from mygui.widgets.title_bar.titlebar_dialog.py_element_dialog import (
    PyColorbarDialog,
)


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


class ColorbarRuntimeTests(unittest.TestCase):
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
            canva_name="ColorbarProject",
        )
        self.canvas = self.window.figure_window.current_canva
        create_regular_axes(self.canvas)
        self.sheet = (
            self.window.table.current_subtable()
            .get_table(0)
            .table_model.sheet
        )
        self.sheet.set_block(
            0,
            0,
            [
                [0.0, 1.0, 10.0],
                [1.0, 2.0, 20.0],
                [2.0, 4.0, 30.0],
                [3.0, 8.0, 40.0],
            ],
        )
        self.x_ref = ColumnRef(
            self.canvas.project_id,
            self.sheet.id,
            self.sheet.columns[0].id,
        )
        self.y_ref = ColumnRef(
            self.canvas.project_id,
            self.sheet.id,
            self.sheet.columns[1].id,
        )
        self.color_ref = ColumnRef(
            self.canvas.project_id,
            self.sheet.id,
            self.sheet.columns[2].id,
        )

    def tearDown(self):
        status_messages.clear_status_handler()
        self.window.close_without_prompt()
        self.app.processEvents()

    def add_mapped_scatter(self, *, object_id="mapped-scatter"):
        pair = self.window.repository.valid_pair(self.x_ref, self.y_ref)
        self.canvas.add_scatter(
            pair.x,
            pair.y,
            24.0,
            "#336699",
            "o",
            "temperature",
            self.x_ref,
            self.y_ref,
            object_id=object_id,
            color_ref=self.color_ref,
            color_mapping=deepcopy(MAPPED_COLOR),
        )
        return self.canvas.component_registry.get(object_id)

    def add_colorbar(self, *, object_id="mapped-colorbar", properties=None):
        self.add_mapped_scatter()
        self.canvas.add_colorbar(
            "mapped-scatter",
            properties or {"label": "Temperature", "location": "right"},
            object_id=object_id,
        )
        return self.canvas.component_registry.get(object_id)

    @staticmethod
    def owner_snapshot(owner):
        return (
            owner.get_position().bounds,
            owner.get_position(original=True).bounds,
            owner.get_subplotspec(),
        )

    @staticmethod
    def callback_ids(mappable):
        return tuple(
            sorted(mappable.callbacks.callbacks.get("changed", {}))
        )

    def test_controller_profile_creation_and_direct_edits(self):
        source = self.add_mapped_scatter()
        eligible = self.canvas.eligible_colorbar_sources()
        self.assertEqual(eligible, ((source.component_id, "temperature"),))

        controller = self.canvas.component_registry.get("mapped-scatter")
        self.canvas.add_colorbar(
            controller.component_id,
            {"label": "Temperature", "outline_color": "#123456"},
            object_id="colorbar-one",
        )
        colorbar = self.canvas.component_registry.get("colorbar-one")
        target = colorbar.resolve_target()

        self.assertIsInstance(target, Colorbar)
        self.assertIs(colorbar.DELETION_POLICY, DeletionPolicy.REMOVE)
        self.assertIs(colorbar.RESTORE_PHASE, RestorePhase.COLORBAR)
        self.assertEqual(colorbar.state.parent_id, self.canvas.current_axes_component_id)
        self.assertEqual(
            colorbar.state.data,
            {"source_component_id": source.component_id},
        )
        self.assertIs(target.mappable, source.resolve_target())
        self.assertIs(
            self.canvas.component_registry.locator.bound_target("colorbar-one"),
            target,
        )
        self.assertNotIn(
            target.ax,
            [
                item.resolve_target()
                for item in self.canvas.component_registry.query(
                    kind=ComponentKind.AXES
                )
            ],
        )
        self.canvas.component_registry.validate_tree()
        self.canvas.component_registry.validate_axes_targets()
        self.assertEqual(self.canvas.eligible_colorbar_sources(), ())

        profile = self.canvas.editor_registry.profile_for(
            ComponentKind.COLORBAR,
            ComponentRole.COLORBAR,
        )
        self.assertIs(profile.placement, EditorPlacement.ELEMENT)
        self.assertEqual(profile.tree.group_title, "Colorbars")
        editor = self.canvas.component_editor_manager.editor("colorbar-one")
        self.assertIsNotNone(editor)
        source_section = editor.section("source")
        self.assertIn(source.component_id, source_section.summary_label.text())

        changed = colorbar.set_property("label", "Energy")
        self.assertTrue(changed.ok)
        self.assertEqual(target.ax.yaxis.label.get_text(), "Energy")
        before = colorbar.state
        rejected = colorbar.set_property("ticklocation", "top")
        self.assertIs(rejected.status, ChangeStatus.REJECTED)
        self.assertEqual(colorbar.state, before)
        self.assertEqual(target.ax.yaxis.get_ticks_position(), "right")

    def test_new_layout_after_colorbar_uses_semantic_axes_indexes(self):
        colorbar = self.add_colorbar()
        target = colorbar.resolve_target()

        created = self.canvas.create_axes_layout(AxesLayoutSpec.grid(1, 2))

        self.assertEqual(len(created), 2)
        axes = sorted(
            self.canvas.component_registry.query(kind=ComponentKind.AXES),
            key=lambda item: item.state.selector["index"],
        )
        self.assertEqual(
            [item.state.selector["index"] for item in axes],
            [0, 1, 2],
        )
        self.assertEqual(len(self.canvas.fig.axes), 4)
        self.assertIs(colorbar.resolve_target(), target)
        self.assertIn(target.ax, self.canvas.fig.axes)
        self.canvas.component_registry.validate_axes_targets()
        self.canvas.validate_component_snapshot()

    def test_no_source_warning_and_duplicate_source_rejection(self):
        events = []
        status_messages.set_status_handler(
            lambda message, level: events.append((message, level))
        )
        dialog = PyColorbarDialog(
            "Colorbar",
            self.window.figure_window,
            self.window,
        )
        try:
            self.assertFalse(dialog.input.has_source())
            self.assertEqual(len(events), 1)
            self.assertEqual(events[0][1], "warning")
        finally:
            dialog.close()

        self.add_colorbar()
        with self.assertRaisesRegex(ValueError, "already has a Colorbar"):
            self.canvas.add_colorbar("mapped-scatter")
        self.assertEqual(
            len(
                self.canvas.component_registry.query(
                    kind=ComponentKind.COLORBAR
                )
            ),
            1,
        )

    def test_creation_faults_restore_exact_pre_call_state(self):
        source = self.add_mapped_scatter()
        registry = self.canvas.component_registry
        figure = self.canvas.fig
        owner = self.canvas.current_axes
        mappable = source.resolve_target()

        def assert_baseline(baseline, events, messages):
            self.assertEqual(tuple(figure.axes), baseline["axes"])
            self.assertEqual(self.owner_snapshot(owner), baseline["owner"])
            self.assertEqual(registry.snapshot(), baseline["registry"])
            self.assertIsNone(mappable.colorbar)
            self.assertEqual(self.callback_ids(mappable), baseline["callbacks"])
            self.assertEqual(self.canvas.current_component_id, baseline["selection"])
            self.assertEqual(registry._pending, baseline["pending"])
            self.assertEqual(events, [])
            self.assertEqual(messages, [])

        baseline = {
            "axes": tuple(figure.axes),
            "owner": self.owner_snapshot(owner),
            "registry": registry.snapshot(),
            "callbacks": self.callback_ids(mappable),
            "selection": self.canvas.current_component_id,
            "pending": dict(registry._pending),
        }
        messages = []
        status_messages.set_status_handler(
            lambda message, level: messages.append((message, level))
        )

        original_colorbar = figure.colorbar

        def leak_then_fail(*args, **kwargs):
            original_colorbar(*args, **kwargs)
            raise RuntimeError("injected construction failure")

        fault_contexts = (
            mock.patch.object(figure, "colorbar", side_effect=leak_then_fail),
            mock.patch.object(
                ColorbarController,
                "sync_from_target",
                side_effect=RuntimeError("injected sync failure"),
            ),
            mock.patch.object(
                registry,
                "register",
                side_effect=RuntimeError("injected registry failure"),
            ),
            mock.patch.object(
                self.canvas.figure_inspector,
                "show_component",
                return_value=False,
            ),
            mock.patch.object(
                figure.canvas,
                "draw",
                side_effect=RuntimeError("injected render failure"),
            ),
        )
        for index, context in enumerate(fault_contexts):
            with self.subTest(fault=index), context:
                events = []
                unsubscribe = registry.subscribe(events.append)
                try:
                    with self.assertRaises(Exception):
                        self.canvas.add_colorbar(
                            source.component_id,
                            object_id=f"failed-colorbar-{index}",
                        )
                finally:
                    unsubscribe()
                assert_baseline(baseline, events, messages)

    def test_source_refresh_rebuild_and_dependency_deletion_rules(self):
        controller = self.add_colorbar()
        registry = self.canvas.component_registry
        source = registry.get("mapped-scatter")
        target = controller.resolve_target()

        changed_mapping = deepcopy(MAPPED_COLOR)
        changed_mapping["cmap"] = "plasma"
        changed_mapping["norm"] = {
            "kind": "linear",
            "params": {"vmin": 5.0, "vmax": 45.0, "clip": True},
        }
        change = self.canvas.chart_data_service.configure_scatter_mapping(
            source,
            color_ref=self.color_ref,
            size_ref=None,
            color_mapping=changed_mapping,
            size_mapping=source.state.properties["size_mapping"],
        )
        self.assertTrue(change.ok)
        self.assertEqual(target.cmap.name, "plasma")
        self.assertEqual((target.norm.vmin, target.norm.vmax), (5.0, 45.0))

        before_array = np.asarray(source.resolve_target().get_array()).copy()
        self.sheet.set_block(0, 2, [[11.0], [22.0], [33.0], [44.0]])
        refreshed = self.canvas.chart_data_service.refresh(source)
        self.assertTrue(refreshed.ok)
        self.assertFalse(
            np.array_equal(
                before_array,
                np.asarray(source.resolve_target().get_array()),
            )
        )
        self.assertIs(target.mappable, source.resolve_target())

        disabled = deepcopy(changed_mapping)
        disabled["enabled"] = False
        rejected = self.canvas.chart_data_service.configure_scatter_mapping(
            source,
            color_ref=None,
            size_ref=None,
            color_mapping=disabled,
            size_mapping=source.state.properties["size_mapping"],
        )
        self.assertIs(rejected.status, ChangeStatus.REJECTED)
        self.assertIn("Delete the dependent Colorbar", rejected.message)

        old = target
        old_axes = target.ax
        source_target = source.resolve_target()
        owner = self.canvas.current_axes
        owner_before = self.owner_snapshot(owner)
        callbacks_before = self.callback_ids(source_target)
        state_before = controller.state
        selection_before = self.canvas.current_component_id
        locator_before = registry.locator.bound_target(controller.component_id)
        with mock.patch.object(
            self.canvas.colorbar_service,
            "_create_runtime",
            side_effect=RuntimeError("injected rebuild failure"),
        ):
            rejected = self.canvas.colorbar_service.apply_properties(
                controller,
                {"location": "left"},
            )
        self.assertIs(rejected.status, ChangeStatus.REJECTED)
        self.assertIs(controller.resolve_target(), old)
        self.assertIs(controller.resolve_target().ax, old_axes)
        self.assertIs(old.mappable, source_target)
        self.assertEqual(self.owner_snapshot(owner), owner_before)
        self.assertEqual(self.callback_ids(source_target), callbacks_before)
        self.assertIs(locator_before, old)
        self.assertEqual(controller.state, state_before)
        self.assertEqual(self.canvas.current_component_id, selection_before)
        self.assertEqual(tuple(self.canvas.fig.axes), (owner, old_axes))

        events = []
        unsubscribe = registry.subscribe(events.append)
        try:
            with mock.patch.object(
                self.canvas.fig.canvas,
                "draw",
                side_effect=RuntimeError("injected rebuild render failure"),
            ):
                rejected = self.canvas.colorbar_service.apply_properties(
                    controller,
                    {"location": "left"},
                )
        finally:
            unsubscribe()
        self.assertIs(rejected.status, ChangeStatus.REJECTED)
        self.assertIs(controller.resolve_target(), old)
        self.assertIs(controller.resolve_target().ax, old_axes)
        self.assertIs(old.mappable, source_target)
        self.assertEqual(self.owner_snapshot(owner), owner_before)
        self.assertEqual(self.callback_ids(source_target), callbacks_before)
        self.assertIs(registry.locator.bound_target(controller.component_id), old)
        self.assertEqual(controller.state, state_before)
        self.assertEqual(self.canvas.current_component_id, selection_before)
        self.assertEqual(tuple(self.canvas.fig.axes), (owner, old_axes))
        self.assertEqual(events, [])

        rebuilt = self.canvas.colorbar_service.apply_properties(
            controller,
            {"location": "left", "fraction": 0.2},
        )
        self.assertTrue(rebuilt.ok)
        replacement = controller.resolve_target()
        self.assertIsNot(replacement, old)
        self.assertEqual(controller.state.properties["location"], "left")
        self.assertIs(registry.locator.bound_target(controller.component_id), replacement)
        self.assertIs(
            self.canvas.component_editor_manager.editor(controller.component_id),
            self.canvas.figure_inspector.inspector(controller.component_id),
        )

        colorbar_id = controller.component_id
        self.assertTrue(self.canvas.delete_component_group((colorbar_id,)))
        self.assertIn(source.component_id, registry)
        self.assertNotIn(colorbar_id, registry)
        self.assertEqual(tuple(self.canvas.fig.axes), (owner,))

    def test_deletion_rollback_and_source_and_axes_cascades(self):
        controller = self.add_colorbar()
        registry = self.canvas.component_registry
        source = registry.get("mapped-scatter")
        colorbar = controller.resolve_target()
        colorbar_axes = colorbar.ax
        owner = self.canvas.current_axes
        baseline = (
            registry.snapshot(),
            tuple(self.canvas.fig.axes),
            self.owner_snapshot(owner),
            self.callback_ids(source.resolve_target()),
            self.canvas.current_component_id,
        )
        original_source_commit = source.commit_remove
        with mock.patch.object(
            source,
            "commit_remove",
            side_effect=RuntimeError("injected source deletion failure"),
        ):
            outcome = self.canvas.deletion_service.prepare(
                DeletionRequest(
                    (source.component_id,),
                    anchor_id=source.component_id,
                )
            ).execute()
        self.assertFalse(outcome.committed)
        self.assertTrue(outcome.rollback_complete)
        self.assertEqual(registry.snapshot(), baseline[0])
        self.assertEqual(tuple(self.canvas.fig.axes), baseline[1])
        self.assertEqual(self.owner_snapshot(owner), baseline[2])
        self.assertEqual(self.callback_ids(source.resolve_target()), baseline[3])
        self.assertEqual(self.canvas.current_component_id, baseline[4])
        self.assertIs(controller.resolve_target(), colorbar)
        self.assertIs(colorbar.ax, colorbar_axes)
        self.assertIs(registry.locator.bound_target(controller.component_id), colorbar)
        self.assertTrue(callable(original_source_commit))

        self.assertTrue(self.canvas.delete_component_group((source.component_id,)))
        self.assertNotIn(source.component_id, registry)
        self.assertNotIn(controller.component_id, registry)
        self.assertEqual(tuple(self.canvas.fig.axes), (owner,))

        source = self.add_mapped_scatter(object_id="mapped-scatter-two")
        self.canvas.add_colorbar(
            source.component_id,
            object_id="mapped-colorbar-two",
        )
        axes_id = self.canvas.current_axes_component_id
        self.assertTrue(self.canvas.delete_component_group((axes_id,)))
        self.assertNotIn(axes_id, registry)
        self.assertNotIn(source.component_id, registry)
        self.assertNotIn("mapped-colorbar-two", registry)
        self.assertEqual(self.canvas.fig.axes, [])

    def test_tree_cohort_selection_fallback_and_source_section_disposal(self):
        first = self.add_colorbar(object_id="colorbar-a")
        second_source = self.add_mapped_scatter(object_id="mapped-scatter-b")
        self.canvas.add_colorbar(
            second_source.component_id,
            object_id="colorbar-b",
        )
        registry = self.canvas.component_registry
        model = self.window.component_tree_host.model
        self.assertTrue(model.index_for_component(first.component_id).isValid())
        self.assertTrue(model.index_for_component("colorbar-b").isValid())
        self.assertEqual(
            self.canvas.editor_registry.profile_for(
                ComponentKind.COLORBAR,
                ComponentRole.COLORBAR,
            ).tree.preview(first.state),
            "mapped-s",
        )
        subscribers_before = len(registry._event_subscribers)
        self.assertTrue(self.canvas.select_component(first.component_id))
        self.assertTrue(
            self.canvas.delete_component_group((first.component_id,))
        )
        self.app.processEvents()
        self.assertEqual(self.canvas.current_component_id, "colorbar-b")
        self.assertFalse(model.index_for_component(first.component_id).isValid())
        self.assertTrue(model.index_for_component("colorbar-b").isValid())
        self.assertLess(len(registry._event_subscribers), subscribers_before)


class ExistingFigureColorbarTests(unittest.TestCase):
    def test_auxiliary_axes_is_excluded_and_relationship_registered_once(self):
        figure = Figure()
        owner = figure.subplots()
        scatter = owner.scatter(
            [0.0, 1.0, 2.0],
            [1.0, 2.0, 3.0],
            c=[10.0, 20.0, 30.0],
            cmap="viridis",
        )
        colorbar = figure.colorbar(scatter, ax=owner)

        registry = register_figure_components(
            figure,
            id_factory=lambda path: path,
        )
        axes = registry.query(kind=ComponentKind.AXES)
        scatters = registry.query(kind=ComponentKind.SCATTER)
        colorbars = registry.query(kind=ComponentKind.COLORBAR)
        self.assertEqual(len(axes), 1)
        self.assertEqual(len(scatters), 1)
        self.assertEqual(len(colorbars), 1)
        self.assertIs(axes[0].resolve_target(), owner)
        self.assertIs(scatters[0].resolve_target(), scatter)
        self.assertIs(colorbars[0].resolve_target(), colorbar)
        self.assertEqual(colorbars[0].state.parent_id, axes[0].component_id)
        self.assertEqual(
            colorbars[0].state.data["source_component_id"],
            scatters[0].component_id,
        )
        self.assertNotIn(
            colorbar.ax,
            [controller.resolve_target() for controller in axes],
        )
        self.assertEqual(
            registry.query(parent_id=colorbars[0].component_id),
            [],
        )
        registry.validate_tree()
        registry.validate_axes_targets()


class ColorbarProjectTests(ColorbarRuntimeTests):
    def test_schema_v13_roundtrip_preserves_stable_source_relationship(self):
        controller = self.add_colorbar(
            object_id="stable-colorbar",
            properties={
                "label": "Mapped value",
                "location": "bottom",
                "fraction": 0.2,
                "shrink": 0.8,
                "aspect": 15.0,
                "pad": 0.1,
            },
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "colorbar.mygui.json"
            save_project_snapshot(path, self.window.figure_window)
            raw = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(raw["schema_version"], 13)
            record = next(
                item
                for item in raw["figure"]["components"]
                if item["id"] == controller.component_id
            )
            self.assertEqual(
                set(record),
                {
                    "id",
                    "kind",
                    "role",
                    "parent_id",
                    "order",
                    "selector",
                    "properties",
                    "data",
                },
            )
            self.assertEqual(
                record["data"],
                {"source_component_id": "mapped-scatter"},
            )
            self.assertNotIn("profile", str(record).casefold())
            self.assertNotIn("qwidget", str(record).casefold())

            loaded = MainWindow()
            try:
                restore_project_snapshot(path, loaded.table, loaded.figure_window)
                restored = loaded.figure_window.current_canva
                restored_colorbar = restored.component_registry.get(
                    "stable-colorbar"
                )
                restored_source = restored.component_registry.get(
                    "mapped-scatter"
                )
                self.assertEqual(
                    restored_colorbar.state.data,
                    {"source_component_id": restored_source.component_id},
                )
                self.assertIs(
                    restored_colorbar.resolve_target().mappable,
                    restored_source.resolve_target(),
                )
                self.assertEqual(
                    restored_colorbar.state.properties["location"],
                    "bottom",
                )
                self.assertEqual(
                    len(
                        restored.component_registry.query(
                            kind=ComponentKind.AXES
                        )
                    ),
                    1,
                )
                self.assertEqual(len(restored.fig.axes), 2)
            finally:
                loaded.close_without_prompt()
                self.app.processEvents()

    def test_schema_graph_validation_and_v10_migration(self):
        controller = self.add_colorbar()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "schema.mygui.json"
            save_project_snapshot(path, self.window.figure_window)
            valid = json.loads(path.read_text(encoding="utf-8"))
            validate_project_snapshot(valid)

            for mutation, message in (
                (
                    lambda snapshot: next(
                        item
                        for item in snapshot["figure"]["components"]
                        if item["id"] == controller.component_id
                    )["data"].update(source_component_id="missing"),
                    "expected a Scatter component id",
                ),
                (
                    lambda snapshot: next(
                        item
                        for item in snapshot["figure"]["components"]
                        if item["id"] == "mapped-scatter"
                    )["properties"]["color_mapping"].update(enabled=False),
                    "mapping is not enabled",
                ),
                (
                    lambda snapshot: next(
                        item
                        for item in snapshot["figure"]["components"]
                        if item["id"] == controller.component_id
                    )["data"].update(
                        source_component_id=next(
                            item["id"]
                            for item in snapshot["figure"]["components"]
                            if item["kind"] == "axes"
                        )
                    ),
                    "expected a Scatter component id",
                ),
            ):
                candidate = deepcopy(valid)
                mutation(candidate)
                with self.subTest(message=message):
                    with self.assertRaisesRegex(ValueError, message):
                        validate_project_snapshot(candidate)

            no_colorbar = deepcopy(valid)
            no_colorbar["figure"]["components"] = [
                item
                for item in no_colorbar["figure"]["components"]
                if item["kind"] != "colorbar"
            ]
            no_colorbar["schema_version"] = 10
            path.write_text(json.dumps(no_colorbar), encoding="utf-8")
            migrated = load_project_file(path)
            self.assertEqual(migrated["schema_version"], 13)
            self.assertEqual(
                migrated["figure"]["components"],
                no_colorbar["figure"]["components"],
            )

            malformed = deepcopy(no_colorbar)
            next(
                item
                for item in malformed["figure"]["components"]
                if item["id"] == "mapped-scatter"
            )["parent_id"] = "missing"
            path.write_text(json.dumps(malformed), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "Unknown parent component"):
                load_project_file(path)

    def test_colorbar_materializer_failure_leaves_no_staged_project(self):
        self.add_colorbar()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "materializer-failure.mygui.json"
            save_project_snapshot(path, self.window.figure_window)
            loaded = MainWindow()
            try:
                with mock.patch.object(
                    PyFigureCanvas,
                    "_materialize_colorbar",
                    side_effect=RuntimeError("injected Colorbar materializer failure"),
                ):
                    with self.assertRaisesRegex(
                        RuntimeError,
                        "Colorbar materializer failure",
                    ):
                        restore_project_snapshot(
                            path,
                            loaded.table,
                            loaded.figure_window,
                        )
                self.app.processEvents()
                self.assertEqual(loaded.repository.projects, {})
                self.assertEqual(loaded.table._subtables, {})
                self.assertEqual(loaded.figure_window.canvas, {})
                self.assertEqual(loaded.figure_window.tabwindow.count(), 0)
            finally:
                loaded.close_without_prompt()
                self.app.processEvents()


if __name__ == "__main__":
    unittest.main()
