# Colorbar Component

Colorbar is a first-class persisted Element. It belongs to its owner Axes in
the Components tree and references one scalar-mapped Scatter by stable
Component ID:

```text
Axes
├── Scatter
└── Colorbars
    └── Colorbar — <source id preview>
```

The Colorbar does not own a colormap, normalization, limits, or scalar data.
Those remain authoritative in the source Scatter's `ScatterColorMapSpec` and
`color_ref`. The first release supports only `scatter/scatter` sources with
scalar color mapping enabled, a valid numeric `color_ref`, and an active
Matplotlib `ScalarMappable`. One source may have at most one Colorbar.

## Create a Colorbar

Select the owner Axes, choose **Add Element → Colorbar...**, then select an
eligible Scatter and its initial placement. The dialog lists only valid
sources under that Axes that do not already have a Colorbar. If the list is
empty, the OK button is disabled and the Message Bar reports a warning.

Creation allocates the stable ID, creates the Colorbar and its auxiliary Axes,
synchronizes style-derived defaults, registers the Controller and Locator,
prepares the Inspector/tree projection, renders, and publishes selection in
one registration transaction. Failure restores the owner layout and source
callback state and leaves no auxiliary Axes or partial Component.

## Inspector parameters

Every persistent field below has one production control. `source_component_id`
is the only Colorbar `data` field; all other rows are `properties` fields.

