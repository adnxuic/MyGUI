import unittest

import numpy as np

from code.database.safe_expression import UnsafeExpressionError, evaluate_curve_expression


class SafeExpressionTests(unittest.TestCase):
    def test_evaluates_basic_numpy_math(self):
        x = np.array([0.0, np.pi / 2])
        y = evaluate_curve_expression("sin(x) + np.cos(x)", x)

        np.testing.assert_allclose(y, np.array([1.0, 1.0]))

    def test_scalar_expression_becomes_curve(self):
        x = np.linspace(0, 1, 3)
        y = evaluate_curve_expression("pi", x)

        np.testing.assert_allclose(y, np.full(3, np.pi))

    def test_rejects_unsafe_calls(self):
        x = np.array([1.0])

        with self.assertRaises(UnsafeExpressionError):
            evaluate_curve_expression("__import__('os').system('dir')", x)

    def test_rejects_attribute_escape(self):
        x = np.array([1.0])

        with self.assertRaises(UnsafeExpressionError):
            evaluate_curve_expression("x.__class__", x)


if __name__ == "__main__":
    unittest.main()
