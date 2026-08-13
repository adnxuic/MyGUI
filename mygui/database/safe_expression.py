"""Parse and evaluate budgeted element-wise mathematical expressions."""

from __future__ import annotations

import ast
from dataclasses import dataclass
import math
from typing import Any, Callable, Mapping

import numpy as np


class UnsafeExpressionError(ValueError):
    """Raised when a math expression exceeds the supported safe subset."""


@dataclass(frozen=True, slots=True)
class ExpressionLimits:
    """Hard limits applied before and during expression evaluation."""

    max_length: int = 512
    max_ast_nodes: int = 128
    max_ast_depth: int = 32
    max_integer_bits: int = 256
    max_abs_exponent: float = 64.0
    max_array_elements: int = 2_000_000


DEFAULT_EXPRESSION_LIMITS = ExpressionLimits()
GENERATED_FIT_EXPRESSION_LIMITS = ExpressionLimits(
    max_length=4096,
    max_ast_nodes=1024,
    max_ast_depth=128,
)

MAX_EXPRESSION_LENGTH = DEFAULT_EXPRESSION_LIMITS.max_length
MAX_EXPRESSION_AST_NODES = DEFAULT_EXPRESSION_LIMITS.max_ast_nodes
MAX_EXPRESSION_AST_DEPTH = DEFAULT_EXPRESSION_LIMITS.max_ast_depth


_ALLOWED_FUNCTIONS: dict[str, Callable[[Any], Any]] = {
    "abs": np.abs,
    "arccos": np.arccos,
    "arcsin": np.arcsin,
    "arcsinh": np.arcsinh,
    "arctan": np.arctan,
    "cos": np.cos,
    "cosh": np.cosh,
    "exp": np.exp,
    "log": np.log,
    "log10": np.log10,
    "sin": np.sin,
    "sinh": np.sinh,
    "sqrt": np.sqrt,
    "tan": np.tan,
    "tanh": np.tanh,
}

_ALLOWED_CONSTANTS: dict[str, float] = {
    "e": float(np.e),
    "nan": float(np.nan),
    "inf": float(np.inf),
    "pi": float(np.pi),
}

_ALLOWED_NUMPY_ATTRIBUTES = set(_ALLOWED_FUNCTIONS) | set(_ALLOWED_CONSTANTS)

_ALLOWED_NODES = (
    ast.Expression,
    ast.BinOp,
    ast.UnaryOp,
    ast.Call,
    ast.Name,
    ast.Load,
    ast.Constant,
    ast.Attribute,
    ast.Add,
    ast.Sub,
    ast.Mult,
    ast.Div,
    ast.Pow,
    ast.Mod,
    ast.USub,
    ast.UAdd,
)


def _ast_depth(node: ast.AST) -> int:
    children = tuple(ast.iter_child_nodes(node))
    if not children:
        return 1
    return 1 + max(_ast_depth(child) for child in children)


def _validate_constant(value: Any, limits: ExpressionLimits) -> None:
    if isinstance(value, (bool, np.bool_)):
        raise UnsafeExpressionError("boolean constants are not allowed")
    if isinstance(value, int):
        if value.bit_length() > limits.max_integer_bits:
            raise UnsafeExpressionError("Integer constant exceeds the configured budget")
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise UnsafeExpressionError("Numeric constants must be finite")
        return
    raise UnsafeExpressionError("Only real numeric constants are allowed")


