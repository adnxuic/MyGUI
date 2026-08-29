# mygui-scanners

Persistent, **non-model-facing** DSH Scanner infrastructure for the MyGUI
repository: a Cordis Scanner Registry service plus the Architecture Scanner
and the Qt Lifecycle Scanner.

> **Scanner plugins are NOT model-facing tools.**
> Nothing in this package registers `ctx.tools` tools, defines model-facing
> tool schemas, or exposes scanners to the LLM in any way (no system prompt,
> no Skill). The architecture is:
>
> ```text
> architecture-scanner
>         |
>         | register
>         v
> myguiScanners (Cordis service)
> ```
>
> A future **dynamic Adapter** — a separate layer that temporarily exposes
> selected registry scanners to an Agent through DSH's tool registry — is
> explicitly out of scope for the scanner implementation and does not live
> here.

---

## 1. What the Scanner Registry is

`myguiScanners` is a Cordis service provided by the `mygui-scanner-registry`
plugin. Scanners are small modules that produce a uniform `ScannerResult`
(see `src/contracts.ts`) for a workspace. The registry owns:

- lifecycle-bound registration (`register()` returns a disposer; scanner
  plugins bind it with `ctx.effect(...)`, so unloading a scanner plugin
  automatically removes the scanner — no stale registrations);
- stable listing / lookup (`list()`, `get()`, `describe()`);
- execution (`run(id, request)`) with strict result-contract validation:
  a scanner that violates the contract fails loudly instead of producing a
  fake success.

The registry plugin itself is a Cordis `Service`, so unloading it removes the
`myguiScanners` service cleanly. No globals, no `node:global` state.

### Public service API

```ts
interface MyguiScannersService {
  register(scanner: ScannerDefinition): () => void; // throws on duplicate id
  list(): ScannerDescriptor[];                      // sorted by id
  get(id: string): ScannerDefinition;               // throws UNKNOWN_SCANNER
  describe(id: string): ScannerDescriptor;          // throws UNKNOWN_SCANNER
  run(id: string, request: ScannerRequest): Promise<ScannerResult>;
}
```

Error codes: `DUPLICATE_SCANNER`, `UNKNOWN_SCANNER`, `INVALID_REQUEST`
(`ScannerRegistryError`); contract violations raise `ScannerContractError`.

## 2. ScannerResult v2 contract

The cross-Harness authority is
`.agents/contracts/scanner-result.schema.json`. Registry, Adapter, Worker and
CLI reject older or malformed results rather than synthesizing missing
fields. A result records `status`, `verdict`, the exact scan `scope`, findings,
gray boundaries, coverage, errors and diagnostics. `unknown` is mandatory
when a failure or incomplete coverage prevents a clean conclusion.

### Finding contract

Every finding is workspace-relative, brief, and fingerprint-stable:

```ts
interface ScannerFinding {
  id: string;            // unique within one result
  scannerId: string;
  ruleId: string;
  severity: 'info' | 'low' | 'medium' | 'high' | 'critical';
  confidence: number;    // [0, 1]
  file: string;          // workspace-relative, never absolute
  line?: number; column?: number;
  title: string; evidence: string; reason: string; // evidence stays short
  suggestedAction: string;
  tags: string[];
  fingerprint: string;   // sha1(ruleId|file|line|normalized evidence)
}
```

No large fix plans are generated inside findings. Gray boundaries use their
own records with classification, location, evidence, a non-violation reason,
and a rule-evolution suggestion; they are never hidden or promoted to
findings without review.

## 3. How to add a new Scanner

1. Create `src/scanners/<name>/scanner.ts` exporting a factory
   `create<Name>Scanner(): ScannerDefinition` (`id`, `version`,
   `description`, `run(request)`).
