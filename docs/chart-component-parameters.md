# Chart Component Parameters

Reference for every Inspector control of the chart components. Each parameter lists its control, its effect, and its values or default. Property keys are given in parentheses so each row maps to one persisted or runtime value. Select a component in the Components tree to open its Inspector; changes apply to that component only.

## Component and section map

| Component | Inspector sections |
| --- | --- |
| Line (generic) | Raw X/Y data, Appearance |
| Function Curve | Definition and range, Appearance |
| Plot | Data source, Appearance |
| Scatter | Data source, Color and size mapping, Appearance |
| Fit Curve | Data source, Fit operations, Fit result, Display range, Appearance |
| Interpolation | Data source, Interpolation parameters, Appearance |
| Legend (per Axes) | Title, Typography, Layout, Layout details, Frame, Advanced |
| Axes Palette (per Axes) | Palette (see [Color Picker](color-picker.md)) |

## Shared Data source section

Plot, Scatter, Interpolation, and Fit Curve share the data source controls.

| Parameter | Meaning |
| --- | --- |
| X Data (x_ref) | The source table column for X values. Number and Datetime columns are accepted. |
| Y Data (y_ref) | The source table column for Y values. Number columns are accepted. |
| X expression (preprocess.x_expression) | Element-wise preprocessing formula applied to the X column. Default x. |
| Y expression (preprocess.y_expression) | Element-wise preprocessing formula applied to the Y column. Default y. |

Both expressions read the original aligned X/Y values and follow the row-validity rules in [Data Preprocessing](data-preprocessing.md). Changing a source or expression has role-specific refresh behavior:

- Plot and Scatter refresh automatically; Plot keeps row gaps for incomplete pairs, Scatter filters them.
- Interpolation recomputes automatically using the new source.
- Fit Curve records the pending change and keeps its previous curve and result until Fit is pressed again.

See [Table Data](table-data.md) for the alignment and refresh rules.

## Shared Line Appearance section

Function Curve, Plot, Fit Curve, Interpolation, and the generic Line share one Appearance section.

### Basic

