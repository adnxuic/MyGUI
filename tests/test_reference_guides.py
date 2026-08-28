"""Focused contracts for constant Reference Line and Reference Band components."""

from __future__ import annotations

from copy import deepcopy
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
from matplotlib.collections import LineCollection, PolyCollection
from matplotlib.figure import Figure
from PySide6.QtWidgets import QApplication, QDialog

from main import MainWindow
from mygui import status_messages
from mygui.figuremodify.axes_layout import AxesCellSpec, AxesLayoutSpec, AxesViewSpec
from mygui.figuremodify.components import (
    ChangeStatus,
    ComponentKind,
    ComponentMutation,
    ComponentRole,
    ComponentState,
    ComponentValidationError,
    DeletionPolicy,
    ReferenceBandController,
    ReferenceLineController,
    RestorePhase,
)
from mygui.figuremodify.components.serialization import validate_v15_figure
from tests.schema_helpers import figure_as_schema_v18
from mygui.project_io import (
    PROJECT_SCHEMA_VERSION,
    load_project_file,
    project_snapshot,
    restore_project_snapshot,
    save_project_snapshot,
)
from mygui.widgets.title_bar.titlebar_dialog.py_element_dialog import (
    PyReferenceBandDialog,
    PyReferenceLineDialog,
)
from tests.axes_helpers import create_regular_axes


def _guide_state(
    controller_type,
    role: ComponentRole,
    *,
    component_id: str,
    properties: dict[str, object] | None = None,
    selector: dict[str, object] | None = None,
    data: dict[str, object] | None = None,
) -> ComponentState:
    values = controller_type.default_properties()
    values.update(properties or {})
    return ComponentState(
        id=component_id,
        kind=ComponentKind.REFERENCE_GUIDE,
        role=role,
        parent_id="axes-1",
        order=1,
        selector=(
            {"object_id": component_id} if selector is None else selector
        ),
        properties=values,
        data={} if data is None else data,
    )


