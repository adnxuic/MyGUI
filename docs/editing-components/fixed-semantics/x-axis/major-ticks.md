# Major Ticks Component

The **Major Ticks** component controls the appearance, length, stroke width, and direction of tick mark protrusions at major tick positions.

## Properties

--8<-- "_snippets/components/ticks/tick-properties.md"

## Advanced

--8<-- "_snippets/components/ticks/tick-advanced.md"

## Project record

Schema v15 persists Major Ticks as `kind: "tick_group"`, `role: "major_tick"`, with `selector: {"axis_name": "x", "group_type": "major"}` under its parent Axes.

## Referenced Matplotlib 3.9.0 URLs

- [Tick API](https://matplotlib.org/3.9.0/api/axis_api.html#matplotlib.axis.Tick)
- [Artist sketch params](https://matplotlib.org/3.9.0/api/artist_api.html#matplotlib.artist.Artist.set_sketch_params)
- [Artist snap](https://matplotlib.org/3.9.0/api/artist_api.html#matplotlib.artist.Artist.set_snap)
