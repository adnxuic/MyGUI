import os
import tempfile
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QWidget

from main import MainWindow
from mygui.database import ColumnRef
from mygui.figuremodify.components import (
    ComponentKind,
    ComponentRole,
    ComponentState,
    ObserverFailure,
    TickLabelGroupController,
)
from mygui.tex_config import TexRuntimeChange, TexRuntimeState
from tests.axes_helpers import create_regular_axes


class PyFigureCanvasBranchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.window = MainWindow()
        self.canvas = self.window.figure_window.add_figure(
            width=4, height=3, dpi=100, style="default", canva_name="TestProject"
        )
        self.project_id = self.canvas.project_id
        self.app.processEvents()

    def tearDown(self):
        self.window.close_without_prompt()
        self.window.deleteLater()
        self.app.processEvents()
        self.directory.cleanup()

    def _setup_sheet_columns(self):
        sheet = self.window.table.current_subtable().get_table(0).table_model.sheet
        sheet.set_block(0, 0, [
            [10, "label_a", "2026-08-01", 100],
            [20, "label_b", "2026-08-02", 200],
            [30, "label_c", "2026-08-03", 300],
        ])
        num_col_1 = ColumnRef(self.project_id, sheet.id, sheet.columns[0].id)
        text_col = ColumnRef(self.project_id, sheet.id, sheet.columns[1].id)
        date_col = ColumnRef(self.project_id, sheet.id, sheet.columns[2].id)
        num_col_2 = ColumnRef(self.project_id, sheet.id, sheet.columns[3].id)
        return sheet, num_col_1, text_col, date_col, num_col_2

    def test_normalize_batch_refs_validation_branches(self):
        sheet, num_col_1, text_col, date_col, num_col_2 = self._setup_sheet_columns()

        # 1. Invalid x_ref type
        with self.assertRaisesRegex(ValueError, "Please select X Data."):
            self.canvas._normalize_batch_refs("not_a_col_ref", (num_col_2,))

        # 2. Empty y_refs
        with self.assertRaisesRegex(ValueError, "Please select at least one Y Data column."):
            self.canvas._normalize_batch_refs(num_col_1, ())

        # 3. Invalid element in y_refs
        with self.assertRaisesRegex(ValueError, "Every Y Data selection must be a column reference."):
            self.canvas._normalize_batch_refs(num_col_1, (num_col_2, "bad_ref"))

        # 4. Duplicate y_refs
        with self.assertRaisesRegex(ValueError, "Duplicate Y Data selections are not allowed."):
            self.canvas._normalize_batch_refs(num_col_1, (num_col_2, num_col_2))

        # 5. Foreign project x_ref
        foreign_x = ColumnRef("other_proj", sheet.id, sheet.columns[0].id)
        with self.assertRaisesRegex(ValueError, "X Data must belong to the current project."):
            self.canvas._normalize_batch_refs(foreign_x, (num_col_2,))

        # 6. Missing x_ref from repository
        missing_x = ColumnRef(self.project_id, sheet.id, "missing_col_id")
        with self.assertRaisesRegex(ValueError, "X Data column was removed."):
            self.canvas._normalize_batch_refs(missing_x, (num_col_2,))

        # 7. Non-numeric / non-datetime x_ref (TEXT)
        with self.assertRaisesRegex(ValueError, "X Data must be numeric or date/time."):
            self.canvas._normalize_batch_refs(text_col, (num_col_2,))

        # 8. Foreign project y_ref
        foreign_y = ColumnRef("other_proj", sheet.id, sheet.columns[3].id)
        with self.assertRaisesRegex(ValueError, "Y Data selection 1 must belong to the current project."):
            self.canvas._normalize_batch_refs(num_col_1, (foreign_y,))

        # 9. Missing y_ref from repository
        missing_y = ColumnRef(self.project_id, sheet.id, "missing_col_id")
        with self.assertRaisesRegex(ValueError, "Y Data selection 1 was removed."):
            self.canvas._normalize_batch_refs(num_col_1, (missing_y,))

        # 10. Non-numeric y_ref (TEXT)
        with self.assertRaisesRegex(ValueError, "Y Data selection 1 must be numeric."):
            self.canvas._normalize_batch_refs(num_col_1, (text_col,))

        # Valid numeric & datetime
        norm_x, norm_y = self.canvas._normalize_batch_refs(num_col_1, (num_col_2,))
        self.assertEqual(norm_x, num_col_1)
        self.assertEqual(norm_y, (num_col_2,))

        norm_date_x, norm_y = self.canvas._normalize_batch_refs(date_col, (num_col_2,))
        self.assertEqual(norm_date_x, date_col)

    def test_batch_series_labels(self):
        sheet, num_col_1, _text_col, _date_col, num_col_2 = self._setup_sheet_columns()
        labels = self.canvas._batch_series_labels((num_col_1, num_col_2))
        self.assertEqual(len(labels), 2)
        self.assertEqual(labels[0], sheet.columns[0].name)
        self.assertEqual(labels[1], sheet.columns[3].name)

    def test_tex_runtime_changed_branches(self):
        change = TexRuntimeChange(
            before=TexRuntimeState(enabled=False, preamble=""),
            after=TexRuntimeState(enabled=True, preamble=""),
        )

        # 1. When disposed, returns None
        self.canvas._disposed = True
        self.assertIsNone(self.canvas._tex_runtime_changed(change))
        self.canvas._disposed = False

        # 2. When text_render_service returns committed=False, discards and returns error message
        with mock.patch.object(
            self.canvas.text_render_service,
            "apply_tex_availability",
            return_value=SimpleNamespace(committed=False, message="TeX engine missing"),
        ):
            with mock.patch.object(self.canvas.message_presenter, "discard_pending") as mock_discard:
                res = self.canvas._tex_runtime_changed(change)
                self.assertEqual(res, "TeX engine missing")
                mock_discard.assert_called_once()

        # 3. When text_render_service returns committed=True, returns None
        with mock.patch.object(
            self.canvas.text_render_service,
            "apply_tex_availability",
            return_value=SimpleNamespace(committed=True, message=None),
        ):
            res = self.canvas._tex_runtime_changed(change)
            self.assertIsNone(res)

    def test_eligible_colorbar_sources(self):
        # When no axes is selected
        self.canvas.current_axes_component_id = None
        self.assertEqual(self.canvas.eligible_colorbar_sources(), ())

        # With regular axes created
        create_regular_axes(self.canvas)
        sources = self.canvas.eligible_colorbar_sources()
        self.assertIsInstance(sources, tuple)

    def test_canvas_replays_nonstandard_tick_styles_before_draw(self):
        create_regular_axes(self.canvas)
        labels = next(
            controller
            for controller in self.canvas.component_registry.query(
                kind=ComponentKind.TICK_LABEL_GROUP
            )
            if isinstance(controller, TickLabelGroupController)
            and controller.state.selector == {"axis": "x", "level": "major"}
        )
        bbox = {
            "enabled": True,
            "boxstyle": "round",
            "facecolor": "#ffffff",
            "edgecolor": "#000000",
            "linewidth": 1.0,
            "line_pattern": {"kind": "preset", "value": "-"},
            "alpha": None,
            "fill": True,
            "hatch": None,
            "pad": 0.3,
        }
        self.assertTrue(labels.set_property("fontweight", "bold").ok)
        self.assertTrue(labels.set_property("bbox", bbox).ok)
        axis = labels.resolve_target()

        axis.reset_ticks()
        recreated = axis.get_major_ticks()
        self.assertTrue(recreated)
        self.assertTrue(
            all(tick.label1.get_bbox_patch() is None for tick in recreated)
        )

        self.canvas.canva.draw()

        for tick in axis.get_major_ticks():
            for label in (tick.label1, tick.label2):
                self.assertEqual(label.get_fontweight(), "bold")
                self.assertIsNotNone(label.get_bbox_patch())

    def test_export_figure_and_save(self):
        # 1. export_figure type check
        with self.assertRaisesRegex(TypeError, "export_figure requires a FigureExportRequest"):
            self.canvas.export_figure("invalid_request")

        # 2. save with default dpi
        out_file = Path(self.directory.name) / "save_default.png"
        self.canvas.save(out_file)
        self.assertTrue(out_file.exists())
        self.assertGreater(out_file.stat().st_size, 0)

        # 3. save with explicit dpi
        out_file_dpi = Path(self.directory.name) / "save_dpi.png"
        self.canvas.save(out_file_dpi, dpi=120)
        self.assertTrue(out_file_dpi.exists())
        self.assertGreater(out_file_dpi.stat().st_size, 0)

    def test_observer_failure_queue_and_flush(self):
        # 1. Disposed canvas does not flush
        self.canvas._disposed = True
        self.canvas._observer_failures = [SimpleNamespace(component_id=None, source="src", phase="ph", error="err")]
        self.canvas._flush_observer_failures()
        self.canvas._disposed = False

        # 2. Empty failures does nothing
        self.canvas._observer_failures = []
        self.canvas._flush_observer_failures()

        # 3. Non-empty failures with component_id=None
        failure_no_comp = SimpleNamespace(component_id=None, source="src1", phase="ph1", error="err1")
        self.canvas._queue_observer_failures([failure_no_comp])
        with mock.patch("mygui.status_messages.show_warning") as mock_warn:
            self.canvas._flush_observer_failures()
            mock_warn.assert_called_once()
            self.assertIn("source=src1", mock_warn.call_args[0][0])
            self.assertNotIn("component=", mock_warn.call_args[0][0])

        # 4. Non-empty failures with component_id present
        failure_with_comp = SimpleNamespace(component_id="comp_1", source="src2", phase="ph2", error="err2")
        self.canvas._queue_observer_failures([failure_with_comp])
        with mock.patch("mygui.status_messages.show_warning") as mock_warn:
            self.canvas._flush_observer_failures()
            mock_warn.assert_called_once()
            self.assertIn("component=comp_1", mock_warn.call_args[0][0])

    def test_axes_selection_and_color_cycle_branches(self):
        self.canvas.current_axes_component_id = None
        self.assertIsNone(self.canvas.current_axes)
        self.assertFalse(self.canvas.has_current_axes)
        self.assertIsNone(self.canvas.current_axes_controller)

        with self.assertRaisesRegex(ValueError, "Select an axes before choosing a chart color."):
            self.canvas.creation_color_cycle()

        with self.assertRaisesRegex(ValueError, "Select an axes before adding a chart."):
            self.canvas._claim_color_order(preferred=None)

        self.assertEqual(self.canvas._claim_color_order(preferred=5), 5)
        self.assertEqual(self.canvas._claim_color_order(preferred=-3), 0)

    def test_document_dpi_and_component_style_fallbacks(self):
        # When reading root state raises, falls back to internal attributes
        with mock.patch.object(self.canvas.component_registry, "get", side_effect=KeyError("root missing")):
            self.assertEqual(self.canvas.document_dpi, self.canvas._document_dpi)
            self.assertEqual(self.canvas.component_style, "default")

    def test_update_current_axes_and_set_by_index_errors(self):
        # 1. Non-string component_id
        with self.assertRaisesRegex(TypeError, "Current axes must be selected by component ID."):
            self.canvas.update_current_axes(12345)

        # 2. Non-AxesController component (root is FigureController)
        with self.assertRaisesRegex(TypeError, "The selected component is not an Axes."):
            self.canvas.update_current_axes(self.canvas.root_component_id)

        # 3. Invalid axes index
        with self.assertRaisesRegex(IndexError, "Invalid axes index: 999"):
            self.canvas.set_current_axes_by_index(999)

    def test_materializer_type_mismatch_branches(self):
        # 1. Colorbar materializer error paths
        dummy_state = ComponentState(
            id="dummy_1",
            kind=ComponentKind.LINE,
            role=ComponentRole.LINE,
            parent_id=self.canvas.root_component_id,
            order=0,
        )
        with self.assertRaisesRegex(ValueError, "Colorbar materializer requires a Colorbar state."):
            self.canvas._materialize_colorbar(dummy_state, None)

        cbar_bad_source_state = ComponentState(
            id="cbar_1",
            kind=ComponentKind.COLORBAR,
            role=ComponentRole.COLORBAR,
            parent_id=self.canvas.root_component_id,
            order=0,
            data={"source_component_id": "non_existent_source_id"},
        )
        with self.assertRaisesRegex(ValueError, "Colorbar source component is unavailable."):
            self.canvas._materialize_colorbar(cbar_bad_source_state, None)

        # 2. Reference Marks materializer error path
        with self.assertRaisesRegex(ValueError, "Reference Marks materializer requires Reflection Positions."):
            self.canvas._materialize_reference_marks(dummy_state, None)

        # 3. Reference Line materializer error path
        with self.assertRaisesRegex(ValueError, "Reference Line materializer requires a Reference Line state."):
            self.canvas._materialize_reference_line(dummy_state, None)

        # 4. Reference Band materializer error path
        with self.assertRaisesRegex(ValueError, "Reference Band materializer requires a Reference Band state."):
            self.canvas._materialize_reference_band(dummy_state, None)

        # 5. Zoom in axes materializer error path
        with self.assertRaisesRegex(ValueError, "Zoom materializer requires an in-axes Zoom state."):
            self.canvas._materialize_zoom_in_axes(dummy_state, None)

        # 6. Image in axes materializer error path
        with self.assertRaisesRegex(ValueError, "Image materializer requires an in-axes Image state."):
            self.canvas._materialize_image_in_axes(dummy_state, None)

        # 7. Text materializer with tuple/list fontfamily
        text_state = ComponentState(
            id="text_item",
            kind=ComponentKind.TEXT,
            role=ComponentRole.TEXT,
            parent_id=self.canvas.root_component_id,
            order=0,
            properties={
                "position": (0.5, 0.5),
                "fontfamily": ["Arial", "sans-serif"],
                "fontsize": 12.0,
                "text": "Hello",
                "usetex": False,
            },
        )
        with mock.patch.object(self.canvas, "add_global_text") as mock_add_text:
            self.canvas._materialize_text(text_state, None)
            mock_add_text.assert_called_once()
            self.assertEqual(mock_add_text.call_args[1]["fontfamily"], "Arial")

    def test_data_dependents_and_restore_component_state_errors(self):
        # 1. remove_data_dependents with empty component_ids
        empty_snapshot = SimpleNamespace(component_states=())
        self.assertTrue(self.canvas.remove_data_dependents(empty_snapshot))

        # 2. prepare_data_dependents with missing component in registry
        missing_snapshot = SimpleNamespace(component_states=(SimpleNamespace(id="missing_comp_1"),))
        with self.assertRaisesRegex(ValueError, "Dependent components changed before deletion: missing_comp_1"):
            self.canvas.prepare_data_dependents(missing_snapshot)

        # 3. _restore_component_state where parent is not an AxesController
        self.canvas.add_global_text(0.5, 0.5, "Label", "Arial", 12.0)
        text_ctrl = self.canvas.component_registry.query(role=ComponentRole.TEXT)[0]
        state_bad_parent = ComponentState(
            id="plot_x",
            kind=ComponentKind.LINE,
            role=ComponentRole.LINE,
            parent_id=text_ctrl.component_id,
            order=0,
        )
        with self.assertRaisesRegex(ValueError, "requires an Axes parent."):
            self.canvas._restore_component_state(state_bad_parent)

    def test_popout_disposed_and_restore_content_mismatch(self):
        # 1. open_canvas_window when disposed returns None
        self.canvas._disposed = True
        self.assertIsNone(self.canvas.open_canvas_window())
        self.canvas._disposed = False

        # 2. _restore_canvas_from_popout when release_content returns unknown widget
        mock_window = mock.MagicMock()
        mock_window.canvas_returned = False
        fake_content = QWidget()
        mock_window.release_content.return_value = fake_content
        with self.assertRaisesRegex(RuntimeError, "The Canvas popout returned unknown content."):
            self.canvas._restore_canvas_from_popout(mock_window)
        fake_content.deleteLater()

    def test_selection_repair_to_axes_or_root(self):
        self.canvas._disposed = False
        with self.assertRaises(AttributeError):
            self.canvas.current_component_id = "external-write"
        self.canvas._current_component_id = "non_existent_id"
        self.canvas.current_axes_component_id = None
        self.canvas._repair_component_selection()
        self.assertEqual(self.canvas.current_component_id, self.canvas.root_component_id)

    def test_component_snapshot_falls_back_to_cached_state(self):
        create_regular_axes(self.canvas)
        controller = next(iter(self.canvas.component_registry.query()))
        with mock.patch.object(
            controller,
            "read_state",
            side_effect=RuntimeError("synthetic snapshot read failure"),
        ):
            snapshot = self.canvas.component_snapshot()
        self.assertEqual(snapshot["root_component_id"], self.canvas.root_component_id)
        self.assertTrue(snapshot["components"])

    def test_add_component_line_and_curve_publish_color_commit(self):
        create_regular_axes(self.canvas)
        restored = self.canvas.add_component_line(
            [0, 1],
            [0, 1],
            "-",
            "black",
            "Restored line",
        )
        self.assertIsNotNone(restored)
        curve = self.canvas.add_curve("x", 0.0, 1.0, "-", "red", "Curve")
        self.assertIsNotNone(curve)
        self.canvas.current_axes_component_id = None
        with self.assertRaisesRegex(ValueError, "Select an axes"):
            self.canvas.add_in_axes(object())

    def test_constructor_selection_and_deletion_fallback_error_branches(self):
        from mygui.figuremodify.component_services import DeletionRequest
        from mygui.widgets.figure_canvas.py_figure_canves import PyFigureCanvas

        with self.assertRaisesRegex(ValueError, "repository and project id"):
            PyFigureCanvas()
        with self.assertRaisesRegex(ValueError, "project metadata"):
            PyFigureCanvas(
                repository=self.window.repository,
                project_id=self.project_id,
            )
        with self.assertRaisesRegex(ValueError, "ColorLibrary"):
            PyFigureCanvas(
                repository=self.window.repository,
                project_id=self.project_id,
                project_metadata=self.canvas.project_metadata,
            )
        with self.assertRaisesRegex(ValueError, "unavailable"):
            self.canvas.commit_prepared_selection(
                "missing-component",
                axes_component_id=None,
            )
        was_disposed = self.canvas._disposed
        self.canvas._disposed = True
        self.canvas.dispose()
        self.canvas._disposed = was_disposed
        create_regular_axes(self.canvas)
        with self.assertRaisesRegex(ValueError, "Axes selection"):
            self.canvas.commit_prepared_selection(
                self.canvas.root_component_id,
                axes_component_id="missing-axes",
            )
        self.assertFalse(self.canvas.select_component("missing-component"))
        previous = self.canvas.current_component_id
        with mock.patch.object(
            self.canvas.figure_inspector,
            "show_component",
            return_value=False,
        ):
            self.assertFalse(
                self.canvas.select_component(self.canvas.root_component_id)
            )
        self.assertEqual(self.canvas.current_component_id, previous)

        returned = SimpleNamespace(canvas_returned=True)
        self.canvas._restore_canvas_from_popout(returned)
        unknown = mock.Mock()
        unknown.canvas_returned = False
        unknown.release_content.return_value = object()
        with self.assertRaisesRegex(RuntimeError, "unknown content"):
            self.canvas._restore_canvas_from_popout(unknown)
        focus_window = mock.Mock()
        focus_window.canvas_returned = False
        focus_window.release_content.return_value = None
        focus_target = mock.Mock()
        focus_target.setFocus.side_effect = RuntimeError("widget gone")
        self.canvas._canvas_popout_window = focus_window
        self.canvas._canvas_focus_return = focus_target
        self.canvas._restore_canvas_from_popout(focus_window)
        self.assertIsNone(self.canvas._canvas_popout_window)
        self.assertIsNone(self.canvas._canvas_focus_return)

        had_draw_pending = hasattr(self.canvas.canva, "_draw_pending")
        if had_draw_pending:
            delattr(self.canvas.canva, "_draw_pending")
        self.canvas.cancel_pending_draw()
        if had_draw_pending:
            self.canvas.canva._draw_pending = False

        failure = ObserverFailure(
            "registry",
            "publish",
            RuntimeError("observer boom"),
            "cid",
        )
        self.canvas._queue_observer_failures((failure,))
        self.canvas._queue_observer_failures((failure,))
        self.canvas._flush_observer_failures()
        self.canvas._flush_observer_failures()
        self.canvas._observer_failures.append(failure)
        self.canvas._disposed = True
        self.canvas._flush_observer_failures()
        self.canvas._disposed = False
        self.canvas._observer_failures.clear()
        self.canvas._focus_annotation_editor("missing-annotation")
        with self.assertRaises(TypeError):
            self.canvas.export_figure(object())

        first = self.canvas.add_curve("x", 0.0, 1.0, "-", "red", "one")
        second = self.canvas.add_curve("x", 0.0, 1.0, "-", "blue", "two")
        del first, second
        curve_ids = [
            controller.component_id
            for controller in self.canvas.component_registry.query()
            if controller.state.role is ComponentRole.FUNCTION_CURVE
        ]
        first_id, second_id = curve_ids[0], curve_ids[1]
        coordinator = self.canvas.deletion_coordinator
        self.canvas._current_component_id = None
        fallback = coordinator._fallback_id(
            DeletionRequest((first_id,)),
            {first_id},
        )
        self.assertTrue(fallback)
        self.assertFalse(
            coordinator.delete(
                DeletionRequest((first_id,)),
                fallback_id=first_id,
                present_result=False,
            )
        )
        self.assertIsNotNone(coordinator.last_outcome)
        self.assertIn("unavailable", coordinator.last_outcome.message)
        self.assertIn(first_id, self.canvas.component_registry)
        self.assertIn(second_id, self.canvas.component_registry)

        def fail_then_restore(component_id):
            if component_id == self.canvas.root_component_id:
                raise RuntimeError("show failed")
            raise RuntimeError("restore failed")

        self.canvas.select_component(first_id)
        with mock.patch.object(
            self.canvas.figure_inspector,
            "show_component",
            side_effect=fail_then_restore,
        ):
            self.assertFalse(
                self.canvas.select_component(self.canvas.root_component_id)
            )

        with mock.patch.object(
            self.canvas.figure_inspector,
            "show_component",
            return_value=False,
        ):
            self.assertFalse(
                coordinator.delete(
                    DeletionRequest((second_id,)),
                    fallback_id=self.canvas.root_component_id,
                    present_result=False,
                )
            )
        self.assertIn(second_id, self.canvas.component_registry)

        with mock.patch.object(
            self.canvas.figure_inspector,
            "restore_component_inspector",
            side_effect=RuntimeError("restore handle failed"),
        ), mock.patch(
            "mygui.figuremodify.services.deletion.PreparedDeletion.execute",
            side_effect=RuntimeError("execute exploded"),
        ):
            self.assertFalse(
                coordinator.delete(
                    DeletionRequest((second_id,)),
                    fallback_id=self.canvas.root_component_id,
                    present_result=False,
                )
            )
        self.assertIn("unexpectedly", coordinator.last_outcome.message)
        self.assertIn(second_id, self.canvas.component_registry)

        _sheet, num_col_1, _text_col, _date_col, num_col_2 = self._setup_sheet_columns()
        with self.assertRaisesRegex(ValueError, "Unsupported fitting engine"):
            self.canvas.add_fit_curve(
                [0.0, 1.0],
                [0.0, 1.0],
                "red",
                "fit",
                num_col_1,
                num_col_2,
                engine="not-an-engine",
            )
        restored = self.canvas.add_fit_curve(
            [0.0, 1.0],
            [0.0, 1.0],
            "red",
            "fit",
            num_col_1,
            num_col_2,
            engine="Python",
            expression="this is not a valid fit expression !!!",
            x_start=0.0,
            x_stop=1.0,
        )
        self.assertIsNotNone(restored)
        self.assertIsNone(
            self.canvas.add_interpolate_curve(
                [0.0],
                [0.0],
                num_col_1,
                num_col_2,
                method="not-a-method",
            )
        )

        axes_id = self.canvas.current_axes_component_id
        with mock.patch.object(
            self.canvas.figure_inspector,
            "finalize_axes_inspector_removal",
            side_effect=RuntimeError("axes finalize boom"),
        ), mock.patch.object(
            self.canvas.figure_inspector,
            "finalize_component_inspector_removal",
            side_effect=RuntimeError("component finalize boom"),
        ), mock.patch.object(
            self.canvas.axes_layout_service,
            "restore_runtime_relationships",
            side_effect=RuntimeError("layout refresh boom"),
        ):
            self.assertTrue(
                coordinator.delete(
                    DeletionRequest((axes_id,)),
                    role_label="axes",
                    present_result=False,
                )
            )
        self.assertTrue(coordinator.last_outcome.notices)


if __name__ == "__main__":
    unittest.main()
