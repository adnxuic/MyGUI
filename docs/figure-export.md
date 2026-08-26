# Figure Export

导出当前图片... and the Matplotlib canvas toolbar Save button open the same
modal export window for the explicit Figure that requested it. The window is a
one-shot export and application-preference feature: it does not change the
Figure's physical size, document DPI, component state, Undo/Redo stack, project
dirty fingerprint, or schema v15 project files.

The File menu and toolbar both call `MenuBar.export_canvas(explicit_canvas)`, so
a background tab or Canvas Window cannot export the currently selected Figure by
mistake. With no project, Cancel, or a declined overwrite, no file is written
and no Message Bar result is shown. A successful export writes one green result
and closes the window; a failed export writes one red result and keeps the
window open.

The export window loads application Export defaults from Settings and can
override them for that one file. `Use project DPI` is a stored strategy; Custom
DPI is stored separately. When the strategy is on, the live export binds the
current project's `document_dpi`. See [Application Settings](settings.md).

`PyFigureCanvas.export_context()` is the only summary the title-bar module
reads. `PyFigureCanvas.export_figure(request)` is the only
[`Figure.savefig`](https://matplotlib.org/3.9.0/api/figure_api.html#matplotlib.figure.Figure.savefig)
entry; it runs inside the existing style context and passes an explicit
`format` plus validated kwargs. Files are written to a same-directory temporary
name and published with `os.replace` only after the result is non-empty.

## Formats

The format combo is authoritative. The destination path must use a legal
extension for that format; `.jpg` / `.jpeg` and `.tif` / `.tiff` are accepted
aliases. Switching format updates a generated default filename. A hand-typed
path with the wrong extension disables Export and shows an inline error.

| Format | Extensions | Kind | Transparency | Matplotlib metadata |
| --- | --- | --- | --- | --- |
| PNG | `.png` | Raster | Yes | Title, Author, Description, Copyright, Software, Comment |
| JPEG | `.jpg`, `.jpeg` | Raster | No | Not supported |
| TIFF | `.tif`, `.tiff` | Raster | Yes | Not supported |
| WebP | `.webp` | Raster | Yes | Not supported |
| PDF | `.pdf` | Vector | Yes | Title, Author, Subject, Keywords, Creator |
| SVG | `.svg` | Vector | Yes | Title, Creator, Description, Keywords, Rights |

The live canvas remains the visual preview. The window updates a text summary as
options change and does not render a thumbnail.

## Output parameters

| Parameter | Control | Meaning | Values / default | Key |
| --- | --- | --- | --- | --- |
| Path | Text + Browse | Destination file. Browse uses the current format filter and does not show a second overwrite prompt. | Generated `{project}.{ext}` in the last successful directory | runtime |
| Format | Combo | Closed export format. | PNG, JPEG, TIFF, WebP, PDF, SVG; default PNG | `export.format` |
| Use project DPI | Radio | Store the strategy “export at the current `document_dpi`”. The live export binds the current project. | On by default | `export.use_project_dpi` |
| Custom DPI | Radio + number | Override only the export resolution. The Figure size in inches is unchanged. See [`Figure.savefig` dpi](https://matplotlib.org/3.9.0/api/figure_api.html#matplotlib.figure.Figure.savefig). | `1`–`2400`; default is the current document DPI | `export.custom_dpi` |
| Size summary | Read-only | Figure width/height in inches and centimetres, plus the nominal pixel size at the selected DPI. | `round(inches × DPI)` | runtime |
| Tight pixel note | Read-only | Shown when Tight contents is selected because the final raster size is known only after rendering. | Empty when using Figure bounds | runtime |
| Vector DPI note | Read-only | Shown for PDF/SVG. DPI only affects embedded or rasterized content. See [`print_figure`](https://matplotlib.org/3.9.0/api/backend_bases_api.html#matplotlib.backend_bases.FigureCanvasBase.print_figure). | Empty for raster formats | runtime |
| Figure bounds | Radio | Export the full Figure. | Default | `export.bbox_inches` = `figure` |
| Tight contents | Radio | Crop to the tight bounding box. See [`savefig` bbox_inches](https://matplotlib.org/3.9.0/api/figure_api.html#matplotlib.figure.Figure.savefig). | Off | `export.bbox_inches` = `tight` |
| Numeric padding | Radio + number | Inches of padding around a tight crop. | `0`–`5`; default `0.1` | `export.pad_inches` |
| Layout padding | Radio | Use the constrained/compressed layout engine padding, or the Matplotlib default when those engines are not active. See [`pad_inches='layout'`](https://matplotlib.org/3.9.0/api/backend_bases_api.html#matplotlib.backend_bases.FigureCanvasBase.print_figure). | Off | `export.pad_inches` = `layout` |
| Transparent background | Checkbox | Makes Axes and Figure patches transparent. Disabled for JPEG. See [`savefig` transparent](https://matplotlib.org/3.9.0/api/figure_api.html#matplotlib.figure.Figure.savefig). | Off | `export.transparent` |
| Background color | Radios + color picker | Current Figure facecolor (`auto`) or a custom color. Hidden from the save request while transparency is on. | Current Figure color | `export.facecolor` |
| Border color | Radios + color picker | Current Figure edgecolor (`auto`) or a custom color. | Current Figure color | `export.edgecolor` |

Restore defaults returns these backend-compatible values without writing
preferences until the next successful export.

## Encoding parameters

Encoding controls switch with the selected format. PDF and SVG show a vector
explanation and no invalid raster encoding widgets.

| Parameter | Control | Meaning | Values / default | Key |
| --- | --- | --- | --- | --- |
| PNG compression level | Number | zlib compression passed through Pillow. Disabled while Optimize is on. See [Agg `print_png`](https://matplotlib.org/3.9.0/api/backend_agg_api.html#matplotlib.backends.backend_agg.FigureCanvasAgg.print_png). | `0`–`9`; default `6` | `export.png_compress_level` |
| PNG Optimize | Checkbox | Pillow `optimize`. When on, compression level is not sent. | Off | `export.png_optimize` |
| JPEG quality | Number | Pillow JPEG quality. Values above 95 are not offered. | `0`–`95`; default `75` | `export.jpeg_quality` |
| JPEG Optimize | Checkbox | Pillow `optimize`. | Off | `export.jpeg_optimize` |
| JPEG Progressive | Checkbox | Pillow `progressive`. | Off | `export.jpeg_progressive` |
| JPEG chroma | Combo | Automatic, 4:4:4, 4:2:2, or 4:2:0 subsampling. Automatic omits the Pillow argument. | Automatic | `export.jpeg_subsampling` |
| TIFF compression | Combo | Uncompressed, PackBits, LZW, or Adobe Deflate. | None | `export.tiff_compression` |
| WebP mode | Combo | Lossy or lossless. | Lossy | `export.webp_lossless` |
| WebP quality | Number | Pillow WebP quality. | `0`–`100`; default `80` | `export.webp_quality` |
| WebP alpha quality | Number | Pillow `alpha_quality`. | `0`–`100`; default `100` | `export.webp_alpha_quality` |
| WebP method | Number | Pillow encoder method. | `0`–`6`; default `4` | `export.webp_method` |
| WebP exact | Checkbox | Preserve exact transparent pixels. | Off | `export.webp_exact` |

## Metadata parameters

Metadata is sent only for PNG, PDF, and SVG. Empty fields are omitted so
Matplotlib can keep automatic Date, Creator, Producer, and Software values.
JPEG, TIFF, and WebP show that Matplotlib 3.9.0 does not embed metadata for
those formats.

| Parameter | Control | Meaning | Values / default | Key |
| --- | --- | --- | --- | --- |
| PNG Title, Author, Description, Copyright, Software, Comment | Text | Latin-1 keys and values required by [Agg `print_png`](https://matplotlib.org/3.9.0/api/backend_agg_api.html#matplotlib.backends.backend_agg.FigureCanvasAgg.print_png). | Empty omitted | `export.metadata` |
| PDF Title, Author, Subject, Keywords, Creator | Text | PDF info dictionary keys. See [PDF `PdfPages` metadata](https://matplotlib.org/3.9.0/api/backend_pdf_api.html#matplotlib.backends.backend_pdf.PdfPages). | Empty omitted | `export.metadata` |
| SVG Title, Creator, Description, Keywords, Rights | Text | Dublin Core metadata. See [SVG `print_svg`](https://matplotlib.org/3.9.0/api/backend_svg_api.html#matplotlib.backends.backend_svg.FigureCanvasSVG.print_svg). | Empty omitted | `export.metadata` |

## Application preferences

Successful exports update the application Export document (last directory,
format, output, encoding, and metadata) through `ExportPreferencesPort` and
do not write `.mygui.json`. If the figure file is written but the preference
commit fails, the file is kept and one yellow warning reports
`Figure exported, but export preferences could not be saved.` The Settings
Center Export page edits the same defaults without exporting a file. After
the first successful dual-slot commit, leftover `figureExport` keys are inert.
Missing or illegal fields fall back item by item to the backend defaults
above.

`PyFigureCanvas.document_dpi` remains the project and default-export DPI. Qt's
device pixel ratio may change the on-screen renderer DPI, but it does not
change `document_dpi`, project `figure.dpi`, Figure size in inches, or default
export dimensions. A 6.4 × 4.8 inch figure at 100 document DPI exports to
640 × 480 pixels by default on 100%, 125%, 150%, and 200% displays.
`PyFigureCanvas.save(filename, dpi=None)` still exists as a compatible default
request: the path extension selects the format, and an explicit `dpi` overrides
the document DPI.

## Matplotlib reference

- [Figure.savefig](https://matplotlib.org/3.9.0/api/figure_api.html#matplotlib.figure.Figure.savefig): format, DPI, transparency, face/edge color, bounding box, padding, and metadata.
- [FigureCanvasBase.print_figure](https://matplotlib.org/3.9.0/api/backend_bases_api.html#matplotlib.backend_bases.FigureCanvasBase.print_figure): print pipeline, `bbox_inches='tight'`, and `pad_inches='layout'`.
- [Agg print_png](https://matplotlib.org/3.9.0/api/backend_agg_api.html#matplotlib.backends.backend_agg.FigureCanvasAgg.print_png): PNG metadata and Pillow kwargs.
- [PDF PdfPages](https://matplotlib.org/3.9.0/api/backend_pdf_api.html#matplotlib.backends.backend_pdf.PdfPages): PDF metadata keys.
- [SVG print_svg](https://matplotlib.org/3.9.0/api/backend_svg_api.html#matplotlib.backends.backend_svg.FigureCanvasSVG.print_svg): SVG metadata keys.