class ReferenceGuideControllerTests(unittest.TestCase):
    def setUp(self):
        self.figure = Figure()
        self.axes = self.figure.subplots()

    def _line(self, **properties):
        component_id = "reference-line-controller"
        state = _guide_state(
            ReferenceLineController,
            ComponentRole.REFERENCE_LINE,
            component_id=component_id,
            properties=properties,
        )
        artist = LineCollection(
            [],
            transform=self.axes.get_xaxis_transform(),
        )
        self.axes.add_collection(artist, autolim=False)
        controller = ReferenceLineController(state, target=artist)
        self.assertTrue(controller.apply_state(state).ok)
        return controller, artist

    def _band(self, **properties):
        component_id = "reference-band-controller"
        state = _guide_state(
            ReferenceBandController,
            ComponentRole.REFERENCE_BAND,
            component_id=component_id,
            properties=properties,
        )
        artist = PolyCollection(
            [],
            transform=self.axes.get_xaxis_transform(),
        )
        self.axes.add_collection(artist, autolim=False)
        controller = ReferenceBandController(state, target=artist)
        self.assertTrue(controller.apply_state(state).ok)
        return controller, artist

    def test_line_exact_contract_validation_and_normalization(self):
        controller, _artist = self._line()
        self.assertEqual(controller.KIND, ComponentKind.REFERENCE_GUIDE)
        self.assertEqual(controller.ROLES, {ComponentRole.REFERENCE_LINE})
        self.assertEqual(controller.RESTORE_PHASE, RestorePhase.DYNAMIC)
        self.assertEqual(controller.DELETION_POLICY, DeletionPolicy.REMOVE)
        self.assertEqual(controller.state.data, {})
        self.assertEqual(
            set(controller.state.properties),
            {
                "label", "visible", "orientation", "value", "span_start",
                "span_end", "color", "linewidth", "linestyle", "alpha",
                "zorder", "clip_on",
            },
        )
        self.assertTrue(controller.set_property("value", 2).ok)
        self.assertEqual(controller.state.properties["value"], 2.0)

        invalid_properties = (
            {"orientation": "diagonal"},
            {"value": float("nan")},
            {"value": float("inf")},
            {"span_start": 0.5, "span_end": 0.5},
            {"span_start": -0.1},
            {"span_end": 1.1},
        )
        for index, properties in enumerate(invalid_properties):
            with self.subTest(index=index):
                with self.assertRaises(ComponentValidationError):
                    ReferenceLineController(
                        _guide_state(
                            ReferenceLineController,
                            ComponentRole.REFERENCE_LINE,
                            component_id=f"invalid-line-{index}",
                            properties=properties,
                        )
                    )
        with self.assertRaises(ComponentValidationError):
            ReferenceLineController(
                _guide_state(
                    ReferenceLineController,
                    ComponentRole.REFERENCE_LINE,
                    component_id="bad-line-selector",
                    selector={"object_id": "bad-line-selector", "index": 0},
                )
            )
        with self.assertRaises(ComponentValidationError):
            ReferenceLineController(
                _guide_state(
                    ReferenceLineController,
                    ComponentRole.REFERENCE_LINE,
                    component_id="bad-line-data",
                    data={"value": 1.0},
                )
            )

    def test_line_vertical_horizontal_geometry_and_transform(self):
        controller, artist = self._line(
            value=2.5,
            span_start=0.2,
            span_end=0.8,
        )
        np.testing.assert_allclose(
            artist.get_segments()[0],
            ((2.5, 0.2), (2.5, 0.8)),
        )
        self.assertIs(artist.get_transform(), self.axes.get_xaxis_transform())

        change = controller.apply_mutation(
            ComponentMutation(
                controller.component_id,
                properties={
                    "orientation": "horizontal",
                    "value": 4.0,
                    "span_start": 0.1,
                    "span_end": 0.9,
                },
                data={},
            )
        )
        self.assertTrue(change.ok, change.message)
        np.testing.assert_allclose(
            artist.get_segments()[0],
            ((0.1, 4.0), (0.9, 4.0)),
        )
        self.assertIs(artist.get_transform(), self.axes.get_yaxis_transform())

    def test_band_exact_contract_validation_and_geometry(self):
        controller, artist = self._band(
            lower=1.0,
            upper=2.0,
            span_start=0.25,
            span_end=0.75,
        )
        self.assertEqual(controller.ROLES, {ComponentRole.REFERENCE_BAND})
        self.assertEqual(controller.state.data, {})
        np.testing.assert_allclose(
            artist.get_paths()[0].vertices[:4],
            ((1.0, 0.25), (2.0, 0.25), (2.0, 0.75), (1.0, 0.75)),
        )
        self.assertIs(artist.get_transform(), self.axes.get_xaxis_transform())

        change = controller.apply_mutation(
            ComponentMutation(
                controller.component_id,
                properties={
                    "orientation": "horizontal",
                    "lower": 3.0,
                    "upper": 5.0,
                    "span_start": 0.1,
                    "span_end": 0.6,
                },
                data={},
            )
        )
        self.assertTrue(change.ok, change.message)
        np.testing.assert_allclose(
            artist.get_paths()[0].vertices[:4],
            ((0.1, 3.0), (0.6, 3.0), (0.6, 5.0), (0.1, 5.0)),
        )
        self.assertIs(artist.get_transform(), self.axes.get_yaxis_transform())

        for index, properties in enumerate(
            (
                {"lower": 1.0, "upper": 1.0},
                {"lower": 2.0, "upper": 1.0},
                {"lower": float("nan")},
                {"upper": float("inf")},
                {"span_start": 0.9, "span_end": 0.1},
            )
        ):
            with self.subTest(index=index):
                with self.assertRaises(ComponentValidationError):
                    ReferenceBandController(
                        _guide_state(
                            ReferenceBandController,
                            ComponentRole.REFERENCE_BAND,
                            component_id=f"invalid-band-{index}",
                            properties=properties,
                        )
                    )


