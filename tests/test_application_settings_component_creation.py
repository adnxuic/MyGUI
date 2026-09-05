"""Components creation defaults: Canvas wiring, restore isolation, and UI."""

from __future__ import annotations

from dataclasses import replace
import json
import os
import tempfile
import unittest
from unittest import mock
from pathlib import Path

from tests.axes_helpers import create_regular_axes

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QCheckBox, QLabel, QTabWidget

from mygui.application_settings import (
    COMPONENT_KEYS,
    GENERAL_COMPONENT_KEYS,
    COMPONENTS_LINE_LINEWIDTH,
    ApplicationSettingsService,
    ComponentDefaultsSettings,
    DefaultValueMode,
    InheritableValue,
    LineComponentDefaults,
    MemorySettingsDocumentPort,
    ScatterComponentDefaults,
    TextComponentDefaults,
)
from mygui.application_settings.document import flatten_snapshot
from mygui.database import ColumnRef
from mygui.figuremodify.style_base.color_models import ColorSelection, normalize_color
from mygui.figuremodify.style_base.creation_defaults import (
    resolve_component_creation_defaults,
)
from mygui.project_io import (
    PROJECT_SCHEMA_VERSION,
    restore_project_snapshot,
    save_project_snapshot,
)
from mygui.widgets.common_widget.min_widget.color_library import ColorLibrary
from mygui.widgets.settings_center.components_page import ComponentsSettingsPage
from main import MainWindow


class CountingComponentDefaults:
    def __init__(self, settings: ComponentDefaultsSettings) -> None:
        self._settings = settings
        self.calls = 0

    def current(self) -> ComponentDefaultsSettings:
        self.calls += 1
        return self._settings


def _override_line(**fields) -> ComponentDefaultsSettings:
    line = LineComponentDefaults()
    for name, value in fields.items():
        line = replace(
            line,
            **{name: InheritableValue(DefaultValueMode.OVERRIDE, value)},
        )
    return ComponentDefaultsSettings(line=line)


class ComponentCreationDefaultsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.window = MainWindow()
        self.window.figure_window.add_figure(
            width=4,
            height=3,
            dpi=100,
            style="default",
            canva_name="ComponentDefaults",
        )
        self.canvas = self.window.figure_window.current_canva
        create_regular_axes(self.canvas)
        self.sheet = (
            self.window.table.current_subtable().get_table(0).table_model.sheet
        )
        self.x_ref = ColumnRef(
            self.canvas.project_id,
            self.sheet.id,
            self.sheet.columns[0].id,
        )
        self.y_ref = ColumnRef(
            self.canvas.project_id,
            self.sheet.id,
            self.sheet.columns[1].id,
        )
        self.sheet.set_block(0, 0, [[0.0, 1.0], [1.0, 2.0], [2.0, 3.0]])

    def tearDown(self):
        self.window.close()
        self.app.processEvents()

    def _inject(self, settings: ComponentDefaultsSettings):
        provider = CountingComponentDefaults(settings)
        self.window.figure_window.set_component_defaults_provider(provider)
        return provider

    def test_figure_style_creation_defaults_are_cached_per_canvas(self):
        self.canvas._creation_defaults_cache = None
        self.canvas._creation_defaults_cache_key = None
        target = (
            "mygui.widgets.figure_canvas.py_figure_canves."
            "resolve_component_creation_defaults"
        )
        with mock.patch(target, wraps=resolve_component_creation_defaults) as resolve:
            first = self.canvas.component_creation_defaults()
            second = self.canvas.component_creation_defaults()
            self.assertIs(first, second)
            resolve.assert_called_once_with("default")

            root = self.canvas.component_registry.get(
                self.canvas.root_component_id
            )
            self.assertTrue(root.set_property("style", "classic").ok)
            classic = self.canvas.component_creation_defaults()
            self.assertIsNot(classic, first)
            self.assertIs(
                self.canvas.component_creation_defaults(),
                classic,
            )
            self.assertEqual(resolve.call_count, 2)
            resolve.assert_called_with("classic")

    def test_inherit_curve_keeps_explicit_style_and_color(self):
        line = self.canvas.add_curve("x", 0, 1, "--", "#112233", "curve")
        self.assertEqual(line.get_linestyle(), "--")
        self.assertEqual(normalize_color(line.get_color()), "#112233")

    def test_line_override_applies_to_unspecified_fields(self):
        self._inject(_override_line(linewidth=4.25, marker="s", markersize=9.0))
        line = self.canvas.add_curve("x", 0, 1, "-", "#445566", "curve")
        self.assertAlmostEqual(float(line.get_linewidth()), 4.25)
        self.assertEqual(line.get_marker(), "s")
        self.assertAlmostEqual(float(line.get_markersize()), 9.0)
        self.assertEqual(normalize_color(line.get_color()), "#445566")

    def test_explicit_linewidth_beats_override(self):
        self._inject(_override_line(linewidth=8.0))
        line = self.canvas.add_curve(
            "x", 0, 1, "-", "#000000", "curve", linewidth=2.0
        )
        self.assertAlmostEqual(float(line.get_linewidth()), 2.0)

    def test_override_color_does_not_consume_palette(self):
        settings = _override_line(color="#00AA00")
        self._inject(settings)
        axes_id = self.canvas.current_axes_component_id
        before_cycle = self.canvas.component_registry.get(axes_id).state.properties.get(
            "color_cycle"
        )
        before_ledger = self.canvas.color_consumption_ledger.history_snapshot()
        recents = list(self.canvas.color_library.recent_colors)
        line = self.canvas.add_curve("x", 0, 1, None, None, "curve")
        after_cycle = self.canvas.component_registry.get(axes_id).state.properties.get(
            "color_cycle"
        )
        self.assertEqual(normalize_color(line.get_color()), "#00AA00")
        self.assertEqual(before_cycle, after_cycle)
        self.assertEqual(
            self.canvas.color_consumption_ledger.history_snapshot(),
            before_ledger,
        )
        self.assertEqual(self.canvas.color_library.recent_colors, recents)

    def test_scatter_override_and_mapping_skips_palette(self):
        scatter_settings = replace(
            ScatterComponentDefaults(),
            marker=InheritableValue(DefaultValueMode.OVERRIDE, "s"),
            size=InheritableValue(DefaultValueMode.OVERRIDE, 64.0),
            linewidth=InheritableValue(DefaultValueMode.OVERRIDE, 2.5),
        )
        self._inject(ComponentDefaultsSettings(scatter=scatter_settings))
        result = self.canvas.add_scatters(
            self.x_ref,
            (self.y_ref,),
            size=None,
            marker=None,
            linewidth=None,
            preprocess=None,
            color_selection=ColorSelection("#ABCDEF"),
        )
        controller = self.canvas.component_registry.get(result.component_ids[0])
        self.assertEqual(controller.state.properties["marker"]["value"], "s")
        self.assertAlmostEqual(controller.state.properties["size"], 64.0)
        self.assertAlmostEqual(controller.state.properties["linewidth"], 2.5)

    def test_text_override_applies_to_free_text_only_path(self):
        text_settings = replace(
            TextComponentDefaults(),
            color=InheritableValue(DefaultValueMode.OVERRIDE, "#FF00AA"),
            fontweight=InheritableValue(DefaultValueMode.OVERRIDE, "bold"),
            fontstyle=InheritableValue(DefaultValueMode.OVERRIDE, "italic"),
        )
        self._inject(ComponentDefaultsSettings(text=text_settings))
        artist = self.canvas.add_text(0.2, 0.3, "hello", "sans-serif", 12.0)
        self.assertEqual(normalize_color(artist.get_color()), "#FF00AA")
        weight = artist.get_fontweight()
        self.assertIn(str(weight).casefold(), {"bold", "700"})
        self.assertEqual(artist.get_fontstyle(), "italic")

    def test_failed_curve_does_not_consume_palette_or_leave_component(self):
        before_ids = set(self.canvas.component_registry)
        before_color = self.canvas.creation_color_cycle().peek()
        recents = list(self.canvas.color_library.recent_colors)
        with self.assertRaises(ValueError):
            self.canvas.add_curve("not a function (", 0, 1, "-", "#123456", "bad")
        self.assertEqual(set(self.canvas.component_registry), before_ids)
        after = self.canvas.creation_color_cycle().peek()
        self.assertEqual(before_color.color, after.color)
        self.assertEqual(self.canvas.color_library.recent_colors, recents)

    def test_settings_keys_never_enter_component_state_or_project(self):
        self._inject(_override_line(linewidth=3.5))
        self.canvas.add_curve("x", 0, 1, "-", "#111111", "curve")
        snapshot = json.dumps(self.canvas.component_snapshot())
        for key in COMPONENT_KEYS:
            self.assertNotIn(key, snapshot)
        path = Path(tempfile.mkdtemp()) / "proj.mygui.json"
        save_project_snapshot(path, self.window.figure_window)
        payload = path.read_text(encoding="utf-8")
        self.assertIn(f'"schema_version": {PROJECT_SCHEMA_VERSION}', payload)
        for key in COMPONENT_KEYS:
            self.assertNotIn(key, payload)

    def test_apply_does_not_mutate_existing_curve(self):
        line = self.canvas.add_curve("x", 0, 1, "-", "#222222", "keep")
        width = float(line.get_linewidth())
        service = ApplicationSettingsService(document=MemorySettingsDocumentPort())
        self.window.figure_window.set_component_defaults_provider(
            service.component_defaults_provider()
        )
        session = service.begin_session()
        result = service.commit_patch(
            session,
            {
                COMPONENTS_LINE_LINEWIDTH: InheritableValue(
                    DefaultValueMode.OVERRIDE, 7.0
                )
            },
        )
        self.assertTrue(result.success)
        self.assertAlmostEqual(float(line.get_linewidth()), width)

    def test_restore_and_history_do_not_read_provider(self):
        settings = _override_line(linewidth=4.0)
        provider = self._inject(settings)
        self.canvas.add_curve("x", 0, 1, "-", "#333333", "saved", linewidth=1.5)
        provider.calls = 0
        path = Path(tempfile.mkdtemp()) / "restore.mygui.json"
        save_project_snapshot(path, self.window.figure_window)
        loaded = MainWindow()
        try:
            loaded.figure_window.set_component_defaults_provider(provider)
            restore_project_snapshot(path, loaded.table, loaded.figure_window)
            self.assertEqual(provider.calls, 0)
        finally:
            loaded.close()
            self.app.processEvents()
        stack = self.window.repository.undo_stack(self.canvas.project_id)
        stack.undo()
        stack.redo()
        self.assertEqual(provider.calls, 0)
        self.canvas.add_component_line([0, 1], [0, 1])
        self.canvas.add_reference_line()
        self.assertEqual(provider.calls, 0)

    def test_plot_fit_interpolation_and_batch_use_line_overrides(self):
        provider = self._inject(_override_line(linewidth=4.25, marker="s"))
        x = [0.0, 1.0, 2.0]
        y = [1.0, 2.0, 3.0]
        plot = self.canvas.add_plot(
            x, y, None, None, None, "plot", self.x_ref, self.y_ref
        )
        self.assertAlmostEqual(float(plot.get_linewidth()), 4.25)
        self.assertEqual(plot.get_marker(), "s")
        fit = self.canvas.add_fit_curve(
            x, y, None, "fit", self.x_ref, self.y_ref, linewidth=None, marker=None
        )
        self.assertAlmostEqual(float(fit.get_linewidth()), 4.25)
        self.assertEqual(fit.get_marker(), "s")
        interpolation = self.canvas.add_interpolate_curve(
            x,
            y,
            self.x_ref,
            self.y_ref,
            "线性插值",
            color=None,
            linewidth=None,
            marker=None,
        )
        self.assertAlmostEqual(float(interpolation.get_linewidth()), 4.25)
        self.assertEqual(interpolation.get_marker(), "s")

        self.sheet.set_block(
            0,
            0,
            [[0.0, 1.0, 4.0], [1.0, 2.0, 5.0], [2.0, 3.0, 6.0]],
        )
        y2 = ColumnRef(
            self.canvas.project_id,
            self.sheet.id,
            self.sheet.columns[2].id,
        )
        provider.calls = 0
        result = self.canvas.add_plots(
            self.x_ref,
            (self.y_ref, y2),
            style=None,
            size=None,
            linewidth=None,
            preprocess=None,
            color_selection=ColorSelection("#112233"),
        )
        self.assertEqual(len(result.component_ids), 2)
        self.assertEqual(provider.calls, 1)
        for component_id in result.component_ids:
            controller = self.canvas.component_registry.get(component_id)
            self.assertAlmostEqual(controller.state.properties["linewidth"], 4.25)
            self.assertEqual(controller.state.properties["marker"]["value"], "s")

    def test_xrd_style_explicit_scatter_beats_override(self):
        scatter_settings = replace(
            ScatterComponentDefaults(),
            marker=InheritableValue(DefaultValueMode.OVERRIDE, "s"),
            size=InheritableValue(DefaultValueMode.OVERRIDE, 80.0),
            linewidth=InheritableValue(DefaultValueMode.OVERRIDE, 3.0),
            color=InheritableValue(DefaultValueMode.OVERRIDE, "#00AA00"),
        )
        self._inject(ComponentDefaultsSettings(scatter=scatter_settings))
        result = self.canvas.add_scatters(
            self.x_ref,
            (self.y_ref,),
            size=12.0,
            marker="D",
            linewidth=0.5,
            preprocess=None,
            color_selection=ColorSelection("#D62728"),
        )
        controller = self.canvas.component_registry.get(result.component_ids[0])
        self.assertEqual(controller.state.properties["marker"]["value"], "D")
        self.assertAlmostEqual(controller.state.properties["size"], 12.0)
        self.assertAlmostEqual(controller.state.properties["linewidth"], 0.5)
        self.assertEqual(
            normalize_color(controller.state.properties["color"]),
            "#D62728",
        )

    def test_global_text_uses_text_defaults(self):
        text_settings = replace(
            TextComponentDefaults(),
            color=InheritableValue(DefaultValueMode.OVERRIDE, "#00AABB"),
            fontweight=InheritableValue(DefaultValueMode.OVERRIDE, "bold"),
        )
        self._inject(ComponentDefaultsSettings(text=text_settings))
        artist = self.canvas.add_global_text(0.4, 0.6, "global", "sans-serif", 11.0)
        self.assertEqual(normalize_color(artist.get_color()), "#00AABB")
        self.assertIn(str(artist.get_fontweight()).casefold(), {"bold", "700"})

    def test_provider_is_read_at_each_creation(self):
        provider = self._inject(_override_line(linewidth=3.0))
        self.canvas.add_curve("x", 0, 1, "-", "#111111", "one")
        first = provider.calls
        self.assertGreaterEqual(first, 1)
        self.canvas.add_curve("x", 0, 1, "-", "#222222", "two")
        self.assertGreater(provider.calls, first)

    def test_provider_failure_warns_and_falls_back(self):
        class Boom:
            def current(self):
                raise RuntimeError("unavailable")

        messages: list[str] = []
        from mygui import status_messages

        status_messages.set_status_handler(
            lambda text, level="info": messages.append(f"{level}:{text}")
        )
        self.addCleanup(status_messages.clear_status_handler)
        self.window.figure_window.set_component_defaults_provider(Boom())
        before = set(self.canvas.component_registry)
        line = self.canvas.add_curve("x", 0, 1, "--", "#ABCDEF", "ok")
        self.assertGreater(len(self.canvas.component_registry), len(before))
        self.assertEqual(line.get_linestyle(), "--")
        self.assertTrue(
            any("defaults could not be read" in item for item in messages)
        )


class ComponentsSettingsPageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_page_has_fifteen_rows_and_inherit_labels(self):
        library = ColorLibrary()
        page = ComponentsSettingsPage(library)
        self.addCleanup(page.deleteLater)
        self.assertEqual(set(page.editors()), set(GENERAL_COMPONENT_KEYS))
        tabs = page.findChild(QTabWidget, "settings_components_tabs")
        self.assertIsNotNone(tabs)
        self.assertEqual(
            [tabs.tabText(index) for index in range(tabs.count())],
            ["Line", "Scatter", "Text"],
        )
        boxes = page.findChildren(QCheckBox)
        labels = {box.text() for box in boxes}
        self.assertIn("Use Figure style", labels)
        self.assertIn("Use Axes palette", labels)
        values = page.draft_values()
        for key in GENERAL_COMPONENT_KEYS:
            self.assertEqual(values[key].mode, DefaultValueMode.INHERIT)
        linewidth = page._rows[COMPONENTS_LINE_LINEWIDTH]
        self.assertFalse(linewidth.value_editor.isEnabled())
        linewidth.inherit_box.setChecked(False)
        self.assertTrue(linewidth.value_editor.isEnabled())
        self.assertEqual(linewidth.value().mode, DefaultValueMode.OVERRIDE)
        for editor in page.keyboard_editors():
            self.assertTrue(int(editor.focusPolicy()) & int(Qt.TabFocus), editor.objectName())
        intros = page.findChildren(QLabel, "settings_page_intro")
        self.assertEqual(len(intros), 1)

    def test_hosted_page_does_not_repeat_the_shell_intro(self):
        service = ApplicationSettingsService(document=MemorySettingsDocumentPort())
        session = service.begin_session()

        class _Host:
            def draft_value(self, key: str):
                values = flatten_snapshot(service.snapshot())
                values.update(session.dirty_patch())
                return values[key]

            def stage_value(self, key: str, value) -> None:
                session.stage(key, value)

            def bind_draft_reloaded(self, _callback) -> None:
                return

        page = ComponentsSettingsPage(ColorLibrary(), host=_Host())
        self.addCleanup(page.deleteLater)
        self.assertEqual(page.findChildren(QLabel, "settings_page_intro"), [])

    def test_color_editor_does_not_write_library(self):
        library = ColorLibrary()
        before = list(library.recent_colors)
        page = ComponentsSettingsPage(library)
        self.addCleanup(page.deleteLater)
        row = page._rows["components.line.color"]
        row.inherit_box.setChecked(False)
        row.value_editor.set_color("#123456", emit=True, record_recent=False)
        self.assertEqual(row.value_editor.color_button.text(), "Choose color…")
        self.assertEqual(library.recent_colors, before)
        self.assertEqual(library.favorite_colors, [])
