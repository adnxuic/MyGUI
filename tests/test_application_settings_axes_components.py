"""Axes Components defaults: 99 NEXT_USE keys, storage, and resolve."""

from __future__ import annotations

import os
import unittest
from dataclasses import replace
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from mygui.application_settings import (
    AXES_COMPONENT_KEYS,
    COMPONENT_KEYS,
    GENERAL_COMPONENT_KEYS,
    PAGE_AXES_COMPONENTS,
    PAGE_COMPONENTS,
    ApplicationSettingsService,
    AxesComponentDefaults,
    ComponentDefaultsSettings,
    DefaultValueMode,
    InheritableValue,
    InheritSource,
    MemorySettingsDocumentPort,
    SettingEffect,
    SettingsHealth,
    production_settings_registry,
)
from mygui.application_settings.document import (
    payload_has_unknown_current_fields,
    snapshot_to_payload,
    values_from_payload,
)
from mygui.application_settings.models import axes_defaults_from_values, axes_defaults_to_values
from mygui.application_settings.values import (
    normalize_inheritable_optional_grid_alpha,
    normalize_inheritable_rotation,
)
from mygui.figuremodify.style_base.creation_preferences import (
    MATPLOTLIB_39_AXES_FALLBACK,
    resolve_axes_appearance,
)


def _service(**kwargs) -> ApplicationSettingsService:
    kwargs.setdefault("document", MemorySettingsDocumentPort())
    return ApplicationSettingsService(**kwargs)


def _override(**items) -> ComponentDefaultsSettings:
    values = axes_defaults_to_values(AxesComponentDefaults())
    for key, value in items.items():
        values[key] = InheritableValue(DefaultValueMode.OVERRIDE, value)
    return ComponentDefaultsSettings(axes=axes_defaults_from_values(values))


