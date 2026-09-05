---
name: modify-application-setting
description: Add, expose, rename, change, or retire a MyGUI application setting and its typed registry, storage migration, runtime effect, tests, and Settings documentation.
---

# Modify Application Setting

Read `.agents/architecture/application-settings.md` and
`.agents/architecture/application-theme.md`. Preserve
`CORE-APPLICATION-SETTINGS` and `CORE-THEME-OWNER`. Appearance keys also
preserve `CORE-FONT-DIAGNOSTICS` and `CORE-MATPLOTLIB-BOUNDARY`. Do not
weaken `CORE-PERSISTENCE-V23` or `CORE-PROJECT-HISTORY`.

This Skill is the only task flow for adding, modifying, renaming, or retiring
an application setting.

## When to use

Use this Skill when the change is an application preference: Appearance,
Workspace, New Figure defaults, Components creation defaults, Axes Components
creation defaults, Export defaults, Integrations actions, or Maintenance
commands, including storage envelope fields, `SettingSpec` contracts,
`SettingEffect`, and Settings Center editors.

Do not use this Skill for:

- Figure/Inspector `PropertySpec` work → `modify-component-property`
- Project schema keys, kinds, or wire shape → `schema-migration`
- Save/open/restore publication → `project-io-change`
- Promotion of QSettings or theme bypass rules →
  `evolve-architecture-rule` (hardening phase, after evidence exists)
- Theme engine internals with no setting-key change → still update
  `application-theme.md`, but do not invent a second preference store

A setting-key change that also needs a new project field is two tasks. Keep
the application setting out of schema v23.

## Procedure

1. Classify the key as persistent, session-only, or immediate command.
   TeX enablement, TeX preamble, and MATLAB connection are session-only and
   must not become persistent keys.
2. Add or update a typed `SettingSpec` (and `SettingsPageSpec` when the page
   set changes): type, default, normalizer, validator, `SettingEffect`, page,
   editor contract, and migration contract. Composite values use closed
   tagged normalizers. Production editors are explicit widgets.
3. If the on-disk envelope shape changes, write a dual-slot migration that
   validates, rolls back, and round-trips. Do not extend inert legacy groups
   (`workspaceLayout`, `figureExport`, `colorLibrary`) with new writers.
4. Wire runtime through `ApplicationSettingsService` / `SettingsSession`.
   Sessions keep a dirty patch plus base revision. Preview `LIVE_REVERSIBLE`
   inside the reversible apply transaction; commit the document only after
   preview succeeds; restore on storage failure.
5. Figure creation, export, and component creation consume
   `NewFigureDefaultsProvider`, `ExportPreferencesPort`, or
   `ComponentDefaultsProvider`. Controllers, domain Services, Canvas helpers,
   `ChartCreationStager`, and `EditorContext` do not receive
   `ApplicationSettingsService`. Components and Axes Components keys are
   `NEXT_USE` inheritable values; they must not change Controller
   `PropertySpec.default` or schema v23. A new Axes Inspector property must
   decide whether it also belongs on the Axes Components creation-defaults
   page. `_inherit_spec()` requires an explicit `page_id`.
6. Color-library keys stay on the color dual-slot port. Reset-all application
   preferences must not delete that library.
7. Update architecture pages in the same change. Update user Settings
   documentation when the Settings Center page exists; never add application
   keys to `docs/component-properties-v23.md`.

Closed `SettingEffect` values are `LIVE_REVERSIBLE`, `NEXT_USE`, and
`RESTART_REQUIRED`. Immediate commands stay out of Apply/OK patches and
require their own confirmation.

## Forbidden

- Editable JSON as a production setting editor
- Writing application preferences into schema v23, Undo/Redo, dirty
  fingerprints, `ComponentState`, or Canvas materialization
- Persisting TeX or MATLAB enablement, preamble, or connection
- Deleting the color library from reset-all application preferences
- Constructing `QSettings()` outside the injected settings backend
- Publishing application font, palette, or bundled QSS outside `ThemeService`
  / `ThemeBindingPort` once that owner exists
- Starting MATLAB, MCR, or TeX from verification

`ARCH-QSETTINGS-BACKEND-BYPASS` and `ARCH-UI-THEME-BYPASS` are promoted
architecture rules. Do not weaken them. QSS color completeness remains a Python
contract test.

## Verification

Fault-inject storage `sync`/status/readback failure, single-slot corruption,
stale session rebase and same-key conflict, runtime apply/rollback/rollback
failure, and color-library write failure (memory and `changed` unchanged).

Checks, with
`E:\PycharmProjects\ven\pyside6_env\Scripts\python.exe`:

- Independent focused check (available now):
  `.agents/checks/verify_application_settings.py`
- Routed `verify_fast --task modify_application_setting` after Integrator
  registers the task, `KNOWN_CHECKS`, and focused modules
- `verify_architecture` when presentation or QSettings call sites change

A required check that is failed, unknown, or not run blocks completion.

Interactive Windows smoke is required when the route declares it. Cover the
affected Settings page plus Cancel/Apply restore. The full 100/125/150/200%
DPI, dual-monitor, OS System-theme, 8/16 pt × three densities, cached window,
native dialog, and missing TeX/MATLAB matrix is the hardening/acceptance
gate; offscreen tests do not claim it.

Appearance or cached Settings-page changes must also pass the mandatory theme
roundtrip acceptance in `.agents/architecture/testing-map.md`, including Figure toolbar glyphs and
hidden page backgrounds after returning to the committed style.
