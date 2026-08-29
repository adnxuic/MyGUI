"""Isolated Error Bar component tests: domain, runtime, transactions, schema."""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from main import MainWindow
from tests.axes_helpers import create_regular_axes

import numpy as np
from matplotlib import colors as mcolors
from matplotlib.figure import Figure

from mygui.database import (
    ColumnRef,
    ColumnType,
    DataPreprocessSpec,
    TableRepository,
)
from mygui.figuremodify.component_services import (
    ErrorBarDataService,
    ErrorBarRuntime,
    resolve_errorbar_data,
)
from mygui.figuremodify.components import (
    ChangeStatus,
    ComponentChange,
    ComponentKind,
    ComponentRegistry,
    ComponentRole,
    ComponentState,
    ErrorBarController,
    ErrorBarData,
    ComponentValidationError,
)
from mygui.figuremodify.components.property_values import (
    DEFAULT_ERROR_SPEC,
    error_spec_references,
    normalize_error_spec,
)
from mygui.figuremodify.matplotlib_adapter import relim_with_errorbars


def _symmetric_ref(ref: ColumnRef) -> dict:
    return {"kind": "symmetric_ref", "ref": ref.to_dict()}


def _asymmetric_ref(minus: ColumnRef, plus: ColumnRef) -> dict:
    return {
        "kind": "asymmetric_ref",
        "minus_ref": minus.to_dict(),
        "plus_ref": plus.to_dict(),
    }


class ErrorSpecNormalizationTests(unittest.TestCase):
    """The closed ErrorSpec tagged contract rejects everything else."""

    def test_none_constant_and_reference_roundtrip(self):
        self.assertEqual(normalize_error_spec({"kind": "none"}), {"kind": "none"})
        constant = normalize_error_spec({"kind": "constant", "minus": 1, "plus": 2.5})
        self.assertEqual(constant, {"kind": "constant", "minus": 1.0, "plus": 2.5})
        ref = {"project_id": "p", "sheet_id": "s", "column_id": "c"}
        self.assertEqual(
            normalize_error_spec({"kind": "symmetric_ref", "ref": ref}),
            {"kind": "symmetric_ref", "ref": deepcopy(ref)},
        )
        self.assertEqual(
            normalize_error_spec(
                {"kind": "asymmetric_ref", "minus_ref": ref, "plus_ref": ref}
            ),
            {"kind": "asymmetric_ref", "minus_ref": deepcopy(ref), "plus_ref": deepcopy(ref)},
        )

    def test_rejects_unknown_kinds_keys_bool_negative_and_nonfinite(self):
        ref = {"project_id": "p", "sheet_id": "s", "column_id": "c"}
        invalid = [
            {"kind": "relative"},
            {"kind": "constant", "minus": 1.0},
            {"kind": "constant", "minus": 1.0, "plus": 2.0, "extra": 3},
            {"kind": "constant", "minus": True, "plus": 2.0},
            {"kind": "constant", "minus": -1.0, "plus": 2.0},
            {"kind": "symmetric_ref", "ref": dict(ref, column_id="")},
            {"kind": "symmetric_ref", "ref": 5},
            {"kind": "asymmetric_ref", "minus_ref": ref},
            "constant",
            None,
        ]
        for value in invalid:
            with self.subTest(value=value):
                with self.assertRaises(ComponentValidationError):
                    normalize_error_spec(value)
        with self.assertRaises(ComponentValidationError):
            normalize_error_spec({"kind": "constant", "minus": float("nan"), "plus": 1.0})

    def test_error_spec_references_extracts_every_column(self):
        ref = {"project_id": "p", "sheet_id": "s", "column_id": "c"}
        other = {"project_id": "p", "sheet_id": "s", "column_id": "d"}
        self.assertEqual(error_spec_references({"kind": "none"}), [])
        self.assertEqual(error_spec_references(self._symmetric_ref_from(ref)), [ref])
        self.assertEqual(
            error_spec_references(
                {"kind": "asymmetric_ref", "minus_ref": ref, "plus_ref": other}
            ),
            [ref, other],
        )

    @staticmethod
    def _symmetric_ref_from(ref):
        return {"kind": "symmetric_ref", "ref": ref}


class ErrorBarDataTestCase(unittest.TestCase):
    """Shared table fixture backing one aligned X/Y pair plus error columns."""

    ROWS = 5

    def setUp(self):
        self.repository = TableRepository()
        self.project = self.repository.create_project("ErrorBars")
        self.sheet = next(iter(self.project.sheets.values()))
        rows = [
            [float(i), float(10 + 2 * i), 0.5, 1.0]
            for i in range(self.ROWS)
        ]
        self.sheet.set_block(0, 0, rows)
        self.x_ref = ColumnRef(self.project.id, self.sheet.id, self.sheet.columns[0].id)
        self.y_ref = ColumnRef(self.project.id, self.sheet.id, self.sheet.columns[1].id)
        self.minus_ref = ColumnRef(self.project.id, self.sheet.id, self.sheet.columns[2].id)
        self.plus_ref = ColumnRef(self.project.id, self.sheet.id, self.sheet.columns[3].id)
        self.preprocess = DataPreprocessSpec()


class ResolveErrorBarDataTests(ErrorBarDataTestCase):
    def test_y_symmetric_and_x_asymmetric_constants_and_columns(self):
        y_constant = resolve_errorbar_data(
            self.repository,
            self.x_ref,
            self.y_ref,
            {"kind": "constant", "minus": 0.25, "plus": 0.75},
            {"kind": "constant", "minus": 1.0, "plus": 1.0},
            self.preprocess,
        )
        self.assertEqual(y_constant.xerr.shape, (2, self.ROWS))
        self.assertTrue(np.allclose(y_constant.xerr[0], 0.25))
        self.assertTrue(np.allclose(y_constant.xerr[1], 0.75))

        both = resolve_errorbar_data(
            self.repository,
            self.x_ref,
            self.y_ref,
            _asymmetric_ref(self.minus_ref, self.plus_ref),
            _symmetric_ref(self.minus_ref),
            self.preprocess,
        )
        self.assertTrue(np.allclose(both.xerr[0], 0.5))
        self.assertTrue(np.allclose(both.xerr[1], 1.0))
        self.assertTrue(np.allclose(both.yerr, 0.5))

    def test_no_errors_produces_none_dimensions(self):
        data = resolve_errorbar_data(
            self.repository,
            self.x_ref,
            self.y_ref,
            None,
            None,
            self.preprocess,
        )
        self.assertIsNone(data.xerr)
        self.assertIsNone(data.yerr)
        self.assertEqual(len(data.x), self.ROWS)

    def test_preprocessing_mask_aligns_error_rows(self):
        # Row 0 has no Y, so row 0 of every error column must be dropped
        # rather than validated - even with an invalid magnitude there.
        spec = DataPreprocessSpec(x_expression="x", y_expression="y")
        raw_y = self.sheet.frame[self.y_ref.column_id].tolist()
        raw_minus = self.sheet.frame[self.minus_ref.column_id].tolist()
        self.sheet.set_block(0, 1, [[None]])
        self.sheet.set_block(0, 2, [[-0.5]])
        try:
            data = resolve_errorbar_data(
                self.repository,
                self.x_ref,
                self.y_ref,
                _symmetric_ref(self.minus_ref),
                {"kind": "constant", "minus": 1.0, "plus": 2.0},
                spec,
            )
        finally:
            self.sheet.set_block(0, 1, [[raw_y[0]]])
            self.sheet.set_block(0, 2, [[raw_minus[0]]])
        self.assertEqual(len(data.x), self.ROWS - 1)
        self.assertEqual(data.xerr.shape, (self.ROWS - 1,))
        self.assertEqual(data.yerr.shape, (2, self.ROWS - 1))
        self.assertTrue(np.all(np.isfinite(data.y)))

    def test_negative_nan_and_inf_drawable_rows_reject_atomically(self):
        raw_minus = self.sheet.frame[self.minus_ref.column_id].tolist()
        for bad_value in (-0.5, None):
            with self.subTest(value=bad_value):
                if bad_value is None:
                    # Missing table cells become NaN in the numeric frame.
                    self.sheet.set_block(0, 2, [[None]])
                else:
                    self.sheet.set_block(0, 2, [[bad_value]])
                try:
                    with self.assertRaisesRegex(
                        ValueError, "non-negative|finite|numeric"
                    ):
                        resolve_errorbar_data(
                            self.repository,
                            self.x_ref,
                            self.y_ref,
                            _symmetric_ref(self.minus_ref),
                            None,
                            self.preprocess,
                        )
                finally:
                    self.sheet.set_block(0, 2, [[raw_minus[0]]])

    def test_non_numeric_or_removed_error_columns_reject(self):
        column = self.sheet.add_column(
            "Notes", ColumnType.TEXT, values=["a"] * self.ROWS
        )
        text_ref = ColumnRef(self.project.id, self.sheet.id, column.id)
        with self.assertRaisesRegex(ValueError, "must be numeric"):
            resolve_errorbar_data(
                self.repository,
                self.x_ref,
                self.y_ref,
                _symmetric_ref(text_ref),
                None,
                self.preprocess,
            )
        self.sheet.remove_column(self.minus_ref.column_id)
        with self.assertRaisesRegex(ValueError, "removed"):
            resolve_errorbar_data(
                self.repository,
                self.x_ref,
                self.y_ref,
                _symmetric_ref(self.minus_ref),
                None,
                self.preprocess,
            )

    def test_all_rows_masked_keeps_empty_component(self):
        self.sheet.set_block(0, 1, [[None]] * self.ROWS)
        data = resolve_errorbar_data(
            self.repository,
            self.x_ref,
            self.y_ref,
            _symmetric_ref(self.minus_ref),
            None,
            self.preprocess,
        )
        self.assertEqual(len(data.x), 0)
        self.assertIsNone(data.yerr)
        self.assertEqual(len(data.xerr), 0)


