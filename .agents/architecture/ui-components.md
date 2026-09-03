# UI Component System

Use this page for MyGUI workbench chrome components: semantic roles, variants,
sizes, tones, application-level component QSS, and the public
`mygui.widgets.ui_components` facade. This is Agent Engineering material, not
user documentation.

This page does not own application preferences, Matplotlib Figure style, or
project schema v23. Preserve `CORE-THEME-OWNER`, `CORE-RESOURCE-BOUNDARY`,
`CORE-APPLICATION-SETTINGS`, `CORE-COMPONENT-STATE`, `CORE-EDITOR-PROFILES`,
`CORE-SELECTION-AUTHORITY`, `CORE-PROJECT-HISTORY`, and
`CORE-PERSISTENCE-V23`.

## Owner

`ThemeService` remains the only publisher of application font, QPalette,
bundled QSS, density metrics, and chrome icon roles. Semantic shadcn-inspired
aliases (`UI_*`) are extra names on the same `ThemeSnapshot` token table; they
map onto the existing neutral-gray plus blue palette and never introduce a
second appearance owner.

`mygui.widgets.ui_components` is the public creation and annotation facade.
It does not call `QApplication.setFont`, `setPalette`, or `setStyleSheet`,
does not load QSS from the process working directory, and does not publish
tokens. Widgets bind regional sheets through `ThemeBindingPort.bind_qss`.

UI theme is not Matplotlib Figure style. A theme or component-style change
must leave Registry trees, selection, Undo/Redo, dirty fingerprints, and
project JSON byte-identical.

## Native widgets and dynamic properties

Production controls stay native PySide6 types (`QPushButton`, `QLineEdit`,
`QComboBox`, `QCheckBox`, `QRadioButton`, `QTabWidget`, `QFrame`, and the
existing wrappers such as `PyEmptyState` and `ColorChoiceWidget`). Do not
replace them with custom `QWidget` subclasses when that would change signals,
test doubles, or submit paths. `ColorChoiceWidget` keeps the 52×52 swatch and
sizes its host from that explicit `minimumSize()`, never from an invalid
`minimumSizeHint()`. Width and height come from separate `minimumSize()`
components; stacking uses swatch width as the wrap threshold and swatch
height as the non-stacked host height.

Semantic style is applied with validated Qt dynamic properties:

| Property | Closed values |
| --- | --- |
| `uiRole` | `button`, `icon-button`, `input`, `textarea`, `select`, `number`, `checkbox`, `radio`, `tabs`, `card`, `alert`, `badge`, `empty-state`, `tree`, `table`, `section`, `status`, `progress` |
| `uiVariant` | `primary`, `secondary`, `outline`, `ghost`, `destructive` |
| `uiSize` | `small`, `default`, `large`, `icon` |
| `uiTone` | `neutral`, `info`, `success`, `warning`, `error` |
| `uiInvalid` | `true` when a control is in a validation-error state |
| `uiBusy` | `true` while a trigger is running a background task |
| `uiTextRole` | `page-title`, `section-title`, `label`, `body`, `muted`, `caption`, `value` |

Call `apply_ui_style()` / `apply_text_style()` after setting properties.
Those helpers compare `uiRole` / `uiVariant` / `uiSize` / `uiTone` /
`uiInvalid` / `uiTextRole` and call `refresh_ui_style()` only when a value
actually changes. Repeat annotation with the same spec is a no-op.
Typography uses `apply_text_style(label, UiTextRole, tone=NEUTRAL)`.
Existing `QGroupBox` hosts use `annotate_section(group)` / `annotate_sections(root)`:
that sets `uiRole=section` and does not change checkable/checked expand state
or child enablement. New UI must create or annotate controls through this
facade. Existing windows migrate by annotation; they keep their current
classes and object names.

Button variants are declared at each call site (`style_button(..., variant=...)`
or an explicit `apply_ui_style`). Do not infer variant from the button label.
Use:

- `primary` for the window's single submit: Create, OK, Apply, Export, Save, Fit
- `destructive` for irreversible Delete, Remove, Clear, and reset library/preferences
- `ghost` for toolbar glyphs, Restore defaults, and light auxiliary actions
- `outline` for Cancel, Configure, Browse, Copy, Rename, and ordinary secondary actions

