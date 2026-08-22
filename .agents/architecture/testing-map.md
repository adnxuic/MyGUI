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
empty, failed, or duplicate collections reject the run. Method-level measured
weights feed deterministic LPT micro-batches, and a fixed worker pool runs each
batch under `coverage run --parallel-mode`. Every batch continues after test
failures, while timeout, process, future, and executed-count failures prevent
partial coverage from reaching the coverage thresholds. `coverage combine`
merges only complete batch data. The Matplotlib font cache is warmed serially
before workers start so concurrent rebuilds cannot race.

`MYGUI_TEST_SHARDS` controls concurrent workers and accepts only integers from
1 through 16. The default is `min(8, max(2, cpu_count))`; 1 restores one batch
and one process. Worker counts above 1 use up to four micro-batches per worker
for dynamic load balancing. The one-hour timeout covers the whole parallel test
pool, not each queued batch. Per-batch and per-test timing evidence is written
to ignored `build/agent-results/application-test-timings.json`. Windows CI pins
four workers. The agent-engineering profile validates routing/contracts and
deterministic DSH typecheck/tests/E2E. Documentation uses
`mkdocs build --strict`.

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