class ErrorBarRuntimeTests(ErrorBarDataTestCase):
    def _runtime(self, registry_target=None):
        data = resolve_errorbar_data(
            self.repository,
            self.x_ref,
            self.y_ref,
            _symmetric_ref(self.minus_ref),
            _symmetric_ref(self.minus_ref),
            self.preprocess,
        )
        figure = Figure()
        axes = figure.subplots()
        figure.canvas.draw_idle = lambda: None
        from mygui.figuremodify.component_services import (
            create_errorbar_container,
        )

        properties = ErrorBarController.default_properties()
        properties["color"] = "#123456"
        properties["ecolor"] = "#123456"
        container = create_errorbar_container(axes, data, properties)
        runtime = ErrorBarRuntime(axes, container, data=data, properties=properties)
        return figure, axes, runtime, data

    def test_zero_capsize_keeps_cap_artists_and_gid_reaches_every_artist(self):
        _figure, _axes, runtime, _data = self._runtime()
        self.assertEqual(runtime.data_line.get_gid(), None)
        runtime.set_gid("eb-runtime")
        for artist in runtime.iter_artists():
            self.assertEqual(artist.get_gid(), "eb-runtime")
        self.assertEqual(len(runtime.caplines), 4)
        self.assertTrue(all(cap.get_markersize() == 0.0 for cap in runtime.caplines))

    def test_rebuild_swaps_container_and_rollback_restores_identity(self):
        figure, axes, runtime, data = self._runtime()
        original_container = runtime.container
        original_line = runtime.data_line
        properties = deepcopy(runtime._properties)
        new_data = ErrorBarData(
            np.asarray(data.x) * 2,
            np.asarray(data.y),
            np.asarray(data.yerr),
            None,
        )
        new_properties = deepcopy(properties)
        new_properties["color"] = "#654321"
        memento = runtime.rebuild(data=new_data, properties=new_properties)
        self.assertIsNot(runtime.container, original_container)
        self.assertNotIn(original_container, axes.containers)
        self.assertNotIn(original_line, axes.lines)
        self.assertEqual(runtime.data_line.get_color(), "#654321")

        runtime.restore_swap(memento)
        self.assertIs(runtime.container, original_container)
        self.assertIs(runtime.data_line, original_line)
        self.assertIn(original_container, axes.containers)
        self.assertIn(original_line, axes.lines)
        # The rollback must also restore the superseded data and style values.
        self.assertTrue(np.allclose(np.asarray(runtime.data.x), np.asarray(data.x)))
        self.assertTrue(np.allclose(np.asarray(runtime.data.yerr), np.asarray(data.yerr)))
        self.assertTrue(np.allclose(np.asarray(runtime.data.xerr), 0.5))
        self.assertEqual(runtime.data_line.get_color(), "#123456")

    def test_removal_handle_commit_and_force_restore_keep_identity(self):
        from mygui.figuremodify.components.matplotlib_removal import (
            MATPLOTLIB_REMOVAL,
        )

        figure, axes, runtime, _data = self._runtime()
        container = runtime.container
        line = runtime.data_line
        containers_before = list(axes.containers)
        lines_before = list(axes.lines)
        handle = MATPLOTLIB_REMOVAL.prepare_errorbar(runtime)
        MATPLOTLIB_REMOVAL.commit(handle)
        self.assertNotIn(container, axes.containers)
        self.assertNotIn(line, axes.lines)
        MATPLOTLIB_REMOVAL.rollback(handle)
        self.assertIs(axes.containers[axes.containers.index(container)], container)
        self.assertEqual(list(axes.containers), containers_before)
        self.assertIn(line, axes.lines)
        self.assertEqual(
            [id(item) for item in axes.lines[: len(lines_before)]],
            [id(item) for item in lines_before],
        )

    def test_rebuild_failure_removes_candidate_and_keeps_previous(self):
        figure, axes, runtime, data = self._runtime()
        original_container = runtime.container
        broken_properties = deepcopy(runtime._properties)
        broken_properties["color"] = "not-a-color"
        with self.assertRaises(Exception):
            runtime.rebuild(
                data=ErrorBarData(np.asarray(data.x), np.asarray(data.y), None, None),
                properties=broken_properties,
            )
        self.assertIs(runtime.container, original_container)
        self.assertIn(original_container, axes.containers)


