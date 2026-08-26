"""Render the MainWindow stylesheet from ThemeSnapshot tokens.

Do not expand Light tokens at import time. ThemeService prerender calls this
through ``BundledQssRenderer`` after settings load.
"""

from collections.abc import Mapping
from typing import Any

from mygui.application_theme.qss import MAINWINDOW_QSS_RESOURCE
from mygui.resources import load_qss_resource


def render_mainwindow_stylesheet(
    tokens: Mapping[str, object] | None = None,
    snapshot: Any | None = None,
) -> str:
    """Expand MainWindow QSS from snapshot tokens, explicit tokens, or live tokens."""

    if snapshot is not None:
        mapping = snapshot.tokens
    elif tokens is not None:
        mapping = tokens
    else:
        from mygui.application_theme.qss import current_qss_tokens

        mapping = current_qss_tokens()
    return load_qss_resource(MAINWINDOW_QSS_RESOURCE, tokens=mapping)
