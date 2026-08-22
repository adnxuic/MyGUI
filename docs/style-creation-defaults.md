# Style Creation Defaults

New chart and free-Text components derive their initial appearance from the
current Figure `style`. The defaults are resolved when the creation dialog is
opened, so changing the Figure style affects later components without
rewriting existing artists.

## Resolved parameters

| Component | Creation defaults |
| --- | --- |
| Curve | line style, implicit line width/marker settings, chart color |
| Plot | line style, line width, marker size, chart color |
| Scatter | marker, floating-point size, implicit edge/line width, chart color |
| Fit | implicit line style, line width/marker settings, chart color |
| Interpolation | implicit line style, line width/marker settings, chart color |
| Text | font family, font size, implicit text color/weight/style |
| In-Axes | child-Axes background/border, indicator line, image interpolation |
| Reference Marks | X major-tick color and tick-line width; does not consume the chart color sequence |

The resolver creates temporary Matplotlib Line, Scatter, Text, child-Axes,
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
| Width / Height | The Figure size in inches. | 6.4 by 4.8 |
| DPI | The document resolution used for exports. | 100 |
| Figure name | The project name; non-empty and unique among open projects. | The style name |

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
- In-Axes Components store their resolved background, frame, indicator, and
  display properties without consuming the Axes chart-color cursor.
- Reference Marks stores its resolved tick-derived color and line width and
  does not consume the Axes chart-color cursor.

These values use the existing schema-v12 component tree. Opening a project
restores existing components from their concrete properties; style resolution
is used only for components created afterward.

## Matplotlib reference

- [Style sheets reference](https://matplotlib.org/3.9.0/gallery/style_sheets/style_sheets_reference.html): the available styles.
- [Customizing Matplotlib](https://matplotlib.org/3.9.0/users/explain/customizing.html): the rcParams each style sets.
- [Color cycles](https://matplotlib.org/3.9.0/users/explain/artists/color_cycle.html): the axes.prop_cycle defaults behind chart colors.
