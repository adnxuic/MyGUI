import builtins
import unittest
from unittest.mock import patch

import numpy as np

from mygui.database.safe_expression import (
    MAX_EXPRESSION_LENGTH,
    UnsafeExpressionError,
    compile_math_expression,
    evaluate_curve_expression,
)


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

    def test_rejects_unsupported_expression_shapes(self):
        x = np.array([1.0])

        blocked = [
            "x[0]",
            "lambda value: value",
            "np.array([1])",
            "sum(x)",
            "np.sin.__call__(x)",
        ]
        for expression in blocked:
            with self.subTest(expression=expression):
                with self.assertRaises(UnsafeExpressionError):
                    evaluate_curve_expression(expression, x)

    def test_interpreter_does_not_call_python_eval(self):
        x = np.array([0.0, 1.0])
        with patch.object(
            builtins,
            "eval",
            side_effect=AssertionError("eval must not be used"),
        ):
            result = evaluate_curve_expression("2*x + 1", x)
        np.testing.assert_allclose(result, [1.0, 3.0])

    def test_rejects_expression_budgets_before_evaluation(self):
        blocked = [
            "x" + " " * MAX_EXPRESSION_LENGTH,
            "+".join(["x"] * 70),
            str(1 << 300),
            "True",
        ]
        for expression in blocked:
            with self.subTest(expression=expression[:40]):
                with self.assertRaises(UnsafeExpressionError):
                    compile_math_expression(expression, {"x"})
        with self.assertRaisesRegex(UnsafeExpressionError, "Power exponent"):
            evaluate_curve_expression("2 ** (2 ** 8)", np.array([1.0]))

    def test_curve_output_must_be_one_dimensional_equal_and_finite(self):
        with self.assertRaisesRegex(UnsafeExpressionError, "one-dimensional"):
            evaluate_curve_expression("x", np.ones((2, 2)))
        with self.assertRaisesRegex(UnsafeExpressionError, "finite"):
            evaluate_curve_expression("1/x", np.array([0.0, 1.0]))


if __name__ == "__main__":
    unittest.main()