class AxesComponentDefaultsContractTests(unittest.TestCase):
    def test_ninety_nine_keys_are_independent_and_typed(self):
        registry = production_settings_registry()
        self.assertEqual(len(AXES_COMPONENT_KEYS), 99)
        self.assertEqual(len(set(AXES_COMPONENT_KEYS)), 99)
        self.assertFalse(set(GENERAL_COMPONENT_KEYS) & set(AXES_COMPONENT_KEYS))
        self.assertEqual(
            COMPONENT_KEYS, (*GENERAL_COMPONENT_KEYS, *AXES_COMPONENT_KEYS)
        )
        self.assertEqual(
            registry.page(PAGE_AXES_COMPONENTS).setting_keys, AXES_COMPONENT_KEYS
        )
        self.assertEqual(
            registry.page(PAGE_COMPONENTS).setting_keys, GENERAL_COMPONENT_KEYS
        )
        for key in AXES_COMPONENT_KEYS:
            spec = registry.spec(key)
            self.assertEqual(spec.effect, SettingEffect.NEXT_USE, key)
            self.assertEqual(spec.page_id, PAGE_AXES_COMPONENTS, key)
            self.assertEqual(spec.inherit_source, InheritSource.FIGURE_STYLE, key)
            self.assertIsInstance(spec.default, InheritableValue)
            self.assertEqual(spec.default.mode, DefaultValueMode.INHERIT, key)
            self.assertTrue(spec.include_in_page_restore)
            self.assertTrue(spec.include_in_reset_all)

    def test_inactive_values_match_the_closed_table(self):
        defaults = production_settings_registry().defaults()
        self.assertEqual(defaults["components.axes.facecolor"].value, "#FFFFFF")
        self.assertEqual(defaults["components.axes.frameon"].value, True)
        self.assertEqual(defaults["components.axes.axisbelow"].value, "line")
        self.assertEqual(
            defaults["components.axes.spines.left.visible"].value, True
        )
        self.assertEqual(
            defaults["components.axes.spines.left.color"].value, "#000000"
        )
        self.assertEqual(
            defaults["components.axes.spines.left.linewidth"].value, 0.8
        )
        self.assertEqual(
            defaults["components.axes.x.major.ticks.primary_visible"].value, True
        )
        self.assertEqual(
            defaults["components.axes.x.minor.ticks.primary_visible"].value, False
        )
        self.assertEqual(
            defaults["components.axes.x.major.ticks.length"].value, 3.5
        )
        self.assertEqual(
            defaults["components.axes.x.minor.ticks.length"].value, 2.0
        )
        self.assertEqual(
            defaults["components.axes.x.major.tick_labels.pad"].value, 3.5
        )
        self.assertEqual(
            defaults["components.axes.x.minor.tick_labels.pad"].value, 3.4
        )
        self.assertIsNone(
            defaults["components.axes.x.major.grid.alpha"].value
        )
        self.assertEqual(
            defaults["components.axes.y.minor.grid.visible"].value, False
        )

    def test_typed_round_trip_keeps_all_ninety_nine_keys(self):
        registry = production_settings_registry()
        service = _service()
        patch = {
            "components.axes.facecolor": InheritableValue(
                DefaultValueMode.OVERRIDE, "#FFEEDD"
            ),
            "components.axes.frameon": InheritableValue(
                DefaultValueMode.OVERRIDE, False
            ),
            "components.axes.axisbelow": InheritableValue(
                DefaultValueMode.OVERRIDE, True
            ),
            "components.axes.spines.left.color": InheritableValue(
                DefaultValueMode.OVERRIDE, "#FF0000"
            ),
            "components.axes.x.major.ticks.direction": InheritableValue(
                DefaultValueMode.OVERRIDE, "in"
            ),
            "components.axes.y.minor.tick_labels.rotation": InheritableValue(
                DefaultValueMode.OVERRIDE, -15.0
            ),
            "components.axes.x.major.grid.alpha": InheritableValue(
                DefaultValueMode.OVERRIDE, None
            ),
            "components.axes.y.major.grid.alpha": InheritableValue(
                DefaultValueMode.OVERRIDE, 0.25
            ),
        }
        result = service.commit_patch(service.begin_session(), patch)
        self.assertTrue(result.success)
        payload = service.document_payload()
        axes = payload["components"]["axes"]
        self.assertEqual(axes["facecolor"], {"kind": "override", "value": "#FFEEDD"})
        self.assertEqual(axes["frameon"], {"kind": "override", "value": False})
        self.assertEqual(axes["axisbelow"], {"kind": "override", "value": True})
        self.assertEqual(
            axes["x"]["major"]["grid"]["alpha"],
            {"kind": "override", "value": None},
        )
        self.assertEqual(
            axes["y"]["major"]["grid"]["alpha"],
            {"kind": "override", "value": 0.25},
        )
        self.assertEqual(
            axes["spines"]["left"]["visible"],
            {"kind": "inherit", "value": True},
        )
        restored = ApplicationSettingsService(
            document=MemorySettingsDocumentPort(payload)
        )
        flat = axes_defaults_to_values(restored.snapshot().components.axes)
        self.assertEqual(set(flat), set(AXES_COMPONENT_KEYS))
        self.assertEqual(flat["components.axes.axisbelow"].value, True)
        self.assertIsNone(flat["components.axes.x.major.grid.alpha"].value)
        self.assertEqual(flat["components.axes.x.major.grid.alpha"].mode, DefaultValueMode.OVERRIDE)
        round_trip = snapshot_to_payload(restored.snapshot(), registry)
        self.assertEqual(round_trip["components"]["axes"], axes)

    def test_missing_axes_section_loads_as_all_inherit(self):
        port = MemorySettingsDocumentPort(
            {
                "appearance": {
                    "theme_mode": "light",
                    "ui_font_point_size": 9,
                    "density": "standard",
                },
                "components": {
                    "line": {
                        "color": {"kind": "override", "value": "#112233"},
                        "linestyle": {"kind": "inherit", "value": "-"},
                        "linewidth": {"kind": "inherit", "value": 1.5},
                        "marker": {"kind": "inherit", "value": "None"},
                        "markersize": {"kind": "inherit", "value": 6.0},
                        "markeredgewidth": {"kind": "inherit", "value": 1.0},
                    }
                },
                "revision": 4,
            }
        )
        service = _service(document=port)
        self.assertEqual(service.health(), SettingsHealth.OK)
        axes = service.snapshot().components.axes
        self.assertEqual(axes.facecolor.mode, DefaultValueMode.INHERIT)
        self.assertEqual(axes.x.major.grid.alpha.mode, DefaultValueMode.INHERIT)
        self.assertIsNone(axes.x.major.grid.alpha.value)
        self.assertEqual(
            service.snapshot().components.line.color.mode,
            DefaultValueMode.OVERRIDE,
        )

    def test_unknown_axes_field_is_read_only_future(self):
        port = MemorySettingsDocumentPort()
        service = _service(document=port)
        stored = dict(service.document_payload())
        components = dict(stored["components"])
        axes = dict(components["axes"])
        axes["future_only"] = True
        components["axes"] = axes
        stored["components"] = components
        port.payload = stored
        service.reload()
        self.assertEqual(service.health(), SettingsHealth.READ_ONLY_FUTURE)
        self.assertFalse(service.writable())
        commits = port.commit_calls
        result = service.commit_patch(
            service.begin_session(),
            {
                "components.axes.facecolor": InheritableValue(
                    DefaultValueMode.OVERRIDE, "#ABCDEF"
                )
            },
        )
        self.assertFalse(result.success)
        self.assertEqual(port.commit_calls, commits)
        self.assertTrue(port.payload["components"]["axes"]["future_only"])

    def test_illegal_values_and_optional_alpha_are_rejected(self):
        with self.assertRaisesRegex(Exception, "between"):
            normalize_inheritable_rotation({"kind": "override", "value": 400})
        with self.assertRaisesRegex(Exception, "between"):
            normalize_inheritable_optional_grid_alpha(
                {"kind": "override", "value": 1.5}
            )
        none_alpha = normalize_inheritable_optional_grid_alpha(
            {"kind": "override", "value": None}
        )
        self.assertIsNone(none_alpha.value)
        zero = normalize_inheritable_optional_grid_alpha(
            {"kind": "override", "value": 0}
        )
        self.assertEqual(zero.value, 0.0)
        registry = production_settings_registry()
        with self.assertRaises(Exception):
            registry.spec("components.axes.x.major.tick_labels.fontsize").normalize(
                {"kind": "override", "value": 0}
            )
        with self.assertRaises(Exception):
            registry.spec("components.axes.axisbelow").normalize(
                {"kind": "override", "value": "above"}
            )

    def test_payload_unknown_detector_sees_extra_axes_group(self):
        registry = production_settings_registry()
        payload = snapshot_to_payload(_service().snapshot(), registry)
        self.assertFalse(payload_has_unknown_current_fields(payload, registry))
        payload["components"]["axes"]["extra"] = 1
        self.assertTrue(payload_has_unknown_current_fields(payload, registry))

    def test_reset_axes_page_restores_inherit_and_keeps_hidden_value(self):
        service = _service()
        service.commit_patch(
            service.begin_session(),
            {
                "components.axes.facecolor": InheritableValue(
                    DefaultValueMode.OVERRIDE, "#123456"
                )
            },
        )
        session = service.begin_session()
        draft = service.reset_section(session, PAGE_AXES_COMPONENTS)
        self.assertTrue(draft.success)
        self.assertEqual(
            session.dirty_patch()["components.axes.facecolor"].mode,
            DefaultValueMode.INHERIT,
        )
        self.assertEqual(
            session.dirty_patch()["components.axes.facecolor"].value,
            "#123456",
        )
        self.assertEqual(
            service.snapshot().components.axes.facecolor.mode,
            DefaultValueMode.OVERRIDE,
        )

    def test_invalid_axes_field_falls_back_to_default(self):
        registry = production_settings_registry()
        values, _revision = values_from_payload(
            {
                "components": {
                    "axes": {
                        "facecolor": {"kind": "override", "value": "blue"},
                        "frameon": {"kind": "override", "value": True},
                    }
                },
                "revision": 2,
            },
            registry,
        )
        self.assertEqual(values["components.axes.facecolor"].mode, DefaultValueMode.INHERIT)
        self.assertEqual(values["components.axes.frameon"].mode, DefaultValueMode.OVERRIDE)

    def test_single_commit_writes_many_axes_keys_atomically(self):
        port = MemorySettingsDocumentPort()
        service = _service(document=port)
        before = port.commit_calls
        patch = {
            key: InheritableValue(DefaultValueMode.OVERRIDE, True)
            for key in (
                "components.axes.frameon",
                "components.axes.spines.left.visible",
                "components.axes.x.major.ticks.primary_visible",
            )
        }
        result = service.commit_patch(service.begin_session(), patch)
        self.assertTrue(result.success)
        self.assertEqual(port.commit_calls, before + 1)
        self.assertEqual(service.snapshot().revision, 1)

    def test_user_docs_name_the_page_and_key_patterns(self):
        text = (Path(__file__).resolve().parents[1] / "docs" / "settings.md").read_text(
            encoding="utf-8"
        )
        self.assertIn("## Axes Components", text)
        self.assertIn("components.axes.facecolor", text)
        self.assertIn("components.axes.spines.", text)
        self.assertIn("99", text)


