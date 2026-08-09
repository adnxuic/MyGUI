# Fitting

This document describes the fitting feature and its user-facing parameters.

## Feature

- A fitting curve uses selected X/Y table data.
- Each fitting curve owns its data selectors, result display, style controls, and engine buttons.
- Engines are selected per fitting curve:
  - `SciPy`: uses the project Python environment.
  - `Matlab`: uses optional MATLAB Runtime / MATLAB Compiler packages.
- Missing MATLAB must not block base GUI startup or SciPy fitting.
- Fit result expressions are evaluated through `safe_expression`.

## Workflow

1. Create or select a fitting curve.
2. Select X data and Y data.
3. Click `SciPy` or `Matlab`.
4. Choose fit type and order.
5. Enable advanced options if needed.
6. Click `Fit`.

The fit options dialog is non-modal. If the dialog is closed before a background fit returns, the result is ignored.

## Data Parameters

| Parameter | Required | Description |
| --- | --- | --- |
| X Data | Yes | Source column for X values. |
| X expression | Yes | Element-wise preprocessing formula. Default `x`. |
| Y Data | Yes | Source column for Y values. |
| Y expression | Yes | Element-wise preprocessing formula. Default `y`. |

Rules:

- X and Y must be non-empty.
- X and Y must have the same length.
- X and Y preprocessing is evaluated from the original row-aligned values.
- Rows with missing or non-finite transformed values are removed as pairs.
- At least one finite transformed pair must remain.
- Some models require stricter domains, such as positive or non-negative X values.

Changing a source or preprocessing expression invalidates any running request
and preserves the previous curve/result until the user explicitly fits again.
The fit dialog range uses the minimum and maximum preprocessed X values.

## Fit Types

- Polynomial: `poly1` through `poly9`
- Exponential: `exp1`, `exp2`
- Logarithmic: `log`
- Gaussian: `gauss1` through `gauss8`
- Power: `power1`, `power2`
- Sine: `sin1` through `sin8`
- Fourier: `fourier1` through `fourier8`
- Weibull: `weibull`
- Sigmoid: `logistic`, `logistic4`, `gompertz`
- Rational: `rat01` through `rat55`

High-order Gaussian, Fourier, and rational models can be numerically sensitive.

## Result Fields

| Field | Description |
| --- | --- |
| `value_expression` | Python-safe expression used to redraw the curve. |
| `show_expression` | Expression shown in the UI. |
| `formula` | Formula text for the selected model. |
| `fit_type` | Selected fit type, such as `poly2`. |
| `coefficients` | Coefficient names, fitted values, and confidence bounds when available. |
| `goodness` | Fit metrics: SSE, R-square, adjusted R-square, DFE, and RMSE. |
| `confidence_level` | Confidence level used for coefficient bounds. |

A failed fit does not update the plotted curve or result table.

## Project Files

Fitting curves are saved in schema v9 as `line/fit_curve` components. Their visual state is stored in `properties`, while references, preprocessing expressions, fitting options, result data, expression, and evaluation range are stored in `data`.
Saved records include a stable `object_id`, X/Y `ColumnRef` objects, fitting engine, fit type,
advanced options when used, fit result, drawing expression, X range, style,
color, and legend label.

Opening a project restores fitting curves from the saved drawing expression and
result payload. It does not rerun SciPy or MATLAB fitting during load. MATLAB
fit results can therefore be viewed without reconnecting MATLAB, but running a
new MATLAB fit still requires a successful MATLAB connection.

## SciPy Engine

SciPy fitting uses `code/database/scipy_fit_models.py` and `code/database/scipy_fit_adapter.py`.

SciPy does not call MATLAB code.

### SciPy Options

| Option | Applies To | Description |
| --- | --- | --- |
| `Lower` | All models | Per-coefficient lower bounds. |
| `Upper` | All models | Per-coefficient upper bounds. |
| `StartPoint` | Nonlinear models | Per-coefficient initial values. Leave all blank to use defaults. |
| `Tol` | Linear bounded fits | Solver tolerance. |
| `MaxIter` | Linear bounded fits | Maximum iterations. |
| `OptimizerMethod` | Nonlinear models | `trf`, `dogbox`, or `lm`; `lm` cannot be used with bounds. |
| `Loss` | Nonlinear models | `linear`, `soft_l1`, `huber`, `cauchy`, or `arctan`. |
| `FScale` | Nonlinear robust loss | Robust loss scale. |
| `MaxNfev` | Nonlinear models | Maximum function evaluations. |
| `FTol` | Nonlinear models | Cost-function tolerance. |
| `XTol` | Nonlinear models | Step-size tolerance. |
| `GTol` | Nonlinear models | Gradient tolerance. |
| `DiffStep` | Nonlinear models | Finite-difference step. |
| `XScale` | Nonlinear models | Parameter scaling value, vector, or `jac`. |

## MATLAB Engine

MATLAB fitting depends on local MATLAB Runtime or MATLAB plus generated MATLAB Compiler Python packages.

The `Matlab` button is enabled only after the global MATLAB connection check succeeds.

Expected package signatures:

```text
get_func(func_name, nargout=3)
curve_fitting(x, y, fit_type, options_json, nargout=6)
```

Old generated package signatures are not supported.

### MATLAB Options

| Option | Applies To | Description |
| --- | --- | --- |
| `Method` | All models | Read-only MATLAB fit method. |
| `Normalize` | All models | MATLAB normalize option. |
| `Robust` | All models | MATLAB robust fitting mode. |
| `TolCon` | All models | MATLAB constraint tolerance. |
| `Lower` | All models | Per-coefficient lower bounds. |
| `Upper` | All models | Per-coefficient upper bounds. |
| `StartPoint` | Nonlinear models | Per-coefficient initial values. Leave all blank to use MATLAB defaults. |
| `Algorithm` | Nonlinear models | MATLAB nonlinear algorithm. |
| `DiffMinChange` | Nonlinear models | Minimum finite-difference change. |
| `DiffMaxChange` | Nonlinear models | Maximum finite-difference change. |
| `MaxFunEvals` | Nonlinear models | Maximum function evaluations. |
| `MaxIter` | Nonlinear models | Maximum iterations. |
| `TolFun` | Nonlinear models | Function tolerance. |
| `TolX` | Nonlinear models | Parameter tolerance. |

### MATLAB Runtime Settings

| Environment Variable | Description |
| --- | --- |
| `MYGUI_MATLAB_CONNECT_TIMEOUT_SECONDS` | MATLAB connection check timeout. |
| `MYGUI_MATLAB_EXPRESSION_TIMEOUT_SECONDS` | MATLAB expression metadata timeout. |
| `MYGUI_MATLAB_FIT_TIMEOUT_SECONDS` | MATLAB fitting timeout. |
| `MYGUI_MATLAB_CONNECT_INITIALIZE_PACKAGES` | Initializes generated packages during connection check when enabled. |
| `MYGUI_MATLAB_LOG_LEVEL` | MATLAB log level. |
| `MYGUI_MATLAB_LOG_DIR` | MATLAB log directory. |
| `MYGUI_MATLAB_MCR_CACHE_ROOT` | Custom MATLAB Runtime cache root. |
| `MCR_CACHE_ROOT` | External MATLAB Runtime cache root. |

Default local paths:

```text
logs/matlab.log
.matlab_runtime_cache/runtime/<key>
```
