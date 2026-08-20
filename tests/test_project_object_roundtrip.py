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

from mygui.database import ColumnRef
from mygui.database.interpolate_func import interpolate_dict
from mygui.figuremodify.components import (
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

        data_roles = {
            ComponentRole.DATA_PLOT,
            ComponentRole.SCATTER,
            ComponentRole.INTERPOLATION,
            ComponentRole.FIT_CURVE,
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
            self.assertEqual(restored_order, [0, 1, 2, 3, 4, 5])
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
        source = canvas.component_registry.query(role=ComponentRole.TEXT)[0]
        self.assertTrue(source.read_state().properties["usetex"])

        tex_config.set_tex_enabled(False, notify=False)
        source.resolve_target().set_usetex(False)
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

            save_project_snapshot(second_path, loaded.figure_window)
            self.assertIn('"usetex": true', second_path.read_text(encoding="utf-8"))
        finally:
            loaded.close()
            self.app.processEvents()


if __name__ == "__main__":
    unittest.main()
