"""Errors raised by the Matplotlib component controller layer."""

from __future__ import annotations


class ComponentError(RuntimeError):
    """Base class for component-controller errors."""


class ComponentValidationError(ComponentError, ValueError):
    """A component state or property value is invalid."""


class ComponentNotFoundError(ComponentError, LookupError):
    """A component or its Matplotlib target cannot be resolved."""


class ComponentDeletedError(ComponentError):
    """An operation was requested for a deleted component."""
