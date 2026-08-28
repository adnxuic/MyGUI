"""Unit tests for FitInputRangeSpec and select_fit_input_pair."""

from __future__ import annotations

import unittest
import numpy as np

from mygui.database import (
    FitInputRangeSpec,
    PreprocessedPair,
    select_fit_input_pair,
)
from mygui.database.fit_input_range import ALL_FIT_INPUT, BOUNDED_FIT_INPUT


class FitInputRangeSpecTests(unittest.TestCase):
    """Test specification validation and serialization."""

    def test_default_is_all_data(self):
        spec = FitInputRangeSpec()
        self.assertEqual(spec.kind, ALL_FIT_INPUT)
        self.assertIsNone(spec.minimum)
        self.assertIsNone(spec.maximum)
        self.assertFalse(spec.is_bounded)
        self.assertEqual(spec.to_dict(), {"kind": "all"})

    def test_bounded_spec_validation_and_serialization(self):
        spec = FitInputRangeSpec(kind=BOUNDED_FIT_INPUT, minimum=50.0, maximum=300.0)
        self.assertEqual(spec.kind, BOUNDED_FIT_INPUT)
        self.assertEqual(spec.minimum, 50.0)
        self.assertEqual(spec.maximum, 300.0)
        self.assertTrue(spec.is_bounded)
        self.assertEqual(
            spec.to_dict(),
            {"kind": "bounded", "minimum": 50.0, "maximum": 300.0},
        )

    def test_from_dict_handles_none_and_instances(self):
        self.assertEqual(FitInputRangeSpec.from_dict(None), FitInputRangeSpec())
        instance = FitInputRangeSpec(kind=BOUNDED_FIT_INPUT, minimum=10.0, maximum=20.0)
        self.assertIs(FitInputRangeSpec.from_dict(instance), instance)

    def test_from_dict_strictly_validates_payload(self):
        # Valid cases
        self.assertEqual(
            FitInputRangeSpec.from_dict({"kind": "all"}),
            FitInputRangeSpec(),
        )
        self.assertEqual(
            FitInputRangeSpec.from_dict({"kind": "bounded", "minimum": 0, "maximum": 100}),
            FitInputRangeSpec(kind=BOUNDED_FIT_INPUT, minimum=0.0, maximum=100.0),
        )

        # Invalid cases
        with self.assertRaisesRegex(ValueError, "must be an object"):
            FitInputRangeSpec.from_dict([1, 2])
        with self.assertRaisesRegex(ValueError, "must declare kind"):
            FitInputRangeSpec.from_dict({"minimum": 1.0, "maximum": 2.0})
        with self.assertRaisesRegex(ValueError, "Unknown fit input range kind"):
            FitInputRangeSpec.from_dict({"kind": "invalid"})
        with self.assertRaisesRegex(ValueError, "only kind"):
            FitInputRangeSpec.from_dict({"kind": "all", "minimum": 1.0})
        with self.assertRaisesRegex(ValueError, "only kind, minimum, and maximum"):
            FitInputRangeSpec.from_dict({"kind": "bounded", "minimum": 1.0, "maximum": 2.0, "extra": 3.0})
        with self.assertRaisesRegex(ValueError, "finite number"):
            FitInputRangeSpec.from_dict({"kind": "bounded", "minimum": "abc", "maximum": 2.0})
        with self.assertRaisesRegex(ValueError, "finite number"):
            FitInputRangeSpec.from_dict({"kind": "bounded", "minimum": True, "maximum": 2.0})
        with self.assertRaisesRegex(ValueError, "finite number"):
            FitInputRangeSpec.from_dict({"kind": "bounded", "minimum": float("nan"), "maximum": 2.0})
        with self.assertRaisesRegex(ValueError, "finite number"):
            FitInputRangeSpec.from_dict({"kind": "bounded", "minimum": 1.0, "maximum": float("inf")})
        with self.assertRaisesRegex(ValueError, "minimum must be below maximum"):
            FitInputRangeSpec.from_dict({"kind": "bounded", "minimum": 100.0, "maximum": 50.0})
        with self.assertRaisesRegex(ValueError, "minimum must be below maximum"):
            FitInputRangeSpec.from_dict({"kind": "bounded", "minimum": 50.0, "maximum": 50.0})


