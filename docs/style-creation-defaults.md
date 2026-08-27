# Style Creation Defaults

New chart, free-Text, Annotation, and ordinary Axes components resolve their initial
appearance when the creation dialog opens. Changing Figure style, Settings →
Components, or Settings → Axes Components after that open does not rewrite
the open dialog or existing artists.

Creation appearance is not the same as a raw Matplotlib style probe.
Precedence is:

1. Explicit values in this creation (dialog, layout request, or XRD rule)
2. Settings → Components or Axes Components override (`NEXT_USE`; see [Application Settings](settings.md))
3. Current Axes palette for Line/Scatter color, or current Figure `style` for other fields
4. Matplotlib 3.9 built-in fallbacks

Inherit Line/Scatter color still uses the Axes palette cursor, not the first
color from a style probe. Restore, Undo/Redo, and project open use persisted
schema-v17 properties and do not read Components or Axes Components settings.

## Resolved parameters

| Component | Creation defaults |
| --- | --- |
| Curve | line style, line width, marker, marker size, marker edge width, chart color |
| Plot | line style, line width, marker, marker size, marker edge width, chart color |
| Scatter | marker, size, line width, chart color; mapped/XRD explicit fields still win |
| Fit | line style, line width, marker, marker size, marker edge width, chart color |
| Interpolation | line style, line width, marker, marker size, marker edge width, chart color |
| Text | font family, font size, color, weight, and style (free Text only) |
| Annotation | Text font family, size, color, weight, and style; arrow color follows text color and arrow width follows Line width; does not consume the chart color sequence |
| Ordinary Axes | facecolor, frameon, axisbelow, four spines, X/Y major/minor ticks, tick labels, and grid |
| In-Axes | child-Axes background/border, indicator line, image interpolation |
| Reference Marks | X major-tick color and tick-line width; does not consume the chart color sequence |
| Reference Line | Reference Marks color and tick-line width; does not consume the chart color sequence |
| Reference Band | Reference Marks color for its face and edge plus tick-line width; does not consume the chart color sequence |

Settings → Components does not cover Annotation, In-Axes, Reference Marks/Line/Band,
Colorbar, Title, or axis labels. Settings → Axes Components covers later
ordinary Axes (main, shared, right Y, and XRD layout Axes) only. It does not
cover Colorbar auxiliary Axes, In-Axes, restore, or history replay. Title,
Axis Label, Legend, limits, scale, locator, formatter, aspect, and margins
are not stored as Axes Components defaults. A later Axes Inspector property
must decide whether it also belongs on that creation-defaults page.

The style resolver creates temporary Matplotlib Line, Scatter, Text, child-Axes,
and inset-indicator artists
inside a short `matplotlib.style.context`. Reading the resulting artists
preserves Matplotlib-specific behavior such as Classic scatter size. The
context is closed before Qt displays the dialog.

All process-global style contexts and Matplotlib style, colormap, marker, and
font catalogs pass through one application adapter. Creation dialogs consume
immutable catalog snapshots and do not import Matplotlib or retain live
artists. The Canvas remains the Matplotlib/Qt creation boundary.

## Available styles

The Style gallery offers these Matplotlib styles:

`default`, `classic`, `seaborn-v0_8`, `ggplot`, `grayscale`,
`dark_background`, `tableau-colorblind10`, `Solarize_Light2`,
`_classic_test_patch`, `_mpl-gallery`, `_mpl-gallery-nogrid`, `bmh`, `fast`,
`fivethirtyeight`, `seaborn-v0_8-bright`, `seaborn-v0_8-colorblind`,
`seaborn-v0_8-dark`, `seaborn-v0_8-dark-palette`, `seaborn-v0_8-darkgrid`,
`seaborn-v0_8-deep`, `seaborn-v0_8-muted`, `seaborn-v0_8-notebook`,
`seaborn-v0_8-paper`, `seaborn-v0_8-pastel`, `seaborn-v0_8-poster`,
`seaborn-v0_8-talk`, `seaborn-v0_8-ticks`, `seaborn-v0_8-white`,
`seaborn-v0_8-whitegrid`.

## Project creation

Selecting a style in the gallery opens the Style dialog, which creates a new project (Figure tab, table project with a Sheet1 sheet, and its own Figure Inspector):

| Parameter | Meaning | Default |
| --- | --- | --- |
| Width / Height | The Figure size in inches. | Application New Figure defaults (fresh install: 6.4 by 4.8). An explicit value in this dialog wins. Opening a project keeps the schema v17 size. |
| DPI | The document resolution used for exports. | Application New Figure defaults (fresh install: 100). An explicit value in this dialog wins. Opening a project keeps the schema v17 DPI. |
| Figure name | The project name; non-empty and unique among open projects. | The style name |

UI theme is not Matplotlib Figure style. Settings Appearance (theme, UI font
size, density) changes application chrome only. It does not change the
Figure `style` list above, `axes.prop_cycle`, or export appearance. See
[Application Settings](settings.md).

## Chart color sequence

`axes.prop_cycle` supplies the default ordered colors for each Axes. Dialogs
preview the next color without changing project state. A successful chart
creation commits the preview; cancellation or validation failure does not.

An explicitly selected application or custom Axes palette takes precedence
over the Figure style colors. A one-operation custom color leaves the current
palette cursor unchanged. Separate Axes retain independent cursors.

The Axes Inspector Palette section displays this effective source and its
ordered colors. Selecting `Style default` reapplies the current Figure
style's palette to existing chart components and subsequent creation.
Selecting `User-selected` chooses and applies a named built-in or custom
palette. A Figure style change alone does not recolor existing components.

## Project parameters

- Figure `properties.style` stores the selected Matplotlib style.
- Axes `properties.color_cycle` stores the active palette snapshot and
  `next_index` after the first successful palette-backed creation.
- Line, Scatter, and Text components store their resolved concrete visual
  properties.
- Annotation stores its resolved Text/Line-derived appearance without reading
  Components Settings and without changing the Axes chart-color cursor.
- In-Axes Components store their resolved background, frame, indicator, and
  display properties without consuming the Axes chart-color cursor.
- Reference Marks stores its resolved tick-derived color and line width and
  does not consume the Axes chart-color cursor.
- Reference Lines and Reference Bands reuse those resolved Reference Marks
  defaults and do not consume the Axes chart-color cursor.

These values use the existing schema-v17 component tree. Opening a project
restores existing components from their concrete properties; style resolution
is used only for components created afterward.

## Matplotlib reference

- [Style sheets reference](https://matplotlib.org/3.9.0/gallery/style_sheets/style_sheets_reference.html): the available styles.
- [Customizing Matplotlib](https://matplotlib.org/3.9.0/users/explain/customizing.html): the rcParams each style sets.
- [Color cycles](https://matplotlib.org/3.9.0/users/explain/artists/color_cycle.html): the axes.prop_cycle defaults behind chart colors.
