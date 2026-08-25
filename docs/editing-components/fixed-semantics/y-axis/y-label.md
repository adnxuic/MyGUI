# Y Label Component

The **Y Label** component represents the dimensional label of the vertical Y Axis. It provides complete typography formatting, alignment, multiline wrapping, Mathtext equations, and optional LaTeX typesetting.

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

For details on LaTeX configuration, see [TeX Rendering Integration](../../../tex-integration.md).

## Advanced

--8<-- "_snippets/components/text/text-advanced.md"

## Project record

Schema v15 persists Y Label as `kind: "text"`, `role: "y_label"`, with `selector: {"axis_name": "y"}` under its parent Axes.

## Referenced Matplotlib 3.9.0 URLs

- [Text API](https://matplotlib.org/3.9.0/api/text_api.html#matplotlib.text.Text)
- [Mathtext guide](https://matplotlib.org/3.9.0/users/explain/text/mathtext.html)
- [Artist sketch params](https://matplotlib.org/3.9.0/api/artist_api.html#matplotlib.artist.Artist.set_sketch_params)
- [Artist snap](https://matplotlib.org/3.9.0/api/artist_api.html#matplotlib.artist.Artist.set_snap)
