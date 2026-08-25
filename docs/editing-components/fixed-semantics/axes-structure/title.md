# Title Component

The **Title** component represents the primary text header of an Axes. It supports full typography styling, math expressions via Mathtext, optional external LaTeX typesetting via `usetex`, background bounding boxes, and arbitrary rotation and alignment.

## Content

--8<-- "_snippets/components/text/text-content.md"

## Typography

--8<-- "_snippets/components/text/text-typography.md"

## Rotation and alignment

--8<-- "_snippets/components/text/text-transform.md"

## Position and visibility

--8<-- "_snippets/components/text/text-position-fixed.md"

## Rendering

--8<-- "_snippets/components/text/text-render.md"

For details on configuring system LaTeX, see [TeX Rendering Integration](../../../tex-integration.md).

## Advanced

--8<-- "_snippets/components/text/text-advanced.md"

## Project record

Schema v15 persists the Title as `kind: "text"`, `role: "title"`, with `selector: {"object_id": component_id}` under its parent Axes.

## Referenced Matplotlib 3.9.0 URLs

- [Text API](https://matplotlib.org/3.9.0/api/text_api.html#matplotlib.text.Text)
- [Mathtext guide](https://matplotlib.org/3.9.0/users/explain/text/mathtext.html)
- [Artist sketch params](https://matplotlib.org/3.9.0/api/artist_api.html#matplotlib.artist.Artist.set_sketch_params)
- [Artist snap](https://matplotlib.org/3.9.0/api/artist_api.html#matplotlib.artist.Artist.set_snap)
