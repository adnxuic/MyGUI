# Application Theme

Use this page for application chrome: theme mode, effective scheme, density,
UI font size, QPalette, bundled QSS, control metrics, and theme icons.
`ThemeService` is the sole publisher. Do not invent a second appearance owner
and do not treat `mygui.widgets.theme` module constants as a live publisher.

Preserve `CORE-THEME-OWNER`. UI theme is not Matplotlib Figure style.

## Owner

`ThemeService` is the only publisher of application font, QPalette, bundled
QSS, density metrics, and chrome icon roles. It holds:

- `ThemeMode = SYSTEM | LIGHT | DARK`
- `EffectiveScheme = LIGHT | DARK`
- `Density = COMPACT | STANDARD | COMFORTABLE`
- immutable `AppearancePreferences` and `ThemeSnapshot`
- the current colors, QPalette, QFont, sizes, QSS tokens, and icon roles

Presentation widgets bind through an injected `ThemeBindingPort`. They do not
call `QApplication.setFont`, `setPalette`, or `setStyleSheet` for application
chrome, and they do not load bundled QSS with a private token table.

`ARCH-UI-THEME-BYPASS` is the promoted Scanner rule for that bypass. It
reports `QApplication`/`app` `setFont`/`setPalette`/`setStyleSheet` outside
`mygui/application_theme/`, including `QApplication.instance().setFont`.
Widget-local `setFont` is not a finding. QSS color completeness stays a
Python contract so Matplotlib and user colors are not lexical false
positives.

## Startup order

Required order after process identity (Windows AppUserModelID may run first):

1. Create `QApplication`
2. Install `mygui.font_diagnostics`
3. Set organization and application name
4. Create the settings backend and `ApplicationSettingsService`
5. Resolve and apply `ThemeSnapshot`
6. Create any `QWidget`

Do not create dialogs, the main window, or other widgets before the first
`ThemeSnapshot` apply. Font diagnostics stay ahead of font and widget setup
(`CORE-FONT-DIAGNOSTICS`).

Keep the platform native Qt style. Do not force Fusion.

## System, Light, and Dark

System follows PySide6 6.7.1 `QStyleHints.colorScheme` and
`colorSchemeChanged`. `Qt.ColorScheme.Unknown` uses the native palette
luminance captured at startup, not a later mutated palette.

Fresh install (no new slots, no legacy): System, 9 pt, Standard.
Detectable legacy migration: Light, 9 pt, Standard, so existing chrome is
unchanged.

Light keeps the current `mygui.widgets.theme` semantic roles. Dark core
colors are closed:

| Role | Hex |
| --- | --- |
| content | `#0F172A` |
| surface | `#1F2937` |
| surface-alt | `#273449` |
| command | `#0B1220` |
| text | `#F8FAFC` |
| muted | `#CBD5E1` |
| accent | `#2563EB` |
| focus | `#60A5FA` |
| border | `#475569` |
| error | `#FCA5A5` |

Ordinary text on its background is at least 4.5:1 contrast. Focus rings and
colors that carry control boundaries are at least 3:1. Forced Dark applies to
the application client area only; do not use private Windows DWM APIs to
recolor native title bars.

UI font size is 8–16 pt inclusive, default 9 pt. Changing appearance must not
mutate Matplotlib Figure, Artists, rcParams, project colors, or schema v17.

## Density

Use these logical-pixel bands, then prevent clipping with
`max(band_height, ceil(QFontMetrics.height()) + vertical_padding)` for row,
rail, button, tree, and control heights.

| Density | Spacing xs/sm/md/lg/xl | Rail / Button | Bottom | Command / Gallery | Table row / header | Tree / Control |
| --- | --- | --- | --- | --- | --- | --- |
| Compact | 3 / 6 / 9 / 12 / 18 | 40 / 36 | 24 | 42 / 64 | 22 / 38 | 22 / 26 |
| Standard | 4 / 8 / 12 / 16 / 24 | 44 / 40 | 28 | 48 / 72 | 24 / 44 | 26 / 30 |
| Comfortable | 5 / 10 / 15 / 20 / 30 | 52 / 48 | 34 | 56 / 84 | 30 / 52 | 32 / 36 |

Standard matches the historical first-run chrome sizes. Compact and
Comfortable scale that grammar rather than inventing a second layout system.

## QSS binding

Production widgets style through `ThemeBindingPort.bind_qss(widget, resource)`.
Bindings hold weak references and detach on `destroyed`, so hidden Settings
and Style dialogs, Inspector hosts, live Fit dialogs, and parentless Canvas
popouts still retokenize.

`mygui.resources.load_qss_resource` only resolves a bundled QSS resource and
expands the token mapping it is given. Callers pass `ThemeSnapshot` tokens
explicitly. The function must not remain a silent reader of a process-global
static token table once `ThemeService` publishes snapshots.

Monochrome chrome icons go through `ThemeIconProvider`, keyed by
source / role / logical size / scheme / density / DPR, plus an optional
variant (rotation / checked). Brand (`matlab.svg`, `app_icon.ico`), preview
(`chart_images/`, `style_images/`, `layout_images/`, `element_images/`), and
user-data icons stay original color. Scheme changes replace the cache table.

