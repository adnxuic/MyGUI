import unittest
from unittest.mock import Mock

import numpy as np
from matplotlib.figure import Figure

from code.database import ColumnRef, TableRepository
from code.figuremodify.component_services import (
    AxesCommandService,
    ChartDataService,
    ComponentDependencyService,
)
from code.figuremodify.components import (
    ComponentEventKind,
    ComponentKind,
    ComponentMutation,
    ComponentRegistry,
    ComponentRole,
    ComponentState,
    DataPlotController,
    FitCurveController,
    register_figure_components,
)
from code.figuremodify.style_base.color_models import PaletteDefinition


def _ref(project_id, sheet_id, column_id):
    return {
        "project_id": project_id,
        "sheet_id": sheet_id,
        "column_id": column_id,
    }


class ComponentServiceTests(unittest.TestCase):
    def setUp(self):
        self.repository = TableRepository()
        self.project = self.repository.create_project("Data")
        self.sheet = next(iter(self.project.sheets.values()))
        self.sheet.set_block(
            0,
            0,
            [[0.0, 1.0], [1.0, 2.0], [2.0, 4.0]],
        )
        self.x_ref = ColumnRef(
            self.project.id,
            self.sheet.id,
            self.sheet.columns[0].id,
        )
        self.y_ref = ColumnRef(
            self.project.id,
            self.sheet.id,
            self.sheet.columns[1].id,
        )
        self.figure = Figure()
        self.axes = self.figure.subplots()
        self.figure.canvas.draw_idle = Mock()
        self.registry = ComponentRegistry()

    def _line_controller(self, component_id, role, line):
        controller_type = (
            FitCurveController
            if role is ComponentRole.FIT_CURVE
            else DataPlotController
        )
        data = {
            "x_ref": self.x_ref.to_dict(),
            "y_ref": self.y_ref.to_dict(),
        }
        if role is ComponentRole.FIT_CURVE:
            data.update(
                engine="Python",
                fit_type=None,
                fit_options=None,
                fit_result=None,
                expression="",
                x_start=0.0,
                x_stop=2.0,
            )
        controller = controller_type(
            ComponentState(
                id=component_id,
                kind=ComponentKind.LINE,
                role=role,
                order=len(self.registry),
                selector={"object_id": component_id},
                properties={"label": component_id},
                data=data,
            )
        )
        return self.registry.register(
            controller,
            target=line,
            require_parent=False,
        )

    def test_registry_transaction_publishes_only_committed_events_and_draws_once(self):
        first_line, = self.axes.plot([0, 1], [1, 2])
        second_line, = self.axes.plot([0, 1], [2, 3])
        first = self._line_controller(
            "first",
            ComponentRole.DATA_PLOT,
            first_line,
        )
        second = self._line_controller(
            "second",
            ComponentRole.DATA_PLOT,
            second_line,
        )
        events = []
        self.registry.subscribe(events.append)
        self.figure.canvas.draw_idle.reset_mock()

        result = self.registry.apply_transaction(
            (
                ComponentMutation(
                    first.component_id,
                    properties={"color": "#112233"},
                ),
                ComponentMutation(
                    second.component_id,
                    properties={"color": "#445566"},
                ),
            )
        )

        self.assertTrue(result.ok)
        self.assertEqual(
            [event.kind for event in events],
            [ComponentEventKind.CHANGED, ComponentEventKind.CHANGED],
        )
        self.assertEqual(self.figure.canvas.draw_idle.call_count, 1)

    def test_registry_transaction_rolls_back_artist_state_and_events(self):
        first_line, = self.axes.plot([0, 1], [1, 2], color="#010101")
        second_line, = self.axes.plot([0, 1], [2, 3], color="#020202")
        first = self._line_controller(
            "first",
            ComponentRole.DATA_PLOT,
            first_line,
        )
        second = self._line_controller(
            "second",
            ComponentRole.DATA_PLOT,
            second_line,
        )
        events = []
        self.registry.subscribe(events.append)
        original_write = second._write_property

        def reject_blue(target, spec, value):
            if (
                spec.key == "color"
                and str(value).casefold() == "#0000ff"
            ):
                raise RuntimeError("synthetic failure")
            return original_write(target, spec, value)

        second._write_property = reject_blue
        try:
            result = self.registry.apply_transaction(
                (
                    ComponentMutation(
                        first.component_id,
                        properties={"color": "#FF0000"},
                    ),
                    ComponentMutation(
                        second.component_id,
                        properties={"color": "#0000FF"},
                    ),
                )
            )
        finally:
            second._write_property = original_write

        self.assertFalse(result.ok)
        self.assertEqual(first_line.get_color().casefold(), "#010101")
        self.assertEqual(second_line.get_color().casefold(), "#020202")
        self.assertEqual(first.state.properties["color"], "#010101")
        self.assertEqual(second.state.properties["color"], "#020202")
        self.assertEqual(events, [])

    def test_empty_axes_can_select_palette_for_future_charts(self):
        registry = register_figure_components(self.figure)
        axes_controller = next(
            controller
            for controller in registry
            if controller.state.kind is ComponentKind.AXES
        )
        service = AxesCommandService(registry)
        palette = PaletteDefinition(
            "custom:future",
            "Future",
            ("#112233", "#445566"),
            source="custom",
        )

        result = service.apply_palette(
            axes_controller.component_id,
            palette,
        )

        self.assertTrue(result.ok)
        self.assertTrue(result.notices)
        self.assertEqual(
            service.cycle_state(
                axes_controller.component_id
            ).active_palette,
            palette,
        )
        status = service.palette_status(axes_controller.component_id)
        self.assertFalse(status.uses_style_default)
        self.assertEqual(status.palette, palette)

    def test_table_refresh_skips_manual_fit_and_keeps_empty_plot_controller(self):
        pair = self.repository.line_pair(self.x_ref, self.y_ref)
        plot_line, = self.axes.plot(pair.x, pair.y)
        fit_line, = self.axes.plot(pair.x, pair.y)
        plot = self._line_controller(
            "plot",
            ComponentRole.DATA_PLOT,
            plot_line,
        )
        fit = self._line_controller(
            "fit",
            ComponentRole.FIT_CURVE,
            fit_line,
        )
        service = ChartDataService(self.repository, self.registry)

        self.sheet.set_block(0, 0, [["", ""], ["", ""], ["", ""]])
        results = service.refresh_affected({self.y_ref})

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].component_id, plot.component_id)
        self.assertTrue(results[0].ok)
        self.assertTrue(results[0].notices)
        self.assertIn(plot.component_id, self.registry)
        self.assertEqual(len(fit_line.get_xdata()), 3)
        self.assertFalse(
            np.isfinite(np.asarray(plot_line.get_ydata(), dtype=float)).any()
        )
        self.assertEqual(fit.state.data["expression"], "")

    def test_dependency_service_restores_exact_component_state(self):
        pair = self.repository.line_pair(self.x_ref, self.y_ref)
        line, = self.axes.plot(pair.x, pair.y)
        controller = self._line_controller(
            "plot",
            ComponentRole.DATA_PLOT,
            line,
        )
        restored = []
        service = ComponentDependencyService(
            self.registry,
            restore_state=restored.append,
        )

        snapshots = service.dependent_states({self.x_ref})
        service.delete_states(snapshots)
        service.restore_states(snapshots)

        self.assertNotIn(controller.component_id, self.registry)
        self.assertEqual(restored, snapshots)


if __name__ == "__main__":
    unittest.main()
