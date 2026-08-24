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
    validate_v14_project_snapshot,
)
from main import MainWindow
from tests.schema_helpers import as_schema_v14


class ProjectSchemaV14Tests(unittest.TestCase):
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

    def test_schema_v14_reference_marks_exact_contract_and_rejections(self):
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
        self.assertEqual(valid["schema_version"], PROJECT_SCHEMA_VERSION)
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
        self.assertEqual(
            component["data"],
            {"positions": [15.2, 15.2, 22.9], "position_ref": None},
        )
        validate_project_snapshot(valid)
        predecessor_v14 = as_schema_v14(valid)
        self.assertEqual(
            self.component(predecessor_v14, "reflection_positions")["data"],
            {"positions": [15.2, 15.2, 22.9]},
        )
        validate_v14_project_snapshot(predecessor_v14)

        predecessor = as_schema_v14(valid)
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

    def test_schema_v14_reference_guides_exact_contract_and_rejections(self):
        self.canvas.add_reference_line(
            {
                "label": "threshold",
                "orientation": "vertical",
                "value": 2.5,
                "span_start": 0.1,
                "span_end": 0.9,
            },
            object_id="schema-reference-line",
            announce=False,
        )
        self.canvas.add_reference_band(
            {
                "label": "range",
                "orientation": "horizontal",
                "lower": -0.2,
                "upper": 0.2,
                "span_start": 0.25,
                "span_end": 0.75,
            },
            object_id="schema-reference-band",
            announce=False,
        )
        valid = self.snapshot()
        self.assertEqual(valid["schema_version"], PROJECT_SCHEMA_VERSION)
        line = self.component(valid, "reference_line")
        band = self.component(valid, "reference_band")
        self.assertEqual(line["kind"], "reference_guide")
        self.assertEqual(band["kind"], "reference_guide")
        self.assertEqual(line["selector"], {"object_id": "schema-reference-line"})
        self.assertEqual(band["selector"], {"object_id": "schema-reference-band"})
        self.assertEqual(line["data"], {})
        self.assertEqual(band["data"], {})
        self.assertEqual(
            set(line["properties"]),
            {
                "label", "visible", "orientation", "value", "span_start",
                "span_end", "color", "linewidth", "linestyle", "alpha",
                "zorder", "clip_on",
            },
        )
        self.assertEqual(
            set(band["properties"]),
            {
                "label", "visible", "orientation", "lower", "upper",
                "span_start", "span_end", "facecolor", "edgecolor",
                "linewidth", "linestyle", "alpha", "zorder", "clip_on",
            },
        )
        validate_project_snapshot(valid)

        predecessor = as_schema_v14(valid)
        predecessor["schema_version"] = 12
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "v12-cannot-contain-reference-guides.json"
            path.write_text(json.dumps(predecessor), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "schema v12"):
                load_project_file(path)

        invalid_mutations = (
            ("reference_line", lambda item: item["selector"].update(index=0)),
            ("reference_line", lambda item: item["properties"].pop("value")),
            ("reference_line", lambda item: item["properties"].update(unknown=True)),
            ("reference_line", lambda item: item["properties"].update(value=float("nan"))),
            ("reference_line", lambda item: item["properties"].update(value=float("inf"))),
            ("reference_line", lambda item: item["properties"].update(orientation="diagonal")),
            ("reference_line", lambda item: item["properties"].update(span_start=0.8, span_end=0.2)),
            ("reference_line", lambda item: item["data"].update(value=2.5)),
            ("reference_line", lambda item: item.update(parent_id=item["parent_id"] + "/xaxis")),
            ("reference_band", lambda item: item["properties"].update(lower=1.0, upper=1.0)),
            ("reference_band", lambda item: item["properties"].update(lower=2.0, upper=1.0)),
            ("reference_band", lambda item: item["properties"].update(lower=float("nan"))),
            ("reference_band", lambda item: item["properties"].update(upper=float("inf"))),
        )
        for index, (role, mutate) in enumerate(invalid_mutations):
            with self.subTest(index=index, role=role):
                candidate = deepcopy(valid)
                mutate(self.component(candidate, role))
                with self.assertRaises(ValueError):
                    validate_project_snapshot(candidate)

    def test_schema_v10_v11_and_v12_migrate_to_v15_without_rewriting_components(self):
        current = self.snapshot()
        original_components = deepcopy(current["figure"]["components"])
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for source_version in (10, 11, 12):
                with self.subTest(source_version=source_version):
                    source = as_schema_v14(current)
                    source["schema_version"] = source_version
                    path = root / f"schema-v{source_version}.mygui.json"
                    path.write_text(json.dumps(source), encoding="utf-8")
                    migrated = load_project_file(path)
                    self.assertEqual(migrated["schema_version"], PROJECT_SCHEMA_VERSION)
                    self.assertEqual(
                        migrated["figure"]["components"],
                        original_components,
                    )

    def test_schema_v13_tick_label_fontfamilies_migrate_to_strings_only(self):
        current = self.snapshot()
        predecessor = as_schema_v14(current)
        predecessor["schema_version"] = 13
        for component in predecessor["figure"]["components"]:
            if component["kind"] != "tick_label_group":
                continue
            family = component["properties"]["fontfamily"]
            component["properties"]["fontfamily"] = [family, "sans-serif"]

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "schema-v13-fontfamily.json"
            path.write_text(json.dumps(predecessor), encoding="utf-8")
            migrated = load_project_file(path)

        self.assertEqual(migrated, current)
        self.assertTrue(
            all(
                isinstance(component["properties"]["fontfamily"], str)
                for component in migrated["figure"]["components"]
                if component["kind"] == "tick_label_group"
            )
        )

    def test_schema_v13_rejects_invalid_tick_label_font_lists(self):
        current = self.snapshot()
        tick_label = next(
            component
            for component in current["figure"]["components"]
            if component["kind"] == "tick_label_group"
        )
        component_index = current["figure"]["components"].index(tick_label)
        for value in ([], ["DejaVu Sans", 3], [""], None):
            with self.subTest(value=value), tempfile.TemporaryDirectory() as directory:
                candidate = as_schema_v14(current)
                candidate["schema_version"] = 13
                candidate["figure"]["components"][component_index]["properties"][
                    "fontfamily"
                ] = value
                path = Path(directory) / "invalid-v13-fontfamily.json"
                path.write_text(json.dumps(candidate), encoding="utf-8")
                with self.assertRaisesRegex(ValueError, "fontfamily"):
                    load_project_file(path)

    def test_schema_v14_requires_nonempty_tick_label_font_string(self):
        current = self.snapshot()
        tick_label = next(
            component
            for component in current["figure"]["components"]
            if component["kind"] == "tick_label_group"
        )
        for value in (["DejaVu Sans"], "", None, 3):
            with self.subTest(value=value):
                candidate = deepcopy(current)
                candidate_tick = next(
                    component
                    for component in candidate["figure"]["components"]
                    if component["id"] == tick_label["id"]
                )
                candidate_tick["properties"]["fontfamily"] = value
                with self.assertRaisesRegex(ValueError, "fontfamily"):
                    validate_project_snapshot(candidate)

    def test_only_exact_integer_v10_through_v15_are_accepted(self):
        current = self.snapshot()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for version in (4, 9, 16, True, 14.0, 15.0, "14", "15"):
                with self.subTest(version=version):
                    candidate = deepcopy(current)
                    candidate["schema_version"] = version
                    path = root / f"unsupported-{str(version)}.json"
                    path.write_text(json.dumps(candidate), encoding="utf-8")
                    with self.assertRaisesRegex(ValueError, "schema version"):
                        load_project_file(path)

        self.assertEqual(PROJECT_SCHEMA_VERSION, 15)

    def test_schema_v15_axes_reserve_and_v14_migration_defaults(self):
        current = self.snapshot()
        axes = self.component(current, "axes")
        self.assertEqual(axes["properties"]["y_lower_reserve"], 0.0)
        predecessor = as_schema_v14(current)
        self.assertNotIn("y_lower_reserve", self.component(predecessor, "axes")["properties"])
        validate_v14_project_snapshot(predecessor)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "schema-v14.mygui.json"
            path.write_text(json.dumps(predecessor), encoding="utf-8")
            migrated = load_project_file(path)
        self.assertEqual(migrated, current)

        illegal = deepcopy(current)
        self.component(illegal, "axes")["properties"]["y_lower_reserve"] = 0.9
        with self.assertRaisesRegex(ValueError, "y_lower_reserve"):
            validate_project_snapshot(illegal)
        self.canvas.add_reference_marks([1.0], announce=False)
        with_marks = self.snapshot()
        self.component(with_marks, "reflection_positions")["data"]["position_ref"] = {
            "project_id": "missing",
            "sheet_id": "missing",
            "column_id": "missing",
        }
        with self.assertRaisesRegex(ValueError, "position_ref"):
            validate_project_snapshot(with_marks)

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
