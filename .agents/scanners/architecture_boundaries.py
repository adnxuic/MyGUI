"""Static enforcement for cross-cutting MyGUI architecture boundaries."""

from __future__ import annotations

import ast
from datetime import datetime, timezone
import hashlib
from pathlib import Path
import re
import time
from typing import Any


SCANNER_ID = "mygui.architecture-boundaries"
SCANNER_VERSION = "1.0.0"
_LEGACY_NORMALIZER = re.compile(r"^normalize_v(?:1[0-9]|2[0-2])_figure$")
_CANVAS_OWNER = "mygui/widgets/figure_canvas/py_figure_canves.py"
_MIGRATION_OWNERS = frozenset({
    "mygui/project_io.py",
    "mygui/figuremodify/components/serialization.py",
})
_SERVICE_PRIVATE_MEMBERS = frozenset({
    "_state",
    "_finalize_remove",
    "_validate_controller_state",
    "_validate_replacement",
})
_PRIVATE_CONTAINER_ATTRS = frozenset({
    "_figure_stack",
    "_inspector_stack",
    "_toolboxes",
    "_chart_stack",
    "_element_stack",
})
_CONTAINER_OWNERS = frozenset({
    "mygui/widgets/fig_control_window/figure_inspector.py",
    "mygui/widgets/fig_control_window/component_editors/containers.py",
})
_SWITCH_STATE_NAMES = frozenset({"_SWITCH_DEPTH", "_OUTER_HOST"})


def _fingerprint(rule_id: str, file: str, line: int, title: str) -> str:
    payload = f"{SCANNER_ID}|{rule_id}|{file}|{line}|{title}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _finding(
    *,
    rule_id: str,
    file: str,
    line: int,
    title: str,
    evidence: str,
    reason: str,
    suggested_action: str,
    severity: str = "high",
) -> dict[str, Any]:
    fingerprint = _fingerprint(rule_id, file, line, title)
    return {
        "id": fingerprint[:16],
        "scannerId": SCANNER_ID,
        "ruleId": rule_id,
        "severity": severity,
        "confidence": 1.0,
        "file": file,
        "line": line,
        "title": title,
        "evidence": evidence,
        "reason": reason,
        "suggestedAction": suggested_action,
        "tags": ["architecture", "static"],
        "fingerprint": fingerprint,
    }


def _assigned_attributes(node: ast.AST):
    if isinstance(node, (ast.Tuple, ast.List)):
        for item in node.elts:
            yield from _assigned_attributes(item)
    elif isinstance(node, ast.Attribute):
        yield node