class ErrorBarControllerTests(ErrorBarDataTestCase):
    def setUp(self):
        super().setUp()
        self.figure = Figure()
        self.axes = self.figure.subplots()
        self.figure.canvas.draw_idle = mock.Mock()
        self.registry = ComponentRegistry()
        self.service = ErrorBarDataService(self.repository, self.registry)
        self.data = resolve_errorbar_data(
            self.repository,
            self.x_ref,
            self.y_ref,
            _symmetric_ref(self.minus_ref),
            None,
            self.preprocess,
        )
        self.state = ComponentState(
            id="eb-1",
            kind=ComponentKind.ERRORBAR,
            role=ComponentRole.ERROR_BAR,
            order=0,
            selector={"object_id": "eb-1"},
            properties=ErrorBarController.default_properties(),
            data={
                "x_ref": self.x_ref.to_dict(),
                "y_ref": self.y_ref.to_dict(),
                "xerr": _symmetric_ref(self.minus_ref),
                "yerr": dict(DEFAULT_ERROR_SPEC),
                "preprocess": self.preprocess.to_dict(),
            },
        )
        self.controller, self.runtime = self._register(self.state)

    def _register(self, state):
        from mygui.figuremodify.component_services import (
            create_errorbar_container,
        )

        drawable = resolve_errorbar_data(
            self.repository,
            state.data["x_ref"],
            state.data["y_ref"],
            state.data["xerr"],
            state.data["yerr"],
            state.data["preprocess"],
        )
        runtime = ErrorBarRuntime(
            self.axes,
            create_errorbar_container(
                self.axes,
                drawable,
                deepcopy(state.properties),
            ),
            data=drawable,
            properties=deepcopy(state.properties),
        )
        controller = ErrorBarController(state, target=runtime)
        self.registry.register(controller, target=runtime, require_parent=False)
        runtime.set_gid(state.id)
        return controller, runtime

    def test_style_property_roundtrip_targets_composite_artists(self):
        change = self.controller.set_property("color", "#ff8800")
        self.assertTrue(change.ok)
        self.assertEqual(self.runtime.data_line.get_color(), "#ff8800")
        synced = self.controller.sync_from_target()
        self.assertEqual(synced.properties["color"], "#ff8800")

        change = self.controller.set_property("ecolor", "#00ff00")
        self.assertTrue(change.ok)
        for collection in self.runtime.barlinecols:
            self.assertEqual(mcolors.to_hex(collection.get_color()), "#00ff00")
        for cap in self.runtime.caplines:
            self.assertEqual(mcolors.to_hex(cap.get_color()), "#00ff00")
        synced = self.controller.sync_from_target()
        self.assertEqual(synced.properties["ecolor"], "#00ff00")

        change = self.controller.set_property("capsize", 3.5)
        self.assertTrue(change.ok)
        self.assertAlmostEqual(self.runtime.caplines[0].get_markersize(), 7.0)

    def test_capsize_increase_does_not_rebuild_component_structure(self):
        artists_before = self.runtime.iter_artists()
        change = self.controller.set_property("capsize", 4.0)
        self.assertTrue(change.ok)
        self.assertEqual(self.runtime.iter_artists(), artists_before)

    def test_unknown_property_and_negative_width_reject_and_restore(self):
        before = self.controller.state
        change = self.controller.set_property("elinewidth", -1.0)
        self.assertFalse(change.ok)
        change = self.controller.set_property("does_not_exist", 1.0)
        self.assertFalse(change.ok)
        self.assertEqual(self.controller.state, before)
        self.assertEqual(
            self.runtime.barlinecols[0].get_linewidths()[0],
            before.properties["elinewidth"],
        )

    def test_service_configure_rebuilds_runtime_and_rejects_invalid_spec(self):
        change = self.service.configure(
            self.controller,
            x_ref=self.x_ref,
            y_ref=self.y_ref,
            xerr=_asymmetric_ref(self.minus_ref, self.plus_ref),
            yerr={"kind": "constant", "minus": 0.1, "plus": 0.2},
            preprocess=self.preprocess,
        )
        self.assertTrue(change.ok, change.message)
        self.assertEqual(len(self.runtime.barlinecols), 2)
        self.assertEqual(len(self.runtime.caplines), 4)
        persisted = self.controller.state.data
        self.assertEqual(persisted["xerr"]["kind"], "asymmetric_ref")
        self.assertEqual(persisted["yerr"]["kind"], "constant")

        rejected = self.service.configure(
            self.controller,
            x_ref=self.x_ref,
            y_ref=self.y_ref,
            xerr={"kind": "constant", "minus": -2.0, "plus": 1.0},
            yerr=dict(DEFAULT_ERROR_SPEC),
            preprocess=self.preprocess,
        )
        self.assertFalse(rejected.ok)
        self.assertEqual(self.controller.state.data["xerr"]["kind"], "asymmetric_ref")
        self.assertEqual(len(self.runtime.barlinecols), 2)

    def test_service_refresh_affected_tracks_error_columns_and_reports_failures(self):
        change = self.service.configure(
            self.controller,
            x_ref=self.x_ref,
            y_ref=self.y_ref,
            xerr=_asymmetric_ref(self.minus_ref, self.plus_ref),
            yerr=dict(DEFAULT_ERROR_SPEC),
            preprocess=self.preprocess,
        )
        self.assertTrue(change.ok, change.message)
        change = self.service.refresh_affected({self.plus_ref})
        self.assertEqual(len(change), 1)
        self.assertTrue(change[0].ok)

        self.sheet.set_block(0, 2, [[-0.5]])
        try:
            change = self.service.refresh_affected({self.minus_ref})
            self.assertEqual(len(change), 1)
            self.assertFalse(change[0].ok)
            failures = self.service.drain_observer_failures()
            self.assertEqual(failures, ())
        finally:
            self.sheet.set_block(0, 2, [[0.5]] * self.ROWS)

    def test_apply_state_replays_full_authoritative_state(self):
        change = self.service.configure(
            self.controller,
            x_ref=self.x_ref,
            y_ref=self.y_ref,
            xerr=dict(DEFAULT_ERROR_SPEC),
            yerr=_symmetric_ref(self.minus_ref),
            preprocess=self.preprocess,
        )
        self.assertTrue(change.ok)
        replay = self.service.apply_state(
            self.controller,
            self.controller.state.clone(
                properties=deepcopy(
                    dict(self.controller.state.properties, color="#010101")
                )
            ),
        )
        self.assertTrue(replay.ok, replay.message)
        self.assertEqual(self.controller.state.properties["color"], "#010101")


class RelimWithErrorbarsTests(ErrorBarDataTestCase):
    def _ymin_for_error_column(self, minus_values: list[float]) -> float:
        self.sheet.set_block(0, 2, [[value] for value in minus_values])
        figure = Figure()
        axes = figure.subplots()
        data = resolve_errorbar_data(
            self.repository,
            self.x_ref,
            self.y_ref,
            None,
            _symmetric_ref(self.minus_ref),
            self.preprocess,
        )
        from mygui.figuremodify.component_services import create_errorbar_container

        properties = ErrorBarController.default_properties()
        container = create_errorbar_container(axes, data, properties)
        ErrorBarRuntime(axes, container, data=data, properties=properties)
        relim_with_errorbars(axes)
        axes.autoscale_view()
        return float(axes.get_ylim()[0])

    def test_error_extent_grows_and_shrinks_limits(self):
        ymin_with_errors = self._ymin_for_error_column([0.5] * self.ROWS)
        ymin_without_errors = self._ymin_for_error_column([0.0] * self.ROWS)
        self.assertGreater(ymin_without_errors, ymin_with_errors)
        self.assertLess(ymin_with_errors, 10.0)

    def test_plain_relim_helper_ignores_non_errorbar_containers(self):
        figure = Figure()
        axes = figure.subplots()
        axes.plot([0.0, 1.0], [0.0, 1.0])
        relim_with_errorbars(axes)
        self.assertAlmostEqual(axes.dataLim.y0, 0.0)


if __name__ == "__main__":
    unittest.main()


class ErrorBarGuiTestCase(unittest.TestCase):
    """Full-window fixture for transaction, history, and IO coverage."""

    ROWS = 5

    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication

        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.window = MainWindow()
        self.window.figure_window.add_figure(
            width=4, height=3, dpi=100, style="default", canva_name="ErrorBars"
        )
        self.canvas = self.window.figure_window.current_canva
        self.repository = self.window.repository
        self.sheet = self._sheet()
        rows = [
            [float(i), float(10 + 2 * i), 0.5, 1.0]
            for i in range(self.ROWS)
        ]
        self.sheet.set_block(0, 0, rows)
        self.x_ref = ColumnRef(self.canvas.project_id, self.sheet.id, self.sheet.columns[0].id)
        self.y_ref = ColumnRef(self.canvas.project_id, self.sheet.id, self.sheet.columns[1].id)
        self.minus_ref = ColumnRef(self.canvas.project_id, self.sheet.id, self.sheet.columns[2].id)
        self.plus_ref = ColumnRef(self.canvas.project_id, self.sheet.id, self.sheet.columns[3].id)
        self._axes_ids = create_regular_axes(self.canvas)
        self.stack = self.repository.undo_stack(self.canvas.project_id)
        self.stack.clear()

    def tearDown(self):
        self.window.close_without_prompt()
        self.app.processEvents()

    def _sheet(self):
        return next(iter(self.repository.project(self.canvas.project_id).sheets.values()))

    def _add_errorbar(self, **overrides):
        kwargs = dict(
            xerr=_symmetric_ref(self.minus_ref),
            yerr=_symmetric_ref(self.plus_ref),
            preprocess=DataPreprocessSpec().to_dict(),
            color_selection=None,
        )
        kwargs.update(overrides)
        return self.canvas.add_errorbar(
            self.x_ref,
            self.y_ref,
            kwargs.pop("label", "errorbar"),
            **kwargs,
        )

    def _errorbar_controller(self):
        controllers = self.canvas.component_registry.query(
            kind=ComponentKind.ERRORBAR,
            role=ComponentRole.ERROR_BAR,
        )
        return controllers[0] if controllers else None

    def _controller(self):
        return self._errorbar_controller()

    def _record(self, text, operation):
        return self.canvas.figure_history.perform(text, operation)


