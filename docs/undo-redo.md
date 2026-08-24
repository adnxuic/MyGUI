# Project Undo and Redo

Each open project has one 50-command Undo/Redo timeline shared by its Table and
Figure. Commands are ordered by when they commit, so a Figure edit, a cell
edit, and a component creation are undone in exactly that reverse order. Each
project tab keeps an independent timeline.

## Controls and shortcuts

The Table toolbar and every Figure navigation toolbar provide **Undo** and
**Redo** actions for the active project. Their labels include the next command,
for example **Undo Create Plots** or **Redo Change Line Color**, and they are
disabled when that direction is unavailable.

| Shortcut | Action |
| --- | --- |
| Ctrl+Z | Undo the latest committed project command. |
| Ctrl+Y | Redo the next project command. |
| Ctrl+Shift+Z | Redo the next project command. |

When a `QLineEdit`, multi-line text editor, or Table cell editor still contains
uncommitted typing, its native text Undo/Redo takes priority. After that value
commits, the same shortcuts use project history. Spin-box value changes always
use project history.

Matplotlib **Back** and **Forward** still navigate Matplotlib's canvas-view
stack. A completed Home, Back, Forward, pan, or rectangle-zoom operation also
records the resulting persisted Axes view as one project command, so project
Undo/Redo can restore its limits. The two controls therefore have different
purposes even though a navigation action is itself undoable.

## Figure commands

A single user action creates one command for:

- Figure, Axes, Axis, Spine, Tick, Tick Label, Grid, Text, Legend, Line,
  Scatter, Colorbar, and in-Axes property changes;
- Function expression/range, raw X/Y data, data references and preprocessing,
  Scatter mapping, interpolation settings, Fit results/ranges, TeX rendering,
  inset-image replacement, palettes, and project rename;
- Axes layouts and creation of Function Curve, Plot, Scatter, Fit,
  Interpolation, Text, Zoom/Image in-Axes elements, and Colorbar components;
- individual, batch, and Axes-subtree deletion.
- completed Matplotlib Home, Back, Forward, pan, zoom, and Figure-options
  changes that alter persisted component state.

Multi-series Plot, Scatter, and Interpolation creation is one atomic command.
Undo restores or removes the complete batch, including original stable IDs,
component order, parent relationships, source references, palette cursor,
selection, and runtime-only color/Fit bookkeeping. Repeated changes to the same
mergeable Inspector property are coalesced until a different command begins.
Rejected or no-op edits do not add commands, and making a new edit after Undo
discards the old Redo branch.

Table-driven chart refresh is part of the Table command that caused it. It does
not create extra Figure commands, so deleting a referenced column or Sheet and
its dependent charts still occupies one chronological slot.

## Save, dirty state, and project lifetime

History is runtime-only and is never written to schema-v15 project JSON. Saving
does not clear the current session's timeline. Opening or restoring a project
starts with empty Undo/Redo actions.

Dirty state compares the current typed Table and normalized Figure component
tree with the latest successful load/save fingerprint. Undoing exactly back to
that fingerprint makes the project clean; Redo makes it dirty again. Closing a
project disposes its history observers and removes its stack with the project.

Undo/Redo reuses the same validated Controllers, domain services, component
materializers, and deletion transaction as the original operation. If replay
fails, MyGUI attempts to restore the last proven state and shows one error. It
then clears the uncertain history cursor so the application cannot continue
from a partially trustworthy Redo branch.
