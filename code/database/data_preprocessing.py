"""Resolve table-backed X/Y data through safe component-local expressions."""

from __future__ import annotations

import ast
from dataclasses import dataclass
from typing import Any, Mapping

import numpy as np

from .safe_expression import compile_math_expression, evaluate_math_expression
from .table_document import ColumnRef


MAX_PREPROCESS_EXPRESSION_LENGTH = 512
MAX_PREPROCESS_AST_NODES = 128
MAX_PREPROCESS_AST_DEPTH = 32


def _ast_depth(node: ast.AST) -> int:
    children = tuple(ast.iter_child_nodes(node))
    if not children:
        return 1
    return 1 + max(_ast_depth(child) for child in children)


def _compile_preprocess_expression(expression: str, axis: str) -> ast.Expression:
    if not isinstance(expression, str) or not expression.strip():
        raise ValueError(f"{axis.upper()} preprocessing expression must be non-empty.")
    if len(expression) > MAX_PREPROCESS_EXPRESSION_LENGTH:
        raise ValueError(
            f"{axis.upper()} preprocessing expression exceeds "
            f"{MAX_PREPROCESS_EXPRESSION_LENGTH} characters."
        )
    parsed = compile_math_expression(expression, {"x", "y"})
    if any(
        isinstance(node, ast.Constant)
        and isinstance(node.value, (bool, np.bool_))
        for node in ast.walk(parsed)
    ):
        raise ValueError(
            f"{axis.upper()} preprocessing expression cannot use boolean constants."
        )
    if sum(1 for _node in ast.walk(parsed)) > MAX_PREPROCESS_AST_NODES:
        raise ValueError(
            f"{axis.upper()} preprocessing expression is too complex."
        )
    if _ast_depth(parsed) > MAX_PREPROCESS_AST_DEPTH:
        raise ValueError(
            f"{axis.upper()} preprocessing expression is nested too deeply."
        )
    return parsed


def _is_identity_expression(expression: str, variable: str) -> bool:
    parsed = _compile_preprocess_expression(expression, variable)
    return isinstance(parsed.body, ast.Name) and parsed.body.id == variable


def _expression_uses(expression: str, variable: str) -> bool:
    parsed = _compile_preprocess_expression(expression, variable)
    return any(
        isinstance(node, ast.Name) and node.id == variable
        for node in ast.walk(parsed)
    )


@dataclass(frozen=True, slots=True)
class DataPreprocessSpec:
    """Persisted X/Y preprocessing expressions for one data-backed component."""

    x_expression: str = "x"
    y_expression: str = "y"

    def __post_init__(self) -> None:
        _compile_preprocess_expression(self.x_expression, "x")
        _compile_preprocess_expression(self.y_expression, "y")

    @property
    def is_identity(self) -> bool:
        """Return whether both axes use their exact identity expressions."""

        return _is_identity_expression(
            self.x_expression, "x"
        ) and _is_identity_expression(self.y_expression, "y")

    def to_dict(self) -> dict[str, str]:
        """Return the strict JSON representation used by component state."""

        return {
            "x_expression": self.x_expression,
            "y_expression": self.y_expression,
        }

    def validate_datetime_x(self) -> None:
        """Validate the restricted expression contract for a date/time X axis."""

        if not _is_identity_expression(self.x_expression, "x"):
            raise ValueError(
                "Date/time X data only supports the identity preprocessing "
                "expression 'x'. Convert the column to numeric data first."
            )
        if _expression_uses(self.y_expression, "x"):
            raise ValueError(
                "Y preprocessing cannot reference date/time X data. "
                "Convert the X column to numeric data first."
            )

    @classmethod
    def from_dict(
        cls,
        value: "DataPreprocessSpec | Mapping[str, Any] | None",
    ) -> "DataPreprocessSpec":
        """Build a validated specification from persisted or runtime input."""

        if value is None:
            return cls()
        if isinstance(value, cls):
            return value
        if not isinstance(value, Mapping):
            raise ValueError("Data preprocessing configuration must be an object.")
        expected = {"x_expression", "y_expression"}
        if set(value) != expected:
            raise ValueError(
                "Data preprocessing configuration must contain only "
                "x_expression and y_expression."
            )
        return cls(
            x_expression=value["x_expression"],
            y_expression=value["y_expression"],
        )


