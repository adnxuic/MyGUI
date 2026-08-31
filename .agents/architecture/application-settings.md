# Application Settings

Use this page for persistent application preferences, the Settings Center
submit path, dual-slot QSettings storage, typed setting registry work, and any
narrow port consumed by Figure creation or export. This is Agent Engineering
material, not user documentation.

Preserve `CORE-APPLICATION-SETTINGS`. Application settings are not Figure
component state. Do not route a setting-key change through `schema-migration`
or write keys into schema v23.

## Authority

The composition root (`main.py` after org/app name, before `MainWindow`)
creates one `SettingsBackend` and one `ApplicationSettingsService`, then
injects both. Application and color-library document ports come from that
backend so they share `WRITE_UNCERTAIN`. Widgets, Controllers, Canvas
helpers, and dialogs do not construct `QSettings()`, do not wrap a second
backend, do not read raw groups such as `workspaceLayout`, `figureExport`,
or `colorLibrary` after migration, and do not keep a second preference model.

`ApplicationSettingsService.snapshot()` is the committed in-memory authority.
UI drafts live only inside a `SettingsSession`. Color library data is a
sibling document on the same backend, not a field of
`ApplicationSettingsSnapshot`.

These values never enter:

- integer schema-v23 project files
- the per-project `QUndoStack` / `FigureHistoryService`
- project dirty fingerprints
- `ComponentState`
- Canvas materialization, snapshot apply, or restore

Opening a project always uses the persisted v15 tree. New-Figure application
defaults never overwrite an opened Figure.

## Dual-slot storage

One backend yields two isolated document ports:

| Document | Slot keys |
| --- | --- |
| Application settings | `applicationSettings/slotA`, `applicationSettings/slotB` |
| Color library | `colorLibrarySettings/slotA`, `colorLibrarySettings/slotB` |

Each slot stores one complete JSON envelope: `schema`, `schema_version`,
`revision`, `payload`, `sha256`. Application envelopes use schema
`mygui.applicationSettings`; color-library envelopes use
`mygui.colorLibrarySettings`. Current `schema_version` is integer `1`.

Same-version unknown payload fields are treated as `READ_ONLY_FUTURE` so
close-save cannot rewrite the blob after normalize-to-default. Incompatible
stored shapes must bump `schema_version`.

Hash is SHA-256 hex of UTF-8 canonical JSON of the envelope with `sha256`
removed: sorted keys, compact separators `(',', ':')`, `allow_nan=False`.
`revision` is a positive signed 64-bit integer. Encoded envelope size is at
most 1 MiB.

There is no active-slot pointer. Load validates both slots independently and
selects the highest valid revision.

| Health | Meaning |
| --- | --- |
| `NORMAL` | Both slots valid, or one missing on a first write, and the chosen revision is current |
| `DEGRADED` | One slot is corrupt; keep the other; the next successful commit repairs the bad slot |
| `READ_ONLY_FUTURE` | Any structurally valid future `schema_version` forbids writes; a valid current-version slot may be used as a read-only snapshot, otherwise built-in defaults |
| `RECOVERY_REQUIRED` | Split-brain (same revision, different payload/hash) or both slots were present and corrupt; do not silently re-import legacy |
| `WRITE_UNCERTAIN` | `sync()` did not prove durability; roll back runtime state; this process must not write again |

Distinguish a missing slot key from a present key that fails decode or hash.
Migrate legacy only when both new slots are absent. After the first successful
new-slot commit, legacy groups remain inert data; production writers for
`workspaceLayout`, `figureExport`, and `colorLibrary` are removed. Isolated
legacy migrators cover Workspace v1/v2, Figure Export v1, and Color Library
v1. A failed domain resets only that domain.

Commit writes the non-current or older slot, then:

`setValue` → `sync` → `status` → fresh-reader readback → decode / hash /
typed equality.

