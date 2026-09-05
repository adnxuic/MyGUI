"""Semantic UI component facade, token aliases, and composed component QSS."""

from __future__ import annotations

import ast
import os
from pathlib import Path
import time
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QGroupBox,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QTableView,
    QTreeView,
    QVBoxLayout,
    QWidget,
)

from mygui.application_theme import (
    COMPONENT_QSS_RESOURCE,
    DIALOG_QSS_RESOURCE,
    DARK_QSS_TOKENS,
    LIGHT_QSS_TOKENS,
    AppearancePreferences,
    Density,
    EffectiveScheme,
    ThemeMode,
    compose_component_stylesheet,
    compose_theme_snapshot,
    contrast_ratio,
    render_application_stylesheet,
    render_resource_stylesheet,
)
from mygui.application_theme.metrics import DENSITY_BANDS, build_density_metrics
from mygui.application_theme.tokens import _ui_semantic_aliases
from mygui.widgets.ui_components import (
    PROPERTY_BUSY,
    PROPERTY_INVALID,
    PROPERTY_ROLE,
    PROPERTY_SIZE,
    PROPERTY_TEXT_ROLE,
    PROPERTY_TONE,
    PROPERTY_VARIANT,
    UiRole,
    UiSize,
    UiTextRole,
    UiTone,
    UiVariant,
    annotate_form_fields,
    annotate_section,
    apply_elided_text,
    apply_text_style,
    apply_ui_style,
    ask_confirmation,
    capture_layout_signature,
    combo_is_protected,
    create_button,
    create_check_box,
    create_combo_box,
    create_empty_state,
    create_icon_button,
    create_line_edit,
    create_radio_button,
    inspect_chrome,
    refresh_ui_style,
    set_busy_state,
    set_validation_state,
    signature_paths,
    style_button,
    style_dialog_button_box,
    style_message_box,
    style_progress_bar,
)
from mygui.widgets.ui_components.matrix import build_component_matrix

ROOT = Path(__file__).resolve().parents[1]
PRODUCTION_ROOT = ROOT / "mygui"


def _qapp() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


class UiComponentFacadeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = _qapp()

    def test_apply_ui_style_sets_closed_properties(self) -> None:
        button = QPushButton("OK")
        apply_ui_style(
            button,
            role=UiRole.BUTTON,
            variant=UiVariant.PRIMARY,
            size=UiSize.LARGE,
            invalid=True,
        )
        self.assertEqual(button.property(PROPERTY_ROLE), "button")
        self.assertEqual(button.property(PROPERTY_VARIANT), "primary")
        self.assertEqual(button.property(PROPERTY_SIZE), "large")
        self.assertEqual(button.property(PROPERTY_INVALID), "true")
        self.assertEqual(button.accessibleName() or button.text(), "OK")

    def test_unknown_role_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            apply_ui_style(QPushButton(), role="unknown-role")

    def test_item_views_repolish_without_index_update(self) -> None:
        tree = apply_ui_style(QTreeView(), role=UiRole.TREE)
        table = apply_ui_style(QTableView(), role=UiRole.TABLE)
        self.assertEqual(tree.property(PROPERTY_ROLE), "tree")
        self.assertEqual(table.property(PROPERTY_ROLE), "table")

    def test_dialog_qss_does_not_select_last_combo_item(self) -> None:
        from mygui.application_theme import bind_widget_qss

        dialog = QDialog()
        bind_widget_qss(dialog, DIALOG_QSS_RESOURCE)
        combo = QComboBox(dialog)
        combo.addItem("first", "a")
        combo.addItem("second", "b")
        combo.addItem("last", "c")
        combo.setCurrentIndex(0)
        apply_ui_style(combo, role=UiRole.SELECT)
        self.assertEqual(combo.currentIndex(), 0)
        self.assertEqual(combo.currentData(), "a")

    def test_editable_combos_are_not_auto_annotated_as_select(self) -> None:
        from mygui.widgets.ui_components import annotate_inspector_control

        combo = QComboBox()
        combo.setEditable(True)
        annotate_inspector_control(combo)
        self.assertIsNone(combo.property(PROPERTY_ROLE))

    def test_collapsed_inspector_group_keeps_children_enabled(self) -> None:
        from mygui.widgets.fig_control_window.component_editors.inspector import (
            InspectorSectionGroup,
        )

        group = InspectorSectionGroup("Rendering")
        layout = QVBoxLayout(group)
        box = QCheckBox("TeX")
        layout.addWidget(box)
        group.setCheckable(True)
        group.setChecked(False)
        box.setEnabled(True)
        self.app.processEvents()
        self.assertTrue(box.isEnabled())
        self.assertFalse(group.isChecked())

    def test_factories_keep_native_types_and_state_matrix(self) -> None:
        cases = []
        for variant in UiVariant:
            for size in (UiSize.SMALL, UiSize.DEFAULT, UiSize.LARGE):
                button = create_button("Label", variant=variant, size=size)
                cases.append((button, variant, size))
                self.assertIsInstance(button, QPushButton)
                self.assertEqual(button.property(PROPERTY_VARIANT), variant.value)
                self.assertEqual(button.property(PROPERTY_SIZE), size.value)
                button.setEnabled(False)
                self.assertFalse(button.isEnabled())
                button.setEnabled(True)
                button.setDown(True)
                self.assertTrue(button.isDown())
                button.setDown(False)
                button.setCheckable(True)
                button.setChecked(True)
                self.assertTrue(button.isChecked())
        self.assertEqual(len(cases), len(UiVariant) * 3)
        icon = create_icon_button(accessible_name="Inspect")
        self.assertEqual(icon.property(PROPERTY_ROLE), "icon-button")
        self.assertEqual(icon.accessibleName(), "Inspect")
        editor = create_line_edit("value", invalid=True)
        self.assertIsInstance(editor, QLineEdit)
        self.assertEqual(editor.property(PROPERTY_INVALID), "true")
        editor.setReadOnly(True)
        self.assertTrue(editor.isReadOnly())
        combo = create_combo_box()
        self.assertIsInstance(combo, QComboBox)
        check = create_check_box("On")
        self.assertIsInstance(check, QCheckBox)
        radio = create_radio_button("Choice")
        radio.setAutoExclusive(False)
        self.assertTrue(radio.isEnabled())

    def test_dialog_button_box_maps_primary_and_outline(self) -> None:
        box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
            | QDialogButtonBox.StandardButton.Apply
        )
        style_dialog_button_box(box)
        self.assertEqual(
            box.button(QDialogButtonBox.StandardButton.Ok).property(PROPERTY_VARIANT),
            "primary",
        )
        self.assertEqual(
            box.button(QDialogButtonBox.StandardButton.Apply).property(
                PROPERTY_VARIANT
            ),
            "primary",
        )
        self.assertEqual(
            box.button(QDialogButtonBox.StandardButton.Cancel).property(
                PROPERTY_VARIANT
            ),
            "outline",
        )

    def test_empty_state_primary_is_annotated(self) -> None:
        panel = create_empty_state("None", "Create a project", "Create")
        self.assertEqual(panel.property(PROPERTY_ROLE), "empty-state")
        self.assertIsNotNone(panel.primary_button)
        self.assertEqual(
            panel.primary_button.property(PROPERTY_VARIANT),
            "primary",
        )

    def test_refresh_ui_style_returns_the_widget(self) -> None:
        label = QLabel("x")
        self.assertIs(refresh_ui_style(label), label)

    def test_elided_text_keeps_tooltip(self) -> None:
        label = QLabel()
        label.resize(40, 20)
        apply_elided_text(label, "A very long command label")
        self.assertEqual(label.toolTip(), "A very long command label")
        self.assertLessEqual(len(label.text()), len("A very long command label"))

    def test_text_roles_and_sections_do_not_change_expand_state(self) -> None:
        label = QLabel("Title")
        apply_text_style(label, UiTextRole.PAGE_TITLE)
        self.assertEqual(label.property(PROPERTY_TEXT_ROLE), "page-title")
        group = QGroupBox("Advanced")
        layout = QVBoxLayout(group)
        box = QCheckBox("TeX")
        layout.addWidget(box)
        group.setCheckable(True)
        group.setChecked(False)
        box.setEnabled(True)
        with (
            patch.object(
                group,
                "setCheckable",
                wraps=group.setCheckable,
            ) as set_checkable,
            patch.object(
                group,
                "setChecked",
                wraps=group.setChecked,
            ) as set_checked,
        ):
            annotate_section(group)
        self.assertEqual(group.property(PROPERTY_ROLE), "section")
        self.assertFalse(group.isChecked())
        self.assertTrue(box.isEnabled())
        set_checkable.assert_not_called()
        set_checked.assert_not_called()

    def test_style_button_requires_an_explicit_variant(self) -> None:
        button = QPushButton("OK")
        with self.assertRaises(TypeError):
            style_button(button)
        style_button(button, variant=UiVariant.PRIMARY)
        self.assertEqual(button.property(PROPERTY_VARIANT), "primary")

    def test_inspect_chrome_reports_missing_role_and_icon_name(self) -> None:
        host = QWidget()
        QPushButton("Go", host)
        problems = inspect_chrome(host)
        self.assertTrue(any("missing uiRole" in item for item in problems))
        styled = create_icon_button(parent=host, accessible_name="Inspect")
        self.assertEqual(inspect_chrome(styled), ())

    def test_protected_combos_are_not_annotated_as_select(self) -> None:
        host = QWidget()
        editable = QComboBox(host)
        editable.setEditable(True)
        editable.addItem("draft")
        checked = QComboBox(host)
        checked.addItem("one")
        checked.addItem("two")
        model = checked.model()
        model.setData(
            model.index(0, 0),
            Qt.CheckState.Checked,
            Qt.ItemDataRole.CheckStateRole,
        )
        annotate_form_fields(host)
        self.assertFalse(editable.property(PROPERTY_ROLE))
        self.assertFalse(checked.property(PROPERTY_ROLE))
        self.assertTrue(combo_is_protected(editable))
        self.assertTrue(combo_is_protected(checked))
        self.assertEqual(inspect_chrome(host), ())

    def test_layout_signature_survives_layout_attribute_shadow(self) -> None:
        host = QWidget()
        box = QVBoxLayout(host)
        host.layout = box
        payload = capture_layout_signature(host)
        self.assertEqual(payload["layout"], "QVBoxLayout")
        self.assertEqual(signature_paths(payload), signature_paths(payload))

    def test_theme_stylesheet_reload_keeps_combo_index_and_checks(self) -> None:
        from mygui.application_theme import bind_widget_qss

        dialog = QDialog()
        combo = QComboBox(dialog)
        combo.addItem("first")
        combo.addItem("second")
        combo.addItem("third")
        combo.setCurrentIndex(1)
        apply_ui_style(combo, role=UiRole.SELECT)
        bind_widget_qss(dialog, DIALOG_QSS_RESOURCE)
        self.assertEqual(combo.currentIndex(), 1)
        bind_widget_qss(dialog, DIALOG_QSS_RESOURCE)
        self.assertEqual(combo.currentIndex(), 1)
        editor = QLineEdit("draft", dialog)
        editor.setSelection(1, 3)
        apply_ui_style(editor, role=UiRole.INPUT)
        bind_widget_qss(dialog, DIALOG_QSS_RESOURCE)
        self.assertEqual(editor.text(), "draft")
        self.assertEqual(editor.selectedText(), "raf")


class UiComponentMatrixTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = _qapp()

    def test_matrix_is_hidden_and_covers_roles(self) -> None:
        host = build_component_matrix()
        self.assertEqual(host.objectName(), "ui_component_matrix")
        self.assertTrue(host.testAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen))
        roles = {
            child.property(PROPERTY_ROLE)
            for child in host.findChildren(QWidget)
            if child.property(PROPERTY_ROLE)
        }
        expected = {
            "button",
            "icon-button",
            "input",
            "textarea",
            "select",
            "number",
            "checkbox",
            "radio",
            "tabs",
            "card",
            "alert",
            "badge",
            "empty-state",
            "section",
            "status",
            "progress",
        }
        self.assertTrue(expected.issubset(roles))
        text_roles = {
            child.property("uiTextRole")
            for child in host.findChildren(QLabel)
            if child.property("uiTextRole")
        }
        self.assertEqual(text_roles, {item.value for item in UiTextRole})

    def test_production_windows_do_not_mount_the_matrix(self) -> None:
        forbidden = "build_component_matrix"
        for path in PRODUCTION_ROOT.rglob("*.py"):
            if path.parent.name == "ui_components" and path.name == "matrix.py":
                continue
            source = path.read_text(encoding="utf-8")
            self.assertNotIn(
                forbidden,
                source,
                msg=f"{path.relative_to(ROOT)} mounts the test matrix",
            )


class UiTokenAndQssTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = _qapp()

    def test_semantic_aliases_map_to_existing_colors(self) -> None:
        for tokens in (dict(LIGHT_QSS_TOKENS), dict(DARK_QSS_TOKENS)):
            aliases = _ui_semantic_aliases(tokens)
            self.assertEqual(aliases["UI_PRIMARY"], tokens["COLOR_ACCENT"])
            self.assertEqual(aliases["UI_RING"], tokens["COLOR_FOCUS"])
            self.assertEqual(aliases["UI_BORDER"], tokens["COLOR_BORDER"])
            self.assertIn("UI_PRIMARY", tokens)
            self.assertGreaterEqual(
                contrast_ratio(
                    tokens["UI_PRIMARY_FOREGROUND"],
                    tokens["UI_PRIMARY"],
                ),
                4.5,
            )
            self.assertGreaterEqual(
                contrast_ratio(
                    tokens["UI_DESTRUCTIVE_FOREGROUND"],
                    tokens["UI_DESTRUCTIVE"],
                ),
                4.5,
            )
            self.assertGreaterEqual(
                contrast_ratio(
                    tokens["UI_RING"],
                    tokens["COLOR_COMMAND_BACKGROUND"],
                ),
                3.0,
            )

    def test_density_and_font_floors_feed_size_tokens(self) -> None:
        for density in Density:
            band = DENSITY_BANDS[density]
            for font_pt in (8, 9, 16):
                metrics = build_density_metrics(density, font_pt + 4)
                self.assertGreaterEqual(metrics.button, band.button)
                self.assertGreaterEqual(metrics.control, band.control)
                snapshot = compose_theme_snapshot(
                    EffectiveScheme.LIGHT,
                    AppearancePreferences(
                        mode=ThemeMode.LIGHT,
                        font_pt=font_pt,
                        density=density,
                    ),
                    font_height=font_pt + 4,
                )
                self.assertEqual(int(snapshot.tokens["SIZE_BUTTON"]), metrics.button)
                self.assertEqual(
                    snapshot.tokens["FONT_PT_PAGE_TITLE"],
                    str(font_pt + 2),
                )
                self.assertEqual(
                    snapshot.tokens["FONT_PT_CAPTION"],
                    str(max(8, font_pt - 1)),
                )
                self.assertEqual(
                    int(snapshot.tokens["SIZE_BUTTON_SMALL"]),
                    max(1, metrics.button - 8),
                )
                self.assertEqual(
                    int(snapshot.tokens["SIZE_SECTION_TITLE_TOP"]),
                    metrics.section_title_top,
                )
                self.assertEqual(
                    int(snapshot.tokens["SIZE_SECTION_MARGIN_TOP"]),
                    metrics.section_margin_top,
                )
                self.assertGreaterEqual(
                    metrics.section_margin_top,
                    metrics.section_title_top + metrics.indicator + metrics.spacing_xs,
                )

    def test_component_qss_is_composed_into_application_and_regional(self) -> None:
        snapshot = compose_theme_snapshot(
            EffectiveScheme.LIGHT,
            AppearancePreferences(),
            font_height=16,
        )
        application = render_application_stylesheet(snapshot)
        regional = render_resource_stylesheet(DIALOG_QSS_RESOURCE, snapshot)
        self.assertIn("QPushButton[uiVariant=\"primary\"]", regional)
        self.assertIn('QPushButton[uiRole="button"]', regional)
        self.assertIn("QMessageBox QPushButton", application)
        self.assertIn("QComboBox QAbstractItemView", application)
        self.assertNotIn("Shared workbench component rules", application)
        self.assertNotRegex(application, r"(?m)^QPushButton\n\{")
        self.assertIn("uiRole=\"section\"", regional)
        self.assertIn("QPushButton[uiVariant=\"primary\"]", regional)
        self.assertIn("QDialog", regional)
        composed = compose_component_stylesheet(
            DIALOG_QSS_RESOURCE,
            LIGHT_QSS_TOKENS,
        )
        self.assertIn("uiVariant", composed)
        self.assertIn("QDialog", composed)
        component_only = compose_component_stylesheet(
            COMPONENT_QSS_RESOURCE,
            LIGHT_QSS_TOKENS,
        )
        doubled = component_only + "\n" + component_only
        self.assertNotEqual(component_only, doubled)
        self.assertEqual(
            component_only.count("Shared workbench component rules"),
            1,
        )
        self.assertIn("subcontrol-position: top left", component_only)
        self.assertIn("SIZE_SECTION_MARGIN_TOP", LIGHT_QSS_TOKENS)
        self.assertIn("QGroupBox[uiRole=\"section\"]::indicator", component_only)

    def test_dark_composed_qss_uses_dark_tokens(self) -> None:
        snapshot = compose_theme_snapshot(
            EffectiveScheme.DARK,
            AppearancePreferences(mode=ThemeMode.DARK),
            font_height=16,
        )
        rendered = render_application_stylesheet(snapshot)
        self.assertIn("mygui-theme-app", rendered)
        self.assertIn(str(snapshot.tokens["SIZE_INDICATOR"]), rendered)
        self.assertNotIn("{{", rendered)


