"""Scan production UI modules for user-visible Chinese string literals."""

from __future__ import annotations

import ast
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
PRODUCTION_ROOT = ROOT / "mygui"
ALLOWLISTED_FILES = frozenset(
    {
        PRODUCTION_ROOT / "database" / "interpolate_func.py",
        # MATLAB exception fragments are matched against runtime errors, not UI copy.
        PRODUCTION_ROOT / "database" / "matlab_adapter.py",
    }
)
_CJK_RANGES = (
    (0x3400, 0x4DBF),
    (0x4E00, 0x9FFF),
    (0xF900, 0xFAFF),
)


def _contains_cjk(text: str) -> bool:
    return any(
        start <= ord(char) <= end
        for char in text
        for start, end in _CJK_RANGES
    )


def _string_nodes(tree: ast.AST) -> list[ast.Constant]:
    docstring_ids = {
        id(node.body[0].value)
        for node in ast.walk(tree)
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
        if node.body
        and isinstance(node.body[0], ast.Expr)
        and isinstance(node.body[0].value, ast.Constant)
        and isinstance(node.body[0].value.value, str)
    }
    found: list[ast.Constant] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
            continue
        if id(node) in docstring_ids:
            continue
        found.append(node)
    return found


class VisibleEnglishScanTests(unittest.TestCase):
    def test_production_user_visible_strings_have_no_cjk(self):
        failures: list[str] = []
        for path in sorted(PRODUCTION_ROOT.rglob("*.py")):
            if path in ALLOWLISTED_FILES:
                continue
            source = path.read_text(encoding="utf-8")
            tree = ast.parse(source, filename=str(path))
            for node in _string_nodes(tree):
                if _contains_cjk(node.value):
                    failures.append(
                        f"{path.relative_to(ROOT)}:{node.lineno}: {node.value!r}"
                    )
        self.assertEqual(failures, [])


if __name__ == "__main__":
    unittest.main()