def _validate_node(
    node: ast.AST,
    variable_names: set[str],
    limits: ExpressionLimits,
) -> None:
    if not isinstance(node, _ALLOWED_NODES):
        raise UnsafeExpressionError(
            f"Unsupported expression syntax: {type(node).__name__}"
        )

    if isinstance(node, ast.Constant):
        _validate_constant(node.value, limits)

    if isinstance(node, ast.Name):
        if (
            node.id not in variable_names
            and node.id not in _ALLOWED_FUNCTIONS
            and node.id not in _ALLOWED_CONSTANTS
            and node.id not in {"np", "numpy"}
        ):
            raise UnsafeExpressionError(f"Unknown name: {node.id}")

    if isinstance(node, ast.Attribute):
        if node.attr.startswith("_"):
            raise UnsafeExpressionError("Private attributes are not allowed")
        if not isinstance(node.value, ast.Name) or node.value.id not in {
            "np",
            "numpy",
        }:
            raise UnsafeExpressionError("Only np.<math> attributes are allowed")
        if node.attr not in _ALLOWED_NUMPY_ATTRIBUTES:
            raise UnsafeExpressionError(
                f"Unsupported numpy attribute: {node.attr}"
            )
        return

    if isinstance(node, ast.Call):
        if len(node.args) != 1:
            raise UnsafeExpressionError(
                "Math functions require exactly one positional argument"
            )
        if node.keywords:
            raise UnsafeExpressionError("Keyword arguments are not allowed")
        if isinstance(node.func, ast.Name):
            if node.func.id not in _ALLOWED_FUNCTIONS:
                raise UnsafeExpressionError(
                    f"Unsupported function: {node.func.id}"
                )
        elif isinstance(node.func, ast.Attribute):
            _validate_node(node.func, variable_names, limits)
        else:
            raise UnsafeExpressionError("Unsupported call target")

    for child in ast.iter_child_nodes(node):
        _validate_node(child, variable_names, limits)


def compile_math_expression(
    expression: str,
    variable_names: set[str] | None = None,
    *,
    limits: ExpressionLimits = DEFAULT_EXPRESSION_LIMITS,
) -> ast.Expression:
    """Parse and validate a mathematical expression without compiling code."""

    if not isinstance(expression, str) or not expression.strip():
        raise UnsafeExpressionError("Expression must be a non-empty string")
    if len(expression) > limits.max_length:
        raise UnsafeExpressionError(
            f"Expression exceeds {limits.max_length} characters"
        )
    variables = set(variable_names or {"x"})
    try:
        parsed = ast.parse(expression, mode="eval")
    except (SyntaxError, RecursionError) as exc:
        raise UnsafeExpressionError(str(exc)) from exc

    node_count = sum(1 for _node in ast.walk(parsed))
    if node_count > limits.max_ast_nodes:
        raise UnsafeExpressionError("Expression is too complex")
    try:
        depth = _ast_depth(parsed)
    except RecursionError as exc:
        raise UnsafeExpressionError("Expression is nested too deeply") from exc
    if depth > limits.max_ast_depth:
        raise UnsafeExpressionError("Expression is nested too deeply")

    _validate_node(parsed, variables, limits)
    return parsed


def _checked_numeric(value: Any, limits: ExpressionLimits) -> Any:
    if isinstance(value, (bool, np.bool_)):
        raise UnsafeExpressionError("boolean values are not allowed")
    if np.isscalar(value):
        if isinstance(value, complex) or np.iscomplexobj(value):
            raise UnsafeExpressionError("Complex values are not allowed")
        try:
            return float(value)
        except (TypeError, ValueError, OverflowError) as exc:
            raise UnsafeExpressionError("Expression values must be real numbers") from exc

    result = np.asarray(value)
    if result.ndim != 1:
        raise UnsafeExpressionError("Expression arrays must be one-dimensional")
    if result.size > limits.max_array_elements:
        raise UnsafeExpressionError(
            "Expression array exceeds the configured element budget"
        )
    if (
        np.issubdtype(result.dtype, np.bool_)
        or np.issubdtype(result.dtype, np.complexfloating)
        or not np.issubdtype(result.dtype, np.number)
    ):
        raise UnsafeExpressionError("Expression arrays must contain real numbers")
    return result


def _function_for_call(node: ast.Call) -> Callable[[Any], Any]:
    if isinstance(node.func, ast.Name):
        return _ALLOWED_FUNCTIONS[node.func.id]
    return _ALLOWED_FUNCTIONS[node.func.attr]