class UiComponentImportBoundaryTests(unittest.TestCase):
    def test_regional_qss_does_not_copy_generic_control_rules(self) -> None:
        generic = (
            "QPushButton\n{",
            "QLineEdit, QPlainTextEdit",
        )
        skip = {
            "mygui/widgets/ui_components/style.qss",
            "mygui/widgets/mainwindow_init/app_style.qss",
        }
        leftovers = []
        for path in (ROOT / "mygui").rglob("*.qss"):
            relative = path.relative_to(ROOT).as_posix()
            if relative in skip:
                continue
            text = path.read_text(encoding="utf-8")
            if any(token in text for token in generic):
                leftovers.append(relative)
        self.assertEqual(leftovers, [])


    def test_facade_does_not_import_matplotlib_or_settings_storage(self) -> None:
        package = PRODUCTION_ROOT / "widgets" / "ui_components"
        forbidden = ("matplotlib", "mygui.figuremodify", "QSettings")
        for path in package.glob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    names = [alias.name for alias in node.names]
                elif isinstance(node, ast.ImportFrom):
                    names = [node.module or ""]
                else:
                    continue
                for name in names:
                    for item in forbidden:
                        self.assertFalse(
                            name.startswith(item),
                            msg=f"{path.name} imports {name}",
                        )


class UiFeedbackTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = _qapp()

    def test_message_bar_tones_prefix_elision_and_accessibility(self) -> None:
        from mygui.widgets.bottom_bar.py_message_bar import PyMessageBar

        bar = PyMessageBar()
        bar.resize(240, 28)
        self.app.processEvents()
        samples = (
            ("info", "Ready.", ""),
            ("success", "Saved the project.", "Success — "),
            ("warning", "Empty data source.", "Warning — "),
            ("error", "Value was rejected.", "Error — "),
        )
        for level, body, prefix in samples:
            bar.show_message(body, level)
            self.app.processEvents()
            self.assertEqual(bar.property("level"), level)
            self.assertEqual(bar.property(PROPERTY_TONE), level)
            full = f"{prefix}{body}"
            self.assertEqual(bar.message_label.toolTip(), full)
            self.assertIn(body, bar.message_label.accessibleDescription())
            self.assertIn(level.title(), bar.message_label.accessibleName())
            self.assertLessEqual(len(bar.message_label.text()), len(full))
        long_body = "Rejected value " + ("x" * 400)
        bar.resize(180, 28)
        bar.show_message(long_body, "error")
        self.app.processEvents()
        self.assertTrue(bar.message_label.text().endswith("…") or bar.message_label.text() != long_body)
        self.assertIn(long_body, bar.message_label.toolTip())
        bar.clear_message()
        self.assertEqual(bar.property("level"), "info")
        bar.close()

    def test_confirmation_button_matrix(self) -> None:
        captured: dict[str, object] = {}

        def _inspect(box_self):
            captured["box"] = box_self
            captured["default"] = box_self.defaultButton()
            captured["escape"] = box_self.escapeButton()
            captured["ok"] = box_self.button(QMessageBox.StandardButton.Ok)
            captured["cancel"] = box_self.button(QMessageBox.StandardButton.Cancel)
            return 0

        from unittest.mock import patch

        host = QWidget()
        with patch.object(QMessageBox, "exec", _inspect):
            self.assertFalse(ask_confirmation(host, "Continue?", "Proceed?"))
        self.assertIs(captured["default"], captured["ok"])
        self.assertIs(captured["escape"], captured["cancel"])
        self.assertEqual(captured["ok"].property(PROPERTY_VARIANT), "primary")
        self.assertEqual(captured["cancel"].property(PROPERTY_VARIANT), "outline")

        with patch.object(QMessageBox, "exec", _inspect):
            self.assertFalse(
                ask_confirmation(
                    host,
                    "Delete?",
                    "Delete the selected sheet?",
                    destructive=True,
                )
            )
        self.assertIs(captured["default"], captured["cancel"])
        self.assertIs(captured["escape"], captured["cancel"])
        self.assertEqual(captured["ok"].property(PROPERTY_VARIANT), "destructive")
        self.assertEqual(captured["cancel"].property(PROPERTY_VARIANT), "outline")
        host.close()

    def test_confirmation_escape_and_close_cancel(self) -> None:
        from PySide6.QtCore import QTimer
        from PySide6.QtTest import QTest

        host = QWidget()
        host.show()
        self.app.processEvents()

        def _escape():
            for widget in QApplication.topLevelWidgets():
                if isinstance(widget, QMessageBox) and widget.isVisible():
                    QTest.keyClick(widget, Qt.Key_Escape)
                    break

        QTimer.singleShot(0, _escape)
        self.assertFalse(ask_confirmation(host, "Title", "Body"))

        def _close():
            for widget in QApplication.topLevelWidgets():
                if isinstance(widget, QMessageBox) and widget.isVisible():
                    widget.close()
                    break

        QTimer.singleShot(0, _close)
        self.assertFalse(
            ask_confirmation(host, "Delete", "Reset now?", destructive=True)
        )
        host.close()

    def test_validation_state_targets_one_control_and_clears(self) -> None:
        other = create_line_edit("ok")
        target = create_line_edit("bad")
        original_tip = "Original help"
        target.setToolTip(original_tip)
        target.setAccessibleDescription("Original help")
        set_validation_state(target, invalid=True, message="Out of range.")
        self.assertEqual(target.property(PROPERTY_INVALID), "true")
        self.assertEqual(target.toolTip(), "Out of range.")
        self.assertEqual(target.accessibleDescription(), "Out of range.")
        self.assertNotEqual(other.property(PROPERTY_INVALID), "true")
        target.setText("restored")
        set_validation_state(target, invalid=False)
        self.assertEqual(target.property(PROPERTY_INVALID), "false")
        self.assertEqual(target.toolTip(), original_tip)
        other.close()
        target.close()

    def test_busy_state_is_idempotent_and_owner_destroy_safe(self) -> None:
        button = QPushButton("Fit")
        set_busy_state(button, True, busy_text="Fitting…")
        self.assertEqual(button.text(), "Fitting…")
        self.assertFalse(button.isEnabled())
        self.assertEqual(button.property(PROPERTY_BUSY), "true")
        set_busy_state(button, True, busy_text="Fitting…")
        self.assertEqual(button.text(), "Fitting…")
        set_busy_state(button, False)
        self.assertEqual(button.text(), "Fit")
        self.assertTrue(button.isEnabled())
        set_busy_state(button, False)
        self.assertEqual(button.text(), "Fit")
        set_busy_state(button, True, busy_text="Connecting…")
        button.deleteLater()
        self.app.processEvents()
        set_busy_state(button, False)

    def test_progress_and_message_box_styling(self) -> None:
        bar = QProgressBar()
        style_progress_bar(bar, tone=UiTone.SUCCESS)
        self.assertEqual(bar.property(PROPERTY_ROLE), "progress")
        self.assertEqual(bar.property(PROPERTY_TONE), "success")
        box = QMessageBox()
        box.setStandardButtons(
            QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel
        )
        style_message_box(
            box,
            tone=UiTone.ERROR,
            primary=box.button(QMessageBox.StandardButton.Ok),
        )
        self.assertEqual(
            box.button(QMessageBox.StandardButton.Ok).property(PROPERTY_VARIANT),
            "primary",
        )
        self.assertEqual(
            box.button(QMessageBox.StandardButton.Cancel).property(PROPERTY_VARIANT),
            "outline",
        )
        bar.close()
        box.close()

    def test_production_code_does_not_call_qmessagebox_warning_or_question(self) -> None:
        allowed = {
            (PRODUCTION_ROOT / "widgets" / "ui_components" / "feedback.py").resolve()
        }
        leftovers = []
        for path in PRODUCTION_ROOT.rglob("*.py"):
            if path.resolve() in allowed:
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call) or not isinstance(
                    node.func, ast.Attribute
                ):
                    continue
                if node.func.attr not in {"warning", "question"}:
                    continue
                owner = node.func.value
                name = ""
                if isinstance(owner, ast.Name):
                    name = owner.id
                elif isinstance(owner, ast.Attribute):
                    name = owner.attr
                if name == "QMessageBox":
                    leftovers.append(f"{path.relative_to(ROOT)}:{node.lineno}")
        main_path = ROOT / "main.py"
        tree = ast.parse(main_path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
                continue
            if node.func.attr not in {"warning", "question"}:
                continue
            owner = node.func.value
            name = owner.id if isinstance(owner, ast.Name) else getattr(owner, "attr", "")
            if name == "QMessageBox":
                leftovers.append(f"main.py:{node.lineno}")
        self.assertEqual(leftovers, [])

    def test_repeat_style_calls_do_not_repolish(self) -> None:
        button = QPushButton("OK")
        apply_ui_style(button, role=UiRole.BUTTON, variant=UiVariant.PRIMARY)
        with patch(
            "mygui.widgets.ui_components.apply.refresh_ui_style",
            wraps=refresh_ui_style,
        ) as polished:
            apply_ui_style(button, role=UiRole.BUTTON, variant=UiVariant.PRIMARY)
            apply_text_style(button, UiTextRole.BODY)
            apply_text_style(button, UiTextRole.BODY)
        self.assertEqual(polished.call_count, 1)
        button.close()

    def test_state_transition_polishes_once(self) -> None:
        button = QPushButton("OK")
        apply_ui_style(button, role=UiRole.BUTTON, variant=UiVariant.PRIMARY)
        with patch(
            "mygui.widgets.ui_components.apply.refresh_ui_style",
            wraps=refresh_ui_style,
        ) as polished:
            apply_ui_style(
                button,
                role=UiRole.BUTTON,
                variant=UiVariant.DESTRUCTIVE,
            )
        self.assertEqual(polished.call_count, 1)
        button.close()

    def test_validation_message_only_skips_polish(self) -> None:
        target = create_line_edit("bad")
        set_validation_state(target, invalid=True, message="First.")
        with patch(
            "mygui.widgets.ui_components.feedback.refresh_ui_style",
            wraps=refresh_ui_style,
        ) as polished:
            set_validation_state(target, invalid=True, message="Second.")
        self.assertEqual(polished.call_count, 0)
        self.assertEqual(target.toolTip(), "Second.")
        with patch(
            "mygui.widgets.ui_components.feedback.refresh_ui_style",
            wraps=refresh_ui_style,
        ) as polished:
            set_validation_state(target, invalid=False)
        self.assertEqual(polished.call_count, 1)
        target.close()

    def test_busy_repeat_does_not_rewrite_or_polish(self) -> None:
        button = QPushButton("Fit")
        set_busy_state(button, True, busy_text="Fitting…")
        with patch.object(button, "setText") as set_text, patch.object(
            button, "setEnabled"
        ) as set_enabled, patch(
            "mygui.widgets.ui_components.feedback.refresh_ui_style",
            wraps=refresh_ui_style,
        ) as polished:
            set_busy_state(button, True, busy_text="Fitting…")
        set_text.assert_not_called()
        set_enabled.assert_not_called()
        self.assertEqual(polished.call_count, 0)
        button.close()

    def test_message_bar_same_tone_is_a_text_fast_path(self) -> None:
        from mygui.widgets.bottom_bar.py_message_bar import PyMessageBar

        bar = PyMessageBar()
        bar.resize(400, 28)
        self.app.processEvents()
        bar.show_message("warmup", "info")
        with patch(
            "mygui.widgets.ui_components.apply.refresh_ui_style",
            wraps=refresh_ui_style,
        ) as polished:
            started = time.perf_counter()
            for index in range(100):
                bar.show_message(f"status {index}", "info")
            elapsed_ms = (time.perf_counter() - started) * 1000
        self.assertEqual(polished.call_count, 0)
        self.assertLessEqual(elapsed_ms, 30)
        with patch(
            "mygui.widgets.ui_components.apply.refresh_ui_style",
            wraps=refresh_ui_style,
        ) as polished:
            bar.show_message("failed", "error")
        self.assertLessEqual(polished.call_count, 2)
        bar.close()

    def test_elided_text_skips_when_width_is_unchanged(self) -> None:
        label = QLabel()
        label.resize(80, 20)
        apply_elided_text(label, "A very long command label")
        with patch.object(label, "setText") as set_text, patch.object(
            label, "setToolTip"
        ) as set_tip:
            apply_elided_text(label, "A very long command label")
        set_text.assert_not_called()
        set_tip.assert_not_called()
        label.close()


if __name__ == "__main__":
    unittest.main()
