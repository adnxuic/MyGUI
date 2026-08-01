# Codex Maintenance Guide

Scope: this file applies to the whole repository.

## Project Basics

- This is a PySide6 + matplotlib desktop GUI for table-driven chart creation and editing.
- Run the app from the repository root with `python main.py`.
- Use the project environment at `E:\PycharmProjects\ven\pyside6_env\Scripts\python.exe` for repository tests, compilation checks, and maintenance scripts. Do not silently substitute another Python installation.
- Resource paths currently depend on root-relative files such as `pictures/icons/...`; do not move assets or change the working-directory assumption without updating all call sites.
- MATLAB and TeX support are optional local integrations. Failures in those paths must not block basic GUI maintenance.

## Working Rules

- Read the relevant components before changing them. Prefer small, local edits over broad rewrites.
- Do not perform large architecture refactors in the same change as a bug fix or maintenance update.
- Keep GUI behavior unchanged unless the task explicitly asks for behavior changes.
- Preserve existing resource names and QSS/JSON file locations unless the task is specifically about resource cleanup.
- Do not delete tracked IDE files, backup files, or sync artifacts as part of unrelated work. Repository hygiene cleanup should be a separate commit.
- Treat `code.database.py_database.databases` as shared global runtime state. Changes around it need focused tests or a clear manual verification path.
- For data-related features, consider whether artifacts connected to that data must refresh when the source data changes.
- Treat user-entered expression evaluation as high risk. Replacing `eval` should be done as a dedicated task.
- When implementing features, consider the Message Bar and State Bar. Prefer surfacing useful user-facing information through the Message Bar, using red for errors, yellow for warnings, and green for successful actions.
- New feature implementations must consider project IO. Ensure feature state can follow the project's save and import workflows when applicable.
- When a feature needs color selection, reuse `ColorChoiceWidget` with the injected application `ColorLibrary`; do not create a separate color menu or eager `QAction` collection. Use `ColorCycleState` only for ordered chart-color sequences, preview with `peek()`, and call `commit()` only after the related operation succeeds.
- Place new code files according to the existing `code/` directory responsibilities: `code/widgets/` is for window and UI components, `code/figuremodify/` is for drawing style modification logic, and `code/database/` is for data processing and data-related helpers. Follow the nearest existing module location before creating a new file.
- Keep handoff notes up to date under `codex_handoff/`. Handoff notes should record only current limitations, not next-step plans.
- After completing a feature, write feature documentation under `docs/`. Keep it to a concise feature description and detailed parameter documentation; do not include limitations or unrelated commentary.

## Component Architecture Rules

- Treat `ComponentRegistry`, `ComponentState`, Controllers, and domain Services as the only mutable business-state path for Figure components. Inspector/UI code must not maintain a second component state model or directly mutate Matplotlib artists; it must submit through the relevant Controller or Service and synchronize from Registry events.
- Build production modification panels with `ComponentInspector` and registered `EditorProfile` objects composed from reusable `EditorSection` implementations. Use `PropertySection` for `PropertySpec`-backed fields and keep `ComponentEditorBase` only as the generic fallback. Do not reintroduce role-specific `Py*ModWidget` classes, monolithic modification panels, `_ChartModWidgetMixin`, or compatibility wrappers around Inspector profiles.
- Reuse `LineAppearanceSection` for all Line roles and `DataReferenceSection` with a role-specific submit strategy. Preserve the established refresh semantics: Plot refreshes automatically, Interpolation recomputes automatically, and Fit records a pending source change until the user explicitly refits.
- Route render-sensitive Text changes through `TextRenderService`, using `apply_many()` for one logical multi-target edit. Keep Legend on `LegendController`/axes commands rather than treating it as a Text component. Fixed semantic components such as Title and axis labels are hidden instead of removed; only genuinely removable components may expose deletion.
- UI synchronization must block recursive signals, roll back the control, Controller state, and artist atomically on failure, and emit at most one Message Bar result for one user action. Sections and editor bindings must detach Registry, repository, TeX, MATLAB, and asynchronous callbacks from `dispose()` or equivalent lifecycle cleanup.
- Creation dialogs may reuse only Controller-free input widgets such as line appearance, data reference, and interpolation option inputs. Accepted dialogs must still create components through the canvas/Controller workflow, and `PyFigureCanvas` must register profiles and ask `ComponentEditorManager` for editors instead of constructing role-specific controls.
- Any newly supported Figure component type must derive all applicable creation defaults from the current authoritative Figure `style`, including line, marker, fill, text, and color-cycle properties. Resolve those defaults through the shared style-creation service, show exposed values in its creation input, create the Matplotlib artist under the same style context, and synchronize the Controller from the new artist before registration. Explicit user choices and an active user-selected Axes palette take precedence; style changes affect only components created afterward unless the user explicitly reapplies a palette or style.
- Persist Figure component state only through the schema-v6 component tree. Profile selection, Section expansion, QWidget state, callbacks, and other UI-only data must never enter `ComponentState` or project files. Any future persisted field or schema change requires a dedicated migration, validation, rollback, and save/open round-trip task; preserve stable component IDs and empty data-backed components.