class ErrorBarCanvasTransactionTests(ErrorBarGuiTestCase):
    def test_create_selects_registers_and_consumes_chart_order(self):
        runtime = self._add_errorbar()
        controller = self._errorbar_controller()
        self.assertIsNotNone(controller)
        self.assertIs(self.canvas.current_component_id, controller.component_id)
        self.assertIs(runtime.container[0].axes, self.canvas.current_axes)
        self.assertEqual(controller.state.order, 0)
        runtime2 = self._add_errorbar(label="second")
        controller2 = self.canvas.component_registry.get(
            runtime2.container[0].get_gid()
        )
        self.assertEqual(controller2.state.order, 1)
        artists = (*runtime.iter_artists(), *runtime2.iter_artists())
        self.assertTrue(all(artist.axes is not None for artist in artists))

    def test_creation_failure_leaves_no_residue(self):
        from mygui.widgets.figure_canvas import chart_creation

        axes = self.canvas.current_axes
        before_containers = len(axes.containers)
        before_lines = len(axes.lines)
        before_collections = len(axes.collections)
        with mock.patch.object(
            chart_creation.ChartCreationStager,
            "stage_errorbar",
            side_effect=RuntimeError("boom"),
        ):
            with self.assertRaisesRegex(RuntimeError, "boom"):
                self._add_errorbar()
        self.assertEqual(len(axes.containers), before_containers)
        self.assertEqual(len(axes.lines), before_lines)
        self.assertEqual(len(axes.collections), before_collections)
        self.assertIsNone(self._errorbar_controller())

    def test_palette_commit_failure_rolls_runtime_back(self):
        from mygui.figuremodify.component_services import AxesCommandService

        axes = self.canvas.current_axes
        before_containers = len(axes.containers)
        before_controllers = len(self.canvas.component_registry.query())
        with mock.patch.object(
            AxesCommandService,
            "commit_color_selection",
            side_effect=ValueError("palette refused"),
        ):
            with self.assertRaisesRegex(ValueError, "palette refused"):
                self._add_errorbar(color_selection=__import__(
                    "mygui.figuremodify.style_base.color_models", fromlist=["ColorSelection"]
                ).ColorSelection("#123456"))
        self.assertEqual(len(axes.containers), before_containers)
        self.assertEqual(len(self.canvas.component_registry.query()), before_controllers)
        self.assertIsNone(self._errorbar_controller())

    def test_undo_redo_creation_and_deletion(self):
        runtime = self._add_errorbar()
        controller = self._errorbar_controller()
        component_id = controller.component_id
        before = self.stack.count()
        self.canvas.delete_component_group((component_id,), role_label="Error Bar")
        self.app.processEvents()
        self.assertIsNone(self._errorbar_controller())
        self.assertNotIn(runtime.container, self.canvas.current_axes.containers)

        self.stack.undo()
        self.app.processEvents()
        restored = self._errorbar_controller()
        self.assertIsNotNone(restored)
        self.assertEqual(restored.component_id, component_id)

        self.stack.undo()
        self.app.processEvents()
        self.assertIsNone(self._errorbar_controller())

        self.stack.redo()
        self.app.processEvents()
        restored = self._errorbar_controller()
        self.assertIsNotNone(restored)
        self.assertEqual(restored.component_id, component_id)
        # Undo and redo replay the same delta without growing the stack.
        self.assertEqual(self.stack.count(), before + 1)

    def test_single_deletion_cleans_container_and_every_artist(self):
        runtime = self._add_errorbar()
        controller = self._errorbar_controller()
        axes = self.canvas.current_axes
        artists = set(map(id, runtime.iter_artists()))
        self.assertTrue(artists)
        self.canvas.delete_component_group(
            (controller.component_id,), role_label="Error Bar"
        )
        self.app.processEvents()
        self.assertNotIn(runtime.container, axes.containers)
        for artist in runtime.iter_artists():
            self.assertNotIn(artist, axes.lines)
            self.assertNotIn(artist, axes.collections)
        self.assertIsNone(self._errorbar_controller())

    def test_deletion_failure_restores_identity_selection_and_palette(self):
        from mygui.figuremodify.components.controllers import errorbar as controller_mod

        runtime = self._add_errorbar()
        controller = self._errorbar_controller()
        axes = self.canvas.current_axes
        palette_before = deepcopy(
            self.canvas.component_registry.get(
                self.canvas.current_axes_component_id
            ).state.properties.get("color_cycle")
        )
        self.canvas.select_component(controller.component_id)

        def failing_prepare(self_ctrl):
            raise RuntimeError("prepare exploded")

        with mock.patch.object(
            controller_mod.ErrorBarController,
            "prepare_remove",
            failing_prepare,
        ):
            deleted = self.canvas.delete_component_group(
                (controller.component_id,), role_label="Error Bar"
            )
        self.assertFalse(deleted)
        self.app.processEvents()
        self.assertIs(self._errorbar_controller(), controller)
        self.assertIn(runtime.container, axes.containers)
        self.assertIn(runtime.data_line, axes.lines)
        self.assertIs(self.canvas.current_component_id, controller.component_id)
        palette_after = self.canvas.component_registry.get(
            self.canvas.current_axes_component_id
        ).state.properties.get("color_cycle")
        self.assertEqual(palette_after, palette_before)

    def test_column_deletion_cascades_to_errorbar(self):
        runtime = self._add_errorbar()
        controller = self._errorbar_controller()
        before = {
            controller.component_id
            for controller in self.canvas.component_registry
        }
        snapshots = self.canvas.dependent_records({self.minus_ref})
        request = self.canvas.prepare_data_dependents(snapshots)
        self.assertTrue(
            self.canvas.remove_data_dependents(snapshots, request)
        )
        self.app.processEvents()
        self.assertNotIn(controller.component_id, self.canvas.component_registry)
        self.assertNotIn(runtime.container, self.canvas.current_axes.containers)
        self.assertEqual(
            {
                item.component_id
                for item in self.canvas.component_registry
            },
            before - {controller.component_id},
        )