2. Create `src/scanners/<name>/plugin.ts` — the Cordis plugin entry:

   ```ts
   import type { Context, Plugin } from '@deepseek-ai/cordis';
   import { createArchitectureScanner } from './scanner.ts';

   const plugin: Plugin.Function<object> = (ctx: Context) => {
     const scanner = createArchitectureScanner();
     ctx.effect(() => ctx.myguiScanners.register(scanner));
   };
   plugin.inject = ['myguiScanners'];
   export default plugin;
   ```

3. Add a loader entry to `dsh/scanners.patch.yml`:

   ```yaml
   - insert:
       - id: mygui-scanner-<name>
         name: mygui-scanners/dist/scanners/<name>/plugin.js
   ```

4. Add tests (per-rule positive + negative fixtures under `tests/fixtures/`).

## 4. How a scanner registers

Via the registry's `register()` inside a Cordis lifecycle effect. Because the
scanner plugin declares `inject: ['myguiScanners']`, Cordis loads it only
once the registry service is available and automatically reloads/unloads it
when the service changes — registration and unregistration always follow the
plugin fiber.

## 5. The Architecture Scanner (v0.5.0)

`mygui.architecture` — static, read-only checks derived from the rules in the
repository's `AGENTS.md` (it never modifies the repo, never formats, never
auto-fixes, never launches the GUI):

| Rule | Checks |
| --- | --- |
| `ARCH-PRIVATE-CONTAINER-ACCESS` | accesses to `_figure_stack`, `_inspector_stack`, `_toolboxes`, `_chart_stack`, `_element_stack` from outside the owning container classes (owners computed from `self.<attr> =` assignments, including subclass ownership) |
| `ARCH-UI-ARTIST-MUTATION` | `.set_*(...)` / `.remove()` / `.set_visible(...)` on Matplotlib-artist-like receivers in `mygui/widgets/` outside Controller/Service/Canvas classes; ambiguous receiver types are emitted as gray boundaries |
| `ARCH-UI-MPL-GLOBAL-STATE-MUTATION` | **independent** of the artist rule: UI code in `mygui/widgets/` directly mutating Matplotlib **process-global** mutable configuration — `rcParams[key] = ...` (mutation `assignment`), `rcParams.update({...})` (`update`), `matplotlib.rc(...)` / `mpl.rc(...)` / `rc(...)` (`rc-call`) — with import-alias resolution (`import matplotlib [as mpl]`, `from matplotlib import rcParams/rc`); reads are never reported; `*Controller` / `*Service` / `*Coordinator` / `*Canvas` classes and files outside `mygui/widgets/` (e.g. `mygui/tex_config.py`, the TeX configuration owner) are exempt |
| `ARCH-SECOND-COMPONENT-STATE` | `ComponentState(...)` / `ComponentRegistry(...)` construction and `self.current_component_id = ...` writes in `mygui/widgets/` outside `PyFigureCanvas` |
| `ARCH-CONTROLLER-BYPASS` | UI writes to controller state (`state.properties/data/selector` assignments, `.update()/.setdefault()/.pop()/.clear()` calls, whole-state replacement) instead of routing edits through Controllers/Services |
| `ARCH-QSETTINGS-BACKEND-BYPASS` | `QSettings(...)` construction and QSettings store mutation (`beginGroup`/`endGroup`/`setValue` on a settings store) outside `mygui/application_settings/storage/` |
| `ARCH-UI-THEME-BYPASS` | `QApplication`/`app` `setFont`/`setPalette`/`setStyleSheet` outside `mygui/application_theme/`; widget-local `setFont` is not reported. Bundled QSS hex completeness stays a Python contract test |
| `ARCH-FIGURE-LAYOUT-ENGINE-BYPASS` | references to retired `constrained_layout` proxy outside `exposure_contract.py`, Axes Layout flow calling `set_layout_engine` or assigning `layout_engine` property, or `AxesLayoutService` calling Figure `apply_state()` as a whole |

