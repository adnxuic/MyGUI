"""Requirement-driven, opaque-box E2E acceptance tests for MyGUI.

This suite implements the 4-tier acceptance methodology:
- Tier 1: Feature Coverage (Core End-to-End User Workflows)
- Tier 2: Boundary & Corner Cases (Stress, Scale, and Failure Recovery)
- Tier 3: Cross-Feature Interactions (Isolation, State Invariants, and Lifecycle)
- Tier 4: Real-World Application Scenarios (Scientific and Analytical Workflows)
"""

from __future__ import annotations

import base64
from io import BytesIO
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image
import numpy as np

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QCoreApplication, QEvent, Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QApplication, QInputDialog, QMessageBox

from main import MainWindow
from mygui import tex_config
from mygui.database import ColumnRef, scipy_fit_adapter
from mygui.figure_export import (
    ExportFormat,
    FigureExportOptions,
    FigureExportRequest,
)
from mygui.figuremodify.components import (
    ComponentKind,
    ComponentRole,
)
from mygui.figuremodify.in_axes import (
    ImageInAxesCreateSpec,
    ZoomInAxesCreateSpec,
)
from mygui.project_io import (
    load_project_file,
    restore_project_snapshot,
    save_project_snapshot,
)
from tests.axes_helpers import create_regular_axes
from tests.schema_helpers import as_schema_v14


class _E2EBaseTestCase(unittest.TestCase):
    """Base fixture for E2E acceptance tests providing clean Qt and temp lifecycle."""

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.work_path = Path(self.temp_dir.name)
        self.window = MainWindow()
        self.window.resize(1280, 800)
        self.window.showNormal()
        self._process_events()

    def tearDown(self):
        tex_config.set_tex_enabled(False, notify=False)
        if self.window is not None:
            self.window.close_without_prompt()
            self.window.deleteLater()
            self.window = None
        self._process_events()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        self._process_events()
        self.temp_dir.cleanup()

    def _process_events(self):
        self.app.processEvents()
        self.app.processEvents()

    def _create_project_with_axes(
        self,
        name: str = "TestProject",
        width: float = 6.0,
        height: float = 4.5,
        dpi: int = 100,
        style: str = "default",
    ):
        """Create a new project tab with a regular axes grid and return handles."""
        self.window.figure_window.add_figure(
            width=width,
            height=height,
            dpi=dpi,
            style=style,
            canva_name=name,
        )
        self._process_events()
        canvas = self.window.figure_window.current_canva
        axes_ids = create_regular_axes(canvas)
        subtable = self.window.table.current_subtable()
        table_view = subtable.get_table(0)
        return canvas, table_view, axes_ids[0]

    @staticmethod
    def _export_canvas(canvas, file_path: Path, fmt: ExportFormat, dpi: int = 100):
        """Export canvas using official FigureExportRequest."""
        request = FigureExportRequest(
            path=file_path,
            format=fmt,
            options=FigureExportOptions.defaults(dpi=dpi),
        )
        canvas.export_figure(request)


