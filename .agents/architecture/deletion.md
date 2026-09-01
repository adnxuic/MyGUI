# Atomic Deletion

`CORE-DELETION-COORDINATOR` requires every production component deletion to
enter through `DeletionCoordinator` with a `DeletionRequest`.

Use this page whenever an operation removes, hides, cascades, or restores a
Figure component or Axes.

Every component makes an explicit deletion decision. Fixed semantic components
hide through visibility and never expose physical delete. Genuinely removable
components declare `DeletionPolicy.REMOVE` and exactly one handler for their
`EditorKey`; handlers declare subtree ownership and leaf handlers reject
Registry children.

All production entry points—Tree single/batch actions, Inspector commands,
Axes deletion, and data-dependency cascades—submit a `DeletionRequest` to
`DeletionCoordinator`. They do not call Registry/Controller physical-delete
primitives directly. Deletion request types, the color-consumption ledger,
and `ComponentDeletionService` are implemented in
`mygui/figuremodify/services/deletion.py` and remain imported through
`mygui.figuremodify.component_services`.

Prepared deletion snapshots Artists, Controllers, Locator bindings, survivor
states, Inspector/container identity and order, tree/schema/live-Axes
validation, palette cursor/ledger, authoritative selection, callbacks, and
pending data state. Failure restores the exact identities and publishes no
intermediate events or success message. Commit publishes one batch lifecycle,
one final refresh/draw, one selection, and at most one Message Bar result.

`ComponentRegistry.delete_transaction()` remains the only Registry deletion
entry. Internally it runs prepare, apply, verify, rollback, and publish on an
ephemeral memento that records object identity, order, Locator bindings, and
compensation diagnostics. Compensation paths record every failed restore;
they do not swallow exceptions with an empty handler. This helper is not a
second deletion or state authority.

Colorbar removal uses `ColorbarRemovalHandle`, not ordinary Artist-list
removal. It pins the Colorbar, auxiliary Axes, Figure Axes ordering, owner Axes
layout/anchor, source callback registry, and source binding. Owner Axes removal
uses `AxesSubtreeRemovalHandle` so external Colorbar auxiliary Axes commit and
roll back with the Axes subtree. Source Scatter cascades are expanded during
deletion planning, before Registry commit.

New removable components require tests for single deletion, same-cohort batch
deletion, dependency cascade, candidate revalidation, selection fallback,
palette restoration, and failures at preparation, physical removal, Inspector
cleanup, verification, and publication stages.
