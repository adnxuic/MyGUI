# Interpolation

MyGUI creates interpolation curves from two saved table columns. The X column is treated as the independent variable and the Y column as `y=f(x)`. Curves are evaluated on a dense X domain between the minimum and maximum source X values.

## Methods

| Method | Behavior |
| --- | --- |
| `三次样条插值` | SciPy `CubicSpline`, a smooth cubic spline with continuous first and second derivatives. |
| `B样条插值` | SciPy `make_interp_spline`, with configurable spline degree `k`. |
| `线性插值` | Piecewise linear interpolation using `numpy.interp`. |
| `最近邻插值` | Uses the nearest source point value for each sampled X value. |
| `前值阶梯插值` | Uses the previous source point value for each sampled X value. |
| `后值阶梯插值` | Uses the next source point value for each sampled X value. |
| `PCHIP保形插值` | SciPy `PchipInterpolator`, a monotonicity-preserving cubic interpolator. |
| `Akima插值` | SciPy `Akima1DInterpolator(method="akima")`, useful for a smooth visual curve through precise data. |
| `Makima插值` | SciPy `Akima1DInterpolator(method="makima")`, the modified Akima variant. |
| `平滑样条` | SciPy `make_smoothing_spline`, a smoothing approximation controlled by lambda. |

## Parameters

| Parameter | Applies to | Description |
| --- | --- | --- |
| `Method` | All interpolation curves | Selects the interpolation algorithm. |
| `X Data` | All interpolation curves | Source table column for X values. Changing it recomputes the interpolation curve. |
| `X expression` | All interpolation curves | Element-wise X preprocessing formula. Default is `x`. |
| `Y Data` | All interpolation curves | Source table column for Y values. Changing it recomputes the interpolation curve. |
| `Y expression` | All interpolation curves | Element-wise Y preprocessing formula. Default is `y`. |
| `Samples` | All interpolation curves | Number of output points drawn on the chart. Default is `1000`; valid range is `2` to `100000`. |
| `k` | `B样条插值` | B-spline degree. Valid range is `1` to `5`, and `k` must be smaller than the number of source data points. |
| `Auto lambda` | `平滑样条` | Lets SciPy choose the smoothing lambda automatically. |
| `Lambda` | `平滑样条` | Manual non-negative smoothing lambda used when `Auto lambda` is disabled. Larger values produce smoother curves. |
| `Color` | All interpolation curves | Line color for the interpolation curve. |
| `Legend` | All interpolation curves | Matplotlib label shown in the axes legend. |

The Interpolation Inspector section exposes the same parameters and recomputes the curve after each change. Its controls are summarized in [Chart Component Parameters](chart-component-parameters.md).

## Data Requirements

- X and Y must be numeric columns. Their values are aligned by Table row.
- Both preprocessing expressions read the original X/Y values and run before
  interpolation.
- Rows with a missing or non-finite source/transformed value are filtered as a pair before interpolation.
- At least 2 source points are required for interpolation.
- X values are sorted before interpolation.
- Duplicate X values are rejected because they overspecify `y=f(x)`.
- `平滑样条` requires at least 5 source points.

## Project Files

Interpolation records are saved as schema-v14 `line/interpolation` components.
Each record has a stable `object_id`, `x_ref`, `y_ref`, and `preprocess`, plus
these interpolation parameters:

| Field | Description |
| --- | --- |
| `samples` | Saved output sample count. |
| `lam_auto` | Whether smoothing lambda is automatic. |
| `lam` | Manual smoothing lambda. `null` means no manual lambda is saved. |

Invalid interpolation input is reported through the Message Bar in red. Successful create and update actions are reported in green.
