"""Public-contract tests for MyGUI application settings and theme types.

These tests assert the locked facade: closed enums, snapshot fields, narrow
ports, and the ban on production JSON editors. They import symbols that
storage and service work are expected to publish. Missing symbols skip with
an explicit reason instead of inventing a pass.
"""

from __future__ import annotations

import ast
import importlib
import inspect
from dataclasses import fields, is_dataclass
from enum import Enum
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
PACKAGE_CANDIDATES = (
    "mygui.application_settings",
    "mygui.application_settings.storage",
    "mygui.application_settings.models",
    "mygui.application_settings.ports",
    "mygui.application_settings.types",
    "mygui.application_settings.registry",
    "mygui.application_settings.service",
    "mygui.application_settings.session",
    "mygui.application_settings.snapshot",
    "mygui.application_settings.bindings",
    "mygui.application_settings.runtime",
    "mygui.application_settings.document",
)

REQUIRED_SNAPSHOT_FIELDS = (
    "appearance",
    "workspace",
    "new_figure",
    "components",
    "export",
)
FORBIDDEN_SNAPSHOT_FIELDS = frozenset({
    "color_library",
    "colorlibrary",
    "tex",
    "matlab",
    "widget",
    "qwidget",
    "callback",
    "inspector",
})
SETTING_EFFECT_NAMES = frozenset({"LIVE_REVERSIBLE", "NEXT_USE", "RESTART_REQUIRED"})
THEME_MODE_NAMES = frozenset({"SYSTEM", "LIGHT", "DARK"})
DENSITY_NAMES = frozenset({"COMPACT", "STANDARD", "COMFORTABLE"})
DOCUMENT_HEALTH_NAMES = frozenset({
    "NORMAL",
    "DEGRADED",
    "READ_ONLY_FUTURE",
    "RECOVERY_REQUIRED",
    "WRITE_UNCERTAIN",
})
FIGURE_DOMAIN_ROOTS = (
    "mygui/figuremodify",
    "mygui/widgets/figure_canvas",
    "mygui/widgets/fig_control_window/component_editors",
)
JSON_EDITOR_TOKENS = frozenset({"json", "JSON", "EditorKind.JSON"})


def _load_module(name: str):
    try:
        return importlib.import_module(name)
    except ImportError:
        return None


def _resolve(symbol: str):
    for name in PACKAGE_CANDIDATES:
        module = _load_module(name)
        if module is not None and hasattr(module, symbol):
            return getattr(module, symbol)
    return None


def _skip_unless_symbol(test, name: str):
    value = _resolve(name)
    if value is None:
        test.skipTest(f"{name} is not importable yet; waiting for the settings facade.")
    return value


def _enum_member_names(enum_cls) -> set[str]:
    if not inspect.isclass(enum_cls) or not issubclass(enum_cls, Enum):
        raise AssertionError(f"{enum_cls!r} is not an Enum")
    return {member.name for member in enum_cls}


def _type_field_names(cls) -> set[str]:
    if is_dataclass(cls):
        return {item.name for item in fields(cls)}
    annotations = getattr(cls, "__annotations__", {}) or {}
    return set(annotations)


def _iter_setting_specs(root_module):
    specs = []
    if root_module is None:
        return specs
    for name in (
        "SETTING_SPECS",
        "PRODUCTION_SETTING_SPECS",
        "SETTINGS_REGISTRY",
        "SETTING_REGISTRY",
    ):
        value = getattr(root_module, name, None)
        if value is None:
            continue
        if isinstance(value, dict):
            specs.extend(value.values())
        elif isinstance(value, (list, tuple)):
            specs.extend(value)
        elif hasattr(value, "specs"):
            specs.extend(list(value.specs))
        elif hasattr(value, "values"):
            specs.extend(list(value.values()))
    for name in (
        "iter_setting_specs",
        "get_setting_specs",
        "setting_specs",
        "production_settings_registry",
        "production_setting_specs",
        "_production_specs",
    ):
        value = getattr(root_module, name, None)
        if not callable(value):
            continue
        try:
            result = value()
        except TypeError:
            continue
        except Exception:
            continue
        if hasattr(result, "specs"):
            specs.extend(list(result.specs))
        elif isinstance(result, (list, tuple)):
            specs.extend(result)
    registry_cls = getattr(root_module, "SettingsRegistry", None)
    if inspect.isclass(registry_cls):
        instance = getattr(root_module, "REGISTRY", None) or getattr(
            root_module, "registry", None
        )
        if instance is not None:
            for attr in ("specs", "all_specs", "setting_specs"):
                payload = getattr(instance, attr, None)
                if callable(payload):
                    specs.extend(list(payload()))
                elif payload is not None:
                    specs.extend(list(payload))
    return specs