The fresh reader is a new `QSettings` on the same organization, application,
and file, not the writer object. Publish the memory snapshot and one event
only after every step succeeds. A failed commit leaves the previous snapshot
unchanged.

## Service, session, and submit

`ApplicationSettingsService` exposes `snapshot()`, `begin_session()`,
`commit_patch()`, `reset_section()`, and `subscribe()`. Events fire
exactly once after a successful commit. Failures and rollbacks emit no
success event.

`SettingsSession` stores only the dirty patch and the base revision. It must
not retain a stale full snapshot copy.

`reset_section` mutates the session draft only. It is not an immediate
disk write.

Disjoint external changes rebase automatically, then commit. A conflicting
key rejects the commit and resynchronizes the session. `SettingsCommitResult`
reports success, warning/error, conflicts, and storage health.

Runtime apply for `LIVE_REVERSIBLE` settings is a reversible transaction:
validate, apply preview without disk, commit the document, and on storage
failure restore the pre-preview appearance. Any step failure rolls back in
reverse order, keeps the committed snapshot, and emits no event.

## Settings Center shell

`mygui.widgets.settings_center` is the cached modal Settings Center. Integrator
holds one `SettingsCenterHost` on MainWindow and opens it from the gear or a
Settings `QAction` via `host.open()`. The host lazily creates a single
`SettingsCenterWindow` (`objectName` `setting_dialog`) that stays subscribed
through `bind_qss` and `subscribe_theme_window` so a hidden dialog still
follows Dark/Light.

On each open the window calls `begin_session()`, reloads every already-created
page from one shared `draft_values` mapping, centers within 90% of the current
screen `availableGeometry` (initial 840×620, minimum 720×520 logical pixels;
smaller screens scale to 90%), and does not write window geometry to QSettings.
Clearing search on session start does not implicitly create pages. Session
start, cached-page refresh, and target selection each run once; the current
page is not loaded a second time on reopen. Switching back to a created page
also reloads it from that mapping. Search Enter/Return is swallowed and OK is
not the default button, so the search box cannot commit.
A search with no matches hides the page stack. Search haystack includes
`SettingSpec` enum choice values/names and Maintenance command keywords.

`SettingsPageHost` exposes `draft_values(keys)` and `stage_values(mapping)` as
the page data path. Single-key `draft_value` / `stage_value` wrap those batch
methods. Export's option group, Appearance's three live values, and Axes Copy
each stage once, update the footer once, and preview appearance at most once.
Successful edits do not reload the page; failures reload widgets from the
authoritative draft. Page switches, Apply resync, and reopen still refresh.
Font-family combos share one process-level catalog model from the Matplotlib
adapter so Axes Components does not insert the family list once per editor.

Appearance draft changes call `ThemeService.preview`. Theme apply/rollback
errors emit one Message Bar result and reload widgets so they stay aligned
with chrome. Accept, Reject, Esc, and the window X finish the session in
`QDialog.done()`; `abandon()` and `release()` are idempotent. Cancel, Esc, and
window close restore pre-session appearance and discard the session without
writing. If the committed theme is System, Cancel then `ensure_committed` so
an OS Light/Dark switch during the session is honored without a no-op theme
transaction. Rollback failure keeps the window open and reports one error.
Apply and OK run `commit_patch` after a rollback-capable preview and are
disabled when the service is not writable (`READ_ONLY_FUTURE`, recovery,
write-uncertain).
`SettingsHealth` keeps those states independent of `DEGRADED`. Storage
failure restores persisted values and the pre-window appearance.
`reset_section` is draft-only (`Restore page defaults`) and excludes hidden
`workspace.layout`. Reset-all stages built-in defaults once through
`service.reset_all_preferences` and reloads every created page. Immediate
commands use `request_immediate_command` with their own confirmation and never
ride the Apply patch. Each user action emits at most one Message Bar result
through the host `on_message` callback; Integrator wires that to MainWindow.
Each page lives in its own `QScrollArea`. Hosted pages omit the in-page
intro label because the shell already shows `SettingsCenterPageSpec.description`.
Components uses Line / Scatter / Text tabs, and Axes Components uses General /
Spines / X Axis / Y Axis tabs; each tab body scrolls internally so the tab bar
stays visible at 840×620. Hosted Axes Components builds General first and
realizes the other tabs on first visit so the initial page open stays cheap.

