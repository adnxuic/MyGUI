# Minor Ticks Component

The **Minor Ticks** component controls the appearance, length, stroke width, and direction of tick mark protrusions at minor tick positions.

These properties remain editable from this child Inspector and from the
owning X/Y Axis **Ticks & Labels** dialog. The unified dialog previews them and
commits Locator, Formatter, Tick, and Tick Label changes atomically.

## Properties

--8<-- "_snippets/components/ticks/tick-properties.md"

## Advanced

--8<-- "_snippets/components/ticks/tick-advanced.md"

## Project record

Schema v15 persists Minor Ticks as `kind: "tick_group"`, `role: "minor_tick"`, with `selector: {"axis_name": "x", "group_type": "minor"}` under its parent Axes.

## Referenced Matplotlib 3.9.0 URLs

- [Tick API](https://matplotlib.org/3.9.0/api/axis_api.html#matplotlib.axis.Tick)
- [Axis ticks guide](https://matplotlib.org/3.9.0/users/explain/axes/axes_ticks.html)
- [Artist sketch params](https://matplotlib.org/3.9.0/api/artist_api.html#matplotlib.artist.Artist.set_sketch_params)
- [Artist snap](https://matplotlib.org/3.9.0/api/artist_api.html#matplotlib.artist.Artist.set_snap)
