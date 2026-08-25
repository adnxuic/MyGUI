| Inspector field | Control | Meaning | Values / default | Persisted / runtime key |
| --- | --- | --- | --- | --- |
| Span Start | Number | Start of the orthogonal span in Axes-fraction coordinates. | Finite `0.0 <= span_start <= 1.0`; default `0.0`; must be less than Span End | `properties.span_start` |
| Span End | Number | End of the orthogonal span in Axes-fraction coordinates. | Finite `0.0 <= span_end <= 1.0`; default `1.0`; must be greater than Span Start | `properties.span_end` |
| Zorder | Number | Draw order relative to other Artists through [`Artist.set_zorder`](https://matplotlib.org/3.9.0/api/_as_gen/matplotlib.artist.Artist.set_zorder.html). | Finite number; default `2.0` (line) / `1.5` (band) | `properties.zorder` |
| Clip On | Checkbox | Enables Axes clipping through [`Artist.set_clip_on`](https://matplotlib.org/3.9.0/api/_as_gen/matplotlib.artist.Artist.set_clip_on.html). | `true` or `false`; default `true` | `properties.clip_on` |
