"""Widget-free fitting service shared by templates and Fit UI workflows."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Callable

import numpy as np
import pandas as pd

from mygui.database import ColumnRef, DataPreprocessSpec, preprocess_aligned_pair
from mygui.database.fit_result import (
    normalize_fit_options_for_storage,
    normalize_fit_result_for_storage,
)
from mygui.database.table_repository import AlignedPair
from mygui.figuremodify.components import ComponentRole, FitEngine


@dataclass(frozen=True, slots=True)
class FitExecutionResult:
    """One completed fit ready to insert into persisted component data."""

    fit_result: dict[str, Any]
    expression: str
    x_start: float
    x_stop: float


def _plot_values(series: pd.Series) -> np.ndarray:
    if pd.api.types.is_datetime64_any_dtype(series.dtype):
        return series.to_numpy(dtype="datetime64[ns]")
    try:
        return series.to_numpy(dtype=float, na_value=np.nan)
    except (TypeError, ValueError) as exc:
        raise ValueError("Selected data column must be numeric or date/time.") from exc


def _document_pair(project, x_ref: ColumnRef, y_ref: ColumnRef) -> AlignedPair:
    if x_ref.project_id != project.id or y_ref.project_id != project.id:
        raise ValueError("Fit references must belong to the staged project.")
    x_series = project.sheets[x_ref.sheet_id].frame[x_ref.column_id].copy(deep=True)
    y_series = project.sheets[y_ref.sheet_id].frame[y_ref.column_id].copy(deep=True)
    if len(x_series) != len(y_series):
        raise ValueError("Data columns must belong to row-aligned Sheets.")
    occupied = (x_series.notna() | y_series.notna()).to_numpy(dtype=bool)
    if occupied.any():
        stop = int(np.flatnonzero(occupied)[-1]) + 1
        x_series = x_series.iloc[:stop]
        y_series = y_series.iloc[:stop]
    else:
        x_series = x_series.iloc[:0]
        y_series = y_series.iloc[:0]
    valid = (x_series.notna() & y_series.notna()).to_numpy(dtype=bool)
    x = _plot_values(x_series)
    y = _plot_values(y_series)
    if np.issubdtype(x.dtype, np.datetime64):
        x = x.astype("datetime64[ns]")
        x[~valid] = np.datetime64("NaT")
    else:
        x = x.astype(float, copy=True)
        x[~valid] = np.nan
    y = y.astype(float, copy=True)
    y[~valid] = np.nan
    return AlignedPair(x, y, valid, int((~valid).sum()))


class FitExecutionService:
    """Execute configured fits without accessing QWidget or live Artists."""

    def execute_arrays(
        self,
        x,
        y,
        fit_type: str,
        fit_options: dict[str, Any] | None,
        *,
        engine: FitEngine | str,
    ) -> dict[str, Any]:
        """Run one adapter against immutable arrays and normalize its result."""

        engine = FitEngine(engine)
        options = normalize_fit_options_for_storage(fit_options)
        if not isinstance(fit_type, str) or not fit_type.strip():
            raise ValueError("Fit Curve is missing a configured model.")
        x_values = np.asarray(x).copy()
        y_values = np.asarray(y).copy()
        if engine is FitEngine.MATLAB:
            from mygui.database import matlab_adapter

            status = matlab_adapter.matlab_status()
            if not status.available:
                raise RuntimeError(status.message or "MATLAB is not connected.")
            raw_result = matlab_adapter.fit_curve_isolated(
                x_values.tolist(), y_values.tolist(), fit_type, options
            )
        else:
            from mygui.database import scipy_fit_adapter

            raw_result = scipy_fit_adapter.fit_curve(
                x_values, y_values, fit_type, options
            )
        result = normalize_fit_result_for_storage(raw_result)
        if result is None:
            raise RuntimeError("Fitting returned no result.")
        return result

    def execute(self, project, component: dict[str, Any]) -> FitExecutionResult:
        """Execute and normalize one Fit component against a staged document."""

        if component.get("role") != ComponentRole.FIT_CURVE.value:
            raise ValueError("Fit execution requires a Fit Curve component.")
        data = component["data"]
        fit_type = data.get("fit_type")
        options = data.get("fit_options")
        x_ref = ColumnRef.from_dict(data["x_ref"])
        y_ref = ColumnRef.from_dict(data["y_ref"])
        pair = preprocess_aligned_pair(
            _document_pair(project, x_ref, y_ref),
            DataPreprocessSpec.from_dict(data["preprocess"]),
            preserve_gaps=False,
        )
        if pair.x.size == 0:
            raise ValueError("Fit Curve has no valid data after preprocessing.")
        result = self.execute_arrays(
            pair.x,
            pair.y,
            fit_type,
            options,
            engine=data["engine"],
        )
        expression = result.get("value_expression")
        if not isinstance(expression, str) or not expression.strip():
            raise RuntimeError("Fitting returned no drawable expression.")
        numeric_x = np.asarray(pair.x, dtype=float)
        return FitExecutionResult(
            result,
            expression,
            float(np.min(numeric_x)),
            float(np.max(numeric_x)),
        )

    def execute_all(
        self,
        project,
        figure: dict[str, Any],
        *,
        cancelled: Callable[[], bool] | None = None,
        progress: Callable[[int, int, str], None] | None = None,
    ) -> tuple[str, ...]:
        """Run configured fits sequentially and mutate only the staged blueprint."""

        fits = [
            component
            for component in figure["components"]
            if component["role"] == ComponentRole.FIT_CURVE.value
        ]
        completed: list[str] = []
        for index, component in enumerate(fits, start=1):
            if cancelled is not None and cancelled():
                raise RuntimeError("Template application was cancelled.")
            if progress is not None:
                progress(index - 1, len(fits), str(component["properties"].get("label", "Fit")))
            result = self.execute(project, component)
            component["data"].update(
                fit_result=deepcopy(result.fit_result),
                expression=result.expression,
                x_start=result.x_start,
                x_stop=result.x_stop,
            )
            completed.append(component["id"])
        if progress is not None:
            progress(len(fits), len(fits), "Fitting complete")
        return tuple(completed)
