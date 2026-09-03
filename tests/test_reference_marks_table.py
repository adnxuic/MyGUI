"""Reflection Positions table merge, refresh, and dependency tests."""

from __future__ import annotations

import os
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pandas as pd
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.collections import LineCollection
from matplotlib.figure import Figure

from mygui.database import ColumnRef, ColumnType, TableRepository
from mygui.figuremodify.components import (
    ChangeStatus,
    ComponentKind,
    ComponentRole,
    ComponentState,
    ReferenceMarksController,
    register_figure_components,
)
from mygui.figuremodify.components.errors import ComponentValidationError
from mygui.figuremodify.reference_marks_data import merged_reference_positions
from main import MainWindow
from tests.axes_helpers import create_regular_axes


class MergedReferencePositionTests(unittest.TestCase):
    def setUp(self):
        self.repository = TableRepository()
        self.project = self.repository.create_project("Merge")
        self.sheet = next(iter(self.project.sheets.values()))
        number = self.sheet.add_column(
            "theta",
            ColumnType.NUMBER,
            values=[10.0, None, 10.0, 22.5],
        )
        text = self.sheet.add_column(
            "label",
            ColumnType.TEXT,
            values=["a", "b", "c", "d"],
        )
        self.number_ref = ColumnRef(self.project.id, self.sheet.id, number.id)
        self.text_ref = ColumnRef(self.project.id, self.sheet.id, text.id)

    def test_manual_table_merge_order_duplicates_and_empty_cells(self):
        merged = merged_reference_positions(
            self.repository,
            self.project.id,
            [1.5, 1.5],
            self.number_ref,
        )
        self.assertEqual(merged, [1.5, 1.5, 10.0, 10.0, 22.5])
        self.assertEqual(
            merged_reference_positions(
                self.repository,
                self.project.id,
                [],
                self.number_ref,
            ),
            [10.0, 10.0, 22.5],
        )
        self.assertEqual(
            merged_reference_positions(self.repository, self.project.id, [3.0], None),
            [3.0],
        )

    def test_invalid_ref_and_nonfinite_values_are_rejected(self):
        with self.assertRaises(ComponentValidationError):
            merged_reference_positions(
                self.repository,
                self.project.id,
                [],
                self.text_ref,
            )
        with patch.object(
            self.repository,
            "series",
            return_value=pd.Series([1.0, float("inf")]),
        ):
            with self.assertRaises(ComponentValidationError):
                merged_reference_positions(
                    self.repository,
                    self.project.id,
                    [1.0],
                    self.number_ref,
                )


class ReferenceMarksTableRuntimeTests(unittest.TestCase):
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
            canva_name="Reflections",
        )
        self.canvas = self.window.figure_window.current_canva
        create_regular_axes(self.canvas)
        self.view = self.window.table.current_subtable().get_table(0)
        self.sheet = self.view.table_model.sheet
        self.sheet.set_block(0, 0, [[15.2], [None], [15.2], [22.9]])
        self.ref = ColumnRef(
            self.canvas.project_id,
            self.sheet.id,
            self.sheet.columns[0].id,
        )

    def tearDown(self):
        self.window.close()
        self.app.processEvents()

    def test_create_merge_live_refresh_and_rollback(self):
        artist = self.canvas.add_reference_marks(
            [1.0],
            {"label": "mixed"},
            object_id="merged-marks",
            announce=False,
            position_ref=self.ref,
        )
        controller = self.canvas.component_registry.get("merged-marks")
        self.assertEqual(controller.state.data["positions"], [1.0])
        self.assertEqual(controller.state.data["position_ref"], self.ref.to_dict())
        xs = [float(segment[0][0]) for segment in artist.get_segments()]
        self.assertEqual(xs, [1.0, 15.2, 15.2, 22.9])

        self.view.table_model.setData(self.view.table_model.index(0, 0), "30", Qt.EditRole)
        self.view.table_model.setData(self.view.table_model.index(1, 0), "31", Qt.EditRole)
        xs = [float(segment[0][0]) for segment in artist.get_segments()]
        self.assertEqual(xs[0], 1.0)
        self.assertIn(30.0, xs)
        self.assertIn(31.0, xs)
        self.assertEqual(controller.state.data["positions"], [1.0])

        before = controller.state
        before_segments = [segment.copy() for segment in artist.get_segments()]
        change = self.canvas.reference_marks_service.update_data(
            controller,
            [float("nan")],
            self.ref,
        )
        self.assertEqual(change.status, ChangeStatus.REJECTED)
        self.assertEqual(controller.state, before)
        self.assertEqual(
            [segment.tolist() for segment in artist.get_segments()],
            [segment.tolist() for segment in before_segments],
        )

    def test_column_deletion_removes_dependent_marks_and_undo_restores_id(self):
        self.canvas.add_reference_marks(
            [],
            object_id="dependent-marks",
            announce=False,
            position_ref=self.ref,
        )
        self.view.setCurrentIndex(self.view.table_model.index(0, 0))
        with patch(
            "mygui.widgets.figure_canvas.py_figure_window.ask_confirmation",
            return_value=True,
        ):
            self.view.delete_column()
        self.assertNotIn("dependent-marks", self.canvas.component_registry)
        self.assertFalse(self.canvas.repository.has_ref(self.ref))
        self.canvas.repository.undo_stack(self.canvas.project_id).undo()
        restored = self.canvas.component_registry.get("dependent-marks")
        self.assertEqual(restored.state.id, "dependent-marks")
        self.assertEqual(restored.state.data["position_ref"], self.ref.to_dict())
        self.assertEqual(
            [float(segment[0][0]) for segment in restored.resolve_target().get_segments()],
            [15.2, 15.2, 22.9],
        )


class ReferenceMarksControllerDataShapeTests(unittest.TestCase):
    def test_apply_state_keeps_position_ref_and_empty_manual_data(self):
        figure = Figure()
        FigureCanvasAgg(figure)
        axes = figure.subplots()
        artist = LineCollection([], transform=axes.get_xaxis_transform())
        axes.add_collection(artist, autolim=False)
        registry = register_figure_components(figure)
        axes_controller = registry.find_one(
            kind=ComponentKind.AXES,
            role=ComponentRole.AXES,
        )
        controller = ReferenceMarksController(
            ComponentState(
                id="shape-marks",
                kind=ComponentKind.REFERENCE_MARKS,
                role=ComponentRole.REFLECTION_POSITIONS,
                parent_id=axes_controller.component_id,
                order=0,
                selector={"object_id": "shape-marks"},
                properties=ReferenceMarksController.default_properties(),
                data={
                    "positions": [2.0],
                    "position_ref": None,
                    "placement": {"kind": "fixed"},
                },
            ),
            target=artist,
        )
        self.assertTrue(controller.apply_state(controller.state).ok)
        change = controller.apply_state(
            controller.state.clone(
                data={
                    "positions": [],
                    "position_ref": None,
                    "placement": {"kind": "fixed"},
                }
            )
        )
        self.assertEqual(change.status, ChangeStatus.EMPTY)
        self.assertEqual(
            controller.snapshot().data,
            {
                "positions": [],
                "position_ref": None,
                "placement": {"kind": "fixed"},
            },
        )


if __name__ == "__main__":
    unittest.main()