def _evaluate_node(
    node: ast.AST,
    variables: Mapping[str, Any],
    limits: ExpressionLimits,
) -> Any:
    if isinstance(node, ast.Expression):
        return _evaluate_node(node.body, variables, limits)
    if isinstance(node, ast.Constant):
        return float(node.value)
    if isinstance(node, ast.Name):
        if node.id in variables:
            return _checked_numeric(variables[node.id], limits)
        if node.id in _ALLOWED_CONSTANTS:
            return _ALLOWED_CONSTANTS[node.id]
        raise UnsafeExpressionError(f"Name cannot be used as a value: {node.id}")
    if isinstance(node, ast.Attribute):
        if node.attr in _ALLOWED_CONSTANTS:
            return _ALLOWED_CONSTANTS[node.attr]
        raise UnsafeExpressionError(
            f"Numpy function cannot be used as a value: {node.attr}"
        )
    if isinstance(node, ast.UnaryOp):
        operand = _evaluate_node(node.operand, variables, limits)
        operation = np.negative if isinstance(node.op, ast.USub) else np.positive
        return _checked_numeric(operation(operand), limits)
    if isinstance(node, ast.Call):
        argument = _evaluate_node(node.args[0], variables, limits)
        with np.errstate(all="ignore"):
            result = _function_for_call(node)(argument)
        return _checked_numeric(result, limits)
    if isinstance(node, ast.BinOp):
        left = _evaluate_node(node.left, variables, limits)
        right = _evaluate_node(node.right, variables, limits)
        if isinstance(node.op, ast.Pow):
            exponent = np.asarray(right)
            if not np.all(np.isfinite(exponent)):
                raise UnsafeExpressionError("Power exponent must be finite")
            if exponent.size and np.max(np.abs(exponent)) > limits.max_abs_exponent:
                raise UnsafeExpressionError(
                    "Power exponent exceeds the configured budget"
                )
            operation = np.power
        else:
            operation = {
                ast.Add: np.add,
                ast.Sub: np.subtract,
                ast.Mult: np.multiply,
                ast.Div: np.divide,
                ast.Mod: np.remainder,
            }[type(node.op)]
        with np.errstate(all="ignore"):
            result = operation(left, right)
        return _checked_numeric(result, limits)
    raise UnsafeExpressionError(
        f"Unsupported expression syntax: {type(node).__name__}"
    )


def evaluate_math_expression(
    expression: str,
    variables: Mapping[str, Any],
    *,
    limits: ExpressionLimits = DEFAULT_EXPRESSION_LIMITS,
) -> Any:
    """Evaluate an expression with the bounded AST interpreter."""

    parsed = compile_math_expression(expression, set(variables), limits=limits)
    return _evaluate_node(parsed, variables, limits)


def evaluate_curve_expression(
    expression: str,
    x: np.ndarray,
    *,
    limits: ExpressionLimits = DEFAULT_EXPRESSION_LIMITS,
) -> np.ndarray:
    """Evaluate a finite one-dimensional curve matching the input X length."""

    x_values = _checked_numeric(x, limits)
    if np.isscalar(x_values):
        raise UnsafeExpressionError("Curve X values must be one-dimensional")
    value = evaluate_math_expression(expression, {"x": x_values}, limits=limits)
    if np.isscalar(value):
        result = np.full(x_values.shape, value, dtype=float)
    else:
        result = np.asarray(value)
    if result.ndim != 1 or result.shape != x_values.shape:
        raise UnsafeExpressionError(
            "Curve result must be one-dimensional and match the X values"
        )
    if not np.issubdtype(result.dtype, np.number) or np.iscomplexobj(result):
        raise UnsafeExpressionError("Curve result must contain real numbers")
    result = result.astype(float, copy=False)
    if not np.all(np.isfinite(result)):
        raise UnsafeExpressionError("Curve result must contain only finite numbers")
    return result
