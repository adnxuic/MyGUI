import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from tests.axes_helpers import create_regular_axes

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
from PySide6.QtTest import QTest

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QComboBox, QDialog

from mygui import status_messages
from mygui.database import ColumnRef, TableChangeSet
from mygui.database.interpolate_func import interpolate_dict
from mygui.figuremodify.components import ComponentRole
from mygui.figuremodify.style_base.color_models import ColorSelection
from mygui.project_io import (
    load_project_file,
    restore_project_snapshot,
    save_project_snapshot,
)
from mygui.widgets.fig_control_window.component_editors import (
    MultiSeriesDataReferenceInput,
)
from mygui.widgets.title_bar.titlebar_dialog.py_chart_dialog import (
    PyInterpolationDialog,
    PyPlotDialog,
)
from main import MainWindow


class BatchChartCreationTests(unittest.TestCase):
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
            canva_name="Batch",
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
                [0.0, 10.0, 20.0, 1.0],
                [1.0, 11.0, 21.0, None],
                [2.0, 12.0, None, None],
                [3.0, 13.0, 23.0, None],
            ],
        )
        for column, name in zip(
            self.sheet.columns[:4],
            ("Shared X", "Y One", "Y Two", "Bad Y"),
        ):
            column.name = name
        self.x_ref = self._ref(0)
        self.y1_ref = self._ref(1)
        self.y2_ref = self._ref(2)
        self.bad_ref = self._ref(3)
        self.window.color_library.recent_colors = []

    def tearDown(self):
        status_messages.clear_status_handler()
        self.window.close()
        self.app.processEvents()

    def _ref(self, index):
        return ColumnRef(
            self.canvas.project_id,
            self.sheet.id,
            self.sheet.columns[index].id,
        )

    @staticmethod
    def _identity_preprocess():
        return {"x_expression": "x", "y_expression": "y"}

    def _palette_selection(self):
        return self.canvas.creation_color_cycle().peek()

    def test_multi_series_dropdown_checks_and_retains_stable_refs(self):
        widget = MultiSeriesDataReferenceInput(
            self.window.repository,
            self.canvas.project_id,
        )
        try:
            self.assertEqual(widget.get_x_ref(), self.x_ref)
            self.assertEqual(widget.get_y_refs(), (self.y1_ref,))
            self.assertIsInstance(widget.y_data_input, QComboBox)
            self.assertFalse(widget.x_expression_input.isHidden())
            self.assertFalse(widget.y_expression_input.isHidden())
            self.assertEqual(widget.x_expression_input.text(), "x")
            self.assertEqual(widget.y_expression_input.text(), "y")

            widget.show()
            self.app.processEvents()
            self.assertTrue(widget.x_expression_input.isVisible())
            self.assertTrue(widget.y_expression_input.isVisible())
            widget.y_data_input.showPopup()
            self.app.processEvents()
            y_two_index = widget.y_data_input.model().index(2, 0)
            y_two_rect = widget.y_data_input.view().visualRect(y_two_index)
            QTest.mouseClick(
                widget.y_data_input.view().viewport(),
                Qt.LeftButton,
                pos=y_two_rect.center(),
            )
            self.app.processEvents()
            self.assertIn(self.y2_ref, widget.get_y_refs())
            self.assertTrue(widget.y_data_input.view().isVisible())
            widget.y_data_input.hidePopup()

            widget.clear_all()
            widget.y_data_input.model().item(2).setCheckState(Qt.Checked)
            self.assertEqual(widget.get_y_refs(), (self.y2_ref,))

            widget.set_y_refs((self.y1_ref, self.y2_ref))
            self.assertEqual(
                widget.get_y_refs(),
                (self.y1_ref, self.y2_ref),
            )
            self.assertIn(
                "2 Y columns selected",
                widget.y_data_input.lineEdit().text(),
            )

            with self.window.repository.mutate(
                TableChangeSet(
                    self.canvas.project_id,
                    metadata_changed=True,
                    reason="test-rename",
                )
            ):
                self.sheet.column(self.y2_ref.column_id).name = "Renamed Y"
            self.assertEqual(
                widget.get_y_refs(),
                (self.y1_ref, self.y2_ref),
            )
            labels = [
                widget.y_data_input.model().item(index).text()
                for index in range(widget.y_data_input.count())
            ]
            self.assertTrue(any(label.endswith("/Renamed Y") for label in labels))
            widget.dispose()
            widget.dispose()
        finally:
            widget.close()

    def test_plot_batch_creates_independent_components_with_one_publication(self):
        event_batches = []
        unsubscribe = self.canvas.component_registry.subscribe_batches(
            event_batches.append
        )
        try:
            with patch.object(self.canvas, "redraw") as redraw:
                result = self.canvas.add_plots(
                    self.x_ref,
                    (self.y1_ref, self.y2_ref),
                    style="--",
                    size=5.0,
                    linewidth=3.5,
                    preprocess=self._identity_preprocess(),
                    color_selection=self._palette_selection(),
                )
            controllers = self.canvas.component_registry.query(
                role=ComponentRole.DATA_PLOT
            )
            self.assertEqual(len(controllers), 2)
            self.assertEqual(
                [controller.state.properties["label"] for controller in controllers],
                ["Y One", "Y Two"],
            )
            self.assertEqual(
                [controller.state.properties["linestyle"] for controller in controllers],
            [
                {"kind": "preset", "value": "--"},
                {"kind": "preset", "value": "--"},
            ],
            )
            self.assertEqual(
                [controller.state.properties["linewidth"] for controller in controllers],
                [3.5, 3.5],
            )
            defaults = self.canvas.component_creation_defaults()
            self.assertEqual(
                tuple(color.casefold() for color in result.colors),
                tuple(
                    color.casefold()
                    for color in defaults.chart_palette.colors[:2]
                ),
            )
            self.assertEqual(
                self.canvas.axes_commands.cycle_state(
                    self.canvas.current_axes_component_id
                ).next_index,
                2,
            )
            self.assertEqual(
                self.canvas.current_component_id,
                result.component_ids[-1],
            )
            self.assertEqual(len(event_batches), 1)
            redraw.assert_called_once_with()
            for component_id, artist in zip(
                result.component_ids, result.artists
            ):
                self.assertIs(
                    self.canvas.component_registry.locator.bound_target(
                        component_id
                    ),
                    artist,
                )
                self.assertIsNotNone(
                    self.canvas.component_editor_manager.editor(component_id)
                )
        finally:
            unsubscribe()

    def test_scatter_batch_filters_each_pair_and_custom_color_is_fixed(self):
        result = self.canvas.add_scatters(
            self.x_ref,
            (self.y1_ref, self.y2_ref),
            size=42.0,
            marker="s",
            preprocess=self._identity_preprocess(),
            color_selection=ColorSelection("#123456"),
        )

        self.assertEqual(result.colors, ("#123456", "#123456"))
        self.assertEqual(result.excluded_counts, (0, 1))
        self.assertEqual(
            [len(artist.get_offsets()) for artist in result.artists],
            [4, 3],
        )
        self.assertIsNone(
            self.canvas.axes_commands.cycle_state(
                self.canvas.current_axes_component_id
            ).active_palette
        )

    def test_scatter_mapping_creation_uses_aligned_mask_without_palette_commit(self):
        color_mapping = {
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
        size_mapping = {
            "enabled": True,
            "input": None,
            "output": [10.0, 90.0],
            "clamp": True,
        }
        before_cycle = self.canvas.axes_commands.cycle_state(
            self.canvas.current_axes_component_id
        ).to_dict()

        result = self.canvas.add_scatters(
            self.x_ref,
            (self.y1_ref,),
            size=42.0,
            marker="o",
            preprocess=self._identity_preprocess(),
            color_selection=self._palette_selection(),
            color_ref=self.y2_ref,
            size_ref=self.y1_ref,
            color_mapping=color_mapping,
            size_mapping=size_mapping,
        )

        controller = self.canvas.component_registry.get(
            result.component_ids[0]
        )
        artist = result.artists[0]
        self.assertEqual(len(artist.get_offsets()), 3)
        np.testing.assert_allclose(artist.get_array(), [20.0, 21.0, 23.0])
        self.assertEqual(len(artist.get_sizes()), 3)
        self.assertEqual(controller.state.data["color_ref"], self.y2_ref.to_dict())
        self.assertEqual(controller.state.data["size_ref"], self.y1_ref.to_dict())
        self.assertEqual(
            self.canvas.axes_commands.cycle_state(
                self.canvas.current_axes_component_id
            ).to_dict(),
            before_cycle,
        )

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "scatter-mapping.mygui.json"
            save_project_snapshot(path, self.window.figure_window)
            loaded = MainWindow()
            try:
                restore_project_snapshot(path, loaded.table, loaded.figure_window)
                restored = loaded.figure_window.current_canva
                restored_controller = restored.component_registry.get(
                    controller.component_id
                )
                self.assertEqual(
                    restored_controller.state.data["color_ref"],
                    self.y2_ref.to_dict(),
                )
                self.assertEqual(
                    restored_controller.state.data["size_ref"],
                    self.y1_ref.to_dict(),
                )
                self.assertEqual(
                    restored_controller.state.properties["color_mapping"],
                    controller.state.properties["color_mapping"],
                )
                np.testing.assert_allclose(
                    restored_controller.resolve_target().get_array(),
                    [20.0, 21.0, 23.0],
                )
                self.assertEqual(
                    len(restored_controller.resolve_target().get_sizes()),
                    3,
                )
            finally:
                loaded.close()
                self.app.processEvents()

    def test_interpolation_batch_uses_shared_options(self):
        method = list(interpolate_dict)[2]
        result = self.canvas.add_interpolate_curves(
            self.x_ref,
            (self.y1_ref, self.y2_ref),
            method=method,
            samples=32,
            k=2,
            lam=None,
            lam_auto=True,
            preprocess=self._identity_preprocess(),
            color_selection=self._palette_selection(),
        )

        self.assertEqual([len(line.get_xdata()) for line in result.artists], [32, 32])
        controllers = self.canvas.component_registry.query(
            role=ComponentRole.INTERPOLATION
        )
        self.assertEqual(
            [controller.state.data["method"] for controller in controllers],
            [method, method],
        )
        self.assertEqual(
            [controller.state.data["samples"] for controller in controllers],
            [32, 32],
        )

    def test_shared_x_refreshes_all_plots_with_one_canvas_draw(self):
        result = self.canvas.add_plots(
            self.x_ref,
            (self.y1_ref, self.y2_ref),
            style="-",
            size=5.0,
            linewidth=2.0,
            preprocess=self._identity_preprocess(),
            color_selection=ColorSelection("#112233"),
        )
        draw_idle = Mock()
        self.canvas.fig.canvas.draw_idle = draw_idle

        with self.window.repository.mutate(
            TableChangeSet(
                self.canvas.project_id,
                changed_columns={self.x_ref},
                reason="test-shared-x",
            )
        ):
            self.sheet.set_cell(1, self.x_ref.column_id, 10.0)

        for line in result.artists:
            self.assertEqual(float(line.get_xdata()[1]), 10.0)
        draw_idle.assert_called_once_with()

    def test_invalid_interpolation_preflight_creates_nothing(self):
        axes_id = self.canvas.current_axes_component_id
        original_selection = self.canvas.current_component_id
        with self.assertRaisesRegex(ValueError, "Bad Y"):
            self.canvas.add_interpolate_curves(
                self.x_ref,
                (self.y1_ref, self.bad_ref),
                method=list(interpolate_dict)[2],
                samples=32,
                preprocess=self._identity_preprocess(),
                color_selection=self._palette_selection(),
            )

        self.assertEqual(
            self.canvas.component_registry.query(
                role=ComponentRole.INTERPOLATION
            ),
            [],
        )
        self.assertEqual(len(self.canvas.current_axes.lines), 0)
        self.assertEqual(self.canvas.current_component_id, original_selection)
        self.assertIsNone(
            self.canvas.axes_commands.cycle_state(axes_id).active_palette
        )
        self.assertEqual(self.window.color_library.recent_colors, [])

    def test_second_registration_failure_rolls_back_entire_batch(self):
        registry = self.canvas.component_registry
        axes_controller = self.canvas.current_axes_controller
        original_axes_state = axes_controller.state
        original_selection = self.canvas.current_component_id
        event_batches = []
        unsubscribe = registry.subscribe_batches(event_batches.append)
        original_register = self.canvas._register_chart_controller
        created_ids = []
        calls = 0

        def fail_second(*args, **kwargs):
            nonlocal calls
            calls += 1
            created_ids.append(args[1])
            if calls == 2:
                raise RuntimeError("synthetic second registration failure")
            return original_register(*args, **kwargs)

        try:
            with patch.object(
                self.canvas,
                "_register_chart_controller",
                side_effect=fail_second,
            ):
                with self.assertRaisesRegex(RuntimeError, "second registration"):
                    self.canvas.add_plots(
                        self.x_ref,
                        (self.y1_ref, self.y2_ref),
                        style="-",
                        size=5.0,
                        linewidth=2.0,
                        preprocess=self._identity_preprocess(),
                        color_selection=self._palette_selection(),
                    )
            self.assertEqual(len(self.canvas.current_axes.lines), 0)
            self.assertEqual(
                registry.query(role=ComponentRole.DATA_PLOT),
                [],
            )
            for component_id in created_ids:
                self.assertNotIn(component_id, registry)
                self.assertIsNone(
                    registry.locator.bound_target(component_id)
                )
                self.assertIsNone(
                    self.canvas.component_editor_manager.editor(component_id)
                )
            self.assertEqual(axes_controller.state, original_axes_state)
            self.assertEqual(self.canvas.current_component_id, original_selection)
            self.assertEqual(event_batches, [])
            self.assertEqual(self.window.color_library.recent_colors, [])
        finally:
            unsubscribe()

    def test_post_autoscale_failure_restores_watched_axes(self):
        registry = self.canvas.component_registry
        axes = self.canvas.current_axes
        axes.set_xlim(-10.0, 10.0)
        axes.set_ylim(-20.0, 20.0)
        self.canvas.current_axes_controller.sync_from_target(strict=True)
        original_state = self.canvas.current_axes_controller.state
        original_flush = registry.flush_updates

        def fail_after_flush():
            original_flush()
            raise RuntimeError("synthetic post-autoscale failure")

        with patch.object(registry, "flush_updates", side_effect=fail_after_flush):
            with self.assertRaisesRegex(RuntimeError, "post-autoscale"):
                self.canvas.add_plots(
                    self.x_ref,
                    (self.y1_ref, self.y2_ref),
                    style="-",
                    size=5.0,
                    linewidth=2.0,
                    preprocess=self._identity_preprocess(),
                    color_selection=self._palette_selection(),
                )

        self.assertEqual(len(self.canvas.current_axes.lines), 0)
        self.assertEqual(self.canvas.current_axes_controller.state, original_state)
        np.testing.assert_allclose(axes.get_xlim(), (-10.0, 10.0))
        np.testing.assert_allclose(axes.get_ylim(), (-20.0, 20.0))

    def test_color_cycle_commit_failure_rolls_back_every_created_component(self):
        axes_controller = self.canvas.current_axes_controller
        original_set_property = axes_controller.set_property

        def reject_cycle(key, value):
            if key == "color_cycle":
                return SimpleNamespace(
                    ok=False,
                    message="synthetic color cycle failure",
                )
            return original_set_property(key, value)

        with patch.object(
            axes_controller,
            "set_property",
            side_effect=reject_cycle,
        ):
            with self.assertRaisesRegex(ValueError, "color cycle failure"):
                self.canvas.add_plots(
                    self.x_ref,
                    (self.y1_ref, self.y2_ref),
                    style="-",
                    size=5.0,
                    linewidth=2.0,
                    preprocess=self._identity_preprocess(),
                    color_selection=self._palette_selection(),
                )

        self.assertEqual(len(self.canvas.current_axes.lines), 0)
        self.assertEqual(
            self.canvas.component_registry.query(
                role=ComponentRole.DATA_PLOT
            ),
            [],
        )
        self.assertIsNone(
            self.canvas.axes_commands.cycle_state(
                self.canvas.current_axes_component_id
            ).active_palette
        )
        self.assertEqual(self.window.color_library.recent_colors, [])

    def test_second_inspector_prepare_failure_removes_first_inspector(self):
        original_prepare = self.canvas._prepare_created_component
        prepared_ids = []

        def fail_second(controller, transaction):
            prepared_ids.append(controller.component_id)
            if len(prepared_ids) == 2:
                raise RuntimeError("synthetic Inspector construction failure")
            return original_prepare(controller, transaction)

        with patch.object(
            self.canvas,
            "_prepare_created_component",
            side_effect=fail_second,
        ):
            with self.assertRaisesRegex(RuntimeError, "Inspector construction"):
                self.canvas.add_scatters(
                    self.x_ref,
                    (self.y1_ref, self.y2_ref),
                    size=20.0,
                    marker="o",
                    preprocess=self._identity_preprocess(),
                    color_selection=self._palette_selection(),
                )

        self.assertEqual(len(self.canvas.current_axes.collections), 0)
        self.assertEqual(
            self.canvas.component_registry.query(
                role=ComponentRole.SCATTER
            ),
            [],
        )
        for component_id in prepared_ids:
            self.assertIsNone(
                self.canvas.component_editor_manager.editor(component_id)
            )

    def test_dialog_reports_one_result_and_zero_selection_disables_create(self):
        dialog = PyPlotDialog("Plot", self.window.figure_window)
        events = []
        status_messages.set_status_handler(
            lambda message, level: events.append((message, level))
        )
        try:
            dialog.data_reference_input.clear_all()
            self.assertFalse(dialog.ok_button.isEnabled())
            dialog.data_reference_input.set_x_ref(self.x_ref)
            selected = {self.y1_ref, self.y2_ref}
            for index in range(
                dialog.data_reference_input.y_data_input.count()
            ):
                item = (
                    dialog.data_reference_input.y_data_input.model().item(index)
                )
                if item.data(Qt.UserRole) in selected:
                    item.setCheckState(Qt.Checked)
            self.assertTrue(dialog.ok_button.isEnabled())
            dialog.accept()
            self.assertEqual(dialog.result(), QDialog.Accepted)
            self.assertEqual(len(events), 1)
            self.assertEqual(events[0][1], "warning")
            self.assertIn("Created 2 Plot curves", events[0][0])
        finally:
            dialog.close()
            dialog.deleteLater()

    def test_interpolation_dialog_failure_is_one_red_message_and_stays_open(self):
        dialog = PyInterpolationDialog(
            "Interpolation", self.window.figure_window
        )
        events = []
        status_messages.set_status_handler(
            lambda message, level: events.append((message, level))
        )
        try:
            dialog.data_reference_input.set_refs(
                self.x_ref,
                (self.y1_ref, self.bad_ref),
            )
            dialog.accept()
            self.assertNotEqual(dialog.result(), QDialog.Accepted)
            self.assertEqual(len(events), 1)
            self.assertEqual(events[0][1], "error")
            self.assertIn("Bad Y", events[0][0])
            self.assertEqual(
                self.canvas.component_registry.query(
                    role=ComponentRole.INTERPOLATION
                ),
                [],
            )
        finally:
            dialog.reject()
            dialog.deleteLater()

    def test_batch_components_roundtrip_without_batch_schema_fields(self):
        result = self.canvas.add_plots(
            self.x_ref,
            (self.y1_ref, self.y2_ref),
            style="-",
            size=5.0,
            linewidth=2.0,
            preprocess={"x_expression": "x", "y_expression": "y/x"},
            color_selection=self._palette_selection(),
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "batch.mygui.json"
            save_project_snapshot(path, self.window.figure_window)
            snapshot = load_project_file(path)
            self.assertEqual(snapshot["schema_version"], 14)
            def keys(value):
                if isinstance(value, dict):
                    for key, child in value.items():
                        yield str(key)
                        yield from keys(child)
                elif isinstance(value, list):
                    for child in value:
                        yield from keys(child)

            self.assertFalse(
                any("batch" in key.casefold() for key in keys(snapshot))
            )

            loaded = MainWindow()
            try:
                restore_project_snapshot(
                    path,
                    loaded.table,
                    loaded.figure_window,
                )
                restored = loaded.figure_window.current_canva
                controllers = restored.component_registry.query(
                    role=ComponentRole.DATA_PLOT
                )
                self.assertEqual(
                    [controller.component_id for controller in controllers],
                    list(result.component_ids),
                )
                self.assertEqual(
                    [controller.state.data["preprocess"] for controller in controllers],
                    [
                        {"x_expression": "x", "y_expression": "y/x"},
                        {"x_expression": "x", "y_expression": "y/x"},
                    ],
                )
            finally:
                loaded.close()
                self.app.processEvents()


if __name__ == "__main__":
    unittest.main()
