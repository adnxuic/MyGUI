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
_RESOURCE_PATH_CACHE: dict[tuple[str, bool], Path] = {}
_ICON_DIRECTORY_CACHE: dict[str, Path] = {}


def clear_resource_path_cache_for_tests() -> None:
    """Drop immutable resource-path caches. Tests only."""

    _RESOURCE_PATH_CACHE.clear()
    _ICON_DIRECTORY_CACHE.clear()


def resource_path(relative_path: str | Path, *, required: bool = True) -> Path:
    """Return an absolute path below the repository resource root."""

    relative = PurePosixPath(str(relative_path).replace("\\", "/"))
    cache_key = (str(relative), bool(required))
    cached = _RESOURCE_PATH_CACHE.get(cache_key)
    if cached is not None:
        return cached
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError("Resource paths must be relative and remain below the resource root.")
    resolved = REPOSITORY_ROOT.joinpath(*relative.parts)
    if required and not resolved.is_file():
        raise FileNotFoundError(f"Application resource does not exist: {relative}")
    return _RESOURCE_PATH_CACHE.setdefault(cache_key, resolved)


def icon_path(relative_path: str | Path) -> str:
    """Return an absolute Qt-compatible path below ``pictures/icons``."""

    relative = PurePosixPath(str(relative_path).replace("\\", "/"))
    return str(resource_path(PurePosixPath("pictures/icons") / relative))


def icon_directory(relative_path: str | Path = "") -> Path:
    """Return a validated directory below ``pictures/icons``."""

    relative = PurePosixPath(str(relative_path).replace("\\", "/"))
    cache_key = str(relative)
    cached = _ICON_DIRECTORY_CACHE.get(cache_key)
    if cached is not None:
        return cached
    directory = resource_path(
        PurePosixPath("pictures/icons") / relative,
        required=False,
    )
    if not directory.is_dir():
        raise FileNotFoundError(f"Application icon directory does not exist: {relative}")
    _ICON_DIRECTORY_CACHE[cache_key] = directory
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


def expand_qss_tokens(source: str, tokens: Mapping[str, object]) -> str:
    """Expand ``{{TOKEN}}`` placeholders using the given snapshot tokens.

    Icon path tokens are merged after ``tokens`` so bundled QSS can reference
    ``ICON_*`` without putting filesystem paths on ThemeSnapshot. The mapping
    is copied in name-sorted order so one snapshot always yields one string.
    """

    if not isinstance(tokens, Mapping):
        raise TypeError("tokens must be a mapping")
    replacements = {str(name): str(tokens[name]) for name in sorted(tokens, key=str)}
    replacements.update(_icon_qss_tokens())

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


def load_qss_resource(
    relative_path: str | Path,
    *,
    tokens: Mapping[str, object] | None = None,
) -> str:
    """Load bundled QSS and expand the token mapping supplied by the caller.

    Production widgets must pass ``ThemeSnapshot`` tokens through
    ``ThemeBindingPort.bind_qss``. When ``tokens`` is omitted, Light snapshot
    tokens are used so tests and resource-only callers still expand QSS.
    After ThemeService publishes a snapshot, production chrome must not rely
    on this Light fallback. This function never reads a mutable process-global
    theme table.
    """

    source = load_text_resource(relative_path)
    if tokens is None:
        from mygui.application_theme.tokens import LIGHT_QSS_TOKENS

        token_map: Mapping[str, object] = LIGHT_QSS_TOKENS
    else:
        token_map = tokens
    return expand_qss_tokens(source, token_map)
