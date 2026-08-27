# Data Preprocessing

Plot, Scatter, Interpolation, and Fit components can transform their selected
table columns without changing the table itself. Each data selector includes
an inline `fx` field for X and Y. The default expressions are `x` and `y`.

Both expressions read the original row-aligned X/Y values and are evaluated
independently. For example, X = `1/x` and Y = `y` draws the selected Y data
against reciprocal X; Y = `y/x` still uses the original X values.

## Parameters

| Parameter | Default | Description |
| --- | --- | --- |
| X Data | — | Number or date/time source column bound to the variable `x`. |
| X expression | `x` | Element-wise expression that produces plotted or analyzed X values. |
| Y Data | — | Number source column bound to the variable `y`. |
| Y expression | `y` | Element-wise expression that produces plotted or analyzed Y values. |

Variable names are lowercase and case-sensitive. Expressions may use `x`,
`y`, numeric constants, `pi`, `e`, arithmetic operators, powers, `abs`,
trigonometric and inverse-trigonometric functions, hyperbolic functions,
`exp`, `log`, `log10`, and `sqrt`. Supported functions may also use their
`np.` or `numpy.` form.

Expressions are limited to 512 characters, 128 syntax nodes, and 32 levels of
syntax nesting. Integer constants are limited to 256 bits, exponent magnitude
is limited to 64, and intermediate arrays are limited to 2,000,000 elements.
The evaluator interprets the validated syntax tree directly and never calls
Python `eval`. Results may be scalar values, which are broadcast to all
rows, or one-dimensional real numeric arrays matching the source row count.
Unknown names, arbitrary attributes or calls, indexing, conditions, lambdas,
collections, Boolean values, complex values, objects, and mismatched shapes
are rejected.

For a date/time X column, the X expression must remain `x`, and the Y
expression cannot reference `x`. This preserves the date axis without an
implicit conversion unit.

## Component behavior

- Plot keeps row positions and turns invalid transformed pairs into line gaps.
- Scatter, Interpolation, and Fit remove invalid transformed pairs together.
- Plot and Scatter update immediately when a source or expression changes.
- Interpolation applies preprocessing before sorting and interpolation, and
  recomputes when its source, expression, or interpolation options change.
- Fit saves source/expression changes but keeps the previous result until the
  user starts a new SciPy or MATLAB fit. Both engines receive the same
  preprocessed values.

Missing values and non-finite expression results produce one yellow Message
Bar warning with the excluded-row count. Invalid expressions produce one red
error and leave the controls, component state, and artist unchanged.

## Project data

Each data-backed component stores the following schema-v17 object inside its
role-specific `data` record:

```json
"preprocess": {
  "x_expression": "x",
  "y_expression": "y"
}
```

Every schema-v17 data-backed component contains this object. Parsed syntax
trees, evaluated arrays, masks, and editor state are runtime-only.
