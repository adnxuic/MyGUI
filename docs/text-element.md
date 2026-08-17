# Text Element

The Text action on the Element command bar adds a free Text component. A Text can be local (inside the currently selected Axes, the default) or global (attached to the whole Figure). Free Text components are removable and are edited through the Components tree and the Inspector. Property keys are given in parentheses.

## Creation parameters

| Parameter | Control | Meaning | Default |
| --- | --- | --- | --- |
| 全局 / 局部 | Two radio buttons | The component scope. 局部 places the Text inside the selected Axes; 全局 attaches it to the Figure. | 局部 |
| Text | Text field | The text content. | Empty |
| x / y | Two spin boxes | The text position. Local Text uses Axes-relative coordinates: (0, 0) is the lower-left corner and (1, 1) the upper-right corner of the Axes area. Global Text uses Figure-relative coordinates with the same 0 to 1 convention. The spin range -1 to 2 allows placing the text outside the Axes or Figure area; the step is 0.01. | 0.5 / 0.5 |
| Font | Editable dropdown | The font family. The list contains the installed system fonts and Matplotlib fonts, each item rendered in its own font, with case-insensitive auto-completion. | Current Figure style text font |
| Font Size | Spin box | The font size in points. | Current Figure style text size |

## Creation workflow

- A project with a Figure must exist. Local Text additionally requires a selected Axes; the dialog refuses with a warning otherwise.
- The initial font family and size are resolved from the current Figure style defaults. See [Style Creation Defaults](style-creation-defaults.md).
- Creation registers the artist, Controller, Components-tree node, and Inspector in one transaction. The Text appears in the tree under its Axes (local) or the Figure root (global) and can be selected for editing.

## Inspector sections

### Content

| Parameter | Meaning |
| --- | --- |
| Text (text) | The text content, including newlines. |

### Typography

| Parameter | Control | Meaning | Default |
| --- | --- | --- | --- |
| Font family (fontfamily) | Font dropdown | The font used to render the text. | sans-serif |
| Font size (fontsize) | Spin box | Font size in points. | 10.0 |
| Font weight (fontweight) | Named/number editor | Stroke thickness: normal, bold, or a numeric weight. | normal |
| Font style (fontstyle) | Dropdown | normal, italic, or oblique. | normal |
| Font stretch (fontstretch) | Named/number editor | Horizontal condensation or expansion of the glyphs. | normal |
| Font variant (fontvariant) | Dropdown | normal or small-caps. | normal |
| Math font family (math_fontfamily) | Text | Font used for math expressions when math parsing is enabled. | dejavusans |
| Parse math (parse_math) | Checkbox | Renders $...$ math with Matplotlib's mathtext engine. | On |
| Color (color) | Color picker | The text color. | #000000 (style default at creation) |
| Alpha (alpha) | Spin box | Opacity from 0 to 1, or None to inherit. | None |

### Rotation and alignment

| Parameter | Meaning | Default |
| --- | --- | --- |
| Rotation (rotation) | Text angle in degrees, or the words horizontal and vertical. | 0.0 |
| Rotation mode (rotation_mode) | How rotation anchors the text: default or anchor. | default |
| Horizontal alignment (horizontalalignment) | left, center, or right relative to the anchor position. | left |
| Vertical alignment (verticalalignment) | top, center, bottom, baseline, or center_baseline. | baseline |
| Multi-line alignment (multialignment) | Alignment of the lines inside a multi-line text block: None, left, center, or right. | None |
| Wrap (wrap) | Wraps long lines at the Axes or Figure width instead of overflowing. | Off |
| Line spacing (linespacing) | Vertical spacing multiple between lines (non-negative). | 1.2 |
| Transform rotates text (transform_rotates_text) | Whether the coordinate transform additionally rotates the text (for skewed transforms). | Off |

### Position and visibility

| Parameter | Meaning | Default |
| --- | --- | --- |
| Position (position) | The x/y anchor position. | (0.0, 0.0) |
| Visible (visible) | Shows or hides the component. | On |
| Z-order (zorder) | Stacking order among artists. | 3.0 |
| Coordinate system (coordinate_system) | The coordinate space of the position: data (Axes data units), axes (Axes-relative 0 to 1), or figure (Figure-relative 0 to 1). Free Text supports all three inside an Axes; Figure-level Text supports only figure. | data for Axes Text, figure for global Text |

### Rendering

| Parameter | Meaning | Default |
| --- | --- | --- |
| Use TeX (usetex) | Requests TeX rendering for this component. The effective rendering falls back to ordinary text when the optional TeX integration is unavailable. See [TeX Rendering Integration](tex-integration.md). | Off |

### Advanced

| Parameter | Meaning | Default |
| --- | --- | --- |
| Text box (bbox) | Draws a box behind the text when enabled: boxstyle (round, square, circle, and others), facecolor, edgecolor, linewidth, line pattern, alpha, fill, hatch, and pad. | Disabled |
| Antialiased (antialiased) | Renders smooth glyph edges. | On |
| Label (label) | The artist label used for lookups; not a visible legend entry. | Empty |
| Clip on (clip_on) | Clips the text to the Axes boundaries. | On |
| GID (gid) | SVG group id for exports. | None |
| In layout (in_layout) | Includes the text in tight-layout calculations. | On |
| Rasterized (rasterized) | Renders the text as a bitmap in vector exports. | Off |
| Sketch params (sketch_params) | (scale, length, randomness) hand-drawn stroke effect; positive finite values, or None to disable. | None |
| Snap (snap) | Aligns the text to the pixel grid: auto (None), on, or off. | None |
| URL (url) | Hyperlink attached to the text in SVG exports. | None |

See [Chart Component Parameters](chart-component-parameters.md) for the shared export parameters and the generic Line/Scatter appearance sections.

## Matplotlib reference

- [Text](https://matplotlib.org/3.9.0/api/text_api.html#matplotlib.text.Text): the Text parameters.
- [Text introduction](https://matplotlib.org/3.9.0/users/explain/text/text_intro.html): positioning and alignment.
- [Mathtext](https://matplotlib.org/3.9.0/users/explain/text/mathtext.html): math rendering behind Parse math and Math font family.