class ErrorBarProjectIoTests(ErrorBarGuiTestCase):
    def test_save_open_roundtrip_keeps_stable_id_order_and_specs(self):
        from mygui.project_io import (
            restore_project_snapshot,
            save_project_snapshot,
        )

        self._add_errorbar()
        controller = self._errorbar_controller()
        saved_id = controller.component_id
        saved_order = controller.state.order
        saved_props = deepcopy(controller.state.properties)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "errorbar.mygui.json"
            save_project_snapshot(path, self.window.figure_window)
            loaded_window = MainWindow()
            try:
                restore_project_snapshot(
                    path, loaded_window.table, loaded_window.figure_window
                )
                restored_canvas = loaded_window.figure_window.current_canva
                restored = restored_canvas.component_registry.get(saved_id)
                self.assertEqual(restored.state.order, saved_order)
                self.assertEqual(restored.state.properties, saved_props)
                self.assertEqual(
                    restored.state.data["xerr"]["kind"], "symmetric_ref"
                )
                axes = restored_canvas.component_registry.resolve_target(
                    restored.state.parent_id
                )
                runtime_restored = restored.resolve_target()
                self.assertIn(runtime_restored.container, axes.containers)
                self.assertEqual(len(runtime_restored.caplines), 4)
                self.assertEqual(
                    runtime_restored.container[0].get_gid(), saved_id
                )
            finally:
                loaded_window.close()

    def test_v20_pins_v19_shape_and_migration_chain_extends_defaults(self):
        from mygui.project_io import (
            load_project_file,
            migrate_v19_to_v20,
            migrate_v20_to_v21,
            save_project_snapshot,
            validate_v19_project_snapshot,
            validate_v20_project_snapshot,
        )

        self._add_errorbar()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "errorbar.mygui.json"
            save_project_snapshot(path, self.window.figure_window)
            current = json.loads(path.read_text(encoding="utf-8"))

        # v19 rejected Error Bar records entirely.
        v19_reject = deepcopy(current)
        v19_reject["schema_version"] = 19
        with self.assertRaisesRegex(ValueError, "Error Bar"):
            validate_v19_project_snapshot(v19_reject)

        # Schema v20 pins the exact predecessor property set: the extended
        # v21 record must not round-trip into v20, while the trimmed v20
        # record validates and migrates with the deterministic defaults.
        v20_extended = deepcopy(current)
        v20_extended["schema_version"] = 20
        with self.assertRaisesRegex(ValueError, "Schema v20 Error Bar"):
            validate_v20_project_snapshot(v20_extended)

        without_errorbar = deepcopy(current)
        without_errorbar["figure"]["components"] = [
            component
            for component in without_errorbar["figure"]["components"]
            if component["kind"] != "errorbar"
        ]
        without_errorbar["schema_version"] = 19
        validate_v19_project_snapshot(without_errorbar)
        migrated_v20 = migrate_v19_to_v20(without_errorbar)
        self.assertEqual(migrated_v20["schema_version"], 20)

        trimmed = deepcopy(current)
        errorbar_component = next(
            component
            for component in trimmed["figure"]["components"]
            if component["kind"] == "errorbar"
        )
        saved_properties = deepcopy(errorbar_component["properties"])
        for key in (
            "markeredgewidth",
            "markerfacecoloralt",
            "fillstyle",
            "drawstyle",
            "antialiased",
            "error_linestyle",
            "error_capstyle",
            "error_antialiased",
            "errorevery",
            "lolims",
            "uplims",
            "xlolims",
            "xuplims",
        ):
            del errorbar_component["properties"][key]
        trimmed["schema_version"] = 20
        validate_v20_project_snapshot(trimmed)
        migrated = migrate_v20_to_v21(trimmed)
        self.assertEqual(migrated["schema_version"], 21)
        migrated_errorbar = next(
            component
            for component in migrated["figure"]["components"]
            if component["kind"] == "errorbar"
        )
        self.assertEqual(migrated_errorbar["properties"], saved_properties)
        self.assertEqual(migrated_errorbar["properties"]["markeredgewidth"], 1.0)
        self.assertEqual(
            migrated_errorbar["properties"]["errorevery"], {"kind": "all"}
        )
        self.assertIs(migrated_errorbar["properties"]["error_capstyle"], None)

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "v20.mygui.json"
            path.write_text(json.dumps(trimmed), encoding="utf-8")
            loaded = load_project_file(path)
        self.assertEqual(loaded["schema_version"], 21)
        loaded_errorbar = next(
            component
            for component in loaded["figure"]["components"]
            if component["kind"] == "errorbar"
        )
        self.assertEqual(loaded_errorbar["properties"], saved_properties)

    def test_non_numeric_error_column_rejects_open_before_publication(self):
        from mygui.project_io import restore_project_snapshot, save_project_snapshot

        self._add_errorbar()
        controller = self._errorbar_controller()
        column = self.sheet.add_column(
            "Notes", ColumnType.TEXT, values=["a"] * self.ROWS
        )
        text_ref = ColumnRef(self.canvas.project_id, self.sheet.id, column.id)
        bad_spec = {"kind": "symmetric_ref", "ref": text_ref.to_dict()}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bad-error-column.mygui.json"
            save_project_snapshot(path, self.window.figure_window)
            payload = json.loads(path.read_text(encoding="utf-8"))
            for component in payload["figure"]["components"]:
                if component["kind"] == "errorbar":
                    component["data"]["xerr"] = bad_spec
            path.write_text(json.dumps(payload), encoding="utf-8")

            before = set(self.window.repository.projects)
            with self.assertRaises(ValueError):
                restore_project_snapshot(
                    path, self.window.table, self.window.figure_window
                )
            self.app.processEvents()
            self.assertEqual(set(self.window.repository.projects), before)
            self.assertIs(self.window.figure_window.current_canva, self.canvas)
        del controller

    def test_v21_rejects_missing_and_unknown_errorbar_properties(self):
        from mygui.project_io import (
            save_project_snapshot,
            validate_project_snapshot,
        )

        self._add_errorbar()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "strict-v21.mygui.json"
            save_project_snapshot(path, self.window.figure_window)
            current = json.loads(path.read_text(encoding="utf-8"))
        component = next(
            item
            for item in current["figure"]["components"]
            if item["kind"] == "errorbar"
        )
        missing = deepcopy(current)
        missing_component = next(
            item
            for item in missing["figure"]["components"]
            if item["kind"] == "errorbar"
        )
        del missing_component["properties"]["error_antialiased"]
        with self.assertRaisesRegex(ValueError, "missing"):
            validate_project_snapshot(missing)

        component["properties"]["unsupported_error_style"] = True
        with self.assertRaisesRegex(ValueError, "unknown"):
            validate_project_snapshot(current)


class ErrorBarTemplateTests(ErrorBarGuiTestCase):
    def test_template_extract_and_nested_refs_remap(self):
        from mygui.template_library import TemplateExtractor
        from mygui.template_library.transform import _replace_refs

        self._add_errorbar()
        extractor = TemplateExtractor(self.repository)
        template = extractor.extract(self.canvas, name="ErrorBar template")
        errorbar_components = [
            component
            for component in template.figure["components"]
            if component["kind"] == "errorbar"
        ]
        self.assertEqual(len(errorbar_components), 1)
        component = errorbar_components[0]
        self.assertEqual(component["data"]["xerr"]["kind"], "symmetric_ref")
        nested_refs = []
        for key in ("xerr", "yerr"):
            nested_refs.extend(error_spec_references(component["data"][key]))
        self.assertEqual(len(nested_refs), 2)
        self.assertTrue(
            all(ref["project_id"] == "template-project" for ref in nested_refs)
        )

        slot_map = {}
        for sheet in template.data_contract.sheets:
            for column in sheet.columns:
                slot_map[ColumnRef("template-project", sheet.id, column.id)] = (
                    ColumnRef("target-project", f"sheet-{len(slot_map)}", f"col-{len(slot_map)}")
                )
        figure = _replace_refs(template.figure, slot_map)
        remapped_errorbars = [
            item
            for item in figure["components"]
            if item["kind"] == "errorbar"
        ]
        self.assertEqual(len(remapped_errorbars), 1)
        remapped_refs = []
        for key in ("xerr", "yerr"):
            remapped_refs.extend(
                error_spec_references(remapped_errorbars[0]["data"][key])
            )
        self.assertEqual(len(remapped_refs), 2)
        self.assertTrue(
            all(ref["project_id"] == "target-project" for ref in remapped_refs)
        )

    def test_template_v4_migrates_to_v5_and_rejects_extended_v4(self):
        from mygui.template_library import TemplateExtractor, template_to_dict
        from mygui.template_library.schema import migrate_v4_template_to_v5

        self._add_errorbar()
        current = template_to_dict(
            TemplateExtractor(self.repository).extract(
                self.canvas,
                name="ErrorBar v5",
            )
        )
        component = next(
            item
            for item in current["figure"]["components"]
            if item["kind"] == "errorbar"
        )
        extended = deepcopy(current)
        extended["schema_version"] = 4
        with self.assertRaisesRegex(ValueError, "Schema v20 Error Bar"):
            migrate_v4_template_to_v5(extended)

        for key in (
            "markeredgewidth",
            "markerfacecoloralt",
            "fillstyle",
            "drawstyle",
            "antialiased",
            "error_linestyle",
            "error_capstyle",
            "error_antialiased",
            "errorevery",
            "lolims",
            "uplims",
            "xlolims",
            "xuplims",
        ):
            del component["properties"][key]
        current["schema_version"] = 4
        migrated = migrate_v4_template_to_v5(current)
        self.assertEqual(template_to_dict(migrated)["schema_version"], 5)
        migrated_component = next(
            item
            for item in migrated.figure["components"]
            if item["kind"] == "errorbar"
        )
        self.assertEqual(
            migrated_component["properties"]["errorevery"],
            {"kind": "all"},
        )
        self.assertFalse(migrated_component["properties"]["lolims"])


