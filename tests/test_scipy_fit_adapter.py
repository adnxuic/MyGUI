import unittest
import json

import numpy as np

from mygui.database import scipy_fit_adapter
from mygui.database.safe_expression import evaluate_curve_expression


class ScipyFitAdapterTests(unittest.TestCase):
    def test_poly2_exact_fit_returns_schema_and_safe_expression(self):
        x = np.linspace(-3.0, 3.0, 13)
        y = 2.0 * x ** 2 - 3.0 * x + 1.5

        result = scipy_fit_adapter.fit_curve(x, y, "poly2")

        self.assertEqual(result["engine"], "Python")
        self.assertEqual(result["fit_type"], "poly2")
        self.assertEqual(result["formula"], "p1*x^2 + p2*x + p3")
        self.assertEqual(result["confidence_level"], 0.95)
        self.assertEqual([item["name"] for item in result["coefficients"]], ["p1", "p2", "p3"])
        self.assertIn("value_expression", result)
        self.assertIn("show_expression", result)
        self.assertEqual(set(result["goodness"]), {"sse", "rsquare", "dfe", "adjrsquare", "rmse"})
        np.testing.assert_allclose(
            evaluate_curve_expression(result["value_expression"], x),
            y,
            atol=1e-10,
        )
        self.assertAlmostEqual(result["goodness"]["rsquare"], 1.0)

    def test_gauss1_synthetic_fit(self):
        x = np.linspace(-5.0, 5.0, 120)
        y = 3.2 * np.exp(-((x - 1.1) / 1.4) ** 2)

        result = scipy_fit_adapter.fit_curve(
            x,
            y,
            "gauss1",
            {"StartPoint": [2.5, 0.8, 1.0], "MaxNfev": 2000},
        )

        values = {item["name"]: item["value"] for item in result["coefficients"]}
        self.assertAlmostEqual(values["a1"], 3.2, places=5)
        self.assertAlmostEqual(values["b1"], 1.1, places=5)
        self.assertAlmostEqual(values["c1"], 1.4, places=5)
        self.assertGreater(result["goodness"]["rsquare"], 0.999999)

    def test_bounds_are_applied_for_linear_fit(self):
        x = np.linspace(0.0, 4.0, 9)
        y = 10.0 * x + 1.0

        result = scipy_fit_adapter.fit_curve(
            x,
            y,
            "poly1",
            {"Lower": [-np.inf, -np.inf], "Upper": [5.0, np.inf]},
        )

        slope = result["coefficients"][0]["value"]
        self.assertLessEqual(slope, 5.0 + 1e-8)

    def test_invalid_numeric_option_raises_clear_error(self):
        x = np.linspace(-2.0, 2.0, 20)
        y = np.exp(-x ** 2)

        with self.assertRaisesRegex(ValueError, "FTol"):
            scipy_fit_adapter.fit_curve(x, y, "gauss1", {"FTol": "bad"})

    def test_get_func_info_exposes_scipy_options_without_matlab_names(self):
        info = scipy_fit_adapter.get_func_info("gauss1")

        self.assertEqual(info["expression"], "a1*exp(-((x-b1)/c1)^2)")
        self.assertEqual(info["coefficients"], ["a1", "b1", "c1"])
        self.assertIn("OptimizerMethod", info["options"])
        self.assertIn("Loss", info["options"])
        self.assertNotIn("Normalize", info["options"])
        self.assertNotIn("TolCon", info["options"])

    def test_default_bounds_and_low_dof_result_are_strict_json(self):
        options = scipy_fit_adapter.default_fit_options("poly1")
        self.assertEqual(options["Lower"], [None, None])
        self.assertEqual(options["Upper"], [None, None])

        result = scipy_fit_adapter.fit_curve([0.0, 1.0], [1.0, 3.0], "poly1")

        self.assertEqual(result["goodness"]["dfe"], 0.0)
        self.assertIsNone(result["goodness"]["adjrsquare"])
        self.assertIsNone(result["goodness"]["rmse"])
        self.assertTrue(
            all(
                coefficient["lower"] is None
                and coefficient["upper"] is None
                for coefficient in result["coefficients"]
            )
        )
        json.dumps(result, allow_nan=False)


if __name__ == "__main__":
    unittest.main()
