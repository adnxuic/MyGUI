| Inspector field | Control | Meaning | Values / default | Persisted / runtime key |
| --- | --- | --- | --- | --- |
| Clip On | Checkbox | Clips the artist to the Axes bounding box. | `true` or `false`; default `true` | `properties.clip_on` |
| Gid | Text | SVG group identifier used in vector exports. | String or none; default none | `properties.gid` |
| In Layout | Checkbox | Includes the artist in tight-layout and constrained-layout calculations. | `true` or `false`; default `true` | `properties.in_layout` |
| Rasterized | Checkbox | Forces bitmap rasterization during vector export. See [`Artist.set_rasterized`](https://matplotlib.org/3.9.0/api/artist_api.html#matplotlib.artist.Artist.set_rasterized). | `true` or `false`; default `false` | `properties.rasterized` |
| Snap | Dropdown | Pixel snapping: auto (`None`), on (`True`), or off (`False`). See [`Artist.set_snap`](https://matplotlib.org/3.9.0/api/artist_api.html#matplotlib.artist.Artist.set_snap). | `None`, `True`, `False`; default None | `properties.snap` |
| Url | Text | Hyperlink URL attached to the artist in SVG export. | Valid URL string or none; default none | `properties.url` |