@dataclass(frozen=True, slots=True)
class PreprocessedPair:
    """Resolved drawable X/Y values and their row validity diagnostics."""

    x: np.ndarray
    y: np.ndarray
    valid_mask: np.ndarray
    excluded_count: int


def _numeric_result(value: Any, length: int, axis: str) -> np.ndarray:
    if np.isscalar(value):
        if isinstance(value, (bool, np.bool_)):
            raise ValueError(
                f"{axis.upper()} preprocessing result must be numeric, not boolean."
            )
        value = np.full(length, value)
    result = np.asarray(value)
    if result.ndim != 1 or len(result) != length:
        raise ValueError(
            f"{axis.upper()} preprocessing result must be a one-dimensional "
            "array matching the source row count."
        )
    if np.issubdtype(result.dtype, np.bool_):
        raise ValueError(
            f"{axis.upper()} preprocessing result must be numeric, not boolean."
        )
    if np.issubdtype(result.dtype, np.complexfloating):
        raise ValueError(
            f"{axis.upper()} preprocessing result must contain real numbers."
        )
    try:
        return result.astype(float, copy=True)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"{axis.upper()} preprocessing result must contain real numbers."
        ) from exc


def _evaluate_numeric(
    expression: str,
    variables: Mapping[str, np.ndarray],
    length: int,
    axis: str,
) -> np.ndarray:
    try:
        with np.errstate(all="ignore"):
            value = evaluate_math_expression(expression, variables)
    except Exception as exc:
        raise ValueError(
            f"{axis.upper()} preprocessing expression failed: {exc}"
        ) from exc
    return _numeric_result(value, length, axis)


def resolve_preprocessed_pair(
    repository,
    x_ref: ColumnRef,
    y_ref: ColumnRef,
    preprocess: DataPreprocessSpec | Mapping[str, Any] | None = None,
    *,
    preserve_gaps: bool,
) -> PreprocessedPair:
    """Resolve aligned table values and apply both expressions atomically."""

    spec = DataPreprocessSpec.from_dict(preprocess)
    raw = repository.line_pair(x_ref, y_ref)
    raw_x = np.asarray(raw.x).copy()
    raw_y = np.asarray(raw.y).copy()
    length = len(raw_x)
    variables = {"x": raw_x, "y": raw_y}
    datetime_x = np.issubdtype(raw_x.dtype, np.datetime64)

    if datetime_x:
        spec.validate_datetime_x()
        transformed_x = raw_x.copy()
    else:
        transformed_x = _evaluate_numeric(
            spec.x_expression,
            variables,
            length,
            "x",
        )
    transformed_y = _evaluate_numeric(
        spec.y_expression,
        variables,
        length,
        "y",
    )

    valid = np.asarray(raw.valid_mask, dtype=bool).copy()
    if datetime_x:
        valid &= ~np.isnat(transformed_x.astype("datetime64[ns]"))
    else:
        valid &= np.isfinite(transformed_x)
    valid &= np.isfinite(transformed_y)
    excluded_count = int((~valid).sum())

    if preserve_gaps:
        x_values = transformed_x.copy()
        y_values = transformed_y.copy()
        if datetime_x:
            x_values = x_values.astype("datetime64[ns]")
            x_values[~valid] = np.datetime64("NaT")
        else:
            x_values = x_values.astype(float, copy=False)
            x_values[~valid] = np.nan
        y_values[~valid] = np.nan
    else:
        if datetime_x:
            numeric_x = transformed_x.astype("datetime64[ns]").astype("int64").astype(float)
            x_values = numeric_x[valid]
        else:
            x_values = transformed_x[valid]
        y_values = transformed_y[valid]

    return PreprocessedPair(
        x=np.asarray(x_values),
        y=np.asarray(y_values),
        valid_mask=valid,
        excluded_count=excluded_count,
    )
