import json
import os
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path

from tests.axes_helpers import create_regular_axes

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from mygui.database import ColumnRef
from mygui.project_io import (
    PROJECT_SCHEMA_VERSION,
    load_project_file,
    project_snapshot,
    restore_project_snapshot,
    validate_project_snapshot,
)
from main import MainWindow


class ProjectSchemaV12Tests(unittest.TestCase):
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
            canva_name="ProjectA",
        )
        self.canvas = self.window.figure_window.current_canva
        create_regular_axes(self.canvas)
        self.sheet = self.window.table.current_subtable().get_table(0).table_model.sheet
        self.sheet.set_block(0, 0, [[0, 1], [1, 2], [2, 4]])
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
        self.canvas.add_curve("x**2", 0, 2, "-", "tab:blue", "curve")
        pair = self.window.repository.line_pair(self.x_ref, self.y_ref)
        self.canvas.add_plot(
            pair.x,
            pair.y,
            "--",
            3,
            "#11223380",
            "plot",
            self.x_ref,
            self.y_ref,
            object_id="plot-object",
        )

    def tearDown(self):
        self.window.close()
        self.app.processEvents()

    def snapshot(self):
        return project_snapshot(self.window.figure_window)

    @staticmethod
    def component(snapshot, role):
        return next(
            component
            for component in snapshot["figure"]["components"]
            if component["role"] == role
        )

    def test_generic_line_uses_finite_equal_length_persisted_xy(self):
        snapshot = self.snapshot()
        function_curve = self.component(snapshot, "function_curve")
        generic_line = {
            "id": "native-generic-line",
            "kind": "line",
            "role": "line",
            "parent_id": function_curve["parent_id"],
            "order": max(
                component["order"]
                for component in snapshot["figure"]["components"]
                if component["kind"] in {"line", "scatter"}
            ) + 1,
            "selector": {"object_id": "native-generic-line"},
            "properties": deepcopy(function_curve["properties"]),
            "data": {"x": [0.0, 1.5, 3.0], "y": [2.0, -1.0, 4.5]},
        }
        snapshot["figure"]["components"].append(generic_line)

        validate_project_snapshot(snapshot)

        invalid_states = (
            ({}, "data.x"),
            ({"x": [0.0, 1.0], "y": [1.0]}, "equal length"),
            ({"x": [0.0], "y": ["bad"]}, "expected number"),
            ({"x": [0.0], "y": [float("inf")]}, "finite"),
        )
        for data, message in invalid_states:
            with self.subTest(data=data):
                candidate = deepcopy(snapshot)
                self.component(candidate, "line")["data"] = data
                with self.assertRaisesRegex(ValueError, message):
                    validate_project_snapshot(candidate)

    def test_schema_v12_reference_marks_exact_contract_and_rejections(self):
        self.canvas.add_reference_marks(
            [15.2, 15.2, 22.9],
            {
                "label": "YBCO",
                "baseline": 0.12,
                "height": 0.04,
                "color": "#123456",
            },
            object_id="reference-ybco",
            announce=False,
        )
        valid = self.snapshot()
        self.assertEqual(valid["schema_version"], 12)
        component = self.component(valid, "reflection_positions")
        self.assertEqual(
            set(component),
            {
                "id",
                "kind",
                "role",
                "parent_id",
                "order",
                "selector",
                "properties",
                "data",
            },
        )
        self.assertEqual(component["kind"], "reference_marks")
        self.assertEqual(
            component["selector"],
            {"object_id": "reference-ybco"},
        )
        self.assertEqual(
            set(component["properties"]),
            {
                "label",
                "visible",
                "baseline",
                "height",
                "color",
                "linewidth",
                "linestyle",
                "alpha",
                "zorder",
                "clip_on",
            },
        )
        self.assertEqual(component["data"], {"positions": [15.2, 15.2, 22.9]})
        validate_project_snapshot(valid)

        predecessor = deepcopy(valid)
        predecessor["schema_version"] = 11
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "v11-cannot-contain-reference-marks.json"
            path.write_text(json.dumps(predecessor), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "schema v11"):
                load_project_file(path)

        invalid_mutations = (
            lambda item: item["selector"].update(index=0),
            lambda item: item["properties"].pop("height"),
            lambda item: item["properties"].update(unknown=True),
            lambda item: item["properties"].update(baseline=-0.1),
            lambda item: item["properties"].update(height=0.0),
            lambda item: item["properties"].update(baseline=0.99, height=0.02),
            lambda item: item["data"].update(unknown=[]),
            lambda item: item["data"].update(positions="15.2, 22.9"),
            lambda item: item["data"].update(positions=[15.2, True]),
            lambda item: item["data"].update(positions=[float("nan")]),
            lambda item: item.update(parent_id=item["parent_id"] + "/xaxis"),
        )
        for index, mutate in enumerate(invalid_mutations):
            with self.subTest(index=index):
                candidate = deepcopy(valid)
                mutate(self.component(candidate, "reflection_positions"))
                with self.assertRaises(ValueError):
                    validate_project_snapshot(candidate)

    def test_schema_v10_and_v11_migrate_to_v12_without_rewriting_components(self):
        current = self.snapshot()
        original_components = deepcopy(current["figure"]["components"])
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for source_version in (10, 11):
                with self.subTest(source_version=source_version):
                    source = deepcopy(current)
                    source["schema_version"] = source_version
                    path = root / f"schema-v{source_version}.mygui.json"
                    path.write_text(json.dumps(source), encoding="utf-8")
                    migrated = load_project_file(path)
                    self.assertEqual(migrated["schema_version"], 12)
                    self.assertEqual(
                        migrated["figure"]["components"],
                        original_components,
                    )

    def test_only_exact_integer_v10_v11_and_v12_are_accepted(self):
        current = self.snapshot()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for version in (4, 9, 13, True, 12.0, "12"):
                with self.subTest(version=version):
                    candidate = deepcopy(current)
                    candidate["schema_version"] = version
                    path = root / f"unsupported-{str(version)}.json"
                    path.write_text(json.dumps(candidate), encoding="utf-8")
                    with self.assertRaisesRegex(ValueError, "schema version"):
                        load_project_file(path)

        self.assertEqual(PROJECT_SCHEMA_VERSION, 12)

    def test_validation_rejects_invalid_graph_and_component_state(self):
        valid = self.snapshot()
        cases = {}

        duplicate_id = deepcopy(valid)
        self.component(duplicate_id, "data_plot")["id"] = self.component(
            duplicate_id,
            "function_curve",
        )["id"]
        cases["Duplicate component id"] = duplicate_id

        unknown_kind = deepcopy(valid)
        self.component(unknown_kind, "data_plot")["kind"] = "image"
        cases["Unknown component kind"] = unknown_kind

        missing_parent = deepcopy(valid)
        self.component(missing_parent, "data_plot")["parent_id"] = "missing"
        cases["Unknown parent component"] = missing_parent

        missing_legend = deepcopy(valid)
        missing_legend["figure"]["components"] = [
            component
            for component in missing_legend["figure"]["components"]
            if component["role"] != "legend"
        ]
        cases["legend component"] = missing_legend

        extra_figure_field = deepcopy(valid)
        extra_figure_field["figure"]["axes"] = []
        cases["must contain only"] = extra_figure_field

        for message, snapshot in cases.items():
            with self.subTest(message=message):
                with self.assertRaisesRegex(ValueError, message):
                    validate_project_snapshot(snapshot)

    def test_validation_rejects_bad_selector_order_color_and_reference(self):
        valid = self.snapshot()
        cases = {}

        duplicate_order = deepcopy(valid)
        self.component(duplicate_order, "data_plot")["order"] = self.component(
            duplicate_order,
            "function_curve",
        )["order"]
        cases["order values must be unique"] = duplicate_order

        invalid_color = deepcopy(valid)
        self.component(invalid_color, "data_plot")["properties"]["color"] = "bad-color"
        cases["properties.color"] = invalid_color

        invalid_ref = deepcopy(valid)
        self.component(invalid_ref, "data_plot")["data"]["x_ref"]["column_id"] = "missing"
        cases["Invalid data reference"] = invalid_ref

        unsafe_expression = deepcopy(valid)
        self.component(unsafe_expression, "function_curve")["data"]["expression"] = (
            "__import__('os').system('echo unsafe')"
        )
        cases["expression is invalid"] = unsafe_expression

        unknown_property = deepcopy(valid)
        self.component(unknown_property, "axes")["properties"]["unsupported"] = True
        cases["unknown"] = unknown_property

        for message, snapshot in cases.items():
            with self.subTest(message=message):
                with self.assertRaisesRegex(ValueError, message):
                    validate_project_snapshot(snapshot)

    def test_root_project_and_table_fields_are_exact(self):
        valid = self.snapshot()
        cases = []
        for path in ("root", "project", "table", "sheet", "column"):
            candidate = deepcopy(valid)
            if path == "root":
                candidate["unsupported"] = True
            elif path == "project":
                candidate["project"]["unsupported"] = True
            elif path == "table":
                candidate["table"]["unsupported"] = True
            elif path == "sheet":
                candidate["table"]["sheets"][0]["unsupported"] = True
            else:
                candidate["table"]["sheets"][0]["columns"][0]["unsupported"] = True
            cases.append((path, candidate))

        for path, candidate in cases:
            with self.subTest(path=path):
                with self.assertRaisesRegex(ValueError, "expected exactly"):
                    validate_project_snapshot(candidate)

    def test_invalid_current_file_is_rejected_before_application_state_changes(self):
        snapshot = self.snapshot()
        self.component(snapshot, "data_plot")["parent_id"] = "missing"

        class Sentinel:
            repository = None
            called = False

            def load_project_table_snapshot(self, _snapshot):
                self.called = True

        sentinel = Sentinel()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "invalid.mygui.json"
            path.write_text(json.dumps(snapshot), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "Unknown parent component"):
                restore_project_snapshot(path, table=sentinel, figure_window=None)
        self.assertFalse(sentinel.called)

    def test_nonstandard_json_numbers_are_rejected_before_validation(self):
        snapshot = self.snapshot()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "invalid-number.mygui.json"
            payload = json.dumps(snapshot).replace('"dpi": 100.0', '"dpi": NaN')
            path.write_text(payload, encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "Invalid JSON numeric constant"):
                load_project_file(path)

    def test_figure_name_must_match_project_name(self):
        snapshot = self.snapshot()
        self.component(snapshot, "figure")["properties"]["name"] = ""

        with self.assertRaisesRegex(
            ValueError,
            "Project and Figure component names must match",
        ):
            validate_project_snapshot(snapshot)


if __name__ == "__main__":
    unittest.main()