B and C register pages with `SettingsCenterHost.register_page(SettingsCenterPageSpec)`.
Factories run once on first visit. Search uses page title, description, and
page keywords plus `SettingsRegistry` spec `key` / `label` / `tooltip` /
enum choice text. Do not invent a second field-keyword catalog.

## Typed registry

Every persistent key declares type, default, normalizer, validator,
`SettingEffect`, page, editor contract, and migration contract through
`SettingSpec` / `SettingsPageSpec`. Production editors are explicit typed
controls. Editable JSON is forbidden.

Closed `SettingEffect` values:

| Effect | Behavior |
| --- | --- |
| `LIVE_REVERSIBLE` | Preview immediately; Cancel restores the pre-session appearance |
| `NEXT_USE` | Takes effect on the next creation or export; live Figures stay unchanged |
| `RESTART_REQUIRED` | Persist now; tell the user a restart is required; do not half-apply |

Persisted pages: `appearance`, `workspace`, `new_figure`, `components`,
`axes_components`, `export`.
Integrations and Maintenance are read-only status, navigation actions, or
immediate commands, not extra snapshot sections. Navigation order is
Appearance, Workspace, New Figure, Components, Axes Components, Export,
Integrations, Maintenance.

Fresh install defaults: theme System, 9 pt, Standard density. Detectable
legacy migration defaults: Light, 9 pt, Standard, so existing visual chrome
is preserved. New Figure defaults: width 6.4 in, height 4.8 in, document DPI
100, with precedence explicit input > application defaults > built-in
defaults. Export preferences store format, output, encoding, metadata, the
`Use project DPI` strategy, a separate custom DPI, and the last directory.
`Use project DPI` is a strategy flag; the live export binds the current
project DPI.

## Narrow ports

Figure Controllers, Figure domain Services, Canvas host helpers, and
`EditorContext` must not receive `ApplicationSettingsService`. Creation and
export consume only:

- `NewFigureDefaultsProvider` for Style creation and first-time text/Excel
  Figure size and document DPI
- `ComponentDefaultsProvider` for Line/Scatter/free-Text and ordinary Axes
  creation appearance (`current()` returns `ComponentDefaultsSettings` with
  nested `axes: AxesComponentDefaults`; do not inject the Settings Service)
- `ExportPreferencesPort` for default export options
- `WorkspaceLayoutPort` for MainWindow remember/restore, immediate reset, and
  close-save. Reset is a confirmed command, not an Apply draft. A close-save
  failure logs and leaves the previous slot; it must not block exit.

MainWindow receives the injected service (and the backend when ColorLibrary
must share the store). A test-only `settings=` `QSettings` is wrapped once
inside `compose_window_settings` for both documents; TitleBar, MenuBar, the
export dialog, and ColorLibrary do not wrap again. MainWindow must not
`setValue` the inert `workspaceLayout` group.

