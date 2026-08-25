# Reflection Positions Component

The **Reflection Positions** component renders diffraction peak marks as short vertical tick marks inside an ordinary Axes. It is backed by one `LineCollection` using data coordinates along X and normalized Axes coordinates along Y via [`Axes.get_xaxis_transform`](https://matplotlib.org/3.9.0/api/_as_gen/matplotlib.axes.Axes.get_xaxis_transform.html).

Changing the X limits moves or clips the marks along with the data, while changing Y limits preserves their relative vertical positioning.

For XRD refinement workflows and feature guides, see [Reference Marks Component](../../reference-marks-component.md).

## General

--8<-- "_snippets/components/reference_guides/reference-guide-general.md"

## Position

| Inspector field | Control | Meaning | Values / default | Persisted / runtime key |
| --- | --- | --- | --- | --- |
| Baseline | Number | Lower Y position in normalized Axes coordinates (0 to 1). Automatic `between_table_ranges` keeps this read-only until Convert to fixed position. | Finite `0.0 <= baseline <= 1.0`; default `0.08` | `properties.baseline` |
| Height | Number | Mark height in normalized Axes coordinates (0 to 1). | Finite `0.0 < height <= 1.0`; default `0.025`; `baseline + height <= 1` | `properties.height` |

## Line

| Inspector field | Control | Meaning | Values / default | Persisted / runtime key |
| --- | --- | --- | --- | --- |
| Color | Color choice | Uniform stroke color for all reflection tick marks. | Hex color; default `#000000` (or style tick color) | `properties.color` |
| Linewidth | Number | Stroke width of reflection tick marks in points. | Finite number `>= 0`; default `0.8` | `properties.linewidth` |
| Linestyle | Line-style choice | Stroke dash pattern of reflection tick marks. | Preset or dash tuple; default `-` | `properties.linestyle` |
| Alpha | Number | Collection opacity factor from 0 to 1. | Finite `0 <= alpha <= 1`; default `1.0` | `properties.alpha` |

## Advanced

| Inspector field | Control | Meaning | Values / default | Persisted / runtime key |
| --- | --- | --- | --- | --- |
| Zorder | Number | Stacking order relative to other artists in the Axes. | Finite number; default `2.0` | `properties.zorder` |
| Clip On | Checkbox | Enables Axes clipping through [`Artist.set_clip_on`](https://matplotlib.org/3.9.0/api/_as_gen/matplotlib.artist.Artist.set_clip_on.html). | `true` or `false`; default `true` | `properties.clip_on` |

## Data

| Inspector field | Control | Meaning | Values / default | Persisted / runtime key |
| --- | --- | --- | --- | --- |
| Positions | Sequence text plus Apply | Manual ordered reflection position sequence. Combined with the Table column when present. | Comma- or space-separated numbers; default empty | `data.positions` |
| Table Column | Column selector plus Apply | Optional current-project Number column appended after manual positions. | Project column or None; default None | `data.position_ref` |
| Placement Sources | Read-only labels / Convert action | Shows fixed placement or the three Table columns bounding automatic vertical placement. | `fixed` or `between_table_ranges`; default `fixed` | `data.placement` |

## FullProf .prf & XRD Workflow Integration

The optional FullProf `.prf` workflow in the **Single Axes** and **Main Plot + Residual** dialogs uses this same component:

- XRD Reflection Positions store `positions: []` and bind `position_ref` to the imported `<source> Reflections/2Theta` column instead of copying PRF numbers.
- Main Plot + Residual and Single without residual use `placement: {"kind": "fixed"}` with `baseline=0.0375` and `height=0.025` so marks occupy the center of the 10% lower-Y reserve (`3.75%–6.25%` of Axes height).
- Single with **Draw residual** uses `placement: {"kind": "between_table_ranges"}` so marks stay centered between the `Yobs-Ycal (PRF)` maximum and lowest `Yobs`/`Ycal` values after ordinary autoscale.
- Ordinary Reflection Positions keep `baseline=0.08` and `height=0.025` and do not change the owning Axes reserve.

## Project record

Schema v15 persists Reflection Positions as `kind: "reference_marks"`, `role: "reflection_positions"`, with `selector: {"object_id": component_id}` under its parent Axes. The `data` object contains `positions`, nullable `position_ref`, and tagged `placement`.

## Referenced Matplotlib 3.9.0 URLs

- [LineCollection API](https://matplotlib.org/3.9.0/api/collections_api.html#matplotlib.collections.LineCollection)
- [Axes.get_xaxis_transform](https://matplotlib.org/3.9.0/api/_as_gen/matplotlib.axes.Axes.get_xaxis_transform.html)
- [Artist set_alpha](https://matplotlib.org/3.9.0/api/_as_gen/matplotlib.artist.Artist.set_alpha.html)
- [Artist set_zorder](https://matplotlib.org/3.9.0/api/_as_gen/matplotlib.artist.Artist.set_zorder.html)
- [Artist set_clip_on](https://matplotlib.org/3.9.0/api/_as_gen/matplotlib.artist.Artist.set_clip_on.html)