class Tier1FeatureCoverageTests(_E2EBaseTestCase):
    """Tier 1: Feature Coverage (Core End-to-End User Workflows)."""

    def test_t1_1_complete_project_lifecycle_and_persistence_roundtrip(self):
        """T1.1: Verify project creation, data population, multi-chart generation, export, save & restore."""
        canvas, table_view, axes_id = self._create_project_with_axes(
            "FullLifecycleProject", width=7.0, height=5.0, dpi=100
        )
        subtable = self.window.table.current_subtable()
        sheet1 = table_view.table_model.sheet
        sheet1.columns[0].name = "Wavelength"
        sheet1.columns[1].name = "Absorption"

        # Add second sheet for auxiliary calibration
        sheet2_view = subtable.add_new_sheet("Calibration")
        sheet2 = sheet2_view.table_model.sheet
        sheet2.columns[0].name = "Standard"
        sheet2.columns[1].name = "Response"
        sheet2.set_block(
            0,
            0,
            [
                [10.0, 0.15],
                [20.0, 0.31],
                [30.0, 0.44],
                [40.0, 0.62],
                [50.0, 0.78],
            ],
        )

        # Populate Sheet 1
        raw_data = [
            [400.0, 0.05],
            [450.0, 0.22],
            [500.0, 0.85],
            [550.0, 0.45],
            [600.0, 0.12],
            [650.0, 0.04],
        ]
        sheet1.set_block(0, 0, raw_data)

        x_ref = ColumnRef(canvas.project_id, sheet1.id, sheet1.columns[0].id)
        y_ref = ColumnRef(canvas.project_id, sheet1.id, sheet1.columns[1].id)
        line_pair = self.window.repository.line_pair(x_ref, y_ref)
        valid_pair = self.window.repository.valid_pair(x_ref, y_ref)

        # 1. Line plot
        canvas.add_plot(
            line_pair.x,
            line_pair.y,
            "-",
            2.0,
            "#1f77b4",
            "Spectral Trace",
            x_ref,
            y_ref,
            object_id="spec-line",
        )

        # 2. Scatter plot with color mapping
        canvas.add_scatter(
            valid_pair.x,
            valid_pair.y,
            40.0,
            "#d62728",
            "o",
            "Peak Samples",
            x_ref,
            y_ref,
            object_id="spec-scatter",
            color_ref=y_ref,
            color_mapping={
                "enabled": True,
                "cmap": "plasma",
                "norm": {
                    "kind": "linear",
                    "params": {"vmin": 0.0, "vmax": 1.0, "clip": False},
                },
                "bad": "#00000000",
                "under": None,
                "over": None,
                "nonfinite": "drop",
            },
        )

        # 3. Colorbar linked to scatter
        canvas.add_colorbar(
            "spec-scatter",
            {"label": "Intensity (a.u.)"},
            object_id="spec-colorbar",
        )

        # 4. Symbolic Curve
        canvas.add_curve(
            "0.85 * exp(-((x-500)/40)**2)",
            400,
            650,
            "--",
            "#2ca02c",
            "Gaussian Model",
            object_id="spec-curve",
        )

        # 5. Reference Marks
        canvas.add_reference_marks(
            [450.0, 500.0, 550.0],
            {
                "label": "Key Transition Peaks",
                "baseline": 0.0,
                "height": 0.9,
                "color": "#9467bd",
                "linewidth": 1.5,
            },
            object_id="spec-refmarks",
            announce=False,
        )

        # 6. Reference Line & Band
        canvas.add_reference_line(
            {"label": "Baseline Threshold", "value": 0.1, "orientation": "horizontal"},
            object_id="spec-refline",
            announce=False,
        )
        canvas.add_reference_band(
            {"label": "Active Band", "lower": 480.0, "upper": 520.0, "orientation": "vertical"},
            object_id="spec-refband",
            announce=False,
        )

        # 7. In-Axes Zoom and Image
        canvas.add_in_axes(
            ZoomInAxesCreateSpec(
                bounds=(0.60, 0.55, 0.35, 0.35),
                xlim=(480.0, 520.0),
                ylim=(0.4, 0.9),
                facecolor="#ffffff",
                edgecolor="#000000",
                linewidth=0.8,
                indicator_color="#333333",
            )
        )
        img = Image.new("RGBA", (4, 4), (100, 150, 200, 255))
        img_buffer = BytesIO()
        img.save(img_buffer, format="PNG")
        canvas.add_in_axes(
            ImageInAxesCreateSpec(
                bounds=(0.05, 0.60, 0.25, 0.25),
                filename="sample_micrograph.png",
                mime_type="image/png",
                payload_base64=base64.b64encode(img_buffer.getvalue()).decode("ascii"),
                facecolor="#ffffff",
                edgecolor="#000000",
                linewidth=0.8,
            )
        )

        # 8. Annotations (Text & Title)
        canvas.add_text(0.5, 0.85, "Primary Peak", "DejaVu Sans", 11)
        canvas.add_global_text(0.5, 0.96, "Spectroscopy Analysis Report", "DejaVu Sans", 14)

        # Verify Figure Export functionality
        export_png = self.work_path / "lifecycle_export.png"
        export_pdf = self.work_path / "lifecycle_export.pdf"
        self._export_canvas(canvas, export_png, ExportFormat.PNG, dpi=150)
        self._export_canvas(canvas, export_pdf, ExportFormat.PDF, dpi=150)
        self.assertTrue(export_png.is_file() and export_png.stat().st_size > 1000)
        self.assertTrue(export_pdf.is_file() and export_pdf.stat().st_size > 1000)

        # Save snapshot
        project_file = self.work_path / "lifecycle_project.mygui.json"
        save_project_snapshot(project_file, self.window.figure_window)
        self.assertTrue(project_file.is_file())

        # Restore into a fresh MainWindow instance
        restored_window = MainWindow()
        try:
            restore_project_snapshot(
                project_file,
                restored_window.table,
                restored_window.figure_window,
            )
            restored_canvas = restored_window.figure_window.current_canva
            self.assertIsNotNone(restored_canvas)
            self.assertEqual(restored_canvas.project_name, "FullLifecycleProject")

            # Verify tables restored
            restored_subtable = restored_window.table.current_subtable()
            project_sheets = restored_window.repository.project(restored_canvas.project_id).sheets
            self.assertEqual(len(project_sheets), 2)
            self.assertEqual(restored_subtable.tabWidget.tabText(0), "Sheet1")
            self.assertEqual(restored_subtable.tabWidget.tabText(1), "Calibration")

            # Verify components restored
            registry = restored_canvas.component_registry
            self.assertIn("spec-line", registry)
            self.assertIn("spec-scatter", registry)
            self.assertIn("spec-colorbar", registry)
            self.assertIn("spec-curve", registry)
            self.assertIn("spec-refmarks", registry)
            self.assertIn("spec-refline", registry)
            self.assertIn("spec-refband", registry)

            # Verify data fidelity
            ref_marks = registry.get("spec-refmarks")
            self.assertEqual(ref_marks.state.data["positions"], [450.0, 500.0, 550.0])

            # Verify in-axes count (zoom + image)
            in_axes_controllers = registry.query(kind=ComponentKind.IN_AXES)
            self.assertEqual(len(in_axes_controllers), 2)

            # Verify texts
            texts = registry.query(role=ComponentRole.TEXT)
            self.assertEqual(len(texts), 2)
        finally:
            restored_window.close_without_prompt()
            restored_window.deleteLater()
            self._process_events()

    def test_t1_2_table_data_editing_and_reactive_propagation(self):
        """T1.2: Verify that table cell edits, TSV pasting, and NaN values dynamically update Matplotlib Artists."""
        canvas, table_view, axes_id = self._create_project_with_axes("DataPropagationProject")
        sheet = table_view.table_model.sheet
        sheet.set_block(0, 0, [[1.0, 10.0], [2.0, 20.0], [3.0, 30.0], [4.0, 40.0]])

        x_ref = ColumnRef(canvas.project_id, sheet.id, sheet.columns[0].id)
        y_ref = ColumnRef(canvas.project_id, sheet.id, sheet.columns[1].id)
        pair = self.window.repository.line_pair(x_ref, y_ref)

        canvas.add_plot(
            pair.x,
            pair.y,
            "-",
            2.0,
            "blue",
            "Live Line",
            x_ref,
            y_ref,
            object_id="live-line",
        )
        line_artist = canvas.component_registry.get("live-line").resolve_target()

        # Step 1: Single cell edit
        model = table_view.table_model
        model.setData(model.index(1, 1), "25.5", Qt.EditRole)
        self._process_events()

        np.testing.assert_allclose(line_artist.get_ydata()[:4], [10.0, 25.5, 30.0, 40.0])

        # Step 2: Multi-cell TSV / CRLF Paste
        table_view.setCurrentIndex(model.index(4, 0))
        QGuiApplication.clipboard().setText("5.0\t50.0\r\n6.0\t60.0\r\n")
        table_view.paste_items()
        self._process_events()

        np.testing.assert_allclose(
            line_artist.get_ydata()[:6],
            [10.0, 25.5, 30.0, 40.0, 50.0, 60.0],
        )

        # Step 3: Undo paste
        self.window.repository.undo_stack(canvas.project_id).undo()
        self._process_events()
        self.assertEqual(model.data(model.index(4, 0)), "")

        # Step 4: Introduce blank/NaN row
        model.setData(model.index(2, 1), "", Qt.EditRole)
        self._process_events()

        self.assertTrue(np.isnan(line_artist.get_ydata()[2]))

    def test_t1_3_component_selection_inspector_mutation_and_undo_redo(self):
        """T1.3: Verify selecting components, mutating visual properties, atomic rollback, and undo/redo."""
        canvas, table_view, axes_id = self._create_project_with_axes("PropertyMutationProject")
        sheet = table_view.table_model.sheet
        sheet.set_block(0, 0, [[0.0, 1.0], [1.0, 3.0], [2.0, 9.0]])
        x_ref = ColumnRef(canvas.project_id, sheet.id, sheet.columns[0].id)
        y_ref = ColumnRef(canvas.project_id, sheet.id, sheet.columns[1].id)
        pair = self.window.repository.line_pair(x_ref, y_ref)

        canvas.add_plot(
            pair.x,
            pair.y,
            "-",
            2.0,
            "#00ff00",
            "Editable Line",
            x_ref,
            y_ref,
            object_id="editable-line",
        )
        line_controller = canvas.component_registry.get("editable-line")
        line_artist = line_controller.resolve_target()
        initial_lw = line_controller.state.properties["linewidth"]

        # Selection authority check
        self.assertTrue(canvas.select_component("editable-line"))
        self.assertEqual(canvas.current_component_id, "editable-line")

        # Mutate properties through undoable editor_context
        res1 = canvas.editor_context.perform(
            "Change Color",
            lambda: line_controller.set_property("color", "#ff00aa"),
        )
        self.assertTrue(res1.ok)
        res2 = canvas.editor_context.perform(
            "Change Linewidth",
            lambda: line_controller.set_property("linewidth", 4.5),
        )
        self.assertTrue(res2.ok)
        self._process_events()

        self.assertEqual(line_controller.state.properties["color"], "#ff00aa")
        self.assertEqual(line_controller.state.properties["linewidth"], 4.5)
        self.assertAlmostEqual(line_artist.get_linewidth(), 4.5)

        # Invalid property mutation rejection (atomic rollback)
        invalid_res = line_controller.set_property("alpha", -0.5)
        self.assertFalse(invalid_res.ok)

        # Test Undo
        undo_stack = self.window.repository.undo_stack(canvas.project_id)
        undo_stack.undo()  # undo linewidth 4.5
        self._process_events()
        self.assertEqual(line_controller.state.properties["linewidth"], initial_lw)

        # Test Redo
        undo_stack.redo()  # redo linewidth 4.5
        self._process_events()
        self.assertEqual(line_controller.state.properties["linewidth"], 4.5)

    def test_t1_4_scientific_curve_fitting_end_to_end(self):
        """T1.4: Verify model fitting, parameter evaluation, fit curve materialization, and persistence."""
        canvas, table_view, axes_id = self._create_project_with_axes("FitProject")
        sheet = table_view.table_model.sheet
        x_pts = np.linspace(-3.0, 3.0, 15)
        y_pts = 2.5 * x_pts**2 - 1.2 * x_pts + 0.8

        sheet.set_block(0, 0, [[float(xi), float(yi)] for xi, yi in zip(x_pts, y_pts, strict=False)])
        x_ref = ColumnRef(canvas.project_id, sheet.id, sheet.columns[0].id)
        y_ref = ColumnRef(canvas.project_id, sheet.id, sheet.columns[1].id)
        valid_pair = self.window.repository.valid_pair(x_ref, y_ref)

        # Execute fitting via scipy_fit_adapter
        fit_result = scipy_fit_adapter.fit_curve(valid_pair.x, valid_pair.y, "poly2")
        self.assertEqual(fit_result["fit_type"], "poly2")
        self.assertAlmostEqual(fit_result["goodness"]["rsquare"], 1.0, places=4)

        # Materialize fit curve on canvas
        canvas.add_fit_curve(
            valid_pair.x,
            valid_pair.y,
            "#0000ff",
            "Quadratic Fit",
            x_ref,
            y_ref,
            fit_type="poly2",
            expression=fit_result["value_expression"],
            x_start=-3.0,
            x_stop=3.0,
            fit_result=fit_result,
            object_id="poly-fit-curve",
        )
        self.assertIn("poly-fit-curve", canvas.component_registry)
        fit_ctrl = canvas.component_registry.get("poly-fit-curve")
        self.assertEqual(fit_ctrl.state.role, ComponentRole.FIT_CURVE)

        # Save and restore project to ensure fit metadata roundtrips
        save_file = self.work_path / "fit_project.mygui.json"
        save_project_snapshot(save_file, self.window.figure_window)

        loaded_win = MainWindow()
        try:
            restore_project_snapshot(
                save_file, loaded_win.table, loaded_win.figure_window
            )
            restored_canvas = loaded_win.figure_window.current_canva
            restored_fit = restored_canvas.component_registry.get("poly-fit-curve")
            self.assertIsNotNone(restored_fit)
            self.assertEqual(restored_fit.state.data["fit_type"], "poly2")
            self.assertIn("p1", [c["name"] for c in restored_fit.state.data["fit_result"]["coefficients"]])
        finally:
            loaded_win.close_without_prompt()
            loaded_win.deleteLater()
            self._process_events()

    def test_t1_5_xrd_reference_marks_workflow(self):
        """T1.5: Verify XRD / diffraction reference marks configuration, positioning, and table linkage."""
        canvas, table_view, axes_id = self._create_project_with_axes("XRDProject")
        positions = [28.44, 47.30, 56.12, 69.13, 76.38, 88.02]  # Silicon 2theta standards

        canvas.add_reference_marks(
            positions,
            {
                "label": "Si Standards",
                "baseline": 0.05,
                "height": 0.25,
                "color": "#e377c2",
                "linewidth": 2.0,
            },
            object_id="si-refmarks",
            announce=False,
        )

        ref_ctrl = canvas.component_registry.get("si-refmarks")
        self.assertIsNotNone(ref_ctrl)
        self.assertEqual(ref_ctrl.state.data["positions"], positions)
        line_collection = ref_ctrl.resolve_target()
        self.assertEqual(len(line_collection.get_segments()), len(positions))

        # Mutate reference mark properties
        ref_ctrl.set_property("color", "#17becf")
        ref_ctrl.set_property("linewidth", 3.0)
        self.assertEqual(ref_ctrl.state.properties["color"], "#17becf")
        self.assertEqual(ref_ctrl.state.properties["linewidth"], 3.0)


