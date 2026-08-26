"""Errors for the application-settings model and commit transaction."""

from __future__ import annotations


class SettingsError(RuntimeError):
    """Base error for application-settings operations."""


class SettingsValidationError(SettingsError, ValueError):
    """A settings value, patch, or section id is invalid."""


class SettingsConflictError(SettingsError):
    """A session patch collides with an external change to the same key."""

    def __init__(self, conflicts: tuple[str, ...], message: str | None = None) -> None:
        self.conflicts = tuple(conflicts)
        super().__init__(
            message
            or (
                "Settings patch conflicts with external changes: "
                + ", ".join(self.conflicts)
            )
        )


class RuntimeBindingError(SettingsError):
    """A live runtime preview apply failed."""


class RuntimeBindingRollbackError(SettingsError):
    """Preview rollback did not restore the pre-apply runtime state."""

    def __init__(
        self,
        rollback_errors: tuple[BaseException, ...],
        *,
        primary: BaseException | None = None,
    ) -> None:
        self.rollback_errors = rollback_errors
        self.primary = primary
        self.rollback_complete = not rollback_errors
        detail = "; ".join(str(error) for error in rollback_errors)
        message = "Settings runtime rollback failed"
        if primary is not None:
            message = f"Settings runtime rollback failed after: {primary}"
        if detail:
            message += f" ({detail})"
        super().__init__(message)
