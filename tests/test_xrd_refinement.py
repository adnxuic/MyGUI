import inspect
import itertools
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import numpy as np

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication
from matplotlib.collections import LineCollection

from main import MainWindow
from mygui.database import ColumnRef, ColumnType
from mygui.figuremodify.components import ComponentKind, ComponentRole
from mygui.fullprof_prf import parse_fullprof_prf, parse_fullprof_prf_text
from mygui.project_io import restore_project_snapshot, save_project_snapshot
from mygui.widgets.title_bar.titlebar_dialog.axes_layout_input import (
    AxesLayoutInput,
)
from mygui.widgets.title_bar.titlebar_dialog.py_title_bar_dialog import (
    PyLayoutDialog,
)
from mygui.widgets.title_bar.titlebar_dialog.xrd_refinement_input import (
    FULLPROF_PRF_FILTER,
    XrdRefinementInput,
)
from mygui.xrd_refinement import (
    FIGURE_COMMAND_TEXT,
    TABLE_COMMAND_TEXT,
    XrdAppearanceConfig,
    XrdPlotAppearance,
    XrdPlotCreationError,
    XrdRefinementImportRequest,
    XrdRefinementImportService,
    XrdRefinementLegendSelection,
    XrdReflectionAppearance,
    XrdScatterAppearance,
    plan_xrd_table_import,
)


FIXTURE = Path(__file__).parent / "test_datas" / "XRD" / "YBCO.prf"
SMALL_PRF = """Demo Chi2: 2.5 CELL: 1 2 3 90 90 120 SPGR: P 1 TEMP: 25
1 3 1.54056 1.54439 0 0 0 0
3 0 0
2Theta Yobs Ycal Yobs-Ycal Backg Posr (hkl) K
10 100 90 -910 5
11 95 96 -1001 5.5
12 80 75 -995 6
15.1876 0 ( 0 0 2 )
15.2256 0 ( 0 0 2 )
15.2256 0 ( 1 0 1 )
"""


def small_result(source_name="Demo"):
    return parse_fullprof_prf_text(SMALL_PRF, source_name=source_name)


def column_by_name(sheet, name):
    return next(column for column in sheet.columns if column.name == name)


def column_values(sheet, name, count):
    column = column_by_name(sheet, name)
    return sheet.frame[column.id].iloc[:count].to_numpy(dtype=float)


class XrdWindowTestCase(unittest.TestCase):
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
            canva_name="XRD",
        )
        self.canvas = self.window.figure_window.current_canva

    def tearDown(self):
        self.window.close()
        self.app.processEvents()

    def main_residual_spec(self):
        value = AxesLayoutInput(
            color_library=self.window.figure_window.color_library,
            preset_key="main_residual",
        )
        try:
            return value.spec()
        finally:
            value.close()
            value.deleteLater()

    def execute(self, legend=None, result=None):
        request = XrdRefinementImportRequest(
            result or small_result(),
            legend or XrdRefinementLegendSelection(),
        )
        return XrdRefinementImportService(
            canvas=self.canvas,
            table_view=self.window.table,
        ).execute(self.main_residual_spec(), request)


