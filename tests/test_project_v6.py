import json
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path

from code.database import ColumnRef, ProjectTableDocument
from code.project_io import (
    PROJECT_SCHEMA_NAME,
    migrate_project_snapshot,
    migrate_v4_to_v5,
    migrate_v5_to_v6,
    restore_project_snapshot,
    validate_project_snapshot,
)
from code.figuremodify.components.serialization import v6_figure_to_legacy


class ProjectV6Tests(unittest.TestCase):
    def setUp(self):
        self.table = ProjectTableDocument.create("ProjectA")
        self.sheet = next(iter(self.table.sheets.values()))
        self.sheet.set_block(0, 0, [[0, 1], [1, 2], [2, 4]])
        self.x_ref = ColumnRef(
            self.table.id, self.sheet.id, self.sheet.columns[0].id
        )
        self.y_ref = ColumnRef(
            self.table.id, self.sheet.id, self.sheet.columns[1].id
        )

    def legacy_figure(self):
        return {
            "name": self.table.name,
            "style": "default",
            "dpi": 100,
            "size_inches": [4, 3],
            "axes_count": 1,
            "axes_layouts": [
                {"nrows": 1, "ncols": 1, "start_index": 0, "count": 1}
            ],
            "axes": [
                {
                    "index": 0,
                    "color_cycle": None,
                    "xlim": [0, 2],
                    "ylim": [0, 4],
                    "xlabel": "X",
                    "ylabel": "Y",
                    "label_fontfamily": "DejaVu Sans",
                    "label_fontsize": 11,
                    "x_label_position": [0.5, 0],
                    "y_label_position": [0, 0.5],
                    "xaxis_visible": True,
                    "yaxis_visible": True,
                    "spines": {
                        name: {
                            "visible": True,
                            "position": ["outward", 0],
                        }
                        for name in ("left", "right", "bottom", "top")
                    },
                    "legend": {"visible": True, "loc": "best"},
                }
            ],
            "curves": [
                {
                    "color_order": 0,
                    "axes_index": 0,
                    "expression": "x**2",
                    "x_start": 0,
                    "x_stop": 2,
                    "style": "-",
                    "color": "tab:blue",
                    "label": "curve",
                }
            ],
            "plots": [
                {
                    "object_id": "plot-object",
                    "color_order": 1,
                    "axes_index": 0,
                    "x_ref": self.x_ref.to_dict(),
                    "y_ref": self.y_ref.to_dict(),
                    "style": "--",
                    "size": 3,
                    "color": "#11223380",
                    "label": "plot",
                }
            ],
            "scatters": [],
            "interpolates": [],
            "fits": [],
            "texts": [
                {
                    "scope": "axes",
                    "axes_index": 0,
                    "x": 0.25,
                    "y": 0.75,
                    "text": "note",
                    "fontfamily": "DejaVu Sans",
                    "fontsize": 12,
                    "usetex": False,
                }
            ],
        }

    def snapshot(self, version=5):
        return {
            "schema": PROJECT_SCHEMA_NAME,
            "schema_version": version,
            "project": {"id": self.table.id, "name": self.table.name},
            "table": self.table.to_snapshot(),
            "figure": self.legacy_figure(),
        }

    @staticmethod
    def component(snapshot, role):
        return next(
            component
            for component in snapshot["figure"]["components"]
            if component["role"] == role
        )

    def test_v5_migration_is_pure_deterministic_and_preserves_object_ids(self):
        original = self.snapshot()
        untouched = deepcopy(original)

        first = migrate_v5_to_v6(original)
        second = migrate_v5_to_v6(original)

        self.assertEqual(original, untouched)
        self.assertEqual(first, second)
        self.assertEqual(first["schema_version"], 6)
        self.assertEqual(
            set(first["figure"]),
            {"root_component_id", "components"},
        )
        self.assertEqual(self.component(first, "data_plot")["id"], "plot-object")
        self.assertEqual(
            self.component(first, "function_curve")["properties"]["color"],
            "#1F77B4",
        )
        plot_properties = self.component(first, "data_plot")["properties"]
        self.assertEqual(plot_properties["linestyle"], "--")
        self.assertEqual(plot_properties["markersize"], 3)
        self.assertNotIn("style", plot_properties)
        self.assertNotIn("size", plot_properties)
        self.assertEqual(
            self.component(first, "text")["properties"]["position"],
            [0.25, 0.75],
        )
        self.assertEqual(
            self.component(first, "legend")["properties"]["location"],
            "best",
        )
        self.assertEqual(
            self.component(first, "axes")["properties"]["xscale"],
            "linear",
        )

        roles = [component["role"] for component in first["figure"]["components"]]
        self.assertEqual(roles.count("figure"), 1)
        self.assertEqual(roles.count("axes"), 1)
        self.assertEqual(roles.count("x_axis"), 1)
        self.assertEqual(roles.count("y_axis"), 1)
        self.assertEqual(roles.count("spine"), 4)
        self.assertEqual(roles.count("major_tick"), 2)
        self.assertEqual(roles.count("minor_tick"), 2)
        self.assertEqual(roles.count("major_tick_label"), 2)
        self.assertEqual(roles.count("minor_tick_label"), 2)
        self.assertEqual(roles.count("grid"), 4)
        self.assertEqual(roles.count("title"), 1)
        self.assertEqual(roles.count("x_label"), 1)
        self.assertEqual(roles.count("y_label"), 1)
        self.assertEqual(roles.count("legend"), 1)
        validate_project_snapshot(first)

        legacy = v6_figure_to_legacy(first["figure"])
        self.assertEqual(legacy["plots"][0]["object_id"], "plot-object")
        self.assertEqual(legacy["plots"][0]["x_ref"], self.x_ref.to_dict())
        self.assertEqual(legacy["curves"][0]["expression"], "x**2")
        self.assertEqual(legacy["texts"][0]["text"], "note")
        self.assertEqual(
            legacy["curves"][0]["object_id"],
            self.component(first, "function_curve")["id"],
        )
        self.assertEqual(
            legacy["texts"][0]["object_id"],
            self.component(first, "text")["id"],
        )

        remigration_input = deepcopy(first)
        remigration_input["schema_version"] = 5
        remigration_input["figure"] = legacy
        remigrated = migrate_v5_to_v6(remigration_input)
        self.assertEqual(
            self.component(remigrated, "function_curve")["id"],
            self.component(first, "function_curve")["id"],
        )
        self.assertEqual(
            self.component(remigrated, "text")["id"],
            self.component(first, "text")["id"],
        )

        native_state = deepcopy(first)
        self.component(native_state, "axes")["properties"]["xlim"] = (0.0, 2.0)
        normalized = migrate_project_snapshot(native_state)
        self.assertIsInstance(
            self.component(normalized, "axes")["properties"]["xlim"],
            list,
        )
        self.assertIsInstance(
            self.component(native_state, "axes")["properties"]["xlim"],
            tuple,
        )

    def test_v4_pipeline_adds_missing_v5_state_then_builds_v6(self):
        v4 = self.snapshot(version=4)
        v4["figure"]["axes"][0].pop("color_cycle")
        for collection in ("curves", "plots", "scatters", "interpolates", "fits"):
            for record in v4["figure"][collection]:
                record.pop("color_order", None)
        original = deepcopy(v4)

        v5 = migrate_v4_to_v5(v4)
        migrated = migrate_project_snapshot(v4)

        self.assertEqual(v4, original)
        self.assertEqual(v5["schema_version"], 5)
        self.assertIsNone(v5["figure"]["axes"][0]["color_cycle"])
        self.assertEqual(v5["figure"]["curves"][0]["color_order"], 0)
        self.assertEqual(v5["figure"]["plots"][0]["color_order"], 1)
        self.assertEqual(migrated["schema_version"], 6)
        validate_project_snapshot(migrated)

    def test_generic_line_uses_persisted_xy_and_a_separate_legacy_collection(self):
        snapshot = migrate_v5_to_v6(self.snapshot())
        function_curve = self.component(snapshot, "function_curve")
        generic_line = {
            "id": "native-generic-line",
            "kind": "line",
            "role": "line",
            "parent_id": function_curve["parent_id"],
            "order": 2,
            "selector": {"object_id": "native-generic-line"},
            "properties": deepcopy(function_curve["properties"]),
            "data": {
                "x": [0.0, 1.5, 3.0],
                "y": [2.0, -1.0, 4.5],
            },
        }
        snapshot["figure"]["components"].append(generic_line)

        validate_project_snapshot(snapshot)
        legacy = v6_figure_to_legacy(snapshot["figure"])

        self.assertEqual(len(legacy["lines"]), 1)
        self.assertEqual(legacy["lines"][0]["object_id"], "native-generic-line")
        self.assertEqual(legacy["lines"][0]["x"], generic_line["data"]["x"])
        self.assertEqual(legacy["lines"][0]["y"], generic_line["data"]["y"])
        self.assertEqual(len(legacy["curves"]), 1)
        self.assertEqual(legacy["curves"][0]["expression"], "x**2")

        remigration_input = deepcopy(snapshot)
        remigration_input["schema_version"] = 5
        remigration_input["figure"] = legacy
        remigrated = migrate_v5_to_v6(remigration_input)
        restored = self.component(remigrated, "line")

        self.assertEqual(restored["id"], generic_line["id"])
        self.assertEqual(restored["data"], generic_line["data"])
        self.assertEqual(restored["properties"], generic_line["properties"])

    def test_generic_line_rejects_missing_mismatched_or_non_numeric_xy(self):
        valid = migrate_v5_to_v6(self.snapshot())
        function_curve = self.component(valid, "function_curve")
        generic_line = {
            "id": "invalid-generic-line",
            "kind": "line",
            "role": "line",
            "parent_id": function_curve["parent_id"],
            "order": 2,
            "selector": {"object_id": "invalid-generic-line"},
            "properties": deepcopy(function_curve["properties"]),
            "data": {"x": [0.0], "y": [1.0]},
        }
        valid["figure"]["components"].append(generic_line)

        invalid_states = (
            ({}, "data.x"),
            ({"x": [0.0, 1.0], "y": [1.0]}, "equal length"),
            ({"x": [0.0], "y": ["bad"]}, "expected number"),
        )
        for data, message in invalid_states:
            with self.subTest(data=data):
                candidate = deepcopy(valid)
                self.component(candidate, "line")["data"] = data
                with self.assertRaisesRegex(ValueError, message):
                    validate_project_snapshot(candidate)

    def test_validation_rejects_invalid_graph_and_component_state(self):
        valid = migrate_v5_to_v6(self.snapshot())
        cases = {}

        duplicate_id = deepcopy(valid)
        duplicate_id["figure"]["components"][-1]["id"] = duplicate_id["figure"]["components"][0]["id"]
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
        valid = migrate_v5_to_v6(self.snapshot())
        cases = {}

        duplicate_selector = deepcopy(valid)
        source = next(
            component
            for component in duplicate_selector["figure"]["components"]
            if component["kind"] == "spine"
        )
        duplicate = deepcopy(source)
        duplicate["id"] = "duplicate-spine"
        duplicate_selector["figure"]["components"].append(duplicate)
        cases["Duplicate semantic selector"] = duplicate_selector

        duplicate_fixed_semantic = deepcopy(valid)
        source = next(
            component
            for component in duplicate_fixed_semantic["figure"]["components"]
            if component["kind"] == "spine"
            and component["selector"]["name"] == "left"
        )
        duplicate = deepcopy(source)
        duplicate["id"] = "duplicate-left-spine"
        duplicate["selector"]["extra"] = "bypass-full-selector-equality"
        duplicate_fixed_semantic["figure"]["components"].append(duplicate)
        cases["exactly one of each standard spine"] = duplicate_fixed_semantic

        duplicate_order = deepcopy(valid)
        self.component(duplicate_order, "data_plot")["order"] = self.component(
            duplicate_order, "function_curve"
        )["order"]
        cases["order values must be unique"] = duplicate_order

        invalid_color = deepcopy(valid)
        self.component(invalid_color, "data_plot")["properties"]["color"] = "bad-color"
        cases["properties.color"] = invalid_color

        invalid_ref = deepcopy(valid)
        self.component(invalid_ref, "data_plot")["data"]["x_ref"]["column_id"] = "missing"
        cases["Invalid data reference"] = invalid_ref

        invalid_size = deepcopy(valid)
        self.component(invalid_size, "data_plot")["properties"]["markersize"] = "large"
        cases["expected number"] = invalid_size

        invalid_enum = deepcopy(valid)
        self.component(invalid_enum, "major_tick")["properties"][
            "direction"
        ] = "sideways"
        cases["must be one of"] = invalid_enum

        unsafe_expression = deepcopy(valid)
        self.component(unsafe_expression, "function_curve")["data"][
            "expression"
        ] = "__import__('os').system('echo unsafe')"
        cases["expression is invalid"] = unsafe_expression

        unknown_property = deepcopy(valid)
        self.component(unknown_property, "axes")["properties"][
            "unsupported"
        ] = True
        cases["unknown"] = unknown_property

        unknown_data = deepcopy(valid)
        self.component(unknown_data, "data_plot")["data"][
            "unsupported"
        ] = True
        cases["data fields"] = unknown_data

        for message, snapshot in cases.items():
            with self.subTest(message=message):
                with self.assertRaisesRegex(ValueError, message):
                    validate_project_snapshot(snapshot)

    def test_invalid_v6_file_is_rejected_before_application_state_changes(self):
        snapshot = migrate_v5_to_v6(self.snapshot())
        self.component(snapshot, "data_plot")["parent_id"] = "missing"

        class Sentinel:
            def __init__(self):
                self.repository = None
                self.called = False

            def load_project_table_snapshot(self, _snapshot):
                self.called = True

        sentinel = Sentinel()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "invalid.mygui.json"
            path.write_text(json.dumps(snapshot), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "Unknown parent component"):
                restore_project_snapshot(path, table=sentinel, figure_window=None)
        self.assertFalse(sentinel.called)

    def test_figure_name_must_match_project_name_even_when_empty(self):
        snapshot = migrate_v5_to_v6(self.snapshot())
        self.component(snapshot, "figure")["properties"]["name"] = ""

        with self.assertRaisesRegex(
            ValueError,
            "Project and Figure component names must match",
        ):
            validate_project_snapshot(snapshot)


if __name__ == "__main__":
    unittest.main()
