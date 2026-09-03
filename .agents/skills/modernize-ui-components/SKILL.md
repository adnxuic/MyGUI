---
name: modernize-ui-components
description: Migrate MyGUI workbench chrome onto the shared shadcn-inspired component facade, application-level component QSS, and ThemeService tokens without changing business state or layout structure.
---

# Modernize UI Components

Read `.agents/architecture/ui-components.md`,
`.agents/architecture/application-theme.md`,
`.agents/architecture/ui-state-boundaries.md`,
`.agents/architecture/runtime-boundaries.md`, and
`.agents/architecture/inspector.md`. Preserve `CORE-THEME-OWNER`,
`CORE-RESOURCE-BOUNDARY`, `CORE-APPLICATION-SETTINGS`,
`CORE-COMPONENT-STATE`, `CORE-EDITOR-PROFILES`,
`CORE-SELECTION-AUTHORITY`, `CORE-PROJECT-HISTORY`, and
`CORE-PERSISTENCE-V23`.

This Skill is the task flow for semantic chrome components, component QSS
deduplication, and workbench/dialog/Inspector visual alignment.

## When to use

Use this Skill when the change is workbench chrome: buttons, icon buttons,
inputs, selects, checkboxes, radios, tabs, cards, alerts, badges, empty
states, Tree/Table chrome, command-bar elision, or regional QSS that currently
copies generic control rules.

Do not use this Skill for:

- Appearance setting keys → `modify-application-setting`
- Figure/Inspector `PropertySpec` contracts → `modify-component-property`
- Theme-bypass rule promotion → `evolve-architecture-rule`
- Selection, Inspector lifecycle, or Qt listener bugs → `debug-gui-regression`

## Procedure

1. Classify the surface (dialog, workbench chrome, Inspector primitive, or
   regional QSS). Keep native PySide6 types and annotate with
   `apply_ui_style()` / factories from `mygui.widgets.ui_components`.
2. Map Create/OK/Apply/Export/Save/Fit to `primary`; Cancel/Configure/Browse/
   Copy/Rename to `outline`; delete/remove/clear/reset-library to
   `destructive`; toolbar glyphs and Restore defaults to `ghost`. Declare the
   variant at each call site. Derive heights from `DensityMetrics`.
3. Put shared control rules in `mygui/widgets/ui_components/style.qss`.
   `ThemeService` composes that document into every regional `bind_qss` sheet.
   The application stylesheet stays the small popup/`QMessageBox` document so
   `QApplication.setStyleSheet` does not re-polish bound workbench trees.
   Light/Dark leaves the process-global popup sheet unchanged so that call is
   skipped; density still rewrites sizes. Regional unique files keep only
   container chrome and are prefixed with the
   shared component document because Qt local stylesheets isolate a subtree. `ThemeBindingRegistry` is
   the only bind table while ThemeService is live. Token publish
   (`publish_qss_tokens`) is separate from widget replay. Each transaction
   applies the application sheet only when that small document changed, plus one
   sheet per changed regional root; identical strings skip `setStyleSheet`. Nested chrome is an explicit
   theme participant; overlapping windows are not a second DFS of the same
   descendants. Settings Center binds a `QssResourceBundle` of center + pages QSS
   once. Do not blanket-polish the widget tree after QSS apply or rollback.
   Repolish only when a dynamic property actually changes. Inspector nested
   stack switches batch one outermost `updateGeometry()` and present only the
   current leaf Inspector on the visible stack. Style Gallery stays
   eager; Layout/Chart/Element Galleries are lazy. Desktop smoke `--all-styles`
   must visit every visible Matplotlib Style Dialog.
4. Apply `UiTextRole` through `apply_text_style` and `UiRole.SECTION` through
   `annotate_section`. Do not change expand/collapse or child enablement.
5. Lock shell/dialog/Inspector structure with `capture_layout_signature`.
   Run `inspect_chrome` on production windows. Preserve editable/checkable
   ComboBox exceptions, command-bar `ghost` (not `icon-button`), `QTabBar`
   scroll buttons, and `QLineEdit` clear/search `QToolButton`s. Signature
   capture must use the Qt layout method, not a shadowed `widget.layout`
   instance attribute.
6. Resolve icons through `ThemeIconProvider`. Do not edit `pictures/icons`.
   Brand, preview, and user-data icons stay original color.
7. Do not change parent `QLayout` structure, widget order, stretch, panel
   positions, or Splitter defaults. Elide text and add tooltips inside the
   existing control.
8. Do not add a production matrix page. Keep the component matrix in tests
   and screenshot evidence under ignored `build/agent-results/`.
9. Route Message Bar, confirmation, modal warning/error, field validation, and
   busy/progress through `mygui.widgets.ui_components`. Do not call
   `QMessageBox.warning` / `QMessageBox.question` from production code. Do not
   add a Toast stack or extra layout nodes. Keep `status_messages` `(text, level)`
   and `start_background_task` unchanged.
10. Update `docs/settings.md` and `docs/workbench.md` only when user-visible
   chrome behavior changes. Do not write application keys into schema v23.

## Forbidden

- A second theme owner, process-global token table, or hard-coded chrome hex
- `QApplication.setFont` / `setPalette` / `setStyleSheet` outside
  `mygui/application_theme/`
- Replacing native controls with custom subclasses that change signals or
  test doubles
- Copying generic button/input/state QSS back into regional sheets
- Replacing icon assets or recoloring brand/preview icons
- Pixel-golden screenshot assertions
- Mutating Matplotlib Figure style, Registry, selection, Undo/Redo, dirty
  fingerprints, or project JSON as part of a visual change
- Direct `QMessageBox.warning` / `QMessageBox.question` outside the feedback
  facade; a second Message Bar plus modal for the same error; new Toast,
  Spinner, or progress-bar widgets

## Verification

Checks, with `E:\PycharmProjects\ven\pyside6_env\Scripts\python.exe`:

- `.agents/checks/verify_fast.py --task modernize_ui_components`
- `.agents/checks/verify_architecture.py --fail-on-gray`
- After the last component phase:
  `.agents/checks/verify_full.py --profile application`

Cover the role/variant/size/text-role/section state matrix; Light/Dark ×
8/9/16 pt × three densities; hidden-dialog retokenize and theme rollback;
960×600–2560×1440 shell geometry; main-window parentage and Splitter
defaults; layout signatures for Settings/create/export/34 Inspectors;
the Inspector geometry matrix in `tests.test_inspector_geometry`;
theme-switch isolation from project state; keyboard focus, accessible
names, and disabled/read-only/invalid. Confirm a Light/Dark switch applies 0 extra application stylesheets plus at most 13 changed
bind roots, with no second-registry replay and no whole-tree polish. Density/size
changes still apply the small application sheet once. Confirm
lazy Layout/Chart/Element Galleries keep stacked indexes and final layout
signatures after first activation. Confirm `pictures/icons/**` is unmodified.

A required check that is failed, unknown, or not run blocks completion.
`manual_smoke: true`: native dialogs, 100/125/150/200% DPI, dual-monitor, and
OS System-theme are Windows desktop evidence; offscreen tests do not claim
them.
