# Verification Map

All local Python commands use
`E:\PycharmProjects\ven\pyside6_env\Scripts\python.exe`. Shared checks call
subprocesses through their current `sys.executable`. Qt tests run with
`QT_QPA_PLATFORM=offscreen`.

## Gates

| Concern | Focused modules |
| --- | --- |
| Package/resources/global Matplotlib | `test_package_boundary`, `test_resource_locator`, `test_matplotlib_boundaries` |
| Controller/value/exposure contracts | `test_component_controllers`, `test_matplotlib_property_contract` |
| Inspector/editor lifecycle | `test_component_inspector`, `test_component_editors`, `test_inspector_geometry` |
| Tree/selection | `test_component_tree` |
| Registration/services | `test_component_services`, `test_component_runtime_integration` |
| Canvas host/batch/restore | `test_py_figure_canvas`, `test_batch_chart_creation`, `test_canvas_popout`, `test_in_axes` |
| Table widget / color picker | `test_table_ui`, `test_color_picker`, `test_color_library` |
| Materialization/schema/IO | `test_component_materializers`, `test_project_schema`, `test_project_io`, `test_project_object_roundtrip`, `test_field_2d_grid`, `test_field_2d_component` |
| Deletion/project publication | `test_component_deletion_and_project_close` |
| Optional TeX/MATLAB/font paths | `test_optional_dependencies`, `test_font_diagnostics`, `test_scipy_fit_adapter` |
| Application settings / dual-slot storage | `test_application_settings_storage`, `test_application_settings_service`, `test_application_settings_session`, `test_application_settings_contracts`, `test_application_settings_new_figure`, `test_application_settings_pages`, `test_application_settings_center`, `test_application_settings_center_c`, `test_application_settings_components`, `test_application_settings_axes_components`, `test_application_settings_component_creation`, `test_application_settings_axes_creation`, `test_color_library`, `test_figure_export`, `test_gui_layout` |
| Application theme / QSS / chrome | `test_application_theme`, `test_application_theme_transactions`, `test_application_theme_chrome`, `test_application_theme_qss` |
| UI component facade / component QSS | `test_ui_components`, `test_ui_layout_signatures`, `test_gui_layout`, `test_command_gallery`, `test_color_picker`, `test_component_inspector` |
| MkDocs component contract | `test_component_documentation` |

`test_inspector_geometry` is the real Inspector geometry matrix, not a
structure-only check. It hosts each of the 34 profiles in a 240/320/480 px
scroll area across 8/9/16 pt, three densities, Light/Dark, and default /
per-group / all-expanded folds. Visible sibling section rects must not
intersect. Buddy field labels keep a readable natural width without internal
word wrap; `QFormLayout.WrapLongRows` moves the editor below the label when
the row is tight. Same-layout siblings are compared without treating
parent/child containment as overlap. GroupBox title and indicator
subcontrols stay inside the frame and do not cover section contents.
Desktop smoke maps every control rectangle into the Inspector host, fails
on unreadably narrow labels, sibling overlap, or style-subcontrol overflow,
and keeps targeted shots for Function Curve Expression/X range, Tick Label
Advanced, and fold bands. After expanding every collapsible group and
restoring the default folds, it measures cached leaf-Inspector switches.
Offscreen MainWindow warm-median construct is ≤150 ms outside coverage
tracing; native construct is ≤300 ms in desktop smoke. Offscreen Qt does
not cover native dialogs, DPI, or System theme.

Refactored dispatch stays table-driven: `ComponentEditorBase._create_editor`
and the Legend, In-Axes, and Secondary Axis `_read_property` /
`_write_property` functions keep McCabe complexity at most 5.
`create_editor_widget` has the same cap. `PyFigureCanvas` methods with
McCabe greater than 10 stay at most 15; public `add_*` wrappers stay at
McCabe 2 because remaining length is signature forwarding into creation
requests. Schema validators, `DeletionCoordinator`, and other hotspot
functions added by the compatibility hardening keep the ceilings in
`tests.test_architecture_rule_evolution` and must not worsen. These caps are
not a repository-wide complexity rule.

