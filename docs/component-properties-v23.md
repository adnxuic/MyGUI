# Component Properties (schema v23)

Schema v23 retains the exact eight-field `ComponentState` record and every
schema-v22 property contract:

```text
id, kind, role, parent_id, order, selector, properties, data
```

It adds the leaf `secondary_axis` kind with `secondary_x_axis` and
`secondary_y_axis` roles. A Secondary Axis owns only a reversible unit mapping,
placement, visibility, label, ticker, tick appearance, spine appearance, and
z-order. Its `data` is exactly `{}`. It never owns data series, limits, scale,
autoscale, aspect, or a normal Axes semantic subtree. See
[Secondary Axis / Unit Transform](secondary-axis-component.md) for the full
property table and tagged value formats.

## Migration

New projects save exact integer `schema_version: 23`. A strict v22 project is
fully validated, deep-copied, and advanced to v23 without changing any Figure,
Table, component ID, parent, order, selector, property, or data content.
Secondary Axis records are rejected by every predecessor validator.

Chart templates use independent schema v7 with a schema-v23 Figure blueprint.
A strict template-v6/schema-v22 blueprint advances to v7 without Figure
content changes.

The complete predecessor ticker contract remains in
[Component Properties (schema v22)](component-properties-v22.md).