class XrdRefinementDialogTests(XrdWindowTestCase):
    def test_xrd_tab_exists_only_for_main_residual_creation(self):
        dialogs = []
        try:
            for preset_key in (
                "single",
                "horizontal_compare",
                "vertical_stack",
                "grid_2x2",
                "grid_3x3",
                "primary_right_y",
            ):
                dialog = PyLayoutDialog(
                    figure_window=self.window.figure_window,
                    preset_key=preset_key,
                )
                dialogs.append(dialog)
                self.assertIsNone(dialog.xrd_input, preset_key)
                self.assertNotIn(
                    "XRD Refinement",
                    [
                        dialog.input.tabs.tabText(index)
                        for index in range(dialog.input.tabs.count())
                    ],
                    preset_key,
                )

            dialog = PyLayoutDialog(
                figure_window=self.window.figure_window,
                preset_key="main_residual",
            )
            dialogs.append(dialog)
            self.assertIsInstance(dialog.xrd_input, XrdRefinementInput)
            self.assertIn(
                "XRD Refinement",
                [dialog.input.tabs.tabText(index) for index in range(dialog.input.tabs.count())],
            )
        finally:
            for dialog in dialogs:
                dialog.close()
                dialog.deleteLater()

    def test_checkbox_off_keeps_the_existing_layout_creation_path(self):
        dialog = PyLayoutDialog(
            figure_window=self.window.figure_window,
            preset_key="main_residual",
        )
        original_sheets = tuple(self.canvas.repository.project(self.canvas.project_id).sheets)
        try:
            self.assertFalse(dialog.xrd_input.import_checkbox.isChecked())
            self.assertFalse(dialog.xrd_input.contents.isEnabled())
            self.assertIsNone(dialog.xrd_input.request())
            self.assertTrue(dialog.ok_button.isEnabled())
            dialog.accept()

            self.assertEqual(
                tuple(self.canvas.repository.project(self.canvas.project_id).sheets),
                original_sheets,
            )
            self.assertEqual(
                len(self.canvas.component_registry.query(kind=ComponentKind.AXES)),
                2,
            )
            stack = self.canvas.repository.undo_stack(self.canvas.project_id)
            self.assertEqual(stack.count(), 1)
            self.assertEqual(stack.text(0), "Create Axes Layout")
        finally:
            dialog.close()
            dialog.deleteLater()

    def test_browse_parses_immediately_and_invalid_input_disables_create(self):
        dialog = PyLayoutDialog(
            figure_window=self.window.figure_window,
            preset_key="main_residual",
        )
        try:
            dialog.xrd_input.import_checkbox.setChecked(True)
            self.assertFalse(dialog.ok_button.isEnabled())
            with mock.patch(
                "mygui.widgets.title_bar.titlebar_dialog."
                "xrd_refinement_input.QFileDialog.getOpenFileName",
                return_value=(str(FIXTURE), FULLPROF_PRF_FILTER),
            ) as get_file:
                dialog.xrd_input.browse()
            self.assertEqual(get_file.call_args.args[3], FULLPROF_PRF_FILTER)
            self.assertTrue(dialog.ok_button.isEnabled())
            self.assertEqual(dialog.xrd_input.title_value.text(), "YBCO")
            self.assertEqual(dialog.xrd_input.chi2_value.text(), "2.3177")
            self.assertEqual(dialog.xrd_input.profile_count_value.text(), "3803")
            self.assertEqual(dialog.xrd_input.reflection_count_value.text(), "338")
            self.assertIn("10.1442", dialog.xrd_input.range_value.text())

            dialog.xrd_input.set_file_path(FIXTURE.with_suffix(".txt"))
            self.assertFalse(dialog.ok_button.isEnabled())
            self.assertIn("Only FullProf .prf", dialog.xrd_input.validation_label.text())
        finally:
            dialog.close()
            dialog.deleteLater()

    def test_input_builds_typed_legend_request_without_state_mutation(self):
        before_components = self.canvas.component_snapshot()
        before_table = self.canvas.repository.snapshot(self.canvas.project_id)
        before_axes = tuple(self.canvas.fig.axes)
        before_history = self.canvas.repository.undo_stack(self.canvas.project_id).count()
        source = inspect.getsource(
            __import__(
                "mygui.widgets.title_bar.titlebar_dialog.xrd_refinement_input",
                fromlist=["XrdRefinementInput"],
            )
        )
        self.assertNotIn("import matplotlib", source.casefold())

        value = XrdRefinementInput()
        try:
            value.import_checkbox.setChecked(True)
            self.assertTrue(value.set_file_path(FIXTURE))
            value.observed_legend.setChecked(False)
            value.calculated_legend.setChecked(True)
            value.reflection_legend.setChecked(True)
            value.residual_legend.setChecked(True)
            request = value.request()
            self.assertIsNotNone(request)
            self.assertEqual(
                request.legend,
                XrdRefinementLegendSelection(False, True, True, True),
            )
        finally:
            value.close()
            value.deleteLater()

        self.assertEqual(self.canvas.component_snapshot(), before_components)
        self.assertEqual(
            self.canvas.repository.snapshot(self.canvas.project_id),
            before_table,
        )
        self.assertEqual(tuple(self.canvas.fig.axes), before_axes)
        self.assertEqual(
            self.canvas.repository.undo_stack(self.canvas.project_id).count(),
            before_history,
        )

    def test_property_buttons_disable_with_import_and_cancel_keeps_request(self):
        dialog = PyLayoutDialog(
            figure_window=self.window.figure_window,
            preset_key="main_residual",
        )
        try:
            xrd = dialog.xrd_input
            self.assertFalse(xrd.observed_property_button.isEnabled())
            self.assertFalse(xrd.calculated_property_button.isEnabled())
            self.assertFalse(xrd.reflection_property_button.isEnabled())
            self.assertFalse(xrd.residual_property_button.isEnabled())
            xrd.import_checkbox.setChecked(True)
            self.assertTrue(xrd.observed_property_button.isEnabled())
            self.assertEqual(xrd._appearance.observed.color, "#D62728")
            self.assertEqual(xrd._appearance.calculated.linewidth, 0.5)
            self.assertEqual(xrd._appearance.residual.linewidth, 0.2)
            self.assertEqual(xrd._appearance.reflection.baseline, 0.0375)
            before = xrd._appearance
            with mock.patch(
                "mygui.widgets.title_bar.titlebar_dialog.xrd_refinement_input.QDialog.exec",
                return_value=0,
            ):
                xrd._edit_observed_appearance()
                xrd._edit_calculated_appearance()
                xrd._edit_residual_appearance()
                xrd._edit_reflection_appearance()
            self.assertEqual(xrd._appearance, before)
        finally:
            dialog.close()
            dialog.deleteLater()


