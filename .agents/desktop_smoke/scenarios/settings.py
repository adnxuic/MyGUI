"""Settings Center + NEXT_USE desktop smoke. Group id: settings."""

from __future__ import annotations

import time
from typing import Any, Callable

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import (
    QApplication,
    QGroupBox,
    QLabel,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QTabWidget,
    QWidget,
)

from mygui.application_settings.keys import (
    COMPONENTS_AXES_FACECOLOR,
    COMPONENTS_LINE_COLOR,
    COMPONENTS_LINE_LINEWIDTH,
    PAGE_APPEARANCE,
    PAGE_AXES_COMPONENTS,
    PAGE_COMPONENTS,
    PAGE_EXPORT,
    PAGE_INTEGRATIONS,
    PAGE_MAINTENANCE,
    PAGE_NEW_FIGURE,
    PAGE_WORKSPACE,
)
from mygui.application_settings.models import DefaultValueMode
from mygui.figuremodify.axes_layout import AxesLayoutSpec
from mygui.figuremodify.components import ComponentKind
from mygui.figuremodify.style_base.color_models import ColorSelection, normalize_color
from mygui.widgets.settings_center.geometry import NAV_PANE_WIDTH
from mygui.widgets.settings_center.inheritable_editors import InheritableSettingRow
from mygui.widgets.settings_center.maintenance_page import MaintenanceSettingsPage
from mygui.widgets.settings_center.pages import SHELL_PAGE_METADATA, SHELL_PAGE_ORDER
from mygui.widgets.settings_center.window import SettingsCenterWindow
from mygui.widgets.settings_pages.workspace import WorkspaceSettingsPage
from mygui.widgets.title_bar.titlebar_dialog.py_chart_dialog import (
    PyCurveDialog,
    PyScatterDialog,
)
from mygui.widgets.title_bar.titlebar_dialog.py_element_dialog import PyTextDialog
from mygui.widgets.title_bar.titlebar_dialog.py_title_bar_dialog import PyLayoutDialog

from desktop_smoke.harness import (
    OVERRIDE_FACECOLOR,
    OVERRIDE_LINEWIDTH,
    ProjectSeed,
    SmokeError,
    SmokeHarness,
)

PAGE_SHOT_NAMES = {
    PAGE_APPEARANCE: "02-page-appearance",
    PAGE_WORKSPACE: "03-page-workspace",
    PAGE_NEW_FIGURE: "04-page-new-figure",
    PAGE_COMPONENTS: "05-page-components",
    PAGE_AXES_COMPONENTS: "06-page-axes-components",
    PAGE_EXPORT: "07-page-export",
    PAGE_INTEGRATIONS: "08-page-integrations",
    PAGE_MAINTENANCE: "09-page-maintenance",
}
EXPECTED_NAV_TITLES = tuple(
    SHELL_PAGE_METADATA[page_id].title for page_id in SHELL_PAGE_ORDER
)
LINE_KEYS = 6
SCATTER_KEYS = 4
TEXT_KEYS = 5