class ErrorEverySpecTests(unittest.TestCase):
    """The closed ErrorEverySpec contract normalizes and rejects strictly."""

    def test_all_and_stride_roundtrip(self):
        from mygui.figuremodify.components.property_values import (
            normalize_error_every,
        )

        self.assertEqual(normalize_error_every({"kind": "all"}), {"kind": "all"})
        self.assertEqual(
            normalize_error_every({"kind": "stride", "start": 2, "step": 3}),
            {"kind": "stride", "start": 2, "step": 3},
        )
        self.assertEqual(
            normalize_error_every({"kind": "stride", "start": 0, "step": 1}),
            {"kind": "all"},
        )

    def test_rejects_bool_negative_and_unknown(self):
        from mygui.figuremodify.components.property_values import (
            normalize_error_every,
        )

        for value in (
            {"kind": "stride", "start": True, "step": 2},
            {"kind": "stride", "start": -1, "step": 2},
            {"kind": "stride", "start": 0, "step": 0},
            {"kind": "stride", "start": 0},
            {"kind": "slice", "start": 0},
            {"kind": "spacing"},
            "all",
        ):
            with self.subTest(value=value):
                with self.assertRaises(ComponentValidationError):
                    normalize_error_every(value)


class ErrorBarStructurePropertyTests(ErrorBarGuiTestCase):
    def test_errorevery_resamples_segments_and_rebuilds_container(self):
        self._add_errorbar(
            xerr=_symmetric_ref(self.minus_ref),
            yerr=None,
            errorevery={"kind": "stride", "start": 1, "step": 2},
        )
        controller = self._controller()
        runtime = controller.resolve_target()
        container_before = runtime.container
        stride_segments = len(runtime.barlinecols[0].get_segments())
        self.assertEqual(stride_segments, 2)
        change = controller.set_property("errorevery", {"kind": "all"})
        self.assertTrue(change.ok, change.message)
        runtime_after = controller.resolve_target()
        self.assertEqual(
            len(runtime_after.barlinecols[0].get_segments()), self.ROWS
        )
        self.assertIsNot(runtime_after.container, container_before)
        self.assertIsNone(controller._swap_memento)

    def test_zero_size_caps_keep_errorevery_sampling_when_made_visible(self):
        self._add_errorbar(
            xerr=_asymmetric_ref(self.minus_ref, self.plus_ref),
            yerr=None,
            capsize=0.0,
            errorevery={"kind": "stride", "start": 1, "step": 2},
        )
        controller = self._controller()
        runtime = controller.resolve_target()
        self.assertEqual(len(runtime.caplines), 2)
        self.assertTrue(
            all(len(cap.get_xdata()) == 2 for cap in runtime.caplines)
        )
        self.assertTrue(controller.set_property("capsize", 4.0).ok)
        self.assertTrue(
            all(cap.get_markersize() == 8.0 for cap in runtime.caplines)
        )
        lower = np.asarray(runtime.caplines[0].get_xdata(), dtype=float)
        expected = np.asarray(runtime.data.x)[1::2] - np.asarray(runtime.data.xerr)[0, 1::2]
        self.assertTrue(np.allclose(lower, expected))

    def test_errorevery_autoscale_shrinks_to_drawn_segments(self):
        self.sheet.set_block(
            0,
            2,
            [[100.0], [1.0], [100.0], [1.0], [100.0]],
        )
        self._add_errorbar(
            xerr=None,
            yerr=_symmetric_ref(self.minus_ref),
            errorevery={"kind": "all"},
        )
        controller = self._controller()
        axes = controller.resolve_target().axes
        upper_all = axes.get_ylim()[1]

        change = controller.set_property(
            "errorevery", {"kind": "stride", "start": 1, "step": 2}
        )

        self.assertTrue(change.ok, change.message)
        upper_stride = axes.get_ylim()[1]
        self.assertLess(upper_stride, upper_all)
        self.assertGreater(upper_stride, max(controller.resolve_target().data.y))

    def test_limit_arrows_follow_axes_direction_flip(self):
        from matplotlib import lines as mlines

        self._add_errorbar(
            yerr={"kind": "constant", "minus": 1.0, "plus": 1.0},
            capsize=4.0,
            lolims=True,
        )
        controller = self._controller()
        runtime = controller.resolve_target()
        markers_before = tuple(cap.get_marker() for cap in runtime.caplines)
        self.assertIn(mlines.CARETUPBASE, markers_before)

        axes_controller = self.canvas.component_registry.get(self._axes_ids[0])
        bottom, top = axes_controller.state.properties["ylim"]
        change = axes_controller.set_property("ylim", (top, bottom))
        self.assertTrue(change.ok, change.message)
        self.assertFalse(runtime.direction_changed())
        markers_after = tuple(cap.get_marker() for cap in runtime.caplines)
        self.assertIn(mlines.CARETDOWNBASE, markers_after)
        self.assertNotEqual(markers_before, markers_after)

    def test_structure_property_rebuild_failure_rolls_back(self):
        from mygui.figuremodify.services import errorbar as errorbar_module

        self._add_errorbar(xerr=_symmetric_ref(self.minus_ref))
        controller = self._controller()
        runtime = controller.resolve_target()
        container_before = runtime.container
        spec_before = deepcopy(controller.state.properties["errorevery"])
        with mock.patch.object(
            errorbar_module,
            "create_errorbar_container",
            side_effect=RuntimeError("rebuild boom"),
        ):
            change = controller.set_property(
                "errorevery", {"kind": "stride", "start": 2, "step": 2}
            )
        self.assertFalse(change.ok)
        self.assertIs(runtime.container, container_before)
        self.assertEqual(
            controller.state.properties["errorevery"], spec_before
        )

    def test_update_failure_restores_exact_container_and_artist_identity(self):
        self._add_errorbar(xerr=_symmetric_ref(self.minus_ref))
        controller = self._controller()
        runtime = controller.resolve_target()
        container_before = runtime.container
        artists_before = runtime.iter_artists()
        state_before = controller.state
        with mock.patch.object(
            controller,
            "_request_updates",
            side_effect=RuntimeError("redraw boom"),
        ):
            change = controller.set_property(
                "errorevery", {"kind": "stride", "start": 1, "step": 2}
            )
        self.assertFalse(change.ok)
        self.assertIs(runtime.container, container_before)
        self.assertEqual(runtime.iter_artists(), artists_before)
        self.assertEqual(controller.state, state_before)

    def test_structure_property_undo_and_redo(self):
        self._add_errorbar(xerr=_symmetric_ref(self.minus_ref))
        controller = self._controller()
        component_id = controller.component_id
        change = self._record(
            "Change Error Bar Every",
            lambda: controller.set_property(
                "errorevery", {"kind": "stride", "start": 1, "step": 2}
            ),
        )
        self.assertTrue(change.ok)
        self.app.processEvents()
        self.assertEqual(
            controller.state.properties["errorevery"],
            {"kind": "stride", "start": 1, "step": 2},
        )

        self.stack.undo()
        self.app.processEvents()
        restored = self.canvas.component_registry.get(component_id)
        self.assertEqual(
            restored.state.properties["errorevery"], {"kind": "all"}
        )
        self.assertEqual(
            len(restored.resolve_target().barlinecols[0].get_segments()),
            self.ROWS,
        )

        self.stack.redo()
        self.app.processEvents()
        restored = self.canvas.component_registry.get(component_id)
        self.assertEqual(
            restored.state.properties["errorevery"],
            {"kind": "stride", "start": 1, "step": 2},
        )


