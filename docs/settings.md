# Application Settings

The Settings Center holds application preferences that are not part of a
project file. Open it from the left activity-rail gear, **Edit > Settings**,
or **Ctrl+,**. The window is created on first use, reused, and uses English
labels. UI theme is not Matplotlib Figure style.

Theme, UI font size, and density change application chrome through
`ThemeService`. They do not change a Figure's Matplotlib `style`,
`axes.prop_cycle`, or export appearance. Figure style is chosen when a
project is created. See [Style Creation Defaults](style-creation-defaults.md).

Settings values never enter `.mygui.json`, Undo/Redo, project dirty
fingerprints, Component state, or Canvas restore. Opening a project always
uses the persisted schema-v23 tree.

Apply saves the current draft and keeps Settings open. OK saves and closes.
Cancel, Esc, and the window close button discard an uncommitted draft,
including a live Appearance preview. Restore page defaults changes only the
draft and, on Workspace, only `workspace.remember_layout` (hidden
`workspace.layout` is restored only by Reset workspace layout now). Immediate
commands (workspace layout reset, incompatible storage reset, color-library
clear/reset/storage reset) confirm separately and do not ride Apply. Search
Enter/Return does not activate OK. Apply and OK are disabled when storage is
read-only. Each user action reports at most one Message Bar result.

The left pane is 190 logical pixels wide and searches page titles, registered
field labels, enum choice words, and Maintenance command names. The window
starts at 840×620 logical pixels
(minimum 720×520), stays within 90% of the current screen, and does not
store its geometry.

## Appearance

These controls preview immediately. They do not mutate Matplotlib Figures,
Artists, `rcParams`, or project colors.

| Parameter | Control | Meaning | Values / default | Key |
| --- | --- | --- | --- | --- |
| Theme | Radios | Workbench chrome scheme. System follows the OS color scheme and shows the effective result, for example `System (Light)`. | System, Light, Dark; default System on a fresh install | `appearance.theme_mode` |
| UI font size | Number | Application font size in points. | `8`–`16`; default `9` | `appearance.ui_font_point_size` |
| Density | Radios | Control spacing and chrome sizes. Standard matches the historical first-run layout. | Compact, Standard, Comfortable; default Standard | `appearance.density` |

## Workspace

Remember layout is an Apply draft. Resetting the layout is an immediate
confirmed command and is not part of Apply. The stored layout covers
splitter sizes, Explorer mode, and Explorer visibility. Window geometry is
not stored. Restore page defaults does not stage the hidden layout.

| Parameter | Control | Meaning | Values / default | Key |
| --- | --- | --- | --- | --- |
| Remember workspace layout | Checkbox | Save splitter and Explorer state when MyGUI closes. | On | `workspace.remember_layout` |
| Workspace layout | Hidden | Splitter sizes, Explorer mode, and Explorer visibility for the next startup. Not shown on this page. Restore page defaults does not change it. | Default splitters / Table / visible | `workspace.layout` |
| Reset workspace layout now… | Button | Apply the default splitter sizes and Explorer visibility immediately. | Separate confirmation | immediate command |

## New Figure

These defaults apply to the Style creation window and to Figures created by
a first-time text or Excel import. Precedence is this session's explicit
input > application defaults > built-in defaults (`6.4` in × `4.8` in,
`100` DPI). Opening a project uses the persisted schema-v23 Figure size and
document DPI and does not overwrite them.