def run_settings_scenarios(harness: SmokeHarness) -> list[dict[str, Any]]:
    """Walk Settings Center and the minimum NEXT_USE creation path."""

    results: list[dict[str, Any]] = []
    seed = harness.seed_default_project()
    harness.grab(seed.canvas, "00-canvas-seed")

    results.append(
        _run_case(harness, "settings.open", lambda: _scenario_open(harness))
    )
    if results[-1]["status"] != "passed":
        return results
    results.append(
        _run_case(harness, "settings.pages", lambda: _scenario_pages(harness))
    )
    results.append(
        _run_case(harness, "settings.search", lambda: _scenario_search(harness))
    )
    results.append(
        _run_case(
            harness,
            "settings.components",
            lambda: _scenario_components(harness),
        )
    )
    results.append(
        _run_case(
            harness,
            "settings.axes_components",
            lambda: _scenario_axes_components(harness),
        )
    )
    results.append(
        _run_case(
            harness,
            "settings.next_use",
            lambda: _scenario_next_use(harness, seed),
        )
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
    except Exception as exc:  # noqa: BLE001 — one failed scenario must not hide later ids
        try:
            dialog = harness.settings_dialog()
            if dialog is not None:
                harness.grab(dialog, f"{scenario_id.replace('.', '-')}-failure")
            elif harness.window is not None:
                harness.grab_main(f"{scenario_id.replace('.', '-')}-failure")
        except Exception:
            pass
        return {
            "id": scenario_id,
            "status": "failed",
            "error": f"{type(exc).__name__}: {exc}",
            "screenshotCount": len(harness.screenshots) - before,
        }


def _scenario_open(harness: SmokeHarness) -> None:
    opened: dict[str, str] = {}

    def while_open() -> None:
        dialog = harness.require_settings()
        opened["objectName"] = dialog.objectName()
        opened["title"] = dialog.windowTitle()
        harness.grab(dialog, "01-open-shell")
        harness.grab_main("01-open-main-with-settings")
        if dialog.objectName() != "setting_dialog":
            raise SmokeError(
                f"Expected objectName setting_dialog, got {dialog.objectName()!r}."
            )
        if "setting" not in dialog.windowTitle().casefold():
            raise SmokeError(
                f"Settings window title is {dialog.windowTitle()!r}."
            )
        apply_button = dialog.apply_button
        ok_button = dialog.ok_button
        cancel_button = dialog.cancel_button
        if apply_button is None or ok_button is None or cancel_button is None:
            raise SmokeError("Apply / OK / Cancel footer buttons are missing.")
        if apply_button.isEnabled():
            raise SmokeError("Apply should be disabled on a clean session.")
        if not ok_button.isEnabled():
            raise SmokeError("OK should be enabled on a writable temporary backend.")
        nav = dialog.nav_list
        titles = [nav.item(index).text() for index in range(nav.count())]
        if titles != list(EXPECTED_NAV_TITLES):
            raise SmokeError(f"Unexpected Settings page order: {titles}.")
        pane = dialog.findChild(QWidget, "settings_nav_pane")
        if pane is None or int(pane.width()) != NAV_PANE_WIDTH:
            width = None if pane is None else int(pane.width())
            raise SmokeError(
                f"Settings nav pane width is {width}, expected {NAV_PANE_WIDTH}."
            )
        dialog.reject()

    harness.open_settings_via_gear(while_open)
    if opened.get("objectName") != "setting_dialog":
        raise SmokeError("Gear click did not open setting_dialog.")


def _scenario_pages(harness: SmokeHarness) -> None:
    dialog = harness.present_settings()
    for page_id in SHELL_PAGE_ORDER:
        started = time.perf_counter()
        harness.select_page(page_id)
        if page_id == PAGE_AXES_COMPONENTS:
            harness.timings["first_axes_components_ms"] = (
                time.perf_counter() - started
            ) * 1000
        expected = SHELL_PAGE_METADATA[page_id].title
        actual = harness.page_title()
        if actual != expected:
            raise SmokeError(
                f"Visible page title is {actual!r}, expected {expected!r}."
            )
        _scroll_page_to_top(dialog, page_id)
        harness.grab(dialog, PAGE_SHOT_NAMES[page_id])
        inner = _page_inner(dialog, page_id)
        if inner is not None:
            harness.grab(inner, f"{PAGE_SHOT_NAMES[page_id]}-inner")
        if page_id == PAGE_COMPONENTS:
            _assert_hosted_intro_once(
                dialog,
                page_id,
                "These defaults apply to components created after Apply.",
            )
            _grab_component_tabs(harness, dialog)
        if page_id == PAGE_AXES_COMPONENTS:
            _assert_hosted_intro_once(
                dialog,
                page_id,
                "These defaults apply to ordinary Axes created after Apply.",
            )
        if page_id == PAGE_APPEARANCE:
            dark = dialog.findChild(QRadioButton, "appearance_theme_dark")
            started = time.perf_counter()
            harness.click(dark)
            harness.timings["appearance_dark_preview_ms"] = (
                time.perf_counter() - started
            ) * 1000
            harness.grab(dialog, "10-appearance-live-dark")
            harness.grab_main("10-appearance-live-dark-main")
        if page_id == PAGE_WORKSPACE:
            page = _page_inner(dialog, page_id)
            if not isinstance(page, WorkspaceSettingsPage):
                raise SmokeError("Workspace page widget is missing.")
            harness.click_and_dismiss_confirm(page.reset_button)
        if page_id == PAGE_MAINTENANCE:
            page = _page_inner(dialog, page_id)
            if not isinstance(page, MaintenanceSettingsPage):
                raise SmokeError("Maintenance page widget is missing.")
            harness.click_and_dismiss_confirm(page.reset_all_button)
    QTest.keyClick(dialog, Qt.Key_Escape)
    harness.pump(80)
    # Esc discards the Appearance live preview. Reopen the cached window.
    started = time.perf_counter()
    dialog = harness.present_settings(PAGE_APPEARANCE, wait_ms=0)
    harness.timings["cached_open_ms"] = (time.perf_counter() - started) * 1000
    harness.pump(80)
    dark = dialog.findChild(QRadioButton, "appearance_theme_dark")
    if dark is not None and dark.isChecked():
        raise SmokeError("Esc did not discard the Appearance Dark preview.")
    started = time.perf_counter()
    harness.close_settings(cancel=True, wait_ms=0)
    harness.timings["cached_close_ms"] = (time.perf_counter() - started) * 1000
    harness.pump(50)

    dialog = harness.present_settings(PAGE_APPEARANCE)
    light = dialog.findChild(QRadioButton, "appearance_theme_light")
    harness.click(light)
    system = dialog.findChild(QRadioButton, "appearance_theme_system")
    harness.click(system)
    font_spin = dialog.findChild(QWidget, "appearance_font_spin")
    if font_spin is not None and hasattr(font_spin, "setValue"):
        started = time.perf_counter()
        font_spin.setValue(10)
        app = harness.app or QApplication.instance()
        if app is not None:
            app.processEvents()
        harness.timings["font_9_to_10_preview_ms"] = (
            time.perf_counter() - started
        ) * 1000
        started = time.perf_counter()
        harness.close_settings(cancel=True, wait_ms=0)
        harness.timings["font_9_to_10_cancel_ms"] = (
            time.perf_counter() - started
        ) * 1000
        harness.pump(50)
    else:
        harness.close_settings(cancel=True)

    dialog = harness.present_settings(PAGE_APPEARANCE)
    harness.click(dialog.ok_button, wait_ms=80)
    dialog = harness.present_settings(PAGE_APPEARANCE)
    started = time.perf_counter()
    dialog.close()
    app = harness.app or QApplication.instance()
    if app is not None:
        app.processEvents()
    harness.timings["cached_close_x_ms"] = (time.perf_counter() - started) * 1000
    harness.pump(50)


def _scenario_search(harness: SmokeHarness) -> None:
    dialog = harness.present_settings()
    dialog.search_edit.setText("Line width")
    harness.pump(80)
    if harness.page_title() != "Components":
        raise SmokeError(
            f"Search 'Line width' opened {harness.page_title()!r}, not Components."
        )
    harness.grab(dialog, "11-search-line-width")
    dialog.search_edit.setText("spine")
    harness.pump(80)
    if harness.page_title() != "Axes Components":
        raise SmokeError(
            f"Search 'spine' opened {harness.page_title()!r}, not Axes Components."
        )
    harness.grab(dialog, "12-search-spine")
    dialog.search_edit.clear()
    harness.pump(40)
    harness.close_settings(cancel=True)


def _scenario_components(harness: SmokeHarness) -> None:
    dialog = harness.present_settings(PAGE_COMPONENTS)
    line_box = dialog.findChild(QGroupBox, "settings_components_line")
    scatter_box = dialog.findChild(QGroupBox, "settings_components_scatter")
    text_box = dialog.findChild(QGroupBox, "settings_components_text")
    _assert_row_count(line_box, LINE_KEYS, "Line")
    _assert_row_count(scatter_box, SCATTER_KEYS, "Scatter")
    _assert_row_count(text_box, TEXT_KEYS, "Text")
    color_row = _row(dialog, COMPONENTS_LINE_COLOR)
    color_button = getattr(color_row.value_editor, "color_button", None)
    if color_button is None or color_button.text() != "Choose color…":
        text = None if color_button is None else color_button.text()
        raise SmokeError(
            f"Components color button is {text!r}, expected 'Choose color…'."
        )
    if color_row.inherit_box.text() != "Use Axes palette":
        raise SmokeError(
            "Line color inherit label is "
            f"{color_row.inherit_box.text()!r}, expected 'Use Axes palette'."
        )
    width_row = _row(dialog, COMPONENTS_LINE_LINEWIDTH)
    if width_row.inherit_box.text() != "Use Figure style":
        raise SmokeError(
            "Line width inherit label is "
            f"{width_row.inherit_box.text()!r}, expected 'Use Figure style'."
        )
    if not width_row.inherit_box.isChecked():
        raise SmokeError("Line width should start inherited.")
    width_row.inherit_box.setChecked(False)
    harness.pump(30)
    width_row.value_editor.setValue(OVERRIDE_LINEWIDTH)
    harness.pump(40)
    if width_row.value().mode is not DefaultValueMode.OVERRIDE:
        raise SmokeError("Unchecking inherit did not stage an override.")
    harness.grab(dialog, "13-components-line-width-draft")
    inner = _page_inner(dialog, PAGE_COMPONENTS)
    if inner is not None:
        harness.grab(inner, "13-components-line-width-draft-inner")
    harness.close_settings(cancel=True)

    dialog = harness.present_settings(PAGE_COMPONENTS)
    width_row = _row(dialog, COMPONENTS_LINE_LINEWIDTH)
    if not width_row.inherit_box.isChecked():
        raise SmokeError(
            "Cancel did not restore Line width inherit on the cached window."
        )
    if width_row.value().mode is not DefaultValueMode.INHERIT:
        raise SmokeError("Reopened Components Line width is not inherit.")
    harness.grab(dialog, "14-components-inherit-restored")
    harness.close_settings(cancel=True)


def _scenario_axes_components(harness: SmokeHarness) -> None:
    dialog = harness.present_settings(PAGE_AXES_COMPONENTS)
    tabs = dialog.findChild(QTabWidget, "settings_axes_components_tabs")
    if tabs is None:
        raise SmokeError("settings_axes_components_tabs is missing.")
    titles = [tabs.tabText(index) for index in range(tabs.count())]
    if titles != ["General", "Spines", "X Axis", "Y Axis"]:
        raise SmokeError(f"Unexpected Axes Components tabs: {titles}.")
    tab_shots = (
        (0, "15-axes-tab-general"),
        (1, "16-axes-tab-spines"),
        (2, "17-axes-tab-x-axis"),
        (3, "18-axes-tab-y-axis"),
    )
    for index, name in tab_shots:
        tabs.setCurrentIndex(index)
        harness.pump(50)
        harness.grab(dialog, name)
        harness.grab(_tab_body(tabs, index), f"{name}-content")
    tabs.setCurrentIndex(2)
    harness.pump(30)
    copy_clicks = (
        ("settings_axes_copy_x_to_y", "19-axes-copy-x-to-y"),
        ("settings_axes_copy_x_major_to_minor", "20-axes-copy-major-to-minor"),
        ("settings_axes_copy_x_minor_to_major", "21-axes-copy-minor-to-major"),
    )
    for object_name, shot in copy_clicks:
        button = dialog.findChild(QPushButton, object_name)
        harness.click(button)
        harness.grab(dialog, shot)
    tabs.setCurrentIndex(3)
    harness.pump(30)
    button = dialog.findChild(QPushButton, "settings_axes_copy_y_to_x")
    harness.click(button)
    harness.grab(dialog, "22-axes-copy-y-to-x")

    favorites_before = list(harness.window.color_library.favorite_colors)
    harness.window.color_library.record_recent("#336699")
    recents_marked = list(harness.window.color_library.recent_colors)
    if "#336699" not in recents_marked:
        raise SmokeError("Could not seed a recent color to prove Restore keeps it.")
    harness.click(dialog.restore_defaults_button)
    face_row = _row(dialog, COMPONENTS_AXES_FACECOLOR)
    if not face_row.inherit_box.isChecked():
        raise SmokeError("Restore page defaults did not return Facecolor to inherit.")
    if harness.window.color_library.recent_colors != recents_marked:
        raise SmokeError("Restore page defaults cleared the color library recents.")
    if harness.window.color_library.favorite_colors != favorites_before:
        raise SmokeError("Restore page defaults changed favorite colors.")
    harness.grab(dialog, "23-axes-restore-page-defaults")
    harness.close_settings(cancel=True)


def _scenario_next_use(harness: SmokeHarness, seed: ProjectSeed) -> None:
    dialog = harness.present_settings(PAGE_COMPONENTS)
    width_row = _row(dialog, COMPONENTS_LINE_LINEWIDTH)
    width_row.inherit_box.setChecked(False)
    harness.pump(20)
    width_row.value_editor.setValue(OVERRIDE_LINEWIDTH)
    harness.pump(30)
    harness.select_page(PAGE_AXES_COMPONENTS)
    face_row = _row(dialog, COMPONENTS_AXES_FACECOLOR)
    face_row.inherit_box.setChecked(False)
    harness.pump(20)
    editor = face_row.value_editor
    set_color = getattr(editor, "set_color", None)
    if not callable(set_color) or not set_color(
        OVERRIDE_FACECOLOR, emit=True, record_recent=False
    ):
        raise SmokeError("Could not set Axes Facecolor override.")
    harness.pump(40)
    harness.grab(dialog, "24-overrides-before-apply")

    figure_window = harness.window.figure_window
    curve_dialog = PyCurveDialog("curve", figure_window, parent=harness.window)
    curve_dialog.setModal(False)
    curve_dialog.show()
    harness.pump(80)
    frozen_before = float(curve_dialog._resolved_line.linewidth)
    harness.grab(curve_dialog, "25-curve-dialog-open-across-apply")
    if not dialog.apply_button.isEnabled():
        raise SmokeError("Apply stayed disabled after staging overrides.")
    harness.click(dialog.apply_button, wait_ms=80)
    harness.grab_main("26-message-bar-after-apply")
    message = harness.window.bottom_bar.message_bar.message_label.text()
    if "applied" not in message.casefold():
        raise SmokeError(f"Apply Message Bar text is {message!r}.")
    level = str(harness.window.bottom_bar.message_bar.property("level") or "")
    if level and level != "success":
        raise SmokeError(f"Apply Message Bar level is {level!r}, expected success.")
    frozen_after = float(curve_dialog._resolved_line.linewidth)
    if frozen_after != frozen_before:
        raise SmokeError(
            "Creation dialog was rewritten after Settings Apply "
            f"({frozen_before} -> {frozen_after})."
        )
    harness.grab(curve_dialog, "27-curve-dialog-after-apply-unchanged")
    curve_dialog.reject()
    harness.pump(40)

    harness.grab(dialog, "28-settings-after-apply")
    harness.close_settings(cancel=False)

    _create_with_dialogs(harness, seed)
    _assert_next_use(harness, seed)


def _create_with_dialogs(harness: SmokeHarness, seed: ProjectSeed) -> None:
    figure_window = harness.window.figure_window
    curve = PyCurveDialog("curve", figure_window, parent=harness.window)
    curve.setModal(False)
    curve.show()
    harness.pump(80)
    harness.grab(curve, "29-curve-dialog-defaults-after-apply")
    if curve.ok_button.text() != "OK" or curve.cancel_button.text() != "Cancel":
        raise SmokeError(
            "Curve dialog buttons are "
            f"{curve.ok_button.text()!r}/{curve.cancel_button.text()!r}, "
            "expected OK/Cancel."
        )
    new_width = float(curve._resolved_line.linewidth)
    if abs(new_width - OVERRIDE_LINEWIDTH) > 1e-6:
        raise SmokeError(
            f"New Curve dialog linewidth is {new_width}, expected {OVERRIDE_LINEWIDTH}."
        )
    curve.reject()
    harness.pump(30)

    scatter = PyScatterDialog("scatter", figure_window, parent=harness.window)
    scatter.setModal(False)
    scatter.show()
    harness.pump(80)
    harness.grab(scatter, "30-scatter-dialog-defaults")
    scatter.reject()
    harness.pump(30)

    text = PyTextDialog(dialog_name="Text", figure_window=figure_window, parent=harness.window)
    text.setModal(False)
    text.show()
    harness.pump(80)
    harness.grab(text, "31-text-dialog-defaults")
    text.reject()
    harness.pump(30)

    layout = PyLayoutDialog(
        dialog_name="Single Axes",
        figure_window=figure_window,
        preset_key="single",
        parent=harness.window,
    )
    layout.setModal(False)
    layout.show()
    harness.pump(80)
    harness.grab(layout, "32-layout-dialog-defaults")
    frozen = getattr(layout, "_frozen_appearance", None)
    if frozen is not None:
        face = normalize_color(frozen.facecolor)
        if face != OVERRIDE_FACECOLOR:
            raise SmokeError(
                f"New Axes dialog frozen facecolor is {face}, "
                f"expected {OVERRIDE_FACECOLOR}."
            )
    layout.reject()
    harness.pump(30)

    canvas = seed.canvas
    seed.new_line = canvas.add_curve("x", 0, 1, None, None, "next-use")
    canvas.add_scatters(
        seed.x_ref,
        (seed.y_ref,),
        size=None,
        marker=None,
        linewidth=None,
        preprocess=None,
        color_selection=ColorSelection("#ABCDEF"),
    )
    canvas.add_text(0.2, 0.85, "next-use", "sans-serif", 12.0)
    old_axes = canvas.component_registry.query(kind=ComponentKind.AXES)
    if len(old_axes) != 1:
        raise SmokeError(
            f"Seed Figure has {len(old_axes)} Axes before the new Figure; expected 1."
        )
    figure_window.add_figure(
        width=6.4,
        height=4.8,
        dpi=100,
        style="default",
        canva_name="DesktopSmokeNext",
    )
    new_canvas = figure_window.current_canva
    if new_canvas is None or new_canvas is canvas:
        raise SmokeError("Could not create a second Figure for Axes NEXT_USE.")
    new_ids = new_canvas.create_axes_layout(AxesLayoutSpec.grid(1, 1))
    if not new_ids:
        raise SmokeError("New Axes layout did not return an id.")
    harness.pump(80)
    try:
        canvas.draw()
        new_canvas.draw()
    except Exception:
        pass
    harness.pump(40)
    harness.grab(new_canvas, "33-canvas-next-use")
    harness.grab_main("34-main-after-next-use")
    seed.new_axes_id = str(new_ids[0])
    seed.new_canvas = new_canvas


def _assert_next_use(harness: SmokeHarness, seed: ProjectSeed) -> None:
    canvas = seed.canvas
    old_axes = canvas.component_registry.query(kind=ComponentKind.AXES)
    if len(old_axes) != 1:
        raise SmokeError(
            f"Existing Figure has {len(old_axes)} Axes after next-use; expected 1."
        )
    old_target = canvas.component_registry.resolve_target(seed.old_axes_id)
    if abs(float(seed.old_line.get_linewidth()) - seed.old_linewidth) > 1e-6:
        raise SmokeError("Existing Curve linewidth changed after Settings Apply.")
    if normalize_color(old_target.get_facecolor()) != seed.old_facecolor:
        raise SmokeError("Existing Axes facecolor changed after Settings Apply.")
    if not seed.new_axes_id:
        raise SmokeError("New Axes id was not recorded.")
    new_canvas = seed.new_canvas
    if new_canvas is None:
        raise SmokeError("New Figure canvas was not recorded.")
    new_target = new_canvas.component_registry.resolve_target(seed.new_axes_id)
    if normalize_color(new_target.get_facecolor()) != OVERRIDE_FACECOLOR:
        raise SmokeError(
            "New Axes did not pick up the Facecolor override "
            f"({normalize_color(new_target.get_facecolor())})."
        )
    if seed.new_line is None:
        raise SmokeError("Could not find the NEXT_USE Curve artist.")
    new_width = float(seed.new_line.get_linewidth())
    if abs(new_width - OVERRIDE_LINEWIDTH) > 1e-6:
        raise SmokeError(
            f"New Curve linewidth is {new_width}, expected {OVERRIDE_LINEWIDTH}."
        )


def _row(dialog: SettingsCenterWindow, key: str) -> InheritableSettingRow:
    widget = dialog.findChild(InheritableSettingRow, f"settings_inheritable_{key}")
    if widget is None:
        raise SmokeError(f"Missing inheritable row {key}.")
    return widget


def _assert_row_count(box: QGroupBox | None, expected: int, title: str) -> None:
    if box is None:
        raise SmokeError(f"Components {title} group is missing.")
    rows = box.findChildren(InheritableSettingRow)
    if len(rows) != expected:
        raise SmokeError(
            f"Components {title} has {len(rows)} inheritable rows, expected {expected}."
        )


def _page_inner(dialog: SettingsCenterWindow, page_id: str) -> QWidget | None:
    scroll = dialog.findChild(QScrollArea, f"settings_page_scroll_{page_id}")
    if scroll is None:
        return None
    return scroll.widget()


def _tab_body(tabs: QTabWidget, index: int) -> QWidget:
    widget = tabs.widget(index)
    if isinstance(widget, QScrollArea):
        inner = widget.widget()
        if inner is not None:
            return inner
    if widget is None:
        raise SmokeError(f"Settings tab {index} is missing.")
    return widget


def _assert_hosted_intro_once(
    dialog: SettingsCenterWindow,
    page_id: str,
    snippet: str,
) -> None:
    description = dialog.findChild(QLabel, "settings_page_description")
    text = None if description is None else description.text()
    if description is None or snippet not in str(text):
        raise SmokeError(
            f"Settings description for {page_id} is {text!r}, expected {snippet!r}."
        )
    inner = _page_inner(dialog, page_id)
    if inner is None:
        raise SmokeError(f"Missing inner widget for {page_id}.")
    intros = inner.findChildren(QLabel, "settings_page_intro")
    if intros:
        raise SmokeError(
            f"Hosted {page_id} page repeated the shell NEXT_USE description."
        )


def _grab_component_tabs(harness: SmokeHarness, dialog: SettingsCenterWindow) -> None:
    tabs = dialog.findChild(QTabWidget, "settings_components_tabs")
    if tabs is None:
        raise SmokeError("settings_components_tabs is missing.")
    titles = [tabs.tabText(index) for index in range(tabs.count())]
    if titles != ["Line", "Scatter", "Text"]:
        raise SmokeError(f"Unexpected Components tabs: {titles}.")
    shots = (
        (0, "05-page-components-line"),
        (1, "05-page-components-scatter"),
        (2, "05-page-components-text"),
    )
    for index, name in shots:
        tabs.setCurrentIndex(index)
        harness.pump(40)
        harness.grab(dialog, name)
        harness.grab(_tab_body(tabs, index), f"{name}-inner")


def _scroll_page_to_top(dialog: SettingsCenterWindow, page_id: str) -> None:
    scroll = dialog.findChild(QScrollArea, f"settings_page_scroll_{page_id}")
    if scroll is None:
        return
    bar = scroll.verticalScrollBar()
    if bar is not None:
        bar.setValue(0)
