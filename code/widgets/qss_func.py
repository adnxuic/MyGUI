"""Helpers for loading QSS files with strict theme-token expansion."""

from collections.abc import Mapping
import re

from code.widgets.theme import QSS_TOKENS


_TOKEN_PATTERN = re.compile(r"\{\{\s*([A-Z][A-Z0-9_]*)\s*\}\}")


def qss_loader(file_path, tokens: Mapping[str, object] | None = None):
    """Load *file_path* and replace ``{{TOKEN_NAME}}`` placeholders.

    Calling the function with only a path remains fully compatible with the
    previous loader.  Theme tokens are strict by design: an unknown or
    malformed placeholder raises ``ValueError`` instead of silently leaving
    invalid QSS in the application.

    ``tokens`` may override or extend the shared values, which is useful for
    isolated widgets and tests without changing the global theme.
    """

    with open(file_path, "r", encoding="utf-8") as qss_file:
        source = qss_file.read()

    replacements = dict(QSS_TOKENS)
    if tokens is not None:
        if not isinstance(tokens, Mapping):
            raise TypeError("tokens must be a mapping")
        replacements.update({str(name): str(value) for name, value in tokens.items()})

    token_names = set(_TOKEN_PATTERN.findall(source))
    unknown = sorted(token_names.difference(replacements))
    if unknown:
        names = ", ".join(unknown)
        raise ValueError(f"Unknown QSS theme token(s): {names}")

    rendered = _TOKEN_PATTERN.sub(lambda match: str(replacements[match.group(1)]), source)
    if "{{" in rendered or "}}" in rendered:
        raise ValueError("Malformed QSS theme token")
    return rendered