class XrdRefinementTableTests(XrdWindowTestCase):
    def test_complete_sheets_stable_refs_unique_names_and_undo_redo(self):
        result = small_result()
        service = XrdRefinementImportService(
            canvas=self.canvas,
            table_view=self.window.table,
        )
        plan = plan_xrd_table_import(
            self.canvas.repository,
            self.canvas.project_id,
            result,
        )
        publications = []
        self.canvas.repository.transaction_committed.connect(publications.append)
        service.import_table(plan)

        project = self.canvas.repository.project(self.canvas.project_id)
        self.assertEqual(
            [column.name for column in plan.profile_sheet.columns],
            ["2Theta", "Yobs", "Ycal", "Yobs-Ycal (PRF)", "Residual", "Backg"],
        )
        self.assertEqual(
            [column.name for column in plan.reflection_sheet.columns],
            ["2Theta", "h", "k", "l"],
        )
        self.assertTrue(
            all(
                column.type is ColumnType.NUMBER
                for sheet in (plan.profile_sheet, plan.reflection_sheet)
                for column in sheet.columns
            )
        )
        np.testing.assert_allclose(
            column_values(plan.profile_sheet, "Yobs-Ycal (PRF)", 3),
            [-910.0, -1001.0, -995.0],
        )
        np.testing.assert_allclose(
            column_values(plan.profile_sheet, "Residual", 3),
            [10.0, -1.0, 5.0],
        )
        np.testing.assert_allclose(
            column_values(plan.reflection_sheet, "2Theta", 3),
            [15.1876, 15.2256, 15.2256],
        )
        self.assertTrue(all(self.canvas.repository.has_ref(ref) for ref in plan.refs))
        self.assertEqual(len(publications), 1)
        self.assertTrue(publications[0].structure_changed)
        self.assertEqual(publications[0].reason, "xrd-refinement-import")

        second = plan_xrd_table_import(
            self.canvas.repository,
            self.canvas.project_id,
            result,
        )
        self.assertEqual(second.profile_sheet.name, "Demo Profile 2")
        self.assertEqual(second.reflection_sheet.name, "Demo Reflections 2")

        stack = self.canvas.repository.undo_stack(self.canvas.project_id)
        self.assertEqual(stack.count(), 1)
        self.assertEqual(stack.text(0), TABLE_COMMAND_TEXT)
        stack.undo()
        self.assertNotIn(plan.profile_sheet.id, project.sheets)
        self.assertNotIn(plan.reflection_sheet.id, project.sheets)
        stack.redo()
        self.assertIs(project.sheets[plan.profile_sheet.id], plan.profile_sheet)
        self.assertIs(project.sheets[plan.reflection_sheet.id], plan.reflection_sheet)
        self.assertTrue(all(self.canvas.repository.has_ref(ref) for ref in plan.refs))

    def test_second_sheet_failure_rolls_back_document_and_rejected_command(self):
        service = XrdRefinementImportService(
            canvas=self.canvas,
            table_view=self.window.table,
        )
        plan = plan_xrd_table_import(
            self.canvas.repository,
            self.canvas.project_id,
            small_result(),
        )
        project = self.canvas.repository.project(self.canvas.project_id)
        before = project.to_snapshot()
        real_add_sheet = project.add_sheet
        calls = 0

        def fail_second(*args, **kwargs):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise RuntimeError("injected second-sheet failure")
            return real_add_sheet(*args, **kwargs)

        with mock.patch.object(project, "add_sheet", side_effect=fail_second):
            with self.assertRaisesRegex(RuntimeError, "Table import was rejected"):
                service.import_table(plan)

        self.assertEqual(project.to_snapshot(), before)
        stack = self.canvas.repository.undo_stack(self.canvas.project_id)
        self.assertEqual(stack.count(), 0)
        self.assertEqual(stack.index(), 0)


