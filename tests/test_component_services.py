import unittest
from unittest.mock import Mock, patch

import matplotlib
import numpy as np
from matplotlib.figure import Figure

from mygui.database import ColumnRef, DataPreprocessSpec, TableRepository
from mygui.database.interpolate_func import interpolate_dict
from mygui.figuremodify.component_services import (
    AxesCommandService,
    ChartDataService,
    ComponentDependencyService,
    FitService,
    InterpolationService,
)
from mygui.figuremodify.components import (
    ComponentEventKind,
    ComponentKind,
    ComponentMutation,
    ComponentRegistry,
    ComponentRegistrationError,
    ComponentRole,
    ComponentState,
    DataPlotController,
    DeletionPolicy,
    FitCurveController,
    FigureController,
    LegendController,
    LineController,
    InterpolationController,
    ScatterController,
    TextController,
    TitleController,
    register_figure_components,
)
from mygui.figuremodify.style_base.color_models import PaletteDefinition


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
            "preprocess": DataPreprocessSpec().to_dict(),
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

    def test_first_party_deletion_policy_and_matplotlib_axes_contract(self):
        self.assertEqual(matplotlib.__version__, "3.9.0")
        self.assertIs(
            FigureController.DELETION_POLICY,
            DeletionPolicy.FORBID,
        )
        self.assertIs(
            TitleController.DELETION_POLICY,
            DeletionPolicy.HIDE,
        )
        self.assertIs(
            LegendController.DELETION_POLICY,
            DeletionPolicy.HIDE,
        )
        for controller_type in (
            LineController,
            ScatterController,
            TextController,
        ):
            self.assertIs(
                controller_type.DELETION_POLICY,
                DeletionPolicy.REMOVE,
            )
        self.assertIsInstance(self.figure._localaxes, list)
        self.assertIsInstance(self.figure._axstack._axes, dict)
        self.assertIn(self.axes, self.figure._localaxes)
        self.assertIn(self.axes, self.figure._axstack._axes)

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

    def test_nested_registration_reuses_scope_and_reports_rollback_errors(self):
        registry = ComponentRegistry()
        with registry.registration_transaction() as outer:
            with registry.registration_transaction() as inner:
                self.assertIs(inner, outer)

        def fail_rollback():
            raise RuntimeError("injected rollback failure")

        with self.assertRaises(ComponentRegistrationError) as captured:
            with registry.registration_transaction() as transaction:
                transaction.on_rollback(fail_rollback)
                raise ValueError("injected primary failure")

        error = captured.exception
        self.assertFalse(error.rollback_complete)
        self.assertIn("primary failure", str(error.primary_error))
        self.assertEqual(len(error.rollback_errors), 1)

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
        first_state = first.state
        second_state = second.state
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
        self.assertEqual(first.state, first_state)
        self.assertEqual(second.state, second_state)
        self.assertEqual(events, [])

    def test_delete_transaction_rolls_back_same_objects_without_events(self):
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
        original_lines = tuple(self.axes.lines)
        events = []
        cleanup = []
        self.registry.subscribe(events.append)
        self.registry.add_cleanup_callback(
            first.component_id,
            lambda state: cleanup.append(state.id),
        )
        original_commit = second.commit_remove

        def fail_commit(_handle):
            raise RuntimeError("synthetic detach failure")

        second.commit_remove = fail_commit
        try:
            result = self.registry.delete_transaction(
                (first.component_id, second.component_id)
            )
        finally:
            second.commit_remove = original_commit

        self.assertFalse(result.ok)
        self.assertIs(self.registry.get(first.component_id), first)
        self.assertIs(self.registry.get(second.component_id), second)
        self.assertIs(first.resolve_target(), first_line)
        self.assertIs(second.resolve_target(), second_line)
        self.assertEqual(tuple(self.axes.lines), original_lines)
        self.assertFalse(first.deleted)
        self.assertFalse(second.deleted)
        self.assertEqual(events, [])
        self.assertEqual(cleanup, [])
        self.figure.canvas.draw_idle.assert_not_called()

    def test_delete_transaction_verifier_failure_restores_container_order(self):
        lines = [
            self.axes.plot([0, 1], [index, index + 1])[0]
            for index in range(4)
        ]
        first = self._line_controller(
            "first",
            ComponentRole.DATA_PLOT,
            lines[1],
        )
        second = self._line_controller(
            "second",
            ComponentRole.DATA_PLOT,
            lines[2],
        )
        original = tuple(self.axes.lines)

        def reject_candidate():
            raise RuntimeError("synthetic tree verifier failure")

        result = self.registry.delete_transaction(
            (first.component_id, second.component_id),
            verifier=reject_candidate,
        )

        self.assertFalse(result.ok)
        self.assertEqual(tuple(self.axes.lines), original)
        self.assertIs(self.axes.lines[1], lines[1])
        self.assertIs(self.axes.lines[2], lines[2])

    def test_delete_transaction_reports_failed_rollback_compensation(self):
        line, = self.axes.plot([0, 1], [1, 2])
        controller = self._line_controller(
            "rollback-incomplete",
            ComponentRole.DATA_PLOT,
            line,
        )
        original_rollback = controller.rollback_remove

        def restore_then_report_failure(handle):
            original_rollback(handle)
            raise RuntimeError("synthetic rollback hook failure")

        with patch.object(
            controller,
            "rollback_remove",
            side_effect=restore_then_report_failure,
        ):
            result = self.registry.delete_transaction(
                (controller.component_id,),
                verifier=lambda: (_ for _ in ()).throw(
                    RuntimeError("synthetic verifier failure")
                ),
            )

        self.assertFalse(result.ok)
        self.assertFalse(result.rollback_complete)
        self.assertIn("Rollback was incomplete", result.message)
        self.assertIs(self.registry.get(controller.component_id), controller)
        self.assertIs(controller.resolve_target(), line)
        self.assertIn(line, self.axes.lines)

    def test_delete_transaction_keeps_commit_when_repaint_fails(self):
        line, = self.axes.plot([0, 1], [1, 2])
        controller = self._line_controller(
            "first",
            ComponentRole.DATA_PLOT,
            line,
        )
        self.figure.canvas.draw_idle.side_effect = RuntimeError(
            "synthetic repaint failure"
        )

        result = self.registry.delete_transaction(
            (controller.component_id,)
        )

        self.assertTrue(result.ok)
        self.assertNotIn(controller.component_id, self.registry)
        self.assertNotIn(line, self.axes.lines)
        self.assertEqual(len(result.notices), 1)
        self.assertEqual(result.notices[0].level.value, "warning")
        self.assertIn("repaint failed", result.notices[0].message)

    def test_delete_transaction_commits_cleanup_events_and_one_draw(self):
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
        cleanup = []
        self.registry.subscribe(events.append)
        for controller in (first, second):
            self.registry.add_cleanup_callback(
                controller.component_id,
                lambda state: cleanup.append(state.id),
            )
        self.figure.canvas.draw_idle.reset_mock()

        result = self.registry.delete_transaction(
            ("first", "first", "second")
        )

        self.assertTrue(result.ok)
        self.assertEqual(tuple(self.axes.lines), ())
        self.assertEqual(cleanup, ["first", "second"])
        self.assertEqual(
            [event.kind for event in events],
            [ComponentEventKind.REMOVED, ComponentEventKind.REMOVED],
        )
        self.assertEqual(self.figure.canvas.draw_idle.call_count, 1)

    def test_delete_transaction_rejects_unknown_and_fixed_semantics(self):
        registry = register_figure_components(self.figure)
        title = registry.find_one(role=ComponentRole.TITLE)

        self.assertTrue(registry.delete_transaction(()).ok)
        self.assertFalse(
            registry.delete_transaction(("missing-component",)).ok
        )
        self.assertFalse(
            registry.delete_transaction((title.component_id,)).ok
        )
        self.assertIn(title.component_id, registry)

    def test_delete_transaction_keeps_requested_ancestor_and_emits_postorder(self):
        registry = register_figure_components(self.figure)
        axes = registry.find_one(kind=ComponentKind.AXES)
        title = registry.find_one(
            parent_id=axes.component_id,
            role=ComponentRole.TITLE,
        )
        events = []
        registry.subscribe(events.append)

        result = registry.delete_transaction(
            (title.component_id, axes.component_id, axes.component_id)
        )

        self.assertTrue(result.ok)
        self.assertNotIn(axes.component_id, registry)
        removed_ids = [
            event.component_id
            for event in events
            if event.kind is ComponentEventKind.REMOVED
        ]
        self.assertIn(title.component_id, removed_ids)
        self.assertEqual(removed_ids[-1], axes.component_id)
        deleted = [
            change
            for change in result.changes
            if change.status.value == "deleted"
        ]
        self.assertEqual(
            [change.component_id for change in deleted],
            [axes.component_id],
        )

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

    def test_chart_preprocessing_persists_filters_and_refreshes(self):
        pair = self.repository.line_pair(self.x_ref, self.y_ref)
        line, = self.axes.plot(pair.x, pair.y)
        plot = self._line_controller(
            "preprocessed-plot",
            ComponentRole.DATA_PLOT,
            line,
        )
        service = ChartDataService(self.repository, self.registry)

        result = service.set_refs(
            plot,
            self.x_ref,
            self.y_ref,
            DataPreprocessSpec("1/x", "y/x"),
        )

        self.assertTrue(result.ok)
        self.assertTrue(result.notices)
        self.assertEqual(
            plot.state.data["preprocess"],
            {"x_expression": "1/x", "y_expression": "y/x"},
        )
        np.testing.assert_allclose(
            np.asarray(line.get_xdata(), dtype=float)[1:],
            [1.0, 0.5],
        )
        np.testing.assert_allclose(
            np.asarray(line.get_ydata(), dtype=float)[1:],
            [2.0, 2.0],
        )
        self.assertTrue(np.isnan(float(line.get_xdata()[0])))

        self.sheet.set_block(1, 0, [[4.0, 8.0]])
        refreshed = service.refresh_affected({self.x_ref, self.y_ref})
        self.assertEqual(len(refreshed), 1)
        self.assertAlmostEqual(float(line.get_xdata()[1]), 0.25)
        self.assertAlmostEqual(float(line.get_ydata()[1]), 2.0)

    def test_fit_preprocessing_is_manual_and_invalidates_inflight_result(self):
        pair = self.repository.valid_pair(self.x_ref, self.y_ref)
        line, = self.axes.plot(pair.x, pair.y)
        fit = self._line_controller(
            "preprocessed-fit",
            ComponentRole.FIT_CURVE,
            line,
        )
        original_x = np.asarray(line.get_xdata()).copy()
        service = FitService(self.repository, self.registry)
        generation = service.next_request(fit.component_id)

        result = service.set_sources(
            fit,
            self.x_ref,
            self.y_ref,
            DataPreprocessSpec("1/x", "y"),
        )

        self.assertTrue(result.ok)
        self.assertTrue(result.notices)
        self.assertFalse(
            service.request_is_current(fit.component_id, generation)
        )
        self.assertTrue(service.has_pending_source_change(fit.component_id))
        np.testing.assert_array_equal(line.get_xdata(), original_x)
        resolved = service.resolve_sources(fit)
        np.testing.assert_allclose(resolved.x, [1.0, 0.5])
        np.testing.assert_allclose(resolved.y, [2.0, 4.0])

    def test_fit_source_change_marks_pending_until_explicit_result(self):
        pair = self.repository.valid_pair(self.x_ref, self.y_ref)
        line, = self.axes.plot(pair.x, pair.y)
        fit = self._line_controller(
            "pending-fit",
            ComponentRole.FIT_CURVE,
            line,
        )
        service = FitService(self.repository, self.registry)

        affected = service.mark_sources_changed({self.y_ref})

        self.assertEqual(affected, (fit.component_id,))
        self.assertTrue(service.has_pending_source_change(fit.component_id))
        result = service.apply_result(
            fit,
            engine="Python",
            fit_type=None,
            fit_options=None,
            fit_result=None,
            expression="x",
            x_start=0.0,
            x_stop=2.0,
        )
        self.assertTrue(result.ok)
        self.assertFalse(service.has_pending_source_change(fit.component_id))

    def test_scatter_preprocessing_filters_nonfinite_rows(self):
        pair = self.repository.valid_pair(self.x_ref, self.y_ref)
        artist = self.axes.scatter(pair.x, pair.y)
        scatter = ScatterController(
            ComponentState(
                id="preprocessed-scatter",
                kind=ComponentKind.SCATTER,
                role=ComponentRole.SCATTER,
                selector={"object_id": "preprocessed-scatter"},
                data={
                    "x_ref": self.x_ref.to_dict(),
                    "y_ref": self.y_ref.to_dict(),
                    "preprocess": DataPreprocessSpec().to_dict(),
                },
            )
        )
        self.registry.register(
            scatter,
            target=artist,
            require_parent=False,
        )
        service = ChartDataService(self.repository, self.registry)

        result = service.set_refs(
            scatter,
            self.x_ref,
            self.y_ref,
            DataPreprocessSpec("1/x", "y"),
        )

        self.assertTrue(result.ok)
        self.assertTrue(result.notices)
        np.testing.assert_allclose(
            np.asarray(artist.get_offsets(), dtype=float),
            [[1.0, 2.0], [0.5, 4.0]],
        )

    def test_interpolation_runs_after_preprocessing_and_refreshes(self):
        method = tuple(interpolate_dict)[2]
        line, = self.axes.plot([], [])
        interpolation = InterpolationController(
            ComponentState(
                id="preprocessed-interpolation",
                kind=ComponentKind.LINE,
                role=ComponentRole.INTERPOLATION,
                selector={"object_id": "preprocessed-interpolation"},
                data={
                    "x_ref": self.x_ref.to_dict(),
                    "y_ref": self.y_ref.to_dict(),
                    "preprocess": DataPreprocessSpec().to_dict(),
                    "method": method,
                    "k": 3,
                    "samples": 25,
                    "lam": None,
                    "lam_auto": True,
                },
            )
        )
        self.registry.register(
            interpolation,
            target=line,
            require_parent=False,
        )
        service = InterpolationService(self.repository, self.registry)

        result = service.configure(
            interpolation,
            x_ref=self.x_ref,
            y_ref=self.y_ref,
            preprocess=DataPreprocessSpec("x+1", "2*y"),
            method=method,
            k=3,
            samples=25,
            lam=None,
            lam_auto=True,
        )

        self.assertTrue(result.ok)
        self.assertEqual(
            interpolation.state.data["preprocess"],
            {"x_expression": "x+1", "y_expression": "2*y"},
        )
        self.assertAlmostEqual(float(line.get_xdata()[0]), 1.0)
        self.assertAlmostEqual(float(line.get_xdata()[-1]), 3.0)
        self.assertAlmostEqual(float(line.get_ydata()[0]), 2.0)
        self.assertAlmostEqual(float(line.get_ydata()[-1]), 8.0)

        self.sheet.set_block(2, 1, [[10.0]])
        refreshed = service.refresh(interpolation)
        self.assertTrue(refreshed.ok)
        self.assertAlmostEqual(float(line.get_ydata()[-1]), 20.0)

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

    def test_dependency_restore_failure_removes_components_restored_so_far(self):
        pair = self.repository.line_pair(self.x_ref, self.y_ref)
        first_line, = self.axes.plot(pair.x, pair.y)
        second_line, = self.axes.plot(pair.x, pair.y)
        self._line_controller("first", ComponentRole.DATA_PLOT, first_line)
        self._line_controller("second", ComponentRole.DATA_PLOT, second_line)
        calls = []

        def restore(state):
            calls.append(state.id)
            if state.id == "second":
                raise RuntimeError("injected second restore failure")
            line, = self.axes.plot(pair.x, pair.y)
            return self._line_controller(state.id, state.role, line)

        service = ComponentDependencyService(
            self.registry,
            restore_state=restore,
        )
        snapshots = service.dependent_states({self.x_ref})
        service.delete_states(snapshots)

        with self.assertRaisesRegex(RuntimeError, "second restore failure"):
            service.restore_states(snapshots)

        self.assertEqual(calls, ["first", "second"])
        self.assertNotIn("first", self.registry)
        self.assertNotIn("second", self.registry)


if __name__ == "__main__":
    unittest.main()