class ReferenceGuideRuntimeTests(unittest.TestCase):
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
            canva_name="ReferenceGuides",
        )
        self.canvas = self.window.figure_window.current_canva
        self.axes_id = create_regular_axes(self.canvas)[0]
        self.stack = self.window.repository.undo_stack(self.canvas.project_id)
        self.stack.clear()

    def tearDown(self):
        self.window.close_without_prompt()
        self.app.processEvents()

    def test_runtime_autoscale_pan_zoom_linear_and_log_transforms(self):
        axes = self.canvas.current_axes
        axes.plot([1.0, 2.0], [3.0, 4.0])
        axes.relim()
        axes.autoscale()
        data_lim = axes.dataLim.get_points().copy()
        xlim = axes.get_xlim()
        ylim = axes.get_ylim()

        line = self.canvas.add_reference_line(
            {"value": 1000.0, "span_start": 0.2, "span_end": 0.8},
            object_id="runtime-reference-line",
            announce=False,
        )
        band = self.canvas.add_reference_band(
            {"lower": 2000.0, "upper": 3000.0},
            object_id="runtime-reference-band",
            announce=False,
        )
        self.assertIsInstance(line, LineCollection)
        self.assertIsInstance(band, PolyCollection)
        np.testing.assert_allclose(axes.dataLim.get_points(), data_lim)
        self.assertEqual(axes.get_xlim(), xlim)
        self.assertEqual(axes.get_ylim(), ylim)
        self.assertIs(line.get_transform(), axes.get_xaxis_transform())
        self.assertIs(band.get_transform(), axes.get_xaxis_transform())

        axes.relim()
        axes.autoscale()
        np.testing.assert_allclose(axes.dataLim.get_points(), data_lim)
        self.assertLess(axes.get_xlim()[1], 1000.0)

        line_controller = self.canvas.component_registry.get(
            "runtime-reference-line"
        )
        band_controller = self.canvas.component_registry.get(
            "runtime-reference-band"
        )
        self.assertTrue(
            self.canvas.reference_guide_service.apply_properties(
                line_controller,
                {"orientation": "horizontal", "value": 5.0},
            ).ok
        )
        self.assertTrue(
            self.canvas.reference_guide_service.apply_properties(
                band_controller,
                {"orientation": "horizontal", "lower": 6.0, "upper": 7.0},
            ).ok
        )
        self.assertIs(line.get_transform(), axes.get_yaxis_transform())
        self.assertIs(band.get_transform(), axes.get_yaxis_transform())

        axes.set_xscale("log")
        axes.set_yscale("log")
        axes.set_xlim(0.5, 20.0)
        axes.set_ylim(0.5, 20.0)
        self.canvas.fig.canvas.draw()
        self.assertEqual(axes.get_xlim(), (0.5, 20.0))
        self.assertEqual(axes.get_ylim(), (0.5, 20.0))
        np.testing.assert_allclose(
            line.get_segments()[0],
            ((0.2, 5.0), (0.8, 5.0)),
        )
        np.testing.assert_allclose(
            band.get_paths()[0].vertices[:4],
            ((0.0, 6.0), (1.0, 6.0), (1.0, 7.0), (0.0, 7.0)),
        )

    def test_creation_and_edit_failures_restore_exact_identity(self):
        axes = self.canvas.current_axes
        before_collections = tuple(axes.collections)
        before_ids = {
            controller.component_id for controller in self.canvas.component_registry
        }
        before_selection = self.canvas.current_component_id
        before_history = self.stack.count()
        with mock.patch.object(
            self.canvas.reference_guide_service,
            "verify_render",
            side_effect=RuntimeError("injected guide render failure"),
        ):
            with self.assertRaisesRegex(RuntimeError, "injected"):
                self.canvas.add_reference_line(
                    {"value": 2.0},
                    object_id="failed-reference-line",
                    announce=False,
                )
        self.assertEqual(tuple(axes.collections), before_collections)
        self.assertEqual(
            {controller.component_id for controller in self.canvas.component_registry},
            before_ids,
        )
        self.assertEqual(self.canvas.current_component_id, before_selection)
        self.assertEqual(self.stack.count(), before_history)

        original_add_collection = axes.add_collection

        def attach_then_fail(collection, *, autolim=True):
            original_add_collection(collection, autolim=autolim)
            raise RuntimeError("injected failure after runtime attachment")

        with mock.patch.object(
            axes,
            "add_collection",
            side_effect=attach_then_fail,
        ):
            with self.assertRaisesRegex(RuntimeError, "runtime attachment"):
                self.canvas.add_reference_line(
                    {"value": 3.0},
                    object_id="attached-failed-reference-line",
                    announce=False,
                )
        self.assertEqual(tuple(axes.collections), before_collections)
        self.assertNotIn(
            "attached-failed-reference-line",
            self.canvas.component_registry,
        )
        self.assertEqual(self.canvas.current_component_id, before_selection)
        self.assertEqual(self.stack.count(), before_history)

        with mock.patch.object(
            self.canvas.component_registry,
            "register",
            side_effect=RuntimeError("injected guide Registry failure"),
        ):
            with self.assertRaisesRegex(RuntimeError, "Registry"):
                self.canvas.add_reference_band(
                    {"lower": 1.0, "upper": 2.0},
                    object_id="failed-reference-band",
                    announce=False,
                )
        self.assertEqual(tuple(axes.collections), before_collections)
        self.assertNotIn("failed-reference-band", self.canvas.component_registry)
        self.assertEqual(self.stack.count(), before_history)

        line = self.canvas.add_reference_line(
            {"value": 2.0},
            object_id="editable-reference-line",
            announce=False,
        )
        controller = self.canvas.component_registry.get(
            "editable-reference-line"
        )
        before_state = controller.state
        before_segments = [segment.copy() for segment in line.get_segments()]
        before_transform = line.get_transform()
        with mock.patch.object(
            self.canvas.reference_guide_service,
            "verify_render",
            side_effect=RuntimeError("injected guide edit render failure"),
        ):
            change = self.canvas.reference_guide_service.apply_properties(
                controller,
                {"orientation": "horizontal", "value": 4.0},
            )
        self.assertEqual(change.status, ChangeStatus.REJECTED)
        self.assertEqual(controller.state, before_state)
        self.assertIs(controller.resolve_target(), line)
        self.assertIs(line.get_transform(), before_transform)
        self.assertEqual(
            [segment.tolist() for segment in line.get_segments()],
            [segment.tolist() for segment in before_segments],
        )

    def test_multiple_axes_and_right_y_owner_contract(self):
        self.assertTrue(self.canvas.delete_axes(self.axes_id))
        primary_id, right_y_id = self.canvas.create_axes_layout(
            AxesLayoutSpec(
                1,
                1,
                (AxesCellSpec(0, 0, right_y=AxesViewSpec()),),
            )
        )
        self.stack.clear()
        self.canvas.update_current_axes(right_y_id)
        line = self.canvas.add_reference_line(
            {"value": 4.0},
            object_id="right-y-reference-line",
            announce=False,
        )
        right_y_axes = self.canvas.component_registry.resolve_target(right_y_id)
        self.assertIs(line.axes, right_y_axes)
        self.assertIs(line.get_transform(), right_y_axes.get_xaxis_transform())
        self.assertEqual(
            self.canvas.component_registry.get(
                "right-y-reference-line"
            ).state.parent_id,
            right_y_id,
        )

        self.canvas.update_current_axes(primary_id)
        band = self.canvas.add_reference_band(
            {"orientation": "horizontal", "lower": 1.0, "upper": 2.0},
            object_id="primary-reference-band",
            announce=False,
        )
        primary_axes = self.canvas.component_registry.resolve_target(primary_id)
        self.assertIs(band.axes, primary_axes)
        self.assertIs(band.get_transform(), primary_axes.get_yaxis_transform())
        self.assertIsNot(line.axes, band.axes)

    def test_creation_dialogs_without_axes_publish_one_warning_and_nothing_else(self):
        empty_window = MainWindow()
        empty_window.figure_window.add_figure(
            width=4,
            height=3,
            dpi=100,
            style="default",
            canva_name="ReferenceGuidesWithoutAxes",
        )
        canvas = empty_window.figure_window.current_canva
        stack = empty_window.repository.undo_stack(canvas.project_id)
        dialogs = (
            PyReferenceLineDialog(
                "Add Reference Line",
                empty_window.figure_window,
            ),
            PyReferenceBandDialog(
                "Add Reference Band",
                empty_window.figure_window,
            ),
        )
        try:
            with mock.patch.object(status_messages, "show_warning") as warning:
                for dialog in dialogs:
                    dialog.accept()
                    self.assertEqual(dialog.result(), QDialog.Rejected)
            self.assertEqual(warning.call_count, 2)
            self.assertEqual(
                canvas.component_registry.query(
                    kind=ComponentKind.REFERENCE_GUIDE,
                ),
                [],
            )
            self.assertEqual(canvas.fig.axes, [])
            self.assertEqual(stack.count(), 0)
        finally:
            for dialog in dialogs:
                dialog.close()
            empty_window.close_without_prompt()
            self.app.processEvents()

    def test_inspector_tree_and_controller_free_creation_dialogs(self):
        line_dialog = PyReferenceLineDialog(
            "Add Reference Line",
            self.window.figure_window,
        )
        band_dialog = PyReferenceBandDialog(
            "Add Reference Band",
            self.window.figure_window,
        )
        try:
            line_dialog.input.value_input.setValue(2.5)
            line_dialog.accept()
            self.assertEqual(line_dialog.result(), QDialog.Accepted)
            band_dialog.input.orientation_input.setCurrentIndex(1)
            band_dialog.input.lower_input.setValue(-0.2)
            band_dialog.input.upper_input.setValue(0.2)
            band_dialog.accept()
            self.assertEqual(band_dialog.result(), QDialog.Accepted)
        finally:
            line_dialog.close()
            band_dialog.close()

        self.app.processEvents()
        guides = self.canvas.component_registry.query(
            kind=ComponentKind.REFERENCE_GUIDE
        )
        self.assertEqual(len(guides), 2)
        by_role = {controller.state.role: controller for controller in guides}
        line_controller = by_role[ComponentRole.REFERENCE_LINE]
        band_controller = by_role[ComponentRole.REFERENCE_BAND]
        self.assertEqual(line_controller.state.data, {})
        self.assertEqual(band_controller.state.data, {})

        for controller, section_keys in (
            (line_controller, ("general", "position", "line", "advanced")),
            (
                band_controller,
                ("general", "position", "fill", "border", "advanced"),
            ),
        ):
            profile = self.canvas.editor_registry.profile_for(
                controller.state.kind,
                controller.state.role,
            )
            self.assertEqual(
                tuple(section.key for section in profile.sections),
                section_keys,
            )
            exposed = [
                key for section in profile.sections for key in section.property_keys
            ]
            self.assertEqual(len(exposed), len(set(exposed)))
            self.assertEqual(set(exposed), set(controller.state.properties))
            self.assertEqual(profile.tree.group_title, "Reference Guides")
            self.assertEqual(profile.tree.group_key, "reference-guides")

        model = self.window.component_tree_host.model
        line_index = model.index_for_component(line_controller.component_id)
        band_index = model.index_for_component(band_controller.component_id)
        self.assertEqual(model.parent(line_index).data(), "Reference Guides")
        self.assertEqual(model.parent(band_index).data(), "Reference Guides")
        self.assertIn("x = 2.5", line_index.data())
        self.assertIn("-0.2 ≤ y ≤ 0.2", band_index.data())

        inspector = self.canvas.component_editor_manager.editor(
            line_controller.component_id
        )
        position = inspector.section("position")
        with mock.patch.object(
            self.canvas.reference_guide_service,
            "apply_properties",
            wraps=self.canvas.reference_guide_service.apply_properties,
        ) as apply_properties:
            result = position._set_controller_property("value", 3.5)
        self.assertTrue(result.ok)
        apply_properties.assert_called_once()
        self.assertEqual(line_controller.state.properties["value"], 3.5)

    def test_inspector_edits_record_and_replay_guide_history(self):
        self.canvas.add_reference_line(
            {
                "label": "editable line",
                "value": 1.0,
                "span_start": 0.2,
                "span_end": 0.8,
            },
            object_id="history-edit-reference-line",
            announce=False,
        )
        self.canvas.add_reference_band(
            {
                "label": "editable band",
                "lower": 3.0,
                "upper": 4.0,
                "span_start": 0.1,
                "span_end": 0.9,
            },
            object_id="history-edit-reference-band",
            announce=False,
        )
        line_controller = self.canvas.component_registry.get(
            "history-edit-reference-line"
        )
        band_controller = self.canvas.component_registry.get(
            "history-edit-reference-band"
        )
        initial_line = line_controller.state
        initial_band = band_controller.state
        initial_count = self.stack.count()

        with tempfile.TemporaryDirectory() as directory:
            save_project_snapshot(
                Path(directory) / "reference-edit-history.mygui.json",
                self.window.figure_window,
            )
            self.assertFalse(
                self.window.figure_window.is_canvas_dirty(self.canvas)
            )

            self.canvas.select_component(line_controller.component_id)
            line_editor = self.canvas.component_editor_manager.editor(
                line_controller.component_id
            )
            line_edits = (
                ("position", "value", 1.5, "Change Reference Line Value"),
                (
                    "position",
                    "orientation",
                    "horizontal",
                    "Change Reference Line Orientation",
                ),
                (
                    "line",
                    "linestyle",
                    "dashed",
                    "Change Reference Line Line Style",
                ),
            )
            for section_key, property_key, value, command_text in line_edits:
                before_count = self.stack.count()
                self.assertTrue(
                    line_editor.section(section_key).apply_property(
                        property_key,
                        value,
                    )
                )
                self.assertEqual(self.stack.count(), before_count + 1)
                self.assertEqual(self.stack.undoText(), command_text)

            self.canvas.select_component(band_controller.component_id)
            band_editor = self.canvas.component_editor_manager.editor(
                band_controller.component_id
            )
            band_edits = (
                ("position", "lower", 2.5, "Change Reference Band Lower"),
                ("position", "upper", 4.5, "Change Reference Band Upper"),
                (
                    "border",
                    "linewidth",
                    2.25,
                    "Change Reference Band Line Width",
                ),
            )
            for section_key, property_key, value, command_text in band_edits:
                before_count = self.stack.count()
                self.assertTrue(
                    band_editor.section(section_key).apply_property(
                        property_key,
                        value,
                    )
                )
                self.assertEqual(self.stack.count(), before_count + 1)
                self.assertEqual(self.stack.undoText(), command_text)

            edited_line = line_controller.state
            edited_band = band_controller.state
            line_runtime = line_controller.resolve_target()
            band_runtime = band_controller.resolve_target()
            np.testing.assert_allclose(
                line_runtime.get_segments()[0],
                [[0.2, 1.5], [0.8, 1.5]],
            )
            self.assertIs(
                line_runtime.get_transform(),
                self.canvas.current_axes.get_yaxis_transform(),
            )
            self.assertEqual(self.canvas.current_component_id, band_controller.component_id)
            self.assertTrue(
                self.window.figure_window.is_canvas_dirty(self.canvas)
            )

            edit_count = len(line_edits) + len(band_edits)
            self.assertEqual(self.stack.count(), initial_count + edit_count)
            for _index in range(edit_count):
                self.stack.undo()
            self.assertEqual(line_controller.state, initial_line)
            self.assertEqual(band_controller.state, initial_band)
            self.assertEqual(
                self.canvas.current_component_id,
                line_controller.component_id,
            )
            self.assertIsInstance(line_controller.resolve_target(), LineCollection)
            self.assertIsInstance(band_controller.resolve_target(), PolyCollection)
            self.assertFalse(
                self.window.figure_window.is_canvas_dirty(self.canvas)
            )

            for _index in range(edit_count):
                self.stack.redo()
            self.assertEqual(line_controller.state, edited_line)
            self.assertEqual(band_controller.state, edited_band)
            self.assertEqual(
                self.canvas.current_component_id,
                band_controller.component_id,
            )
            self.assertIs(line_controller.resolve_target(), line_runtime)
            self.assertIs(band_controller.resolve_target(), band_runtime)
            self.assertTrue(
                self.window.figure_window.is_canvas_dirty(self.canvas)
            )

    def test_history_batch_delete_axes_subtree_and_round_trip(self):
        self.canvas.add_reference_line(
            {"label": "first", "value": 1.0},
            object_id="history-reference-line-1",
            announce=False,
        )
        self.canvas.add_reference_line(
            {"label": "second", "value": 2.0},
            object_id="history-reference-line-2",
            announce=False,
        )
        self.canvas.add_reference_band(
            {"label": "band", "lower": 3.0, "upper": 4.0},
            object_id="history-reference-band",
            announce=False,
        )
        self.assertEqual(self.stack.count(), 3)
        controller = self.canvas.component_registry.get(
            "history-reference-line-1"
        )
        self.assertTrue(
            self.canvas.editor_context.perform(
                "Change Reference Line Value",
                lambda: self.canvas.reference_guide_service.apply_properties(
                    controller,
                    {"value": 1.5},
                ),
            ).ok
        )
        edited = controller.state
        self.stack.undo()
        self.assertEqual(controller.state.properties["value"], 1.0)
        self.stack.redo()
        self.assertEqual(controller.state, edited)

        self.assertTrue(
            self.canvas.delete_component_group(
                ("history-reference-line-1", "history-reference-line-2"),
                "Reference Lines",
            )
        )
        self.assertNotIn("history-reference-line-1", self.canvas.component_registry)
        self.assertNotIn("history-reference-line-2", self.canvas.component_registry)
        self.assertIn("history-reference-band", self.canvas.component_registry)
        self.stack.undo()
        self.assertEqual(
            self.canvas.component_registry.get("history-reference-line-1").state,
            edited,
        )
        self.assertIn("history-reference-line-2", self.canvas.component_registry)
        self.stack.redo()
        self.assertNotIn("history-reference-line-1", self.canvas.component_registry)

        self.stack.undo()
        before_save = project_snapshot(
            self.window.figure_window,
            canvas=self.canvas,
        )
        self.assertEqual(before_save["schema_version"], PROJECT_SCHEMA_VERSION)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "reference-guides.mygui.json"
            save_project_snapshot(path, self.window.figure_window)
            self.assertEqual(load_project_file(path), before_save)
            loaded = MainWindow()
            try:
                restore_project_snapshot(path, loaded.table, loaded.figure_window)
                restored = loaded.figure_window.current_canva
                for component_id, target_type in (
                    ("history-reference-line-1", LineCollection),
                    ("history-reference-line-2", LineCollection),
                    ("history-reference-band", PolyCollection),
                ):
                    self.assertEqual(
                        restored.component_registry.get(component_id).state,
                        self.canvas.component_registry.get(component_id).state,
                    )
                    self.assertIsInstance(
                        restored.component_registry.resolve_target(component_id),
                        target_type,
                    )
            finally:
                loaded.close_without_prompt()
                self.app.processEvents()

            invalid = deepcopy(before_save)
            for item in invalid["figure"]["components"]:
                if item["id"] == "history-reference-line-1":
                    item["properties"]["value"] = float("nan")
                    break
            invalid_path = Path(directory) / "invalid-reference-guide.json"
            invalid_path.write_text(json.dumps(invalid), encoding="utf-8")
            rejected = MainWindow()
            try:
                with self.assertRaises(ValueError):
                    restore_project_snapshot(
                        invalid_path,
                        rejected.table,
                        rejected.figure_window,
                    )
                self.assertEqual(rejected.figure_window.tabwindow.count(), 0)
                self.assertEqual(rejected.repository.projects, {})
                self.assertEqual(rejected.component_tree_host._sessions, {})
            finally:
                rejected.close_without_prompt()
                self.app.processEvents()

        self.assertTrue(self.canvas.delete_axes(self.axes_id))
        for component_id in (
            "history-reference-line-1",
            "history-reference-line-2",
            "history-reference-band",
        ):
            self.assertNotIn(component_id, self.canvas.component_registry)
        self.stack.undo()
        for component_id in (
            "history-reference-line-1",
            "history-reference-line-2",
            "history-reference-band",
        ):
            self.assertIn(component_id, self.canvas.component_registry)

        validate_v15_figure(
            figure_as_schema_v18(self.canvas.component_snapshot()),
            {},
            self.canvas.project_id,
            self.canvas.project_name,
        )
        self.assertEqual(PROJECT_SCHEMA_VERSION, 19)


if __name__ == "__main__":
    unittest.main()