class ErrorBarStylePropertyTests(ErrorBarGuiTestCase):
    def test_markeredgewidth_and_capthick_are_independent(self):
        self._add_errorbar(
            xerr=_symmetric_ref(self.minus_ref),
            capsize=4.0,
            capthick=0.5,
            markeredgewidth=2.5,
        )
        controller = self._controller()
        runtime = controller.resolve_target()
        self.assertEqual(runtime.data_line.get_markeredgewidth(), 2.5)
        self.assertEqual(runtime.caplines[0].get_markeredgewidth(), 0.5)
        change = controller.set_property("markeredgewidth", 3.0)
        self.assertTrue(change.ok)
        self.assertEqual(runtime.data_line.get_markeredgewidth(), 3.0)
        self.assertEqual(runtime.caplines[0].get_markeredgewidth(), 0.5)
        change = controller.set_property("capthick", 1.5)
        self.assertTrue(change.ok)
        self.assertEqual(runtime.data_line.get_markeredgewidth(), 3.0)
        self.assertEqual(runtime.caplines[0].get_markeredgewidth(), 1.5)

    def test_error_line_styles_apply_to_collections_and_caps(self):
        self._add_errorbar(
            xerr=_symmetric_ref(self.minus_ref),
            capsize=4.0,
            elinewidth=1.0,
            error_linestyle={"kind": "custom", "offset": 0.0, "dashes": [4.0, 2.0]},
            error_capstyle="round",
            error_antialiased=False,
        )
        controller = self._controller()
        runtime = controller.resolve_target()
        collection = runtime.barlinecols[0]
        self.assertEqual(collection.get_linestyle()[0][1], [4.0, 2.0])
        self.assertEqual(collection.get_capstyle(), "round")
        self.assertFalse(bool(collection.get_antialiased()[0]))
        self.assertFalse(bool(runtime.caplines[0].get_antialiased()))

        change = controller.set_property("error_capstyle", None)
        self.assertTrue(change.ok)
        self.assertIsNone(runtime.barlinecols[0]._capstyle)
        change = controller.set_property("error_antialiased", True)
        self.assertTrue(change.ok)
        self.assertTrue(bool(runtime.barlinecols[0].get_antialiased()[0]))

    def test_data_line_extras_roundtrip(self):
        self._add_errorbar(
            drawstyle="steps-mid",
            antialiased=False,
            markerfacecoloralt="#123456",
            fillstyle="left",
        )
        controller = self._controller()
        runtime = controller.resolve_target()
        self.assertEqual(runtime.data_line.get_drawstyle(), "steps-mid")
        self.assertFalse(runtime.data_line.get_antialiased())
        self.assertEqual(runtime.data_line.get_markerfacecoloralt(), "#123456")
        self.assertEqual(runtime.data_line.get_fillstyle(), "left")
        synced = controller.sync_from_target()
        self.assertEqual(synced.properties["drawstyle"], "steps-mid")
        self.assertEqual(synced.properties["fillstyle"], "left")