def _editor_kind(spec) -> str:
    for attr in ("editor_kind", "editor", "editorKind", "kind"):
        value = getattr(spec, attr, None)
        if value is not None:
            return str(getattr(value, "name", value))
    if isinstance(spec, dict):
        for key in ("editor_kind", "editor", "editorKind", "kind"):
            if key in spec:
                return str(spec[key])
    return ""


def _iter_production_python(relative_roots: tuple[str, ...]):
    for relative in relative_roots:
        root = ROOT / relative
        if not root.is_dir():
            continue
        for path in root.rglob("*.py"):
            yield path


def _imports_symbol(path: Path, symbol: str) -> bool:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            for alias in node.names:
                if alias.name == symbol:
                    return True
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.rsplit(".", 1)[-1] == symbol:
                    return True
    return False


class ApplicationSettingsIsolationTests(unittest.TestCase):
    """Contracts that do not require the settings facade to exist."""

    def test_figure_domain_does_not_import_full_settings_service(self):
        offenders = [
            path.relative_to(ROOT).as_posix()
            for path in _iter_production_python(FIGURE_DOMAIN_ROOTS)
            if _imports_symbol(path, "ApplicationSettingsService")
        ]
        self.assertEqual(
            offenders,
            [],
            "Figure Controllers/Services/Canvas helpers must use narrow ports, "
            "not ApplicationSettingsService: " + ", ".join(offenders),
        )

    def test_contract_module_does_not_import_tex_or_matlab(self):
        package = ROOT / "mygui" / "application_settings"
        self.assertTrue(package.is_dir())
        forbidden_prefixes = (
            "mygui.database.matlab",
            "mygui.tex_config",
            "matlab_fallbacks",
        )
        hits: list[str] = []
        for path in package.rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            imported: list[str] = []
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imported.extend(alias.name for alias in node.names)
                elif isinstance(node, ast.ImportFrom) and node.module:
                    imported.append(node.module)
            for name in imported:
                if name in forbidden_prefixes or name.startswith(forbidden_prefixes):
                    hits.append(f"{path.relative_to(ROOT).as_posix()}:{name}")
        self.assertEqual(hits, [])

    def test_component_state_schema_excludes_application_setting_fields(self):
        from mygui.figuremodify.components.models import ComponentState

        names = {item.name for item in fields(ComponentState)}
        leaked = names & {
            "appearance",
            "workspace",
            "new_figure",
            "export",
            "theme_mode",
            "ui_font_point_size",
            "remember_layout",
            "revision",
        }
        self.assertEqual(leaked, set())
        self.assertEqual(
            names,
            {
                "id",
                "kind",
                "role",
                "parent_id",
                "order",
                "selector",
                "properties",
                "data",
            },
        )

    def test_persistence_and_history_modules_do_not_embed_application_settings(self):
        forbidden = (
            "ApplicationSettingsService",
            "applicationSettings",
            "colorLibrarySettings",
            "ui_font_point_size",
            "remember_layout",
        )
        roots = (
            ROOT / "mygui/project_io.py",
            ROOT / "mygui/widgets/figure_canvas/canvas_snapshot.py",
            ROOT / "mygui/widgets/figure_canvas/component_materializers.py",
            ROOT / "mygui/figuremodify/history.py",
            ROOT / "mygui/figuremodify/components/models.py",
        )
        offenders: list[str] = []
        for path in roots:
            if not path.is_file():
                continue
            text = path.read_text(encoding="utf-8")
            for token in forbidden:
                if token in text:
                    offenders.append(f"{path.relative_to(ROOT).as_posix()}:{token}")
        self.assertEqual(offenders, [])


