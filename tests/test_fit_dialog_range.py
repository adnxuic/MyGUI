"""Unit and integration tests for Fit Data Range widget and FitService."""

from __future__ import annotations

import unittest
import numpy as np

from PySide6.QtWidgets import QApplication

from mygui.database import (
    ColumnRef,
    ColumnType,
    DataPreprocessSpec,
    FitInputRangeSpec,
    TableRepository,
    scipy_fit_adapter,
    select_fit_input_pair,
)
from mygui.figuremodify.components import (
    ComponentKind,
    ComponentRegistry,
    ComponentRole,
    ComponentState,
    FitCurveController,
    FitEngine,
)
from mygui.figuremodify.services.chart_data import FitService
from mygui.widgets.fig_control_window.py_fit_options_window import FitDataRangeWidget


def _app() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


class FitDataRangeWidgetTests(unittest.TestCase):
    """Test FitDataRangeWidget UI controls and validation."""

    @classmethod
    def setUpClass(cls):
        _app()

    def test_widget_defaults_and_toggle(self):
        widget = FitDataRangeWidget()
        self.assertTrue(widget.use_all_checkbox.isChecked())
        self.assertFalse(widget.minimum_input.isEnabled())
        self.assertFalse(widget.maximum_input.isEnabled())
        self.assertEqual(widget.range_spec(), FitInputRangeSpec(kind="all"))

        widget.set_available_range(10.0, 200.0)
        self.assertIn("10 to 200", widget.available_label.text())

        # Uncheck "use all" enables inputs and populates available range
        widget.use_all_checkbox.setChecked(False)
        self.assertTrue(widget.minimum_input.isEnabled())
        self.assertTrue(widget.maximum_input.isEnabled())
        self.assertEqual(widget.minimum_input.text(), "10")
        self.assertEqual(widget.maximum_input.text(), "200")
        self.assertEqual(
            widget.range_spec(),
            FitInputRangeSpec(kind="bounded", minimum=10.0, maximum=200.0),
        )

        # Re-checking disables inputs
        widget.use_all_checkbox.setChecked(True)
        self.assertFalse(widget.minimum_input.isEnabled())
        self.assertFalse(widget.maximum_input.isEnabled())
        self.assertEqual(widget.range_spec(), FitInputRangeSpec(kind="all"))

    def test_widget_set_range_spec(self):
        widget = FitDataRangeWidget()
        widget.set_available_range(0.0, 500.0)

        # Set bounded range
        widget.set_range_spec(FitInputRangeSpec(kind="bounded", minimum=50.0, maximum=300.0))
        self.assertFalse(widget.use_all_checkbox.isChecked())
        self.assertEqual(widget.minimum_input.text(), "50")
        self.assertEqual(widget.maximum_input.text(), "300")
        self.assertEqual(
            widget.range_spec(),
            FitInputRangeSpec(kind="bounded", minimum=50.0, maximum=300.0),
        )

        # Set all-data range
        widget.set_range_spec(FitInputRangeSpec(kind="all"))
        self.assertTrue(widget.use_all_checkbox.isChecked())
        self.assertEqual(widget.range_spec(), FitInputRangeSpec(kind="all"))

    def test_widget_input_validation(self):
        widget = FitDataRangeWidget()
        widget.use_all_checkbox.setChecked(False)

        widget.minimum_input.setText("")
        widget.maximum_input.setText("100")
        with self.assertRaisesRegex(ValueError, "minimum must not be empty"):
            widget.range_spec()

        widget.minimum_input.setText("50")
        widget.maximum_input.setText("")
        with self.assertRaisesRegex(ValueError, "maximum must not be empty"):
            widget.range_spec()

        widget.minimum_input.setText("not_a_number")
        widget.maximum_input.setText("100")
        with self.assertRaisesRegex(ValueError, "minimum must be a finite number"):
            widget.range_spec()

        widget.minimum_input.setText("50")
        widget.maximum_input.setText("inf")
        with self.assertRaisesRegex(ValueError, "maximum must be a finite number"):
            widget.range_spec()

        widget.minimum_input.setText("100")
        widget.maximum_input.setText("50")
        with self.assertRaisesRegex(ValueError, "minimum must be below maximum"):
            widget.range_spec()