`ThemeWindowRegistry` holds weak `QWidget` references and drops them on
`destroyed`. Cached Settings/Style/Layout/Fit dialogs, Inspector hosts, and
parentless Canvas popouts call `subscribe_theme_window`. They must not store
`ComponentState`, selection IDs, or color-cycle cursors. Python-side chrome
sizes are limited to the `SIZE_PARTICIPANTS` object names; do not apply density
metrics to an arbitrary `QTableView` or `QTreeView`.

QSS that sets `background-color` (for example Settings `COLOR_SURFACE`) can
override `QPalette.Window` on that widget. The snapshot palette `Window` role
remains `COLOR_CONTENT_BACKGROUND`. Retokenize local QSS in the theme
transaction `qss` step so hidden dialogs still follow Dark/Light.

A widget-local stylesheet isolates that widget and its descendants from
ancestor and application `color` rules. Production sheets that set
`background-color` on a container also set `color` (and `QLabel` /
`QCheckBox` / `QRadioButton` / `QGroupBox` roles) so Dark→Light cannot leave
`WindowText` on the previous scheme. QScrollArea viewports used by Inspector
and Canvas are styled and receive the snapshot palette without
`WA_SetPalette`.

After local QSS replay, the `qss` step unpolish/polish bound widgets and
subscribed windows so native Qt styles drop the previous scheme's cache.
`current_qss_tokens()` follows the in-flight hub snapshot for the rest of
the transaction; rollback restores the captured hub snapshot.

## Theme transaction

Apply, including Settings preview, is one reversible transaction. Widget steps
are chosen from the actual delta after pre-render:

1. Strictly validate preferences and resolve System to `EffectiveScheme`.
2. Pre-render only the artifacts required by the planned steps: QPalette,
   font, and metrics always; QSS documents and icons only when those steps
   will run. Font-only previews must not rasterize chrome icons or expand
   stylesheets.
3. Capture mementos for `QApplication`, each bound widget, structural sizes,
   and icons.
4. On the GUI thread apply only the steps that changed. The font step
   filters `FontChange` on hidden widgets so cached Settings pages are not
   polished during a 1 pt preview:
   - A 1 pt font change is always the font step only, even when high-DPI
     font metrics would move the size floor by a pixel. Larger jumps also
     run QSS and density metrics when the font-metric size floor actually
     changes control heights.
   - Effective Light/Dark changes run Palette, QSS, and Icon.
   - Density changes run QSS, Metrics, and Icon.
   Compare pre-rendered QSS with the applied sheets. Unchanged documents
   publish the new snapshot and tokens without `setStyleSheet`.
   Publish the in-flight snapshot to the runtime hub before those widget
   steps so token readers see the new scheme.
5. On any failure, roll back in reverse order of the steps that actually ran.
   Keep the current `ThemeSnapshot` and emit no event.
6. Settings Apply finishes the reversible preview first, then the dual-slot
   document commit. Storage failure restores both the persisted values and the
   pre-window appearance.
7. Success publishes one `themeChanged(old, new)`.

Preview of `LIVE_REVERSIBLE` appearance follows the same rollback rules.
A preview session records the union of steps it actually executed. Cancel,
Esc, and dialog close restore those steps in reverse from the pre-session
memento. `ThemeService.ensure_committed(preferences)` is a no-event, no-redraw
no-op when the published effective theme already matches; it runs one apply
when System Light/Dark changed during the session.

## UI theme versus Figure style

Application theme owns workbench chrome. Matplotlib style, rcParams, Axes
palettes, Artist colors, and `CORE-MATPLOTLIB-BOUNDARY` catalogs stay on
`mygui.figuremodify.matplotlib_adapter` and Controllers. A theme switch must
leave Registry trees, selection, history, and project JSON byte-identical.

Do not use theme tokens as Figure defaults. Do not use Figure style as
application QSS.

## Completion checklist

- Startup tests (or source-order tests until the composition root changes)
  encode `QApplication` → font diagnostics → org/app name → settings →
  `ThemeSnapshot` → first widget.
- System, Light, and Dark each resolve; Unknown System uses the startup
  native luminance fallback.
- Fresh versus migrated defaults are System versus Light at 9 pt Standard.
- Contrast contracts cover Light and Dark body text (4.5:1) and
  focus/boundary colors (3:1).
- Density × 8 pt and 16 pt uses the table above and the font-metric floor.
- Token expansion covers every bundled QSS placeholder from a snapshot, not
  from ad hoc hex in Python chrome.
- Hidden windows, Canvas popouts, and icon DPR caches retokenize without
  leaked `destroyed` connections.
- Fault injection rolls back at pre-render, widget apply, and storage commit
  without a success event or a mutated snapshot.
- Figure/Registry/selection/history/project JSON are unchanged across theme
  transactions.
- Full Windows DPI, dual-monitor, and OS System-theme smoke is the
  hardening/acceptance gate. Offscreen tests do not claim that coverage.

The composition root applies `ThemeSnapshot` after settings load and before
any `QWidget`. Appearance `SettingSpec`s stay on `application_settings`;
`ThemeService` remains the only chrome publisher. The Settings Center shell
previews appearance through `ThemeService.preview` / `cancel_preview` /
`restore_pre_session_appearance` / `ensure_committed`. Theme apply/rollback
errors surface as one Message Bar result; widgets reload so they stay aligned
with chrome. After Cancel, if the committed mode is System,
`ensure_committed` runs so an OS Light/Dark switch during the session is
honored without repeating an identical transaction. Successful incompatible
storage reset uses the same `apply_committed_appearance` path as startup.
`ARCH-UI-THEME-BYPASS` is promoted.
