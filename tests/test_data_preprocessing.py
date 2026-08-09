import unittest

import numpy as np
import pandas as pd

from code.database import (
    ColumnType,
    DataPreprocessSpec,
    TableRepository,
    resolve_preprocessed_pair,
)


class DataPreprocessingTests(unittest.TestCase):
    def setUp(self):
        self.repository = TableRepository()
        project = self.repository.create_project("Project")
        self.project_id = project.id
        self.sheet = next(iter(project.sheets.values()))
        self.sheet.add_column("T", ColumnType.NUMBER, column_id="x")
        self.sheet.add_column("Chi", ColumnType.NUMBER, column_id="y")
        self.x_ref = self.repository.column_ref(project.id, self.sheet.id, "x")
        self.y_ref = self.repository.column_ref(project.id, self.sheet.id, "y")

    def set_values(self, x, y):
        index = self.sheet.frame.index
        self.sheet.frame["x"] = pd.Series(x).reindex(index)
        self.sheet.frame["y"] = pd.Series(y).reindex(index)

    def test_spec_round_trip_and_identity(self):
        identity = DataPreprocessSpec()
        self.assertTrue(identity.is_identity)
        self.assertEqual(
            DataPreprocessSpec.from_dict(identity.to_dict()),
            identity,
        )
        self.assertFalse(DataPreprocessSpec("1/x", "y").is_identity)

    def test_inverse_and_cross_axis_expressions_use_original_inputs(self):
        self.set_values([1.0, 2.0, 4.0], [2.0, 6.0, 20.0])
        pair = resolve_preprocessed_pair(
            self.repository,
            self.x_ref,
            self.y_ref,
            DataPreprocessSpec("1/x", "y/x"),
            preserve_gaps=False,
        )
        np.testing.assert_allclose(pair.x, [1.0, 0.5, 0.25])
        np.testing.assert_allclose(pair.y, [2.0, 3.0, 5.0])
        self.assertEqual(pair.excluded_count, 0)

    def test_scalar_broadcast(self):
        self.set_values([1.0, 2.0], [3.0, 4.0])
        pair = resolve_preprocessed_pair(
            self.repository,
            self.x_ref,
            self.y_ref,
            DataPreprocessSpec("pi", "2"),
            preserve_gaps=False,
        )
        np.testing.assert_allclose(pair.x, [np.pi, np.pi])
        np.testing.assert_allclose(pair.y, [2.0, 2.0])

    def test_nonfinite_rows_are_gaps_or_filtered(self):
        self.set_values([1.0, 0.0, 2.0], [3.0, 4.0, np.nan])
        spec = DataPreprocessSpec("1/x", "y")
        line = resolve_preprocessed_pair(
            self.repository,
            self.x_ref,
            self.y_ref,
            spec,
            preserve_gaps=True,
        )
        self.assertTrue(np.isnan(line.x[1:]).all())
        self.assertTrue(np.isnan(line.y[1:]).all())
        self.assertEqual(line.excluded_count, 2)
        filtered = resolve_preprocessed_pair(
            self.repository,
            self.x_ref,
            self.y_ref,
            spec,
            preserve_gaps=False,
        )
        np.testing.assert_allclose(filtered.x, [1.0])
        np.testing.assert_allclose(filtered.y, [3.0])

    def test_rejects_unsafe_oversized_and_invalid_output(self):
        with self.assertRaises(ValueError):
            DataPreprocessSpec("__import__('os')", "y")
        with self.assertRaises(ValueError):
            DataPreprocessSpec("x" * 513, "y")
        self.set_values([1.0], [2.0])
        with self.assertRaisesRegex(ValueError, "boolean"):
            resolve_preprocessed_pair(
                self.repository,
                self.x_ref,
                self.y_ref,
                DataPreprocessSpec("True", "y"),
                preserve_gaps=False,
            )

    def test_datetime_only_allows_identity_x_and_y_without_x_dependency(self):
        self.sheet.column("x").type = ColumnType.DATETIME
        index = self.sheet.frame.index
        self.sheet.frame["x"] = pd.Series(
            np.asarray(
                ["2024-01-01", "2024-01-02"],
                dtype="datetime64[ns]",
            )
        ).reindex(index)
        self.sheet.frame["y"] = pd.Series([1.0, 2.0]).reindex(index)
        pair = resolve_preprocessed_pair(
            self.repository,
            self.x_ref,
            self.y_ref,
            DataPreprocessSpec("x", "2*y"),
            preserve_gaps=True,
        )
        self.assertTrue(np.issubdtype(pair.x.dtype, np.datetime64))
        np.testing.assert_allclose(pair.y, [2.0, 4.0])
        with self.assertRaisesRegex(ValueError, "Date/time X"):
            resolve_preprocessed_pair(
                self.repository,
                self.x_ref,
                self.y_ref,
                DataPreprocessSpec("1/x", "y"),
                preserve_gaps=True,
            )
        with self.assertRaisesRegex(ValueError, "cannot reference"):
            resolve_preprocessed_pair(
                self.repository,
                self.x_ref,
                self.y_ref,
                DataPreprocessSpec("x", "y/x"),
                preserve_gaps=True,
            )


if __name__ == "__main__":
    unittest.main()
