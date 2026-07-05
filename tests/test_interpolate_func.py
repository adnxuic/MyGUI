import unittest

import numpy as np

from code.database.interpolate_func import (
    CubicSpline_interpolate,
    b_spline_splrep_interpolate,
    interpolate_curve,
    interpolate_dict,
)


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

    def test_all_methods_return_requested_samples(self):
        x = np.array([0.0, 1.0, 2.0, 3.0, 4.0, 5.0])
        y = np.sin(x)

        for method in interpolate_dict:
            with self.subTest(method=method):
                x_new, y_new = interpolate_curve(x, y, method, k=3, samples=64)

                self.assertEqual(len(x_new), 64)
                self.assertEqual(len(y_new), 64)
                self.assertAlmostEqual(x_new[0], 0.0)
                self.assertAlmostEqual(x_new[-1], 5.0)
                self.assertTrue(np.isfinite(y_new).all())

    def test_unsorted_x_is_sorted_before_interpolation(self):
        x = np.array([2.0, 0.0, 1.0])
        y = np.array([4.0, 0.0, 2.0])

        x_new, y_new = interpolate_curve(x, y, "线性插值", samples=3)

        np.testing.assert_allclose(x_new, np.array([0.0, 1.0, 2.0]))
        np.testing.assert_allclose(y_new, np.array([0.0, 2.0, 4.0]))

    def test_invalid_inputs_raise_value_error(self):
        cases = [
            (np.array([0.0, 1.0]), np.array([0.0]), "same length"),
            (np.array([0.0, 0.0]), np.array([0.0, 1.0]), "unique"),
            (np.array([0.0, np.nan]), np.array([0.0, 1.0]), "NaN"),
            (np.array(["a", "b"]), np.array([0.0, 1.0]), "numbers"),
            (np.array([[0.0, 1.0]]), np.array([[0.0, 1.0]]), "one-dimensional"),
        ]

        for x, y, message in cases:
            with self.subTest(message=message):
                with self.assertRaisesRegex(ValueError, message):
                    interpolate_curve(x, y, "线性插值")

    def test_b_spline_rejects_order_not_smaller_than_data_count(self):
        x = np.array([0.0, 1.0, 2.0])
        y = np.array([0.0, 1.0, 0.0])

        with self.assertRaisesRegex(ValueError, "smaller than the number of data points"):
            interpolate_curve(x, y, "B样条插值", k=3)

    def test_smoothing_spline_accepts_auto_and_manual_lambda(self):
        x = np.array([0.0, 1.0, 2.0, 3.0, 4.0])
        y = np.array([0.0, 1.0, 0.0, 1.0, 0.0])

        auto_x, auto_y = interpolate_curve(x, y, "平滑样条", samples=20, lam_auto=True)
        manual_x, manual_y = interpolate_curve(x, y, "平滑样条", samples=20, lam=0.5, lam_auto=False)

        self.assertEqual(len(auto_x), 20)
        self.assertEqual(len(manual_x), 20)
        self.assertTrue(np.isfinite(auto_y).all())
        self.assertTrue(np.isfinite(manual_y).all())


if __name__ == "__main__":
    unittest.main()
