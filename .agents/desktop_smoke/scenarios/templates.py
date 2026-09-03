"""Chart Templates extract/apply/Settings desktop smoke. Group id: templates."""

from __future__ import annotations

from pathlib import Path
import time
from typing import Any, Callable

from PySide6.QtCore import QTimer

from mygui.application_settings.keys import PAGE_TEMPLATES
from mygui.database import ColumnRef, ColumnType
from mygui.excel_io import ExcelColumnSpec, ExcelSheetSpec
from mygui.figuremodify.axes_layout import AxesLayoutSpec
from mygui.figuremodify.components import ComponentKind
from mygui.figuremodify.style_base.color_models import ColorSelection
from mygui.template_library import TEMPLATE_FILE_SUFFIX, TemplateExtractor
from mygui.widgets.settings_center.templates_page import (
    TEMPLATES_MISS_DESCRIPTION,
    TemplatesSettingsPage,
)
from mygui.widgets.template_workflow import TemplateApplyDialog, TemplateExtractDialog

from desktop_smoke.harness import SmokeError, SmokeHarness


def run_templates_scenarios(harness: SmokeHarness) -> list[dict[str, Any]]:
    """Walk extract, Settings Templates, immediate writes, and Apply mapping."""

    results: list[dict[str, Any]] = []
    results.append(
        _run_case(harness, "templates.extract", lambda: _scenario_extract(harness))
    )
    results.append(
        _run_case(
            harness,
            "templates.settings_library",
            lambda: _scenario_settings_library(harness),
        )
    )
    results.append(
        _run_case(harness, "templates.apply", lambda: _scenario_apply(harness))
    )
    return results


def _run_case(
    harness: SmokeHarness,
    scenario_id: str,
    body: Callable[[], None],
) -> dict[str, Any]:
    before = len(harness.screenshots)
    try:
        body()
        return {
            "id": scenario_id,
            "status": "passed",
            "screenshotCount": len(harness.screenshots) - before,
        }
    except Exception as exc:  # noqa: BLE001
        try:
            harness.dismiss_all_dialogs()
            harness.grab_main(f"{scenario_id.replace('.', '-')}-failure")
        except Exception:
            pass
        return {
            "id": scenario_id,
            "status": "failed",
            "error": f"{type(exc).__name__}: {exc}",
            "screenshotCount": len(harness.screenshots) - before,
        }


def _library(harness: SmokeHarness):
    return harness.window.template_workflow.library


def _template_files(harness: SmokeHarness) -> list[Path]:
    root = Path(_library(harness).root)
    if not root.is_dir():
        return []
    return sorted(root.glob(f"*{TEMPLATE_FILE_SUFFIX}"))


def _scenario_extract(harness: SmokeHarness) -> None:
    canvas = harness.create_project("Smoke_Template_Source")
    canvas.create_axes_layout(AxesLayoutSpec.grid(1, 1))
    harness.pump(50)
    harness.seed_multi_column_table(canvas)
    sheet = harness.window.table.current_subtable().get_table(0).table_model.sheet
    sheet.columns[0].name = "X"
    sheet.columns[1].name = "Y"
    x_ref = ColumnRef(canvas.project_id, sheet.id, sheet.columns[0].id)
    y_ref = ColumnRef(canvas.project_id, sheet.id, sheet.columns[1].id)
    canvas.add_plots(
        x_ref,
        (y_ref,),
        style="-",
        size=6.0,
        linewidth=1.5,
        preprocess=None,
        color_selection=ColorSelection(color="#1f77b4"),
    )
    harness.pump(60)

    extractor = TemplateExtractor(harness.window.table.repository)
    draft = extractor.extract(canvas, name="Smoke Instrument Template", notes="desktop smoke")
    dialog = TemplateExtractDialog(draft, parent=harness.window)
    dialog.setModal(False)
    dialog.show()
    harness.pump(80)
    harness.grab(dialog, "templates-01-extract-dialog")
    template = dialog.result_template()
    _library(harness).save(template)
    dialog.accept()
    harness.pump(40)
    if not _template_files(harness):
        raise SmokeError("Extract did not write a template file into the isolated library.")
    harness.grab_main("templates-02-main-after-extract")


def _templates_page(harness: SmokeHarness) -> TemplatesSettingsPage:
    dialog = harness.present_settings(PAGE_TEMPLATES)
    page = dialog.findChild(TemplatesSettingsPage)
    if page is None:
        raise SmokeError("TemplatesSettingsPage was not created.")
    return page