def _scan_tree(relative: str, tree: ast.AST) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for node in ast.walk(tree):
        targets: list[ast.AST] = []
        if isinstance(node, ast.Assign):
            targets = list(node.targets)
        elif isinstance(node, ast.AnnAssign):
            targets = [node.target]
        elif isinstance(node, ast.AugAssign):
            targets = [node.target]
        for target in targets:
            for attribute in _assigned_attributes(target):
                if (
                    attribute.attr == "current_component_id"
                    and relative != _CANVAS_OWNER
                ):
                    findings.append(_finding(
                        rule_id="CORE-SELECTION-AUTHORITY",
                        file=relative,
                        line=attribute.lineno,
                        title="Canvas selection written outside its owner",
                        evidence="assignment to .current_component_id",
                        reason=(
                            "Only PyFigureCanvas may commit authoritative component "
                            "selection."
                        ),
                        suggested_action="Call a Canvas-owned selection capability.",
                    ))
                if (
                    relative.startswith("mygui/figuremodify/services/")
                    and attribute.attr == "_state"
                ):
                    findings.append(_finding(
                        rule_id="CORE-COMPONENT-STATE",
                        file=relative,
                        line=attribute.lineno,
                        title="Service writes Controller private state",
                        evidence="assignment to controller._state",
                        reason="Services must use a declared Controller transaction API.",
                        suggested_action="Restore through a Controller runtime memento.",
                    ))

        if isinstance(node, ast.ImportFrom):
            if node.module == "mygui.figuremodify.components.serialization":
                for alias in node.names:
                    if (
                        _LEGACY_NORMALIZER.match(alias.name)
                        and relative not in _MIGRATION_OWNERS
                    ):
                        findings.append(_finding(
                            rule_id="CORE-PERSISTENCE-V23",
                            file=relative,
                            line=node.lineno,
                            title="Current runtime imports a predecessor normalizer",
                            evidence=f"import {alias.name}",
                            reason=(
                                "Current runtime validation must follow the single current "
                                "schema alias."
                            ),
                            suggested_action="Use normalize_current_figure().",
                        ))

        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            member = node.func.attr
            if (
                relative.startswith("mygui/figuremodify/services/")
                and member in _SERVICE_PRIVATE_MEMBERS
            ):
                findings.append(_finding(
                    rule_id="CORE-COMPONENT-STATE",
                    file=relative,
                    line=node.lineno,
                    title="Service calls a Controller private transaction primitive",
                    evidence=f"call to .{member}()",
                    reason="Cross-layer transactions require a declared Controller API.",
                    suggested_action="Use the public Controller transaction capability.",
                ))
            if (
                relative.startswith("mygui/widgets/")
                and member == "setStyleSheet"
                and node.args
                and isinstance(node.args[0], ast.Constant)
                and isinstance(node.args[0].value, str)
                and node.args[0].value.strip()
            ):
                findings.append(_finding(
                    rule_id="CORE-THEME-OWNER",
                    file=relative,
                    line=node.lineno,
                    title="Presentation widget installs an inline stylesheet",
                    evidence=node.args[0].value.strip(),
                    reason="Production widget chrome must be retokenized by ThemeService.",
                    suggested_action="Use an object/property selector in bound bundled QSS.",
                    severity="medium",
                ))
            if (
                relative.startswith("mygui/widgets/figure_canvas/")
                and member in {"set_position", "set_subplotspec", "set_in_layout"}
            ):
                findings.append(_finding(
                    rule_id="CORE-AXES-GEOMETRY-OWNER",
                    file=relative,
                    line=node.lineno,
                    title="Canvas helper mutates Axes geometry directly",
                    evidence=f"call to .{member}()",
                    reason="AxesGeometryService is the sole geometry policy owner.",
                    suggested_action="Submit the geometry change to AxesGeometryService.",
                ))

        if (
            isinstance(node, ast.Attribute)
            and node.attr in _PRIVATE_CONTAINER_ATTRS
            and relative not in _CONTAINER_OWNERS
        ):
            findings.append(_finding(
                rule_id="ARCH-PRIVATE-CONTAINER-ACCESS",
                file=relative,
                line=node.lineno,
                title="Inspector host private container accessed outside owner",
                evidence=f"access to .{node.attr}",
                reason=(
                    "Callers must use public Inspector host APIs instead of "
                    "private stacked-container attributes."
                ),
                suggested_action="Use public add/find/show/remove/register_switch_viewports APIs.",
            ))
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "getattr"
            and len(node.args) >= 2
            and isinstance(node.args[1], ast.Constant)
            and node.args[1].value in _PRIVATE_CONTAINER_ATTRS
            and relative not in _CONTAINER_OWNERS
        ):
            findings.append(_finding(
                rule_id="ARCH-PRIVATE-CONTAINER-ACCESS",
                file=relative,
                line=node.lineno,
                title="Inspector host private container probed with getattr",
                evidence=f"getattr(..., {node.args[1].value!r})",
                reason=(
                    "Private stacked-container probing is forbidden outside "
                    "the container owner modules."
                ),
                suggested_action="Register the stack with attach_switch_host().",
            ))
        if isinstance(node, ast.Name) and node.id in _SWITCH_STATE_NAMES:
            findings.append(_finding(
                rule_id="ARCH-INSPECTOR-SWITCH-ISOLATION",
                file=relative,
                line=node.lineno,
                title="Module-level Inspector switch batch state",
                evidence=node.id,
                reason=(
                    "Switch depth and dirty flags belong on each "
                    "CurrentPageStackedWidget instance."
                ),
                suggested_action="Keep batch state on the outermost stacked widget.",
            ))
        if (
            relative.startswith("mygui/application_theme/")
            and _unbounded_widget_find_children(node)
        ):
            findings.append(_finding(
                rule_id="ARCH-THEME-UNBOUNDED-SCAN",
                file=relative,
                line=node.lineno,
                title="Theme path scans an unbounded QWidget tree",
                evidence="findChildren(QWidget) without FindDirectChildrenOnly",
                reason=(
                    "Theme palette, metrics, and icons must use explicit "
                    "window/participant sets instead of full-tree scans."
                ),
                suggested_action="Register explicit participants or iterate direct children.",
            ))
    return findings