class FitServiceRangeIntegrationTests(unittest.TestCase):
    """Test FitService handling of fit_input_range across workflows."""

    def setUp(self):
        _app()
        self.repository = TableRepository()
        self.project_id = "test-project"
        doc = self.repository.create_project("Project", project_id=self.project_id)
        sheet = next(iter(doc.sheets.values()))
        self.sheet_id = sheet.id
        col_x = sheet.add_column("X", ColumnType.NUMBER, values=[2.0, 50.0, 150.0, 300.0, 350.0])
        col_y = sheet.add_column("Y", ColumnType.NUMBER, values=[10.0, 20.0, 30.0, 40.0, 50.0])
        self.x_col_id = col_x.id
        self.y_col_id = col_y.id
        self.x_ref = ColumnRef(self.project_id, self.sheet_id, self.x_col_id)
        self.y_ref = ColumnRef(self.project_id, self.sheet_id, self.y_col_id)
        self.registry = ComponentRegistry()
        self.fit_service = FitService(self.repository, self.registry)

        # Create a Line2D artist mock/instance
        from matplotlib.lines import Line2D
        self.artist = Line2D([], [])
        self.controller = FitCurveController(
            ComponentState(
                id="fit-1",
                kind=ComponentKind.LINE,
                role=ComponentRole.FIT_CURVE,
                parent_id="axes-1",
                order=1,
                selector={"object_id": "fit-1"},
                properties={"visible": True, "color": "blue"},
                data={
                    "x_ref": self.x_ref.to_dict(),
                    "y_ref": self.y_ref.to_dict(),
                    "preprocess": DataPreprocessSpec().to_dict(),
                    "engine": FitEngine.PYTHON.value,
                    "fit_type": "poly1",
                    "fit_options": {},
                    "fit_result": {},
                    "expression": "",
                    "x_start": 0.0,
                    "x_stop": 1.0,
                    "fit_input_range": {"kind": "all"},
                },
            )
        )
        self.registry.register(self.controller, target=self.artist, require_parent=False)

    def test_apply_result_with_bounded_range(self):
        pair = self.fit_service.resolve_sources(self.controller)
        spec = FitInputRangeSpec(kind="bounded", minimum=50.0, maximum=300.0)
        selected = select_fit_input_pair(pair, spec)
        self.assertEqual(len(selected.x), 3)

        fit_res = scipy_fit_adapter.fit_curve(selected.x, selected.y, "poly1")
        change = self.fit_service.apply_result(
            self.controller,
            engine=FitEngine.PYTHON,
            fit_type="poly1",
            fit_options={},
            fit_result=fit_res,
            expression=fit_res["value_expression"],
            x_start=selected.x_start,
            x_stop=selected.x_stop,
            fit_input_range=spec,
        )
        self.assertTrue(change.ok)
        state_data = self.controller.state.data
        self.assertEqual(state_data["x_start"], 50.0)
        self.assertEqual(state_data["x_stop"], 300.0)
        self.assertEqual(
            state_data["fit_input_range"],
            {"kind": "bounded", "minimum": 50.0, "maximum": 300.0},
        )
        # Verify rendered X interval matches [50.0, 300.0]
        line_x, _ = self.artist.get_data()
        self.assertAlmostEqual(float(np.min(line_x)), 50.0)
        self.assertAlmostEqual(float(np.max(line_x)), 300.0)

    def test_update_display_range_preserves_fit_input_range(self):
        self.test_apply_result_with_bounded_range()
        change = self.fit_service.update_display_range(self.controller, 0.0, 400.0)
        self.assertTrue(change.ok)
        state_data = self.controller.state.data
        self.assertEqual(state_data["x_start"], 0.0)
        self.assertEqual(state_data["x_stop"], 400.0)
        self.assertEqual(
            state_data["fit_input_range"],
            {"kind": "bounded", "minimum": 50.0, "maximum": 300.0},
        )

    def test_set_sources_retains_range_and_marks_pending(self):
        self.test_apply_result_with_bounded_range()
        self.assertFalse(self.fit_service.has_pending_source_change("fit-1"))

        # Update preprocessing
        spec = DataPreprocessSpec(x_expression="2*x")
        change = self.fit_service.set_sources(
            self.controller,
            self.x_ref,
            self.y_ref,
            preprocess=spec,
        )
        self.assertTrue(change.changed)
        self.assertTrue(self.fit_service.has_pending_source_change("fit-1"))
        # fit_input_range is retained
        self.assertEqual(
            self.controller.state.data["fit_input_range"],
            {"kind": "bounded", "minimum": 50.0, "maximum": 300.0},
        )


if __name__ == "__main__":
    unittest.main()
