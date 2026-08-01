# Components Tree

The Components Explorer is the only navigation entry for Figure Components.
It shares the left Explorer area with the project Table. Select
`Components` on the activity rail to open it; select `Table` to switch pages,
or click the active page button again to collapse the Explorer.

## Tree projection

`ComponentTreeModel` projects the active Canvas `ComponentRegistry`.
Component nodes and their ancestry always come from `ComponentState.parent_id`.
The presentation adds non-selectable, UI-only group nodes:

- every Axes has an `Axes Components` group for its fixed direct children,
  including X/Y Axis, Spines, Title, and Legend;
- two or more removable siblings with the same `kind` and role are collected
  under a plural role group such as `Function Curves`, `Plots`, `Scatters`,
  or `Texts`;
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
`Text — note preview`. A Component Tooltip lists:

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
Closing a project releases its Registry and Canvas callbacks and discards its
tree session. Selection, expansion, search text, and Explorer page state are
not part of schema v6.

When a project is first bound, the tree selects the current Axes when one
exists, otherwise the Figure root. Creating an Axes, Chart, or free Text
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
- Axes use the confirmation flow and `AxesCommandService`.
- removable Line, Scatter, and free Text Components use
  `ComponentDeletionService`.
- `Batch Delete Same Type...` includes only removable siblings with the same
  `parent_id`, kind, and role.

After confirmation, fallback is calculated from the actual deletion set and
moves to the next surviving sibling, previous sibling, nearest surviving
ancestor, or Figure root. A failed transaction leaves Registry state, Matplotlib
artists, Inspectors, and selection unchanged. The first release does not
support drag reparenting, drag ordering, inline rename, visibility icons, or
canvas highlighting.
