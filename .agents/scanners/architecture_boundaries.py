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
    return findings


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