class Tier2BoundaryAndCornerCaseTests(_E2EBaseTestCase):
    """Tier 2: Boundary & Corner Cases (Stress, Scale, and Failure Recovery)."""

    def test_t2_1_empty_and_extreme_data_boundaries(self):
        """T2.1: Verify application robustness on 0-length data, single points, all-NaN series, and extreme coordinates."""
        canvas, table_view, axes_id = self._create_project_with_axes("BoundaryProject")
        sheet = table_view.table_model.sheet

        # Case A: Single point
        sheet.set_block(0, 0, [[1.0, 100.0]])
        x_ref = ColumnRef(canvas.project_id, sheet.id, sheet.columns[0].id)
        y_ref = ColumnRef(canvas.project_id, sheet.id, sheet.columns[1].id)
        valid_pair = self.window.repository.valid_pair(x_ref, y_ref)
        canvas.add_scatter(
            valid_pair.x, valid_pair.y, 20.0, "red", "o", "Single Point", x_ref, y_ref, object_id="single-pt"
        )
        self.assertIn("single-pt", canvas.component_registry)

        # Case B: Extreme coordinates (1e12 and 1e-12)
        sheet.set_block(1, 0, [[1e12, 1e-12], [2e12, 2e-12]])
        line_pair = self.window.repository.line_pair(x_ref, y_ref)
        canvas.add_plot(
            line_pair.x, line_pair.y, "-", 1.5, "black", "Extreme Line", x_ref, y_ref, object_id="extreme-line"
        )
        self.assertIn("extreme-line", canvas.component_registry)

        # Case C: All-NaN columns
        sheet2_view = self.window.table.current_subtable().add_new_sheet("NaNSheet")
        sheet2 = sheet2_view.table_model.sheet
        sheet2.set_block(0, 0, [["", ""], ["", ""]])
        nan_x = ColumnRef(canvas.project_id, sheet2.id, sheet2.columns[0].id)
        nan_y = ColumnRef(canvas.project_id, sheet2.id, sheet2.columns[1].id)
        nan_valid = self.window.repository.valid_pair(nan_x, nan_y)
        self.assertEqual(len(nan_valid.x), 0)
        self.assertEqual(len(nan_valid.y), 0)

        # Add scatter on empty valid pairs - should not raise exception
        canvas.add_scatter(
            nan_valid.x, nan_valid.y, 10.0, "green", "s", "Empty Scatter", nan_x, nan_y, object_id="empty-scatter"
        )
        self.assertIn("empty-scatter", canvas.component_registry)

        # Case D: Tabular data block (15 points)
        large_x = np.linspace(0, 10, 15)
        large_y = np.sin(large_x)
        sheet.set_block(0, 0, [[float(xi), float(yi)] for xi, yi in zip(large_x, large_y, strict=False)])
        large_pair = self.window.repository.line_pair(x_ref, y_ref)
        self.assertEqual(len(large_pair.x), 15)
        self.assertAlmostEqual(large_pair.x[0], 0.0)

    def test_t2_2_schema_migration_and_corrupt_file_rejection(self):
        """T2.2: Verify sequential schema migration (v13 -> v14 -> v15) and clean rejection of corrupt files."""
        canvas, table_view, axes_id = self._create_project_with_axes("SchemaMigrationProject")
        sheet = table_view.table_model.sheet
        sheet.set_block(0, 0, [[1.0, 2.0], [3.0, 4.0]])
        x_ref = ColumnRef(canvas.project_id, sheet.id, sheet.columns[0].id)
        y_ref = ColumnRef(canvas.project_id, sheet.id, sheet.columns[1].id)
        pair = self.window.repository.line_pair(x_ref, y_ref)
        canvas.add_plot(pair.x, pair.y, "-", 2.0, "blue", "Migrate Line", x_ref, y_ref)

        snapshot_v15 = self.work_path / "snap_v15.mygui.json"
        save_project_snapshot(snapshot_v15, self.window.figure_window)

        # Construct synthetic v14 payload
        v15_data = json.loads(snapshot_v15.read_text(encoding="utf-8"))
        v14_data = as_schema_v14(v15_data)
        snapshot_v14 = self.work_path / "snap_v14.mygui.json"
        snapshot_v14.write_text(json.dumps(v14_data, indent=2), encoding="utf-8")

        # Construct synthetic v13 payload
        v13_data = json.loads(snapshot_v14.read_text(encoding="utf-8"))
        v13_data["schema_version"] = 13
        snapshot_v13 = self.work_path / "snap_v13.mygui.json"
        snapshot_v13.write_text(json.dumps(v13_data, indent=2), encoding="utf-8")

        # Verify loading v13 migrates smoothly to v15
        test_win = MainWindow()
        try:
            restore_project_snapshot(snapshot_v13, test_win.table, test_win.figure_window)
            self.assertEqual(test_win.figure_window.current_canva.project_name, "SchemaMigrationProject")

            # Corrupt file test A: Missing schema version
            corrupt_data = dict(v15_data)
            del corrupt_data["schema_version"]
            corrupt_file = self.work_path / "corrupt_no_ver.mygui.json"
            corrupt_file.write_text(json.dumps(corrupt_data), encoding="utf-8")
            with self.assertRaises(Exception):
                load_project_file(corrupt_file)

            # Corrupt file test B: Retired schema version 4
            v4_data = dict(v15_data)
            v4_data["schema_version"] = 4
            v4_file = self.work_path / "retired_v4.mygui.json"
            v4_file.write_text(json.dumps(v4_data), encoding="utf-8")
            with self.assertRaises(Exception):
                load_project_file(v4_file)
        finally:
            test_win.close_without_prompt()
            test_win.deleteLater()
            self._process_events()

    def test_t2_3_cascade_deletion_and_referential_integrity(self):
        """T2.3: Verify cascade deletion of multi-dependent components and 100% undo recovery."""
        canvas, table_view, axes_id = self._create_project_with_axes("CascadeProject")
        sheet = table_view.table_model.sheet
        sheet.set_block(0, 0, [[1.0, 10.0], [2.0, 20.0], [3.0, 30.0]])
        x_ref = ColumnRef(canvas.project_id, sheet.id, sheet.columns[0].id)
        y_ref = ColumnRef(canvas.project_id, sheet.id, sheet.columns[1].id)
        pair = self.window.repository.line_pair(x_ref, y_ref)
        valid_pair = self.window.repository.valid_pair(x_ref, y_ref)

        # Create line plot, scatter plot, and colorbar all dependent on y_ref
        canvas.add_plot(pair.x, pair.y, "-", 2.0, "blue", "Line", x_ref, y_ref, object_id="dep-line")
        canvas.add_scatter(
            valid_pair.x,
            valid_pair.y,
            30.0,
            "red",
            "o",
            "Scatter",
            x_ref,
            y_ref,
            object_id="dep-scatter",
            color_ref=y_ref,
            color_mapping={
                "enabled": True,
                "cmap": "viridis",
                "norm": {"kind": "linear", "params": {"vmin": 10.0, "vmax": 30.0, "clip": False}},
                "bad": "#00000000",
                "under": None,
                "over": None,
                "nonfinite": "drop",
            },
        )
        canvas.add_colorbar("dep-scatter", {"label": "Values"}, object_id="dep-colorbar")

        self.assertIn("dep-line", canvas.component_registry)
        self.assertIn("dep-scatter", canvas.component_registry)
        self.assertIn("dep-colorbar", canvas.component_registry)

        # Delete column 1 (y_ref)
        table_view.setCurrentIndex(table_view.table_model.index(0, 1))
        with patch(
            "mygui.widgets.figure_canvas.py_figure_window.ask_confirmation",
            return_value=True,
        ):
            table_view.delete_column()
        self._process_events()

        # Dependent components must be cleanly unlinked/deleted
        self.assertNotIn("dep-line", canvas.component_registry)
        self.assertNotIn("dep-scatter", canvas.component_registry)
        self.assertNotIn("dep-colorbar", canvas.component_registry)
        self.assertFalse(self.window.repository.has_ref(y_ref))

        # Undo the column deletion: dependent data plots must be restored
        self.window.repository.undo_stack(canvas.project_id).undo()
        self._process_events()

        self.assertTrue(self.window.repository.has_ref(y_ref))
        self.assertIn("dep-line", canvas.component_registry)
        self.assertIn("dep-scatter", canvas.component_registry)

    def test_t2_4_text_unicode_glyph_and_tex_runtime_fallback(self):
        """T2.4: Verify unicode Greek symbols, math expressions, and graceful TeX runtime fallback."""
        canvas, table_view, axes_id = self._create_project_with_axes("UnicodeTeXProject")

        # 1. Unicode Greek and special symbols
        unicode_str = "Diffraction Angle 2θ (λ = 1.5406 Å, α=0.05, ΔE/E < 10⁻⁴)"
        canvas.add_text(0.1, 0.9, unicode_str, "DejaVu Sans", 11, object_id="unicode-txt")
        self.assertIn("unicode-txt", canvas.component_registry)
        txt_target = canvas.component_registry.get("unicode-txt").resolve_target()
        self.assertEqual(txt_target.get_text(), unicode_str)

        # 2. Math expression with TeX toggled off / fallback
        tex_config.set_tex_enabled(False, notify=False)
        canvas.add_text(0.1, 0.5, r"$\int_0^\infty e^{-x^2} dx = \frac{\sqrt{\pi}}{2}$", "DejaVu Sans", 12, object_id="math-txt")
        self.assertIn("math-txt", canvas.component_registry)

        # Verify export still succeeds with unicode characters
        export_out = self.work_path / "unicode_render.png"
        self._export_canvas(canvas, export_out, ExportFormat.PNG, dpi=100)
        self.assertTrue(export_out.is_file())


