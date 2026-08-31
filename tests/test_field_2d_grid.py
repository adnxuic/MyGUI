"""Unit tests for FIELD_2D long-table grid construction."""

from __future__ import annotations

import os
import unittest
from unittest.mock import patch

import numpy as np

from mygui.figuremodify.components import ComponentValidationError
from mygui.figuremodify.components.property_values import (
    normalize_contour_levels_spec,
)
from mygui.figuremodify.field_grid import (
    Field2DGridError,
    build_field_grid,
    heatmap_extent,
    is_equispaced,
    max_field_grid_cells,
)
from mygui.resource_limits import load_resource_limits


def _grid(rows, **kwargs):
    xs, ys, zs = zip(*rows, strict=False)
    return build_field_grid(xs, ys, zs, **kwargs)


class Field2DGridTests(unittest.TestCase):
    def test_sorts_centers_and_masks_missing_z(self):
        grid = _grid(
            [
                (1.0, 1.0, 4.0),
                (0.0, 0.0, 1.0),
                (1.0, 0.0, None),
                (0.0, 1.0, float("nan")),
            ]
        )
        np.testing.assert_allclose(grid.x, [0.0, 1.0])
        np.testing.assert_allclose(grid.y, [0.0, 1.0])
        self.assertEqual(grid.z.shape, (2, 2))
        self.assertEqual(float(grid.z[0, 0]), 1.0)
        self.assertEqual(float(grid.z[1, 1]), 4.0)
        self.assertTrue(np.ma.is_masked(grid.z[0, 1]))
        self.assertTrue(np.ma.is_masked(grid.z[1, 0]))
        self.assertFalse(grid.empty)
        self.assertEqual(grid.skipped_xy_count, 0)

    def test_pandas_na_sentinels_are_treated_as_blank(self):
        class NAType:
            def __bool__(self):
                raise TypeError("boolean value of NA is ambiguous")

            def __eq__(self, other):
                return self

            def __ne__(self, other):
                return self

        NAType.__name__ = "NAType"
        missing = NAType()
        grid = build_field_grid(
            [0.0, 1.0, missing],
            [0.0, 0.0, missing],
            [1.0, 2.0, missing],
        )
        self.assertEqual((grid.ny, grid.nx), (1, 2))
        self.assertEqual(grid.skipped_xy_count, 0)
        grid = build_field_grid(
            [0.0, 1.0, 0.0, 1.0, None, ""],
            [0.0, 0.0, 1.0, 1.0, None, "  "],
            [1.0, 2.0, 3.0, 4.0, None, None],
        )
        self.assertEqual((grid.ny, grid.nx), (2, 2))
        self.assertEqual(grid.skipped_xy_count, 0)
        self.assertFalse(grid.empty)

    def test_non_finite_xy_rows_are_skipped(self):
        grid = _grid(
            [
                (0.0, 0.0, 1.0),
                (1.0, 0.0, 2.0),
                (None, 1.0, 3.0),
                (float("inf"), 1.0, 4.0),
                (0.0, float("nan"), 5.0),
            ]
        )
        self.assertEqual(grid.skipped_xy_count, 3)
        self.assertEqual((grid.ny, grid.nx), (1, 2))
        self.assertFalse(grid.empty)

    def test_all_blank_or_skipped_rows_yield_empty_grid(self):
        grid = _grid(
            [
                (None, None, None),
                (float("nan"), 0.0, 1.0),
            ]
        )
        self.assertTrue(grid.empty)
        self.assertEqual(grid.cell_count, 0)

    def test_duplicate_coordinates_are_rejected(self):
        with self.assertRaisesRegex(Field2DGridError, "Duplicate"):
            _grid(
                [
                    (0.0, 0.0, 1.0),
                    (1.0, 0.0, 2.0),
                    (0.0, 0.0, 3.0),
                ]
            )

    def test_cell_budget_is_checked_before_allocation(self):
        with self.assertRaisesRegex(Field2DGridError, "cell budget"):
            _grid(
                [
                    (0.0, 0.0, 1.0),
                    (1.0, 0.0, 2.0),
                    (0.0, 1.0, 3.0),
                    (1.0, 1.0, 4.0),
                ],
                max_cells=3,
            )

    def test_environment_cell_budget_and_hard_cap(self):
        self.assertEqual(max_field_grid_cells({}), 2_000_000)
        self.assertEqual(
            load_resource_limits({"MYGUI_MAX_FIELD_GRID_CELLS": "16"}).max_field_grid_cells,
            16,
        )
        with self.assertRaisesRegex(ValueError, "between"):
            load_resource_limits({"MYGUI_MAX_FIELD_GRID_CELLS": "10000001"})
        with patch.dict(os.environ, {"MYGUI_MAX_FIELD_GRID_CELLS": "3"}):
            with self.assertRaisesRegex(Field2DGridError, "cell budget"):
                _grid(
                    [
                        (0.0, 0.0, 1.0),
                        (1.0, 0.0, 2.0),
                        (0.0, 1.0, 3.0),
                        (1.0, 1.0, 4.0),
                    ]
                )

    def test_heatmap_equispaced_tolerance(self):
        self.assertTrue(is_equispaced(np.array([0.0, 1.0, 2.0])))
        step = 1.0
        atol = 1e-12 * max(1.0, abs(step))
        self.assertTrue(is_equispaced(np.array([0.0, 1.0, 2.0 + atol])))
        with self.assertRaisesRegex(Field2DGridError, "equally spaced"):
            _grid(
                [
                    (0.0, 0.0, 1.0),
                    (1.0, 0.0, 2.0),
                    (3.0, 0.0, 3.0),
                    (0.0, 1.0, 4.0),
                    (1.0, 1.0, 5.0),
                    (3.0, 1.0, 6.0),
                ],
                require_equispaced=True,
            )

    def test_single_point_heatmap_extent_uses_half_cell(self):
        grid = _grid([(2.0, 5.0, 1.0)], require_equispaced=True)
        self.assertEqual(heatmap_extent(grid.x, grid.y), (1.5, 2.5, 4.5, 5.5))
        self.assertEqual(grid.heatmap_extent(), (1.5, 2.5, 4.5, 5.5))

    def test_contour_below_2x2_is_empty_but_valid(self):
        grid = _grid(
            [
                (0.0, 0.0, 1.0),
                (1.0, 0.0, 2.0),
            ],
            minimum_shape=(2, 2),
        )
        self.assertTrue(grid.empty)
        self.assertEqual((grid.ny, grid.nx), (1, 2))

    def test_contour_levels_count_and_strict_increase(self):
        self.assertEqual(
            normalize_contour_levels_spec({"kind": "count", "count": 8}),
            {"kind": "count", "count": 8},
        )
        with self.assertRaisesRegex(ComponentValidationError, "between 2 and 256"):
            normalize_contour_levels_spec({"kind": "count", "count": 1})
        with self.assertRaisesRegex(ComponentValidationError, "strictly increasing"):
            normalize_contour_levels_spec({"kind": "values", "values": [0.0, 0.0, 1.0]})
        self.assertEqual(
            normalize_contour_levels_spec({"kind": "values", "values": [0.0, 1.0, 2.5]}),
            {"kind": "values", "values": [0.0, 1.0, 2.5]},
        )


if __name__ == "__main__":
    unittest.main()