`verify_fast` runs compileall, Ruff, and the route's focused modules.
`verify_full --profile application` runs the complete suite once under branch
coverage with a one-hour subprocess budget, writes coverage JSON, then compares
each required file against its floor. Global coverage remains 80%. Each
established critical file must reach 90%, and each transaction-critical file
must reach 85%; a high group total cannot hide one weak file. The transaction
set is `registry`, `_delete_transaction`, `serialization`, `matplotlib_removal`,
`DeletionCoordinator`, template transformation, and Secondary Axis runtime; its
next hardening target is 90% without lowering another gate. Summary `coverage report` output is kept
for humans. Additional per-file floors cover the Figure toolbar (90%), Settings
envelope (85%), template application/storage (80%), and the Template workflow,
Title menu, Chart/Element creation dialogs, Inspector containers/Axes
sections, and Spec editor modules (80%). A discovery subprocess collects exact unittest IDs;
empty, failed, or duplicate collections reject the run.

All application batches share one process pool. GUI-sensitive modules keep
process isolation (one fresh coverage process per module, or per test ID for
configured hotspots such as `test_xrd_refinement`) so Qt, Matplotlib, and
`QApplication` state never run concurrently in the same process. Pure
contract, parsing, numerical, and static-analysis tests form LPT
micro-batches. The unified scheduler submits every batch in deterministic
longest-processing-time order. Both isolation styles run under
`coverage run --parallel-mode`, so all test IDs contribute to the combined
report. Every batch continues after test failures, while timeout, process,
future, and executed-count failures prevent partial coverage from reaching the
coverage thresholds. `coverage combine` merges only complete batch data. The
Matplotlib font cache is warmed serially before workers start so concurrent
rebuilds cannot race.

Isolation mode and historical duration live in one complete
`APPLICATION_TEST_MODULES` table. Added, removed, or unclassified test modules
fail plan validation; there is no 0.1s fallback for unknown modules.

`MYGUI_TEST_SHARDS` is the concurrency cap for the entire application pool and
accepts only integers from 1 through 16. The default is 4, matching Windows
CI. `1` is serial diagnostic mode: batches still use process isolation, but
only one worker runs at a time. Core worker counts above 1 still pack up to
four micro-batches per worker. `APPLICATION_TEST_TIMEOUT_SECONDS` defaults to
one hour for the complete test plan and
`APPLICATION_BATCH_TIMEOUT_SECONDS` defaults to 20 minutes. A batch receives
the smaller of its per-batch limit and the remaining global budget. Complete
plans, summaries, structured failures/errors, assigned test IDs, and untruncated
batch logs are written under ignored `build/agent-results/application/` using
contract v3 (`maxWorkers`, `isolationMode`, deterministic `launchOrder`, batch
durations, and completeness). Per-test and aggregated per-module timings remain
available in `build/agent-results/application-test-timings.json`. Windows CI
pins four pool workers and uploads both evidence locations. The
agent-engineering profile validates routing/contracts and deterministic
architecture scanners without importing the Windows GUI runtime. Standalone
`verify_architecture` executes the de-duplicated union of every CORE rule's
Python and scanner enforcement; `--skip-python` is reserved for the Ubuntu
Agent Core profile. Documentation uses `mkdocs build --strict`.

## Mandatory theme roundtrip acceptance

Every change to the theme publisher, palette/QSS/icon application or rollback,
Settings page caching, Inspector visibility/style inheritance, or Figure
toolbar creation/reparenting/theme participation must verify UI Style switching.
The `debug_gui_regression`, `modernize_ui_components`, and
`modify_application_setting` routes require `test_application_theme`,
`test_application_theme_transactions`, `test_application_theme_chrome`, and
`test_application_theme_qss`; Agent Core tests prevent dropping that coverage.
Use the union with other matching feature routes.

Run Light → Dark → Light and Dark → Light → Dark, repeated switching,
reselecting the committed mode, Cancel/Esc/close, storage failure, and partial
apply failure. Visit a Settings page before switching, revisit it afterward,
and cover pages/windows created during preview. Check actual background,
viewport, text, and every Matplotlib navigation-toolbar glyph (including cached
or popped-out canvases); token equality or one Home icon on a direct committed
apply is insufficient. Keep project state, selection, history, and Figure
rendering unchanged. Native `settings.theme_roundtrip` must pass in addition
to offscreen tests. Preserve the stylesheet-write and frame-time gates above;
unrun or failed acceptance blocks completion.

## Fault injection

