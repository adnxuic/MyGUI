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
| Materialization/schema/IO | `test_component_materializers`, `test_project_schema`, `test_project_io`, `test_project_object_roundtrip` |
| Deletion/project publication | `test_component_deletion_and_project_close` |
| Optional TeX/MATLAB/font paths | `test_optional_dependencies`, `test_font_diagnostics` |

`verify_fast` runs compileall, Ruff, and the route's focused modules.
`verify_full --profile application` runs the complete suite once under branch
coverage with a one-hour subprocess budget, then applies global 74% and
critical-file 80% reports. A discovery subprocess collects exact unittest IDs;
empty, failed, or duplicate collections reject the run. Tests that own
QApplication/QWidget/QTimer event-loop state, Figure canvases, or process-global
Matplotlib state run on one deterministic `application-gui` serial worker, with
one fresh coverage process per test module. Pure contract, parsing, numerical,
and static-analysis tests use measured weights in deterministic LPT
`application-core` micro-batches and a fixed worker pool. Both pools run under
`coverage run --parallel-mode`, so all test IDs contribute to the combined
report. Every batch continues after test failures, while timeout, process,
future, and executed-count failures prevent partial coverage from reaching the
coverage thresholds. `coverage combine` merges only complete batch data. The
Matplotlib font cache is warmed serially before workers start so concurrent
rebuilds cannot race.

`MYGUI_TEST_SHARDS` controls application-core workers and accepts only integers
from 1 through 16. The default is `min(8, max(2, cpu_count))`; the GUI pool
always has one worker. Core worker counts above 1 use up to four micro-batches
per worker for dynamic load balancing. `APPLICATION_TEST_TIMEOUT_SECONDS`
defaults to one hour for the complete test plan and
`APPLICATION_BATCH_TIMEOUT_SECONDS` defaults to 20 minutes. A batch receives
the smaller of its per-batch limit and the remaining global budget. Complete
plans, summaries, structured failures/errors, assigned test IDs, and untruncated
batch logs are written under ignored `build/agent-results/application/`.
Per-test and aggregated per-module timings remain available in
`build/agent-results/application-test-timings.json`. Windows CI pins four core
workers and uploads both evidence locations. The agent-engineering profile
validates routing/contracts and deterministic DSH typecheck/tests/E2E.
Documentation uses `mkdocs build --strict`.

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
