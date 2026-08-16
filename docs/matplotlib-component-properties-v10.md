# Matplotlib 3.9 component properties (schema v10)

MyGUI targets Matplotlib 3.9.0. Every production `(ComponentKind,
ComponentRole)` has one Controller and one exact Inspector profile. Persistent
properties are edited only through Controllers or domain Services, and every
property/data key is exposed once or explicitly hidden by its profile.

At startup, the static Matplotlib exposure contract compares the public
setters reported by `matplotlib.artist.ArtistInspector` with the project's
`core`, `advanced`, `alias`, `derived/owned_elsewhere`, and
`unsupported(reason)` classifications. This is a version-drift guard, not an
automatic widget generator.

## Property ownership

| Component | Core property groups |
| --- | --- |
| Figure | name/style, size/DPI, face/edge/frame, linewidth/alpha, tagged layout engine |
| Axes | ordered limits and autoscale, aspect/box aspect, margins, adjustable/anchor, axis-below/frame/visibility, palette, rasterization and layout/export fields |
| X/Y Axis | one tagged scale, major/minor locator and formatter, label/offset placement, offset text style, overlapping-location policy |
| Spine | visibility, color/width, tagged line pattern, position/bounds, alpha, cap/join/antialias, z-order and export fields |
| Tick Group | primary/secondary side visibility, direction, length/width/color, z-order, antialias and export fields |
| Tick Label Group | primary/secondary side visibility, the sole `pad`, complete safe text typography/alignment/render/export fields |
| Grid | visibility, color/width/alpha, tagged line pattern, gap color, cap/join/antialias and export fields; layering is owned by Axes `axisbelow` |
| Text | content/position, safe typography, alignment/rotation, bbox/wrap/line spacing, math/TeX flags, coordinate system for Free Text, z-order and export fields |
| Legend | tagged location/anchor, columns/layout/entry scope, entry/title fonts, marker/point settings, padding/spacing, frame appearance, dragging, z-order and export fields |
| Line roles | label/visibility/color, tagged line/marker/markevery, width/drawstyle/gap color, marker fill/alternate face, cap/join/antialias, z-order and export fields |
| Scatter | uniform face/edge appearance, tagged marker/line pattern, optional color/size column mappings, hatch/cap/join/antialias, z-order and export fields |
| Zoom Inset | child-Axes bounds/limits/style plus region fill/hatch/tagged line pattern and four tagged connector records |
| Image Inset | child-Axes style plus all Matplotlib 3.9 interpolation values, origin/nullable extent, resampling/filter settings, stage, image visibility/z-order and export fields |

There is one authority for each overlapping Matplotlib state:

- X/Y Axis owns `ScaleSpec`; Axes does not persist a second scale.
- Ordered Axes `xlim`/`ylim` own inversion; an inversion control is only a
  proxy that reverses those limits.
- Tick and Tick Label groups own their respective primary/secondary side
  visibility; Axis does not persist `ticks_position`.
- Tick Label Group alone owns `pad`.
- X Axis label position accepts `bottom/top`; Y Axis accepts `left/right`.
- Axes `axisbelow` owns effective grid layering.

Generic Line stores finite, equal-length `x` and `y` arrays and exposes them
through `RawXYDataSection`. Empty arrays are valid. Plot, Interpolation, and
Fit continue to use the shared `TableRepository` with automatic refresh,
automatic recomputation, and explicit refit semantics respectively.

## Tagged values

Tagged objects are the persisted shape only. They reject unknown keys,
non-finite numbers, and invalid kind/parameter combinations, and every
Inspector control always writes the complete object.

Each composite property has a dedicated control instead of a JSON text field:

- Inline controls: `line_pattern` (preset list plus dash offset and on/off
  lengths), `marker_spec` (named or numbered symbol plus regular-polygon
  fields), `optional_color` (`Set` checkbox with `ColorChoiceWidget`),
  `named_number` (keyword or number for font weight and stretch),
  `legend_anchor` (none/point/bounds), `axes_anchor` (compass code or point),
  `number_sequence` (comma-separated numbers), `string_list` (one value per
  line), and `position`/`size`/`range`/`triplet`/`rectangle` numeric groups
  with an optional `Set` checkbox.
- Summary plus `Configure…` dialogs: `scale_spec`, `locator_spec`,
  `formatter_spec`, `font_spec`, `layout_spec`, `markevery`, `text_box`,
  `scatter_color_map` (with a nested normalization dialog),
  `scatter_size_map`, and `connectors`.

An unset optional color is persisted as `null` where the property allows it
and as the string `"none"` for Line `markerfacecoloralt`. Sketch parameters and
Image `extent` are `null` or a complete numeric group.

### Layout and scale

```json
{"kind":"tight","params":{"pad":1.08,"w_pad":null,"h_pad":null,"rect":null}}
```

`FigureLayoutSpec.kind` is `none`, `tight`, `constrained`, or `compressed`.
Tight layout uses `pad`, `w_pad`, `h_pad`, and nullable four-value `rect`.
Constrained/compressed use `w_pad`, `h_pad`, `wspace`, `hspace`, and nullable
`rect`.

```json
{"kind":"log","params":{"base":10.0,"subs":null,"nonpositive":"clip"}}
```

