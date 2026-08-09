# Atomic Component Deletion

All physical Figure-component deletion uses the Canvas-owned
`DeletionCoordinator`. Tree single/batch actions, Axes deletion, Inspector
commands, and table-data dependency cascades submit stable IDs through the same
two-phase workflow. Deletion state is runtime-only and does not change schema
v6.

## Runtime values

| Type | Parameter | Meaning |
| --- | --- | --- |
| `DeletionRequest` | `component_ids` | Ordered stable IDs requested as one all-or-none operation; duplicates are removed. |
|  | `anchor_id` | Component used to calculate same-cohort next/previous fallback. |
|  | `reason` | `single`, `batch`, `axes`, `data_dependency`, or `programmatic`. |
| `DeletionPlan` | `requested_ids` | Revalidated request IDs. |
|  | `root_ids` | Minimal roots after parent/child request folding. |
|  | `removed_ids` | Complete child-first deletion closure. |
|  | `state_replacements` | Surviving Axes reindex and palette-cursor states committed with deletion. |
|  | `fallback_id` | Prepared authoritative selection after commit. |
| `DeletionOutcome` | `committed` | Whether Registry and artist deletion crossed the commit boundary. |
|  | `rollback_complete` | Whether every attempted compensation completed. |
|  | `removed_ids` | IDs removed by a committed request. |
|  | `selected_component_id` | Selection published by the coordinator. |
|  | `notices` / `message` | Single user-facing warning or error result. |
| `DeleteCandidate` | `component_id` | Stable ID shown as secondary dialog information. |
|  | `instance_label` | Exact source-tree display label, including group instance numbering. |
|  | `parent_label` | Display label for the shared parent scope. |
|  | `cohort_key` | Runtime `parent + kind + role + REMOVE policy` identity. |

## Commit behavior

Preparation validates the deletion policy and exact `DeletionHandler`, rejects
leaf handlers with registered children, computes the complete closure and
survivor effects, prepares the fallback Inspector, and reversibly detaches Axes
Panels. The Registry stages artist removal, survivor state, Locator unbinding,
the complete Components-tree projection, and a schema-v7 snapshot. Only a
fully valid candidate publishes cleanup, one Registry event batch, one redraw,
the prepared selection, and one Message Bar result.

Palette-backed handler keys compose `ColorCycleDeletionEffect`; palette
release is therefore explicit and does not depend on capability-name
heuristics. Future composite handlers must set subtree ownership and cover all
registered child artists.

Failure restores the same Controllers, artists, Matplotlib container order,
Locator bindings, Inspector identities, callbacks, palette cursor, pending
updates, tree projection, and selection. A compensation error is reported with
`rollback_complete=False`; it is never described as a complete rollback.

## Batch and dependency behavior

Batch candidates always come from the unfiltered source model and must share
the full cohort key. The dialog starts with every item selected, allows any
subset, and revalidates the original cohort immediately before deletion. A
changed candidate rejects the entire request.

Data-dependency snapshots contain both dependent `ComponentState` records and
their parent Axes states. Table mutation runs only after every Canvas deletion
succeeds. A failed Canvas deletion compensates earlier Canvas commits and
returns `False`, so the table command becomes obsolete without changing table
data or its Undo stack. Undo restores stable IDs, data references, and the exact
parent palette cursor.
