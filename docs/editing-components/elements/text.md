# Text Component

The **Text** component represents a free-floating or coordinate-anchored text annotation in the Figure or an Axes.

For workflow guides and text element positioning, see [Text Element](../../text-element.md).

## Content

--8<-- "_snippets/components/text/text-content.md"

## Typography

--8<-- "_snippets/components/text/text-typography.md"

## Rotation and alignment

--8<-- "_snippets/components/text/text-transform.md"

## Position and visibility

| Inspector field | Control | Meaning | Values / default | Persisted / runtime key |
| --- | --- | --- | --- | --- |
| Position | Position editor | Text anchor coordinates `(x, y)` in the selected coordinate system. | Tuple of 2 numbers; default `[0.0, 0.0]` | `properties.position` |
| Visible | Checkbox | Shows or hides the text artist. | `true` or `false`; default `true` | `properties.visible` |
| Zorder | Number | Stacking order of the text artist. | Finite number; default `3.0` | `properties.zorder` |
| Coordinate System | Dropdown | Coordinate reference frame: `data`, `axes`, or `figure`. | `data`, `axes`, `figure`; default `data` | `properties.coordinate_system` |

## Rendering

--8<-- "_snippets/components/text/text-render.md"

For LaTeX details, see [TeX Rendering Integration](../../tex-integration.md).

## Advanced

--8<-- "_snippets/components/text/text-advanced.md"

## Project record

Schema v15 persists standalone Text as `kind: "text"`, `role: "text"`, with `selector: {"object_id": component_id}` under its parent Figure or Axes.

## Referenced Matplotlib 3.9.0 URLs

- [Text API](https://matplotlib.org/3.9.0/api/text_api.html#matplotlib.text.Text)
- [Mathtext guide](https://matplotlib.org/3.9.0/users/explain/text/mathtext.html)
- [Artist sketch params](https://matplotlib.org/3.9.0/api/artist_api.html#matplotlib.artist.Artist.set_sketch_params)
- [Artist snap](https://matplotlib.org/3.9.0/api/artist_api.html#matplotlib.artist.Artist.set_snap)
