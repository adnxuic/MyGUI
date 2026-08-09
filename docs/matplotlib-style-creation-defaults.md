# Matplotlib Style Creation Defaults

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

The resolver creates temporary Matplotlib Line, Scatter, Text, child-Axes,
and inset-indicator artists
inside a short `matplotlib.style.context`. Reading the resulting artists
preserves Matplotlib-specific behavior such as Classic scatter size. The
context is closed before Qt displays the dialog.

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

These values use the existing schema-v8 component tree. Opening a project
restores existing components from their concrete properties; style resolution
is used only for components created afterward.
