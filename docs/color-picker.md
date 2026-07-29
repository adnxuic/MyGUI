# Color Picker

MyGUI uses one color picker for Curve, Plot, Scatter, Fit, and Interpolation charts. Without an explicitly selected Axes palette, chart creation follows the current Figure style's `axes.prop_cycle`; a user-selected built-in or custom Axes palette takes precedence. Opening or cancelling a dialog only previews the next color, and the palette cursor advances after the chart is created successfully.

## Color parameters

| Parameter | Range | Description |
| --- | --- | --- |
| HEX | Matplotlib color name, `#RGB`, `#RGBA`, `#RRGGBB`, or `#RRGGBBAA` | The selected color. Saved values are normalized to uppercase `#RRGGBB` or `#RRGGBBAA`. |
| R, G, B | `0`–`255` | Red, green, and blue channels. |
| Opacity | `0`–`100%` | Alpha channel; transparent colors are shown over a checkerboard. |
| Recent colors | Up to `20` | Colors recorded after a successful creation or application, newest first and without duplicates. |
| Favorite colors | Application-level | User-selected colors retained in the color library. |
| Favorite palettes | Application-level | Built-in or custom palettes retained as favorites. |

The picker contains all existing 296 single colors and 77 built-in palettes in their existing order. Single colors are one-operation choices and do not advance the active style or user-palette cursor. Choosing a color from a palette activates that ordered palette for later chart creation.

## Custom palettes

A custom palette has a stable UUID, a unique non-empty name, and 2–12 ordered colors. The palette editor supports adding, editing, removing, and reordering colors. Custom palettes, favorites, and recent colors are stored in the versioned `colorLibrary` `QSettings` group.

Deleting a custom palette from the application library does not affect open charts or saved projects. A project stores the active palette's complete color snapshot and can continue its sequence without the application-level entry.

## Axes palette panel

The Axes Inspector's Palette section shows the effective source, palette name, and ordered color strip. The strip keeps a readable minimum swatch width and wraps onto additional rows when the Inspector is narrow or the palette contains many colors:

- `Style default · <style>` uses the current Figure style's `axes.prop_cycle`.
- `Built-in palette · <name>` identifies a built-in palette selected by the user.
- `Custom palette · <name>` identifies the exact custom palette selected by the user.

Changing Source to `User-selected` opens the existing palette picker. Cancelling restores the authoritative source shown by the panel. `Choose…` changes one user-selected palette to another. Changing Source to `Style default` resolves the current Figure style again.

Either successful switch recolors Curve, Plot, Scatter, Fit, and Interpolation artists in creation order. Colors repeat when the Axes has more chart objects than the palette. The next index is `object count modulo palette length`. An empty Axes still stores the selection for its first future chart.

The operation updates widgets, artists, the Axes color-cycle state, and project records together. It keeps Legend visibility and location, refreshes the Legend once, and schedules one canvas redraw. If an update fails, all colors and the source selector are restored and the Message Bar reports the rollback.

## Keyboard and accessibility

Color and palette views use standard Qt arrow-key navigation, Enter/double-click activation, focus outlines, tooltips, and accessible names. The picker is a bounded, resizable dialog with scrollable model/delegate views; chart inspectors do not pre-create color actions.
