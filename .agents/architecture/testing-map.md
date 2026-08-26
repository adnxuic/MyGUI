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
| Inspector/editor lifecycle | `test_component_inspector`, `test_component_editors` |
| Tree/selection | `test_component_tree` |
| Registration/services | `test_component_services`, `test_component_runtime_integration` |
| Canvas host/batch/restore | `test_py_figure_canvas`, `test_batch_chart_creation`, `test_canvas_popout`, `test_in_axes` |
| Table widget / color picker | `test_table_ui`, `test_color_picker`, `test_color_library` |
| Materialization/schema/IO | `test_component_materializers`, `test_project_schema`, `test_project_io`, `test_project_object_roundtrip` |
| Deletion/project publication | `test_component_deletion_and_project_close` |
| Optional TeX/MATLAB/font paths | `test_optional_dependencies`, `test_font_diagnostics`, `test_scipy_fit_adapter` |
| Application settings / dual-slot storage | `test_application_settings_storage`, `test_application_settings_service`, `test_application_settings_session`, `test_application_settings_contracts`, `test_application_settings_new_figure`, `test_application_settings_pages`, `test_application_settings_center`, `test_application_settings_center_c`, `test_application_settings_components`, `test_application_settings_axes_components`, `test_application_settings_component_creation`, `test_application_settings_axes_creation`, `test_color_library`, `test_figure_export`, `test_gui_layout` |
| Application theme / QSS / chrome | `test_application_theme`, `test_application_theme_transactions`, `test_application_theme_chrome`, `test_application_theme_qss` |
| MkDocs component contract | `test_component_documentation` |

`verify_fast` runs compileall, Ruff, and the route's focused modules.
`verify_full --profile application` runs the complete suite once under branch
coverage with a one-hour subprocess budget, then applies global 74% and
critical-file 80% reports. A discovery subprocess collects exact unittest IDs;
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
agent-engineering profile validates routing/contracts and deterministic DSH
typecheck/tests/E2E. Documentation uses `mkdocs build --strict`.

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

`.agents/checks/verify_desktop_smoke.py` is a local Windows check. The
implemented walk is **Settings Center + NEXT_USE only** (Components / Axes
Components pages, Cancel/Apply restore, a minimum new Curve / Scatter / Text
creation, and a new Figure for Axes). It is not a full-application walk:
galleries, 27
Inspectors, XRD, table, Canvas popout, TeX/MATLAB Connect, and export encoding
remain on the manual smoke page. Evidence is PNG screenshots plus
`summary.json` under `build/agent-results/desktop-smoke/`. It is **not** part of
`APPLICATION_TEST_MODULES` or `verify_full`. Do not set
`QT_QPA_PLATFORM=offscreen`. Pixel-golden comparison is not used; assertions
are structural. Native file dialogs, drag/drop, and multi-monitor DPI remain
manual.