| Parameter | Control | Meaning | Values / default | Key |
| --- | --- | --- | --- | --- |
| Default Figure width | Number | Width in inches for new Figures. | `0.1`–`100`; default `6.4` in | `new_figure.width_in` |
| Default Figure height | Number | Height in inches for new Figures. | `0.1`–`100`; default `4.8` in | `new_figure.height_in` |
| Default document DPI | Number | Document DPI for new Figures. See [`Figure.dpi`](https://matplotlib.org/3.9.0/api/figure_api.html#matplotlib.figure.Figure.dpi). | `1`–`2400`; default `100` | `new_figure.document_dpi` |

## Templates

Templates are external files, not application-preference keys. This page is
therefore not part of `PAGE_IDS`; **Restore page defaults** is disabled.
Template operations take effect immediately even if Settings is later closed
with Cancel. See [Chart Templates](chart-templates.md) for extraction,
matching, privacy, and application behavior.

| Operation | Control | Meaning | Persistence |
| --- | --- | --- | --- |
| Search | Text | Filter by name, notes, and required headers; corrupt records remain identifiable by filename. | None |
| Required Data | Read-only text | Sheet and column contract for the selected template. Extra lines scroll; stretching the window does not spread or clip the lines. | None |
| Apply Template… | Button | Close Settings and open the shared four-step Apply Template workflow. | Creates a new dirty project only after success |
| Rename… | Button | Change the unique display name without changing the template UUID filename. | Immediate atomic file replacement |
| Save Notes | Button | Save up to 2,000 characters. | Immediate atomic file replacement |
| Duplicate | Button | Create a new template ID and unique name. | Immediate new file |
| Update from Figure… | Button | Preserve ID, name, notes, and creation time while replacing the contract and Figure blueprint after confirmation. | Immediate atomic file replacement |
| Import… / Export… | Buttons | Transfer one strict `.mygui-template.json` file. Same-ID imports require replacement confirmation. Empty library also offers Import… in the placeholder. | Immediate file operation |
| Refresh | Button | Reload valid and corrupt files from the template directory. | None |
| Delete… | Button | Delete the selected template after confirmation. | Immediate, not Undoable |
| Open Template Folder | Button | Create the repository-root `template/` directory if needed and open it. | Directory creation only |

## Components

These defaults apply only to components created after Apply. They do not
change existing Artists, the open project, Undo/Redo, or schema-v23 files.
Opening a project restores persisted component properties and does not apply
this page. Restore page defaults and Reset all restore every field to
**inherit** (the last custom value is kept but unused until you uncheck
inherit). Color editors on this page do not write the color library. Line,
Scatter, and Text sit on separate tabs so the default 840×620 window shows one
complete group.

Precedence for a new component: this creation's explicit dialog input >
Components override > current Axes palette (Line/Scatter color) or Figure
style (other fields) > Matplotlib 3.9 built-in fallbacks. See
[Style Creation Defaults](style-creation-defaults.md).

Inherit color for Line and Scatter continues to use the current Axes palette
cursor, not the first style-probe color. An override color is a custom
selection: it does not advance the palette. Mapped Scatter and XRD fields
that the request sets explicitly still win; unset appearance fields use this
page.

| Parameter | Control | Meaning | Values / default | Key |
| --- | --- | --- | --- | --- |
| Line color | Inherit checkbox + color | Function Curve, Plot, Fit, and Interpolation. Inherit uses the Axes palette. | Inherit; inactive `#1F77B4` | `components.line.color` |
| Line style | Inherit checkbox + preset | Closed presets only. See [linestyles](https://matplotlib.org/3.9.0/gallery/lines_bars_and_markers/linestyles.html). | Inherit; inactive `-` | `components.line.linestyle` |
| Line width | Inherit checkbox + number | Line width in points. See [`Line2D.set_linewidth`](https://matplotlib.org/3.9.0/api/_as_gen/matplotlib.lines.Line2D.html#matplotlib.lines.Line2D.set_linewidth). | Inherit; inactive `1.5` | `components.line.linewidth` |
| Line marker | Inherit checkbox + marker | Marker symbol. See [markers](https://matplotlib.org/3.9.0/api/markers_api.html). | Inherit; inactive `None` | `components.line.marker` |
| Marker size | Inherit checkbox + number | Marker size in points. | Inherit; inactive `6.0` | `components.line.markersize` |
| Marker edge width | Inherit checkbox + number | Marker edge width in points. | Inherit; inactive `1.0` | `components.line.markeredgewidth` |
| Scatter color | Inherit checkbox + color | Ordinary Scatter fill (edge follows color). Inherit uses the Axes palette. | Inherit; inactive `#1F77B4` | `components.scatter.color` |
| Scatter marker | Inherit checkbox + marker | Ordinary Scatter marker. | Inherit; inactive `o` | `components.scatter.marker` |
| Scatter size | Inherit checkbox + number | Marker area in points-squared. See [`Axes.scatter` s](https://matplotlib.org/3.9.0/api/_as_gen/matplotlib.axes.Axes.scatter.html). | Inherit; inactive `36.0` | `components.scatter.size` |
| Scatter line width | Inherit checkbox + number | Marker outline width. | Inherit; inactive `1.0` | `components.scatter.linewidth` |
| Text font family | Inherit checkbox + font | Free axes/figure Text only, not Title or axis labels. See [fonts](https://matplotlib.org/3.9.0/users/explain/text/fonts.html). | Inherit; inactive `sans-serif` | `components.text.fontfamily` |
| Text font size | Inherit checkbox + number | Free Text size in points. | Inherit; inactive `10.0` | `components.text.fontsize` |
| Text color | Inherit checkbox + color | Free Text color. Inherit uses Figure style. | Inherit; inactive `#000000` | `components.text.color` |
| Text font weight | Inherit checkbox + enum | `normal` or `bold`. | Inherit; inactive `normal` | `components.text.fontweight` |
| Text font style | Inherit checkbox + enum | `normal` or `italic`. | Inherit; inactive `normal` | `components.text.fontstyle` |

## Axes Components

These defaults apply only to ordinary Axes created after Apply. They do not
change existing Artists, Colorbar auxiliary Axes, In-Axes, project restore,
Undo/Redo, or schema-v23 files. Opening a project restores persisted Axes
properties and does not apply this page. Restore page defaults and Reset all
restore every field to **inherit** (the last custom value is kept but unused
until you uncheck inherit). Color editors on this page do not write the color
library.

The page sits after Components: New Figure → Components → Axes Components →
Export. Its four tabs are General, Spines, X Axis, and Y Axis. Each tab body
scrolls internally so the tab bar stays visible at the default 840×620 window.
X and Y each
group Major and Minor independently; there is no implicit coupling. Draft
**Copy X → Y**, **Copy Y → X**, **Copy Major → Minor**, and **Copy Minor →
Major** copy mode and the hidden value into the other group without committing
until Apply.

Title, Axis Label, Legend, limits, scale, locator, formatter, aspect, and
margins are not stored here. Later Axes Inspector properties must decide
whether they also belong on this creation-defaults page.

Precedence for a new ordinary Axes: this layout dialog's explicit values
(including XRD scientific rules) > Axes Components override > current Figure
style > Matplotlib 3.9 built-in fallbacks. See
[Style Creation Defaults](style-creation-defaults.md) and
[Axes Layout Templates](axes-layouts.md). Right-Y transparent background,
shared outer labels, and XRD range/reserve rules still win after appearance
is applied. The layout dialog freezes one resolved snapshot when it opens;
later Settings Apply does not rewrite that open dialog.

Numeric ranges: line/tick width `0`–`100`, tick length and pad `0`–`100`,
font size `1`–`1000`, rotation `-360`–`360`, grid alpha `None` or `0`–`1`.
Colors are stored as hex. `axisbelow` keeps the raw values `True`, `False`,
and `"line"`. Envelope v1 payloads that omit `components.axes` load as all
inherit.

### General

| Parameter | Control | Meaning | Values / default | Key |
| --- | --- | --- | --- | --- |
| Facecolor | Inherit checkbox + color | Axes patch color. See [`Axes.set_facecolor`](https://matplotlib.org/3.9.0/api/_as_gen/matplotlib.axes.Axes.set_facecolor.html). | Inherit; inactive `#FFFFFF` | `components.axes.facecolor` |
| Frame on | Inherit checkbox + checkbox | Draw the Axes frame. See [`Axes.set_frame_on`](https://matplotlib.org/3.9.0/api/_as_gen/matplotlib.axes.Axes.set_frame_on.html). | Inherit; inactive on | `components.axes.frameon` |
| Axis below | Inherit checkbox + enum | Whether axis spines/ticks draw below plots. See [`Axes.set_axisbelow`](https://matplotlib.org/3.9.0/api/_as_gen/matplotlib.axes.Axes.set_axisbelow.html). | Inherit; inactive `line`; choices `True`, `False`, `line` | `components.axes.axisbelow` |

### Spines

Each of left, right, top, and bottom is an independent key group. See
[`Spine`](https://matplotlib.org/3.9.0/api/spines_api.html).

| Parameter | Control | Meaning | Values / default | Key |
| --- | --- | --- | --- | --- |
| Visible | Inherit checkbox + checkbox | Show that spine. | Inherit; inactive on | `components.axes.spines.<left/right/top/bottom>.visible` |
| Color | Inherit checkbox + color | Spine edge color. | Inherit; inactive `#000000` | `components.axes.spines.<side>.color` |
| Line width | Inherit checkbox + number | Spine width in points. | Inherit; inactive `0.8` | `components.axes.spines.<side>.linewidth` |
| Line style | Inherit checkbox + preset | Spine pattern. See [linestyles](https://matplotlib.org/3.9.0/gallery/lines_bars_and_markers/linestyles.html). | Inherit; inactive `-` | `components.axes.spines.<side>.linestyle` |

Concrete keys: `components.axes.spines.left.visible`,
`components.axes.spines.left.color`, `components.axes.spines.left.linewidth`,
`components.axes.spines.left.linestyle`, and the same four fields for
`right`, `top`, and `bottom` (16 keys).

### Ticks

X/Y and Major/Minor are independent. See
[`Axes.tick_params`](https://matplotlib.org/3.9.0/api/_as_gen/matplotlib.axes.Axes.tick_params.html).

| Parameter | Control | Meaning | Values / default | Key |
| --- | --- | --- | --- | --- |
| Primary visible | Inherit checkbox + checkbox | Bottom ticks (X) or left ticks (Y). Major inactive on; minor inactive off. | Inherit | `components.axes.<x/y>.<major/minor>.ticks.primary_visible` |
| Secondary visible | Inherit checkbox + checkbox | Top ticks (X) or right ticks (Y). | Inherit; inactive off | `components.axes.<x/y>.<major/minor>.ticks.secondary_visible` |
| Direction | Inherit checkbox + enum | `in`, `out`, or `inout`. | Inherit; inactive `out` | `components.axes.<x/y>.<major/minor>.ticks.direction` |
| Length | Inherit checkbox + number | Tick length in points. Major inactive `3.5`; minor `2.0`. | Inherit | `components.axes.<x/y>.<major/minor>.ticks.length` |
| Width | Inherit checkbox + number | Tick width in points. Major inactive `0.8`; minor `0.6`. | Inherit | `components.axes.<x/y>.<major/minor>.ticks.width` |
| Color | Inherit checkbox + color | Tick color. | Inherit; inactive `#000000` | `components.axes.<x/y>.<major/minor>.ticks.color` |

### Tick labels

| Parameter | Control | Meaning | Values / default | Key |
| --- | --- | --- | --- | --- |
| Primary visible | Inherit checkbox + checkbox | Bottom labels (X) or left labels (Y). Major inactive on; minor inactive off. | Inherit | `components.axes.<x/y>.<major/minor>.tick_labels.primary_visible` |
| Secondary visible | Inherit checkbox + checkbox | Top labels (X) or right labels (Y). | Inherit; inactive off | `components.axes.<x/y>.<major/minor>.tick_labels.secondary_visible` |
| Color | Inherit checkbox + color | Label color. | Inherit; inactive `#000000` | `components.axes.<x/y>.<major/minor>.tick_labels.color` |
| Font family | Inherit checkbox + font | Label family. See [fonts](https://matplotlib.org/3.9.0/users/explain/text/fonts.html). | Inherit; inactive `sans-serif` | `components.axes.<x/y>.<major/minor>.tick_labels.fontfamily` |
| Font size | Inherit checkbox + number | Label size in points. | Inherit; inactive `10.0` | `components.axes.<x/y>.<major/minor>.tick_labels.fontsize` |
| Font weight | Inherit checkbox + enum | Closed weight tokens. | Inherit; inactive `normal` | `components.axes.<x/y>.<major/minor>.tick_labels.fontweight` |
| Font style | Inherit checkbox + enum | `normal`, `italic`, or `oblique`. | Inherit; inactive `normal` | `components.axes.<x/y>.<major/minor>.tick_labels.fontstyle` |
| Rotation | Inherit checkbox + number | Label rotation in degrees. | Inherit; inactive `0` | `components.axes.<x/y>.<major/minor>.tick_labels.rotation` |
| Pad | Inherit checkbox + number | Padding from the axis. Major inactive `3.5`; minor `3.4`. | Inherit | `components.axes.<x/y>.<major/minor>.tick_labels.pad` |

### Grid

See [`Axes.grid`](https://matplotlib.org/3.9.0/api/_as_gen/matplotlib.axes.Axes.grid.html).

| Parameter | Control | Meaning | Values / default | Key |
| --- | --- | --- | --- | --- |
| Visible | Inherit checkbox + checkbox | Show that grid. | Inherit; inactive off | `components.axes.<x/y>.<major/minor>.grid.visible` |
| Color | Inherit checkbox + color | Grid line color. | Inherit; inactive `#B0B0B0` | `components.axes.<x/y>.<major/minor>.grid.color` |
| Line style | Inherit checkbox + preset | Grid pattern. See [linestyles](https://matplotlib.org/3.9.0/gallery/lines_bars_and_markers/linestyles.html). | Inherit; inactive `-` | `components.axes.<x/y>.<major/minor>.grid.linestyle` |
| Line width | Inherit checkbox + number | Grid width in points. | Inherit; inactive `0.8` | `components.axes.<x/y>.<major/minor>.grid.linewidth` |
| Alpha | Inherit checkbox + None checkbox + number | Grid opacity. `None` leaves Matplotlib's unset alpha. | Inherit; inactive `None` | `components.axes.<x/y>.<major/minor>.grid.alpha` |

Together these tables are 99 independent persisted keys.

## Export

The Export page reuses the same options editor as
[Figure Export](figure-export.md). It stores application defaults only. It does
not change an open Figure, and it does not run an export. The next export
window loads these defaults and can override them for that one file.

`Use project DPI` stores a strategy, not a copied DPI number. On the Settings
Export page the radio label does not freeze a DPI number from the first open.
Custom DPI is stored separately and is kept when the strategy is selected. A
live export binds the current project's `document_dpi` when the strategy is
on. Color pickers on this page do not write the color library; recents and
favorites change only through Maintenance commands.

| Parameter | Control | Meaning | Values / default | Key |
| --- | --- | --- | --- | --- |
| Format | Combo | Default export format. | PNG, JPEG, TIFF, WebP, PDF, SVG; default PNG | `export.format` |
| Use project DPI | Radio | Store the strategy “export at the current project's document DPI”. | On | `export.use_project_dpi` |
| Custom DPI | Radio + number | Stored override used when the strategy is off. See [`Figure.savefig` dpi](https://matplotlib.org/3.9.0/api/figure_api.html#matplotlib.figure.Figure.savefig). | `1`–`2400`; default `100` | `export.custom_dpi` |
| Figure bounds | Radio | Default crop is the full Figure. | Default | `export.bbox_inches` = `figure` |
| Tight contents | Radio | Default crop is the tight bounding box. See [`savefig` bbox_inches](https://matplotlib.org/3.9.0/api/figure_api.html#matplotlib.figure.Figure.savefig). | Off | `export.bbox_inches` = `tight` |
| Numeric padding | Radio + number | Inches of padding around a tight crop. | `0`–`5`; default `0.1` | `export.pad_inches` |
| Layout padding | Radio | Use layout-engine padding, or the Matplotlib default when those engines are not active. See [`pad_inches='layout'`](https://matplotlib.org/3.9.0/api/backend_bases_api.html#matplotlib.backend_bases.FigureCanvasBase.print_figure). | Off | `export.pad_inches` = `layout` |
| Transparent background | Checkbox | Default transparent Axes and Figure patches. Disabled for JPEG. See [`savefig` transparent](https://matplotlib.org/3.9.0/api/figure_api.html#matplotlib.figure.Figure.savefig). | Off | `export.transparent` |
| Background color | Radios + color picker | Current Figure facecolor (`auto`) or a custom color. | Current Figure color | `export.facecolor` |
| Border color | Radios + color picker | Current Figure edgecolor (`auto`) or a custom color. | Current Figure color | `export.edgecolor` |
| PNG compression level | Number | zlib compression passed through Pillow. Disabled while Optimize is on. See [Agg `print_png`](https://matplotlib.org/3.9.0/api/backend_agg_api.html#matplotlib.backends.backend_agg.FigureCanvasAgg.print_png). | `0`–`9`; default `6` | `export.png_compress_level` |
| PNG Optimize | Checkbox | Pillow `optimize`. When on, compression level is not sent. | Off | `export.png_optimize` |
| JPEG quality | Number | Pillow JPEG quality. Values above 95 are not offered. | `0`–`95`; default `75` | `export.jpeg_quality` |
| JPEG Optimize | Checkbox | Pillow `optimize`. | Off | `export.jpeg_optimize` |
| JPEG Progressive | Checkbox | Pillow `progressive`. | Off | `export.jpeg_progressive` |
| JPEG chroma | Combo | Automatic, 4:4:4, 4:2:2, or 4:2:0 subsampling. | Automatic | `export.jpeg_subsampling` |
| TIFF compression | Combo | Uncompressed, PackBits, LZW, or Adobe Deflate. | None | `export.tiff_compression` |
| WebP mode | Combo | Lossy or lossless. | Lossy | `export.webp_lossless` |
| WebP quality | Number | Pillow WebP quality. | `0`–`100`; default `80` | `export.webp_quality` |
| WebP alpha quality | Number | Pillow `alpha_quality`. | `0`–`100`; default `100` | `export.webp_alpha_quality` |
| WebP method | Number | Pillow encoder method. | `0`–`6`; default `4` | `export.webp_method` |
| WebP exact | Checkbox | Preserve exact transparent pixels. | Off | `export.webp_exact` |
| PNG Title, Author, Description, Copyright, Software, Comment | Text | Latin-1 keys and values required by [Agg `print_png`](https://matplotlib.org/3.9.0/api/backend_agg_api.html#matplotlib.backends.backend_agg.FigureCanvasAgg.print_png). Empty omitted. | Empty | `export.metadata` |
| PDF Title, Author, Subject, Keywords, Creator | Text | PDF info dictionary keys. See [PDF `PdfPages` metadata](https://matplotlib.org/3.9.0/api/backend_pdf_api.html#matplotlib.backends.backend_pdf.PdfPages). Empty omitted. | Empty | `export.metadata` |
| SVG Title, Creator, Description, Keywords, Rights | Text | Dublin Core metadata. See [SVG `print_svg`](https://matplotlib.org/3.9.0/api/backend_svg_api.html#matplotlib.backends.backend_svg.FigureCanvasSVG.print_svg). Empty omitted. | Empty | `export.metadata` |
| Last directory | Hidden | Last successful export folder. Not edited on this page. | Empty until an export succeeds | `export.last_directory` |

## Integrations

The Integrations page is read-only. It does not start TeX or MATLAB, does not
remount the existing right-hand panels, and does not save TeX enablement,
preamble, or MATLAB connection. Those remain this-session state. See
[TeX Rendering Integration](tex-integration.md) and [Fitting](fitting.md).

| Parameter | Control | Meaning | Values / default | Key |
| --- | --- | --- | --- | --- |
| TeX availability | Read-only | Whether a TeX executable is on PATH. | Available or Unavailable | runtime |
| TeX session | Read-only | Whether TeX is enabled in this application session. | Enabled or Disabled this session | runtime |
| TeX diagnostics | Read-only | Short summary. No TeX process is started. | PATH / session note | runtime |
| Open TeX panel… | Button | Closes Settings, then asks the main window to show the existing right-rail TeX panel. | — | runtime action |
| MATLAB availability | Read-only | Whether the MATLAB Python runtime can be imported. | Available or Unavailable | runtime |
| MATLAB session | Read-only | Whether MATLAB is connected in this session. | Connected or Not connected this session | runtime |
| MATLAB diagnostics | Read-only | Short summary. MATLAB/MCR is not started. | Import / session note | runtime |
| Open MATLAB panel… | Button | Closes Settings, then asks the main window to show the existing right-rail MATLAB panel. | — | runtime action |

Missing TeX or MATLAB does not block Settings or the rest of the GUI.

## Maintenance

Application preferences and the color library are sibling dual-slot documents
on the same store. Maintenance shows each document's health and offers reset
commands. Reset-all application preferences never deletes the color library.

| Parameter | Control | Meaning | Values / default | Key |
| --- | --- | --- | --- | --- |
| Application preferences health | Read-only | Dual-slot health of application settings. | Normal; Degraded; Read-only future; Recovery required; Write uncertain | runtime |
| Color library health | Read-only | Dual-slot health of the color library. | Same closed set | runtime |
| Reset all application preferences… | Button | Stages built-in Appearance, Workspace, New Figure, Components (all inherit), Axes Components (all inherit), and Export defaults. Apply commits. Hidden when storage is not writable. Never deletes the color library. | Confirmation, then draft | session draft |
| Reset incompatible storage now… | Button | Immediate recovery: clears application dual-slot keys and leftover `workspaceLayout` / `figureExport` / `colorLibrary` legacy groups, then restores writable defaults. Not Apply. Shown only for Read-only future, Recovery required, or Write uncertain. | Separate confirmation | immediate command |
| Color library counts | Read-only | Persisted recents, favorite colors, favorite palettes, and custom palettes. Built-in palettes are not counted. Recovery/future storage that was not loaded does not show zeros as an empty library. | `0` on a fresh library | runtime |
| Clear recent colors… | Button | Immediate clear of recent colors. Favorites and custom palettes stay. Disabled until color storage is Normal or Degraded. | Separate confirmation | color-library command |
| Reset color library… | Button | Immediate clear of recents, favorites, and custom palettes. Built-in palettes remain. Disabled until color storage is Normal or Degraded. | Separate confirmation | color-library command |
| Reset color library storage now… | Button | Immediate clear of the color dual-slot only, then a writable empty library. Shown for Recovery required. Future-only color storage is read-only. | Separate confirmation | immediate command |

## Storage

Preferences use injected dual-slot `QSettings` documents
(`applicationSettings` and `colorLibrarySettings`). After the first successful
new-slot commit, the older `workspaceLayout`, `figureExport`, and
`colorLibrary` groups are leftover data and are no longer written. See
[GUI Workbench](workbench.md) and [Color Picker](color-picker.md).

## Matplotlib reference

- [Figure.dpi](https://matplotlib.org/3.9.0/api/figure_api.html#matplotlib.figure.Figure.dpi): document DPI used by New Figure defaults.
- [Linestyles gallery](https://matplotlib.org/3.9.0/gallery/lines_bars_and_markers/linestyles.html): Line style presets on the Components and Axes Components pages.
- [Markers API](https://matplotlib.org/3.9.0/api/markers_api.html): Line and Scatter marker catalogs.
- [Line2D.set_linewidth](https://matplotlib.org/3.9.0/api/_as_gen/matplotlib.lines.Line2D.html#matplotlib.lines.Line2D.set_linewidth): Line width.
- [Axes.scatter](https://matplotlib.org/3.9.0/api/_as_gen/matplotlib.axes.Axes.scatter.html): Scatter size and linewidth.
- [Fonts explainer](https://matplotlib.org/3.9.0/users/explain/text/fonts.html): free-Text and Axes tick-label font family.
- [Axes.set_facecolor](https://matplotlib.org/3.9.0/api/_as_gen/matplotlib.axes.Axes.set_facecolor.html): Axes Components facecolor.
- [Axes.set_frame_on](https://matplotlib.org/3.9.0/api/_as_gen/matplotlib.axes.Axes.set_frame_on.html): Axes Components frameon.
- [Axes.set_axisbelow](https://matplotlib.org/3.9.0/api/_as_gen/matplotlib.axes.Axes.set_axisbelow.html): Axes Components axisbelow.
- [Spine](https://matplotlib.org/3.9.0/api/spines_api.html): Axes Components spines.
- [Axes.tick_params](https://matplotlib.org/3.9.0/api/_as_gen/matplotlib.axes.Axes.tick_params.html): Axes Components ticks and tick labels.
- [Axes.grid](https://matplotlib.org/3.9.0/api/_as_gen/matplotlib.axes.Axes.grid.html): Axes Components grid.
- [Figure.savefig](https://matplotlib.org/3.9.0/api/figure_api.html#matplotlib.figure.Figure.savefig): format, DPI, transparency, face/edge color, bounding box, padding, and metadata.
- [FigureCanvasBase.print_figure](https://matplotlib.org/3.9.0/api/backend_bases_api.html#matplotlib.backend_bases.FigureCanvasBase.print_figure): print pipeline, `bbox_inches='tight'`, and `pad_inches='layout'`.
- [Agg print_png](https://matplotlib.org/3.9.0/api/backend_agg_api.html#matplotlib.backends.backend_agg.FigureCanvasAgg.print_png): PNG metadata and Pillow kwargs.
- [PDF PdfPages](https://matplotlib.org/3.9.0/api/backend_pdf_api.html#matplotlib.backends.backend_pdf.PdfPages): PDF metadata keys.
- [SVG print_svg](https://matplotlib.org/3.9.0/api/backend_svg_api.html#matplotlib.backends.backend_svg.FigureCanvasSVG.print_svg): SVG metadata keys.
