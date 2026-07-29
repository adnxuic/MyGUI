"""Compile and evaluate restricted mathematical expressions."""

import ast
from typing import Any, Callable, Mapping

import numpy as np


class UnsafeExpressionError(ValueError):
    """Raised when a math expression uses unsupported or unsafe syntax."""


_ALLOWED_FUNCTIONS: dict[str, Callable[..., Any]] = {
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


def _validate_node(node: ast.AST, variable_names: set[str]) -> None:
    if not isinstance(node, _ALLOWED_NODES):
        raise UnsafeExpressionError(f"Unsupported expression syntax: {type(node).__name__}")

    if isinstance(node, ast.Constant) and not isinstance(node.value, (int, float)):
        raise UnsafeExpressionError("Only numeric constants are allowed")

    if isinstance(node, ast.Name):
        if node.id not in variable_names and node.id not in _ALLOWED_FUNCTIONS and node.id not in _ALLOWED_CONSTANTS:
            raise UnsafeExpressionError(f"Unknown name: {node.id}")

    if isinstance(node, ast.Attribute):
        if node.attr.startswith("_"):
            raise UnsafeExpressionError("Private attributes are not allowed")
        if not isinstance(node.value, ast.Name) or node.value.id not in {"np", "numpy"}:
            raise UnsafeExpressionError("Only np.<math> attributes are allowed")
        if node.attr not in _ALLOWED_NUMPY_ATTRIBUTES:
            raise UnsafeExpressionError(f"Unsupported numpy attribute: {node.attr}")
        return

    if isinstance(node, ast.Call):
        if isinstance(node.func, ast.Name):
            if node.func.id not in _ALLOWED_FUNCTIONS:
                raise UnsafeExpressionError(f"Unsupported function: {node.func.id}")
        elif isinstance(node.func, ast.Attribute):
            _validate_node(node.func, variable_names)
        else:
            raise UnsafeExpressionError("Unsupported call target")

        if node.keywords:
            raise UnsafeExpressionError("Keyword arguments are not allowed")

    for child in ast.iter_child_nodes(node):
        _validate_node(child, variable_names)


def compile_math_expression(expression: str, variable_names: set[str] | None = None) -> ast.Expression:
    """Compile math expression for safe reuse."""

    variables = set(variable_names or {"x"})
    try:
        parsed = ast.parse(expression, mode="eval")
    except SyntaxError as exc:
        raise UnsafeExpressionError(str(exc)) from exc

    _validate_node(parsed, variables)
    return parsed


def evaluate_math_expression(expression: str, variables: Mapping[str, Any]) -> Any:
    """Evaluate math expression in the restricted math environment."""

    parsed = compile_math_expression(expression, set(variables))
    compiled = compile(parsed, "<math-expression>", "eval")
    namespace: dict[str, Any] = {
        "__builtins__": {},
        "np": np,
        "numpy": np,
        **_ALLOWED_FUNCTIONS,
        **_ALLOWED_CONSTANTS,
    }
    return eval(compiled, namespace, dict(variables))


def evaluate_curve_expression(expression: str, x: np.ndarray) -> np.ndarray:
    """Evaluate curve expression in the restricted math environment."""

    value = evaluate_math_expression(expression, {"x": x})
    if np.isscalar(value):
        return np.full_like(x, value, dtype=float)
    return np.asarray(value)