Severity mapping for `ARCH-UI-MPL-GLOBAL-STATE-MUTATION` (the scanner ladder
has no `warning`/`error`): user `warning` → `medium` (architecture smell,
default), user `error` → `high`. The rule reads the workspace `AGENTS.md` on
every run and escalates `medium` → `high` when it explicitly forbids UI
mutation of Matplotlib global configuration (e.g. "UI must not mutate
Matplotlib global configuration directly", or "Matplotlib configuration
mutation must go through TexConfigService / RenderingService / Controller /
equivalent owner").

The compact root contract intentionally retains that explicit prohibition.
`architecture-rules.test.ts` reads the real root `AGENTS.md` and locks both the
positive escalation and the Artist-only negative case, so instruction
refactors cannot silently change Scanner severity.

Registry metadata: the scanner declares `capabilities` —
`ui_artist_mutation`, `ui_matplotlib_global_state_mutation`,
`matplotlib_rcparams_mutation`, `rendering_configuration_ownership`,
`qsettings_backend_bypass`, `ui_theme_bypass`,
`figure_layout_engine_ownership` — so Worker selection matches tasks like
"rcParams mutation", "Matplotlib global state", "render configuration
ownership", and "layout engine ownership".

Test files (`tests/`, `test_*.py`, `fixtures/`) are excluded from the default
production scan; an explicit `include` pattern re-enables them (findings then
carry the `test-code` tag).

The scanner runs a dependency-free lexical analyzer (see
`src/lib/py/`): strings/comments are blanked before analysis, class/def
scopes are tracked by indentation, and attribute chains are extracted with
one-level local alias resolution. No Python interpreter, no AST framework, no
network, no LLM.

## 5.5 The Qt Lifecycle Scanner (v0.2.0)

`mygui.qt-lifecycle` — static, read-only Qt lifecycle / QObject ownership
checks derived from the Qt patterns actually present in the MyGUI codebase
(never a general Qt style checker, never modifies the repo, never launches
the GUI):

| Rule | Checks |
| --- | --- |
| `QT-TIMER-OWNERSHIP` | `self.<attr> = QTimer()` without a Qt parent (`QTimer(self)` / `QTimer(parent=self)` are fine) and with no `.stop()` / `.deleteLater()` anywhere in the owning class body (repository negative evidence: `context.py` parentless-but-stopped, `common.py` / `py_action_gallery.py` parented) |
| `QT-THREAD-LIFECYCLE` | instance `QThread` that is started somewhere in the class and has no `quit()`/`wait()`/`requestInterruption()`/`terminate()`/`deleteLater()` shutdown vocabulary in the class body (repository evidence: MyGUI uses daemon `threading.Thread` + module bridge with explicit drain/cancel paths; this rule guards future QThread regressions) |
| `QT-SIGNAL-REBIND` | a repeatable method (`sync/update/refresh/rebind/reset/switch/restore/apply/select/setup...`) connects a **new lambda** to a signal while the owning class never calls `.disconnect()` (repository negative evidence: `component_tree.py` always disconnects before reconnecting; `__init__`-time and method-bound connects are never reported) |

`QTimer.singleShot` and `threading.Thread`/`subprocess` are deliberately out
of scope: they are not member lifecycle objects.

## 6. How to test

```bash
npm run setup:host-links   # links @deepseek-ai/cordis from the local dsh install (run once)
npm install                # typescript + @types/node (uses a project-local npm cache)
npm run typecheck          # tsc --noEmit (strict)
npm run test               # build + node --test tests/
npm run scan -- .          # run the architecture scanner on a workspace
```

**Build contract (Phase 3.5):** `src/` is the single source of truth;
`dist/` is a generated artifact produced only by `npm run build`
(`tsc -p tsconfig.build.json`). Never hand-edit or hand-maintain files
under `dist/`. `dist/` is gitignored by repository convention, so a fresh
checkout must run `npm run build` before loading the plugins into a DSH
profile. The repo-local `dsh/scanners.patch.yml` and the deployed
`~/.dsh/profiles/web/cordis.patch.yml` both reference
`mygui-scanners/dist/...` and therefore require a built package.

Unit tests cover: registry lifecycle (register/list/get/run, duplicate and
unknown ids, unload ⇒ unregister, deterministic order, contract
enforcement), per-rule positive/negative fixtures, test-file isolation,
workspace-relative paths, line numbers, fingerprint stability, abort
signals, and the **non-model-facing invariant** (a trap `tools` service whose
`register()` throws + a static source check).

### Phase-2 e2e verifications (real `dsh` boot)

Two extra verification overlays run inside a real `dsh` boot in an isolated
`DSH_HOME` (`.dsh-home/`, gitignored):

```bash
npm run verify:e2e            # phase 1: registry lifecycle (see above)
bash dsh/verify-adapter-e2e.sh
# phase 2a: dynamic Adapter lifecycle — hot plug (tool absent -> mount ->
# present -> run -> unmount -> absent), real scanner execution, failure
# cleanup (scanner throws -> tool still removed), non-persistence.
bash dsh/verify-worker-preset-e2e.sh
# phase 2b: mount-validates the `scanner-worker` agent preset via
# agentPresets.standingKeyFor in an isolated boot (the running session
# cannot do this in-process: tool-cordis Host inspect providers are process
# singletons).
```

See `dsh/adapter-e2e.patch.yml` and `dsh/worker-preset-e2e.patch.yml`.

## 7. Persistent loading through DSH composition

The plugins are **persistent Cordis plugins** (source lives in this
repository, version-controlled), not dynamic in-memory packages. They are
mounted through DSH's Loader via a repo-local patch overlay:

```bash
# 1. Build the package.
npm run build

# 2. Make the package resolvable from the profile's node_modules
#    (the loader imports entry `name` specifiers from the profile dir).
mkdir -p "$DSH_HOME/profiles/<profile>/node_modules"
ln -s /abs/path/to/MyGUI/.dsh/scanners \
      "$DSH_HOME/profiles/<profile>/node_modules/mygui-scanners"

# 3. Boot dsh with the scanner overlay (repeatable --patch).
dsh --profile <profile> \
    --patch .dsh/scanners/dsh/scanners.patch.yml
```

Current DSH version rules (0.1.0-rc.7): the Loader resolves entry `name`
specifiers from its `baseUrl` (the profile directory), so the package must be
exposed there under the bare name `mygui-scanners` (symlink above), and the
entries import the compiled `dist/` modules. To make the mount permanent,
append the same `- insert:` rows to the profile's own `cordis.patch.yml`
(`$DSH_HOME/profiles/<profile>/cordis.patch.yml`); the repo-local overlay is
the version-controlled, machine-independent way to keep it reproducible.

End-to-end verification (real `dsh` boot, isolated `DSH_HOME` under
`.dsh-home/`, then asserts register/list/run/unload and the absence of
model-facing tools, then exits):

```bash
npm run verify:e2e
```

## 8. Layout

```text
src/
  contracts.ts                 # Scanner contracts + errors
  registry/                    # mygui-scanner-registry plugin + service
  scanners/architecture/       # mygui.architecture scanner
  scanners/qt-lifecycle/       # mygui.qt-lifecycle scanner
    scanner.ts  plugin.ts  rules/  (4 rules + shared helpers)
  lib/
    py/                        # dependency-free Python tokenizer + file model
    files.ts  hash.ts          # workspace discovery, fingerprints
  plugins/e2e-exit-plugin.ts   # verification-only plugin (never in production)
  cli/scan.ts                  # standalone scanner CLI
dsh/
  scanners.patch.yml           # repo-local persistent-loading overlay
  e2e-exit.patch.yml           # verification overlay (verify:e2e)
  verify-e2e.sh                # isolated real-dsh boot verification
tests/                         # node:test suite + fixture workspaces
```
