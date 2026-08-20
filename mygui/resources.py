"""Resolve immutable application resources independently of the process CWD."""

from __future__ import annotations

from collections.abc import Mapping
import json
from pathlib import Path, PurePosixPath
import re
from typing import Any


PACKAGE_ROOT = Path(__file__).resolve().parent
REPOSITORY_ROOT = PACKAGE_ROOT.parent
_QSS_TOKEN_PATTERN = re.compile(r"\{\{\s*([A-Z][A-Z0-9_]*)\s*\}\}")


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


def load_text_resource(relative_path: str | Path) -> str:
    """Load one UTF-8 text resource below the repository root."""

    return resource_path(relative_path).read_text(encoding="utf-8")


def load_json_resource(relative_path: str | Path) -> Any:
    """Load one UTF-8 JSON resource below the repository root."""

    return json.loads(load_text_resource(relative_path))


def _icon_qss_tokens() -> dict[str, str]:
    """Return QSS tokens that resolve bundled icon files to POSIX URLs."""

    return {
        "ICON_ARROW_DOWN": Path(icon_path("arrow_down.svg")).as_posix(),
        "ICON_ARROW_UP": Path(icon_path("arrow_up.svg")).as_posix(),
        "ICON_CHECK": Path(icon_path("check.svg")).as_posix(),
        "ICON_CHECK_INDETERMINATE": Path(
            icon_path("check_indeterminate.svg")
        ).as_posix(),
    }


def load_qss_resource(
    relative_path: str | Path,
    *,
    tokens: Mapping[str, object] | None = None,
) -> str:
    """Load bundled QSS and strictly expand shared theme tokens."""

    from mygui.widgets.theme import QSS_TOKENS

    source = load_text_resource(relative_path)
    replacements = dict(QSS_TOKENS)
    replacements.update(_icon_qss_tokens())
    if tokens is not None:
        if not isinstance(tokens, Mapping):
            raise TypeError("tokens must be a mapping")
        replacements.update(
            {str(name): str(value) for name, value in tokens.items()}
        )

    token_names = set(_QSS_TOKEN_PATTERN.findall(source))
    unknown = sorted(token_names.difference(replacements))
    if unknown:
        names = ", ".join(unknown)
        raise ValueError(f"Unknown QSS theme token(s): {names}")

    rendered = _QSS_TOKEN_PATTERN.sub(
        lambda match: str(replacements[match.group(1)]),
        source,
    )
    if "{{" in rendered or "}}" in rendered:
        raise ValueError("Malformed QSS theme token")
    return rendered