## Component Tree and Selection Rules

- `PyFigureCanvas.current_component_id` is the only authoritative component selection. The Components tree, search filter, and Inspector synchronize that value and must not maintain a second selected-component model. Tree sessions may retain only UI state such as typed expansion keys.
- Represent projection nodes with `ComponentNodeKey` and `GroupNodeKey`, exposed through `TreeNodeKey` and `NODE_KEY_ROLE`. Keep `COMPONENT_ID_ROLE` exclusively for real component IDs. Never encode UI groups as reserved component-ID strings or persist tree keys in `ComponentState` or schema-v6 files.
- Build a complete candidate projection and validate duplicate keys, missing parents, parent/child relationships, cycles, and reachability before atomically replacing the active model. A failed rebuild must leave the previous usable projection intact.
- Drive labels, grouping, previews, and ordering from the profile's UI-only `TreePresentationSpec`. Do not add component-role presentation branches to the tree or container code.
- Keep tree responsibilities split under `code/widgets/component_tree/`: typed keys, presentation resolution, Model/Filter, View/Host, and deletion dialog code must remain in their corresponding modules instead of growing a new monolithic tree widget.
- Commit and emit a component selection only after its Inspector has been ensured and displayed successfully. On failure, restore the tree highlight, Canvas selection, Inspector visibility/cache, and related UI state together, and emit one red Message Bar result for the user action.
- A user-entered search that hides the current component must keep the Canvas and Inspector selection while clearing only the visible tree highlight. Programmatic or external selection of a filtered component must clear the search, and clearing search must restore the current component highlight.
- Compute post-delete selection from the actual confirmed deletion set: next surviving same-group component, previous survivor, parent, nearest surviving ancestor, then Figure root. “Delete similar components” means the same parent, `ComponentKind`, `ComponentRole`, and deletion policy.

## Inspector Container Rules

- Use responsibility-based names for Inspector layout code: `Host` owns project-level selection, `Panel` owns one Figure/Axes scope, `Stack` switches role-specific toolboxes, `ToolBox` owns visible Inspectors, `Section` edits part of a component, and `Input` is Controller-free dialog input.
- Keep the production hierarchy `FigureInspectorHost` -> `FigureInspectorPanel` -> `AxesInspectorPanel` -> `AxesSemanticInspectorPanel`/Chart and Element stacks. High-level Figure/Axes navigation belongs in `code/widgets/fig_control_window/figure_inspector.py`; reusable Inspector stacks and toolboxes belong in `code/widgets/fig_control_window/component_editors/containers.py`.
- The `all_mod_widgets/` directory is retained only for existing QSS resources. Do not place new Python editor or container implementations there, and do not move its QSS files without updating every explicit resource path.
- Window and Canvas callers must use the public container methods for add, find, show, remove, clear, and toolbox lookup. They must not access `_figure_stack`, `_inspector_stack`, `_toolboxes`, `_chart_stack`, `_element_stack`, or other private Qt layout state.
- `FigureInspectorHost` owns the empty-project offset and project-index mapping. `FigureInspectorPanel` owns Figure elements and Axes selection. `AxesInspectorPanel` routes components from the explicit `EditorProfile.placement`; do not restore role hardcoding or `_is_semantic` classification.
- `ComponentEditorManager.create()` is the only production path for creating visible component editors. Toolboxes provide `add_inspector()` and `remove_inspector()` to Manager lifecycle callbacks; container removal must not bypass `dispose()`.
- Use the exact `EditorKey = (ComponentKind, ComponentRole)` for Profile, toolbox, and Inspector routing. Every production Controller must have one unique Profile with a valid explicit placement, a `TreePresentationSpec`, and non-empty unique `SectionSpec` keys. Validate the complete production registry during Canvas startup so invalid, missing, or duplicate declarations fail before component publication.
- Figure-root Inspectors may be prepared during Figure setup; all other component Inspectors are created on first selection and cached by component. `show_component()` may ensure an Inspector, but lookup-only APIs must not create one as a side effect. `ComponentEditorBase` remains only an explicitly selected generic or test fallback and is never a silent production fallback.
- Resolve Figure and Axes ownership through `ComponentRegistry` ancestry, not Matplotlib artist inspection or private Qt layout state.
- Every Inspector container level must provide idempotent recursive `dispose()`. Release Manager tracking before Section cleanup, isolate individual cleanup exceptions, undo partially constructed Sections in reverse order, and detach Registry, repository, TeX, MATLAB, and asynchronous listeners. Removing or clearing a container must use these public lifecycle paths rather than only `deleteLater()`.
- Treat container renames as atomic repository-wide migrations: update imports, attributes, methods, tests, docs, and handoff notes together, then remove the old names rather than adding aliases or `__getattr__` compatibility paths.
- Historical Canvas names such as `PyFigureCanvas`, `py_figure_canves.py`, `current_canva`, and `canva` remain outside the Inspector container naming scheme. Do not rename them opportunistically as part of unrelated Inspector work; handle them only in a dedicated repository-wide naming task.