Command-bar and activity-rail tools stay `uiRole=button` + `ghost`. Do not use
`uiRole=icon-button` / `UiSize.ICON` there: the icon-button rule sets a square
`max-width` and would crush gallery labels.

## Typography

`ThemeService` derives `FONT_PT_BODY`, `FONT_PT_PAGE_TITLE` (body + 2 pt),
`FONT_PT_SECTION_TITLE`, `FONT_PT_CAPTION` (max(8, body - 1)),
`FONT_WEIGHT_TITLE` (600), and `FONT_WEIGHT_BODY` (400). The font chain stays
Segoe UI / Microsoft YaHei / sans-serif. Hierarchy is weight and color except
for those two point-size offsets.

## Layout signatures and runtime inspection

`capture_layout_signature()` / `signature_paths()` lock parentage, layout type,
child order, stretch, Splitter orientation/count, Tab object names, and stack
counts. They ignore pixel geometry, fonts, QSS, `qt_*` internals, and
Matplotlib canvas widgets.

`inspect_chrome(root)` requires visible interactive controls to have a closed
`uiRole`. Buttons and icon-buttons need an explicit `uiVariant`. Icon-buttons
need both a tooltip and an accessible name. Exemptions: `qt_*` object names,
the test matrix, Matplotlib chrome, editable ComboBox trees, check-model
ComboBox trees, scrollbars, headers, size grips, tab bars, `QTabBar` scroll
`QToolButton`s, `QLineEdit` clear/search `QToolButton`s, exact-type
`QAbstractButton` table corner widgets, and unannotated color-grid
`QListView`s. `annotate_inspector_control` / `annotate_form_fields`
never mark those protected combos as `select`. ComponentInspector annotates
remaining native fields after section construction; Chart/Element/Errorbar
title-bar dialogs still do not call whole-tree `annotate_form_fields`.

## Visual contract

Heights and spacing derive from `DensityMetrics` (`SIZE_BUTTON`,
`SIZE_CONTROL`, `SIZE_TREE`, `SIZE_TABLE_ROW`, `SPACE_*`, `SIZE_INDICATOR`,
`SIZE_SCROLLBAR`, `SIZE_SECTION_TITLE_TOP`, `SIZE_SECTION_TITLE_LEFT`,
`SIZE_SECTION_MARGIN_TOP`). Application and regional component rules target
semantic `uiRole` attributes so native dialogs and Matplotlib toolbars are
not restyled. Group boxes, tree/table views, list widgets, and tab bars use
`[uiRole="section"|"tree"|"table"|"tabs"]` rather than bare type selectors.
`QGroupBox[uiRole="section"]` titles use `subcontrol-origin: margin` and
`subcontrol-position: top left` with those section tokens so the title and
indicator stay inside the frame. Title background is `UI_CARD` so the border
does not cut through the text or checkbox. Contents stay at least `SPACE_XS`
below the title band.
`QPushButton[uiRole="button"]` `min-width` is 0 so Inspector
actions can shrink to the panel; icon-buttons keep `SIZE_ICON_BUTTON`, and
status `QMessageBox` buttons keep a dedicated application rule. The font chain
stays Segoe UI / Microsoft YaHei / sans-serif. Do not add a legacy/new visual
toggle setting.

Default button appearance is outline (surface fill, strong border). Use:

- `primary` for Create, OK, Apply, Export, and empty-state primary actions
- `outline` / `secondary` for Cancel and ordinary auxiliary actions
- `destructive` for delete
- `ghost` / `icon` for icon tool actions

The required interaction matrix is enabled, hover, pressed, focus, checked,
disabled, read-only, invalid, and indeterminate. Selected tree/table/list
items and checked tools combine background, border, and font-weight so
selection is not color-only. Ordinary text contrast stays
at least 4.5:1; focus rings and control-boundary colors stay at least 3:1.

## Style publish

`ThemeService` is the only stylesheet publisher. While it is live,
`ThemeBindingRegistry` is the only QSS bind registry. `bind_widget_qss()`
does not also register the module-level fallback. Token publish
(`publish_qss_tokens`) updates watchers without replaying bound widgets.
Each theme transaction applies the application stylesheet at most once and
each changed regional root at most once; identical strings skip
`setStyleSheet`. Theme windows are independent style roots; nested chrome
joins explicit metrics/icon participant sets and is not walked as a second
tree. Dynamic properties call `refresh_ui_style()` only when
`uiRole`, `uiVariant`, `uiSize`, `uiTone`, `uiInvalid`, or `uiTextRole`
actually change.