def _mentions_direct_children_only(node: ast.AST) -> bool:
    for child in ast.walk(node):
        if isinstance(child, ast.Attribute) and child.attr == "FindDirectChildrenOnly":
            return True
        if isinstance(child, ast.Name) and child.id == "FindDirectChildrenOnly":
            return True
    return False


def _is_qwidget_type(node: ast.AST) -> bool:
    return (
        isinstance(node, ast.Name) and node.id == "QWidget"
    ) or (
        isinstance(node, ast.Attribute) and node.attr == "QWidget"
    )


def _unbounded_widget_find_children(node: ast.AST) -> bool:
    if not isinstance(node, ast.Call):
        return False
    func = node.func
    if not isinstance(func, ast.Attribute) or func.attr != "findChildren":
        return False
    if not node.args or not _is_qwidget_type(node.args[0]):
        return False
    for keyword in node.keywords:
        if keyword.arg == "options" and _mentions_direct_children_only(keyword.value):
            return False
    return not any(_mentions_direct_children_only(arg) for arg in node.args[1:])


def scan(root: Path) -> dict[str, Any]:
    """Return a complete ScannerResult-v2 record for production Python."""

    started_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    started = time.monotonic()
    findings: list[dict[str, Any]] = []
    visited: list[str] = []
    skipped: list[dict[str, str]] = []
    errors: list[dict[str, Any]] = []
    for path in sorted((root / "mygui").rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        relative = path.relative_to(root).as_posix()
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=relative)
        except (OSError, SyntaxError, UnicodeError) as exc:
            skipped.append({"file": relative, "reason": str(exc)})
            errors.append({
                "code": "python_parse_failed",
                "message": str(exc),
                "recoverable": False,
                "file": relative,
            })
            continue
        visited.append(relative)
        findings.extend(_scan_tree(relative, tree))

    by_severity: dict[str, int] = {}
    for finding in findings:
        severity = finding["severity"]
        by_severity[severity] = by_severity.get(severity, 0) + 1
    status = "partial" if errors else "completed"
    verdict = "unknown" if errors else "violation" if findings else "clean"
    return {
        "contractVersion": 2,
        "scanner": {"id": SCANNER_ID, "version": SCANNER_VERSION},
        "status": status,
        "verdict": verdict,
        "scope": {
            "workspace": str(root),
            "include": ["mygui/**/*.py"],
            "exclude": ["**/__pycache__/**"],
            "changedFiles": [],
        },
        "startedAt": started_at,
        "durationMs": round((time.monotonic() - started) * 1000, 3),
        "findings": findings,
        "grayBoundaries": [],
        "coverage": {
            "filesVisited": visited,
            "filesSkipped": skipped,
            "limitations": [],
        },
        "errors": errors,
        "diagnostics": [],
        "summary": {
            "findings": len(findings),
            "grayBoundaries": 0,
            "errors": len(errors),
            "bySeverity": by_severity,
        },
    }