class ErrorBarDataEditingTests(ErrorBarGuiTestCase):
    def _section(self, controller):
        from mygui.widgets.fig_control_window.component_editors.sections.errorbar import (
            ErrorBarDataSection,
        )

        section = ErrorBarDataSection(
            controller,
            context=self.canvas.editor_context,
        )
        self.addCleanup(section.dispose)
        return section

    def _spec_input(self):
        from mygui.widgets.fig_control_window.component_editors.errorbar_inputs import (
            ErrorSpecInput,
        )

        widget = ErrorSpecInput(
            self.window.repository,
            self.canvas.project_id,
            label="Y Error",
        )
        self.addCleanup(widget.dispose)
        return widget

    def test_errorevery_editor_exposes_only_closed_all_and_stride_modes(self):
        from mygui.figuremodify.components import EditorKind
        from mygui.widgets.fig_control_window.component_editors import (
            ErrorEveryEditor,
        )

        self.assertIs(
            ErrorBarController.property_specs()["errorevery"].editor,
            EditorKind.ERROR_EVERY,
        )
        editor = ErrorEveryEditor({"kind": "all"})
        dialog = editor._dialog()
        self.addCleanup(editor.close)
        self.addCleanup(dialog.close)
        self.assertEqual(
            tuple(
                dialog.kind_input.itemData(index)
                for index in range(dialog.kind_input.count())
            ),
            ("all", "stride"),
        )

    def test_mode_switch_keeps_incomplete_draft_without_none_downgrade(self):
        widget = self._spec_input()
        widget.mode_input.setCurrentIndex(2)  # Symmetric Column
        self.assertEqual(widget.mode_input.currentData(), "symmetric_ref")
        self.assertIs(widget.page_stack.currentWidget(), widget.symmetric_page)
        self.assertIsNotNone(widget.spec_error())
        self.assertIn("select one numeric error column", widget.spec_error())
        # Completing the draft clears the error without resetting the mode.
        widget.symmetric_input.setCurrentIndex(1)
        self.assertIsNone(widget.spec_error())
        self.assertEqual(
            widget.value()["kind"], "symmetric_ref"
        )

    def test_asymmetric_draft_requires_both_columns(self):
        widget = self._spec_input()
        widget.mode_input.setCurrentIndex(3)
        self.assertIsNotNone(widget.spec_error())
        widget.asymmetric_minus_input.setCurrentIndex(1)
        self.assertIsNotNone(widget.spec_error())
        widget.asymmetric_plus_input.setCurrentIndex(2)
        self.assertIsNone(widget.spec_error())
        self.assertEqual(widget.value()["kind"], "asymmetric_ref")

    def test_creation_dialog_submits_error_styles_and_all_error_modes(self):
        from mygui.widgets.title_bar.titlebar_dialog.py_errorbar_dialog import (
            PyErrorBarDialog,
        )

        dialog = PyErrorBarDialog(
            "Error Bar",
            figure_window=self.window.figure_window,
        )
        self.addCleanup(dialog.close)
        dialog.data_reference_input.set_refs(self.x_ref, self.y_ref)
        x_error = dialog.x_error_input
        x_error.mode_input.setCurrentIndex(3)
        x_error._set_ref(x_error.asymmetric_minus_input, self.minus_ref)
        x_error._set_ref(x_error.asymmetric_plus_input, self.plus_ref)
        y_error = dialog.y_error_input
        y_error.mode_input.setCurrentIndex(1)
        y_error.minus_input.setValue(0.25)
        y_error.plus_input.setValue(0.75)
        dialog.appearance_input.color_input.set_color("#654321")
        dialog.line_style_editor.set_style("--")
        dialog.marker_editor.set_marker("s")
        dialog.marker_editor.set_size(7.5)
        dialog.style_group.ecolor_input.set_color("#123456")
        dialog.style_group.linewidth_input.setValue(2.25)
        dialog.style_group.markeredgewidth_input.setValue(2.0)
        dialog.style_group.markerfacecoloralt_input.enabled_input.setChecked(True)
        dialog.style_group.markerfacecoloralt_input.color_input.set_color("#ABCDEF")
        dialog.style_group.fillstyle_input.setCurrentText("left")
        dialog.style_group.drawstyle_input.setCurrentText("steps-mid")
        dialog.style_group.antialiased_input.setChecked(False)
        dialog.style_group.elinewidth_input.setValue(1.75)
        dialog.style_group.capsize_input.setValue(3.0)
        dialog.style_group.capthick_input.setValue(0.8)
        dialog.style_group.error_linestyle_input.set_value(
            {"kind": "preset", "value": ":"}
        )
        dialog.style_group.error_capstyle_input.setCurrentIndex(
            dialog.style_group.error_capstyle_input.findData("round")
        )
        dialog.style_group.error_antialiased_input.setChecked(False)
        dialog.style_group.barsabove_input.setChecked(True)
        dialog.style_group.errorevery_start_input.setValue(1)
        dialog.style_group.errorevery_input.setValue(2)
        dialog.style_group.lolims_input.setChecked(True)
        dialog.style_group.uplims_input.setChecked(True)
        dialog.style_group.xlolims_input.setChecked(True)
        dialog.style_group.xuplims_input.setChecked(True)

        dialog.accept()

        controller = self._controller()
        self.assertIsNotNone(controller)
        self.assertEqual(controller.state.data["xerr"]["kind"], "asymmetric_ref")
        self.assertEqual(
            controller.state.data["yerr"],
            {"kind": "constant", "minus": 0.25, "plus": 0.75},
        )
        properties = controller.state.properties
        self.assertEqual(properties["color"], "#654321")
        self.assertEqual(properties["linestyle"]["value"], "--")
        self.assertEqual(properties["marker"]["value"], "s")
        self.assertEqual(properties["markersize"], 7.5)
        self.assertEqual(properties["ecolor"], "#123456")
        self.assertEqual(properties["linewidth"], 2.25)
        self.assertEqual(properties["markeredgewidth"], 2.0)
        self.assertEqual(properties["markerfacecoloralt"], "#abcdef")
        self.assertEqual(properties["fillstyle"], "left")
        self.assertEqual(properties["drawstyle"], "steps-mid")
        self.assertFalse(properties["antialiased"])
        self.assertEqual(properties["elinewidth"], 1.75)
        self.assertEqual(properties["capsize"], 3.0)
        self.assertEqual(properties["capthick"], 0.8)
        self.assertEqual(properties["error_linestyle"]["value"], ":")
        self.assertEqual(properties["error_capstyle"], "round")
        self.assertFalse(properties["error_antialiased"])
        self.assertTrue(properties["barsabove"])
        for key in ("lolims", "uplims", "xlolims", "xuplims"):
            self.assertTrue(properties[key])
        self.assertEqual(
            properties["errorevery"],
            {"kind": "stride", "start": 1, "step": 2},
        )

    def test_creation_dialog_scrolls_and_defaults_to_distinct_xy_columns(self):
        from PySide6.QtCore import Qt
        from PySide6.QtWidgets import QScrollArea

        from mygui.widgets.title_bar.titlebar_dialog.py_errorbar_dialog import (
            PyErrorBarDialog,
        )

        dialog = PyErrorBarDialog(
            "Error Bar",
            figure_window=self.window.figure_window,
        )
        self.addCleanup(dialog.close)
        dialog.show()
        self.app.processEvents()

        self.assertIsInstance(dialog.scroll_area, QScrollArea)
        self.assertTrue(dialog.scroll_area.widgetResizable())
        self.assertIs(dialog.scroll_area.widget(), dialog.content_widget)
        self.assertEqual(
            dialog.scroll_area.horizontalScrollBarPolicy(),
            Qt.ScrollBarAlwaysOff,
        )
        self.assertLessEqual(dialog.height(), 720)
        self.assertGreater(
            dialog.scroll_area.verticalScrollBar().maximum(),
            0,
        )
        self.assertEqual(dialog.data_reference_input.get_x_ref(), self.x_ref)
        self.assertEqual(dialog.data_reference_input.get_y_ref(), self.y_ref)

    def test_deleted_column_marks_draft_incomplete(self):
        widget = self._spec_input()
        widget.mode_input.setCurrentIndex(2)
        widget.symmetric_input.setCurrentIndex(1)
        self.assertIsNone(widget.spec_error())
        column_id = widget.symmetric_input.currentData().column_id
        self.sheet.remove_column(column_id)
        widget._repository_changed(
            type(
                "C",
                (),
                {
                    "project_id": self.canvas.project_id,
                    "metadata_changed": True,
                    "structure_changed": True,
                },
            )()
        )
        self.assertIsNotNone(widget.spec_error())
        self.assertEqual(widget.mode_input.currentData(), "symmetric_ref")

    def test_section_apply_submits_once_and_reset_restores(self):
        self._add_errorbar(yerr=_symmetric_ref(self.minus_ref))
        controller = self._controller()
        section = self._section(controller)
        self.assertTrue(section.apply_button.isEnabled())
        self.assertEqual(section.hint_label.text(), "")

        # Draft: switch the Y error to a constant; nothing commits yet.
        section.data_input.y_error_input.mode_input.setCurrentIndex(1)
        self.assertTrue(section.apply_button.isEnabled())
        self.assertEqual(
            controller.state.data["yerr"]["kind"], "symmetric_ref"
        )
        section.data_input.y_error_input.minus_input.setValue(0.25)
        section.data_input.y_error_input.plus_input.setValue(0.75)

        stack_count = self.stack.count()
        self.assertTrue(section.apply_clicked())
        self.assertEqual(
            controller.state.data["yerr"],
            {"kind": "constant", "minus": 0.25, "plus": 0.75},
        )
        self.assertEqual(self.stack.count(), stack_count + 1)

        # Reset restores the committed state without adding history.
        section.data_input.y_error_input.minus_input.setValue(9.0)
        section.reset_clicked()
        self.assertEqual(
            section.data_input.y_error_input.minus_input.value(), 0.25
        )
        self.assertEqual(self.stack.count(), stack_count + 1)

    def test_section_unchanged_apply_is_noop(self):
        self._add_errorbar(yerr=_symmetric_ref(self.minus_ref))
        controller = self._controller()
        section = self._section(controller)
        runtime = controller.resolve_target()
        container_before = runtime.container
        stack_count = self.stack.count()

        self.assertTrue(section.apply_clicked())

        self.assertEqual(self.stack.count(), stack_count)
        self.assertIs(runtime.container, container_before)

    def test_section_blocks_apply_for_incomplete_draft(self):
        self._add_errorbar(yerr=_symmetric_ref(self.minus_ref))
        controller = self._controller()
        section = self._section(controller)
        # Switch to asymmetric with no columns picked: draft incomplete.
        section.data_input.y_error_input.mode_input.setCurrentIndex(3)
        self.assertFalse(section.apply_button.isEnabled())
        self.assertIn("select the minus", section.hint_label.text())
        stack_count = self.stack.count()
        self.assertFalse(section.apply_clicked())
        self.assertEqual(self.stack.count(), stack_count)
        self.assertEqual(
            controller.state.data["yerr"]["kind"], "symmetric_ref"
        )

        # Completing the draft re-enables Apply.
        section.data_input.y_error_input.asymmetric_minus_input.setCurrentIndex(1)
        section.data_input.y_error_input.asymmetric_plus_input.setCurrentIndex(2)
        self.assertTrue(section.apply_button.isEnabled())
        self.assertTrue(section.apply_clicked())
        self.assertEqual(
            controller.state.data["yerr"]["kind"], "asymmetric_ref"
        )

    def test_section_rejection_restores_last_committed_controls(self):
        self._add_errorbar(yerr=_symmetric_ref(self.minus_ref))
        controller = self._controller()
        section = self._section(controller)
        # The service rejects the Apply (simulated data-resolution failure);
        # the section must present the error and restore the committed
        # controls so the visible draft matches the authoritative state.
        section.data_input.y_error_input.minus_input.setValue(1.0)
        section.data_input.y_error_input.plus_input.setValue(2.0)
        section.data_input.y_error_input.mode_input.setCurrentIndex(1)
        rejected = ComponentChange(
            controller.component_id,
            None,
            controller.state,
            controller.state,
            ChangeStatus.REJECTED,
            message="Error Bar yerr column was removed.",
        )
        stack_count = self.stack.count()
        with mock.patch.object(
            self.canvas.errorbar_service,
            "configure",
            return_value=rejected,
        ):
            self.assertFalse(section.apply_clicked())
        self.assertEqual(self.stack.count(), stack_count)
        self.assertEqual(
            controller.state.data["yerr"]["kind"], "symmetric_ref"
        )
        self.assertEqual(
            section.data_input.y_error_input.mode_input.currentData(),
            "symmetric_ref",
        )


if __name__ == "__main__":
    unittest.main()
