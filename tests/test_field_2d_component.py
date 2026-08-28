"""Runtime, Colorbar, history, and schema-v16 coverage for FIELD_2D charts."""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path
from unittest import mock

from tests.axes_helpers import create_regular_axes

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
from matplotlib.cm import ScalarMappable
from matplotlib.collections import QuadMesh
from matplotlib.contour import QuadContourSet
from matplotlib.image import AxesImage
from PySide6.QtWidgets import QApplication

from main import MainWindow
from mygui import status_messages
from mygui.database import ColumnRef, ColumnType, TableChangeSet
from mygui.figuremodify.components import (
    ChangeStatus,
    ComponentKind,
    ComponentRole,
    ComponentValidationError,
)
from mygui.figuremodify.components.serialization import (
    validate_v15_figure,
    validate_v16_figure,
)
from mygui.figuremodify.field_2d_runtime import Field2DRuntime
from mygui.project_io import (
    PROJECT_SCHEMA_VERSION,
    load_project_file,
    restore_project_snapshot,
    save_project_snapshot,
    validate_project_snapshot,
    validate_v15_project_snapshot,
)
from tests.schema_helpers import as_schema_v15, figure_as_schema_v18
from mygui.widgets.common_widget.min_widget.color_library import ColorLibrary
from mygui.widgets.fig_control_window.component_editors.spec_editors import (
    ColorMapSpecEditor,
    ContourLabelSpecEditor,
    ContourLevelsSpecEditor,
    GridEdgeSpecEditor,
)


GRID_ROWS = [
    [0.0, 0.0, 1.0],
    [1.0, 0.0, 2.0],
    [0.0, 1.0, 3.0],
    [1.0, 1.0, 4.0],
]


