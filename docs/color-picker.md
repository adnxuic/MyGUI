# Color Picker

MyGUI uses one color picker for Curve, Plot, Scatter, Fit, and Interpolation charts. Chart creation starts with black unless the current axes has an active palette. Opening or cancelling a dialog only previews the next color; the palette cursor advances after the chart is created successfully.

## Color parameters

| Parameter | Range | Description |
| --- | --- | --- |
| HEX | Matplotlib color name, `#RGB`, `#RGBA`, `#RRGGBB`, or `#RRGGBBAA` | The selected color. Saved values are normalized to uppercase `#RRGGBB` or `#RRGGBBAA`. |
| R, G, B | `0`–`255` | Red, green, and blue channels. |
| Opacity | `0`–`100%` | Alpha channel; transparent colors are shown over a checkerboard. |
| Recent colors | Up to `20` | Colors recorded after a successful creation or application, newest first and without duplicates. |
| Favorite colors | Application-level | User-selected colors retained in the color library. |
| Favorite palettes | Application-level | Built-in or custom palettes retained as favorites. |

The picker contains all existing 296 single colors and 77 built-in palettes in their existing order. Single colors are one-operation choices. Choosing a color from a palette activates that ordered palette for later chart creation.

## Custom palettes

A custom palette has a stable UUID, a unique non-empty name, and 2–12 ordered colors. The palette editor supports adding, editing, removing, and reordering colors. Custom palettes, favorites, and recent colors are stored in the versioned `colorLibrary` `QSettings` group.

Deleting a custom palette from the application library does not affect open charts or saved projects. A project stores the active palette's complete color snapshot and can continue its sequence without the application-level entry.

## Apply to axes

`Apply palette to axes` recolors active chart objects in creation order and includes Curve, Plot, Scatter, Fit, and Interpolation artists. Colors repeat when the axes has more objects than the palette. After success, the next index is `object count modulo palette length`.

The operation updates widgets, artists, and project records together. It keeps legend visibility and location, refreshes the legend once, and schedules one canvas redraw. If an update fails, all colors are restored and the Message Bar reports the rollback.

## Keyboard and accessibility

Color and palette views use standard Qt arrow-key navigation, Enter/double-click activation, focus outlines, tooltips, and accessible names. The picker is a bounded, resizable dialog with scrollable model/delegate views; chart inspectors do not pre-create color actions.