Style Gallery is created at startup. Layout, Chart, and Element Galleries are
created on first legal activation or first property access, keep stacked
indexes 0–3, and subscribe with the current `ThemeSnapshot`. Inspector nested
`CurrentPageStackedWidget` page switches present only the current leaf
Inspector on the visible stack, batch `updateGeometry()` to the
outermost stack, and then update the Component Tree viewport, Inspector
viewport, and needed scrollbars only.

## Component QSS composition

Qt local stylesheets isolate a widget tree from the application stylesheet.
`ThemeService` therefore composes `mygui/widgets/ui_components/style.qss`
into every regional `bind_qss` document. The application stylesheet is only
`app_style.qss` (combo popups, spin arrows, `QMessageBox` buttons) so a
scheme change does not polish the workbench twice. Light/Dark keeps the
process-global popup sheet byte-identical (structure, sizes, and icon URLs
only; colors come from QPalette) so `QApplication.setStyleSheet` is skipped.
Density and font-metric size changes still rewrite that small sheet.
Regional files keep only that region's unique container chrome (command bar,
activity rails, Settings navigation pane, Inspector host, Tree/Table hosts).
Do not copy generic button, input, checkbox, radio, or validation-state rules
into regional sheets.

Do not attach generic `QComboBox { ... }` body rules to parent sheets.
Combo chrome is `QComboBox[uiRole="select"]` only. Unannotated editable
combos (multi-select data references) keep native Qt combo behavior.
Chart, Element, and Errorbar creation dialogs must not call
`annotate_form_fields` on the whole tree. Applying a parent `QComboBox`
sheet resets `currentIndex`, and a local `QComboBox QAbstractItemView`
rule isolates the popup from checkable models.
Theme QSS apply restores combo index and check state after `setStyleSheet`.

Bundled QSS and icons still resolve only through `mygui.resources`. Token
expansion uses the in-flight `ThemeSnapshot`; do not hard-code chrome hex in
Python or QSS.

## Layout freeze

"Do not change layout" means: do not change parent `QLayout` structure,
widget order, stretch, panel positions, Splitter defaults, or workbench
ratios. Allowed: control height, padding, radius, icon gap, text elision, and
tooltips. Command-bar labels elide inside the existing gallery/tool buttons;
do not widen the parent chrome to fit text.

## Icons

Do not replace or edit files under `pictures/icons`. Unify size, tint,
padding, checked, and disabled states through `ThemeIconProvider`. Brand
(`matlab.svg`, `app_icon.ico`), preview (`chart_images/`, `style_images/`,
`layout_images/`, `element_images/`), and user-data icons stay original
color.

## Inspector and dialogs

Inspector editors remain one exact `EditorProfile` per
`(ComponentKind, ComponentRole)`. Annotate the primitive controls those
profiles already create; do not add a generic JSON editor or a second
Inspector shell. Field titles use `labeled_form_row()` /
`add_labeled_form_row()`: single-line labels at natural font width, with
buddy, tooltip, and accessible name. `QFormLayout.WrapLongRows` moves the
editor below the label when the 240 px Inspector cannot fit both on one
row. Collapsible Advanced `InspectorSectionGroup` hosts hide
children when collapsed and must not disable them, so TeX and other
listeners can still sync. Dialogs keep field order, submit path, cache/reuse,
rollback, and window-size policy. UI still submits through public
Controllers, Services, Canvas capabilities, Inspector/container APIs, and
`DeletionCoordinator`.

## Component matrix

The role/variant/size/tone matrix is a test-and-screenshot helper. Do not add
a production Settings page, workbench panel, or layout row to display it.

## Selection for later UI

| Need | Role | Variant | Size |
| --- | --- | --- | --- |
| Confirm / create / export | `button` | `primary` | `default` |
| Cancel / auxiliary | `button` | `outline` | `default` |
| Delete | `button` | `destructive` | `default` |
| Toolbar glyph | `icon-button` | `ghost` | `icon` |
| Text field | `input` | `outline` | `default` |
| Long text | `textarea` | `outline` | `default` |
| Combo / enum | `select` | `outline` | `default` |
| Spin box | `number` | `outline` | `default` |
| Boolean | `checkbox` | `outline` | `default` |
| Exclusive choice | `radio` | `outline` | `default` |
| Section host | `section` or `card` | `outline` | `default` |
| Validation / status | `alert` or `badge` | — | `small` plus `uiTone` |
| Unpopulated view | `empty-state` | `primary` action | `default` |

