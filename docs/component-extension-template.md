# Figure Component Extension Template

Use this checklist when adding a Figure component. It preserves the single
mutable state path, lazy Inspector lifecycle, current Figure style, and
schema-v6 project behavior.

## Domain declaration

1. Choose the nearest existing `ComponentKind` and `ComponentRole`. Adding a
   new enum value or persistent field is a separate schema migration task with
   validation, migration, rollback, and save/open tests.
2. Implement the Controller, explicit `DeletionPolicy`, property specs,
   selector/data validation, and Locator strategy. Fixed semantic components
   hide; genuinely removable artists implement reversible removal.
3. Put cross-component, repository, or render-sensitive work in a domain
   Service. Inspector code submits to the Controller or Service and never
   mutates Matplotlib directly.

## Creation

1. Resolve defaults from the current authoritative Figure style and show the
   exposed values in a Controller-free creation input.
2. Reuse the injected `ColorLibrary`. For ordered chart colors, preview with
   `ColorCycleState.peek()` and call `commit()` only after creation succeeds.
3. Create the artist under the same style context, synchronize the Controller
   from that artist, and register it inside
   `ComponentRegistry.registration_transaction()`.
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
- Deletion, data refresh semantics, stable-ID save/open, and schema-v6
  round-trip are covered without persisting Profiles, typed tree keys,
  Section expansion, QWidget state, or callbacks.
