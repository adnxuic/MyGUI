import unittest
from unittest.mock import Mock

import numpy as np
from matplotlib.figure import Figure

from code.figuremodify.component_services import FunctionCurveService
from code.figuremodify.components import (
    ComponentKind,
    ComponentRegistry,
    ComponentRole,
    ComponentState,
    DataPlotController,
    FunctionCurveController,
    ScatterController,
)


class ChartControllerStyleTests(unittest.TestCase):
    def setUp(self):
        self.figure = Figure()
        self.axes = self.figure.subplots()
        self.figure.canvas.draw_idle = Mock()
        self.registry = ComponentRegistry()

    def _register(self, controller_type, component_id, role, artist, data):
        state = ComponentState(
            id=component_id,
            kind=(
                ComponentKind.SCATTER
                if role is ComponentRole.SCATTER
                else ComponentKind.LINE
            ),
            role=role,
            order=0,
            selector={"object_id": component_id},
            properties={},
            data=data,
        )
        return self.registry.register(
            controller_type(state),
            target=artist,
            require_parent=False,
        )

    def test_curve_rejects_invalid_expression_atomically(self):
        line, = self.axes.plot([0.0, 1.0], [0.0, 1.0], label="curve")
        controller = self._register(
            FunctionCurveController,
            "curve",
            ComponentRole.FUNCTION_CURVE,
            line,
            {"expression": "x", "x_start": 0.0, "x_stop": 1.0},
        )
        previous_y = np.asarray(line.get_ydata()).copy()

        result = FunctionCurveService(self.registry).update(
            controller,
            "__import__('os')",
            0.0,
            1.0,
        )

        self.assertFalse(result.ok)
        self.assertEqual(controller.state.data["expression"], "x")
        np.testing.assert_array_equal(line.get_ydata(), previous_y)

    def test_plot_style_and_size_update_artist_and_controller_state(self):
        line, = self.axes.plot([0.0, 1.0], [1.0, 2.0], label="plot")
        ref = {"project_id": "p", "sheet_id": "s", "column_id": "c"}
        controller = self._register(
            DataPlotController,
            "plot",
            ComponentRole.DATA_PLOT,
            line,
            {"x_ref": ref, "y_ref": {**ref, "column_id": "y"}},
        )

        style = controller.set_property("linestyle", "--")
        size = controller.set_property("markersize", 7.5)

        self.assertTrue(style.ok)
        self.assertTrue(size.ok)
        self.assertEqual(line.get_linestyle(), "--")
        self.assertEqual(line.get_markersize(), 7.5)
        self.assertEqual(controller.state.properties["linestyle"], "--")
        self.assertEqual(controller.state.properties["markersize"], 7.5)

    def test_scatter_marker_and_size_update_artist_and_state(self):
        scatter = self.axes.scatter(
            [0.0, 1.0],
            [1.0, 2.0],
            s=20,
            marker="o",
            label="scatter",
        )
        ref = {"project_id": "p", "sheet_id": "s", "column_id": "c"}
        controller = self._register(
            ScatterController,
            "scatter",
            ComponentRole.SCATTER,
            scatter,
            {"x_ref": ref, "y_ref": {**ref, "column_id": "y"}},
        )

        marker = controller.set_property("marker", "s")
        size = controller.set_property("size", 42.0)

        self.assertTrue(marker.ok)
        self.assertTrue(size.ok)
        self.assertEqual(controller.state.properties["marker"], "s")
        self.assertEqual(controller.state.properties["size"], 42.0)
        np.testing.assert_allclose(scatter.get_sizes(), [42.0])

    def test_registry_delete_is_idempotent_and_refreshes_legend(self):
        line, = self.axes.plot([0.0, 1.0], [1.0, 2.0], label="plot")
        self.axes.legend()
        ref = {"project_id": "p", "sheet_id": "s", "column_id": "c"}
        controller = self._register(
            DataPlotController,
            "plot",
            ComponentRole.DATA_PLOT,
            line,
            {"x_ref": ref, "y_ref": {**ref, "column_id": "y"}},
        )

        first = controller.delete()
        second = controller.delete()

        self.assertTrue(first.ok)
        self.assertTrue(second.ok)
        self.assertNotIn("plot", self.registry)
        self.assertNotIn(line, self.axes.lines)
        self.assertIsNone(self.axes.get_legend())


if __name__ == "__main__":
    unittest.main()