| Section / field | Control | Meaning | Values and default | Persisted key |
| --- | --- | --- | --- | --- |
| Source | Read-only summary | Stable Scatter dependency and ownership reminder. | Selected at creation; cannot be rebound in this release. | `data.source_component_id` |
| Placement / Location | Choice | Side of the owner Axes; orientation is derived and is not persisted separately. See [`Figure.colorbar`](https://matplotlib.org/3.9.0/api/_as_gen/matplotlib.figure.Figure.colorbar.html). | `left`, `right` (default), `top`, `bottom` | `properties.location` |
| Placement / Fraction | Number | Fraction of the original Axes reserved for the Colorbar. See [`Figure.colorbar`](https://matplotlib.org/3.9.0/api/_as_gen/matplotlib.figure.Figure.colorbar.html). | `0.001`–`1`; default `0.15` | `properties.fraction` |
| Placement / Shrink | Number | Scale factor applied to Colorbar length. See [`Figure.colorbar`](https://matplotlib.org/3.9.0/api/_as_gen/matplotlib.figure.Figure.colorbar.html). | `0.001`–`1`; default `1` | `properties.shrink` |
| Placement / Aspect | Number | Long-to-short dimension ratio. See [`Figure.colorbar`](https://matplotlib.org/3.9.0/api/_as_gen/matplotlib.figure.Figure.colorbar.html). | Positive number; default `20` | `properties.aspect` |
| Placement / Pad | Number | Gap between owner Axes and Colorbar as a fraction of the original Axes. See [`Figure.colorbar`](https://matplotlib.org/3.9.0/api/_as_gen/matplotlib.figure.Figure.colorbar.html). | `0`–`1`; default `0.05` | `properties.pad` |
| Scale & Ticks / Locator | Locator editor | Tagged major-tick placement contract. See [Matplotlib ticker locators](https://matplotlib.org/3.9.0/api/ticker_api.html#tick-locating). | `LocatorSpec`; default `auto` | `properties.locator` |
| Scale & Ticks / Formatter | Formatter editor | Tagged major-tick label format. Fixed formatters require an equal-length fixed locator. See [Matplotlib tick formatting](https://matplotlib.org/3.9.0/api/ticker_api.html#tick-formatting). | `FormatterSpec`; default scalar formatter | `properties.formatter` |
| Scale & Ticks / Minor ticks | Check box | Enables or disables minor ticks on the derived Colorbar axis. See [`Colorbar.minorticks_on`](https://matplotlib.org/3.9.0/api/colorbar_api.html#matplotlib.colorbar.Colorbar.minorticks_on). | `false` (default) or `true` | `properties.minor_ticks` |
| Scale & Ticks / Tick location | Choice | Tick side; incompatible horizontal/vertical combinations are rejected. See [`Colorbar.ticklocation`](https://matplotlib.org/3.9.0/api/colorbar_api.html#matplotlib.colorbar.Colorbar.ticklocation). | `auto` (default), `left`, `right`, `top`, `bottom` | `properties.ticklocation` |
| Label / Label | Text | Colorbar axis label. See [`Colorbar.set_label`](https://matplotlib.org/3.9.0/api/colorbar_api.html#matplotlib.colorbar.Colorbar.set_label). | Text; default empty | `properties.label` |
| Label / Label font | Font editor | Complete family, size, weight, style, stretch, variant, and color for the label. See [`Text`](https://matplotlib.org/3.9.0/api/text_api.html#matplotlib.text.Text). | `FontSpec`; default sans-serif, 10 pt, normal, black | `properties.label_font` |
| Appearance / Visible | Check box | Shows or hides the complete Colorbar auxiliary Axes. | `true` (default) or `false` | `properties.visible` |
| Appearance / Tick font | Font editor | Complete font contract for major and minor tick labels. See [`Text`](https://matplotlib.org/3.9.0/api/text_api.html#matplotlib.text.Text). | `FontSpec`; default sans-serif, 10 pt, normal, black | `properties.tick_font` |
| Appearance / Outline visible | Check box | Shows or hides the Colorbar outline. See [`Colorbar.outline`](https://matplotlib.org/3.9.0/api/colorbar_api.html#matplotlib.colorbar.Colorbar). | `true` (default) or `false` | `properties.outline_visible` |
| Appearance / Outline color | Color picker | Outline edge color through the shared Color Library. See [`Colorbar.outline`](https://matplotlib.org/3.9.0/api/colorbar_api.html#matplotlib.colorbar.Colorbar). | Matplotlib color; default `#000000` | `properties.outline_color` |
| Appearance / Outline width | Number | Outline width in points. See [`Colorbar.outline`](https://matplotlib.org/3.9.0/api/colorbar_api.html#matplotlib.colorbar.Colorbar). | Non-negative number; default `0.8` | `properties.outline_linewidth` |
| Advanced / Extend | Choice | Adds neither, one, or both out-of-range extensions. See [`Figure.colorbar`](https://matplotlib.org/3.9.0/api/_as_gen/matplotlib.figure.Figure.colorbar.html). | `neither` (default), `both`, `min`, `max` | `properties.extend` |
| Advanced / Spacing | Choice | Uniform or proportional spacing for discrete boundaries. See [`Figure.colorbar`](https://matplotlib.org/3.9.0/api/_as_gen/matplotlib.figure.Figure.colorbar.html). | `uniform` (default), `proportional` | `properties.spacing` |
| Advanced / Draw edges | Check box | Draws separator lines between discrete color regions. See [`Figure.colorbar`](https://matplotlib.org/3.9.0/api/_as_gen/matplotlib.figure.Figure.colorbar.html). | `false` (default) or `true` | `properties.drawedges` |

Location, fraction, shrink, aspect, pad, extend, spacing, and draw-edges edits
reconstruct the Matplotlib Colorbar transactionally. The same Inspector and
Controller identities remain active. A construction or render failure restores
the original Colorbar object, auxiliary Axes, Locator binding, source callback,
owner geometry/anchor, selection, and state without publishing an event.

## Source refresh and deletion

Changes to Scatter scalar colors, colormap, normalization, or table data update
the existing Colorbar through `ColorbarService`; the Colorbar state does not
copy those values. Scalar color mapping cannot be disabled while a dependent
Colorbar exists. Delete the Colorbar first.

- Deleting a Colorbar preserves its source Scatter.
- Deleting the source Scatter plans and removes its Colorbar in the same
  `DeletionCoordinator` transaction.
- Deleting the owner Axes removes the Colorbar and its auxiliary Axes with the
  complete Axes subtree.

## Persistence

Schema v13 stores Colorbar with the standard eight-field `ComponentState`
record, owner Axes `parent_id`, `selector.object_id`, complete properties, and
`data.source_component_id`. Restore materializes ordinary charts and Scatter
sources before the later Colorbar phase. Missing, wrong-kind, cross-Axes,
mapping-disabled, or duplicate source relationships are rejected before the
project tab is published.

## Referenced Matplotlib 3.9.0 pages

- [`Figure.colorbar`](https://matplotlib.org/3.9.0/api/_as_gen/matplotlib.figure.Figure.colorbar.html)
- [Colorbar API](https://matplotlib.org/3.9.0/api/colorbar_api.html)
- [Ticker API](https://matplotlib.org/3.9.0/api/ticker_api.html)
- [Text API](https://matplotlib.org/3.9.0/api/text_api.html)
