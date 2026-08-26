"""Errors for ThemeService transactions."""

from __future__ import annotations


class ThemeError(RuntimeError):
    """Base error for application-theme operations."""


class ThemeValidationError(ThemeError, ValueError):
    """Appearance preferences are outside the closed contract."""


class ThemeApplyError(ThemeError):
    """A theme apply/preview step failed after a complete rollback."""


class ThemeRollbackError(ThemeError):
    """Rollback did not restore the pre-apply chrome. Health is UNCERTAIN."""

    def __init__(
        self,
        rollback_errors: tuple[BaseException, ...],
        *,
        primary: BaseException | None = None,
    ) -> None:
        self.rollback_errors = tuple(rollback_errors)
        self.primary = primary
        self.rollback_complete = not rollback_errors
        detail = "; ".join(str(error) for error in rollback_errors)
        message = "Theme rollback failed"
        if primary is not None:
            message = f"Theme rollback failed after: {primary}"
        if detail:
            message += f" ({detail})"
        super().__init__(message)