The composition root injects the New Figure port into `PyFigureWindow`
(`new_figure_defaults=` or `set_new_figure_defaults_provider`) from
`service.new_figure_defaults_provider()`, and the Components port
(`component_defaults=` or `set_component_defaults_provider`) from
`service.component_defaults_provider()`. Style creation, first-time text
import, and first-time Excel import call `current()` at use time through
`creation_figure_size()` or `resolve_new_figure_defaults`; they must not
cache a snapshot. Line/Scatter/free-Text creation merges style, palette, and
Components overrides in `creation_preferences.py` at use time. Ordinary Axes
creation merges Figure style, Axes Components overrides, and Matplotlib 3.9
fallbacks in `resolve_axes_appearance()`; Settings/UI must not import
Matplotlib. Creation dialogs freeze one snapshot in `__init__` and ignore
later Apply until a new dialog opens. `AxesLayoutService.create()` accepts
that frozen `ResolvedAxesAppearance` or reads the provider once at the start
of a programmatic create. `load_project_figure_snapshot`, schema-v23 open,
materializers, Undo/Redo replay, layout geometry updates, Colorbar auxiliary
Axes, In-Axes, `add_component_line`, and Reference Guide restore never
call `ComponentDefaultsProvider`. `ChartCreationStager` receives resolved
kwargs only.

Once a Figure exists, later edits stay on Controllers, domain Services, and
project history. Components and Axes Components keys use
`SettingEffect.NEXT_USE`. Wire shape is
`{"kind": "inherit"|"override", "value": ...}`; inherit still stores the last
custom value. Envelope `schema_version` stays `1`: a missing `components`
or `components.axes` section loads as all inherit; same-version unknown
fields stay `READ_ONLY_FUTURE`. Do not put these keys in schema v23 or
`docs/component-properties-v23.md`. Title, Axis Label, Legend, limits, scale,
locator, formatter, aspect, and margins are not Axes Components defaults; a
later Axes Inspector property must decide whether it also joins that page.
`ARCH-COMPONENT-DEFAULTS-BYPASS` remains
a planned gray candidate for `evolve-architecture-rule`; this task does not
add a new rule.

## Color library

`ColorLibrary` remains the color-domain authority on its own dual-slot
document, constructed with `backend.color_library_settings_port()`. It is
not merged into `ApplicationSettingsSnapshot`. A failed color-library commit
must not change in-memory lists and must not emit `changed`. Reset-all
application preferences never deletes the color library; recent-color clear
and library reset are separate confirmed commands.

## Settings Center pages (Export, Integrations, Maintenance)

These three pages live in `mygui.widgets.settings_center`. They do not own
the Settings shell footer. Integrator calls
`register_c_pages(settings_host, color_library=..., backend=..., service=...,
on_open_tex_panel=..., on_open_matlab_panel=...)`, which uses
`SettingsCenterHost.register_page` with `SettingsPageHost` factories. Isolated
tests may still construct the widgets with `page_spec()`.

- **Export** reuses `FigureExportOptionsPanel` with no Controller or Registry
  state. Settings Export sets `persist_color_library=False` and hides
  favorite controls so picking a color does not `_publish` the color dual-slot.
  `Use project DPI` is a stored strategy shown without a frozen DPI number;
  Custom DPI is independent; a live export binds the current project's
  document DPI. Each export window can still override the defaults for that
  export. Values enter the session draft as `export.*` keys and commit through
  Apply/OK.
- **Integrations** is read-only TeX/MATLAB availability, session state, and a
  short diagnostic. `openTexPanelRequested` and `openMatlabPanelRequested` are
  the public actions MainWindow must connect to the existing right-rail
  panels. The page must not remount `PyTexWindow` / `PyMatlabWindow` and must
  not start either runtime.
- **Maintenance** shows dual-slot `DocumentHealth` as Normal, Degraded,
  Read-only future, Recovery required, or Write uncertain. In Normal/Degraded,
  `Reset all application preferences…` stages built-in defaults on the session
  (Apply commits) and never touches the color library. In incompatible health,
  `Reset incompatible storage now…` is an immediate confirmed command that
  calls `SettingsBackend.reset_incompatible_documents()` (`clear_legacy_keys`
  plus clearing the application slots, then a writable default commit), then
  `apply_committed_appearance` and a full page reload. Color library counts,
  `Clear recent colors…`, and `Reset color library…` are independent confirmed
  commands enabled only when color health is Normal or Degraded. Recovery
  required shows `Reset color library storage now…` (clears only the color
  dual-slot). Future-only color storage is read-only with diagnostics. A
  recovery load with `payload is None` must not apply `{}` as an empty library.