def _scenario_settings_library(harness: SmokeHarness) -> None:
    files_before = _template_files(harness)
    if not files_before:
        raise SmokeError("Settings library scenario requires an extracted template.")
    dialog = harness.present_settings(PAGE_TEMPLATES)
    if dialog.restore_defaults_button.isEnabled():
        raise SmokeError("Templates Restore page defaults must stay disabled.")
    page = _templates_page(harness)
    page.refresh()
    harness.pump(60)
    if page.list.count() < 1:
        raise SmokeError("Settings Templates list is empty after extract.")
    page.list.setCurrentRow(0)
    harness.pump(40)
    harness.grab(dialog, "templates-03-settings-detail")
    harness.grab(page, "templates-03-settings-detail-inner")

    page.search.setText("zzz-no-such-template")
    harness.pump(40)
    if page.miss_frame.isHidden():
        raise SmokeError("Template search miss placeholder was not shown.")
    if page.miss_description.text() != TEMPLATES_MISS_DESCRIPTION:
        raise SmokeError(
            "Templates miss copy is "
            f"{page.miss_description.text()!r}, expected {TEMPLATES_MISS_DESCRIPTION!r}."
        )
    harness.grab(dialog, "templates-04-search-miss")
    page.search.clear()
    harness.pump(40)

    template = page._template()
    if template is None:
        raise SmokeError("Could not read the selected template from Settings.")
    original_name = template.metadata.name

    QTimer.singleShot(0, harness.accept_input_dialog)
    page.duplicate_button.click()
    harness.pump(80)
    harness.accept_input_dialog()
    page.refresh()
    harness.pump(40)
    files_after_dup = _template_files(harness)
    if len(files_after_dup) < 2:
        duplicated = _library(harness).duplicate(template.metadata.id, f"{original_name} Copy")
        page.refresh(duplicated.metadata.id)
        harness.pump(40)
        files_after_dup = _template_files(harness)
    if len(files_after_dup) < 2:
        raise SmokeError("Duplicate did not write a second template file immediately.")
    harness.grab(dialog, "templates-05-after-duplicate")

    harness.close_settings(cancel=True)
    if len(_template_files(harness)) < 2:
        raise SmokeError("Settings Cancel rolled back an immediate template duplicate.")

    dialog = harness.present_settings(PAGE_TEMPLATES)
    page = _templates_page(harness)
    page.refresh()
    harness.pump(40)
    if page.list.count() < 2:
        raise SmokeError("Reopened Templates page lost the duplicated file.")
    page.list.setCurrentRow(page.list.count() - 1)
    harness.pump(30)
    harness.click_and_accept_confirm(page.delete_button)
    page.refresh()
    harness.pump(40)
    if len(_template_files(harness)) < 1:
        raise SmokeError("Delete removed every isolated template file.")
    harness.grab(dialog, "templates-06-after-delete")
    harness.close_settings(cancel=False)


def _apply_specs() -> list[ExcelSheetSpec]:
    return [
        ExcelSheetSpec(
            "source",
            "Data",
            [
                ExcelColumnSpec("X", ColumnType.NUMBER, [10.0, 20.0, 30.0, 40.0]),
                ExcelColumnSpec("Y", ColumnType.NUMBER, [4.0, 9.0, 16.0, 25.0]),
                ExcelColumnSpec("Extra", ColumnType.TEXT, ["a", "b", "c", "d"]),
            ],
        )
    ]


def _scenario_apply(harness: SmokeHarness) -> None:
    templates = list(_library(harness).templates())
    if not templates:
        raise SmokeError("Apply scenario requires a saved template.")
    template = templates[0]
    source_path = Path(harness._tempdir.name) / "template-apply.csv"
    source_path.write_text("X,Y,Extra\n10,4,a\n20,9,b\n30,16,c\n40,25,d\n", encoding="utf-8")

    before_ids = {
        canvas.project_id
        for canvas in _iter_canvases(harness)
    }
    dialog = TemplateApplyDialog(
        harness.window.template_workflow,
        parent=harness.window,
        template_id=template.metadata.id,
    )
    dialog.setModal(False)
    dialog.show()
    harness.pump(80)
    if dialog.template_list.count() < 1:
        raise SmokeError("Apply Template dialog listed no templates.")
    harness.grab(dialog, "templates-07-apply-select")

    dialog.next_button.click()
    harness.pump(40)
    dialog._source_file = source_path
    dialog._specs = _apply_specs()
    dialog.source_edit.setText(str(source_path))
    dialog.project_name_edit.setText("Smoke_Applied_Template")
    dialog.data_summary.setText("1 Sheet(s), 3 column(s) selected.")
    harness.grab(dialog, "templates-08-apply-data")

    dialog.next_button.click()
    harness.pump(80)
    if dialog.mapping_table.rowCount() < 1:
        raise SmokeError("Apply mapping table was empty.")
    harness.grab(dialog, "templates-09-apply-mapping")

    dialog.next_button.click()
    harness.pump(80)
    harness.grab(dialog, "feedback-template-busy")
    deadline = time.perf_counter() + 30.0
    while time.perf_counter() < deadline:
        harness.pump(200)
        try:
            visible = dialog.isVisible()
            progress = dialog.progress_label.text()
        except RuntimeError:
            visible = False
            progress = ""
        if not visible or "success" in progress.casefold():
            break
        if progress and "could not" in progress.casefold():
            raise SmokeError(f"Template apply failed: {progress}")
    else:
        raise SmokeError("Template apply did not finish within 30s.")

    harness.dismiss_all_dialogs()
    harness.pump(80)
    after_ids = {
        canvas.project_id
        for canvas in _iter_canvases(harness)
    }
    if after_ids <= before_ids:
        raise SmokeError("Apply Template did not publish a new project tab.")
    restored = harness.window.figure_window.current_canva
    if restored is None:
        raise SmokeError("Applied template canvas is missing.")
    plots = restored.component_registry.query(kind=ComponentKind.LINE)
    if not plots:
        raise SmokeError("Applied template is missing the expected Line component.")
    harness.grab_canvas("templates-10-applied-canvas")
    harness.grab_main("templates-11-applied-main")


def _iter_canvases(harness: SmokeHarness):
    return list(harness.window.figure_window.canvases())