## Component Registration and Project Transactions

- Use `ComponentRegistry.registration_transaction()` for component publication. Treat artist creation, Controller/Registry registration, Locator bindings, lazy Inspector insertion, tree lifecycle events, selection, pending refresh state, and color-cycle consumption as one logical operation.
- Publish lifecycle events, redraw, success messages, and selection changes only after the transaction commits. Roll back to the exact pre-call state on failure, including artists, Controllers, Locator entries, cached Inspectors, listeners, pending updates, allocated IDs, and creation-color cursors; do not expose intermediate `ADDED` or `REMOVED` events, and show at most one red error result.
- Create or delete an Axes together with its fixed semantic subtree as one compound transaction. Do not leave a partially registered Axes, semantic Controller, Inspector panel, or ID allocation after failure.
- Use Registry batch event contexts and batch subscriptions for compound operations. Axes creation/deletion, project restore, and other logical batches should cause one tree projection rebuild and one final refresh, while preserving persisted Axes state.
- Stage project creation and restore before publication. Prepare the Canvas, Inspector hierarchy, tree session, project fingerprints, and subscriptions before adding official mappings or tabs. Failures before or after tab insertion must clean up by stable object/project ID rather than scanning tabs or matching display names.

## New Figure Component Checklist

- Prefer an existing `ComponentKind` and `ComponentRole`. Adding a kind, role, or persisted property is a separate schema migration task with validation, rollback, and save/open round-trip coverage.
- Implement `ComponentState`, Controller, explicit deletion policy, property/data validation, Locator binding, and any domain Service first. Fixed semantic components hide; only genuinely removable components expose deletion.
- Resolve all applicable line, marker, fill, text, and color defaults from the current authoritative Figure style. Show exposed defaults in a Controller-free creation input, create the Matplotlib artist under the same style context, and synchronize Controller state from the artist before registration.
- Reuse the injected `ColorLibrary`. For ordered chart colors, call `ColorCycleState.peek()` for the candidate and `commit()` only after the full registration transaction succeeds. Explicit user values and the active Axes palette take precedence.
- Register one exact `EditorProfile` per supported `EditorKey`, with explicit `EditorPlacement`, reusable `EditorSection` factories, unique `SectionSpec` keys, and a complete UI-only `TreePresentationSpec`. A new supported component must not require edits to tree grouping or container dispatch code.
- Route all edits through Controllers or Services. Continue using `TextRenderService.apply_many()` for one logical render-sensitive text edit, keep Legend on `LegendController`/Axes commands, and preserve Plot/Interpolation/Fit data-reference refresh semantics.
- Cover successful creation, empty data where valid, lazy Inspector reuse, deletion, data-source refresh, every failure rollback stage, stable-ID schema-v6 save/open, and the absence of Profile/Section/tree UI state from persisted files. Document the final feature and parameters under `docs/`; keep only current limitations in `codex_handoff/`.

## Component Verification Baseline

- Run the complete suite from the repository root with `E:\PycharmProjects\ven\pyside6_env\Scripts\python.exe -m unittest discover -s tests -v`. Do not replace the project interpreter with a system Python.
- Run `E:\PycharmProjects\ven\pyside6_env\Scripts\python.exe -m compileall -q code tests main.py` and the applicable Qt tests with `QT_QPA_PLATFORM=offscreen` after component-tree, Inspector, transaction, or project-restore changes.
- Add focused tests for typed-key collisions, search/selection synchronization, deletion fallback, profile validation, lazy Inspector identity, idempotent cleanup, Registry batch counts, project publication rollback, and schema-v6 round trips whenever those paths change.
- Fault-injection tests must cover artist creation, Registry registration, Section construction, Stack insertion, state synchronization, and failures on both sides of tab publication. Assert no residual artist, Controller, Locator binding, tree node, listener, color consumption, or selection change.
- Offscreen tests do not replace interactive smoke checks for multi-Figure/multi-Axes navigation, tree search, Chart/Element switching, creation/deletion, save/open, and operation without TeX or MATLAB.
