import unittest

import numpy as np

from code.database.interpolate_func import CubicSpline_interpolate, b_spline_splrep_interpolate


class InterpolateFunctionTests(unittest.TestCase):
    def test_cubic_spline_returns_dense_domain(self):
        x = np.array([0.0, 1.0, 2.0, 3.0])
        y = x ** 2

        x_new, y_new = CubicSpline_interpolate(x, y)

        self.assertEqual(len(x_new), 1000)
        self.assertEqual(len(y_new), 1000)
        self.assertAlmostEqual(x_new[0], 0.0)
        self.assertAlmostEqual(x_new[-1], 3.0)

    def test_splrep_b_spline_accepts_order(self):
        x = np.array([0.0, 1.0, 2.0, 3.0])
        y = np.array([0.0, 1.0, 0.0, 1.0])

        x_new, y_new = b_spline_splrep_interpolate(x, y, k=2)

        self.assertEqual(len(x_new), 1000)
        self.assertEqual(len(y_new), 1000)


if __name__ == "__main__":
    unittest.main()