When changing component registration, deletion, Inspector, project restore, or
tree projection, cover failures in Artist creation, Registry registration,
Section construction, Stack insertion, state synchronization, verification,
and both sides of tab publication. Assert no residual Artist, Controller,
Locator binding, tree node, listener, color consumption, or selection change.

## Manual smoke

Routes declaring `manual_smoke: true` require appropriate Windows desktop
checks for multi-Figure/multi-Axes navigation, Tree search, Chart/Element
switching, creation/deletion, save/open, and operation without TeX/MATLAB.
Native dialogs, drag/drop, multi-monitor DPI, and real integration runtimes are
not claimed by offscreen automation.

## Desktop smoke walk

`verify_desktop_smoke.py` is a local Windows check. It opens
the real MainWindow, clicks controls, and writes PNG plus `summary.json` under
`build/agent-results/desktop-smoke/`. Groups (`--only`) are `settings`,
`templates`, `field_2d`, `charts_1d`, `elements`, `inspectors`,
`layouts_xrd`, `axes_smoke`, `deletion_history`, `project_lifecycle`, and
`styles`. Settings includes the Templates page (Restore disabled, isolated
empty library). The templates group extracts, duplicates, and applies a chart
template without native file dialogs. Inspectors walk all 34 production
`(ComponentKind, ComponentRole)` profiles, expand every collapsible section
group, and write screenshots plus control rectangles mapped into the Inspector
host. Geometry failures (unreadably narrow buddy labels, sibling overlap, or
GroupBox title/indicator overflow) fail the walk. Qt `Negative sizes`
warnings also fail the walk. Native Inspector/theme
timings use the desktop smoke frame probe with 3 warmup frames and 20 samples
(`dispatch_ms` / `first_paint_ms` / `settle_ms`). Cached Inspector switch
gates are dispatch p95 ≤16 ms, first paint p95 ≤100 ms, and settle p95
≤150 ms, with 0 `ComponentState` clones, 0 Matplotlib redraws, and 0
full-window polish. Theme preview and rollback settle p95 must be ≤1000 ms
and at least 30% faster than the phase-0 native baseline (1500 ms / 2200 ms).
The `charts_1d` group also recreates Plot and Text dialogs and creates then
deletes Curve and Text components with the same 3-warmup/20-sample frame probe.
Dialog gates are dispatch p95 ≤50 ms, first paint p95 ≤100 ms, and settle p95
≤150 ms. Lightweight creation gates are dispatch p95 ≤200 ms, first paint
p95 ≤250 ms, settle p95 ≤300 ms, and at least 40% faster than the recorded
phase-0 baseline. Each measured creation permits no stylesheet write and
requires exactly one Inspector construction and one selection publication.
Curve requires exactly one queued canvas draw and no synchronous draw. Text
requires exactly one synchronous TextRenderService validation draw and no
redundant queued draw. Default-style resolution must not recur in measured
dialog samples after the three warmups.
The styles group opens Style Dialogs (default: `default`, `dark_background`, `seaborn-v0_8-colorblind`);
`--all-styles` adds the styles group if needed and visits every visible
Matplotlib Style Dialog (26), excluding Apply Template and hidden styles.
Each Style Dialog is opened, screenshotted, and Rejected; Figure, selection,
Settings, and history must stay unchanged. Count mismatches fail. Style walks
run after other performance scenarios.

`summary.json` uses `timingSchemaVersion: 2`. Frame probes record `dispatch_ms`,
`first_paint_ms`, and `settle_ms` (3 warmup + 20 samples, raw/median/P95) without
a fixed-duration `pump()` inside the timed interval; timeout is 2 s. Existing
aggregate keys remain compatibility aliases. Timings cover MainWindow construct (native ≤300 ms),
Appearance Dark preview/rollback, first versus cached Settings page open, lazy
Gallery first create versus cached open, cached component Inspector switch, and
100 same-tone Message Bar updates. Cached Inspector switch also records the
paint region. Native file dialogs, drag/drop, multi-monitor DPI, and live
TeX/MATLAB remain on the manual smoke page. DPI 100/125/150/200%, mixed-DPI
dual-monitor migration, and OS System Light→Dark→Light are marked verified only
after a real walk; missing hardware is unverified. It is **not** part of
`APPLICATION_TEST_MODULES` or `verify_full`. Do not set
`QT_QPA_PLATFORM=offscreen`. Pixel-golden comparison is not used; assertions
are structural.