`ScaleSpec` supports:

- `linear` with no parameters;
- `log(base, subs, nonpositive)`;
- `symlog(base, linthresh, linscale, subs)`;
- `logit(nonpositive, one_half, use_overline)`;
- `asinh(linear_width, base, subs)`.

Scale is applied before locator and formatter restoration. Shared axes update
atomically.

### Tickers

`LocatorSpec` has `{"kind": ..., "params": {...}}` and supports `auto`,
`auto_minor`, `max_n`, `multiple`, `linear`, `fixed`, `log`, `symlog`,
`asinh`, `logit`, and `null`.

`FormatterSpec` uses the same outer shape and supports `scalar`,
`engineering`, `percent`, restricted `str_method`, `fixed`, `log`,
`log_exponent`, `log_mathtext`, `log_sci`, `logit`, and `null`. A fixed
formatter is valid only with a fixed locator containing the same number of
locations. `FuncFormatter` and arbitrary callable formatters are never
deserialized.

### Lines and markers

```json
{"kind":"custom","offset":0.0,"dashes":[6.0,2.0,1.0,2.0]}
```

`LinePatternSpec` is a preset (`-`, `--`, `-.`, `:`, `None`) or an even,
positive finite dash sequence with a finite offset.

`MarkerSpec` is `{"kind":"symbol","value":"o"}` (named or numbered
Matplotlib marker) or `regular_polygon(sides, style, angle)`.

`MarkEverySpec` supports `all`, positive `stride`, `slice`, explicit integer
`indices`, and display-distance `spacing`.

### Text and legend

`FontSpec` contains `family`, `size`, `weight`, `style`, `stretch`, `variant`,
and `color`. `TextBoxSpec` is `{"enabled":false}` or a complete enabled
record containing box style, colors, linewidth, tagged line pattern, alpha,
fill, hatch, and pad.

Legend location is either a named/code preset or an Axes-coordinate point:

```json
{"kind":"preset","value":"upper right"}
{"kind":"point","x":0.25,"y":0.75}
```

Legend anchor is `none`, a point, or four-value bounds. Constructor-sensitive
Legend edits are rebuilt by the Legend/Axes service; failure restores the old
artist, Locator binding, Controller state, and visibility.

### Scatter mappings

`ScatterColorMapSpec` contains `enabled`, colormap name, tagged `NormSpec`,
bad/under/over colors, and `nonfinite` (`drop` or `bad`). `NormSpec` supports
linear, log, symlog, power, two-slope, centered, boundary, asinh, and no-norm;
callable `FuncNorm` is excluded.

`ScatterSizeMapSpec` contains `enabled`, a nullable input range, a two-value
non-negative output range in points², and `clamp`.

Color and size columns are optional `color_ref`/`size_ref` records in Scatter
data. X/Y, color, and size resolve from one TableRepository snapshot and the
same original-row mask. Invalid X/Y and size rows are dropped. Invalid color
rows are dropped or rendered with the colormap bad color. Empty output keeps
the component. Enabling color mapping does not advance the Axes palette; the
saved uniform face color is restored when mapping is disabled.

### Insets

Each Zoom connector has `visible`, `color`, tagged `line_pattern`, `linewidth`,
`alpha`, and `zorder`. The service normalizes Matplotlib 3.9's
`(Rectangle, connectors)` return value and mirrors Line/Scatter content
without persisting a second scale.

Image Inset supports `none`, `auto`, `antialiased`, `nearest`, `bilinear`,
`bicubic`, `spline16`, `spline36`, `hanning`, `hamming`, `hermite`, `kaiser`, `blackman`,
`quadric`, `catrom`, `gaussian`, `bessel`, `mitchell`, `sinc`, and `lanczos`.
RGB(A) embedded images do not expose ineffective scalar cmap/norm/clim fields.

## Core, advanced, style, and transactions

Inspector profiles group frequent controls under Core and keep safe export or
render details in collapsed Advanced sections. Colors use the injected
`ColorChoiceWidget` and application `ColorLibrary`, including the color fields
inside the optional-color, font, text-box, connector, and Scatter color-mapping
controls.

Creation precedence is: explicit input, active Axes palette, then Figure
style. Artists are created inside the same Matplotlib style context and the
Controller is synchronized from the created artist before publication. A
palette cursor commits only after the complete registration transaction
succeeds. Style changes affect future components only.

Scale/ticker/side changes, Text rendering, Legend reconstruction, Scatter
mapping, and Inset updates are Controller/Service transactions. Validation,
setter, render, redraw, or materialization failures restore persistent and
runtime state before publishing events or a Message Bar result.

## Persistence

Schema v10 retains the eight-field `ComponentState` record, stable IDs,
hierarchy, and empty data-backed components. Files must contain the exact
persistent property set declared by the role's Controller; missing and
unknown keys are rejected before Table/Figure publication. Composite values
must already use their tagged object shape.

Only exact integer schema version `10` is accepted. Saving writes v10. Schema
v4-v9, booleans/floats/strings that resemble `10`, and unknown versions are
rejected; this release intentionally provides no in-process v9 migration.
Inspector profiles, section expansion, tree session keys, QWidget state, and
callbacks are never serialized.
