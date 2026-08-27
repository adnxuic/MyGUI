# Axes and Figure Component Parameters

Reference for every Inspector control of the Figure root and the per-Axes semantic components: Figure, Axes, X/Y Axis, Spine, Tick Group, Tick Label Group, and Grid. Each parameter lists its control, its effect, and its values or default. Property keys are given in parentheses. The chart components (Plot, Scatter, curves, Legend) are documented in [Chart Component Parameters](chart-component-parameters.md) and the Axes Palette controls in [Color Picker](color-picker.md).

## Shared Artist export parameters

Every component's Advanced group ends with the same export parameters:

| Parameter | Meaning | Default |
| --- | --- | --- |
| Clip on (clip_on) | Clips the artist to the Axes boundaries. | On |
| GID (gid) | SVG group id used in exports. | None |
| In layout (in_layout) | Includes the artist in tight-layout calculations. | On |
| Rasterized (rasterized) | Renders the artist as a bitmap in vector exports. | Off |
| Sketch params (sketch_params) | (scale, length, randomness) hand-drawn stroke effect; positive finite values, or None to disable. See [Artist sketch params](https://matplotlib.org/3.9.0/api/artist_api.html#matplotlib.artist.Artist.set_sketch_params). | None |
| Snap (snap) | Pixel-grid alignment: auto (None), on, or off. See [Artist snap](https://matplotlib.org/3.9.0/api/artist_api.html#matplotlib.artist.Artist.set_snap). | None |
| URL (url) | Hyperlink attached to the artist in SVG exports. | None |

## Figure

| Parameter | Control | Meaning | Default |
| --- | --- | --- | --- |
| Name (name) | Text | The project name; also updates the project tab and table name. | Project name |
| Style (style) | Text | The Matplotlib style the Figure was created with. Changing it affects only components created afterwards, and reapplies the palette only through the Axes Palette section. | default |
| Size (size_inches) | Size editor | The Figure size in inches (width, height). | 6.4 by 4.8 |
| DPI (dpi) | Number | The document resolution used for exports. | 100 |
| Face color (facecolor) | Color picker | The Figure background color. | #ffffff |
| Edge color (edgecolor) | Color picker | The Figure outline color. | #ffffff |
| Frame on (frameon) | Checkbox | Draws the Figure background patch. | On |
| Line width (linewidth) | Number | The Figure outline width. | 0.0 |
| Alpha (alpha) | Number | The background opacity from 0 to 1, or None to inherit. | None |
| Layout engine (layout_engine) | Structured dialog | The tagged Figure layout: none, tight (pad, w_pad, h_pad, rect), constrained, or compressed (w_pad, h_pad, wspace, hspace, rect). See the [layout engine API](https://matplotlib.org/3.9.0/api/layout_engine_api.html). | none |
| Label (label) | Text | The artist label used for lookups. | Empty |
| Visible (visible) | Checkbox | Shows or hides the Figure. | On |
| Z-order (zorder) | Number | Stacking order. | 0.0 |

Plus the shared export parameters above.

## Axes

### Limits

| Parameter | Control | Meaning | Default |
| --- | --- | --- | --- |
| X limits (xlim) | Range editor | The X data range (min, max). | 0.0 to 1.0 |
| Y limits (ylim) | Range editor | The Y data range (min, max). | 0.0 to 1.0 |
| Autoscale X (autoscalex_on) | Checkbox | Automatically fits the X range to the data. Re-enabling it immediately recalculates the data limits and fits the current data. | On |
| Autoscale Y (autoscaley_on) | Checkbox | Automatically fits the Y range to the data. Re-enabling it immediately recalculates the data limits and fits the current data, then reapplies any lower-Y visual reserve. | On |
| Lower Y reserve (y_lower_reserve) | Number | Extra visual space added below the ordinary autoscale interval, as a fraction of the final Axes height. After each ordinary Y autoscale the interval expands toward the visual bottom in axis-transform space by `S × r / (1-r)`, so autoscale content occupies the upper `1-r` of the Axes. The expansion is not accumulated across repeated autoscales. Manual Y limits are used unchanged while autoscale is off. Ordinary Axes default to `0`; XRD Main Plot + Residual and Single without residual use `0.1`; Single with residual overlay uses `0.0`. | Finite `0 <= r < 0.9`; default `0.0` |

### Appearance

| Parameter | Control | Meaning | Default |
| --- | --- | --- | --- |
| Aspect (aspect) | Aspect editor | The height-to-width ratio of the Axes box: auto, equal, or a positive number. | auto |
| Face color (facecolor) | Color picker | The Axes background color. | #ffffff |
| Visible (visible) | Checkbox | Shows or hides the Axes. | On |
| X margin (xmargin) | Number | The automatic X padding fraction added to each side of the data. When the value is `0`, autoscale X uses the data interval with no locator expansion. XRD Single and Main Plot + Residual set this to `0` so X stays on the imported 2θ range. | 0.05 |
| Y margin (ymargin) | Number | The automatic Y padding fraction added to each side of the data. | 0.05 |
| Adjustable (adjustable) | Dropdown | Which Axes dimension changes to satisfy the aspect: box or datalim. | box |
| Anchor (anchor) | Anchor editor | How the Axes box is anchored when its size differs from the available space (C, SW, S, SE, E, NE, N, NW, W, and combinations). See [Axes.set_anchor](https://matplotlib.org/3.9.0/api/_as_gen/matplotlib.axes.Axes.set_anchor.html). | C |
| Box aspect (box_aspect) | Number | The fixed physical box aspect ratio, or None for automatic. | None |
| Axis below (axisbelow) | Dropdown | Whether ticks and grid lines draw below or above the data: True (below), False (above), or line (grid below, ticks above). | line |
| Frame on (frameon) | Checkbox | Draws the Axes frame (its four spines and background). | On |
| Z-order (zorder) | Number | Stacking order of the Axes patch. | 0.0 |

### Advanced

| Parameter | Control | Meaning | Default |
| --- | --- | --- | --- |
| Rasterization z-order (rasterization_zorder) | Number | Artists below this z-order are rasterized when the Axes is rasterized; None disables the threshold. | None |
| Alpha (alpha) | Number | The Axes patch opacity from 0 to 1, or None. | None |
| Label (label) | Text | The artist label used for lookups. | Empty |

Plus the shared export parameters above.

### Other sections

- Layout: the Edit layout geometry action opens the layout dialog documented in [Axes Layout Templates](axes-layouts.md).
- Palette: the color source and ordered strip (color_cycle) documented in [Color Picker](color-picker.md).

## X Axis and Y Axis

The X Axis and Y Axis components expose the same controls; the Y Axis adds Offset position.

### Properties

| Parameter | Control | Meaning | Default |
| --- | --- | --- | --- |
| Visible (visible) | Checkbox | Shows or hides the axis, its ticks, and its tick labels. | On |
| Scale (scale) | Structured dialog | The coordinate scale: linear, log (base, subs, nonpositive clip or mask), symlog (base, linthresh, linscale, subs), logit (nonpositive, one_half, use_overline), or asinh (linear_width, base, subs). See the [scales explainer](https://matplotlib.org/3.9.0/users/explain/axes/axes_scales.html). | linear |
| Major locator (major_locator) | Structured dialog | Where major ticks are placed: auto, auto_minor (n), max_n (nbins, steps, integer, symmetric, prune, min_n_ticks), multiple (base, offset), linear (numticks), fixed (locations, nbins), log (base, subs, numticks), symlog (transform, subs), asinh, logit (minor, automatic or numeric nbins), or null. See the [ticker API](https://matplotlib.org/3.9.0/api/ticker_api.html). | auto |
| Major formatter (major_formatter) | Structured dialog | How major tick labels are written: scalar (use_offset, use_math_text, use_locale, scientific, powerlimits), engineering, percent, str_method (format using only x and pos), fixed (labels), log, log_exponent, log_mathtext, log_sci, logit, or null. See the [ticker API](https://matplotlib.org/3.9.0/api/ticker_api.html). | scalar |
| Minor locator (minor_locator) | Structured dialog | Where minor ticks are placed; same kinds as the major locator. Enabling a Minor Grid, Tick, or Tick Label while this is null installs and persists the Matplotlib 3.9 default for the current scale. Existing custom locators are retained. | null |
| Minor formatter (minor_formatter) | Structured dialog | How minor tick labels are written; same kinds as the major formatter. | null |
| Label position (label_position) | Dropdown | The side the tick labels occupy: bottom or top for X, left or right for Y. | bottom / left |
| Remove overlapping (remove_overlapping_locs) | Checkbox | Automatically hides overlapping tick labels. | On |
| Offset font (offset_font) | Font editor | The font of the offset notation text (the ×10^3 factor shown in the corner). | sans-serif 10 |
| Offset visible (offset_visible) | Checkbox | Shows or hides the offset notation text. | On |
| Offset position (offset_position, Y only) | Dropdown | Where the Y-axis offset text sits: left or right. | left |

### Advanced

| Parameter | Control | Meaning | Default |
| --- | --- | --- | --- |
| Z-order (zorder) | Number | Stacking order. | 1.5 |
| Alpha (alpha) | Number | Opacity from 0 to 1, or None to inherit. | None |

Plus the shared export parameters above.

## Spine

One Spine component exists per Axes side: Left, Right, Top, and Bottom Spine.

### Properties

| Parameter | Control | Meaning | Default |
| --- | --- | --- | --- |
| Visible (visible) | Checkbox | Shows or hides the spine. | On |
| Color (color) | Color picker | The spine line color. | #000000 |
| Line width (linewidth) | Number | The spine line width. | 0.8 |
| Line style (linestyle) | Pattern editor | The spine line pattern (preset or custom). See the [line style reference](https://matplotlib.org/3.9.0/gallery/lines_bars_and_markers/linestyles.html). | solid |
| Position (position) | Position editor | Where the spine sits: a pair such as outward 0.0, axes 1.0, or data <value>, or the fixed words center or zero. See [Spine.set_position](https://matplotlib.org/3.9.0/api/_as_gen/matplotlib.spines.Spine.html#matplotlib.spines.Spine.set_position). | outward 0.0 |
| Bounds (bounds) | Range editor, optional | Restricts the spine to a (min, max) segment along the other axis; None draws the full side. | None |
| Alpha (alpha) | Number | Opacity from 0 to 1, or None to inherit. | None |
| Cap style (capstyle) | Dropdown | The line cap shape: butt, projecting, or round. See the [cap/join style reference](https://matplotlib.org/3.9.0/gallery/lines_bars_and_markers/joinstyle.html). | projecting |
| Join style (joinstyle) | Dropdown | The line join shape: miter, round, or bevel. See the [cap/join style reference](https://matplotlib.org/3.9.0/gallery/lines_bars_and_markers/joinstyle.html). | miter |

### Advanced

| Parameter | Control | Meaning | Default |
| --- | --- | --- | --- |
| Antialiased (antialiased) | Checkbox | Renders smooth edges. | On |
| Z-order (zorder) | Number | Stacking order. | 2.5 |

Plus the shared export parameters above.

## Tick Group

One Tick Group component exists per axis level: X Major, X Minor, Y Major, and Y Minor Ticks. Each side of an Axes has primary and secondary tick sets.

Enabling either side of a Minor Tick group automatically activates the
scale-appropriate minor locator when the Axis locator is currently null.
Hiding the ticks does not remove or replace that locator.

### Properties

| Parameter | Control | Meaning | Default |
| --- | --- | --- | --- |
| Primary visible (primary_visible) | Checkbox | Shows or hides the ticks on the primary side of the Axes. | On |
| Secondary visible (secondary_visible) | Checkbox | Shows or hides the ticks on the opposite (secondary) side of the Axes. | Off |
| Direction (direction) | Dropdown | Which way the ticks point: in, out, or inout. | out |
| Length (length) | Number | The tick length in points. | 3.5 |
| Width (width) | Number | The tick line width. | 0.8 |
| Color (color) | Color picker | The tick line color. | #000000 |
| Z-order (zorder) | Number | Stacking order. | 2.01 |

### Advanced

| Parameter | Control | Meaning | Default |
| --- | --- | --- | --- |
| Antialiased (antialiased) | Checkbox | Renders smooth edges. | On |

Plus the shared export parameters above.

## Tick Label Group

One Tick Label Group component exists per axis level: X Major, X Minor, Y Major, and Y Minor Tick Labels.

Minor Tick Label visibility uses the same automatic-locator behavior as Minor
Ticks. A configured custom locator remains authoritative.

### Properties

| Parameter | Control | Meaning | Default |
| --- | --- | --- | --- |
| Primary visible (primary_visible) | Checkbox | Shows or hides the labels on the primary side of the Axes. | On |
| Secondary visible (secondary_visible) | Checkbox | Shows or hides the labels on the opposite (secondary) side of the Axes. | Off |
| Color (color) | Color picker | The label text color. | #000000 |
| Font size (fontsize) | Number | The label font size in points. | 10.0 |
| Rotation (rotation) | Number | The label angle in degrees. | 0.0 |
| Font family (fontfamily) | Font dropdown | The primary label font family. Runtime input may use a Matplotlib font-family sequence, but the Controller and schema v17 persist exactly its first family as one non-empty string. See the [fonts explainer](https://matplotlib.org/3.9.0/users/explain/text/fonts.html). | sans-serif |
| Pad (pad) | Number | The distance between the labels and the ticks, in points. | 3.5 |
| Font weight (fontweight) | Named/number editor | The label stroke thickness. | normal |
| Font style (fontstyle) | Dropdown | normal, italic, or oblique. | normal |
| Font stretch (fontstretch) | Named/number editor | Horizontal glyph condensation or expansion. | normal |
| Font variant (fontvariant) | Dropdown | normal or small-caps. | normal |
| Alpha (alpha) | Number | Opacity from 0 to 1, or None to inherit. | None |
| Rotation mode (rotation_mode) | Dropdown | How rotation anchors each label: default, anchor, xtick, or ytick. See [Text.set_rotation_mode](https://matplotlib.org/3.9.0/api/text_api.html#matplotlib.text.Text.set_rotation_mode). | default |
| Horizontal alignment (horizontalalignment) | Dropdown | left, center, or right. | center |
| Vertical alignment (verticalalignment) | Dropdown | top, center, bottom, baseline, or center_baseline. | baseline |
| Multi-line alignment (multialignment) | Dropdown | Alignment inside multi-line labels: None, left, center, or right. | None |
| Wrap (wrap) | Checkbox | Wraps long labels at the Axes width. | Off |
| Line spacing (linespacing) | Number | Vertical spacing multiple between label lines. | 1.2 |
| Math font family (math_fontfamily) | Text | Font for math expressions when math parsing is enabled. See the [mathtext explainer](https://matplotlib.org/3.9.0/users/explain/text/mathtext.html). | dejavusans |
| Parse math (parse_math) | Checkbox | Renders $...$ math with Matplotlib's mathtext engine. | On |
| Use TeX (usetex) | Checkbox | Requests TeX rendering; falls back to ordinary text when TeX is unavailable. See [TeX Rendering Integration](tex-integration.md). | Off |
| Text box (bbox) | Structured editor | Draws a box behind each label when enabled (boxstyle, facecolor, edgecolor, linewidth, line pattern, alpha, fill, hatch, pad). See [FancyBboxPatch](https://matplotlib.org/3.9.0/api/_as_gen/matplotlib.patches.FancyBboxPatch.html) for boxstyle values. | Disabled |
| Z-order (zorder) | Number | Stacking order. | 3.0 |

### Advanced

| Parameter | Control | Meaning | Default |
| --- | --- | --- | --- |
| Antialiased (antialiased) | Checkbox | Renders smooth edges. | On |
| Transform rotates text (transform_rotates_text) | Checkbox | Whether the coordinate transform additionally rotates the labels. | Off |

Plus the shared export parameters above.

## Grid

One Grid component exists per axis level: X Major, X Minor, Y Major, and Y Minor Grid. Its layer is owned by the Axes axisbelow setting.

Enabling a Minor Grid activates and persists the scale-appropriate minor
locator when necessary. X and Y activation are independent, and hiding the
grid does not clear the locator.

### Properties

| Parameter | Control | Meaning | Default |
| --- | --- | --- | --- |
| Visible (visible) | Checkbox | Shows or hides the grid lines. | Off |
| Color (color) | Color picker | The grid line color. | #b0b0b0 |
| Line style (linestyle) | Pattern editor | The grid line pattern (preset or custom). | solid |
| Line width (linewidth) | Number | The grid line width. | 0.8 |
| Alpha (alpha) | Number | Opacity from 0 to 1, or None to inherit. | 1.0 |
| Gap color (gapcolor) | Optional color | An alternating color shown inside dashed gaps. | None |
| Dash cap style (dash_capstyle) | Dropdown | The dash cap shape: butt, projecting, or round. See the [cap/join style reference](https://matplotlib.org/3.9.0/gallery/lines_bars_and_markers/joinstyle.html). | butt |
| Dash join style (dash_joinstyle) | Dropdown | The dash join shape: miter, round, or bevel. See the [cap/join style reference](https://matplotlib.org/3.9.0/gallery/lines_bars_and_markers/joinstyle.html). | round |
| Solid cap style (solid_capstyle) | Dropdown | The solid cap shape: butt, projecting, or round. See the [cap/join style reference](https://matplotlib.org/3.9.0/gallery/lines_bars_and_markers/joinstyle.html). | projecting |
| Solid join style (solid_joinstyle) | Dropdown | The solid join shape: miter, round, or bevel. See the [cap/join style reference](https://matplotlib.org/3.9.0/gallery/lines_bars_and_markers/joinstyle.html). | round |

### Advanced

| Parameter | Control | Meaning | Default |
| --- | --- | --- | --- |
| Antialiased (antialiased) | Checkbox | Renders smooth edges. | On |

Plus the shared export parameters above.

## Title and Axis Labels

Title, X Label, and Y Label are fixed semantic Text components. They share the Inspector sections documented in [Text Element](text-element.md) (Content, Typography, Rotation and alignment, Rendering, Advanced); their Position section omits the coordinate system choice because each role uses its fixed coordinate space. X/Y Label `position` is always interpreted through `Axes.transAxes`: `(0.5, -0.1)` means centered horizontally and one tenth of the Axes height below the Axes, and retains that relative placement after drawing, resizing, and reopening the project.

## Generic Line raw data

The generic Line component exposes Raw X/Y data instead of a table reference: the x and y value arrays the artist draws. It has no creation dialog; its Appearance section is the shared Line Appearance section in [Chart Component Parameters](chart-component-parameters.md).

## Matplotlib reference

- [Figure](https://matplotlib.org/3.9.0/api/_as_gen/matplotlib.figure.Figure.html): the Figure properties.
- [Axes](https://matplotlib.org/3.9.0/api/_as_gen/matplotlib.axes.Axes.html): limits, aspect, margins, and frame properties.
- [Axis](https://matplotlib.org/3.9.0/api/axis_api.html#matplotlib.axis.Axis), [Spine](https://matplotlib.org/3.9.0/api/spines_api.html#matplotlib.spines.Spine), and [Tick](https://matplotlib.org/3.9.0/api/axis_api.html#matplotlib.axis.Tick): the per-Axes semantic artists.
- [Tick locators and formatters](https://matplotlib.org/3.9.0/api/ticker_api.html) and [scales](https://matplotlib.org/3.9.0/api/scale_api.html): the tagged scale, locator, and formatter kinds.
- [Layout engines](https://matplotlib.org/3.9.0/api/layout_engine_api.html): none, tight, constrained, and compressed.
- [Axis ticks and labels](https://matplotlib.org/3.9.0/users/explain/axes/axes_ticks.html): the tick and tick label explainer.
- [Axes.grid](https://matplotlib.org/3.9.0/api/_as_gen/matplotlib.axes.Axes.grid.html): the grid line properties.
- [Axes scales explainer](https://matplotlib.org/3.9.0/users/explain/axes/axes_scales.html) and [Axes.set_anchor](https://matplotlib.org/3.9.0/api/_as_gen/matplotlib.axes.Axes.set_anchor.html): the scale kinds and anchor codes.
- [Line style reference](https://matplotlib.org/3.9.0/gallery/lines_bars_and_markers/linestyles.html) and [cap/join style reference](https://matplotlib.org/3.9.0/gallery/lines_bars_and_markers/joinstyle.html): the line pattern presets and segment shapes.
- [Fonts explainer](https://matplotlib.org/3.9.0/users/explain/text/fonts.html) and [mathtext](https://matplotlib.org/3.9.0/users/explain/text/mathtext.html): the label typography and math font options.
- [FancyBboxPatch](https://matplotlib.org/3.9.0/api/_as_gen/matplotlib.patches.FancyBboxPatch.html): the text-box boxstyle values.
- [Spine.set_position](https://matplotlib.org/3.9.0/api/_as_gen/matplotlib.spines.Spine.html#matplotlib.spines.Spine.set_position): the spine position pair, center, and zero values.
- [Text.set_rotation_mode](https://matplotlib.org/3.9.0/api/text_api.html#matplotlib.text.Text.set_rotation_mode): the tick label rotation anchoring modes.
- [Artist sketch and snap properties](https://matplotlib.org/3.9.0/api/artist_api.html): the Sketch params and Snap settings.
