"""Components defaults: 15 NEXT_USE keys, inheritable wire, and storage."""

from __future__ import annotations

import math
import os
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from mygui.application_settings import (
    AXES_COMPONENT_KEYS,
    COMPONENT_KEYS,
    GENERAL_COMPONENT_KEYS,
    COMPONENTS_LINE_COLOR,
    COMPONENTS_LINE_LINEWIDTH,
    COMPONENTS_SCATTER_COLOR,
    COMPONENTS_TEXT_COLOR,
    DefaultValueMode,
    InheritableValue,
    InheritSource,
    MemorySettingsDocumentPort,
    PAGE_AXES_COMPONENTS,
    PAGE_COMPONENTS,
    SettingEffect,
    SettingsHealth,
    ApplicationSettingsService,
    production_settings_registry,
)
from mygui.application_settings.document import (
    build_path_trie,
    payload_has_unknown_current_fields,
    snapshot_to_payload,
    values_from_payload,
)
from mygui.application_settings.values import (
    normalize_inheritable_color,
    normalize_inheritable_linewidth,
)


def _service(**kwargs) -> ApplicationSettingsService:
    kwargs.setdefault("document", MemorySettingsDocumentPort())
    return ApplicationSettingsService(**kwargs)


class ComponentDefaultsContractTests(unittest.TestCase):
    def test_fifteen_keys_are_next_use_and_independent(self):
        registry = production_settings_registry()
        self.assertEqual(len(GENERAL_COMPONENT_KEYS), 15)
        self.assertEqual(len(AXES_COMPONENT_KEYS), 99)
        self.assertEqual(COMPONENT_KEYS, (*GENERAL_COMPONENT_KEYS, *AXES_COMPONENT_KEYS))
        self.assertEqual(
            registry.page(PAGE_COMPONENTS).setting_keys, GENERAL_COMPONENT_KEYS
        )
        self.assertEqual(
            registry.page(PAGE_AXES_COMPONENTS).setting_keys, AXES_COMPONENT_KEYS
        )
        for key in GENERAL_COMPONENT_KEYS:
            spec = registry.spec(key)
            self.assertEqual(spec.effect, SettingEffect.NEXT_USE)
            self.assertEqual(spec.page_id, PAGE_COMPONENTS)
            self.assertTrue(spec.include_in_page_restore)
            self.assertTrue(spec.include_in_reset_all)
            self.assertIsInstance(spec.default, InheritableValue)
            self.assertEqual(spec.default.mode, DefaultValueMode.INHERIT)
            self.assertIsNotNone(spec.inherit_source)
        for key in AXES_COMPONENT_KEYS:
            spec = registry.spec(key)
            self.assertEqual(spec.effect, SettingEffect.NEXT_USE)
            self.assertEqual(spec.page_id, PAGE_AXES_COMPONENTS)
            self.assertTrue(spec.include_in_page_restore)
            self.assertTrue(spec.include_in_reset_all)
            self.assertIsInstance(spec.default, InheritableValue)
            self.assertEqual(spec.default.mode, DefaultValueMode.INHERIT)
            self.assertEqual(spec.inherit_source, InheritSource.FIGURE_STYLE)

        self.assertEqual(
            registry.spec(COMPONENTS_LINE_COLOR).inherit_source,
            InheritSource.AXES_PALETTE,
        )
        self.assertEqual(
            registry.spec(COMPONENTS_SCATTER_COLOR).inherit_source,
            InheritSource.AXES_PALETTE,
        )
        self.assertEqual(
            registry.spec(COMPONENTS_TEXT_COLOR).inherit_source,
            InheritSource.FIGURE_STYLE,
        )
        self.assertEqual(
            registry.spec(COMPONENTS_LINE_LINEWIDTH).inherit_source,
            InheritSource.FIGURE_STYLE,
        )

    def test_inactive_values_match_the_closed_table(self):
        defaults = production_settings_registry().defaults()
        expected = {
            "components.line.color": "#1F77B4",
            "components.line.linestyle": "-",
            "components.line.linewidth": 1.5,
            "components.line.marker": "None",
            "components.line.markersize": 6.0,
            "components.line.markeredgewidth": 1.0,
            "components.scatter.color": "#1F77B4",
            "components.scatter.marker": "o",
            "components.scatter.size": 36.0,
            "components.scatter.linewidth": 1.0,
            "components.text.fontfamily": "sans-serif",
            "components.text.fontsize": 10.0,
            "components.text.color": "#000000",
            "components.text.fontweight": "normal",
            "components.text.fontstyle": "normal",
        }
        for key, value in expected.items():
            item = defaults[key]
            self.assertEqual(item.mode, DefaultValueMode.INHERIT, key)
            self.assertEqual(item.value, value, key)

    def test_inheritable_wire_round_trips_and_keeps_inactive_value(self):
        service = _service()
        override = InheritableValue(
            mode=DefaultValueMode.OVERRIDE,
            value=2.5,
        )
        inherit_custom = InheritableValue(
            mode=DefaultValueMode.INHERIT,
            value=2.5,
        )
        result = service.commit_patch(
            service.begin_session(),
            {
                COMPONENTS_LINE_LINEWIDTH: override,
            },
        )
        self.assertTrue(result.success)
        payload = service.document_payload()
        self.assertEqual(
            payload["components"]["line"]["linewidth"],
            {"kind": "override", "value": 2.5},
        )
        self.assertEqual(
            payload["components"]["line"]["color"],
            {"kind": "inherit", "value": "#1F77B4"},
        )
        restored = ApplicationSettingsService(
            document=MemorySettingsDocumentPort(payload)
        )
        line = restored.snapshot().components.line
        self.assertEqual(line.linewidth.mode, DefaultValueMode.OVERRIDE)
        self.assertEqual(line.linewidth.value, 2.5)
        self.assertEqual(line.color.mode, DefaultValueMode.INHERIT)
        self.assertEqual(line.color.value, "#1F77B4")

        inherit_kept = service.commit_patch(
            service.begin_session(),
            {
                COMPONENTS_LINE_LINEWIDTH: inherit_custom,
            },
        )
        self.assertTrue(inherit_kept.success)
        self.assertEqual(
            service.document_payload()["components"]["line"]["linewidth"],
            {"kind": "inherit", "value": 2.5},
        )

    def test_normalizer_rejects_unknown_kind_type_nan_and_range(self):
        with self.assertRaisesRegex(Exception, "exactly"):
            normalize_inheritable_linewidth(
                {"kind": "inherit", "value": 1.5, "extra": True}
            )
        with self.assertRaisesRegex(Exception, "kind"):
            normalize_inheritable_linewidth({"kind": "style", "value": 1.5})
        with self.assertRaisesRegex(Exception, "number"):
            normalize_inheritable_linewidth({"kind": "override", "value": "wide"})
        with self.assertRaisesRegex(Exception, "finite"):
            normalize_inheritable_linewidth(
                {"kind": "override", "value": math.nan}
            )
        with self.assertRaisesRegex(Exception, "finite"):
            normalize_inheritable_linewidth(
                {"kind": "override", "value": math.inf}
            )
        with self.assertRaisesRegex(Exception, "between"):
            normalize_inheritable_linewidth({"kind": "override", "value": 10_000})
        with self.assertRaisesRegex(Exception, "Component color"):
            normalize_inheritable_color({"kind": "override", "value": "blue"})

    def test_missing_v1_components_section_loads_as_all_inherit(self):
        port = MemorySettingsDocumentPort(
            {
                "appearance": {
                    "theme_mode": "light",
                    "ui_font_point_size": 9,
                    "density": "standard",
                },
                "revision": 3,
            }
        )
        service = _service(document=port)
        self.assertEqual(service.health(), SettingsHealth.OK)
        self.assertTrue(service.writable())
        components = service.snapshot().components
        self.assertEqual(components.line.color.mode, DefaultValueMode.INHERIT)
        self.assertEqual(components.line.color.value, "#1F77B4")
        self.assertEqual(components.scatter.marker.value, "o")
        self.assertEqual(components.text.fontsize.value, 10.0)
        self.assertEqual(components.axes.facecolor.mode, DefaultValueMode.INHERIT)
        self.assertEqual(components.axes.facecolor.value, "#FFFFFF")
        self.assertEqual(components.axes.x.major.grid.alpha.value, None)
        payload = snapshot_to_payload(
            service.snapshot(), production_settings_registry()
        )
        self.assertEqual(
            payload["components"]["line"]["linestyle"]["kind"], "inherit"
        )

    def test_unknown_three_level_field_is_read_only_future(self):
        port = MemorySettingsDocumentPort()
        service = _service(document=port)
        stored = dict(service.document_payload())
        components = dict(stored["components"])
        line = dict(components["line"])
        line["future_only"] = True
        components["line"] = line
        stored["components"] = components
        port.payload = stored
        service.reload()
        self.assertEqual(service.health(), SettingsHealth.READ_ONLY_FUTURE)
        self.assertFalse(service.writable())
        commits = port.commit_calls
        result = service.commit_patch(
            service.begin_session(),
            {
                COMPONENTS_LINE_LINEWIDTH: InheritableValue(
                    DefaultValueMode.OVERRIDE, 3.0
                )
            },
        )
        self.assertFalse(result.success)
        self.assertEqual(port.commit_calls, commits)
        self.assertTrue(port.payload["components"]["line"]["future_only"])

    def test_composite_leaf_internals_are_not_unknown_fields(self):
        registry = production_settings_registry()
        payload = snapshot_to_payload(
            _service().snapshot(), registry
        )
        self.assertFalse(payload_has_unknown_current_fields(payload, registry))
        payload["workspace"]["layout"]["not_a_schema_key"] = 1
        self.assertFalse(payload_has_unknown_current_fields(payload, registry))
        payload["export"]["metadata"]["fields"]["Extra"] = "x"
        self.assertFalse(payload_has_unknown_current_fields(payload, registry))
        payload["components"]["line"]["color"]["extra"] = True
        self.assertFalse(payload_has_unknown_current_fields(payload, registry))
        payload["components"]["new_group"] = {}
        self.assertTrue(payload_has_unknown_current_fields(payload, registry))

    def test_path_trie_covers_three_level_component_keys(self):
        trie = build_path_trie()
        self.assertIn("components", trie)
        self.assertIn("line", trie["components"])
        self.assertIsNone(trie["components"]["line"]["color"])
        self.assertIsNone(
            trie["components"]["axes"]["spines"]["left"]["visible"]
        )
        self.assertIsNone(
            trie["components"]["axes"]["x"]["major"]["grid"]["alpha"]
        )
        self.assertIsNone(trie["workspace"]["layout"])
        self.assertIsNone(trie["export"]["metadata"])

    def test_reset_page_and_reset_all_restore_inherit_on_draft_only(self):
        service = _service()
        service.commit_patch(
            service.begin_session(),
            {
                COMPONENTS_LINE_LINEWIDTH: InheritableValue(
                    DefaultValueMode.OVERRIDE, 4.0
                )
            },
        )
        session = service.begin_session()
        draft = service.reset_section(session, PAGE_COMPONENTS)
        self.assertTrue(draft.success)
        self.assertEqual(
            session.dirty_patch()[COMPONENTS_LINE_LINEWIDTH].mode,
            DefaultValueMode.INHERIT,
        )
        self.assertEqual(service.snapshot().components.line.linewidth.value, 4.0)
        self.assertEqual(
            service.snapshot().components.line.linewidth.mode,
            DefaultValueMode.OVERRIDE,
        )

        all_draft = service.reset_all_preferences(service.begin_session())
        self.assertTrue(all_draft.success)
        self.assertEqual(
            service.snapshot().components.line.linewidth.mode,
            DefaultValueMode.OVERRIDE,
        )

    def test_same_key_conflict_is_field_granular(self):
        service = _service()
        first = service.begin_session()
        second = service.begin_session()
        first.stage(
            COMPONENTS_LINE_COLOR,
            InheritableValue(DefaultValueMode.OVERRIDE, "#FF0000"),
        )
        committed = service.commit_patch(first)
        self.assertTrue(committed.success)
        second.stage(
            COMPONENTS_LINE_COLOR,
            InheritableValue(DefaultValueMode.OVERRIDE, "#00FF00"),
        )
        second.stage(
            COMPONENTS_LINE_LINEWIDTH,
            InheritableValue(DefaultValueMode.OVERRIDE, 3.0),
        )
        conflicted = service.commit_patch(second)
        self.assertFalse(conflicted.success)
        self.assertEqual(conflicted.conflicts, (COMPONENTS_LINE_COLOR,))
        self.assertEqual(
            service.snapshot().components.line.color.value, "#FF0000"
        )
        self.assertIn(COMPONENTS_LINE_LINEWIDTH, second.dirty_patch())
        self.assertNotIn(COMPONENTS_LINE_COLOR, second.dirty_patch())

    def test_storage_failure_does_not_change_snapshot_or_revision(self):
        port = MemorySettingsDocumentPort()
        service = _service(document=port)
        before = service.snapshot()
        port.fail_commit = True
        result = service.commit_patch(
            service.begin_session(),
            {
                COMPONENTS_TEXT_COLOR: InheritableValue(
                    DefaultValueMode.OVERRIDE, "#FF00FF"
                )
            },
        )
        self.assertFalse(result.success)
        self.assertEqual(service.snapshot(), before)
        self.assertEqual(service.snapshot().revision, before.revision)
        self.assertFalse(result.event_emitted)
        self.assertIsNone(port.payload)

    def test_provider_does_not_expose_the_settings_service(self):
        service = _service()
        service.commit_patch(
            service.begin_session(),
            {
                COMPONENTS_SCATTER_COLOR: InheritableValue(
                    DefaultValueMode.OVERRIDE, "#112233"
                )
            },
        )
        provider = service.component_defaults_provider()
        current = provider.current()
        self.assertEqual(current.scatter.color.value, "#112233")
        self.assertEqual(current.scatter.color.mode, DefaultValueMode.OVERRIDE)
        self.assertFalse(hasattr(provider, "commit_patch"))
        self.assertFalse(hasattr(provider, "begin_session"))
        self.assertFalse(hasattr(provider, "snapshot"))

    def test_values_from_payload_ignores_invalid_component_fields(self):
        registry = production_settings_registry()
        values, revision = values_from_payload(
            {
                "components": {
                    "line": {
                        "color": {"kind": "override", "value": "not-a-color"},
                        "linewidth": {"kind": "override", "value": 2.0},
                    }
                },
                "revision": 9,
            },
            registry,
        )
        self.assertEqual(revision, 9)
        self.assertEqual(values[COMPONENTS_LINE_COLOR].mode, DefaultValueMode.INHERIT)
        self.assertEqual(values[COMPONENTS_LINE_LINEWIDTH].mode, DefaultValueMode.OVERRIDE)
        self.assertEqual(values[COMPONENTS_LINE_LINEWIDTH].value, 2.0)


