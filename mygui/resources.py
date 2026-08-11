"""Resolve immutable application resources independently of the process CWD."""

from __future__ import annotations

from pathlib import Path, PurePosixPath


PACKAGE_ROOT = Path(__file__).resolve().parent
REPOSITORY_ROOT = PACKAGE_ROOT.parent


def resource_path(relative_path: str | Path, *, required: bool = True) -> Path:
    """Return an absolute path below the repository resource root."""

    relative = PurePosixPath(str(relative_path).replace("\\", "/"))
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError("Resource paths must be relative and remain below the resource root.")
    resolved = REPOSITORY_ROOT.joinpath(*relative.parts)
    if required and not resolved.is_file():
        raise FileNotFoundError(f"Application resource does not exist: {relative}")
    return resolved


def icon_path(relative_path: str | Path) -> str:
    """Return an absolute Qt-compatible path below ``pictures/icons``."""

    relative = PurePosixPath(str(relative_path).replace("\\", "/"))
    return str(resource_path(PurePosixPath("pictures/icons") / relative))


def icon_directory(relative_path: str | Path = "") -> Path:
    """Return a validated directory below ``pictures/icons``."""

    relative = PurePosixPath(str(relative_path).replace("\\", "/"))
    directory = resource_path(
        PurePosixPath("pictures/icons") / relative,
        required=False,
    )
    if not directory.is_dir():
        raise FileNotFoundError(f"Application icon directory does not exist: {relative}")
    return directory
