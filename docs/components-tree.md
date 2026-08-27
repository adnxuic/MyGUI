# Components Tree

The Components Explorer is the only navigation entry for Figure Components.
It shares the left Explorer area with the project Table. Select
`Components` on the activity rail to open it; select `Table` to switch pages,
or click the active page button again to collapse the Explorer.

## Using the tree

- Click a Component node to select it and open its exact Inspector; the active Axes follows the Registry ancestry of the selection.
- Type in the search box to filter by label, kind, or role. Clearing the search restores the previous expansion state. A search that hides the selected Component keeps the Canvas and Inspector selection and clears only the tree highlight.
- Right-click a removable Component to Delete it or choose Batch Delete Same Type.... Annotation additionally offers **Duplicate Annotation**; Figure and fixed semantic Components have no delete action.
- After deletion, selection falls back to the next surviving same-cohort Component, the previous survivor, the parent, the nearest surviving ancestor, or the Figure root.

## Tree projection

`ComponentTreeModel` projects the active Canvas `ComponentRegistry`.
Component nodes and their ancestry always come from `ComponentState.parent_id`.
The presentation adds non-selectable, UI-only group nodes:

- every Axes has an `Axes Structure` group for its fixed structural children
  (Left/Right/Top/Bottom Spine, Title, Legend), while `X Axis` and `Y Axis`
  are direct backbone children under the Axes alongside dynamic charts/curves;
- under `X Axis` and `Y Axis`, fixed components (Major Ticks, Minor Ticks,
  Major Grid, Minor Grid, Axis Label) are direct children without extra folders;
- under Major and Minor Ticks, `Tick Labels` appears directly without intermediate
  virtual folders;
- two or more removable siblings with the same `kind` and role are collected
  under a plural role group such as `Function Curves`, `Plots`, `Scatters`,
  `Pseudocolor`, `Heatmaps`, `Contours`,
  or `Texts`;
- every Axes has an always-present `Annotations` group for its persistent
  Annotation children, even when it contains only one Annotation;
- a repeated-role group disappears again when fewer than two matching
  siblings remain.

Members of a repeated-role group receive one-based presentation names such
as `curve1` and `curve2`. When a readable label or content preview exists it
is appended, for example `curve1 — Raw Data`. This numbering is recomputed
from the UI order and is not a persisted component property.

Group nodes use typed `GroupNodeKey` values, while real nodes use
`ComponentNodeKey(component_id)`. They occupy separate Python types and
cannot collide even when a real stable ID begins with the historical
`@ui-group:` text. Typed group keys are used only to restore expansion state
and cannot select an Inspector or open a deletion menu. Component stable IDs
remain the only selection, refresh, Inspector lookup, and deletion targets.

Labels are presentation-only and update from Registry events. Examples
include `Figure — Project`, `Axes 1`, `Left Spine`, `Plot — Raw Data`, and
`Text — note preview`, an Annotation name/text preview, `Reflection Positions — YBCO`, and the shared
`Reference Guides` group containing formula or label previews. A Component
Tooltip lists:

| Field | Source |
| --- | --- |
| ID | `ComponentState.id` |
| Kind | `ComponentState.kind` |
| Role | `ComponentState.role` |
| Parent | `ComponentState.parent_id` |

A group Tooltip identifies it as UI-only and reports its real parent ID.

Sibling order is a UI-only semantic order. Axes use selector index; fixed
Axes semantics are grouped in a predictable editing order; Charts and free
Text preserve `ComponentState.order`. Group membership and sorting are
recomputed from the Registry after project open and never write to the
Registry or project file.

## Search and session state

Search matches Component and group labels, kind, and role without case
sensitivity. Ancestors of every match remain visible; matching a group keeps
its members visible. Clearing search restores the pre-search expansion state.

`PyFigureCanvas.current_component_id` is the only selection authority. The
tree remembers only typed expanded-node keys for the current application
session; it does not keep a second selected ID. Switching project tabs
reflects the Canvas selection and restores expansion.
Reference Line and Reference Band always share one UI-only **Reference Guides**
group under their owner Axes. The group is not a Component and is never saved.

Closing a project releases its Registry and Canvas callbacks and discards its
tree session. Selection, expansion, search text, and Explorer page state are
not part of schema v17.

When a project is first bound, the tree selects the current Axes when one
exists, otherwise the Figure root. Creating an Axes, Chart, free Text,
Reference Marks, Reference Guide, or Annotation component
selects the new Component and opens its exact Inspector, but does not force
the Explorer to change page or become visible.

## Inspector and deletion behavior

Tree selection calls `PyFigureCanvas.select_component(component_id)`.
Registry ancestry determines the active Axes, and the public Inspector
container APIs show exactly one `ComponentInspector` for that stable ID.
An Axes-owned Component selects its Axes ancestor. Selecting a Figure-level
Component does not discard the previously active Axes used by creation
workflows.

Typing a search that hides the current Component leaves the Canvas and
Inspector unchanged and clears only the tree highlight. Clearing the search
reveals and reselects the current Component. If creation or another external
operation selects a Component hidden by the active search, the search is
cleared automatically so the authoritative selection is visible. Search and
model resets never select the first visible row as a side effect.

Right-click actions are determined by the Controller deletion policy:

- Figure and fixed semantic Components have no physical delete action.
- Axes and removable Line, Scatter, FIELD_2D, and free Text Components use the same
  Canvas `DeletionCoordinator` entry.
- Annotation uses that same deletion path. Its profile-declared duplicate
  action calls the Canvas generic duplicate command; the tree does not inspect
  Annotation kind or role.
- `Batch Delete Same Type...` includes only removable siblings with the same
  `parent_id`, kind, role, and `REMOVE` policy. Search changes only what is
  visible; it never narrows this business cohort.

The view sends the typed node hit by the pointer without changing selection.
The Host opens that exact Component Inspector first and suppresses the menu if
selection fails. A single-delete confirmation names the displayed instance and
stable ID and defaults to Cancel. Batch rows use the source model's numbered
instance labels, show stable IDs, start fully selected, and support Select All,
Clear All, and partial selection. Confirmation revalidates the complete cohort;
any missing, moved, or policy-changed candidate rejects the whole request.

After commit, fallback is calculated once from the actual deletion set: keep a
surviving current selection, otherwise choose the next or previous survivor in
the same cohort, then the parent, nearest surviving ancestor, or Figure root.
The Host never overwrites this result. A failed transaction leaves Registry
state, Matplotlib artists and ordering, Locator bindings, Inspector identities,
palette cursors, tree projection, and selection unchanged and shows one red
result. The first release does not support drag reparenting, drag ordering,
inline rename, visibility icons, or canvas highlighting.
