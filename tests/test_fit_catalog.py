import unittest
from pathlib import Path

from mygui.database import matlab_adapter, scipy_fit_adapter
from mygui.database.fit_catalog import (
    FIT_MODEL_GROUPS,
    FIT_MODEL_IDS,
    fit_model_group,
)
from mygui.database.safe_expression import (
    GENERATED_FIT_EXPRESSION_LIMITS,
    compile_math_expression,
)
from mygui.database.scipy_fit_models import SCIPY_FIT_MODELS


class FitCatalogTests(unittest.TestCase):
    def test_all_backends_share_one_ordered_catalog(self):
        self.assertEqual(len(FIT_MODEL_IDS), 72)
        self.assertEqual(tuple(SCIPY_FIT_MODELS), FIT_MODEL_IDS)
        self.assertIs(scipy_fit_adapter.FIT_TYPES, FIT_MODEL_GROUPS)
        self.assertIs(matlab_adapter.FIT_TYPES, FIT_MODEL_GROUPS)
        self.assertEqual(fit_model_group("poly9"), "poly")
        with self.assertRaises(KeyError):
            fit_model_group("unknown-model")

    def test_matlab_build_script_targets_runtime_package_location(self):
        script = (
            Path(__file__).resolve().parents[1]
            / "matlab_sources"
            / "build_packages_r2025a.m"
        ).read_text(encoding="utf-8")
        self.assertNotIn("E:\\PycharmProjects\\MyGUI", script)
        self.assertNotIn('"code", "database", "matlab_func"', script)
        self.assertIn('"mygui", "database", "matlab_func"', script)

    def test_every_model_has_scipy_and_matlab_safe_metadata(self):
        for model_id in FIT_MODEL_IDS:
            with self.subTest(model_id=model_id):
                scipy_spec = SCIPY_FIT_MODELS[model_id]
                self.assertEqual(scipy_spec.fit_type, model_id)
                self.assertIn(model_id, FIT_MODEL_GROUPS[scipy_spec.group])
                matlab_info = matlab_adapter.fallback_func_info(model_id)
                self.assertTrue(matlab_info["coefficients"])
                compile_math_expression(
                    matlab_adapter._matlab_formula_to_python_expression(
                        matlab_info["expression"]
                    ),
                    variable_names={
                        "x",
                        *matlab_info["coefficients"],
                    },
                    limits=GENERATED_FIT_EXPRESSION_LIMITS,
                )


if __name__ == "__main__":
    unittest.main()