class Tier3CrossFeatureInteractionTests(_E2EBaseTestCase):
    """Tier 3: Cross-Feature Interactions (Isolation, State Invariants, and Lifecycle)."""

    def test_t3_1_multi_project_tab_isolation_and_switching(self):
        """T3.1: Verify concurrent multi-project tabs keep TableRepository, registries, and undo stacks isolated."""
        fig_win = self.window.figure_window

        # Project 1
        canvas1, view1, _ = self._create_project_with_axes("ProjectOne")
        sheet1 = view1.table_model.sheet
        sheet1.set_block(0, 0, [[1.0, 10.0], [2.0, 20.0]])
        x_ref1 = ColumnRef(canvas1.project_id, sheet1.id, sheet1.columns[0].id)
        y_ref1 = ColumnRef(canvas1.project_id, sheet1.id, sheet1.columns[1].id)
        canvas1.add_plot(
            self.window.repository.line_pair(x_ref1, y_ref1).x,
            self.window.repository.line_pair(x_ref1, y_ref1).y,
            "-",
            2.0,
            "blue",
            "P1-Line",
            x_ref1,
            y_ref1,
            object_id="p1-line",
        )

        # Project 2
        canvas2, view2, _ = self._create_project_with_axes("ProjectTwo")
        sheet2 = view2.table_model.sheet
        sheet2.set_block(0, 0, [[10.0, 100.0], [20.0, 200.0]])
        x_ref2 = ColumnRef(canvas2.project_id, sheet2.id, sheet2.columns[0].id)
        y_ref2 = ColumnRef(canvas2.project_id, sheet2.id, sheet2.columns[1].id)
        canvas2.add_plot(
            self.window.repository.line_pair(x_ref2, y_ref2).x,
            self.window.repository.line_pair(x_ref2, y_ref2).y,
            "--",
            3.0,
            "red",
            "P2-Line",
            x_ref2,
            y_ref2,
            object_id="p2-line",
        )

        # Project 3
        canvas3, view3, _ = self._create_project_with_axes("ProjectThree")
        sheet3 = view3.table_model.sheet
        sheet3.set_block(0, 0, [[100.0, 1000.0], [200.0, 2000.0]])
        x_ref3 = ColumnRef(canvas3.project_id, sheet3.id, sheet3.columns[0].id)
        y_ref3 = ColumnRef(canvas3.project_id, sheet3.id, sheet3.columns[1].id)
        canvas3.add_plot(
            self.window.repository.line_pair(x_ref3, y_ref3).x,
            self.window.repository.line_pair(x_ref3, y_ref3).y,
            ":",
            1.5,
            "green",
            "P3-Line",
            x_ref3,
            y_ref3,
            object_id="p3-line",
        )

        self.assertEqual(fig_win.tabwindow.count(), 3)

        # Switch to Project 1
        fig_win.tabwindow.setCurrentWidget(canvas1)
        self._process_events()
        self.assertEqual(self.window.table.current_project_id, canvas1.project_id)
        self.assertIn("p1-line", fig_win.current_canva.component_registry)
        self.assertNotIn("p2-line", fig_win.current_canva.component_registry)

        # Switch to Project 2 and perform undo
        fig_win.tabwindow.setCurrentWidget(canvas2)
        self._process_events()
        self.assertEqual(self.window.table.current_project_id, canvas2.project_id)
        undo2 = self.window.repository.undo_stack(canvas2.project_id)
        undo2.undo()  # Undo p2-line addition
        self.assertNotIn("p2-line", canvas2.component_registry)

        # Verify Project 1 & 3 are completely unaffected
        self.assertIn("p1-line", canvas1.component_registry)
        self.assertIn("p3-line", canvas3.component_registry)

        # Close Project 2
        p2_index = fig_win.tabwindow.indexOf(canvas2)
        with patch.object(self.window, "_project_close_choice", return_value=QMessageBox.Discard):
            self.window.close_project_from_tab(p2_index)
        self._process_events()
        self.assertEqual(fig_win.tabwindow.count(), 2)

    def test_t3_2_complex_interleaved_undo_redo_and_save_workflow(self):
        """T3.2: Verify multi-step interleaved edits, undos, redos, and snapshot consistency."""
        canvas, table_view, axes_id = self._create_project_with_axes("InterleavedProject")
        sheet = table_view.table_model.sheet
        sheet.set_block(0, 0, [[1.0, 5.0], [2.0, 10.0], [3.0, 15.0]])
        x_ref = ColumnRef(canvas.project_id, sheet.id, sheet.columns[0].id)
        y_ref = ColumnRef(canvas.project_id, sheet.id, sheet.columns[1].id)

        # Step 1: Add line plot
        pair = self.window.repository.line_pair(x_ref, y_ref)
        canvas.add_plot(pair.x, pair.y, "-", 2.0, "blue", "Line 1", x_ref, y_ref, object_id="step-line")

        # Step 2: Add curve
        canvas.add_curve("2*x + 3", 1, 3, "--", "red", "Curve 2", object_id="step-curve")

        # Step 3: Add text
        canvas.add_text(0.5, 0.5, "Annotation", "DejaVu Sans", 12, object_id="step-text")

        # Verify initial count
        self.assertIn("step-line", canvas.component_registry)
        self.assertIn("step-curve", canvas.component_registry)
        self.assertIn("step-text", canvas.component_registry)

        undo_stack = self.window.repository.undo_stack(canvas.project_id)

        # Undo text
        undo_stack.undo()
        self.assertNotIn("step-text", canvas.component_registry)
        self.assertIn("step-curve", canvas.component_registry)

        # Undo curve
        undo_stack.undo()
        self.assertNotIn("step-curve", canvas.component_registry)
        self.assertIn("step-line", canvas.component_registry)

        # Save snapshot at intermediate state
        intermediate_file = self.work_path / "intermediate.mygui.json"
        save_project_snapshot(intermediate_file, self.window.figure_window)

        # Redo curve
        undo_stack.redo()
        self.assertIn("step-curve", canvas.component_registry)
        self.assertNotIn("step-text", canvas.component_registry)

        # Redo text
        undo_stack.redo()
        self.assertIn("step-text", canvas.component_registry)

        # Restore intermediate snapshot in another window
        check_win = MainWindow()
        try:
            restore_project_snapshot(intermediate_file, check_win.table, check_win.figure_window)
            res_canvas = check_win.figure_window.current_canva
            self.assertIn("step-line", res_canvas.component_registry)
            self.assertNotIn("step-curve", res_canvas.component_registry)
            self.assertNotIn("step-text", res_canvas.component_registry)
        finally:
            check_win.close_without_prompt()
            check_win.deleteLater()
            self._process_events()

    def test_t3_3_canvas_popout_and_docking_lifecycle(self):
        """T3.3: Verify canvas popout floating window, live updates while popped out, and clean re-docking."""
        canvas, table_view, axes_id = self._create_project_with_axes("PopoutLifecycleProject")
        sheet = table_view.table_model.sheet
        sheet.set_block(0, 0, [[1.0, 10.0], [2.0, 20.0]])
        x_ref = ColumnRef(canvas.project_id, sheet.id, sheet.columns[0].id)
        y_ref = ColumnRef(canvas.project_id, sheet.id, sheet.columns[1].id)
        pair = self.window.repository.line_pair(x_ref, y_ref)
        canvas.add_plot(pair.x, pair.y, "-", 2.0, "blue", "Line", x_ref, y_ref, object_id="pop-line")

        # Trigger popout
        canvas.popout_action.trigger()
        self._process_events()

        popout_win = canvas._canvas_popout_window
        self.assertIsNotNone(popout_win)
        self.assertTrue(popout_win.isVisible())

        # Modify table data while canvas is floating
        table_view.table_model.setData(table_view.table_model.index(1, 1), "35.0", Qt.EditRole)
        self._process_events()

        line_artist = canvas.component_registry.get("pop-line").resolve_target()
        self.assertEqual(line_artist.get_ydata()[1], 35.0)

        # Close popout and re-dock
        popout_win.close()
        self._process_events()

        self.assertIsNone(canvas._canvas_popout_window)
        self.assertFalse(canvas._canvas_popout_placeholder.isVisible())

    def test_t3_4_table_type_mutation_cascades(self):
        """T3.4: Verify changing column type from number to text triggers cascade deletion and undo restores."""
        canvas, table_view, axes_id = self._create_project_with_axes("TypeCascadeProject")
        sheet = table_view.table_model.sheet
        sheet.set_block(0, 0, [[1.0, 10.0], [2.0, 20.0], [3.0, 30.0]])
        x_ref = ColumnRef(canvas.project_id, sheet.id, sheet.columns[0].id)
        y_ref = ColumnRef(canvas.project_id, sheet.id, sheet.columns[1].id)
        pair = self.window.repository.line_pair(x_ref, y_ref)
        canvas.add_plot(pair.x, pair.y, "-", 2.0, "blue", "Type Plot", x_ref, y_ref, object_id="type-plot")

        table_view.setCurrentIndex(table_view.table_model.index(0, 0))
        with patch.object(QInputDialog, "getItem", return_value=("text", True)), \
                patch(
                    "mygui.widgets.figure_canvas.py_figure_window.ask_confirmation",
                    return_value=True,
                ):
            table_view.change_column_type()
        self._process_events()

        self.assertEqual(sheet.column(x_ref.column_id).type.value, "text")
        self.assertNotIn("type-plot", canvas.component_registry)

        # Undo type mutation
        self.window.repository.undo_stack(canvas.project_id).undo()
        self._process_events()

        self.assertEqual(sheet.column(x_ref.column_id).type.value, "number")
        self.assertIn("type-plot", canvas.component_registry)