class ApplicationSettingsFacadeTests(unittest.TestCase):
    def test_setting_effect_is_a_closed_set(self):
        enum_cls = _skip_unless_symbol(self, "SettingEffect")
        self.assertEqual(_enum_member_names(enum_cls), SETTING_EFFECT_NAMES)

    def test_theme_mode_and_density_are_closed_sets(self):
        theme_mode = _skip_unless_symbol(self, "ThemeMode")
        density = _skip_unless_symbol(self, "Density")
        self.assertEqual(_enum_member_names(theme_mode), THEME_MODE_NAMES)
        self.assertEqual(_enum_member_names(density), DENSITY_NAMES)

    def test_document_health_is_a_closed_set(self):
        enum_cls = _skip_unless_symbol(self, "DocumentHealth")
        self.assertEqual(_enum_member_names(enum_cls), DOCUMENT_HEALTH_NAMES)

    def test_snapshot_exposes_the_persisted_sections(self):
        snapshot_cls = _skip_unless_symbol(self, "ApplicationSettingsSnapshot")
        names = _type_field_names(snapshot_cls)
        missing = [field for field in REQUIRED_SNAPSHOT_FIELDS if field not in names]
        self.assertEqual(missing, [], f"snapshot missing fields: {missing}")
        leaked = [
            name
            for name in names
            if name.lower().replace("-", "_") in FORBIDDEN_SNAPSHOT_FIELDS
            or "matlab" in name.lower()
            or "color_library" in name.lower()
            or name.lower().startswith("tex_")
        ]
        self.assertEqual(
            leaked,
            [],
            "snapshot must not persist color library, TeX/MATLAB, or UI objects: "
            + ", ".join(leaked),
        )

    def test_setting_editor_kind_excludes_json(self):
        kind_cls = _skip_unless_symbol(self, "SettingEditorKind")
        names = {item.name.upper() for item in kind_cls}
        values = {str(item.value).lower() for item in kind_cls}
        self.assertNotIn("JSON", names)
        self.assertNotIn("json", values)

    def test_settings_session_and_commit_result_exist(self):
        session = _skip_unless_symbol(self, "SettingsSession")
        commit = _skip_unless_symbol(self, "SettingsCommitResult")
        self.assertTrue(inspect.isclass(session), session)
        self.assertTrue(inspect.isclass(commit), commit)

    def test_service_exposes_snapshot_session_and_commit(self):
        service = _skip_unless_symbol(self, "ApplicationSettingsService")
        self.assertTrue(inspect.isclass(service), service)
        for name in ("snapshot", "begin_session", "commit_patch"):
            self.assertTrue(
                callable(getattr(service, name, None)),
                f"{service.__name__}.{name} must exist",
            )

    def test_narrow_ports_exist_and_are_types(self):
        for name in (
            "NewFigureDefaultsProvider",
            "ComponentDefaultsProvider",
            "ExportPreferencesPort",
            "WorkspaceLayoutPort",
        ):
            port = _skip_unless_symbol(self, name)
            self.assertTrue(inspect.isclass(port), name)

    def test_parent_facade_does_not_export_storage_result_types(self):
        package = _load_module("mygui.application_settings")
        if package is None:
            self.skipTest("mygui.application_settings is not importable yet.")
        exported = set(getattr(package, "__all__", ()))
        self.assertNotIn("DocumentLoadResult", exported)
        self.assertNotIn("StorageCommitResult", exported)
        self.assertFalse(hasattr(package, "DocumentLoadResult"))
        self.assertFalse(hasattr(package, "StorageCommitResult"))

    def test_production_setting_specs_do_not_use_json_editors(self):
        package = _load_module("mygui.application_settings")
        spec_cls = _resolve("SettingSpec")
        if package is None or spec_cls is None:
            self.skipTest("SettingSpec facade is not importable yet.")
        factory = getattr(package, "production_settings_registry", None)
        if callable(factory):
            try:
                registry = factory()
            except Exception as exc:
                self.fail(f"production_settings_registry() failed: {exc}")
            specs = list(getattr(registry, "specs", ()) or ())
            self.assertTrue(
                specs,
                "production_settings_registry() published no SettingSpec entries",
            )
        else:
            specs = _iter_setting_specs(package)
            if not specs:
                for name in PACKAGE_CANDIDATES[1:]:
                    specs.extend(_iter_setting_specs(_load_module(name)))
            if not specs:
                self.skipTest("No SettingSpec registry is published yet.")
        json_specs = []
        for spec in specs:
            kind = _editor_kind(spec)
            if kind.upper() == "JSON" or kind in JSON_EDITOR_TOKENS:
                json_specs.append(repr(spec))
        self.assertEqual(
            json_specs,
            [],
            "production settings must not use editable JSON editors: "
            + ", ".join(json_specs),
        )


if __name__ == "__main__":
    unittest.main()
