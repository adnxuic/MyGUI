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
    DeleteReason,
    DeletionRequest,
    FitService,
    InterpolationService,
)
from mygui.figuremodify.components import (
    ChangeStatus,
    ComponentChange,
    ComponentEventKind,
    ComponentKind,
    ComponentMutation,
    ComponentNotFoundError,
    ComponentRegistry,
    ComponentRegistrationError,
    ComponentRole,
    ComponentState,
    ComponentValidationError,
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
    UpdateImpact,
    create_controller,
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

    def test_registration_post_restore_rollback_runs_after_watched_targets(self):
        line, = self.axes.plot([0, 1], [1, 2])
        controller = self._line_controller(
            "post-restore-order",
            ComponentRole.DATA_PLOT,
            line,
        )
        order = []
        restore = controller._restore_transaction_snapshot

        def record_restore(snapshot):
            order.append("restore")
            restore(snapshot)

        with patch.object(
            controller,
            "_restore_transaction_snapshot",
            side_effect=record_restore,
        ):
            with self.assertRaisesRegex(ValueError, "injected failure"):
                with self.registry.registration_transaction() as transaction:
                    transaction.watch_existing(controller.component_id)
                    transaction.on_rollback(lambda: order.append("before"))
                    transaction.on_rollback_after_restore(
                        lambda: order.append("after")
                    )
                    raise ValueError("injected failure")

        self.assertEqual(order, ["before", "restore", "after"])

    def test_registry_observer_failure_is_structured_and_non_blocking(self):
        line, = self.axes.plot([0, 1], [1, 2], color="#010101")
        controller = self._line_controller(
            "observer-line",
            ComponentRole.DATA_PLOT,
            line,
        )
        failures = []
        self.registry.set_observer_failure_handler(failures.extend)

        def broken_observer(_event):
            raise RuntimeError("injected observer failure")

        self.registry.subscribe(broken_observer)
        change = controller.set_property("color", "#112233")

        self.assertTrue(change.ok)
        self.assertEqual(len(failures), 1)
        self.assertEqual(failures[0].component_id, controller.component_id)
        self.assertEqual(failures[0].phase, "lifecycle")
        self.assertTrue(failures[0].source.endswith("broken_observer"))
        self.assertIsInstance(failures[0].error, RuntimeError)

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

    def test_delete_transaction_reports_prepare_cycle_and_replacement_errors(self):
        first_line, = self.axes.plot([0, 1], [1, 2])
        second_line, = self.axes.plot([0, 1], [2, 3])
        leaf_line, = self.axes.plot([0, 1], [3, 4])
        first = self._line_controller(
            "cycle-a",
            ComponentRole.DATA_PLOT,
            first_line,
        )
        second = self._line_controller(
            "cycle-b",
            ComponentRole.DATA_PLOT,
            second_line,
        )
        leaf = self._line_controller(
            "cycle-leaf",
            ComponentRole.DATA_PLOT,
            leaf_line,
        )
        first._state = first.state.clone(parent_id=second.component_id)
        second._state = second.state.clone(parent_id=first.component_id)
        leaf._state = leaf.state.clone(parent_id=first.component_id)
        result = self.registry.delete_transaction((leaf.component_id,))
        self.assertFalse(result.ok)
        self.assertIn("cycle", result.message.casefold())

        line, = self.axes.plot([0, 1], [4, 5])
        controller = self._line_controller(
            "collect-cycle",
            ComponentRole.DATA_PLOT,
            line,
        )
        self.registry._children[controller.component_id].add(controller.component_id)
        result = self.registry.delete_transaction((controller.component_id,))
        self.assertFalse(result.ok)
        self.registry._children[controller.component_id].discard(
            controller.component_id
        )

        result = self.registry.delete_transaction(
            (),
            state_replacements=("not-a-state",),
        )
        self.assertFalse(result.ok)
        self.assertIn("ComponentState", result.message)

        survivor = self._line_controller(
            "survivor",
            ComponentRole.DATA_PLOT,
            self.axes.plot([0, 1], [5, 6])[0],
        )
        result = self.registry.delete_transaction(
            (),
            state_replacements=(survivor.state, survivor.state.clone()),
        )
        self.assertFalse(result.ok)
        self.assertIn("Duplicate", result.message)

        doomed = self._line_controller(
            "doomed",
            ComponentRole.DATA_PLOT,
            self.axes.plot([0, 1], [6, 7])[0],
        )
        result = self.registry.delete_transaction(
            (doomed.component_id,),
            state_replacements=(doomed.state.clone(),),
        )
        self.assertFalse(result.ok)
        self.assertIn("replace removed", result.message.casefold())

    def test_delete_transaction_force_restores_artist_state_and_locator(self):
        from mygui.figuremodify.components.matplotlib_removal import (
            MATPLOTLIB_REMOVAL,
        )

        line, = self.axes.plot([0, 1], [1, 2])
        controller = self._line_controller(
            "force-restore",
            ComponentRole.DATA_PLOT,
            line,
        )
        self.registry.locator.bind(controller.component_id, line)

        def fail_rollback(_handle):
            raise RuntimeError("synthetic artist rollback failure")

        with patch.object(controller, "rollback_remove", fail_rollback):
            with patch.object(
                MATPLOTLIB_REMOVAL,
                "force_restore",
                side_effect=RuntimeError("synthetic force restore failure"),
            ):
                result = self.registry.delete_transaction(
                    (controller.component_id,),
                    verifier=lambda: (_ for _ in ()).throw(
                        RuntimeError("synthetic verifier failure")
                    ),
                )
        self.assertFalse(result.ok)
        self.assertFalse(result.rollback_complete)
        self.assertIn("forced artist restoration failed", result.message)

        line, = self.axes.plot([0, 1], [2, 3])
        controller = self._line_controller(
            "force-state",
            ComponentRole.DATA_PLOT,
            line,
        )

        def fail_state_restore(_snapshot):
            raise RuntimeError("synthetic state rollback failure")

        with patch.object(
            controller,
            "_restore_transaction_snapshot",
            fail_state_restore,
        ):
            with patch.object(
                type(controller),
                "_restore_transaction_snapshot",
                side_effect=RuntimeError("synthetic forced state failure"),
            ):
                result = self.registry.delete_transaction(
                    (),
                    state_replacements=(controller.state.clone(),),
                    verifier=lambda: (_ for _ in ()).throw(
                        RuntimeError("synthetic verifier failure")
                    ),
                )
        self.assertFalse(result.ok)
        self.assertIn("forced state restoration failed", result.message)

        line, = self.axes.plot([0, 1], [3, 4])
        controller = self._line_controller(
            "force-locator",
            ComponentRole.DATA_PLOT,
            line,
        )
        self.registry.locator.bind(controller.component_id, line)
        original_unbind = self.registry.locator.unbind

        def unbind_then_fail(component_id):
            original_unbind(component_id)
            raise RuntimeError("synthetic unbind failure")

        with patch.object(self.registry.locator, "unbind", unbind_then_fail):
            with patch.object(
                self.registry.locator,
                "bind",
                side_effect=RuntimeError("synthetic bind failure"),
            ):
                result = self.registry.delete_transaction(
                    (controller.component_id,),
                )
        self.assertFalse(result.ok)
        self.assertIn("Locator rollback failed", result.message)
        self.assertIs(self.registry.get(controller.component_id), controller)

    def test_delete_transaction_observer_failure_does_not_block_commit(self):
        line, = self.axes.plot([0, 1], [1, 2])
        controller = self._line_controller(
            "observer-delete",
            ComponentRole.DATA_PLOT,
            line,
        )
        failures = []
        self.registry.set_observer_failure_handler(failures.extend)

        def broken_observer(_event):
            raise RuntimeError("injected delete observer failure")

        self.registry.subscribe(broken_observer)
        result = self.registry.delete_transaction((controller.component_id,))
        self.assertTrue(result.ok)
        self.assertNotIn(controller.component_id, self.registry)
        self.assertEqual(len(failures), 1)
        self.assertIn("broken_observer", failures[0].source)

    def test_delete_transaction_replacement_apply_failure_rolls_back(self):
        line, = self.axes.plot([0, 1], [1, 2])
        controller = self._line_controller(
            "replace-fail",
            ComponentRole.DATA_PLOT,
            line,
        )
        replacement = controller.state.clone(
            properties={**controller.state.properties, "color": "#ff0000"}
        )
        with patch.object(
            controller,
            "apply_state",
            side_effect=RuntimeError("synthetic replacement failure"),
        ):
            result = self.registry.delete_transaction(
                (),
                state_replacements=(replacement,),
            )
        self.assertFalse(result.ok)
        self.assertIs(self.registry.get(controller.component_id), controller)

    def test_delete_transaction_rejected_replacement_shared_child_and_finalize(self):
        line, = self.axes.plot([0, 1], [1, 2])
        controller = self._line_controller(
            "replace-rejected",
            ComponentRole.DATA_PLOT,
            line,
        )
        replacement = controller.state.clone(
            properties={**controller.state.properties, "color": "#00ff00"}
        )

        def reject_state(_state):
            return ComponentChange(
                controller.component_id,
                None,
                controller.state,
                replacement,
                ChangeStatus.REJECTED,
                message="replacement rejected",
            )

        with patch.object(controller, "apply_state", reject_state):
            result = self.registry.delete_transaction(
                (),
                state_replacements=(replacement,),
            )
        self.assertFalse(result.ok)
        self.assertIn("replacement rejected", result.message)

        first_line, = self.axes.plot([0, 1], [2, 3])
        second_line, = self.axes.plot([0, 1], [3, 4])
        shared_line, = self.axes.plot([0, 1], [4, 5])
        first = self._line_controller("share-a", ComponentRole.DATA_PLOT, first_line)
        second = self._line_controller("share-b", ComponentRole.DATA_PLOT, second_line)
        shared = self._line_controller("share-child", ComponentRole.DATA_PLOT, shared_line)
        self.registry._children[first.component_id].add(shared.component_id)
        self.registry._children[second.component_id].add(shared.component_id)
        shared._state = shared.state.clone(parent_id=first.component_id)
        result = self.registry.delete_transaction(
            (first.component_id, second.component_id)
        )
        self.assertTrue(result.ok)
        self.assertNotIn(shared.component_id, self.registry)

        line, = self.axes.plot([0, 1], [5, 6])
        controller = self._line_controller(
            "finalize-warning",
            ComponentRole.DATA_PLOT,
            line,
        )
        with patch.object(
            controller,
            "_finalize_remove",
            side_effect=RuntimeError("synthetic finalize failure"),
        ):
            result = self.registry.delete_transaction((controller.component_id,))
        self.assertTrue(result.ok)
        self.assertTrue(
            any("Matplotlib cleanup" in notice.message for notice in result.notices)
        )

        production = register_figure_components(self.figure)
        axes_controller = next(
            item
            for item in production
            if item.state.kind is ComponentKind.AXES
        )
        extra, = self.axes.plot([0, 1], [6, 7])
        extra_controller = DataPlotController(
            ComponentState(
                id="axes-replace-line",
                kind=ComponentKind.LINE,
                role=ComponentRole.DATA_PLOT,
                parent_id=axes_controller.component_id,
                order=len(production),
                selector={"object_id": "axes-replace-line"},
                properties={"label": "axes-replace-line"},
                data={
                    "x_ref": self.x_ref.to_dict(),
                    "y_ref": self.y_ref.to_dict(),
                    "preprocess": DataPreprocessSpec().to_dict(),
                },
            )
        )
        production.register(extra_controller, target=extra)
        result = production.delete_transaction(
            (extra_controller.component_id,),
            state_replacements=(axes_controller.state.clone(),),
        )
        self.assertTrue(result.ok)

    def test_cleanup_and_listener_unsubscribe_are_idempotent(self):
        line, = self.axes.plot([0, 1], [1, 2])
        controller = self._line_controller(
            "cleanup",
            ComponentRole.DATA_PLOT,
            line,
        )
        with self.assertRaises(TypeError):
            self.registry.add_cleanup_callback(controller.component_id, "nope")
        with self.assertRaises(TypeError):
            self.registry.add_remove_listener("nope")
        with self.assertRaises(TypeError):
            self.registry.subscribe("nope")
        try:
            with self.registry.registration_transaction() as transaction:
                with self.assertRaises(TypeError):
                    transaction.on_rollback("nope")
                with self.assertRaises(TypeError):
                    transaction.on_rollback_after_restore("nope")
                raise RuntimeError("abort registration without a Figure root")
        except RuntimeError:
            pass
        unsubscribe = self.registry.add_cleanup_callback(
            controller.component_id,
            lambda _state: None,
        )
        unsubscribe()
        unsubscribe()
        listener = self.registry.add_remove_listener(lambda _state: None)
        listener()
        listener()
        subscriber = self.registry.subscribe(lambda _event: None)
        subscriber()
        subscriber()

    def test_observer_without_handler_logs_and_restore_rejection_rolls_back(self):
        line, = self.axes.plot([0, 1], [1, 2])
        controller = self._line_controller(
            "observer-log",
            ComponentRole.DATA_PLOT,
            line,
        )

        def broken_observer(_event):
            raise RuntimeError("injected observer without handler")

        self.registry.subscribe(broken_observer)
        result = self.registry.delete_transaction((controller.component_id,))
        self.assertTrue(result.ok)

        line2, = self.axes.plot([0, 1], [2, 3])
        surviving = self._line_controller(
            "restore-rollback",
            ComponentRole.DATA_PLOT,
            line2,
        )
        original = surviving.snapshot()
        rejected = ComponentChange(
            surviving.component_id,
            None,
            original,
            original,
            ChangeStatus.REJECTED,
            message="synthetic restore rejection",
        )
        restored = ComponentChange(
            surviving.component_id,
            None,
            original,
            original,
            ChangeStatus.APPLIED,
        )
        with patch.object(
            surviving,
            "restore",
            side_effect=[rejected, restored],
        ):
            changes = self.registry.restore({surviving.component_id: original})
        self.assertEqual(changes[0].status, ChangeStatus.REJECTED)
        with self.assertRaises(ComponentNotFoundError):
            self.registry.find_one(kind=ComponentKind.LEGEND)
        line3, = self.axes.plot([0, 1], [3, 4])
        self._line_controller(
            "second-line",
            ComponentRole.DATA_PLOT,
            line3,
        )
        with self.assertRaises(ComponentValidationError):
            self.registry.find_one(kind=ComponentKind.LINE)

    def test_observer_failure_handler_exception_is_logged(self):
        line, = self.axes.plot([0, 1], [1, 2])
        controller = self._line_controller(
            "observer-handler-boom",
            ComponentRole.DATA_PLOT,
            line,
        )

        def broken_observer(_event):
            raise RuntimeError("injected observer")

        def boom(_failures):
            raise RuntimeError("handler boom")

        self.registry.subscribe(broken_observer)
        self.registry.set_observer_failure_handler(boom)
        result = self.registry.delete_transaction((controller.component_id,))
        self.assertTrue(result.ok)

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

    def test_legend_rebuild_commits_and_render_failure_restores_identity(self):
        registry = register_figure_components(self.figure)
        axes_controller = registry.find_one(kind=ComponentKind.AXES)
        self.axes.plot([0, 1], [1, 2], label="series")
        service = AxesCommandService(registry)
        legend_controller, original = service.ensure_legend(
            axes_controller.component_id
        )

        changed = service.apply_legend_properties(
            legend_controller,
            {
                "location": {
                    "kind": "preset",
                    "value": "upper left",
                },
                "ncols": 2,
            },
        )

        self.assertTrue(changed.ok)
        rebuilt = self.axes.get_legend()
        self.assertIsNot(rebuilt, original)
        self.assertIs(
            registry.locator.bound_target(legend_controller.component_id),
            rebuilt,
        )
        before_state = legend_controller.state

        with patch.object(
            self.figure.canvas,
            "draw",
            side_effect=RuntimeError("synthetic legend render failure"),
        ):
            rejected = service.apply_legend_properties(
                legend_controller,
                {
                    "location": {
                        "kind": "preset",
                        "value": "lower right",
                    }
                },
            )

        self.assertFalse(rejected.ok)
        self.assertIs(self.axes.get_legend(), rebuilt)
        self.assertIs(
            registry.locator.bound_target(legend_controller.component_id),
            rebuilt,
        )
        self.assertEqual(legend_controller.state, before_state)

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
        service.deletion_service.delete(
            DeletionRequest(
                tuple(state.id for state in snapshots),
                reason=DeleteReason.DATA_DEPENDENCY,
            )
        )
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
        service.deletion_service.delete(
            DeletionRequest(
                tuple(state.id for state in snapshots),
                reason=DeleteReason.DATA_DEPENDENCY,
            )
        )

        with self.assertRaisesRegex(RuntimeError, "second restore failure"):
            service.restore_states(snapshots)

        self.assertEqual(calls, ["first", "second"])
        self.assertNotIn("first", self.registry)
        self.assertNotIn("second", self.registry)

    def test_interpolation_service_insufficient_points_and_all_methods(self):
        self.sheet.set_block(0, 0, [[0.0, 1.0], [1.0, 2.0], [2.0, 4.0], [3.0, 8.0], [4.0, 16.0], [5.0, 32.0]])
        pair = self.repository.line_pair(self.x_ref, self.y_ref)
        line, = self.axes.plot(pair.x, pair.y)
        initial_method = "线性插值"
        interpolation = InterpolationController(
            ComponentState(
                id="interp_methods",
                kind=ComponentKind.LINE,
                role=ComponentRole.INTERPOLATION,
                order=0,
                selector={"object_id": "interp_methods"},
                properties={"label": "interp"},
                data={
                    "x_ref": self.x_ref.to_dict(),
                    "y_ref": self.y_ref.to_dict(),
                    "preprocess": DataPreprocessSpec().to_dict(),
                    "method": initial_method,
                    "k": 3,
                    "samples": 50,
                    "lam": None,
                    "lam_auto": True,
                },
            )
        )
        self.registry.register(interpolation, target=line, require_parent=False)
        service = InterpolationService(self.repository, self.registry)

        # Test method families from interpolate_dict
        for method in ("线性插值", "三次样条插值", "PCHIP保形插值", "Akima插值", "平滑样条"):
            result = service.configure(
                interpolation,
                x_ref=self.x_ref,
                y_ref=self.y_ref,
                preprocess=DataPreprocessSpec(),
                method=method,
                k=3,
                samples=30,
                lam=None,
                lam_auto=True,
            )
            self.assertTrue(result.ok)



    def test_function_curve_service_evaluation_and_domain_errors(self):
        line, = self.axes.plot([0.0, 1.0], [0.0, 1.0])
        from mygui.figuremodify.components import FunctionCurveController
        from mygui.figuremodify.component_services import FunctionCurveService

        controller = FunctionCurveController(
            ComponentState(
                id="func_curve",
                kind=ComponentKind.LINE,
                role=ComponentRole.FUNCTION_CURVE,
                order=0,
                selector={"object_id": "func_curve"},
                properties={"label": "func"},
                data={
                    "expression": "sin(x)",
                    "x_start": 0.0,
                    "x_stop": 10.0,
                },
            )
        )
        self.registry.register(controller, target=line, require_parent=False)
        service = FunctionCurveService(self.registry)

        # Valid update
        valid_change = service.update(controller, "2 * x + 1", 0.0, 5.0, samples=50)
        self.assertTrue(valid_change.ok)
        self.assertEqual(controller.state.data["expression"], "2 * x + 1")

        # Invalid syntax expression rejection
        bad_syntax_change = service.update(controller, "sin(x +", 0.0, 5.0)
        self.assertFalse(bad_syntax_change.ok)

        # Non-finite range rejection
        bad_range_change = service.update(controller, "x", float("nan"), 5.0)
        self.assertFalse(bad_range_change.ok)

    def test_colorbar_service_source_and_dependents_queries(self):
        from mygui.figuremodify.component_services import ColorbarService
        service = ColorbarService(self.registry)

        self.assertFalse(service.has_dependents("non_existent_source"))
        self.assertEqual(service.dependents("non_existent_source"), ())
        self.assertEqual(service.eligible_sources("non_existent_axes"), ())


class RegistryFaultInjectionTests(unittest.TestCase):
    def _tree(self, *, include_artists=True):
        figure = Figure()
        axes = figure.subplots()
        if include_artists:
            axes.plot([0.0, 1.0], [1.0, 2.0])
        registry = register_figure_components(
            figure,
            id_factory=lambda path: path,
            include_artists=include_artists,
        )
        return figure, axes, registry

    def _replace_state(self, registry, component_id, **changes):
        controller = registry.get(component_id)
        controller._state = controller.state.clone(**changes)
        return controller

    def _reparent(self, registry, component_id, new_parent_id):
        controller = registry.get(component_id)
        old_parent = controller.state.parent_id
        registry._children[old_parent].discard(component_id)
        registry._children[new_parent_id].add(component_id)
        controller._state = controller.state.clone(parent_id=new_parent_id)
        return controller

    def test_query_snapshot_ancestor_and_empty_transaction_helpers(self):
        figure, axes, registry = self._tree()
        axes_id = "figure/axes/0"
        line_id = "figure/axes/0/line/0"
        self.assertGreater(len(registry), 0)
        self.assertIn("figure", registry)
        self.assertTrue(any(item.component_id == "figure" for item in registry))
        self.assertTrue(registry.states())
        self.assertEqual(
            registry.find_one(
                kind=ComponentKind.AXES,
                selector={"index": 0},
            ).component_id,
            axes_id,
        )
        self.assertEqual(
            registry.query(kind="line", capabilities="color")[0].component_id,
            line_id,
        )
        self.assertEqual(
            registry.query(
                parent_id="figure",
                recursive=True,
                kind=ComponentKind.LINE,
            )[0].component_id,
            line_id,
        )
        self.assertEqual(
            registry.ancestor(line_id, kind="axes").component_id,
            axes_id,
        )
        self.assertEqual(
            registry.ancestor(
                line_id,
                kind=ComponentKind.LINE,
                include_self=True,
            ).component_id,
            line_id,
        )
        self.assertIsNone(
            registry.ancestor("figure", kind=ComponentKind.AXES)
        )
        self.assertTrue(registry.apply_transaction(()).ok)
        self.assertIn(line_id, registry.snapshot([line_id]))
        changes = registry.set_properties([(line_id, "color", "#abcdef")])
        self.assertTrue(changes[0].ok)
        registry.request_update(None, UpdateImpact.REDRAW)
        registry.request_update(axes, UpdateImpact.NONE)
        registry.request_update(axes, UpdateImpact.REDRAW)
        registry.request_update(axes, UpdateImpact.RELIM | UpdateImpact.AUTOSCALE)
        registry._forget_subtree("missing-component")
        registry._children[axes_id].add("stale-child")
        child_ids = [item.component_id for item in registry.children(axes_id)]
        self.assertNotIn("stale-child", child_ids)
        with self.assertRaises(ComponentNotFoundError):
            registry.descendants("missing-component")
        with self.assertRaises(ComponentNotFoundError):
            registry.get("missing-component")
        self.assertIsNone(registry.resolve_target("missing-component"))
        line = registry.get(line_id)
        line._deleted = True
        self.assertIsNone(registry.resolve_target(line_id))
        with self.assertRaises(TypeError):
            registry.set_observer_failure_handler("nope")
        with self.assertRaises(TypeError):
            registry.subscribe_batches("nope")

    def test_event_filters_clear_and_registration_invariants(self):
        figure, axes, registry = self._tree()
        line_id = "figure/axes/0/line/0"
        filtered = []
        skipped_batches = []

        def boom_cleanup(_state):
            raise RuntimeError("cleanup boom")

        class AnonymousObserver:
            def __call__(self, _event):
                raise RuntimeError("anonymous observer")

        registry.subscribe(filtered.append, kinds=[ComponentEventKind.REMOVED])
        registry.subscribe(AnonymousObserver())
        registry.subscribe_batches(
            skipped_batches.append,
            kinds=[ComponentEventKind.REMOVED],
        )

        def boom_batch(_events):
            raise RuntimeError("batch boom")

        unsubscribe_batch = registry.subscribe_batches(boom_batch)
        result = registry.apply_transaction(
            (
                ComponentMutation(
                    line_id,
                    properties={"color": "#112233"},
                ),
            ),
            verifier=lambda: (_ for _ in ()).throw(RuntimeError("verifier")),
        )
        self.assertFalse(result.ok)
        self.assertEqual(filtered, [])
        self.assertEqual(skipped_batches, [])
        unsubscribe_batch()
        unsubscribe_batch()
        registry.add_cleanup_callback(line_id, boom_cleanup)
        deleted = registry.delete_transaction((line_id,))
        self.assertTrue(deleted.ok)
        registry.clear()
        self.assertEqual(len(registry), 0)

    def test_register_rejects_duplicates_and_missing_parents(self):
        _figure, axes, registry = self._tree()
        line = registry.get("figure/axes/0/line/0")
        with self.assertRaises(ComponentValidationError):
            registry.register(line, target=line.resolve_target())
        orphan = create_controller(
            line.state.clone(
                id="orphan-line",
                parent_id="missing-parent",
                selector={"object_id": "orphan-line"},
            ),
            target=axes.lines[0],
        )
        with self.assertRaises(ComponentValidationError):
            registry.register(orphan, target=axes.lines[0])
        registry._registration_active = True
        registry._active_registration_transaction = None
        with self.assertRaisesRegex(RuntimeError, "inconsistent"):
            with registry.registration_transaction():
                pass
        registry._registration_active = False
        with self.assertRaisesRegex(RuntimeError, "abort after duplicate watch"):
            with registry.registration_transaction() as transaction:
                transaction.watch_existing(line.component_id)
                transaction.watch_existing(line.component_id)
                raise RuntimeError("abort after duplicate watch")

    def test_validate_tree_reports_structural_faults(self):
        _figure, _axes, registry = self._tree()
        figure = registry.get("figure")
        figure._state = figure.state.clone(selector={"scope": "project"})
        with self.assertRaisesRegex(ComponentValidationError, "scope='figure'"):
            registry.validate_tree()

        _figure, _axes, registry = self._tree()
        self._replace_state(
            registry,
            "figure/axes/0/line/0",
            parent_id="missing-parent",
        )
        with self.assertRaisesRegex(ComponentValidationError, "unknown parent"):
            registry.validate_tree()

        _figure, _axes, registry = self._tree()
        line_id = "figure/axes/0/line/0"
        registry._children["figure"].add(line_id)
        registry._children["figure/axes/0"].discard(line_id)
        with self.assertRaisesRegex(ComponentValidationError, "out of sync"):
            registry.validate_tree()

        _figure, _axes, registry = self._tree()
        registry._children["figure"].add("ghost-node")
        with self.assertRaisesRegex(ComponentValidationError, "unknown component"):
            registry.validate_tree()

        _figure, _axes, registry = self._tree()
        extra = registry.get("figure/axes/0/line/0")
        extra._state = extra.state.clone(
            id="disconnected-line",
            selector={"object_id": "disconnected-line"},
        )
        registry._controllers["disconnected-line"] = extra
        registry._controllers.pop("figure/axes/0/line/0")
        registry._children["figure/axes/0"].discard("figure/axes/0/line/0")
        with self.assertRaisesRegex(ComponentValidationError, "disconnected"):
            registry.validate_tree()

        _figure, _axes, registry = self._tree()
        line = registry.get("figure/axes/0/line/0")
        line._state.selector["bad"] = {1, 2}
        with self.assertRaisesRegex(ComponentValidationError, "JSON-compatible"):
            registry.validate_tree()

        _figure, _axes, registry = self._tree()
        self._replace_state(
            registry,
            "figure/axes/0/line/0",
            kind=ComponentKind.FIGURE,
            role=ComponentRole.FIGURE,
        )
        with self.assertRaisesRegex(ComponentValidationError, "cannot have parent kind"):
            registry.validate_tree()

        _figure, _axes, registry = self._tree()
        self._reparent(
            registry,
            "figure/axes/0/title",
            "figure/axes/0/axis/x/grid/major",
        )
        with self.assertRaisesRegex(ComponentValidationError, "cannot have parent kind"):
            registry.validate_tree()

    def test_validate_tree_reports_selector_and_axes_semantic_faults(self):
        cases = (
            ("figure/axes/0", {"selector": {"index": True}}, "non-negative"),
            ("figure/axes/0/axis/x", {"selector": {"axis": "y"}}, "axis='x'"),
            (
                "figure/axes/0/spine/left",
                {"selector": {"name": "diagonal"}},
                "standard spine",
            ),
            (
                "figure/axes/0/axis/x/tick/major",
                {"selector": {"axis": "z", "level": "major"}},
                "axis=x|y",
            ),
            (
                "figure/axes/0/axis/x/tick/major",
                {"selector": {"axis": "y", "level": "major"}},
                "does not match its parent",
            ),
            (
                "figure/axes/0/axis/x/tick/major/label",
                {"selector": {"axis": "x", "level": "minor"}},
                "level does not match",
            ),
            (
                "figure/axes/0/axis/x/tick/major",
                {"role": ComponentRole.MINOR_TICK},
                "role does not match",
            ),
            (
                "figure/axes/0/axis/x/tick/major/label",
                {"role": ComponentRole.MINOR_TICK_LABEL},
                "role does not match",
            ),
            (
                "figure/axes/0/axis/x/label",
                {"selector": {"axis": "y"}},
                "axis='x'",
            ),
            (
                "figure/axes/0/line/0",
                {"selector": {"object_id": "other"}},
                "object_id equal to its component id",
            ),
            (
                "figure/axes/0/line/0",
                {
                    "kind": ComponentKind.SECONDARY_AXIS,
                    "role": ComponentRole.SECONDARY_X_AXIS,
                    "selector": {"object_id": "other"},
                },
                "only object_id",
            ),
            (
                "figure/axes/0/line/0",
                {
                    "kind": ComponentKind.REFERENCE_MARKS,
                    "role": ComponentRole.REFLECTION_POSITIONS,
                    "selector": {"object_id": "other"},
                },
                "only object_id",
            ),
            (
                "figure/axes/0/line/0",
                {
                    "kind": ComponentKind.REFERENCE_GUIDE,
                    "role": ComponentRole.REFERENCE_LINE,
                    "selector": {"object_id": "other"},
                },
                "only object_id",
            ),
            (
                "figure/axes/0/line/0",
                {
                    "kind": ComponentKind.ANNOTATION,
                    "role": ComponentRole.ANNOTATION,
                    "selector": {"object_id": "other"},
                },
                "only object_id",
            ),
            (
                "figure/axes/0/line/0",
                {
                    "kind": ComponentKind.IN_AXES,
                    "role": ComponentRole.IN_AXES_ZOOM,
                    "selector": {"object_id": "other"},
                },
                "object_id equal to its component id",
            ),
            (
                "figure/axes/0/title",
                {
                    "role": ComponentRole.TEXT,
                    "selector": {
                        "object_id": "figure/axes/0/title",
                        "scope": "figure",
                    },
                },
                "scope does not match",
            ),
        )
        for component_id, changes, pattern in cases:
            with self.subTest(component_id=component_id, pattern=pattern):
                _figure, _axes, registry = self._tree()
                self._replace_state(registry, component_id, **changes)
                with self.assertRaisesRegex(ComponentValidationError, pattern):
                    registry.validate_tree()

        missing = (
            ("figure/axes/0/title", "exactly one Title"),
            ("figure/axes/0/spine/left", "standard Spine"),
            ("figure/axes/0/axis/x", "exactly one x and one"),
            ("figure/axes/0/axis/x/label", "exactly one label"),
            ("figure/axes/0/axis/x/tick/major", "major and minor Tick"),
            ("figure/axes/0/axis/x/grid/major", "major and minor Grid"),
            (
                "figure/axes/0/axis/x/tick/major/label",
                "exactly one Tick Label",
            ),
        )
        for component_id, pattern in missing:
            with self.subTest(missing=component_id):
                _figure, _axes, registry = self._tree()
                registry._forget_subtree(component_id)
                with self.assertRaisesRegex(ComponentValidationError, pattern):
                    registry.validate_tree()

    def test_validate_axes_targets_and_ancestor_cycle(self):
        empty = ComponentRegistry()
        with self.assertRaisesRegex(ComponentValidationError, "exactly one Figure"):
            empty.validate_axes_targets()
        with self.assertRaisesRegex(ComponentValidationError, "exactly one Figure"):
            empty.validate_tree()

        figure, axes, registry = self._tree()
        figure_controller = registry.get("figure")
        with patch.object(
            figure_controller,
            "resolve_target",
            return_value=object(),
        ):
            with self.assertRaisesRegex(ComponentValidationError, "unavailable"):
                registry.validate_axes_targets()

        with patch.object(
            registry.get("figure/axes/0"),
            "resolve_target",
            return_value=None,
        ):
            with self.assertRaisesRegex(ComponentValidationError, "no Axes target"):
                registry.validate_axes_targets()

        two = Figure()
        left, right = two.subplots(1, 2)
        two_registry = register_figure_components(
            two,
            id_factory=lambda path: path,
            include_artists=False,
        )
        left_axes = two_registry.get("figure/axes/0")
        right_axes = two_registry.get("figure/axes/1")
        with patch.object(
            right_axes,
            "resolve_target",
            return_value=left_axes.resolve_target(),
        ):
            with self.assertRaisesRegex(ComponentValidationError, "same artist"):
                two_registry.validate_axes_targets()

        figure, axes, registry = self._tree()
        axes.remove()
        with self.assertRaisesRegex(ComponentValidationError, "detached"):
            registry.validate_axes_targets()

        figure, axes, registry = self._tree()
        line_id = "figure/axes/0/line/0"
        axes_id = "figure/axes/0"
        self._replace_state(registry, line_id, parent_id=axes_id)
        self._replace_state(registry, axes_id, parent_id=line_id)
        with self.assertRaisesRegex(ComponentValidationError, "ancestor cycle"):
            registry.ancestor(
                line_id,
                kind=ComponentKind.FIGURE,
                include_self=False,
            )

        self._replace_state(registry, line_id, parent_id="ghost-parent")
        self.assertIsNone(registry.ancestor(line_id, include_self=False))

    def test_delete_transaction_rebinds_locator_after_typeerror(self):
        figure, axes, registry = self._tree()
        line_id = "figure/axes/0/line/0"
        original_unbind = registry.locator.unbind

        def fail_unbind(component_id):
            original_unbind(component_id)
            raise RuntimeError("injected unbind failure")

        with patch.object(registry.locator, "unbind", side_effect=fail_unbind):
            with patch.object(
                registry.locator,
                "bind",
                side_effect=TypeError("injected bind type error"),
            ):
                result = registry.delete_transaction((line_id,))
        self.assertFalse(result.ok)
        self.assertIn(line_id, registry)
        self.assertIn("Locator rollback", result.message)

    def test_colorbar_and_secondary_axis_tree_checks(self):
        figure, axes, registry = self._tree()
        line = registry.get("figure/axes/0/line/0")
        colorbar_state = ComponentState(
            id="fake-colorbar",
            kind=ComponentKind.COLORBAR,
            role=ComponentRole.COLORBAR,
            parent_id="figure/axes/0",
            order=line.state.order + 10,
            selector={"object_id": "fake-colorbar"},
            data={"source_component_id": line.component_id},
        )
        registry.register(
            create_controller(colorbar_state, target=None),
            target=None,
            require_parent=True,
        )
        with self.assertRaisesRegex(ComponentValidationError, "Scatter or FIELD_2D"):
            registry.validate_tree()

        figure, axes, registry = self._tree()
        self._replace_state(
            registry,
            "figure/axes/0/line/0",
            kind=ComponentKind.COLORBAR,
            role=ComponentRole.COLORBAR,
            selector={"object_id": "other-colorbar"},
            data={"source_component_id": "missing-source"},
        )
        with self.assertRaisesRegex(ComponentValidationError, "object_id equal"):
            registry.validate_tree()

        figure = Figure()
        left, right = figure.subplots(1, 2)
        left.scatter([0.0], [1.0])
        registry = register_figure_components(
            figure,
            id_factory=lambda path: path,
            include_artists=True,
        )
        scatter = registry.query(kind=ComponentKind.SCATTER)[0]
        mismatch = ComponentState(
            id="cb-mismatch",
            kind=ComponentKind.COLORBAR,
            role=ComponentRole.COLORBAR,
            parent_id="figure/axes/1",
            order=scatter.state.order + 20,
            selector={"object_id": "cb-mismatch"},
            data={"source_component_id": scatter.component_id},
        )
        registry.register(
            create_controller(mismatch, target=None),
            target=None,
        )
        with self.assertRaisesRegex(ComponentValidationError, "same owner Axes"):
            registry.validate_tree()

        figure = Figure()
        axes = figure.subplots()
        axes.scatter([0.0], [1.0])
        registry = register_figure_components(
            figure,
            id_factory=lambda path: path,
            include_artists=True,
        )
        scatter = registry.query(kind=ComponentKind.SCATTER)[0]
        for suffix in ("a", "b"):
            state = ComponentState(
                id=f"cb-dup-{suffix}",
                kind=ComponentKind.COLORBAR,
                role=ComponentRole.COLORBAR,
                parent_id="figure/axes/0",
                order=scatter.state.order + 30 + ord(suffix),
                selector={"object_id": f"cb-dup-{suffix}"},
                data={"source_component_id": scatter.component_id},
            )
            registry.register(
                create_controller(state, target=None),
                target=None,
            )
        with self.assertRaisesRegex(ComponentValidationError, "more than one Colorbar"):
            registry.validate_tree()


if __name__ == "__main__":
    unittest.main()