## Integrations and immediate commands

The Integrations page is read-only availability, session state, and a short
diagnostic summary, plus actions that open the existing TeX and MATLAB
panels. It does not remount those widgets and does not start either runtime.
TeX enablement, preamble, and MATLAB connection remain session state owned by
`CORE-TEX-OWNER` and `mygui.database.matlab_adapter`. They are never
application-setting keys.

Apply submits the session and keeps the window open. OK submits then closes.
Cancel, Esc, and window close revert uncommitted preview. Immediate commands
(`Reset workspace layout now…`, incompatible storage reset, color-library
reset/clear) require their own confirmation and must not ride the Apply
patch. Each user action emits at most one Message Bar result. Closing the
application must not be blocked by a workspace-layout write failure; keep the
previous slot and log.

A workspace-layout write on exit that cannot be proven still leaves the last
good slot intact.

## Promoted architecture rules

These candidates were recorded as planned boundaries during settings
decoupling, then classified `new_invariant` after production callers left the
storage adapter.

- `ARCH-QSETTINGS-BACKEND-BYPASS` — production code outside
  `mygui/application_settings/storage/` must not construct `QSettings(...)`
  or mutate a QSettings store (`beginGroup`, `endGroup`, `setValue` on a
  settings-named receiver, including aliases such as `QS = QSettings` /
  `prefs = settings`). Type annotations and duck-type checks are not
  constructions. **Promoted.**
- `ARCH-UI-THEME-BYPASS` — production code outside `mygui/application_theme/`
  must not publish application font, palette, or bundled QSS via
  `QApplication`/`app` `setFont`/`setPalette`/`setStyleSheet`, including
  `QApplication.instance().setFont`. Widget-local `setFont` is not application
  chrome. **Promoted.**

QSS color completeness is a Python contract (`tests.test_application_theme_qss`),
so Matplotlib and user colors are not false
positives. Keep these invariants when touching QSettings or chrome publishers.

## Completion checklist

- Every new or renamed persistent key has a `SettingSpec`, normalizer,
  validator, effect, page, editor, and migration contract.
- Dual-slot tests cover alternating writes, single- and dual-slot corruption,
  equal-revision split-brain, future+current, hash/readback/status faults,
  revision and 1 MiB bounds, and `WRITE_UNCERTAIN`.
- Legacy tests cover isolated, mixed, and unknown-version Workspace, Export,
  and Color Library domains; both slots missing migrate, both corrupt do not.
- Session tests cover disjoint rebase, same-key conflict, `reset_section`
  draft-only, events exactly once, and storage failure with unchanged
  snapshot.
- Runtime tests cover apply success, apply failure rollback, and rollback
  failure without a fake success.
- Isolation tests prove settings are absent from schema v23, Undo/Redo, dirty
  fingerprints, `ComponentState`, and Canvas snapshots.
- Color-library write failure leaves memory, `changed`, and project color
  cycles unchanged. Reset-all leaves the library intact.
- Export preference write failure after a successful image keeps the file and
  emits one warning.
- TeX/MATLAB absence does not block Settings or basic GUI work; checks must
  not start those runtimes.
- User-facing Settings documentation is updated only when the Settings Center
  exists (that documentation task). Architecture updates stay in this page.
- Interactive Windows smoke for a setting-key change covers the affected
  page. The full 100/125/150/200% DPI, dual-monitor, System theme, 8/16 pt ×
  three densities, cached window, native dialog, and missing TeX/MATLAB
  matrix belongs to the hardening/acceptance gate, not to offscreen tests.

Run `.agents/checks/verify_application_settings.py` before finishing. Routed
`verify_fast --task modify_application_setting` is required after Integrator
registers the task.
