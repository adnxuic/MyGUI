# Multi-Series Chart Creation

Plot, Scatter, and Interpolation creation dialogs can create several editable
chart components in one operation. Select one shared X column and check one or
more Y columns. Each selected Y produces its own Matplotlib artist, stable
Component ID, Controller, Components-tree entry, and Inspector.

## Data selection parameters

- **X Data**: one Number or Datetime column from the current project.
- **Y Data**: a compact multi-select dropdown containing Number columns from
  the current project. Check one or more entries; selected columns are
  processed in their displayed Sheet/column order. Create is disabled while
  none are checked. Inside the open dropdown, Space, Enter, or Return toggles
  the highlighted column without closing the list.
- **X fx**: one safe preprocessing expression copied to every created
  component as its X expression.
- **Y fx**: one safe preprocessing expression evaluated separately for every
  `(X, Y)` pair and copied to each component. Both expression inputs remain
  beside their corresponding data dropdown.

The first available X column is selected when a dialog opens. Y defaults to
the next available Number column (normally the table's second column), with a
fallback to the first Number column when no alternative exists. Repository
structure and metadata updates retain still-valid selections by stable
`ColumnRef`, so renaming or moving a column does not change its identity.

## Chart parameters

- **Plot**: line style, line width, and marker size are shared by all new Plot
  components. Missing or invalid row pairs remain gaps. Unspecified fields
  follow Settings → Components, then Figure style.
- **Scatter**: marker and size are shared by all new Scatter components.
  Missing or invalid row pairs are filtered independently per Y column. An
  optional color column with a colormap and normalization mapping, and an
  optional size column with an input/output size range mapping, can be
  enabled per batch; while the color mapping is checked, the batch color
  picker is disabled. Mapped fields beat Components defaults.
- **Interpolation**: method, Samples, spline order, and smoothing-lambda
  options are shared. Each selected source pair is validated and interpolated
  independently before any component is published. Line appearance follows
  the same Components/style precedence as Plot.
- **Color**: the default or another palette-backed choice is the first color
  in a sequence assigned across the checked Y columns. A one-off custom color
  is applied to every component and does not advance the Axes palette cursor.
- **Label**: each new legend label uses its Y column name. Duplicate selected
  names are qualified as `Sheet/Column`.

After creation, every component can be selected and edited independently in
its existing Inspector, including its data reference, preprocessing, label,
color, and appearance.

## Commit and feedback behavior

The complete selection is validated before chart publication. Creation then
registers all artists, Controllers, Locator bindings, Inspectors, and the final
color-cycle state as one operation. If any selected data pair, interpolation,
registration, or Inspector step fails, no component from the batch remains.

One green Message Bar result reports a clean batch. If preprocessing masks or
filters rows, one yellow result reports the total excluded row-pair count and
the number of affected curves. A failed batch leaves the dialog open and
shows one red result naming the failing Y series.

Each component persists through the existing schema-v23 component tree with
its own `x_ref`, `y_ref`, and `preprocess` data. Dropdown checks and other
creation-dialog state are not written to project files.

Every Inspector control of the created components is documented in
[Plot](editing-components/charts/plot.md) and [Scatter](editing-components/charts/scatter.md).