class Field2DComponentTests(unittest.TestCase):
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
            canva_name="Field2DProject",
        )
        self.canvas = self.window.figure_window.current_canva
        create_regular_axes(self.canvas)
        self.sheet = (
            self.window.table.current_subtable()
            .get_table(0)
            .table_model.sheet
        )
        self.sheet.set_block(0, 0, GRID_ROWS)
        self.x_ref = ColumnRef(
            self.canvas.project_id,
            self.sheet.id,
            self.sheet.columns[0].id,
        )
        self.y_ref = ColumnRef(
            self.canvas.project_id,
            self.sheet.id,
            self.sheet.columns[1].id,
        )
        self.z_ref = ColumnRef(
            self.canvas.project_id,
            self.sheet.id,
            self.sheet.columns[2].id,
        )

    def tearDown(self):
        status_messages.clear_status_handler()
        self.window.close_without_prompt()
        self.app.processEvents()

    def add_chart(self, method, object_id, **kwargs):
        getattr(self.canvas, method)(
            self.x_ref,
            self.y_ref,
            self.z_ref,
            object_id=object_id,
            **kwargs,
        )
        return self.canvas.component_registry.get(object_id)

    def test_compound_editors_are_closed_tagged_controls(self):
        library = ColorLibrary()
        colormap = ColorMapSpecEditor(
            {
                "cmap": "viridis",
                "norm": {
                    "kind": "linear",
                    "params": {"vmin": None, "vmax": None, "clip": False},
                },
                "bad": "#00000000",
                "under": None,
                "over": None,
            },
            color_library=library,
        )
        edge = GridEdgeSpecEditor({"kind": "none"}, color_library=library)
        levels = ContourLevelsSpecEditor({"kind": "count", "count": 8})
        labels = ContourLabelSpecEditor(
            {
                "enabled": False,
                "fmt": "general",
                "fontsize": 10.0,
                "color": None,
                "inline": True,
                "inline_spacing": 5.0,
            },
            color_library=library,
        )
        try:
            self.assertEqual(colormap.value()["cmap"], "viridis")
            self.assertEqual(edge.value(), {"kind": "none"})
            self.assertEqual(levels.value()["count"], 8)
            self.assertFalse(labels.value()["enabled"])
        finally:
            colormap.close()
            edge.close()
            levels.close()
            labels.close()

    def test_pseudocolor_heatmap_and_contour_create_and_refresh(self):
        pseudo = self.add_chart("add_pseudocolor", "pseudo-1")
        heat = self.add_chart("add_heatmap", "heat-1")
        contour = self.add_chart("add_contour", "contour-1")
        self.assertIsInstance(pseudo.resolve_target().primary, QuadMesh)
        self.assertIsInstance(heat.resolve_target().primary, AxesImage)
        self.assertIsInstance(contour.resolve_target().primary, QuadContourSet)
        self.assertEqual(heat.resolve_target().primary.origin, "lower")
        self.assertEqual(pseudo.state.kind, ComponentKind.FIELD_2D)
        self.assertEqual(pseudo.state.role, ComponentRole.PSEUDOCOLOR)
        self.assertEqual(set(pseudo.state.data), {"x_ref", "y_ref", "z_ref"})
        self.assertNotEqual(pseudo.state.order, heat.state.order)

        before = np.ma.filled(pseudo.resolve_target().mappable.get_array(), np.nan).copy()
        with self.window.repository.mutate(
            TableChangeSet(
                self.canvas.project_id,
                {self.z_ref},
                reason="field-2d-refresh",
            )
        ):
            self.sheet.set_block(0, 2, [[10.0], [20.0], [30.0], [40.0]])
        self.app.processEvents()
        after = np.ma.filled(pseudo.resolve_target().mappable.get_array(), np.nan)
        self.assertFalse(np.array_equal(before, after))

    def test_contour_modes_and_labels(self):
        lines = self.add_chart(
            "add_contour",
            "contour-lines",
            properties={"mode": "lines"},
        )
        filled = self.add_chart(
            "add_contour",
            "contour-filled",
            properties={"mode": "filled"},
        )
        overlay = self.add_chart(
            "add_contour",
            "contour-overlay",
            properties={"mode": "overlay"},
        )
        self.assertIs(lines.resolve_target().primary, lines.resolve_target().lines)
        self.assertIs(filled.resolve_target().primary, filled.resolve_target().filled)
        self.assertIs(overlay.resolve_target().mappable, overlay.resolve_target().filled)
        self.assertIsNotNone(overlay.resolve_target().lines)

        change = self.canvas.field_2d_service.apply_properties(
            filled,
            {
                "labels": {
                    "enabled": True,
                    "fmt": "general",
                    "fontsize": 9.0,
                    "color": None,
                    "inline": True,
                    "inline_spacing": 5.0,
                }
            },
        )
        self.assertTrue(change.ok)
        runtime = filled.resolve_target()
        self.assertTrue(runtime.labels)
        self.assertFalse(runtime.lines.get_visible())

    def test_construction_rebuild_rolls_back_artist_identity(self):
        controller = self.add_chart("add_pseudocolor", "pseudo-rebuild")
        old = controller.resolve_target()
        old_primary = old.primary
        locator = self.canvas.component_registry.locator
        with mock.patch.object(
            self.canvas.field_2d_service,
            "_verify_render",
            side_effect=RuntimeError("injected FIELD_2D draw failure"),
        ):
            change = self.canvas.field_2d_service.apply_properties(
                controller,
                {"shading": "gouraud"},
            )
        self.assertIs(change.status, ChangeStatus.REJECTED)
        restored = controller.resolve_target()
        self.assertIs(restored, old)
        self.assertIs(restored.primary, old_primary)
        self.assertIs(locator.bound_target(controller.component_id), old)
        self.assertEqual(controller.state.properties["shading"], "auto")

        rebuilt = self.canvas.field_2d_service.apply_properties(
            controller,
            {"shading": "gouraud"},
        )
        self.assertTrue(rebuilt.ok)
        self.assertIsNot(controller.resolve_target(), old)
        self.assertEqual(controller.state.properties["shading"], "gouraud")

    def test_empty_component_keeps_placeholder_and_rejects_new_colorbar(self):
        self.sheet.set_block(0, 2, [[None], [None], [None], [None]])
        controller = self.add_chart("add_contour", "contour-empty")
        runtime = controller.resolve_target()
        self.assertTrue(runtime.empty)
        self.assertIsInstance(runtime.mappable, ScalarMappable)
        self.assertFalse(runtime.has_drawable)
        with self.assertRaisesRegex(ComponentValidationError, "Empty FIELD_2D"):
            self.canvas.add_colorbar(controller.component_id, object_id="cbar-empty")
        self.assertNotIn("cbar-empty", self.canvas.component_registry)

    def test_duplicate_coordinates_roll_back_creation(self):
        self.sheet.set_block(
            0,
            0,
            [
                [0.0, 0.0, 1.0],
                [0.0, 0.0, 2.0],
            ],
        )
        with self.assertRaisesRegex(ComponentValidationError, "Duplicate"):
            self.canvas.add_pseudocolor(
                self.x_ref,
                self.y_ref,
                self.z_ref,
                object_id="pseudo-dup",
            )
        self.assertNotIn("pseudo-dup", self.canvas.component_registry)

    def test_cross_sheet_refs_are_rejected(self):
        other_view = self.window.table.current_subtable().add_new_sheet("Other")
        other = other_view.table_model.sheet
        other.set_block(0, 0, [[0.0], [1.0]])
        other_ref = ColumnRef(
            self.canvas.project_id,
            other.id,
            other.columns[0].id,
        )
        with self.assertRaisesRegex(ComponentValidationError, "same worksheet"):
            self.canvas.add_heatmap(
                self.x_ref,
                self.y_ref,
                other_ref,
                object_id="heat-cross",
            )
        self.assertNotIn("heat-cross", self.canvas.component_registry)

    def test_heatmap_rejects_uneven_spacing(self):
        self.sheet.set_block(
            0,
            0,
            [
                [0.0, 0.0, 1.0],
                [1.0, 0.0, 2.0],
                [3.0, 0.0, 3.0],
                [0.0, 1.0, 4.0],
                [1.0, 1.0, 5.0],
                [3.0, 1.0, 6.0],
            ],
        )
        with self.assertRaisesRegex(ComponentValidationError, "equally spaced"):
            self.canvas.add_heatmap(
                self.x_ref,
                self.y_ref,
                self.z_ref,
                object_id="heat-uneven",
            )

    def test_delete_and_undo_redo(self):
        controller = self.add_chart("add_pseudocolor", "pseudo-history")
        stack = self.window.repository.undo_stack(self.canvas.project_id)
        self.assertGreaterEqual(stack.count(), 1)
        stack.undo()
        self.assertNotIn("pseudo-history", self.canvas.component_registry)
        stack.redo()
        restored = self.canvas.component_registry.get("pseudo-history")
        self.assertIsInstance(restored.resolve_target(), Field2DRuntime)
        self.canvas.select_component(controller.component_id)
        stack.clear()
        self.assertTrue(self.canvas.delete_component_group((controller.component_id,)))
        self.assertNotIn("pseudo-history", self.canvas.component_registry)
        stack.undo()
        self.assertIn("pseudo-history", self.canvas.component_registry)
        self.assertIsInstance(
            self.canvas.component_registry.get("pseudo-history").resolve_target(),
            Field2DRuntime,
        )
        stack.redo()
        self.assertNotIn("pseudo-history", self.canvas.component_registry)

    def test_colorbar_for_each_role_refresh_empty_transition_and_cascade(self):
        sources = {
            "pseudo-cbar": self.add_chart("add_pseudocolor", "pseudo-cbar"),
            "heat-cbar": self.add_chart("add_heatmap", "heat-cbar"),
            "contour-cbar": self.add_chart("add_contour", "contour-cbar"),
        }
        locations = {"pseudo-cbar": "right", "heat-cbar": "left", "contour-cbar": "top"}
        with mock.patch.object(
            self.canvas.colorbar_service,
            "create_runtime",
            side_effect=RuntimeError("injected FIELD_2D Colorbar failure"),
        ):
            with self.assertRaisesRegex(RuntimeError, "injected FIELD_2D Colorbar failure"):
                self.canvas.add_colorbar(
                    sources["pseudo-cbar"].component_id,
                    object_id="cbar-failed",
                )
        self.assertNotIn("cbar-failed", self.canvas.component_registry)

        colorbars = {}
        for source_id, source in sources.items():
            self.canvas.add_colorbar(
                source.component_id,
                {"label": source_id, "location": locations[source_id]},
                object_id=f"cbar-{source_id}",
            )
            colorbars[source_id] = self.canvas.component_registry.get(
                f"cbar-{source_id}"
            )
            self.assertEqual(
                colorbars[source_id].state.data["source_component_id"],
                source.component_id,
            )

        with self.assertRaisesRegex(ComponentValidationError, "already has a Colorbar"):
            self.canvas.add_colorbar(sources["pseudo-cbar"].component_id)

        change = self.canvas.field_2d_service.apply_properties(
            sources["pseudo-cbar"],
            {
                "colormap": {
                    "cmap": "plasma",
                    "norm": {
                        "kind": "linear",
                        "params": {"vmin": None, "vmax": None, "clip": False},
                    },
                    "bad": "#00000000",
                    "under": None,
                    "over": None,
                }
            },
        )
        self.assertTrue(change.ok)
        self.assertEqual(
            colorbars["pseudo-cbar"].resolve_target().cmap.name,
            "plasma",
        )

        with self.window.repository.mutate(
            TableChangeSet(
                self.canvas.project_id,
                {self.z_ref},
                reason="field-2d-empty-transition",
            )
        ):
            self.sheet.set_block(0, 2, [[None], [None], [None], [None]])
        self.app.processEvents()
        empty_runtime = sources["heat-cbar"].resolve_target()
        self.assertTrue(empty_runtime.empty)
        self.assertIn("cbar-heat-cbar", self.canvas.component_registry)

        self.assertTrue(
            self.canvas.delete_component_group((sources["contour-cbar"].component_id,))
        )
        self.assertNotIn("contour-cbar", self.canvas.component_registry)
        self.assertNotIn("cbar-contour-cbar", self.canvas.component_registry)

    def test_schema_v17_round_trip_and_v15_rejection(self):
        self.add_chart("add_pseudocolor", "pseudo-save")
        self.add_chart("add_heatmap", "heat-save")
        self.add_chart("add_contour", "contour-save")
        self.canvas.add_colorbar("pseudo-save", object_id="cbar-save")
        snapshot = self.canvas.component_snapshot()
        validate_v16_figure(
            figure_as_schema_v18(snapshot),
            {
                self.x_ref: ColumnType.NUMBER,
                self.y_ref: ColumnType.NUMBER,
                self.z_ref: ColumnType.NUMBER,
            },
            self.canvas.project_id,
            self.canvas.project_name,
        )
        with self.assertRaisesRegex(ValueError, "FIELD_2D is not part"):
            validate_v15_figure(
                snapshot,
                {
                    self.x_ref: ColumnType.NUMBER,
                    self.y_ref: ColumnType.NUMBER,
                    self.z_ref: ColumnType.NUMBER,
                },
                self.canvas.project_id,
                self.canvas.project_name,
            )

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "field-2d.mygui.json"
            save_project_snapshot(path, self.window.figure_window)
            raw = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(raw["schema_version"], PROJECT_SCHEMA_VERSION)
            self.assertEqual(PROJECT_SCHEMA_VERSION, 19)
            roles = {
                component["role"]
                for component in raw["figure"]["components"]
                if component["kind"] == "field_2d"
            }
            self.assertEqual(roles, {"pseudocolor", "heatmap", "contour"})
            predecessor = as_schema_v15(raw)
            validate_v15_project_snapshot(predecessor)
            self.assertFalse(
                any(
                    component["kind"] == "field_2d"
                    for component in predecessor["figure"]["components"]
                )
            )
            v15_path = Path(directory) / "field-2d-v15.mygui.json"
            v15_path.write_text(json.dumps(predecessor), encoding="utf-8")
            migrated = load_project_file(v15_path)
            self.assertEqual(migrated["schema_version"], PROJECT_SCHEMA_VERSION)
            self.assertFalse(
                any(
                    component["kind"] == "field_2d"
                    for component in migrated["figure"]["components"]
                )
            )

            loaded = MainWindow()
            try:
                restore_project_snapshot(path, loaded.table, loaded.figure_window)
                restored = loaded.figure_window.current_canva
                self.assertIn("pseudo-save", restored.component_registry)
                self.assertIn("heat-save", restored.component_registry)
                self.assertIn("contour-save", restored.component_registry)
                self.assertIn("cbar-save", restored.component_registry)
                empty_ok = restored.component_registry.get("contour-save")
                self.assertTrue(empty_ok.resolve_target() is not None)
            finally:
                loaded.close_without_prompt()
                self.app.processEvents()

        illegal = deepcopy(raw)
        illegal["schema_version"] = 15
        with self.assertRaisesRegex(ValueError, "FIELD_2D is not part"):
            validate_v15_project_snapshot(illegal)
        with self.assertRaisesRegex(ValueError, "Unsupported project schema version 15"):
            validate_project_snapshot(illegal)


if __name__ == "__main__":
    unittest.main()
