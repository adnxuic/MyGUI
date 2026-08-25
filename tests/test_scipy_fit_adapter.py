import json
import unittest

import numpy as np

from mygui.database import scipy_fit_adapter
from mygui.database.safe_expression import evaluate_curve_expression
from mygui.database.scipy_fit_models import (
    _finite_domain,
    _nonnegative_x_domain,
    _positive_x_domain,
    _safe_exp,
    _safe_scale,
    _span,
)



class ScipyFitAdapterTests(unittest.TestCase):
    def test_fit_models_domain_validators(self):
        # Empty arrays
        self.assertEqual(_finite_domain(np.array([]), np.array([])), "X Data and Y Data must not be empty.")
        # Length mismatch
        self.assertEqual(_finite_domain(np.array([1.0, 2.0]), np.array([1.0])), "X Data and Y Data must have the same length.")
        # NaN / Inf values
        self.assertEqual(_finite_domain(np.array([1.0, np.nan]), np.array([1.0, 2.0])), "X Data and Y Data must contain only finite numbers.")
        self.assertEqual(_finite_domain(np.array([1.0, 2.0]), np.array([1.0, np.inf])), "X Data and Y Data must contain only finite numbers.")
        # Positive X domain
        self.assertIsNone(_positive_x_domain(np.array([1.0, 2.0]), np.array([1.0, 2.0])))
        self.assertEqual(_positive_x_domain(np.array([0.0, 1.0]), np.array([1.0, 2.0])), "This fit type requires X values greater than 0.")
        # Non-negative X domain
        self.assertIsNone(_nonnegative_x_domain(np.array([0.0, 1.0]), np.array([1.0, 2.0])))
        self.assertEqual(_nonnegative_x_domain(np.array([-1.0, 1.0]), np.array([1.0, 2.0])), "This fit type requires X values greater than or equal to 0.")

        # Helper functions: _span, _safe_scale, _safe_exp
        self.assertEqual(_span(np.array([1.0])), 1.0)
        self.assertAlmostEqual(_span(np.array([1.0, 5.0])), 4.0)
        self.assertEqual(_safe_scale(np.array([])), 1.0)
        self.assertGreater(_safe_scale(np.array([1.0, 10.0])), 0.0)
        self.assertAlmostEqual(float(_safe_exp(0.0)), 1.0)

    def test_all_model_families_evaluation_and_start_points(self):
        x = np.linspace(0.5, 5.0, 30)
        # 1. Exponential: exp1, exp2
        y_exp1 = 2.0 * np.exp(0.5 * x)
        res_exp1 = scipy_fit_adapter.fit_curve(x, y_exp1, "exp1")
        self.assertAlmostEqual(res_exp1["goodness"]["rsquare"], 1.0, places=3)

        y_exp2 = 1.5 * np.exp(0.3 * x) + 0.8 * np.exp(-0.2 * x)
        res_exp2 = scipy_fit_adapter.fit_curve(x, y_exp2, "exp2")
        self.assertGreater(res_exp2["goodness"]["rsquare"], 0.99)

        # 2. Gaussian: gauss2, gauss3
        y_gauss2 = 2.0 * np.exp(-((x - 1.5) / 0.8) ** 2) + 1.5 * np.exp(-((x - 3.5) / 0.6) ** 2)
        res_gauss2 = scipy_fit_adapter.fit_curve(x, y_gauss2, "gauss2")
        self.assertGreater(res_gauss2["goodness"]["rsquare"], 0.99)

        # 3. Fourier: fourier1, fourier2
        y_four1 = 2.0 + 1.5 * np.cos(0.8 * x) + 0.5 * np.sin(0.8 * x)
        res_four1 = scipy_fit_adapter.fit_curve(x, y_four1, "fourier1")
        self.assertGreater(res_four1["goodness"]["rsquare"], 0.99)

        # 4. Sine: sin1, sin2
        y_sin1 = 2.5 * np.sin(1.2 * x + 0.3)
        res_sin1 = scipy_fit_adapter.fit_curve(x, y_sin1, "sin1")
        self.assertGreater(res_sin1["goodness"]["rsquare"], 0.99)

        # 5. Power: power1, power2
        y_pow1 = 2.0 * x ** 1.5
        res_pow1 = scipy_fit_adapter.fit_curve(x, y_pow1, "power1")
        self.assertAlmostEqual(res_pow1["goodness"]["rsquare"], 1.0, places=3)

        y_pow2 = 2.0 * x ** 1.5 + 3.0
        res_pow2 = scipy_fit_adapter.fit_curve(x, y_pow2, "power2")
        self.assertAlmostEqual(res_pow2["goodness"]["rsquare"], 1.0, places=3)

        # 6. Rational: rat02, rat12
        y_rat02 = 1.0 / (1.0 + 0.5 * x + 0.2 * x ** 2)
        res_rat02 = scipy_fit_adapter.fit_curve(x, y_rat02, "rat02")
        self.assertGreater(res_rat02["goodness"]["rsquare"], 0.99)

        # 7. Weibull
        y_weib = 0.5 * 1.5 * (x ** 0.5) * np.exp(-0.5 * (x ** 1.5))
        res_weib = scipy_fit_adapter.fit_curve(x, y_weib, "weibull")
        self.assertGreater(res_weib["goodness"]["rsquare"], 0.95)

    def test_scipy_fit_adapter_option_parsers_and_validation_errors(self):
        from mygui.database.scipy_fit_adapter import (
            _as_float_array,
            _parse_float,
            _parse_float_sequence,
            _parse_optional_float,
            _parse_optional_float_sequence,
            _parse_optional_int,
        )

        with self.assertRaisesRegex(ValueError, "X Data must contain only numbers"):
            _as_float_array(["not", "numbers"], "X Data")

        # _parse_float
        self.assertEqual(_parse_float("2.5", "Test"), 2.5)
        with self.assertRaisesRegex(ValueError, "Test must be a number"):
            _parse_float("bad", "Test")
        with self.assertRaisesRegex(ValueError, "Test must be greater than 0"):
            _parse_float("-1.0", "Test", positive=True)

        # _parse_optional_float & _parse_optional_int
        self.assertIsNone(_parse_optional_float("", "Test"))
        self.assertIsNone(_parse_optional_int(None, "Test"))
        self.assertEqual(_parse_optional_int("10", "Test"), 10)
        with self.assertRaisesRegex(ValueError, "Test must be an integer"):
            _parse_optional_int("bad", "Test")
        with self.assertRaisesRegex(ValueError, "Test must be greater than 0"):
            _parse_optional_int("-2", "Test", positive=True)

        # _parse_float_sequence & _parse_optional_float_sequence
        seq = _parse_float_sequence("1.0, 2.0, 3.0", 3, "Seq")
        np.testing.assert_allclose(seq, [1.0, 2.0, 3.0])
        with self.assertRaisesRegex(ValueError, "Seq must be specified"):
            _parse_float_sequence(None, 2, "Seq")
        with self.assertRaisesRegex(ValueError, "Seq must contain 2 values"):
            _parse_float_sequence("1.0, 2.0, 3.0", 2, "Seq")

        self.assertIsNone(_parse_optional_float_sequence("", 2, "Seq"))
        self.assertIsNone(_parse_optional_float_sequence([None, None], 2, "Seq"))
        with self.assertRaisesRegex(ValueError, "Seq must be either fully specified"):
            _parse_optional_float_sequence([1.0, None], 2, "Seq")

    def test_scipy_fit_adapter_bounds_validation_and_coercion(self):
        from mygui.database.scipy_fit_adapter import _coerce_start_to_bounds

        x = np.linspace(0.0, 4.0, 10)
        y = 2.0 * x + 1.0

        # Lower > Upper error
        with self.assertRaisesRegex(ValueError, "Lower bounds must be less than or equal to Upper bounds"):
            scipy_fit_adapter.fit_curve(x, y, "poly1", {"Lower": [5.0, 0.0], "Upper": [2.0, 1.0]})

        # _coerce_start_to_bounds directly
        coerced = _coerce_start_to_bounds(
            np.array([np.nan, -1.0, 10.0]),
            np.array([0.0, 0.0, 0.1]),
            np.array([10.0, 5.0, 5.0]),
        )
        self.assertTrue(np.all(np.isfinite(coerced)))
        self.assertGreaterEqual(coerced[1], 0.0)
        self.assertLessEqual(coerced[2], 5.0)

        # Fit curve with fully specified start points outside bounds (coerced)
        res = scipy_fit_adapter.fit_curve(
            x,
            y,
            "gauss1",
            {
                "Lower": [0.0, 0.0, 0.1],
                "Upper": [10.0, 5.0, 5.0],
                "StartPoint": [1.0, -1.0, 10.0],
            },
        )
        self.assertIsNotNone(res)



    def test_scipy_fit_adapter_nonlinear_methods_and_losses(self):
        x = np.linspace(0.5, 4.0, 20)
        y = 3.0 * np.exp(-x)

        # Invalid OptimizerMethod & Loss
        with self.assertRaisesRegex(ValueError, "OptimizerMethod must be one of"):
            scipy_fit_adapter.fit_curve(x, y, "exp1", {"OptimizerMethod": "bad_method"})
        with self.assertRaisesRegex(ValueError, "Loss must be one of"):
            scipy_fit_adapter.fit_curve(x, y, "exp1", {"Loss": "bad_loss"})

        # LM with bounds error
        with self.assertRaisesRegex(ValueError, "OptimizerMethod 'lm' cannot be used with bounds"):
            scipy_fit_adapter.fit_curve(
                x,
                y,
                "exp1",
                {"OptimizerMethod": "lm", "Lower": [0.0, -10.0], "Upper": [10.0, 10.0]},
            )

        # LM with robust loss error
        with self.assertRaisesRegex(ValueError, "OptimizerMethod 'lm' only supports linear loss"):
            scipy_fit_adapter.fit_curve(x, y, "exp1", {"OptimizerMethod": "lm", "Loss": "huber"})

        # Successful LM fit
        res_lm = scipy_fit_adapter.fit_curve(x, y, "exp1", {"OptimizerMethod": "lm"})
        self.assertGreater(res_lm["goodness"]["rsquare"], 0.99)

        # Robust loss functions: soft_l1, huber, cauchy, arctan
        for loss in ("soft_l1", "huber", "cauchy", "arctan"):
            res_loss = scipy_fit_adapter.fit_curve(x, y, "exp1", {"OptimizerMethod": "trf", "Loss": loss})
            self.assertGreater(res_loss["goodness"]["rsquare"], 0.99)

        # XScale option forms
        res_scale_jac = scipy_fit_adapter.fit_curve(x, y, "exp1", {"XScale": "jac"})
        self.assertIsNotNone(res_scale_jac)
        res_scale_seq = scipy_fit_adapter.fit_curve(x, y, "exp1", {"XScale": [1.0, 1.0]})
        self.assertIsNotNone(res_scale_seq)

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

