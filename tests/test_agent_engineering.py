from __future__ import annotations

import copy
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time
import unittest
from unittest.mock import patch

import yaml
from jsonschema import Draft202012Validator


ROOT = Path(__file__).resolve().parents[1]
CHECKS = ROOT / ".agents" / "checks"


def _load(name: str):
    path = CHECKS / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class CoverageIssueFixture(unittest.TestCase):
    """Explicitly loaded fixture; method names avoid normal discovery."""

    def failure(self):
        self.fail("structured failure")

    def error(self):
        raise RuntimeError("structured error")


class AgentEngineeringTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import sys

        sys.path.insert(0, str(CHECKS))
        cls.runner = _load("_runner")
        cls.agent_core = _load("verify_agent_core")
        cls.coverage_batch = _load("_coverage_batch")
        cls.verify_full = _load("verify_full")

    @classmethod
    def tearDownClass(cls):
        import sys

        if str(CHECKS) in sys.path:
            sys.path.remove(str(CHECKS))

    def test_current_agent_core_is_consistent(self):
        self.assertEqual(self.agent_core.validate_agent_core(ROOT), [])

    def test_agents_size_normalizes_line_endings_and_has_only_an_upper_bound(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            lf = root / "lf.md"
            crlf = root / "crlf.md"
            short = root / "short.md"
            oversized = root / "oversized.md"
            lf.write_bytes(b"first\nsecond\n")
            crlf.write_bytes(b"first\r\nsecond\r\n")
            short.write_text("# Rules\n", encoding="utf-8")
            oversized.write_text("x" * (8 * 1024 + 1), encoding="utf-8")

            self.assertEqual(
                self.agent_core._normalized_lf_size(lf),
                self.agent_core._normalized_lf_size(crlf),
            )
            self.assertEqual(self.agent_core._validate_agents_size(short), [])
            self.assertTrue(self.agent_core._validate_agents_size(oversized))

    def test_catalog_core_ids_match_the_root_index_exactly(self):
        catalog = self.runner.load_yaml(ROOT / ".agents/rule-catalog.yaml")
        catalog_ids = {
            entry["id"] for entry in catalog["rules"]
            if entry["id"].startswith("CORE-")
        }
        root_ids = set(self.agent_core.CORE_RULE_PATTERN.findall(
            (ROOT / "AGENTS.md").read_text(encoding="utf-8")
        ))
        self.assertEqual(len(catalog_ids), 18)
        self.assertEqual(root_ids, catalog_ids)

    def test_catalog_validation_is_bidirectional_and_checks_anchors_and_enforcement(self):
        catalog = self.runner.load_yaml(ROOT / ".agents/rule-catalog.yaml")
        agents_text = (ROOT / "AGENTS.md").read_text(encoding="utf-8")

        missing_root = agents_text.replace("CORE-RESOURCE-BOUNDARY", "REMOVED-RULE")
        errors = self.agent_core._validate_rule_catalog(ROOT, catalog, missing_root)
        self.assertTrue(any("absent from AGENTS.md" in error for error in errors))

        extra_root = agents_text + "\nCORE-UNREGISTERED\n"
        errors = self.agent_core._validate_rule_catalog(ROOT, catalog, extra_root)
        self.assertTrue(any("Unregistered global rules" in error for error in errors))

        bad_anchor = copy.deepcopy(catalog)
        bad_anchor["rules"][0]["source"] = ".agents/architecture/runtime-boundaries.md#missing"
        errors = self.agent_core._validate_rule_catalog(ROOT, bad_anchor, agents_text)
        self.assertTrue(any("missing source anchor" in error for error in errors))

        absent_anchor = copy.deepcopy(catalog)
        absent_anchor["rules"][0]["source"] = ".agents/architecture/runtime-boundaries.md"
        errors = self.agent_core._validate_rule_catalog(ROOT, absent_anchor, agents_text)
        self.assertTrue(any("must include a Markdown anchor" in error for error in errors))

        wrong_source = copy.deepcopy(catalog)
        wrong_source["rules"][0]["source"] = ".agents/architecture/agent-core.md#authority-and-loading"
        errors = self.agent_core._validate_rule_catalog(ROOT, wrong_source, agents_text)
        self.assertTrue(any("rule ID is absent" in error for error in errors))

        bad_enforcement = copy.deepcopy(catalog)
        bad_enforcement["rules"][0]["enforcement"] = ["tests.missing_contract"]
        errors = self.agent_core._validate_rule_catalog(ROOT, bad_enforcement, agents_text)
        self.assertTrue(any("missing enforcement test module" in error for error in errors))

        bad_scanner = copy.deepcopy(catalog)
        bad_scanner["rules"][0]["enforcement"] = ["mygui.unknown"]
        errors = self.agent_core._validate_rule_catalog(ROOT, bad_scanner, agents_text)
        self.assertTrue(any("unknown enforcement target" in error for error in errors))

    def test_rule_catalog_schema_rejects_unknown_fields(self):
        catalog = self.runner.load_yaml(ROOT / ".agents/rule-catalog.yaml")
        catalog["rules"][0]["unexpected"] = True
        schema = json.loads((
            ROOT / ".agents/contracts/rule-catalog.schema.json"
        ).read_text(encoding="utf-8"))
        self.assertTrue(list(Draft202012Validator(schema).iter_errors(catalog)))

    def test_agent_source_scan_ignores_generated_python_bytecode(self):
        with tempfile.TemporaryDirectory() as directory:
            agents = Path(directory) / ".agents"
            source = agents / "checks" / "check.py"
            bytecode = agents / "checks" / "__pycache__" / "check.pyc"
            source.parent.mkdir(parents=True)
            bytecode.parent.mkdir(parents=True)
            source.write_text("authored source", encoding="utf-8")
            bytecode.write_bytes(b"cordis_run dynamicCordisRunner")

            self.assertEqual(list(self.agent_core._agent_source_files(agents)), [source])

    def test_yaml_loader_rejects_duplicate_task_or_rule_keys(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "duplicate.yaml"
            path.write_text("tasks:\n  same: 1\n  same: 2\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "Duplicate YAML key"):
                self.runner.load_yaml(path)

    def test_required_not_run_prevents_completed_task_result(self):
        verification = [{
            "id": "missing", "command": "missing", "status": "not_run",
            "required": True, "durationMs": 0, "evidence": "not available",
        }]
        result = self.runner.task_result("test", verification)
        self.assertEqual(result["status"], "failed")

    def test_application_coverage_timeout_covers_the_full_gui_suite(self):
        self.assertGreaterEqual(
            self.verify_full.APPLICATION_TEST_TIMEOUT_SECONDS,
            3600,
        )
        self.assertGreaterEqual(
            self.verify_full.APPLICATION_BATCH_TIMEOUT_SECONDS,
            60,
        )

    def test_application_discovery_returns_unique_exact_test_ids(self):
        test_ids = self.coverage_batch.collect_test_ids()
        self.assertTrue(test_ids)
        self.assertEqual(test_ids, sorted(test_ids))
        self.assertEqual(len(test_ids), len(set(test_ids)))
        self.assertTrue(all(test_id.startswith("tests.test_") for test_id in test_ids))
        self.assertIn(
            "tests.test_agent_engineering.AgentEngineeringTests."
            "test_application_discovery_returns_unique_exact_test_ids",
            test_ids,
        )

    def test_application_discovery_rejects_empty_failed_and_duplicate_suites(self):
        class ExampleTests(unittest.TestCase):
            def test_one(self):
                pass

        failed_type = type(
            "_FailedTest",
            (unittest.TestCase,),
            {"runTest": lambda self: None},
        )
        fixtures = (
            (unittest.TestSuite(), "no application tests"),
            (unittest.TestSuite([failed_type()]), "failed imports"),
            (
                unittest.TestSuite([
                    ExampleTests("test_one"),
                    ExampleTests("test_one"),
                ]),
                "duplicate test IDs",
            ),
        )
        for suite, message in fixtures:
            with self.subTest(message=message):
                with patch.object(
                    self.coverage_batch.unittest.defaultTestLoader,
                    "discover",
                    return_value=suite,
                ):
                    with self.assertRaisesRegex(RuntimeError, message):
                        self.coverage_batch.collect_test_ids()

    def test_test_id_normalization_preserves_namespace_package_execution(self):
        normalize = self.coverage_batch._normalized_test_id
        self.assertEqual(
            normalize("test_safe_expression.SafeExpressionTests.test_rejects_unsafe_calls"),
            "tests.test_safe_expression.SafeExpressionTests.test_rejects_unsafe_calls",
        )
        self.assertEqual(
            normalize("tests.test_safe_expression.SafeExpressionTests.test_rejects_unsafe_calls"),
            "tests.test_safe_expression.SafeExpressionTests.test_rejects_unsafe_calls",
        )

    def test_method_batches_are_deterministic_complete_and_single_process_compatible(self):
        test_ids = [
            f"tests.test_example.ExampleTests.test_{index:02d}"
            for index in range(20)
        ]
        weights = {
            test_id: float(index + 1)
            for index, test_id in enumerate(test_ids)
        }
        first = self.verify_full._balanced_test_batches(
            test_ids,
            2,
            weights=weights,
        )
        second = self.verify_full._balanced_test_batches(
            list(reversed(test_ids)),
            2,
            weights=weights,
        )
        self.assertEqual(first, second)
        self.assertEqual(len(first), 8)
        flattened = [test_id for batch in first for test_id in batch]
        self.assertEqual(sorted(flattened), sorted(test_ids))
        self.assertEqual(len(flattened), len(set(flattened)))
        self.assertEqual(
            self.verify_full._balanced_test_batches(test_ids, 1, weights=weights),
            [sorted(test_ids)],
        )
        self.assertEqual(
            self.verify_full._module_from_test_id(
                "tests.nested.test_example.ExampleTests.test_one"
            ),
            "test_example",
        )

    def test_default_application_pool_uses_four_workers(self):
        with patch.dict(os.environ):
            os.environ.pop("MYGUI_TEST_SHARDS", None)
            self.assertEqual(self.verify_full.default_test_shards(), 4)
            self.assertEqual(self.verify_full.DEFAULT_TEST_WORKERS, 4)

    def test_application_plan_uses_one_shared_process_pool(self):
        modules = {
            "test_component_editors": (
                self.verify_full.ISOLATION_GUI_MODULE,
                2.6,
            ),
            "test_gui_layout": (
                self.verify_full.ISOLATION_GUI_MODULE,
                21.5,
            ),
            "test_safe_expression": (self.verify_full.ISOLATION_CORE, 0.1),
            "test_resource_limits": (self.verify_full.ISOLATION_CORE, 0.0),
            "test_xrd_refinement": (
                self.verify_full.ISOLATION_GUI_TEST,
                40.0,
            ),
        }
        test_ids = [
            "tests.test_component_editors.GuiTests.test_widget",
            "tests.test_gui_layout.GuiTests.test_layout",
            "tests.test_safe_expression.CoreTests.test_expression",
            "tests.test_resource_limits.CoreTests.test_budget",
            "tests.test_xrd_refinement.XrdRefinementFigureTests.test_a",
            "tests.test_xrd_refinement.XrdRefinementFigureTests.test_b",
        ]
        with patch.object(self.verify_full, "APPLICATION_TEST_MODULES", modules):
            plan = self.verify_full._build_test_plan(test_ids, 4)

        self.assertEqual(plan["contractVersion"], 3)
        self.assertEqual(plan["maxWorkers"], 4)
        self.assertEqual(plan["isolationMode"], "process")
        self.assertFalse(plan["serial"])
        self.assertEqual(len(plan["groups"]), 1)
        self.assertEqual(plan["groups"][0]["name"], "application")
        self.assertEqual(plan["groups"][0]["workers"], 4)
        isolations = {batch["isolation"] for batch in plan["batches"]}
        self.assertEqual(
            isolations,
            {
                self.verify_full.ISOLATION_GUI_MODULE,
                self.verify_full.ISOLATION_GUI_TEST,
                self.verify_full.ISOLATION_CORE,
            },
        )
        gui_module_batches = [
            batch
            for batch in plan["batches"]
            if batch["isolation"] == self.verify_full.ISOLATION_GUI_MODULE
        ]
        self.assertEqual(len(gui_module_batches), 2)
        self.assertTrue(
            all(len(batch["testIds"]) == 1 for batch in gui_module_batches)
        )
        xrd_batches = [
            batch
            for batch in plan["batches"]
            if batch["isolation"] == self.verify_full.ISOLATION_GUI_TEST
        ]
        self.assertEqual(len(xrd_batches), 2)
        self.assertTrue(all(len(batch["testIds"]) == 1 for batch in xrd_batches))
        flattened = [
            test_id
            for batch in plan["batches"]
            for test_id in batch["testIds"]
        ]
        self.assertEqual(sorted(flattened), sorted(test_ids))
        self.assertEqual(len(flattened), len(set(flattened)))

    def test_unified_pool_lpt_launch_order_is_stable(self):
        modules = {
            "test_gui_heavy": (self.verify_full.ISOLATION_GUI_MODULE, 100.0),
            "test_gui_light": (self.verify_full.ISOLATION_GUI_MODULE, 10.0),
            "test_core_a": (self.verify_full.ISOLATION_CORE, 50.0),
            "test_xrd_refinement": (self.verify_full.ISOLATION_GUI_TEST, 40.0),
        }
        test_ids = [
            "tests.test_gui_heavy.T.test_one",
            "tests.test_gui_light.T.test_one",
            "tests.test_core_a.T.test_one",
            "tests.test_xrd_refinement.T.test_a",
            "tests.test_xrd_refinement.T.test_b",
        ]
        with patch.object(self.verify_full, "APPLICATION_TEST_MODULES", modules):
            first = self.verify_full._build_test_plan(test_ids, 4)
            second = self.verify_full._build_test_plan(list(reversed(test_ids)), 4)
        self.assertEqual(first["launchOrder"], second["launchOrder"])
        self.assertEqual(
            [batch["testIds"] for batch in first["batches"]],
            [batch["testIds"] for batch in second["batches"]],
        )
        estimates = [batch["estimatedSeconds"] for batch in first["batches"]]
        self.assertEqual(estimates, sorted(estimates, reverse=True))
        self.assertEqual(
            first["batches"][0]["testIds"],
            ["tests.test_gui_heavy.T.test_one"],
        )

    def test_complete_module_classification_rejects_unknown_and_missing(self):
        modules = {
            "test_known": (self.verify_full.ISOLATION_CORE, 1.0),
            "test_other": (self.verify_full.ISOLATION_CORE, 1.0),
        }
        with patch.object(self.verify_full, "APPLICATION_TEST_MODULES", modules):
            with self.assertRaisesRegex(ValueError, "unclassified test modules"):
                self.verify_full._build_test_plan(
                    ["tests.test_mystery.T.test_one"],
                    4,
                )
            with self.assertRaisesRegex(
                ValueError,
                "classified modules not collected",
            ):
                self.verify_full._build_test_plan(
                    ["tests.test_known.T.test_one"],
                    4,
                )

    def test_single_worker_falls_back_to_serial_process_isolation(self):
        modules = {
            "test_gui_layout": (self.verify_full.ISOLATION_GUI_MODULE, 21.5),
            "test_safe_expression": (self.verify_full.ISOLATION_CORE, 0.1),
            "test_xrd_refinement": (self.verify_full.ISOLATION_GUI_TEST, 9.0),
        }
        test_ids = [
            "tests.test_gui_layout.GuiTests.test_layout",
            "tests.test_safe_expression.CoreTests.test_expression",
            "tests.test_xrd_refinement.T.test_mask_00",
            "tests.test_xrd_refinement.T.test_mask_01",
        ]
        with patch.object(self.verify_full, "APPLICATION_TEST_MODULES", modules):
            plan = self.verify_full._build_test_plan(test_ids, 1)
        self.assertEqual(plan["maxWorkers"], 1)
        self.assertTrue(plan["serial"])
        self.assertEqual(plan["groups"][0]["workers"], 1)
        gui_batches = [
            batch
            for batch in plan["batches"]
            if batch["isolation"] == self.verify_full.ISOLATION_GUI_MODULE
        ]
        xrd_batches = [
            batch
            for batch in plan["batches"]
            if batch["isolation"] == self.verify_full.ISOLATION_GUI_TEST
        ]
        core_batches = [
            batch
            for batch in plan["batches"]
            if batch["isolation"] == self.verify_full.ISOLATION_CORE
        ]
        self.assertEqual(len(gui_batches), 1)
        self.assertEqual(len(xrd_batches), 2)
        self.assertEqual(len(core_batches), 1)
        self.assertEqual(len(core_batches[0]["testIds"]), 1)

    def test_xrd_legend_combination_ids_cover_all_bitmasks(self):
        prefix = (
            "tests.test_xrd_refinement.XrdRefinementFigureTests."
            "test_legend_combination_mask_"
        )
        test_ids = self.coverage_batch.collect_test_ids()
        combo_ids = [
            test_id for test_id in test_ids if test_id.startswith(prefix)
        ]
        self.assertEqual(len(combo_ids), 16)
        self.assertEqual(len(combo_ids), len(set(combo_ids)))
        masks = []
        for test_id in combo_ids:
            suffix = test_id[len(prefix):]
            self.assertRegex(suffix, r"^\d{2}$")
            masks.append(int(suffix, 10))
        self.assertEqual(sorted(masks), list(range(16)))
        covered = {
            (
                bool(mask & 0b0001),
                bool(mask & 0b0010),
                bool(mask & 0b0100),
                bool(mask & 0b1000),
            )
            for mask in masks
        }
        self.assertEqual(len(covered), 16)

    def test_application_plan_keeps_gui_sensitive_tests_in_one_serial_pool(self):
        gui_modules = {
            "test_component_editors",
            "test_component_inspector",
            "test_figure_history",
            "test_component_runtime_integration",
            "test_gui_data_flow",
            "test_gui_layout",
        }
        self.assertTrue(
            gui_modules <= self.verify_full.GUI_SENSITIVE_TEST_MODULES
        )
        self.assertEqual(
            self.verify_full.APPLICATION_TEST_MODULES["test_xrd_refinement"][0],
            self.verify_full.ISOLATION_GUI_TEST,
        )

    def test_test_worker_environment_is_strictly_validated(self):
        with patch.dict(os.environ, {"MYGUI_TEST_SHARDS": "8"}):
            self.assertEqual(self.verify_full.default_test_shards(), 8)
        for invalid in ("", "workers", "0", "17", "-1"):
            with self.subTest(value=invalid):
                with patch.dict(os.environ, {"MYGUI_TEST_SHARDS": invalid}):
                    with self.assertRaisesRegex(ValueError, "1 through 16"):
                        self.verify_full.default_test_shards()

    def test_application_timeout_environment_is_strictly_validated(self):
        with patch.dict(
            os.environ,
            {"APPLICATION_BATCH_TIMEOUT_SECONDS": "45"},
        ):
            self.assertEqual(
                self.verify_full.configured_timeout_seconds(
                    "APPLICATION_BATCH_TIMEOUT_SECONDS",
                    1200,
                ),
                45,
            )
        for invalid in ("", "seconds", "0", "-1"):
            with self.subTest(value=invalid):
                with patch.dict(
                    os.environ,
                    {"APPLICATION_BATCH_TIMEOUT_SECONDS": invalid},
                ):
                    with self.assertRaisesRegex(ValueError, "positive integer"):
                        self.verify_full.configured_timeout_seconds(
                            "APPLICATION_BATCH_TIMEOUT_SECONDS",
                            1200,
                        )

    def test_coverage_batch_records_structured_failures_and_errors(self):
        test_ids = [
            "tests.test_agent_engineering.CoverageIssueFixture.failure",
            "tests.test_agent_engineering.CoverageIssueFixture.error",
        ]
        plan = {
            "batches": [{"index": 0, "testIds": test_ids}],
        }
        suite = unittest.TestSuite([
            CoverageIssueFixture("failure"),
            CoverageIssueFixture("error"),
        ])
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            plan_path = root / "plan.json"
            result_path = root / "batch-000.json"
            plan_path.write_text(json.dumps(plan), encoding="utf-8")
            with patch.object(
                self.coverage_batch.unittest.defaultTestLoader,
                "loadTestsFromNames",
                return_value=suite,
            ):
                returncode = self.coverage_batch._run_batch(
                    plan_path,
                    0,
                    result_path,
                )
            result = json.loads(result_path.read_text(encoding="utf-8"))

        self.assertEqual(returncode, 1)
        self.assertEqual(result["contractVersion"], 3)
        self.assertEqual(result["failureCount"], 1)
        self.assertEqual(result["errorCount"], 1)
        self.assertEqual(result["failures"][0]["testId"], test_ids[0])
        self.assertEqual(result["failures"][0]["exceptionType"], "AssertionError")
        self.assertIn("structured failure", result["failures"][0]["message"])
        self.assertIn("Traceback", result["failures"][0]["traceback"])
        self.assertEqual(result["errors"][0]["testId"], test_ids[1])
        self.assertEqual(result["errors"][0]["exceptionType"], "RuntimeError")
        self.assertIn("structured error", result["errors"][0]["message"])

    def test_coverage_batch_timeout_and_oserror_are_required_failures(self):
        test_ids = ["tests.test_example.ExampleTests.test_one"]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cases = (
                subprocess.TimeoutExpired(["coverage"], 1),
                OSError("injected spawn failure"),
            )
            for error in cases:
                with self.subTest(error=type(error).__name__):
                    with patch.object(
                        self.verify_full.subprocess,
                        "run",
                        side_effect=error,
                    ):
                        step, metadata, _ = self.verify_full._run_coverage_batch(
                            0,
                            test_ids,
                            1,
                            root / "plan.json",
                            root / "result.json",
                            time.monotonic() + 30,
                        )
                    self.assertEqual(step["status"], "failed")
                    self.assertTrue(step["required"])
                    self.assertFalse(metadata["complete"])
                    self.assertEqual(metadata["testsRun"], 0)
                    self.assertTrue((root / "result.log").is_file())
                    self.assertEqual(len(metadata["errors"]), 1)

    def test_coverage_batch_rejects_a_successful_process_with_incomplete_result(self):
        test_ids = ["tests.test_example.ExampleTests.test_one"]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            result_path = root / "result.json"
            result_path.write_text(json.dumps({
                "expectedCount": 1,
                "testsRun": 0,
                "complete": True,
                "successful": True,
                "testTimings": [],
            }), encoding="utf-8")
            completed = subprocess.CompletedProcess([], 0, stdout="full batch log")
            with patch.object(
                self.verify_full.subprocess,
                "run",
                return_value=completed,
            ):
                step, metadata, _ = self.verify_full._run_coverage_batch(
                    0,
                    test_ids,
                    1,
                    root / "plan.json",
                    result_path,
                    time.monotonic() + 30,
                )
            preserved_log = (root / "result.log").read_text(encoding="utf-8")
        self.assertEqual(step["status"], "failed")
        self.assertFalse(metadata["complete"])
        self.assertIn("full batch log", preserved_log)

    def test_future_exception_is_recorded_and_prevents_complete_coverage(self):
        test_id = "tests.test_example.ExampleTests.test_one"
        plan = {
            "workers": 1,
            "batches": [{"index": 0, "testIds": [test_id]}],
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with (
                patch.object(
                    self.verify_full,
                    "APPLICATION_TIMINGS_PATH",
                    root / "timings.json",
                ),
                patch.object(
                    self.verify_full,
                    "_run_coverage_batch",
                    side_effect=RuntimeError("injected future failure"),
                ),
            ):
                steps, coverage_complete = self.verify_full._execute_test_plan(
                    plan,
                    root / "plan.json",
                    root,
                    30,
                )
        self.assertFalse(coverage_complete)
        self.assertEqual(steps[0]["status"], "failed")
        self.assertIn("injected future failure", steps[0]["evidence"])
        self.assertEqual(steps[-1]["id"], "unittest_coverage_parallel_summary")
        self.assertEqual(steps[-1]["status"], "failed")

    def test_unwritable_result_target_records_explicit_failure(self):
        result = self.runner.task_result("test-output", [])
        with tempfile.TemporaryDirectory() as directory:
            code = self.runner.finish(result, directory, "test-output")
        self.assertEqual(code, 1)
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["verification"][-1]["id"], "task_result_output")

    def test_all_routes_declare_complete_public_shape(self):
        task_map = yaml.safe_load((ROOT / ".agents" / "task-map.yaml").read_text(encoding="utf-8"))
        expected = {
            "skill", "architecture", "checks", "scanners", "focused_tests",
            "documentation", "manual_smoke",
        }
        for route in task_map["tasks"].values():
            self.assertEqual(set(route), expected)

    def test_route_validation_rejects_missing_skill_and_unknown_scanner(self):
        task_map = self.runner.load_task_map(ROOT)
        missing_skill = copy.deepcopy(task_map)
        missing_skill["tasks"]["architecture_audit"]["skill"] = ".agents/skills/missing/SKILL.md"
        self.assertTrue(any("missing skill" in error for error in self.agent_core.validate_task_routes(ROOT, missing_skill)))

        unknown_scanner = copy.deepcopy(task_map)
        unknown_scanner["tasks"]["architecture_audit"]["scanners"] = ["mygui.unknown"]
        self.assertTrue(any("unknown scanner" in error for error in self.agent_core.validate_task_routes(ROOT, unknown_scanner)))

        missing_test = copy.deepcopy(task_map)
        missing_test["tasks"]["maintain_agent_core"]["focused_tests"] = ["tests.missing_agent_core"]
        self.assertTrue(any(
            "missing focused test module" in error
            for error in self.agent_core.validate_task_routes(ROOT, missing_test)
        ))

    def test_task_map_schema_rejects_unknown_fields(self):
        task_map = self.runner.load_task_map(ROOT)
        task_map["tasks"]["fix_ci"]["unexpected"] = True
        schema = json.loads((ROOT / ".agents/contracts/task-map.schema.json").read_text(encoding="utf-8"))
        self.assertTrue(list(Draft202012Validator(schema).iter_errors(task_map)))

    def test_scanner_result_schema_accepts_all_states_and_rejects_bad_evidence(self):
        schema = json.loads((ROOT / ".agents/contracts/scanner-result.schema.json").read_text(encoding="utf-8"))
        validator = Draft202012Validator(schema)

        def result(status="completed", verdict="clean"):
            return {
                "contractVersion": 2,
                "scanner": {"id": "mygui.test", "version": "1.0.0"},
                "status": status,
                "verdict": verdict,
                "scope": {"workspace": "C:/workspace", "include": [], "exclude": [], "changedFiles": []},
                "startedAt": "2026-08-20T00:00:00Z",
                "durationMs": 1,
                "findings": [],
                "grayBoundaries": [],
                "coverage": {"filesVisited": ["mygui/file.py"], "filesSkipped": [], "limitations": []},
                "errors": [],
                "diagnostics": [],
                "summary": {"findings": 0, "grayBoundaries": 0, "errors": 0, "bySeverity": {}},
            }

        fixtures = [
            result(), result(verdict="violation"), result(verdict="gray_boundary"),
            result(status="partial", verdict="unknown"), result(status="failed", verdict="unknown"),
        ]
        for fixture in fixtures:
            self.assertEqual(list(validator.iter_errors(fixture)), [])

        bad = result(verdict="violation")
        bad["findings"] = [{
            "id": "bad", "scannerId": "mygui.test", "ruleId": "R", "severity": "high",
            "confidence": 1.5, "file": "C:/absolute.py", "title": "t", "evidence": "e",
            "reason": "r", "suggestedAction": "a", "tags": [], "fingerprint": "f",
        }]
        bad["summary"] = {"findings": 1, "grayBoundaries": 0, "errors": 0, "bySeverity": {"high": 1}}
        self.assertGreaterEqual(len(list(validator.iter_errors(bad))), 2)

        extra = result()
        extra["legacyField"] = True
        self.assertTrue(list(validator.iter_errors(extra)))


if __name__ == "__main__":
    unittest.main()
