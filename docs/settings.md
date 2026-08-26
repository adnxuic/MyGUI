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
uses the persisted schema-v15 tree.

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
`100` DPI). Opening a project uses the persisted schema-v15 Figure size and
document DPI and does not overwrite them.

| Parameter | Control | Meaning | Values / default | Key |
| --- | --- | --- | --- | --- |
| Default Figure width | Number | Width in inches for new Figures. | `0.1`–`100`; default `6.4` in | `new_figure.width_in` |
| Default Figure height | Number | Height in inches for new Figures. | `0.1`–`100`; default `4.8` in | `new_figure.height_in` |
| Default document DPI | Number | Document DPI for new Figures. See [`Figure.dpi`](https://matplotlib.org/3.9.0/api/figure_api.html#matplotlib.figure.Figure.dpi). | `1`–`2400`; default `100` | `new_figure.document_dpi` |

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
| Reset all application preferences… | Button | Stages built-in Appearance, Workspace, New Figure, and Export defaults. Apply commits. Hidden when storage is not writable. | Confirmation, then draft | session draft |
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
- [Figure.savefig](https://matplotlib.org/3.9.0/api/figure_api.html#matplotlib.figure.Figure.savefig): format, DPI, transparency, face/edge color, bounding box, padding, and metadata.
- [FigureCanvasBase.print_figure](https://matplotlib.org/3.9.0/api/backend_bases_api.html#matplotlib.backend_bases.FigureCanvasBase.print_figure): print pipeline, `bbox_inches='tight'`, and `pad_inches='layout'`.
- [Agg print_png](https://matplotlib.org/3.9.0/api/backend_agg_api.html#matplotlib.backends.backend_agg.FigureCanvasAgg.print_png): PNG metadata and Pillow kwargs.
- [PDF PdfPages](https://matplotlib.org/3.9.0/api/backend_pdf_api.html#matplotlib.backends.backend_pdf.PdfPages): PDF metadata keys.
- [SVG print_svg](https://matplotlib.org/3.9.0/api/backend_svg_api.html#matplotlib.backends.backend_svg.FigureCanvasSVG.print_svg): SVG metadata keys.
