# Figure Component Extension Template

Use this checklist when adding a Figure component. It preserves the single
mutable state path, lazy Inspector lifecycle, current Figure style, and
schema-v16 project behavior.

## Domain declaration

1. Choose the nearest existing `ComponentKind` and `ComponentRole`. Adding a
   new enum value or persistent field is a separate schema migration task with
   validation, migration, rollback, and save/open tests.
2. Implement the Controller, explicit `DeletionPolicy`, property specs,
   selector/data validation, and Locator strategy in
   `mygui/figuremodify/components/controllers/` and export the type from that
   package. Fixed semantic components hide; genuinely removable artists
   implement reversible removal.
   Declare every property editor with `EditorKind`; use `AUTO` only when the
   value type or choices uniquely determine the control. A composite value must
   declare its dedicated inline or dialog editor kind; `JSON` is reserved for
   tests and never renders a production property.
3. Put cross-component, repository, or render-sensitive work in a domain
   Service under `mygui/figuremodify/services/` and re-export it from
   `mygui.figuremodify.component_services`. Inspector code submits to the
   Controller or Service and never mutates Matplotlib directly.
4. For `REMOVE`, register one exact `DeletionHandler` for the Editor key.
   Compose `ColorCycleDeletionEffect` only for palette-backed components. A
   leaf handler must have no registered children; a composite handler owns
   and tests its complete child-artist removal coverage.
5. For every runtime-created persisted component, declare `RESTORE_PHASE` on
   its Controller and register one exact `ComponentMaterializer` through
   `register_canvas_materializers()` in
   `canvas_materialize_handlers.py`, with a thin `PyFigureCanvas._materialize_*`
   wrapper. The Canvas validates missing, extra, duplicate, non-callable, and
   phase-mismatched declarations before publishing components. Fixed semantic
   components use `RESTORE_PHASE = None`. `ComponentMaterializerRegistry`
   remains the Matplotlib-free declaration table.

## Creation

1. Resolve defaults from the current authoritative Figure style and show the
   exposed values in a Controller-free creation input.
2. Reuse the injected `ColorLibrary`. For ordered chart colors, preview with
   `ColorCycleState.peek()` and call `commit()` only after creation succeeds.
3. Create the artist under the same style context, synchronize the Controller
   from that artist, and register it inside
   `ComponentRegistry.registration_transaction()`. Multi-series Plot, Scatter,
   and Interpolation creation stages through `ChartCreationStager` on the
   Canvas host; public `add_*` methods stay on `PyFigureCanvas`.
4. Preflight the lazy Inspector before transaction commit. Failure removes
   the artist, Controller, Locator binding, cached Inspector, pending updates,
   and any consumed creation cursor without publishing lifecycle events.

## Inspector and tree declaration

Register one exact `EditorProfile` for every supported `EditorKey`:

```python
profile = EditorProfile(
    "example",
    "Example",
    (
        SectionSpec("appearance", "Appearance", appearance_factory),
    ),
    placement=EditorPlacement.ELEMENT,
    tree=TreePresentationSpec(
        "Example",
        group_title="Examples",
        instance_prefix="example",
        preview=lambda state: state.properties.get("label"),
        sort_bucket=40,
    ),
)
editor_registry.register_profile(
    ComponentKind.EXAMPLE,
    profile,
    role=ComponentRole.EXAMPLE,
)
```

Every factory returns a QWidget implementing `EditorSection`. Section keys are
non-empty and unique. `placement` controls Figure, Axes semantic, Chart, or
Element routing; `TreePresentationSpec` supplies all UI-only label, group,
preview, and sort behavior. No tree or container source edit is required.

## Acceptance matrix

- Creation succeeds with current-style defaults and commits one Registry
  lifecycle batch, one final selection, and one refresh.
- Failures at artist creation, registration, Section construction, Stack
  insertion, state synchronization, or render verification restore the exact
  pre-call state and publish no intermediate events.
- First selection creates one Inspector; repeated selection reuses it; direct
  panel/project removal disposes every callback exactly once.
- Empty data remains a valid registered and persisted component where the
  domain permits it.
- Every dynamic Controller key has a parameterized schema-v16 save/open test;
  materializer failure leaves no project tab, artist, Controller, Locator,
  Inspector, listener, selection, or color consumption behind.
- Deletion, data refresh semantics, stable-ID save/open, and schema-v16
  round-trip are covered without persisting Profiles, typed tree keys,
  Section expansion, QWidget state, or callbacks.
- Single and batch deletion cover exact right-click targeting, full cohorts
  under search, same-cohort fallback, one Registry batch/redraw/message, and
  fault injection at artist, survivor state, Locator, Panel, fallback
  Inspector, tree/schema verification, and rollback compensation stages.
