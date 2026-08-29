import json
import os
import tempfile
import unittest
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QSettings, Qt
from PySide6.QtGui import QShowEvent
from PySide6.QtWidgets import QApplication, QPlainTextEdit

from main import MainWindow
from mygui.database import ColumnRef, ColumnType, scipy_fit_adapter
from mygui.excel_io import ExcelColumnSpec, ExcelSheetSpec
from mygui.figuremodify.components import ComponentKind
from mygui.resource_limits import ResourceLimits
from mygui.resources import REPOSITORY_ROOT
from mygui.template_library import (
    TemplateApplyService,
    TemplateExtractor,
    TemplateLibrary,
    TemplateMatcher,
    normalize_header,
    parse_template,
    parse_template_record,
    template_to_dict,
    validate_template,
)
from mygui.widgets.settings_center.templates_page import (
    TEMPLATES_EMPTY_DESCRIPTION,
    TEMPLATES_PAGE_DESCRIPTION,
    TemplatesSettingsPage,
)
from mygui.widgets.template_workflow import TemplateApplyDialog, TemplateExtractDialog
from tests.axes_helpers import create_regular_axes


def imported_specs(x_values=None, y_values=None, *, names=("X", "Y"), target="Data"):
    return [
        ExcelSheetSpec(
            "source",
            target,
            [
                ExcelColumnSpec(names[0], ColumnType.NUMBER, x_values or [10, 20, 30, 40]),
                ExcelColumnSpec(names[1], ColumnType.NUMBER, y_values or [4, 9, 16, 25]),
                ExcelColumnSpec("Extra", ColumnType.TEXT, ["a", "b", "c", "d"]),
            ],
        )
    ]


class TemplateFeatureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.window = MainWindow()
        self.window.figure_window.add_figure(
            width=4,
            height=3,
            dpi=100,
            style="default",
            canva_name="Source Project",
        )
        self.canvas = self.window.figure_window.current_canva
        create_regular_axes(self.canvas)
        self.sheet = self.window.table.current_subtable().get_table(0).table_model.sheet
        self.sheet.columns[0].name = "X"
        self.sheet.columns[1].name = "Y"
        self.sheet.set_block(0, 0, [[0, 1], [1, 3], [2, 5], [3, 7]])
        self.x_ref = ColumnRef(
            self.canvas.project_id, self.sheet.id, self.sheet.columns[0].id
        )
        self.y_ref = ColumnRef(
            self.canvas.project_id, self.sheet.id, self.sheet.columns[1].id
        )
        pair = self.window.repository.line_pair(self.x_ref, self.y_ref)
        self.canvas.add_plot(
            pair.x,
            pair.y,
            "-",
            2,
            "black",
            "Observed",
            self.x_ref,
            self.y_ref,
        )
        self.extractor = TemplateExtractor(self.window.repository)
        self.library = TemplateLibrary(Path(self.temp.name) / "templates")

    def test_default_library_uses_repository_template_directory(self):
        self.assertEqual(TemplateLibrary().root, REPOSITORY_ROOT / "template")

    def tearDown(self):
        self.window.close()
        self.app.processEvents()
        self.temp.cleanup()

    def add_fit(self):
        pair = self.window.repository.line_pair(self.x_ref, self.y_ref)
        options = scipy_fit_adapter.default_fit_options("poly1")
        result = scipy_fit_adapter.fit_curve(
            pair.x[pair.valid_mask], pair.y[pair.valid_mask], "poly1", options
        )
        self.canvas.add_fit_curve(
            pair.x[pair.valid_mask],
            pair.y[pair.valid_mask],
            "red",
            "Linear fit",
            self.x_ref,
            self.y_ref,
            engine="Python",
            fit_type="poly1",
            fit_options=options,
            fit_result=result,
            expression=result["value_expression"],
            x_start=0,
            x_stop=3,
        )
        return result

    def template(self, *, fit=False):
        if fit:
            self.add_fit()
        return self.extractor.extract(self.canvas, name="Instrument Template", notes="Reusable")

    def test_extract_uses_only_referenced_columns_and_fresh_local_ids(self):
        fit_result = self.add_fit()
        self.sheet.add_column("Unused", ColumnType.NUMBER, values=[100, 200])
        source_ids = {
            item["id"] for item in self.canvas.component_snapshot()["components"]
        }
        template = self.extractor.extract(self.canvas, name="Instrument Template")

        self.assertEqual(
            [column.name for column in template.data_contract.sheets[0].columns],
            ["X", "Y"],
        )
        self.assertTrue(
            source_ids.isdisjoint(
                {item["id"] for item in template.figure["components"]}
            )
        )
        encoded = json.dumps(template_to_dict(template))
        for source_id in source_ids:
            self.assertNotIn(source_id, encoded)
        fit = next(item for item in template.figure["components"] if item["role"] == "fit_curve")
        self.assertIsNone(fit["data"]["fit_result"])
        self.assertEqual(fit["data"]["expression"], "")
        self.assertIsNotNone(fit_result)
        root = next(
            item for item in template.figure["components"]
            if item["id"] == template.figure["root_component_id"]
        )
        self.assertEqual(root["properties"]["name"], "{{project_name}}")

    def test_unconfigured_fit_blocks_extraction(self):
        pair = self.window.repository.line_pair(self.x_ref, self.y_ref)
        self.canvas.add_fit_curve(
            pair.x[pair.valid_mask],
            pair.y[pair.valid_mask],
            "red",
            "Not configured",
            self.x_ref,
            self.y_ref,
        )
        with self.assertRaisesRegex(ValueError, "Configure and run"):
            self.extractor.extract(self.canvas, name="Blocked")

    def test_schema_is_closed_exact_and_rejects_nonfinite_and_unknown_tokens(self):
        raw = template_to_dict(self.template())
        for version in (True, 1, 2, 3, 4, 5.0, 0, -1):
            with self.subTest(version=version):
                candidate = deepcopy(raw)
                candidate["schema_version"] = version
                with self.assertRaisesRegex(ValueError, "schema version"):
                    parse_template(candidate)
        candidate = deepcopy(raw)
        candidate["extra"] = True
        with self.assertRaisesRegex(ValueError, "expected exactly"):
            parse_template(candidate)
        candidate = deepcopy(raw)
        candidate["figure"]["components"][0]["properties"]["dpi"] = float("nan")
        with self.assertRaisesRegex(ValueError, "finite"):
            parse_template(candidate)
        candidate = deepcopy(raw)
        root_id = candidate["figure"]["root_component_id"]
        root = next(item for item in candidate["figure"]["components"] if item["id"] == root_id)
        root["properties"]["name"] = "{{secret_variable}}"
        with self.assertRaisesRegex(ValueError, "unknown variables"):
            parse_template(candidate)

    def test_library_is_lazy_atomic_and_isolates_corrupt_files(self):
        template = self.template()
        self.assertEqual(self.library.entries(), ())
        self.assertFalse(self.library.root.exists())
        path = self.library.save(template)
        self.assertTrue(path.is_file())
        old_bytes = path.read_bytes()
        with self.assertRaisesRegex(ValueError, "already exists"):
            self.library.save(replace(template, metadata=replace(template.metadata, id="aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa", name="instrument template")))
        corrupt = self.library.root / "bad.mygui-template.json"
        corrupt.write_text("{broken", encoding="utf-8")
        entries = self.library.entries()
        self.assertEqual(sum(entry.valid for entry in entries), 1)
        self.assertEqual(sum(not entry.valid for entry in entries), 1)

        with mock.patch("mygui.template_library.storage.os.replace", side_effect=OSError("locked")):
            with self.assertRaisesRegex(OSError, "locked"):
                self.library.save_notes(template.metadata.id, "changed")
        self.assertEqual(path.read_bytes(), old_bytes)
        self.assertEqual(list(self.library.root.glob("*.tmp")), [])

    def test_library_crud_import_export_and_size_budget(self):
        template = self.template()
        self.library.save(template)
        renamed = self.library.rename(template.metadata.id, "Renamed")
        self.assertEqual(self.library.path_for(template.metadata.id).name, f"{template.metadata.id}.mygui-template.json")
        self.assertEqual(renamed.metadata.name, "Renamed")
        noted = self.library.save_notes(template.metadata.id, "new notes")
        self.assertEqual(noted.metadata.notes, "new notes")
        duplicate = self.library.duplicate(template.metadata.id)
        self.assertNotEqual(duplicate.metadata.id, template.metadata.id)
        exported = Path(self.temp.name) / "exported.json"
        self.library.export_template(template.metadata.id, exported)
        with self.assertRaises(FileExistsError):
            self.library.import_template(exported)
        imported = self.library.import_template(exported, replace_same_id=True)
        self.assertEqual(imported.metadata.id, template.metadata.id)
        with mock.patch(
            "mygui.template_library.storage.load_resource_limits",
            return_value=ResourceLimits(max_template_bytes=1),
        ):
            with self.assertRaisesRegex(ValueError, "file-size budget"):
                self.library.save(duplicate, replace_existing=True)
        self.library.delete(duplicate.metadata.id)
        self.assertFalse(self.library.path_for(duplicate.metadata.id).exists())

    def test_header_matching_normalization_reorder_extra_ambiguity_and_types(self):
        template = self.template()
        sheet = template.data_contract.sheets[0]
        renamed_columns = (
            replace(sheet.columns[0], name="Ｔｅｍｐ　 K"),
            replace(sheet.columns[1], name="Signal (V)"),
        )
        template = replace(
            template,
            data_contract=replace(
                template.data_contract,
                sheets=(replace(sheet, columns=renamed_columns),),
            ),
        )
        specs = imported_specs(names=("  temp   k ", "signal (v)"))
        specs[0].columns.reverse()
        plan = TemplateMatcher().match(template, specs)
        self.assertTrue(plan.valid)
        self.assertEqual(normalize_header(" Ａ　 B "), "a b")

        ambiguous = TemplateMatcher().match(template, specs + deepcopy(specs))
        self.assertFalse(ambiguous.valid)
        self.assertEqual(ambiguous.ambiguous_slots, (sheet.id,))
        explicit = TemplateMatcher().match(
            template, specs + deepcopy(specs), explicit_sheet_mapping={sheet.id: 1}
        )
        self.assertTrue(explicit.valid)
        wrong = deepcopy(specs)
        next(
            column
            for column in wrong[0].columns
            if normalize_header(column.name) == "signal (v)"
        ).type = ColumnType.TEXT
        self.assertFalse(TemplateMatcher().match(template, wrong).valid)
        missing = deepcopy(specs)
        missing[0].columns.pop()
        self.assertFalse(TemplateMatcher().match(template, missing).valid)

    def test_prepare_remaps_every_runtime_identity_resolves_text_and_refits(self):
        template = self.template(fit=True)
        title = next(item for item in template.figure["components"] if item["role"] == "title")
        title["properties"]["text"] = "{{source_file_stem}} — {{project_name}}"
        validate_template(template)
        source_ids = {item["id"] for item in template.figure["components"]}
        service = TemplateApplyService(self.window.repository)
        plan = service.prepare(
            template,
            imported_specs(y_values=[2, 5, 8, 11]),
            source_file="sample-02.csv",
            project_name="Applied Project",
        )
        runtime_ids = {item["id"] for item in plan.project_snapshot["figure"]["components"]}
        self.assertTrue(source_ids.isdisjoint(runtime_ids))
        fitted = next(
            item for item in plan.project_snapshot["figure"]["components"]
            if item["role"] == "fit_curve"
        )
        self.assertIsNotNone(fitted["data"]["fit_result"])
        self.assertTrue(fitted["data"]["expression"])
        applied_title = next(
            item for item in plan.project_snapshot["figure"]["components"]
            if item["role"] == "title"
        )
        self.assertEqual(applied_title["properties"]["text"], "sample-02 — Applied Project")
        all_refs = json.dumps(plan.project_snapshot["figure"])
        self.assertNotIn(self.canvas.project_id, all_refs)
        self.assertIn(plan.project.id, all_refs)
        self.assertEqual(len(plan.project.sheets[next(iter(plan.project.sheets))].columns), 3)

    def test_fit_failure_and_cancel_never_publish(self):
        template = self.template(fit=True)
        before = set(self.window.repository.projects)
        service = TemplateApplyService(self.window.repository)
        with mock.patch(
            "mygui.database.scipy_fit_adapter.fit_curve",
            side_effect=RuntimeError("fit failed"),
        ):
            with self.assertRaisesRegex(RuntimeError, "fit failed"):
                service.prepare(
                    template,
                    imported_specs(),
                    source_file="data.csv",
                    project_name="Failed Project",
                )
        self.assertEqual(set(self.window.repository.projects), before)
        with self.assertRaisesRegex(RuntimeError, "cancelled"):
            service.prepare(
                template,
                imported_specs(),
                source_file="data.csv",
                project_name="Cancelled Project",
                cancelled=lambda: True,
            )
        self.assertEqual(set(self.window.repository.projects), before)

    def test_template_v1_migration_and_custom_fit_range(self):
        template = self.template(fit=True)
        raw_v3 = template_to_dict(template)
        # Create strict v1 template payload
        raw_v1 = deepcopy(raw_v3)
        raw_v1["schema_version"] = 1
        for comp in raw_v1["figure"]["components"]:
            if comp.get("kind") == "line" and comp.get("role") == "fit_curve":
                comp["data"].pop("fit_input_range", None)
            if comp.get("kind") == "axes":
                comp["data"].pop("geometry", None)
                comp["properties"]["in_layout"] = True

        migrated = parse_template_record(raw_v1)
        self.assertEqual(template_to_dict(migrated)["schema_version"], 5)
        fit_v1 = next(
            c for c in migrated.figure["components"]
            if c.get("role") == "fit_curve"
        )
        self.assertEqual(fit_v1["data"]["fit_input_range"], {"kind": "all"})
        axes_v1 = next(
            c for c in migrated.figure["components"]
            if c.get("kind") == "axes"
        )
        self.assertEqual(axes_v1["data"]["geometry"], {"mode": "grid"})
        self.assertNotIn("in_layout", axes_v1["properties"])

        # Test v2 -> v3 migration
        raw_v2 = deepcopy(raw_v3)
        raw_v2["schema_version"] = 2
        for comp in raw_v2["figure"]["components"]:
            if comp.get("kind") == "axes":
                comp["data"].pop("geometry", None)
                comp["properties"]["in_layout"] = True
        migrated_v2 = parse_template_record(raw_v2)
        self.assertEqual(template_to_dict(migrated_v2)["schema_version"], 5)
        axes_v2 = next(
            c for c in migrated_v2.figure["components"]
            if c.get("kind") == "axes"
        )
        self.assertEqual(axes_v2["data"]["geometry"], {"mode": "grid"})
        self.assertNotIn("in_layout", axes_v2["properties"])

        # Test v3 -> v4 -> v5 and direct v4 -> v5 migrations
        raw_v3_direct = template_to_dict(template)
        raw_v3_direct["schema_version"] = 3
        migrated_v3 = parse_template_record(raw_v3_direct)
        self.assertEqual(template_to_dict(migrated_v3)["schema_version"], 5)
        self.assertEqual(migrated_v3.figure, template.figure)
        raw_v4_direct = template_to_dict(template)
        raw_v4_direct["schema_version"] = 4
        migrated_v4 = parse_template_record(raw_v4_direct)
        self.assertEqual(template_to_dict(migrated_v4)["schema_version"], 5)
        self.assertEqual(migrated_v4.figure, template.figure)

        # Bounded fit input range in template
        fit_v3 = next(
            c for c in template.figure["components"]
            if c.get("role") == "fit_curve"
        )
        fit_v3["data"]["fit_input_range"] = {
            "kind": "bounded",
            "minimum": 1.0,
            "maximum": 3.0,
        }
        validate_template(template)

        service = TemplateApplyService(self.window.repository)
        plan = service.prepare(
            template,
            imported_specs(
                x_values=[0.0, 1.0, 2.0, 3.0, 4.0],
                y_values=[10, 20, 30, 40, 50],
            ),
            source_file="sample-bounded.csv",
            project_name="Bounded Applied",
        )
        applied_fit = next(
            item for item in plan.project_snapshot["figure"]["components"]
            if item["role"] == "fit_curve"
        )
        self.assertEqual(
            applied_fit["data"]["fit_input_range"],
            {"kind": "bounded", "minimum": 1.0, "maximum": 3.0},
        )
        self.assertEqual(applied_fit["data"]["x_start"], 1.0)
        self.assertEqual(applied_fit["data"]["x_stop"], 3.0)

    def test_publish_is_dirty_empty_history_and_rolls_back_materialization_failure(self):
        template = self.template()
        service = TemplateApplyService(self.window.repository)
        plan = service.prepare(
            template,
            imported_specs(),
            source_file="data.csv",
            project_name="Applied",
        )
        service.publish(plan, table=self.window.table, figure_window=self.window.figure_window)
        canvas = self.window.figure_window.current_canva
        self.assertEqual(canvas.project_id, plan.project.id)
        self.assertIsNone(canvas.project_path)
        self.assertTrue(self.window.figure_window.is_canvas_dirty(canvas))
        self.assertEqual(self.window.repository.undo_stack(plan.project.id).count(), 0)

        second = service.prepare(
            template,
            imported_specs(),
            source_file="data2.csv",
            project_name="Broken",
        )
        previous_canvas = self.window.figure_window.current_canva
        before_ids = set(self.window.repository.projects)
        with mock.patch.object(
            self.window.figure_window,
            "load_project_figure_snapshot",
            side_effect=RuntimeError("materialize failed"),
        ):
            with self.assertRaisesRegex(RuntimeError, "materialize failed"):
                service.publish(
                    second,
                    table=self.window.table,
                    figure_window=self.window.figure_window,
                )
        self.assertEqual(set(self.window.repository.projects), before_ids)
        self.assertIs(self.window.figure_window.current_canva, previous_canvas)

    def test_template_autoscale_recomputes_but_fixed_range_is_preserved(self):
        auto_template = self.template()
        service = TemplateApplyService(self.window.repository)
        auto_plan = service.prepare(
            auto_template,
            imported_specs(x_values=[100, 120, 180, 200]),
            source_file="auto.csv",
            project_name="Auto",
        )
        service.publish(auto_plan, table=self.window.table, figure_window=self.window.figure_window)
        auto_axes = self.window.figure_window.current_canva.component_registry.query(
            kind=ComponentKind.AXES
        )[0]
        self.assertGreater(auto_axes.state.properties["xlim"][0], 50)

        source_axes = self.canvas.component_registry.query(kind=ComponentKind.AXES)[0]
        self.assertTrue(source_axes.set_property("xlim", [-2.0, 8.0]).ok)
        self.assertTrue(source_axes.set_property("autoscalex_on", False).ok)
        fixed_template = self.extractor.extract(self.canvas, name="Fixed Template")
        fixed_plan = service.prepare(
            fixed_template,
            imported_specs(x_values=[100, 120, 180, 200]),
            source_file="fixed.csv",
            project_name="Fixed",
        )
        service.publish(fixed_plan, table=self.window.table, figure_window=self.window.figure_window)
        fixed_axes = self.window.figure_window.current_canva.component_registry.query(
            kind=ComponentKind.AXES
        )[0]
        self.assertEqual(fixed_axes.state.properties["xlim"], [-2.0, 8.0])

    def test_edit_style_and_settings_template_surfaces(self):
        self.window.template_workflow.library = self.library
        menu = self.window.title_bar.menu_bar
        menu._sync_edit_actions()
        self.assertEqual(
            [action.text() for action in menu.edit_menu.actions()],
            ["Change to Template…", "", "Settings"],
        )
        self.assertTrue(menu.change_to_template_action.isEnabled())
        style = self.window.title_bar.selector_style_bar
        self.assertEqual(next(iter(style.action_dict)), "Apply Template")
        self.assertTrue(style.action_dict["Apply Template"].isEnabled())

        template = self.template()
        self.library.save(template)
        extract_dialog = TemplateExtractDialog(template)
        try:
            self.assertGreater(extract_dialog.text_table.rowCount(), 0)
            self.assertEqual(extract_dialog.result_template().metadata.id, template.metadata.id)
        finally:
            extract_dialog.close()
        apply_dialog = TemplateApplyDialog(self.window.template_workflow)
        try:
            apply_dialog.workflow.library = self.library
            apply_dialog._populate_templates()
            self.assertEqual(apply_dialog.template_list.count(), 1)
        finally:
            apply_dialog.close()

    def test_settings_templates_page_lists_corruption_and_immediate_notes(self):
        template = self.template()
        self.library.save(template)
        (self.library.root / "bad.mygui-template.json").write_text("bad", encoding="utf-8")

        class Host:
            def __init__(self):
                self.messages = []

            def request_immediate_command(self, _command_id, *, handler, **_kwargs):
                handler()

            def emit_message(self, text, level="info"):
                self.messages.append((text, level))

        host = Host()
        self.window.template_workflow.library = self.library
        page = TemplatesSettingsPage(
            self.library, self.window.template_workflow, host
        )
        try:
            self.assertEqual(page.list.count(), 2)
            valid_row = next(
                row
                for row in range(page.list.count())
                if page.list.item(row).data(Qt.UserRole + 2) == template.metadata.id
            )
            page.list.setCurrentRow(valid_row)
            self.assertFalse(page.notes_button.isEnabled())
            page.notes.setPlainText("edited")
            self.assertTrue(page.notes_button.isEnabled())
            page._save_notes()
            self.assertFalse(page.notes_button.isEnabled())
            self.assertEqual(self.library.get(template.metadata.id).metadata.notes, "edited")
            page.search.setText("bad")
            self.assertEqual(sum(not page.list.item(row).isHidden() for row in range(2)), 1)
        finally:
            page.close()

    def test_settings_templates_page_empty_and_corrupt_states(self):
        class Host:
            def __init__(self):
                self.messages = []

            def request_immediate_command(self, _command_id, *, handler, **_kwargs):
                handler()

            def emit_message(self, text, level="info"):
                self.messages.append((text, level))

        host = Host()
        empty_library = TemplateLibrary(Path(self.temp.name) / "empty_templates")
        self.window.template_workflow.library = empty_library
        page = TemplatesSettingsPage(
            empty_library, self.window.template_workflow, host
        )
        try:
            # Empty library state
            self.assertEqual(page.list.count(), 0)
            self.assertFalse(page.empty_frame.isHidden())
            self.assertTrue(page.miss_frame.isHidden())
            self.assertTrue(page.header_card.isHidden())
            self.assertFalse(page.apply_button.isEnabled())
            self.assertFalse(page.delete_button.isEnabled())
            self.assertNotIn("below", page.empty_description.text().casefold())
            self.assertEqual(page.empty_description.text(), TEMPLATES_EMPTY_DESCRIPTION)
            self.assertEqual(
                page.empty_import_button.objectName(), "template_empty_import_button"
            )

            # Add a corrupt template
            corrupt_file = empty_library.ensure_directory() / "malformed.mygui-template.json"
            corrupt_file.write_text("{not valid json", encoding="utf-8")
            page.refresh()
            self.assertEqual(page.list.count(), 1)
            self.assertTrue(page.empty_frame.isHidden())
            self.assertTrue(page.miss_frame.isHidden())
            self.assertFalse(page.error_frame.isHidden())
            self.assertFalse(page.header_card.isHidden())
            self.assertIn("Corrupted", page.error_title.text())
            self.assertFalse(page.apply_button.isEnabled())
            self.assertTrue(page.delete_button.isEnabled())

            # Delete corrupt template
            page._delete()
            self.assertFalse(corrupt_file.exists())
            self.assertEqual(page.list.count(), 0)
            self.assertFalse(page.empty_frame.isHidden())
        finally:
            page.close()

    def test_settings_templates_page_refresh_button_and_show_event(self):
        class Host:
            def __init__(self):
                self.messages = []

            def request_immediate_command(self, _command_id, *, handler, **_kwargs):
                handler()

            def emit_message(self, text, level="info"):
                self.messages.append((text, level))

        host = Host()
        library = TemplateLibrary(Path(self.temp.name) / "refresh_templates")
        template = self.template()
        library.save(template)

        self.window.template_workflow.library = library
        page = TemplatesSettingsPage(
            library, self.window.template_workflow, host
        )
        try:
            self.assertEqual(page.list.count(), 1)

            # Create an additional template on disk
            second = self.extractor.extract(self.canvas, name="Second Template")
            library.save(second)
            self.assertEqual(page.list.count(), 1)  # not refreshed yet

            # Click refresh button
            page.refresh_button.click()
            self.assertEqual(page.list.count(), 2)
            self.assertTrue(any(msg[0] == "Template library refreshed" for msg in host.messages))

            # Create a third template on disk
            third = self.extractor.extract(self.canvas, name="Third Template")
            library.save(third)

            # Re-trigger showEvent
            page.showEvent(QShowEvent())
            self.assertEqual(page.list.count(), 3)
        finally:
            page.close()

    def test_settings_templates_page_layout_copy_and_search_miss(self):
        class Host:
            def __init__(self):
                self.messages = []

            def request_immediate_command(self, _command_id, *, handler, **_kwargs):
                handler()

            def emit_message(self, text, level="info"):
                self.messages.append((text, level))

        self.assertNotIn("below", TEMPLATES_PAGE_DESCRIPTION.casefold())
        self.assertNotIn("below", TEMPLATES_EMPTY_DESCRIPTION.casefold())

        host = Host()
        empty_library = TemplateLibrary(Path(self.temp.name) / "layout_empty_templates")
        self.window.template_workflow.library = empty_library
        empty_page = TemplatesSettingsPage(
            empty_library, self.window.template_workflow, host
        )
        try:
            empty_page.resize(640, 420)
            empty_page.show()
            self.app.processEvents()
            frame = empty_page.empty_frame
            desc = empty_page.empty_description
            self.assertGreater(frame.height(), desc.height())
            self.assertLessEqual(desc.geometry().bottom(), frame.contentsRect().bottom())
            self.assertLessEqual(
                empty_page.empty_title.geometry().bottom(), frame.contentsRect().bottom()
            )
            self.assertFalse(empty_page.empty_import_button.isHidden())
        finally:
            empty_page.close()

        library = TemplateLibrary(Path(self.temp.name) / "layout_templates")
        template = self.template()
        library.save(template)
        self.window.template_workflow.library = library
        page = TemplatesSettingsPage(library, self.window.template_workflow, host)
        try:
            page.resize(520, 420)
            page.show()
            self.app.processEvents()
            self.assertTrue(page.empty_frame.isHidden())
            self.assertFalse(page.detail_page.isHidden())
            header = page.header_card
            self.assertFalse(header.isHidden())
            for button in (
                page.apply_button,
                page.update_button,
                page.rename_button,
                page.duplicate_button,
                page.export_button,
                page.delete_button,
            ):
                self.assertTrue(button.isVisible())
                self.assertTrue(header.rect().contains(button.geometry().center()))

            self.assertIsInstance(page.contract, QPlainTextEdit)
            self.assertTrue(page.contract.isReadOnly())
            page.contract.setPlainText("\n".join(f"column-{index}" for index in range(24)))
            page.resize(520, 420)
            self.app.processEvents()
            compact_doc = page.contract.document().size().height()
            compact_widget = page.contract.height()
            self.assertGreater(page.contract.verticalScrollBar().maximum(), 0)
            page.resize(520, 720)
            self.app.processEvents()
            stretched_doc = page.contract.document().size().height()
            self.assertAlmostEqual(compact_doc, stretched_doc, delta=2)
            self.assertGreater(page.contract.height(), compact_widget)

            page.search.setText("zzz-no-such-template")
            self.app.processEvents()
            self.assertTrue(page.empty_frame.isHidden())
            self.assertTrue(page.header_card.isHidden())
            self.assertFalse(page.miss_frame.isHidden())
            self.assertIn("matching search", page.miss_title.text().casefold())
        finally:
            page.close()


class TemplateSettingsIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_templates_page_is_not_a_persisted_settings_page(self):
        with tempfile.TemporaryDirectory() as directory:
            settings = QSettings(str(Path(directory) / "settings.ini"), QSettings.IniFormat)
            window = MainWindow(settings=settings)
            try:
                center = window.settings_center.present("templates")
                self.assertEqual(center.nav_list.currentItem().data(Qt.UserRole), "templates")
                self.assertFalse(center.restore_defaults_button.isEnabled())
            finally:
                window.close()
                self.app.processEvents()


if __name__ == "__main__":
    unittest.main()