| Parameter | Control | Meaning | Default |
| --- | --- | --- | --- |
| Label (label) | Text | The legend entry text. Empty labels do not create legend entries. | Empty |
| Visible (visible) | Checkbox | Shows or hides the artist. | On |
| Color (color) | Color picker | The line color, normalized to #RRGGBB. | #1f77b4 |
| Line style (linestyle) | Preset / custom editor | The line pattern. Presets are solid, dashed, dashdot, dotted, and none. A custom pattern stores a dash offset and an even-length positive dash sequence. See the [line style reference](https://matplotlib.org/3.9.0/gallery/lines_bars_and_markers/linestyles.html). | solid |
| Line width (linewidth) | Spin box | The line thickness; non-negative. | 1.5 |
| Draw style (drawstyle) | Dropdown | How consecutive points are connected: default (straight segments), steps, steps-pre, steps-mid, or steps-post (staircase variants). See the [step demo](https://matplotlib.org/3.9.0/gallery/lines_bars_and_markers/step_demo.html). | default |
| Gap color (gapcolor) | Optional color | An alternating color shown inside dashed gaps. It has no visible effect on a solid line. | None |

### Marker

| Parameter | Control | Meaning | Default |
| --- | --- | --- | --- |
| Marker (marker) | Marker editor | The marker shape: none, a symbol (o, s, ^, and others), or a regular polygon defined by side count, style, and angle. See the [marker reference](https://matplotlib.org/3.9.0/api/markers_api.html). | none |
| Marker size (markersize) | Spin box | The marker size in points; non-negative. | 6.0 |
| Marker face color (markerfacecolor) | Color picker | The marker fill color. | Follows Color |
| Alternate face color (markerfacecoloralt) | Optional color | A second fill color used by the half-fill styles left, right, bottom, and top. See the [fill style reference](https://matplotlib.org/3.9.0/gallery/lines_bars_and_markers/marker_fillstyle_reference.html). | none |
| Marker edge color (markeredgecolor) | Color picker | The marker outline color. | Follows Color |
| Marker edge width (markeredgewidth) | Spin box | The marker outline width; non-negative. | 1.0 |
| Fill style (fillstyle) | Dropdown | Which part of the marker is filled: full, left, right, bottom, top, or none. See the [fill style reference](https://matplotlib.org/3.9.0/gallery/lines_bars_and_markers/marker_fillstyle_reference.html). | full |
| Mark every (markevery) | Structured editor | Which data points receive a marker: all, stride (start, step), slice (start, stop, step), indices (explicit list), or spacing (start, distance). See the [markevery demo](https://matplotlib.org/3.9.0/gallery/lines_bars_and_markers/markevery_demo.html). | all |

### Advanced

| Parameter | Control | Meaning | Default |
| --- | --- | --- | --- |
| Alpha (alpha) | Spin box | Overall opacity from 0 to 1, or None to inherit. | None |
| Z-order (zorder) | Spin box | Stacking order among artists; higher values draw on top. | 2.0 |
| Dash cap style (dash_capstyle) | Dropdown | The cap shape of dash segments: butt, projecting, or round. See the [cap/join style reference](https://matplotlib.org/3.9.0/gallery/lines_bars_and_markers/joinstyle.html). | butt |
| Dash join style (dash_joinstyle) | Dropdown | The join shape of dash segments: miter, round, or bevel. See the [cap/join style reference](https://matplotlib.org/3.9.0/gallery/lines_bars_and_markers/joinstyle.html). | round |
| Solid cap style (solid_capstyle) | Dropdown | The cap shape of solid segments: butt, projecting, or round. See the [cap/join style reference](https://matplotlib.org/3.9.0/gallery/lines_bars_and_markers/joinstyle.html). | projecting |
| Solid join style (solid_joinstyle) | Dropdown | The join shape of solid segments: miter, round, or bevel. See the [cap/join style reference](https://matplotlib.org/3.9.0/gallery/lines_bars_and_markers/joinstyle.html). | round |
| Antialiased (antialiased) | Checkbox | Renders smooth edges. | On |
| Clip on (clip_on) | Checkbox | Clips the artist to the Axes boundaries. | On |
| GID (gid) | Text | SVG group id used in exports. | None |
| In layout (in_layout) | Checkbox | Includes the artist in tight-layout calculations. | On |
| Rasterized (rasterized) | Checkbox | Renders the artist as a bitmap in vector exports. | Off |
| Sketch params (sketch_params) | Triplet editor | (scale, length, randomness) hand-drawn stroke effect; positive finite values, or None to disable. See [Artist sketch params](https://matplotlib.org/3.9.0/api/artist_api.html#matplotlib.artist.Artist.set_sketch_params). | None |
| Snap (snap) | Dropdown | Pixel-grid alignment: auto (None), on, or off. See [Artist snap](https://matplotlib.org/3.9.0/api/artist_api.html#matplotlib.artist.Artist.set_snap). | None |
| URL (url) | Text | Hyperlink attached to the artist in SVG exports. | None |

## Scatter Appearance section

| Parameter | Control | Meaning | Default |
| --- | --- | --- | --- |
| Label (label) | Text | The legend entry text. Empty labels do not create legend entries. | Empty |
| Visible (visible) | Checkbox | Shows or hides the artist. | On |
| Color (color) | Color picker | The uniform marker face color. It is ignored while a color mapping is enabled. | #1f77b4 |
| Edge color (edgecolor) | Color picker | The uniform marker outline color. | #1f77b4 |
| Marker (marker) | Marker editor | The marker shape; default circle. See the [marker reference](https://matplotlib.org/3.9.0/api/markers_api.html). | o |
| Size (size) | Spin box | The uniform marker size (Matplotlib point-squared scale); non-negative. It is ignored while a size mapping is enabled. | 36.0 |
| Line width (linewidth) | Spin box | The marker outline width; non-negative. | 1.0 |
| Line style (linestyle) | Preset / custom editor | The marker outline pattern. See the [line style reference](https://matplotlib.org/3.9.0/gallery/lines_bars_and_markers/linestyles.html). | none |
| Hatch (hatch) | Text | The marker fill pattern (/, x, and others), or none. See the [hatch style reference](https://matplotlib.org/3.9.0/gallery/shapes_and_collections/hatch_style_reference.html). | None |
| Cap style (capstyle) | Dropdown | The marker outline cap shape: auto (None), butt, projecting, or round. See the [cap/join style reference](https://matplotlib.org/3.9.0/gallery/lines_bars_and_markers/joinstyle.html). | None |
| Join style (joinstyle) | Dropdown | The marker outline join shape: auto (None), miter, round, or bevel. See the [cap/join style reference](https://matplotlib.org/3.9.0/gallery/lines_bars_and_markers/joinstyle.html). | None |

### Scatter advanced

| Parameter | Control | Meaning | Default |
| --- | --- | --- | --- |
| Alpha (alpha) | Spin box | Overall opacity from 0 to 1, or None to inherit. | None |
| Z-order (zorder) | Spin box | Stacking order among artists. | 1.0 |
| Antialiased (antialiased) | Checkbox | Renders smooth edges. | On |
| Clip on (clip_on) | Checkbox | Clips the artist to the Axes boundaries. | On |
| GID (gid) | Text | SVG group id used in exports. | None |
| In layout (in_layout) | Checkbox | Includes the artist in tight-layout calculations. | On |
| Rasterized (rasterized) | Checkbox | Renders the artist as a bitmap in vector exports. | Off |
| Sketch params (sketch_params) | Triplet editor | (scale, length, randomness) hand-drawn stroke effect; positive finite values, or None to disable. See [Artist sketch params](https://matplotlib.org/3.9.0/api/artist_api.html#matplotlib.artist.Artist.set_sketch_params). | None |
| Snap (snap) | Dropdown | Pixel-grid alignment: auto (None), on, or off. See [Artist snap](https://matplotlib.org/3.9.0/api/artist_api.html#matplotlib.artist.Artist.set_snap). | None |
| URL (url) | Text | Hyperlink attached to the whole collection in SVG exports. | None |
| URLs (urls) | String list | Per-point hyperlinks in SVG exports; empty list means none. | Empty |

## Scatter Color and size mapping section

The mapping section maps a data column to per-point colors and sizes. When a mapping is enabled it replaces the uniform Color or Size control for every point.

| Parameter | Control | Meaning | Default |
| --- | --- | --- | --- |
| Color column (color_ref) | Column dropdown | The source column for per-point colors; a Number column. Required while the color mapping is enabled. | None |
| Enable color mapping (color_mapping.enabled) | Checkbox | Activates the per-point color mapping. | Off |
| Colormap (color_mapping.cmap) | Dropdown | The registered Matplotlib colormap used to convert normalized values to colors. See the [colormaps](https://matplotlib.org/3.9.0/users/explain/colors/colormaps.html). | viridis |
| Norm (color_mapping.norm) | Structured dialog | The normalization applied to the column values. Kinds are linear, log, symlog, power, two_slope, centered, boundary, asinh, and none, each with its own parameters plus the common vmin, vmax, and clip bounds. See the [colormap norms](https://matplotlib.org/3.9.0/users/explain/colors/colormapnorms.html). | linear, vmin/vmax auto, clip off |
| Bad color (color_mapping.bad) | Color picker | The color used for non-finite input values when the nonfinite policy is bad. | Transparent |
| Under color (color_mapping.under) | Optional color | The color for values below vmin when clip is on; None extends the colormap ends. | None |
| Over color (color_mapping.over) | Optional color | The color for values above vmax when clip is on; None extends the colormap ends. | None |
| Nonfinite policy (color_mapping.nonfinite) | Dropdown | How non-finite values are handled: drop excludes those points, bad renders them with the bad color. | drop |
| Size column (size_ref) | Column dropdown | The source column for per-point sizes; a Number column. Required while the size mapping is enabled. | None |
| Enable size mapping (size_mapping.enabled) | Checkbox | Activates the per-point size mapping. | Off |
| Input range (size_mapping.input) | Two values, optional | The column value range mapped to the output range; empty means the data minimum and maximum are used. | None |
| Output range (size_mapping.output) | Two values | The marker size range the input range maps onto; non-negative values. | 12.0 to 120.0 |
| Clamp (size_mapping.clamp) | Checkbox | On: values outside the input range map to the output ends. Off: values outside the range are extrapolated linearly. Mapped sizes are never negative. | On |

An enabled mapping without its source column is rejected. In the creation dialog the batch color picker is disabled while the color mapping is checked.

## Function Curve Definition and range section

The expression, X Start/X Stop, and derived sample count are documented in [Function Curve](function-curve.md).

## Fit Curve sections

- Data source: the shared X/Y and preprocessing controls above. Changes keep the previous curve until Fit is pressed again.
- Fit operations: engine (SciPy or Matlab), fit type, and advanced options (fit_options).
- Fit result: the read-only fit statistics and drawing expression (fit_result).
- Display range: the X range used to draw the fitted curve (x_start, x_stop).
- Appearance: the shared Line Appearance section.

Every fit parameter is documented in [Fitting](fitting.md).

## Interpolation parameters section

- Method, Samples, spline order k, and the smoothing-lambda options recompute the curve automatically after each change.

Every interpolation parameter is documented in [Interpolation](interpolation.md).

## Legend parameters

Each Axes has one Legend component. The Legend appears only when entries exist to display.

### Title and Typography

| Parameter | Control | Meaning | Default |
| --- | --- | --- | --- |
| Title (title) | Text | The legend title text. | Empty |
| Label font (label_font) | Font editor | The font of the entry labels: family list, size, weight, style, stretch, variant, and color. | sans-serif 10 |
| Title font (title_font) | Font editor | The font of the title text. | sans-serif 10 |

### Layout

| Parameter | Control | Meaning | Default |
| --- | --- | --- | --- |
| Visible (visible) | Checkbox | Shows or hides the legend. | Off until entries exist |
| Location (location) | Position editor | Where the legend sits: a preset name (best, upper right, upper left, lower left, lower right, right, center left, center right, lower center, upper center, center, and the outside placements outside right upper, outside right lower, outside left upper, outside left lower, outside upper right, outside upper left, outside lower right, outside lower left), a numeric location code 0 through 10, or an explicit (x, y) point in Axes coordinates. See the [legend guide](https://matplotlib.org/3.9.0/users/explain/axes/legend_guide.html). | best |
| Columns (ncols) | Spin box | The number of legend columns; at least 1. | 1 |
| Entry scope (entry_scope) | Dropdown | axes lists only entries belonging to this Axes; twin_pair merges the primary and right-Y entries into the primary legend (used by the Primary + Right Y layout). | axes |

### Layout details

| Parameter | Control | Meaning | Default |
| --- | --- | --- | --- |
| Anchor (bbox_to_anchor) | Structured editor | Pins the legend to a reference point or box: none (location-based), point (x, y), or bounds (x, y, width, height) in Axes coordinates. | none |
| Mode (mode) | Dropdown | none or expand; expand stretches the entries to fill the anchor box. | None |
| Alignment (alignment) | Dropdown | The title alignment relative to the entries: left, center, or right. | center |
| Reverse (reverse) | Checkbox | Reverses the entry order. | Off |
| Marker first (markerfirst) | Checkbox | Draws the handle before the label. | On |
| Draggable (draggable) | Checkbox | Lets the user drag the legend with the mouse. | Off |
| Draggable update (draggable_update) | Dropdown | What dragging updates: loc (the location) or bbox (the anchor box). | loc |
| Points per handle (numpoints) | Spin box | The number of points shown in each Line handle. | 1 |
| Scatter points (scatterpoints) | Spin box | The number of points shown in each Scatter handle. | 1 |
| Scatter offsets (scatteryoffsets) | Number sequence | The y offsets of the scatter points in the handle. | 0.375, 0.5, 0.3125 |
| Marker scale (markerscale) | Spin box | The size multiplier for markers inside the legend. | 1.0 |
| Border pad (borderpad) | Spin box | The padding between the frame and the entries, in font-size units. | 0.4 |
| Label spacing (labelspacing) | Spin box | The vertical spacing between entries, in font-size units. | 0.5 |
| Handle length (handlelength) | Spin box | The length of each entry handle, in font-size units. | 2.0 |
| Handle height (handleheight) | Spin box | The height of each entry handle, in font-size units. | 0.7 |
| Handle-text pad (handletextpad) | Spin box | The spacing between a handle and its label, in font-size units. | 0.8 |
| Border-axes pad (borderaxespad) | Spin box | The padding between the legend and the Axes, in font-size units. | 0.5 |
| Column spacing (columnspacing) | Spin box | The horizontal spacing between columns, in font-size units. | 2.0 |

### Frame

| Parameter | Control | Meaning | Default |
| --- | --- | --- | --- |
| Frame on (frameon) | Checkbox | Draws the frame. | On |
| Face color (facecolor) | Color picker | The frame background color. | #ffffff |
| Edge color (edgecolor) | Color picker | The frame outline color. | #cccccc |
| Frame alpha (framealpha) | Spin box | The frame opacity from 0 to 1, or None. | 0.8 |
| Fancy box (fancybox) | Checkbox | Rounds the frame corners. | On |
| Shadow (shadow) | Checkbox | Draws a drop shadow behind the frame. | Off |
| Frame line width (frame_linewidth) | Spin box | The frame outline width. | 1.0 |
| Frame line style (frame_linestyle) | Pattern editor | The frame outline pattern. | solid |
| Frame hatch (frame_hatch) | Text | The frame fill pattern, or none. See the [hatch style reference](https://matplotlib.org/3.9.0/gallery/shapes_and_collections/hatch_style_reference.html). | None |

### Legend advanced

| Parameter | Control | Meaning | Default |
| --- | --- | --- | --- |
| Z-order (zorder) | Spin box | Stacking order among artists. | 5.0 |
| Alpha (alpha) | Spin box | Overall opacity from 0 to 1, or None to inherit. | None |
| Label (label) | Text | The artist label used for lookups; not a visible legend entry. | Empty |
| Clip on (clip_on), GID (gid), In layout (in_layout), Rasterized (rasterized), Sketch params (sketch_params), Snap (snap), URL (url) | Various | The shared export parameters documented in the Line Appearance Advanced table above. | See that table |

## Axes Palette section

The per-Axes Palette section shows the effective color source and its ordered color strip. See [Color Picker](color-picker.md).

## Matplotlib reference

- [Line2D](https://matplotlib.org/3.9.0/api/_as_gen/matplotlib.lines.Line2D.html): the Line Appearance parameters.
- [PathCollection](https://matplotlib.org/3.9.0/api/collections_api.html#matplotlib.collections.PathCollection): the Scatter parameters.
- [Legend](https://matplotlib.org/3.9.0/api/legend_api.html#matplotlib.legend.Legend): the Legend parameters.
- [Marker reference](https://matplotlib.org/3.9.0/api/markers_api.html): marker symbols.
- [Line style reference](https://matplotlib.org/3.9.0/gallery/lines_bars_and_markers/linestyles.html) and [hatch reference](https://matplotlib.org/3.9.0/gallery/shapes_and_collections/hatch_style_reference.html).
- [Step demo](https://matplotlib.org/3.9.0/gallery/lines_bars_and_markers/step_demo.html) and [cap/join style reference](https://matplotlib.org/3.9.0/gallery/lines_bars_and_markers/joinstyle.html): the Line Appearance drawstyle and dash segment shapes.
- [Marker fill style reference](https://matplotlib.org/3.9.0/gallery/lines_bars_and_markers/marker_fillstyle_reference.html) and [markevery demo](https://matplotlib.org/3.9.0/gallery/lines_bars_and_markers/markevery_demo.html): the Marker options.
- [Colormaps](https://matplotlib.org/3.9.0/users/explain/colors/colormaps.html) and [colormap norms](https://matplotlib.org/3.9.0/users/explain/colors/colormapnorms.html): the Scatter color mapping.
- [Legend guide](https://matplotlib.org/3.9.0/users/explain/axes/legend_guide.html): the Legend location presets, numeric codes, and outside placements.
- [Artist sketch and snap properties](https://matplotlib.org/3.9.0/api/artist_api.html): the Sketch params and Snap settings.
