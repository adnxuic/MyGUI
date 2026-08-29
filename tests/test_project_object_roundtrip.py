import os
import base64
from io import BytesIO
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tests.axes_helpers import create_regular_axes

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication
from PIL import Image
from matplotlib.collections import LineCollection

from mygui.database import ColumnRef, ColumnType, DataPreprocessSpec
from mygui.database.interpolate_func import interpolate_dict
from mygui.figuremodify.components import (
    ComponentKind,
    ComponentRole,
    validate_controller_contracts,
)
from mygui.figuremodify.in_axes import (
    ImageInAxesCreateSpec,
    ZoomInAxesCreateSpec,
)
from mygui import tex_config
from mygui.project_io import restore_project_snapshot, save_project_snapshot
from main import MainWindow


class ProjectObjectRoundtripTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.path = Path(self.directory.name) / "objects.mygui.json"
        self.window = MainWindow()

    def tearDown(self):
        tex_config.set_tex_enabled(False, notify=False)
        self.window.close()
        self.app.processEvents()
        self.directory.cleanup()

    def test_tick_font_and_axis_label_axes_coordinates_roundtrip(self):
        self.window.figure_window.add_figure(
            width=4,
            height=3,
            dpi=100,
            style="default",
            canva_name="AxisState",
        )
        canvas = self.window.figure_window.current_canva
        axes_id, = create_regular_axes(canvas)
        x_axis = canvas.component_registry.find_one(
            parent_id=axes_id,
            kind=ComponentKind.AXIS,
            role=ComponentRole.X_AXIS,
        )
        tick_labels = canvas.component_registry.find_one(
            kind=ComponentKind.TICK_LABEL_GROUP,
            selector={"axis": "x", "level": "major"},
        )
        x_label = canvas.component_registry.find_one(
            parent_id=x_axis.component_id,
            role=ComponentRole.X_LABEL,
        )
        self.assertTrue(
            tick_labels.set_property("fontfamily", ["DejaVu Sans"]).ok
        )
        self.assertTrue(x_label.set_property("position", (0.4, -0.12)).ok)

        save_project_snapshot(self.path, self.window.figure_window)
        loaded = MainWindow()
        try:
            restore_project_snapshot(
                self.path,
                loaded.table,
                loaded.figure_window,
            )
            restored = loaded.figure_window.current_canva
            restored_ticks = restored.component_registry.get(
                tick_labels.component_id
            )
            restored_label = restored.component_registry.get(
                x_label.component_id
            )
            target = restored_label.resolve_target()
            axes = restored.component_registry.resolve_target(axes_id)

            self.assertEqual(
                restored_ticks.state.properties["fontfamily"],
                "DejaVu Sans",
            )
            self.assertEqual(
                restored_ticks.resolve_target().get_major_ticks()[0]
                .label1.get_fontfamily()[0],
                "DejaVu Sans",
            )
            self.assertEqual(target.get_position(), (0.4, -0.12))
            self.assertIs(target.get_transform(), axes.transAxes)
            restored.fig.set_size_inches(7.0, 5.0)
            restored.fig.canvas.draw()
            self.assertIs(target.get_transform(), axes.transAxes)
            self.assertEqual(target.get_position(), (0.4, -0.12))
        finally:
            loaded.close()
            self.app.processEvents()

    def test_data_components_and_text_roundtrip_with_stable_ids(self):
        self.window.figure_window.add_figure(
            width=4, height=3, dpi=100, style="default", canva_name="ProjectA"
        )
        canvas = self.window.figure_window.current_canva
        create_regular_axes(canvas)
        sheet = self.window.table.current_subtable().get_table(0).table_model.sheet
        sheet.set_block(0, 0, [[0, 1], [1, 2], [2, 4], [3, 8]])
        x_ref = ColumnRef(canvas.project_id, sheet.id, sheet.columns[0].id)
        y_ref = ColumnRef(canvas.project_id, sheet.id, sheet.columns[1].id)
        error_minus = sheet.add_column("ErrorMinus", ColumnType.NUMBER, values=[0.1, 0.2, 0.1, 0.2])
        error_plus = sheet.add_column("ErrorPlus", ColumnType.NUMBER, values=[0.3, 0.4, 0.3, 0.4])
        error_minus_ref = ColumnRef(canvas.project_id, sheet.id, error_minus.id)
        error_plus_ref = ColumnRef(canvas.project_id, sheet.id, error_plus.id)
        field_x = sheet.add_column("FieldX", ColumnType.NUMBER, values=[0.0, 1.0, 0.0, 1.0])
        field_y = sheet.add_column("FieldY", ColumnType.NUMBER, values=[0.0, 0.0, 1.0, 1.0])
        field_z = sheet.add_column("FieldZ", ColumnType.NUMBER, values=[1.0, 2.0, 3.0, 4.0])
        field_x_ref = ColumnRef(canvas.project_id, sheet.id, field_x.id)
        field_y_ref = ColumnRef(canvas.project_id, sheet.id, field_y.id)
        field_z_ref = ColumnRef(canvas.project_id, sheet.id, field_z.id)
        line_pair = self.window.repository.line_pair(x_ref, y_ref)
        valid_pair = self.window.repository.valid_pair(x_ref, y_ref)

        canvas.add_plot(line_pair.x, line_pair.y, "-", 2, "black", "plot", x_ref, y_ref)
        canvas.add_scatter(
            valid_pair.x,
            valid_pair.y,
            20,
            "red",
            "o",
            "scatter",
            x_ref,
            y_ref,
            object_id="roundtrip-scatter",
            color_ref=y_ref,
            color_mapping={
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
            },
        )
        canvas.add_colorbar(
            "roundtrip-scatter",
            {"label": "Mapped values"},
            object_id="roundtrip-colorbar",
        )
        canvas.add_curve("x", 0, 3, "-", "green", "curve")
        canvas.add_component_line([0, 1], [2, 3], "-", "cyan", "line")
        canvas.add_reference_marks(
            [15.2, 15.2, 22.9],
            {
                "label": "YBCO",
                "baseline": 0.12,
                "height": 0.04,
                "color": "#123456",
                "linewidth": 1.4,
            },
            object_id="roundtrip-reference-marks",
            announce=False,
        )
        canvas.add_reference_line(
            {
                "label": "threshold",
                "value": 2.5,
                "span_start": 0.2,
                "span_end": 0.8,
            },
            object_id="roundtrip-reference-line",
            announce=False,
        )
        canvas.add_reference_band(
            {
                "label": "range",
                "orientation": "horizontal",
                "lower": 1.0,
                "upper": 2.0,
            },
            object_id="roundtrip-reference-band",
            announce=False,
        )
        linear_method = list(interpolate_dict)[2]
        canvas.add_interpolate_curve(
            valid_pair.x, valid_pair.y, x_ref, y_ref, linear_method, samples=64, label="interpolate"
        )
        canvas.add_fit_curve(
            valid_pair.x, valid_pair.y, "blue", "fit", x_ref, y_ref,
            fit_type="poly2", expression="x**2", x_start=0, x_stop=3,
            fit_result={"formula": "x**2", "coefficients": [], "goodness": {}},
        )
        canvas.add_text(0.25, 0.75, "axes text", "DejaVu Sans", 12)
        canvas.add_annotation(
            {
                "text": "roundtrip annotation",
                "xy": (1.0, 2.0),
                "xytext": (18.0, 24.0),
                "arrow_style": "filled_arrow",
            },
            object_id="roundtrip-annotation",
            announce=False,
        )
        canvas.add_global_text(0.5, 0.5, "figure text", "DejaVu Sans", 14)
        canvas.add_in_axes(
            ZoomInAxesCreateSpec(
                bounds=(0.55, 0.55, 0.35, 0.35),
                xlim=(0.0, 1.0),
                ylim=(0.0, 2.0),
                facecolor="#ffffff",
                edgecolor="#000000",
                linewidth=0.8,
                indicator_color="#000000",
            )
        )
        image = Image.new("RGBA", (2, 2), (20, 40, 80, 255))
        buffer = BytesIO()
        image.save(buffer, format="PNG")
        canvas.add_in_axes(
            ImageInAxesCreateSpec(
                bounds=(0.05, 0.55, 0.35, 0.35),
                filename="embedded.png",
                mime_type="image/png",
                payload_base64=base64.b64encode(buffer.getvalue()).decode("ascii"),
                facecolor="#ffffff",
                edgecolor="#000000",
                linewidth=0.8,
            )
        )
        canvas.add_pseudocolor(
            field_x_ref,
            field_y_ref,
            field_z_ref,
            object_id="roundtrip-pseudocolor",
        )
        canvas.add_heatmap(
            field_x_ref,
            field_y_ref,
            field_z_ref,
            object_id="roundtrip-heatmap",
        )
        canvas.add_contour(
            field_x_ref,
            field_y_ref,
            field_z_ref,
            object_id="roundtrip-contour",
        )
        canvas.add_errorbar(
            x_ref,
            y_ref,
            "errorbar",
            xerr={
                "kind": "asymmetric_ref",
                "minus_ref": error_minus_ref.to_dict(),
                "plus_ref": error_plus_ref.to_dict(),
            },
            yerr={"kind": "constant", "minus": 0.25, "plus": 0.25},
            preprocess=DataPreprocessSpec().to_dict(),
            object_id="roundtrip-errorbar",
        )

        data_roles = {
            ComponentRole.DATA_PLOT,
            ComponentRole.SCATTER,
            ComponentRole.ERROR_BAR,
            ComponentRole.INTERPOLATION,
            ComponentRole.FIT_CURVE,
            ComponentRole.PSEUDOCOLOR,
            ComponentRole.HEATMAP,
            ComponentRole.CONTOUR,
        }
        object_ids = {
            controller.component_id
            for controller in canvas.component_registry.query()
            if controller.state.role in data_roles
        }
        save_project_snapshot(self.path, self.window.figure_window)

        loaded = MainWindow()
        try:
            restore_project_snapshot(self.path, loaded.table, loaded.figure_window)
            restored = loaded.figure_window.current_canva
            restored_ids = {
                controller.component_id
                for controller in restored.component_registry.query()
                if controller.state.role in data_roles
            }
            self.assertEqual(restored_ids, object_ids)
            reference = restored.component_registry.get(
                "roundtrip-reference-marks"
            )
            self.assertEqual(
                reference.state.data["positions"],
                [15.2, 15.2, 22.9],
            )
            self.assertIsNone(reference.state.data["position_ref"])
            reference_target = reference.resolve_target()
            self.assertIsInstance(reference_target, LineCollection)
            self.assertEqual(len(reference_target.get_segments()), 3)
            self.assertEqual(
                sum(
                    target is reference_target
                    for axes in restored.fig.axes
                    for target in axes.collections
                ),
                1,
            )
            expected_dynamic_keys = set(validate_controller_contracts())
            self.assertEqual(
                {
                    (controller.state.kind, controller.state.role)
                    for controller in restored.component_registry.query()
                    if (controller.state.kind, controller.state.role)
                    in expected_dynamic_keys
                },
                expected_dynamic_keys,
            )
            for key in expected_dynamic_keys:
                with self.subTest(kind=key[0].value, role=key[1].value):
                    self.assertTrue(
                        restored.component_registry.query(
                            kind=key[0],
                            role=key[1],
                        )
                    )
            for role in data_roles:
                self.assertEqual(
                    len(
                        restored.component_registry.query(role=role)
                    ),
                    1,
                )
            fit = restored.component_registry.query(
                role=ComponentRole.FIT_CURVE
            )[0]
            self.assertEqual(
                fit.state.properties["color"].casefold(),
                "#0000ff",
            )
            restored_order = [
                controller.state.order
                for controller in restored.component_registry.query(
                    capabilities={"color", "data"},
                    parent_id=restored.current_axes_component_id,
                    recursive=True,
                )
            ]
            self.assertEqual(
                restored_order,
                [0, 1, 2, 3, 4, 5, reference.state.order],
            )
            self.assertEqual(
                len(
                    restored.component_registry.query(
                        role=ComponentRole.TEXT
                    )
                ),
                2,
            )
        finally:
            loaded.close()
            self.app.processEvents()

    def test_requested_tex_mode_survives_restore_without_tex_runtime(self):
        self.window.figure_window.add_figure(
            width=4, height=3, dpi=100, style="default", canva_name="ProjectA"
        )
        canvas = self.window.figure_window.current_canva
        create_regular_axes(canvas)
        tex_config.set_tex_enabled(True, notify=False)
        with patch.object(canvas.fig.canvas, "draw"):
            canvas.add_text(
                0.25,
                0.75,
                r"$x^2$",
                "DejaVu Sans",
                12,
                usetex=True,
            )
            annotation_artist = canvas.add_annotation(
                {
                    "text": r"$T_N$",
                    "xy": (0.5, 0.5),
                    "usetex": True,
                },
                object_id="tex-roundtrip-annotation",
                announce=False,
            )
        source = canvas.component_registry.query(role=ComponentRole.TEXT)[0]
        source_annotation = canvas.component_registry.get(
            annotation_artist.get_gid()
        )
        self.assertTrue(source.read_state().properties["usetex"])
        self.assertTrue(
            source_annotation.read_state().properties["usetex"]
        )

        tex_config.set_tex_enabled(False, notify=False)
        source.resolve_target().set_usetex(False)
        source_annotation.resolve_target().set_usetex(False)
        save_project_snapshot(self.path, self.window.figure_window)

        loaded = MainWindow()
        second_path = Path(self.directory.name) / "objects-resaved.mygui.json"
        try:
            restore_project_snapshot(self.path, loaded.table, loaded.figure_window)
            restored = loaded.figure_window.current_canva
            controller = restored.component_registry.query(
                role=ComponentRole.TEXT
            )[0]
            self.assertTrue(controller.read_state().properties["usetex"])
            self.assertFalse(controller.resolve_target().get_usetex())
            annotation = restored.component_registry.get(
                "tex-roundtrip-annotation"
            )
            self.assertTrue(annotation.read_state().properties["usetex"])
            self.assertFalse(annotation.resolve_target().get_usetex())

            save_project_snapshot(second_path, loaded.figure_window)
            self.assertIn('"usetex": true', second_path.read_text(encoding="utf-8"))
        finally:
            loaded.close()
            self.app.processEvents()


if __name__ == "__main__":
    unittest.main()