Example:

```python
from mygui.widgets.ui_components import UiVariant, create_button, apply_ui_style

ok = create_button("OK", variant=UiVariant.PRIMARY, parent=dialog)
apply_ui_style(existing_line_edit, role="input")
```

Do not add hard-coded chrome colors or bypass `ThemeService`.

## Feedback facade

`mygui.widgets.ui_components` is the only production presenter for confirmation
and modal warning/error boxes. `ask_confirmation()`, `present_warning()`,
`present_error()`, `style_message_box()`, `style_progress_bar()`,
`set_validation_state()`, and `set_busy_state()` live there.

- `UiRole.STATUS` marks the existing bottom Message Bar and status labels.
  `PyMessageBar` keeps the `level` property for compatibility and maps it onto
  `UiTone`. Visible text in the same `QLabel` uses `Success —`, `Warning —`,
  and `Error —` prefixes; long text elides in the current width; tooltip and
  accessible name/description keep the full level and body. Same-tone updates
  replace text only. A tone change refreshes the Frame and Label at most once
  each. Elision is cached by full text, effective width, and font, so a resize
  that does not change the measurable width skips `setText`, tooltip, and
  accessible attributes. There is no close button or timer. One user action
  emits at most one Message Bar result and must not also pop a duplicate
  warning box.
- Ordinary confirms use a primary Continue button as the default. Destructive
  confirms (delete, clear, reset, overwrite) use a destructive Continue with
  Cancel as the default; Esc and the window close cancel. `english_buttons.ask_yes_no`
  forwards to `ask_confirmation`.
- External file, storage, and unrecoverable runtime failures use
  `present_error`. Recoverable validation, success, empty data, and workbench
  warnings use the Message Bar or existing page state. Modal creation dialogs
  may use `present_warning` because the Message Bar is covered; they still
  must not dual-write the bar.
- `set_validation_state` marks the exact failing control (`uiInvalid`, error
  tooltip, accessible description) and restores the original help text when
  cleared. Style is refreshed only when valid/invalid actually switches;
  message-only edits update tooltip and accessible description. Multi-field
  failures still produce one summary Message Bar or one modal. Submit buttons
  stay enabled so the user can retry.
- `set_busy_state` is idempotent: it stores original button text and enabled
  state once, shows `Fitting…` / `Connecting…` / `Validating…`, and restores
  on success, failure, cancel, and owner destruction. Repeat busy calls do not
  disable again, rewrite the label, or polish. Late callbacks must not revive
  a destroyed widget. Template apply restyles the existing `QProgressBar`; do
  not add a Spinner, Toast, or extra progress bar.
- Production code outside `feedback.py` must not call `QMessageBox.warning` or
  `QMessageBox.question`. Native `QFileDialog` and `QColorDialog` stay native.
  QMenu, QToolTip, and QScrollBar rules live in application-level component
  QSS; regional sheets do not copy them.

## Completion checklist

- Light, Dark, and System still resolve through `ThemeService`.
- Compact / Standard / Comfortable × 8–16 pt keep the density table and the
  font-metric floor.
- Hidden Settings/Style/Layout/Fit dialogs, Inspector hosts, and Canvas
  popouts retokenize, including composed component QSS.
- Theme apply failure rolls back; icon cache still keys by role / size /
  scheme / density / DPR.
- 960×600 through 2560×1440: no critical label clipping; visible Canvas width
  stays at least 400 px when space permits.
- Main-window parentage, child order, Splitter defaults, and panel positions
  stay unchanged. Layout-signature tests cover the shell, Settings Center,
  create/export dialogs, and all 34 Inspector profiles.
- Theme switch does not mutate Registry, selection, Undo/Redo, dirty
  fingerprints, or project JSON.
- Keyboard focus, accessible names, and disabled / read-only / invalid states
  remain distinguishable. Runtime `inspect_chrome` covers production chrome.
- `pictures/icons/**` is unmodified.
- Offscreen tests do not claim native dialogs, drag/drop, multi-monitor DPI,
  or live TeX/MATLAB. Those remain `manual_smoke`.
- Pixel-golden screenshot tests are forbidden; desktop smoke PNGs are human
  review evidence only.