class XrdRefinementFigureTests(XrdWindowTestCase):
    def test_component_mapping_data_residual_labels_and_managed_artists(self):
        result = small_result()
        outcome = self.execute(
            XrdRefinementLegendSelection(True, True, True, True),
            result,
        )
        registry = self.canvas.component_registry
        observed = registry.get(outcome.observed_id)
        calculated = registry.get(outcome.calculated_id)
        references = registry.get(outcome.reflection_positions_id)
        residual = registry.get(outcome.residual_id)

        self.assertEqual(
            (observed.state.parent_id, observed.state.kind, observed.state.role),
            (outcome.main_axes_id, ComponentKind.SCATTER, ComponentRole.SCATTER),
        )
        self.assertEqual(
            (calculated.state.parent_id, calculated.state.kind, calculated.state.role),
            (outcome.main_axes_id, ComponentKind.LINE, ComponentRole.DATA_PLOT),
        )
        self.assertEqual(
            (references.state.parent_id, references.state.kind, references.state.role),
            (
                outcome.main_axes_id,
                ComponentKind.REFERENCE_MARKS,
                ComponentRole.REFLECTION_POSITIONS,
            ),
        )
        self.assertEqual(
            (residual.state.parent_id, residual.state.kind, residual.state.role),
            (outcome.residual_axes_id, ComponentKind.LINE, ComponentRole.DATA_PLOT),
        )

        main_axes = registry.resolve_target(outcome.main_axes_id)
        residual_axes = registry.resolve_target(outcome.residual_axes_id)
        self.assertTrue(main_axes.get_shared_x_axes().joined(main_axes, residual_axes))
        main_subplot = registry.get(outcome.main_axes_id).state.data["subplot"]
        residual_subplot = registry.get(outcome.residual_axes_id).state.data["subplot"]
        self.assertEqual(
            (main_subplot["row"], main_subplot["column"], main_subplot["layer"]),
            (0, 0, "primary"),
        )
        self.assertEqual(
            (
                residual_subplot["row"],
                residual_subplot["column"],
                residual_subplot["layer"],
            ),
            (1, 0, "primary"),
        )
        source = inspect.getsource(XrdRefinementImportService)
        self.assertIn("axes_for_layout", source)
        self.assertNotIn("fig.axes[", source)

        offsets = np.asarray(observed.resolve_target().get_offsets(), dtype=float)
        np.testing.assert_allclose(offsets[:, 0], result.profile.two_theta)
        np.testing.assert_allclose(offsets[:, 1], result.profile.yobs)
        np.testing.assert_allclose(
            calculated.resolve_target().get_xdata(),
            result.profile.two_theta,
        )
        np.testing.assert_allclose(
            calculated.resolve_target().get_ydata(),
            result.profile.ycal,
        )
        np.testing.assert_allclose(
            residual.resolve_target().get_ydata(),
            result.profile.residual,
        )
        self.assertNotEqual(
            tuple(result.profile.residual),
            tuple(result.profile.prf_difference),
        )
        self.assertEqual(residual.state.data["y_ref"], outcome.table.residual_ref.to_dict())
        self.assertEqual(references.state.data["positions"], [])
        self.assertEqual(
            references.state.data["position_ref"],
            outcome.table.reflection_position_ref.to_dict(),
        )
        self.assertEqual(
            [float(segment[0][0]) for segment in references.resolve_target().get_segments()],
            [item.position for item in result.reflections],
        )
        main_controller = registry.get(outcome.main_axes_id)
        residual_controller = registry.get(outcome.residual_axes_id)
        self.assertEqual(main_controller.state.properties["y_lower_reserve"], 0.1)
        self.assertEqual(residual_controller.state.properties["y_lower_reserve"], 0.0)
        self.assertEqual(references.state.properties["baseline"], 0.0375)
        self.assertEqual(references.state.properties["height"], 0.025)
        self.assertAlmostEqual(
            float(references.resolve_target().get_segments()[0][0][1]),
            0.0375,
        )
        self.assertAlmostEqual(
            float(references.resolve_target().get_segments()[0][1][1]),
            0.0625,
        )

        self.assertEqual(main_axes.get_ylabel(), "Intensity (a.u.)")
        self.assertEqual(residual_axes.get_xlabel(), "2θ (°)")
        self.assertEqual(residual_axes.get_ylabel(), "Residual")
        self.assertEqual(len(registry.query(role=ComponentRole.DATA_PLOT)), 2)
        self.assertEqual(len(registry.query(role=ComponentRole.SCATTER)), 1)
        self.assertEqual(
            len(registry.query(role=ComponentRole.REFLECTION_POSITIONS)),
            1,
        )

        reference_target = references.resolve_target()
        managed_line_collections = [
            artist
            for axes in (main_axes, residual_axes)
            for artist in axes.collections
            if isinstance(artist, LineCollection)
        ]
        self.assertEqual(managed_line_collections, [reference_target])
        self.assertEqual(list(main_axes.lines), [calculated.resolve_target()])
        self.assertEqual(list(residual_axes.lines), [residual.resolve_target()])

        backg = column_by_name(outcome.table.profile_sheet, "Backg")
        backg_ref = ColumnRef(
            self.canvas.project_id,
            outcome.table.profile_sheet.id,
            backg.id,
        ).to_dict()
        self.assertNotIn(
            backg_ref,
            [controller.state.data.get("y_ref") for controller in registry.query()],
        )
        self.assertEqual(observed.state.properties["color"], "#d62728")
        self.assertEqual(observed.state.properties["edgecolor"], "#d62728")
        self.assertEqual(observed.state.properties["size"], 1.0)
        self.assertEqual(calculated.state.properties["color"], "#000000")
        self.assertEqual(calculated.state.properties["linewidth"], 0.5)
        self.assertEqual(residual.state.properties["color"], "#0000ff")
        self.assertEqual(residual.state.properties["linewidth"], 0.2)

    def test_user_appearance_override_and_reflection_table_refresh(self):
        appearance = XrdAppearanceConfig(
            observed=XrdScatterAppearance(
                color="#00AA00",
                edgecolor="#00AA00",
                marker="s",
                size=4.0,
            ),
            calculated=XrdPlotAppearance("#111111", 1.5, "--"),
            residual=XrdPlotAppearance("#123456", 0.8, ":"),
            reflection=XrdReflectionAppearance(
                label="Custom reflections",
                baseline=0.02,
                height=0.03,
            ),
        )
        request = XrdRefinementImportRequest(
            small_result("Override"),
            XrdRefinementLegendSelection(True, True, True, False),
            appearance=appearance,
        )
        outcome = XrdRefinementImportService(
            canvas=self.canvas,
            table_view=self.window.table,
        ).execute(self.main_residual_spec(), request)
        observed = self.canvas.component_registry.get(outcome.observed_id)
        calculated = self.canvas.component_registry.get(outcome.calculated_id)
        residual = self.canvas.component_registry.get(outcome.residual_id)
        references = self.canvas.component_registry.get(outcome.reflection_positions_id)
        self.assertEqual(observed.state.properties["color"], "#00aa00")
        self.assertEqual(observed.state.properties["size"], 4.0)
        self.assertEqual(calculated.state.properties["linewidth"], 1.5)
        self.assertEqual(residual.state.properties["linewidth"], 0.8)
        self.assertEqual(references.state.properties["label"], "Custom reflections")
        self.assertEqual(references.state.properties["baseline"], 0.02)
        sheet = self.canvas.repository.sheet(
            self.canvas.project_id,
            outcome.table.reflection_position_ref.sheet_id,
        )
        column = sheet.column(outcome.table.reflection_position_ref.column_id)
        frame = sheet.frame[column.id].copy()
        frame.iloc[0] = 40.0
        frame.iloc[1] = 41.0
        frame.iloc[2] = 42.0
        sheet.frame[column.id] = frame
        change = self.canvas.reference_marks_service.refresh(references)
        self.assertTrue(change.ok)
        xs = [
            float(segment[0][0])
            for segment in references.resolve_target().get_segments()
        ]
        self.assertEqual(xs[:3], [40.0, 41.0, 42.0])

    def test_every_legend_checkbox_combination_is_independent(self):
        for values in itertools.product((False, True), repeat=4):
            with self.subTest(selection=values):
                window = MainWindow()
                window.figure_window.add_figure(
                    width=4,
                    height=3,
                    dpi=100,
                    style="default",
                    canva_name="Legend",
                )
                canvas = window.figure_window.current_canva
                layout_input = AxesLayoutInput(
                    color_library=window.figure_window.color_library,
                    preset_key="main_residual",
                )
                try:
                    selection = XrdRefinementLegendSelection(*values)
                    outcome = XrdRefinementImportService(
                        canvas=canvas,
                        table_view=window.table,
                    ).execute(
                        layout_input.spec(),
                        XrdRefinementImportRequest(small_result(), selection),
                    )
                    registry = canvas.component_registry
                    main_legend = registry.find_one(
                        parent_id=outcome.main_axes_id,
                        kind=ComponentKind.LEGEND,
                        role=ComponentRole.LEGEND,
                        recursive=False,
                    )
                    residual_legend = registry.find_one(
                        parent_id=outcome.residual_axes_id,
                        kind=ComponentKind.LEGEND,
                        role=ComponentRole.LEGEND,
                        recursive=False,
                    )
                    expected_main = [
                        label
                        for include, label in zip(
                            values[:3],
                            ("Observed", "Calculated", "Reflection positions"),
                        )
                        if include
                    ]
                    expected_residual = ["Residual"] if values[3] else []
                    main_target = registry.resolve_target(main_legend.component_id)
                    residual_target = registry.resolve_target(residual_legend.component_id)
                    if expected_main:
                        self.assertIsNotNone(main_target)
                        self.assertEqual(
                            [text.get_text() for text in main_target.get_texts()],
                            expected_main,
                        )
                        self.assertTrue(main_target.get_visible())
                    elif main_target is not None:
                        self.assertEqual(main_target.get_texts(), [])
                        self.assertFalse(main_target.get_visible())
                    if expected_residual:
                        self.assertIsNotNone(residual_target)
                        self.assertEqual(
                            [text.get_text() for text in residual_target.get_texts()],
                            expected_residual,
                        )
                        self.assertTrue(residual_target.get_visible())
                    elif residual_target is not None:
                        self.assertEqual(residual_target.get_texts(), [])
                        self.assertFalse(residual_target.get_visible())
                    if main_target is not None and residual_target is not None:
                        self.assertIsNot(main_target, residual_target)
                    self.assertEqual(
                        main_legend.state.properties["visible"],
                        bool(expected_main),
                    )
                    self.assertEqual(
                        residual_legend.state.properties["visible"],
                        bool(expected_residual),
                    )
                    attached_main = registry.resolve_target(outcome.main_axes_id).get_legend()
                    attached_residual = registry.resolve_target(
                        outcome.residual_axes_id
                    ).get_legend()
                    self.assertIs(
                        attached_main,
                        main_target if expected_main else None,
                    )
                    self.assertIs(
                        attached_residual,
                        residual_target if expected_residual else None,
                    )
                finally:
                    layout_input.close()
                    layout_input.deleteLater()
                    window.close()
                    self.app.processEvents()

    def test_history_order_and_replay_preserve_cross_domain_dependency(self):
        outcome = self.execute()
        stack = self.canvas.repository.undo_stack(self.canvas.project_id)
        project = self.canvas.repository.project(self.canvas.project_id)
        self.assertEqual(stack.count(), 2)
        self.assertEqual(
            [stack.text(index) for index in range(stack.count())],
            [TABLE_COMMAND_TEXT, FIGURE_COMMAND_TEXT],
        )

        stack.undo()
        self.assertNotIn(outcome.observed_id, self.canvas.component_registry)
        self.assertIn(outcome.table.profile_sheet.id, project.sheets)
        self.assertIn(outcome.table.reflection_sheet.id, project.sheets)
        stack.undo()
        self.assertNotIn(outcome.table.profile_sheet.id, project.sheets)
        self.assertNotIn(outcome.table.reflection_sheet.id, project.sheets)

        stack.redo()
        self.assertTrue(self.canvas.repository.has_ref(outcome.table.residual_ref))
        stack.redo()
        self.assertIn(outcome.observed_id, self.canvas.component_registry)
        self.assertIn(outcome.residual_id, self.canvas.component_registry)
        residual = self.canvas.component_registry.resolve_target(outcome.residual_id)
        np.testing.assert_allclose(residual.get_ydata(), [10.0, -1.0, 5.0])

    def test_figure_failure_leaves_imported_data_but_no_partial_hierarchy(self):
        before_snapshot = self.canvas.component_snapshot()
        before_axes = tuple(self.canvas.fig.axes)
        before_layouts = self.canvas.axes_layout_service.layout_definitions()
        with mock.patch.object(
            self.canvas,
            "add_reference_marks",
            side_effect=RuntimeError("injected reflection failure"),
        ):
            with self.assertRaisesRegex(
                XrdPlotCreationError,
                "Data imported, plot creation failed",
            ):
                self.execute()

        self.assertEqual(self.canvas.component_snapshot(), before_snapshot)
        self.assertEqual(tuple(self.canvas.fig.axes), before_axes)
        self.assertEqual(
            self.canvas.axes_layout_service.layout_definitions(),
            before_layouts,
        )
        project = self.canvas.repository.project(self.canvas.project_id)
        self.assertIn("Demo Profile", [sheet.name for sheet in project.sheets.values()])
        self.assertIn(
            "Demo Reflections",
            [sheet.name for sheet in project.sheets.values()],
        )
        stack = self.canvas.repository.undo_stack(self.canvas.project_id)
        self.assertEqual(stack.count(), 1)
        self.assertEqual(stack.text(0), TABLE_COMMAND_TEXT)


