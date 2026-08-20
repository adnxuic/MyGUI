from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

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


class AgentEngineeringTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import sys

        sys.path.insert(0, str(CHECKS))
        cls.runner = _load("_runner")
        cls.agent_core = _load("verify_agent_core")

    @classmethod
    def tearDownClass(cls):
        import sys

        if str(CHECKS) in sys.path:
            sys.path.remove(str(CHECKS))

    def test_current_agent_core_is_consistent(self):
        self.assertEqual(self.agent_core.validate_agent_core(ROOT), [])

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