class SelectFitInputPairTests(unittest.TestCase):
    """Test data filtering with select_fit_input_pair."""

    def test_all_data_selection(self):
        pair = PreprocessedPair(
            x=np.array([2.0, 10.0, 50.0, 150.0, 300.0]),
            y=np.array([1.0, 2.0, 3.0, 4.0, 5.0]),
            valid_mask=np.array([True, True, True, True, True]),
            excluded_count=1,
        )
        selected = select_fit_input_pair(pair, FitInputRangeSpec())
        np.testing.assert_array_equal(selected.x, [2.0, 10.0, 50.0, 150.0, 300.0])
        np.testing.assert_array_equal(selected.y, [1.0, 2.0, 3.0, 4.0, 5.0])
        self.assertEqual(selected.excluded_count, 0)
        self.assertEqual(selected.x_start, 2.0)
        self.assertEqual(selected.x_stop, 300.0)

    def test_bounded_selection_inclusive_endpoints(self):
        pair = PreprocessedPair(
            x=np.array([2.0, 50.0, 150.0, 300.0, 350.0]),
            y=np.array([1.0, 2.0, 3.0, 4.0, 5.0]),
            valid_mask=np.array([True, True, True, True, True]),
            excluded_count=0,
        )
        spec = FitInputRangeSpec(kind="bounded", minimum=50.0, maximum=300.0)
        selected = select_fit_input_pair(pair, spec)
        np.testing.assert_array_equal(selected.x, [50.0, 150.0, 300.0])
        np.testing.assert_array_equal(selected.y, [2.0, 3.0, 4.0])
        self.assertEqual(selected.excluded_count, 2)
        self.assertEqual(selected.x_start, 50.0)
        self.assertEqual(selected.x_stop, 300.0)

    def test_bounded_selection_unsorted_and_duplicate_x(self):
        pair = PreprocessedPair(
            x=np.array([300.0, 50.0, 2.0, 150.0, 50.0, 400.0, 300.0]),
            y=np.array([10.0, 20.0, 30.0, 40.0, 50.0, 60.0, 70.0]),
            valid_mask=np.ones(7, dtype=bool),
            excluded_count=0,
        )
        spec = FitInputRangeSpec(kind="bounded", minimum=50.0, maximum=300.0)
        selected = select_fit_input_pair(pair, spec)
        np.testing.assert_array_equal(selected.x, [300.0, 50.0, 150.0, 50.0, 300.0])
        np.testing.assert_array_equal(selected.y, [10.0, 20.0, 40.0, 50.0, 70.0])
        self.assertEqual(selected.excluded_count, 2)
        self.assertEqual(selected.x_start, 50.0)
        self.assertEqual(selected.x_stop, 300.0)

    def test_require_data_raises_when_no_points_in_range(self):
        pair = PreprocessedPair(
            x=np.array([2.0, 10.0, 20.0]),
            y=np.array([1.0, 2.0, 3.0]),
            valid_mask=np.ones(3, dtype=bool),
            excluded_count=0,
        )
        spec = FitInputRangeSpec(kind="bounded", minimum=50.0, maximum=300.0)
        with self.assertRaisesRegex(ValueError, "contains no valid preprocessed rows"):
            select_fit_input_pair(pair, spec, require_data=True)

        # When require_data is False, returns empty arrays without error
        selected = select_fit_input_pair(pair, spec, require_data=False)
        self.assertEqual(selected.x.size, 0)
        self.assertEqual(selected.y.size, 0)
        self.assertEqual(selected.excluded_count, 3)
        self.assertEqual(selected.x_start, 50.0)
        self.assertEqual(selected.x_stop, 300.0)


if __name__ == "__main__":
    unittest.main()
