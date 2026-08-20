"""Static gates for the authorized Matplotlib/UI dependency boundaries."""

from __future__ import annotations

import ast
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
PRESENTATION_ROOTS = (
    ROOT / "mygui" / "widgets" / "fig_control_window",
    ROOT / "mygui" / "widgets" / "title_bar",
    ROOT / "mygui" / "widgets" / "component_tree",
    ROOT / "mygui" / "widgets" / "bottom_bar",
)
ADAPTER = ROOT / "mygui" / "figuremodify" / "matplotlib_adapter.py"
TEX_CONFIG = ROOT / "mygui" / "tex_config.py"
MAIN = ROOT / "main.py"
FONT_DIAGNOSTICS = ROOT / "mygui" / "font_diagnostics.py"


def _python_files(root: Path):
    yield from sorted(root.rglob("*.py"))


def _tree(path: Path) -> ast.AST:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


class MatplotlibBoundaryTests(unittest.TestCase):
    def test_presentation_modules_do_not_import_or_resolve_matplotlib_targets(self):
        violations = []
        for root in PRESENTATION_ROOTS:
            for path in _python_files(root):
                for node in ast.walk(_tree(path)):
                    if isinstance(node, ast.Import):
                        if any(name.name.startswith("matplotlib") for name in node.names):
                            violations.append((path, node.lineno, "matplotlib import"))
                    elif isinstance(node, ast.ImportFrom):
                        if (node.module or "").startswith("matplotlib"):
                            violations.append((path, node.lineno, "matplotlib import"))
                    elif isinstance(node, ast.Call):
                        if isinstance(node.func, ast.Attribute) and node.func.attr == "resolve_target":
                            violations.append((path, node.lineno, "resolve_target call"))
                    elif isinstance(node, ast.Attribute) and node.attr == "fig":
                        violations.append((path, node.lineno, "Figure runtime access"))
        self.assertEqual(violations, [])

    def test_global_matplotlib_mutation_has_one_authorized_boundary(self):
        rc_writes = []
        style_contexts = []
        backend_changes = []
        paths = [*_python_files(ROOT / "mygui"), MAIN]
        for path in paths:
            tree = _tree(path)
            style_aliases = set()
            matplotlib_aliases = set()
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for name in node.names:
                        if name.name == "matplotlib":
                            matplotlib_aliases.add(name.asname or "matplotlib")
                elif isinstance(node, ast.ImportFrom) and node.module == "matplotlib":
                    for name in node.names:
                        if name.name == "style":
                            style_aliases.add(name.asname or "style")

            for node in ast.walk(tree):
                if isinstance(node, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
                    targets = (
                        node.targets
                        if isinstance(node, ast.Assign)
                        else [node.target]
                    )
                    for target in targets:
                        if (
                            isinstance(target, ast.Subscript)
                            and isinstance(target.value, ast.Attribute)
                            and target.value.attr == "rcParams"
                        ):
                            rc_writes.append((path, node.lineno))
                if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
                    continue
                owner = node.func.value
                if (
                    node.func.attr == "context"
                    and isinstance(owner, ast.Name)
                    and owner.id in style_aliases
                ):
                    style_contexts.append((path, node.lineno))
                if (
                    node.func.attr == "use"
                    and isinstance(owner, ast.Name)
                    and owner.id in matplotlib_aliases
                ):
                    backend_changes.append((path, node.lineno))

        self.assertTrue(rc_writes)
        self.assertEqual({path for path, _line in rc_writes}, {TEX_CONFIG})
        self.assertEqual({path for path, _line in style_contexts}, {ADAPTER})
        self.assertEqual({path for path, _line in backend_changes}, {MAIN})

    def test_process_font_warning_hooks_have_one_authorized_boundary(self):
        qt_handler_hooks = []
        python_warning_hooks = []
        for path in _python_files(ROOT / "mygui"):
            for node in ast.walk(_tree(path)):
                if (
                    isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Name)
                    and node.func.id == "qInstallMessageHandler"
                ):
                    qt_handler_hooks.append((path, node.lineno))
                if not isinstance(node, (ast.Assign, ast.AnnAssign)):
                    continue
                targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                if any(
                    isinstance(target, ast.Attribute)
                    and isinstance(target.value, ast.Name)
                    and target.value.id == "warnings"
                    and target.attr == "showwarning"
                    for target in targets
                ):
                    python_warning_hooks.append((path, node.lineno))

        self.assertTrue(qt_handler_hooks)
        self.assertTrue(python_warning_hooks)
        self.assertEqual(
            {path for path, _line in qt_handler_hooks},
            {FONT_DIAGNOSTICS},
        )
        self.assertEqual(
            {path for path, _line in python_warning_hooks},
            {FONT_DIAGNOSTICS},
        )


if __name__ == "__main__":
    unittest.main()