class Tier4RealWorldScenarioTests(_E2EBaseTestCase):
    """Tier 4: Real-World Application Scenarios (Scientific and Analytical Workflows)."""

    def test_t4_1_spectroscopy_xrd_peak_analysis_scenario(self):
        """T4.1: End-to-end material science XRD / Raman multi-peak refinement and publication export."""
        canvas, table_view, axes_id = self._create_project_with_axes(
            "XRDPowderRefinement", width=8.0, height=6.0, dpi=120
        )
        sheet = table_view.table_model.sheet
        sheet.columns[0].name = "2Theta_deg"
        sheet.columns[1].name = "Observed_Intensity"

        # Generate realistic multi-peak XRD profile within sheet capacity (19 points)
        two_theta = np.linspace(20.0, 70.0, 19)
        background = 50.0 + 0.5 * two_theta
        # Peaks at 28.44 (Si 111), 47.30 (Si 220), 56.12 (Si 311)
        peak1 = 800.0 * np.exp(-((two_theta - 28.44) / 1.5) ** 2)
        peak2 = 450.0 * np.exp(-((two_theta - 47.30) / 1.5) ** 2)
        peak3 = 300.0 * np.exp(-((two_theta - 56.12) / 1.5) ** 2)
        intensity = background + peak1 + peak2 + peak3

        sheet.set_block(0, 0, [[float(t), float(y)] for t, y in zip(two_theta, intensity, strict=False)])
        x_ref = ColumnRef(canvas.project_id, sheet.id, sheet.columns[0].id)
        y_ref = ColumnRef(canvas.project_id, sheet.id, sheet.columns[1].id)
        pair = self.window.repository.line_pair(x_ref, y_ref)

        # 1. Plot raw profile
        canvas.add_plot(
            pair.x,
            pair.y,
            "-",
            1.2,
            "#000000",
            "Observed Pattern",
            x_ref,
            y_ref,
            object_id="xrd-observed",
        )

        # 2. Add Bragg peak reference marks
        bragg_peaks = [28.44, 47.30, 56.12]
        canvas.add_reference_marks(
            bragg_peaks,
            {
                "label": "Si (Fd-3m) Reflections",
                "baseline": 0.05,
                "height": 0.25,
                "color": "#1f77b4",
                "linewidth": 2.0,
            },
            object_id="si-bragg-marks",
            announce=False,
        )

        # 3. Fit primary (111) peak
        mask = (two_theta >= 24.0) & (two_theta <= 35.0)
        fit_res = scipy_fit_adapter.fit_curve(
            two_theta[mask],
            intensity[mask],
            "gauss1",
            {"StartPoint": [800.0, 28.4, 1.5]},
        )
        canvas.add_fit_curve(
            two_theta[mask],
            intensity[mask],
            "#d62728",
            "Si (111) Gaussian Fit",
            x_ref,
            y_ref,
            fit_type="gauss1",
            expression=fit_res["value_expression"],
            x_start=24.0,
            x_stop=35.0,
            fit_result=fit_res,
            object_id="si-111-fit",
        )

        # 4. Inset Zoom on (111) Peak
        canvas.add_in_axes(
            ZoomInAxesCreateSpec(
                bounds=(0.55, 0.50, 0.38, 0.42),
                xlim=(27.0, 30.0),
                ylim=(40.0, 900.0),
                facecolor="#fbfbfb",
                edgecolor="#222222",
                linewidth=1.0,
                indicator_color="#444444",
            )
        )

        # 5. Peak Annotations
        canvas.add_text(0.18, 0.85, "(111)", "DejaVu Sans", 11)
        canvas.add_text(0.55, 0.50, "(220)", "DejaVu Sans", 11)
        canvas.add_text(0.72, 0.35, "(311)", "DejaVu Sans", 11)
        canvas.add_global_text(0.5, 0.96, "Silicon Powder X-ray Diffraction Refinement", "DejaVu Sans", 14)

        # 6. High-res vector & raster export
        png_out = self.work_path / "xrd_refinement.png"
        pdf_out = self.work_path / "xrd_refinement.pdf"
        self._export_canvas(canvas, png_out, ExportFormat.PNG, dpi=300)
        self._export_canvas(canvas, pdf_out, ExportFormat.PDF, dpi=300)
        self.assertTrue(png_out.is_file())
        self.assertTrue(pdf_out.is_file())

        # 7. Save and restore verification
        proj_out = self.work_path / "xrd_analysis.mygui.json"
        save_project_snapshot(proj_out, self.window.figure_window)

        audit_win = MainWindow()
        try:
            restore_project_snapshot(proj_out, audit_win.table, audit_win.figure_window)
            audited = audit_win.figure_window.current_canva
            self.assertIn("xrd-observed", audited.component_registry)
            self.assertIn("si-bragg-marks", audited.component_registry)
            self.assertIn("si-111-fit", audited.component_registry)
            self.assertEqual(len(audited.component_registry.query(kind=ComponentKind.IN_AXES)), 1)
        finally:
            audit_win.close_without_prompt()
            audit_win.deleteLater()
            self._process_events()

    def test_t4_2_kinetic_time_series_experiment_scenario(self):
        """T4.2: End-to-end chemical kinetics reaction rates, multi-sheet tracking, and colormap mapping."""
        canvas, table_view, axes_id = self._create_project_with_axes("KineticsStudy")
        subtable = self.window.table.current_subtable()
        sheet1 = table_view.table_model.sheet
        sheet1.columns[0].name = "Time_min"
        sheet1.columns[1].name = "Reactant_A_mM"

        # Sheet 1: Concentration vs Time (15 points)
        time_pts = np.linspace(0.0, 60.0, 15)
        k_rate = 0.05
        conc_pts = 100.0 * np.exp(-k_rate * time_pts)
        sheet1.set_block(0, 0, [[float(t), float(c)] for t, c in zip(time_pts, conc_pts, strict=False)])

        # Sheet 2: Reaction Temperature
        sheet2_view = subtable.add_new_sheet("EnvironmentalSensors")
        sheet2 = sheet2_view.table_model.sheet
        sheet2.columns[0].name = "Time_min"
        sheet2.columns[1].name = "Temp_C"
        temp_pts = 25.0 + 5.0 * np.sin(time_pts / 10.0)
        sheet2.set_block(0, 0, [[float(t), float(tp)] for t, tp in zip(time_pts, temp_pts, strict=False)])

        x_ref = ColumnRef(canvas.project_id, sheet1.id, sheet1.columns[0].id)
        y_ref = ColumnRef(canvas.project_id, sheet1.id, sheet1.columns[1].id)
        temp_ref = ColumnRef(canvas.project_id, sheet2.id, sheet2.columns[1].id)

        valid_pair = self.window.repository.valid_pair(x_ref, y_ref)

        # Plot scatter colored by temperature
        canvas.add_scatter(
            valid_pair.x,
            valid_pair.y,
            35.0,
            "#ff7f0e",
            "D",
            "Concentration Points",
            x_ref,
            y_ref,
            object_id="kinetics-scatter",
            color_ref=temp_ref,
            color_mapping={
                "enabled": True,
                "cmap": "coolwarm",
                "norm": {"kind": "linear", "params": {"vmin": 20.0, "vmax": 30.0, "clip": False}},
                "bad": "#00000000",
                "under": None,
                "over": None,
                "nonfinite": "drop",
            },
        )
        canvas.add_colorbar("kinetics-scatter", {"label": "Reactor Temp (°C)"}, object_id="temp-colorbar")

        # Fit exponential decay
        fit_result = scipy_fit_adapter.fit_curve(
            valid_pair.x,
            valid_pair.y,
            "exp1",
            {"StartPoint": [100.0, -0.05]},
        )
        canvas.add_fit_curve(
            valid_pair.x,
            valid_pair.y,
            "#1f77b4",
            "First Order Model",
            x_ref,
            y_ref,
            fit_type="exp1",
            expression=fit_result["value_expression"],
            x_start=0.0,
            x_stop=60.0,
            fit_result=fit_result,
            object_id="exp-fit",
        )

        self.assertIn("kinetics-scatter", canvas.component_registry)
        self.assertIn("temp-colorbar", canvas.component_registry)
        self.assertIn("exp-fit", canvas.component_registry)

        # Save and verify
        snap_file = self.work_path / "kinetics_study.mygui.json"
        save_project_snapshot(snap_file, self.window.figure_window)
        self.assertTrue(snap_file.is_file())

    def test_t4_3_multi_figure_batch_export_scenario(self):
        """T4.3: End-to-end multi-figure dashboard creation, batch export, and clean resource teardown."""
        fig_win = self.window.figure_window

        # 1. Project A: Functional Plot
        canvas_a, table_a, _ = self._create_project_with_axes("DashboardFigA", width=5.0, height=4.0)
        canvas_a.add_curve("sin(x)", -3.14, 3.14, "-", "blue", "Sine Wave", object_id="figa-sine")

        # 2. Project B: Scatter Data
        canvas_b, table_b, _ = self._create_project_with_axes("DashboardFigB", width=5.0, height=4.0)
        sheet_b = table_b.table_model.sheet
        sheet_b.set_block(0, 0, [[1.0, 2.0], [2.0, 4.0], [3.0, 8.0], [4.0, 16.0]])
        xb_ref = ColumnRef(canvas_b.project_id, sheet_b.id, sheet_b.columns[0].id)
        yb_ref = ColumnRef(canvas_b.project_id, sheet_b.id, sheet_b.columns[1].id)
        pair_b = self.window.repository.valid_pair(xb_ref, yb_ref)
        canvas_b.add_scatter(pair_b.x, pair_b.y, 25.0, "darkorange", "^", "Exp Data", xb_ref, yb_ref, object_id="figb-scatter")

        # 3. Project C: Reference Lines & Bands
        canvas_c, table_c, _ = self._create_project_with_axes("DashboardFigC", width=5.0, height=4.0)
        canvas_c.add_reference_line({"label": "Target Limit", "value": 50.0, "orientation": "horizontal"}, object_id="figc-line")
        canvas_c.add_reference_band({"label": "Tolerance Range", "lower": 45.0, "upper": 55.0, "orientation": "horizontal"}, object_id="figc-band")

        # Batch Export all figures
        export_dir = self.work_path / "batch_exports"
        export_dir.mkdir(exist_ok=True)

        for idx, (proj_id, canva) in enumerate(list(fig_win.canvas.items())):
            target_path = export_dir / f"figure_{idx}_{canva.project_name}.png"
            self._export_canvas(canva, target_path, ExportFormat.PNG, dpi=100)
            self.assertTrue(target_path.is_file() and target_path.stat().st_size > 500)

        # Clean closing of all tabs
        with patch.object(self.window, "_project_close_choice", return_value=QMessageBox.Discard):
            while fig_win.tabwindow.count() > 0:
                self.window.close_project_from_tab(0)
                self._process_events()

        self.assertEqual(fig_win.tabwindow.count(), 0)
        self.assertEqual(len(fig_win.canvas), 0)


if __name__ == "__main__":
    unittest.main()