class CreationPreferenceResolverTests(unittest.TestCase):
    def test_explicit_beats_override_beats_inherited(self):
        from dataclasses import replace

        from mygui.application_settings.models import LineComponentDefaults
        from mygui.figuremodify.style_base.color_models import (
            ColorSelection,
            PaletteDefinition,
            PaletteSource,
        )
        from mygui.figuremodify.style_base.creation_defaults import LineCreationDefaults
        from mygui.figuremodify.style_base.creation_preferences import (
            resolve_inheritable,
            resolve_line_appearance,
        )

        setting = InheritableValue(DefaultValueMode.OVERRIDE, 4.0)
        self.assertEqual(resolve_inheritable(2.5, setting, 1.5), 2.5)
        self.assertEqual(resolve_inheritable(None, setting, 1.5), 4.0)
        inherit = InheritableValue(DefaultValueMode.INHERIT, 4.0)
        self.assertEqual(resolve_inheritable(None, inherit, 1.5), 1.5)

        style = LineCreationDefaults(
            linestyle="--",
            linewidth=1.5,
            marker="None",
            markersize=6.0,
            markeredgewidth=1.0,
        )
        palette = ColorSelection(
            "#FF0000",
            palette=PaletteDefinition(
                id="test",
                name="test",
                category="test",
                source=PaletteSource.BUILTIN,
                colors=("#FF0000", "#00FF00"),
            ),
            palette_index=0,
        )
        line = replace(
            LineComponentDefaults(),
            color=InheritableValue(DefaultValueMode.OVERRIDE, "#00AA00"),
            linewidth=InheritableValue(DefaultValueMode.OVERRIDE, 3.25),
        )
        settings = type("S", (), {"line": line})()
        resolved = resolve_line_appearance(
            style,
            settings,
            palette_selection=palette,
        )
        self.assertEqual(resolved.color, "#00AA00")
        self.assertIsNone(resolved.color_selection.palette)
        self.assertFalse(resolved.consume_palette)
        self.assertEqual(resolved.linewidth, 3.25)
        self.assertEqual(resolved.linestyle, "--")

        inherit_resolved = resolve_line_appearance(
            style,
            None,
            palette_selection=palette,
        )
        self.assertEqual(inherit_resolved.color, "#FF0000")
        self.assertTrue(inherit_resolved.consume_palette)

    def test_chart_creation_helpers_do_not_import_settings_service(self):
        root = Path(__file__).resolve().parents[1]
        for relative in (
            "mygui/widgets/figure_canvas/chart_creation.py",
            "mygui/widgets/figure_canvas/canvas_materialize_handlers.py",
        ):
            text = (root / relative).read_text(encoding="utf-8")
            self.assertNotIn("from mygui.application_settings", text, relative)
        prefs = (
            root / "mygui/figuremodify/style_base/creation_preferences.py"
        ).read_text(encoding="utf-8")
        self.assertNotIn("from mygui.application_settings", prefs)
        self.assertNotIn("import ApplicationSettingsService", prefs)


if __name__ == "__main__":
    unittest.main()