class XrdRefinementRoundTripTests(XrdWindowTestCase):
    def test_saved_project_reopens_after_source_prf_is_deleted(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "Transient.prf"
            project_path = root / "xrd-project.mygui.json"
            source.write_text(SMALL_PRF, encoding="utf-8")
            result = parse_fullprof_prf(source)
            outcome = self.execute(result=result)
            save_project_snapshot(project_path, self.window.figure_window)
            source.unlink()

            payload = project_path.read_text(encoding="utf-8")
            self.assertNotIn(str(source), payload)
            self.assertNotIn(".prf", payload.casefold())

            restored_window = MainWindow()
            try:
                with mock.patch(
                    "mygui.fullprof_prf.parse_fullprof_prf",
                    side_effect=AssertionError("restore must not read PRF"),
                ) as parser:
                    restore_project_snapshot(
                        project_path,
                        restored_window.table,
                        restored_window.figure_window,
                    )
                parser.assert_not_called()
                canvas = restored_window.figure_window.current_canva
                project = canvas.repository.project(canvas.project_id)
                names = [sheet.name for sheet in project.sheets.values()]
                self.assertIn("Transient Profile", names)
                self.assertIn("Transient Reflections", names)

                axes = canvas.component_registry.query(kind=ComponentKind.AXES)
                self.assertEqual(len(axes), 2)
                axes_by_row = {
                    controller.state.data["subplot"]["row"]: controller for controller in axes
                }
                main = axes_by_row[0].resolve_target()
                residual_axes = axes_by_row[1].resolve_target()
                self.assertTrue(main.get_shared_x_axes().joined(main, residual_axes))
                self.assertEqual(
                    len(canvas.component_registry.query(role=ComponentRole.REFLECTION_POSITIONS)),
                    1,
                )
                restored_residual = canvas.component_registry.query(role=ComponentRole.DATA_PLOT)
                restored_residual = next(
                    item
                    for item in restored_residual
                    if item.state.properties["label"] == ""
                    and item.state.parent_id == axes_by_row[1].component_id
                )
                np.testing.assert_allclose(
                    restored_residual.resolve_target().get_ydata(),
                    [10.0, -1.0, 5.0],
                )
                self.assertEqual(
                    canvas.component_registry.get(outcome.reflection_positions_id).state.data[
                        "positions"
                    ],
                    [],
                )
                self.assertEqual(
                    canvas.component_registry.get(outcome.reflection_positions_id).state.data[
                        "position_ref"
                    ],
                    outcome.table.reflection_position_ref.to_dict(),
                )
                main_legend = main.get_legend()
                self.assertEqual(
                    [text.get_text() for text in main_legend.get_texts()],
                    ["Observed", "Calculated"],
                )
                self.assertTrue(main_legend.get_visible())
                self.assertFalse(residual_axes.get_legend().get_visible())
            finally:
                restored_window.close()
                self.app.processEvents()


if __name__ == "__main__":
    unittest.main()
