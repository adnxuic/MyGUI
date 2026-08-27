# Function Curve

The Curve action on the Chart command bar creates a function curve component. A function curve is a Line drawn by evaluating a mathematical expression of one variable x over a fixed x range. Expressions are evaluated through the restricted safe-expression interpreter described in [Resource and Process Limits](resource-limits.md); no Python eval is used.

## Creation parameters

| Parameter | Control | Meaning | Default |
| --- | --- | --- | --- |
| Function expression | Text field | The expression of x to evaluate. It must be non-empty and valid; it is checked when OK is pressed. The legend label follows this text automatically while typing. | x |
| X range | Two spin boxes (start, stop) | The finite endpoints of the evaluation range. The curve is evaluated on 1000 evenly spaced points between them. | 0 to 100 |
| Line style | Preset / custom pattern editor | The line pattern: solid, dashed, dashdot, dotted, none, or a custom dash sequence. The initial value follows Settings → Components, then the current Figure style. See the [line style reference](https://matplotlib.org/3.9.0/gallery/lines_bars_and_markers/linestyles.html). | Style or Components default |
| Color | Color picker | The line color. Inherit uses the next Axes palette color; a Components override is a custom color and does not advance the palette. The cursor advances only after a palette-backed creation succeeds. | Palette, Components override, or explicit color |
| Legend label | Text field | The legend entry text. Empty labels do not appear in the legend. | Follows the expression text |

## Creation workflow

- A project with a Figure must exist, and an Axes must be selected; otherwise the dialog refuses with a warning.
- The initial line style, width, marker, and color follow explicit dialog input, then Settings → Components, then the Axes palette (color) or Figure style (other fields). Changing Figure style or Components defaults after the dialog opens does not rewrite this dialog. See [Style Creation Defaults](style-creation-defaults.md).
- Creation publishes the artist, Controller, Components-tree node, Inspector, and the palette color cursor as one registration transaction. A failed creation leaves nothing behind and reports one red Message Bar result.

## Inspector sections

Select the curve in the Components tree to open its Inspector.

### Definition and range

| Parameter | Meaning |
| --- | --- |
| Expression | The expression of x to evaluate, edited with the same safe-expression validation. A rejected edit rolls back and shows one red Message Bar result. |
| X Start / X Stop | The finite endpoints of the evaluation range. Changing them re-evaluates the curve while keeping the current sample count. |
| Samples (samples, derived) | The number of points used to draw the curve. New curves use 1000 points; updating the expression or range keeps the existing count. This value is derived and not directly editable. |

### Appearance

The shared Line Appearance section. Every parameter is documented in [Function Curve](editing-components/charts/function-curve.md).

## Persistence

A function curve stores expression, x_start, and x_stop in its component data and its visual properties in the schema-v17 component tree. See [Project Files](project-files.md).

## Matplotlib reference

- [Line style reference](https://matplotlib.org/3.9.0/gallery/lines_bars_and_markers/linestyles.html): the line pattern presets and custom dash sequences.
