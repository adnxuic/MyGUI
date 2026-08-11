"""Errors raised by the Matplotlib component controller layer."""

from __future__ import annotations


class ComponentError(RuntimeError):
    """Base class for component-controller errors."""


class ComponentValidationError(ComponentError, ValueError):
    """A component state or property value is invalid."""


class ComponentRegistrationError(ComponentError):
    """Report a failed registration whose compensation was incomplete."""

    def __init__(
        self,
        primary_error: BaseException,
        rollback_errors: tuple[BaseException, ...],
    ) -> None:
        self.primary_error = primary_error
        self.rollback_errors = rollback_errors
        self.rollback_complete = not rollback_errors
        detail = "; ".join(str(error) for error in rollback_errors)
        message = f"Component registration failed: {primary_error}"
        if detail:
            message += f" Registration rollback was incomplete: {detail}"
        super().__init__(message)


class ComponentNotFoundError(ComponentError, LookupError):
    """A component or its Matplotlib target cannot be resolved."""


class ComponentDeletedError(ComponentError):
    """An operation was requested for a deleted component."""