class AxesAppearanceResolverTests(unittest.TestCase):
    def test_override_beats_style_and_fallback(self):
        style = replace(MATPLOTLIB_39_AXES_FALLBACK, facecolor="#ABCDEF")
        settings = _override(
            **{
                "components.axes.facecolor": "#FF00AA",
                "components.axes.frameon": False,
                "components.axes.axisbelow": True,
                "components.axes.spines.left.color": "#00FF00",
                "components.axes.x.major.grid.visible": True,
                "components.axes.x.major.grid.alpha": None,
                "components.axes.y.minor.ticks.primary_visible": True,
            }
        )
        resolved = resolve_axes_appearance(style, settings)
        self.assertEqual(resolved.facecolor, "#FF00AA")
        self.assertFalse(resolved.frameon)
        self.assertEqual(resolved.axisbelow, True)
        self.assertEqual(resolved.spines.left.color, "#00FF00")
        self.assertTrue(resolved.x.major.grid.visible)
        self.assertIsNone(resolved.x.major.grid.alpha)
        self.assertTrue(resolved.y.minor.ticks.primary_visible)
        self.assertEqual(resolved.x.major.ticks.direction, "out")

    def test_inherit_keeps_style_including_false_bools(self):
        style = replace(
            MATPLOTLIB_39_AXES_FALLBACK,
            facecolor="#111111",
            frameon=False,
            axisbelow=False,
        )
        resolved = resolve_axes_appearance(style, ComponentDefaultsSettings())
        self.assertEqual(resolved.facecolor, "#111111")
        self.assertFalse(resolved.frameon)
        self.assertEqual(resolved.axisbelow, False)

    def test_missing_style_uses_matplotlib_39_fallback(self):
        settings = _override(**{"components.axes.facecolor": "#ABCDEF"})
        resolved = resolve_axes_appearance(None, settings)
        self.assertEqual(resolved.facecolor, "#ABCDEF")
        self.assertEqual(resolved.spines.right.linewidth, 0.8)
        self.assertEqual(resolved.x.minor.ticks.width, 0.6)

    def test_grid_alpha_override_none_is_not_replaced_by_fallback(self):
        style = replace(
            MATPLOTLIB_39_AXES_FALLBACK,
            x=replace(
                MATPLOTLIB_39_AXES_FALLBACK.x,
                major=replace(
                    MATPLOTLIB_39_AXES_FALLBACK.x.major,
                    grid=replace(
                        MATPLOTLIB_39_AXES_FALLBACK.x.major.grid, alpha=0.4
                    ),
                ),
            ),
        )
        settings = _override(**{"components.axes.x.major.grid.alpha": None})
        resolved = resolve_axes_appearance(style, settings)
        self.assertIsNone(resolved.x.major.grid.alpha)
        inherited = resolve_axes_appearance(style, ComponentDefaultsSettings())
        self.assertEqual(inherited.x.major.grid.alpha, 0.4)

    def test_resolver_does_not_import_matplotlib_or_settings_service(self):
        root = Path(__file__).resolve().parents[1]
        prefs = (
            root / "mygui/figuremodify/style_base/creation_preferences.py"
        ).read_text(encoding="utf-8")
        self.assertNotIn("import matplotlib", prefs)
        self.assertNotIn("from matplotlib", prefs)
        self.assertNotIn("from mygui.application_settings", prefs)
        page = (
            root / "mygui/widgets/settings_center/axes_components_page.py"
        ).read_text(encoding="utf-8")
        self.assertNotIn("import matplotlib", page)
        self.assertNotIn("from matplotlib", page)


if __name__ == "__main__":
    unittest.main()
