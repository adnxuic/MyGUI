"""Appearance, Workspace, and New Figure Settings Center pages.

These widgets expose ``page_spec()`` for Agent A's Settings Center shell.
They do not own Apply / OK / Cancel / Restore page defaults.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from .appearance import (
    AppearanceSettingsPage,
    make_appearance_factory,
    page_spec as appearance_page_spec,
)
from .new_figure import (
    NewFigureSettingsPage,
    make_new_figure_factory,
    page_spec as new_figure_page_spec,
)
from .page import SettingsPageWidget, SettingsUiPageSpec
from .workspace import (
    WorkspaceSettingsPage,
    make_workspace_factory,
    page_spec as workspace_page_spec,
)

_SHELL_MODULES = (
    "mygui.widgets.settings_center",
    "mygui.widgets.settings_center.host",
    "mygui.widgets.settings_center.pages",
)


def builtin_page_specs(
    *,
    reset_layout_now: Callable[[], Any] | None = None,
    layout_port: Any | None = None,
):
    """Return the three page specs in Settings Center navigation order."""

    return (
        appearance_page_spec(make_appearance_factory()),
        workspace_page_spec(
            make_workspace_factory(
                reset_layout_now=reset_layout_now,
                layout_port=layout_port,
            )
        ),
        new_figure_page_spec(make_new_figure_factory()),
    )


def register_pages(
    register_page: Callable[[Any], Any],
    *,
    reset_layout_now: Callable[[], Any] | None = None,
    layout_port: Any | None = None,
):
    """Register Appearance, Workspace, and New Figure with the shell."""

    specs = builtin_page_specs(
        reset_layout_now=reset_layout_now,
        layout_port=layout_port,
    )
    for spec in specs:
        register_page(spec)
    return specs


def register_b_pages(
    center: Any,
    *,
    reset_layout_now: Callable[[], Any] | None = None,
    layout_port: Any | None = None,
) -> list[Any]:
    """Register the three B pages when ``center.register_page`` exists."""

    register = getattr(center, "register_page", None)
    if not callable(register):
        return []
    return list(
        register_pages(
            register,
            reset_layout_now=reset_layout_now,
            layout_port=layout_port,
        )
    )


def try_register_with_shell() -> bool:
    """Register with a module-level ``register_page`` if the shell published one."""

    import importlib

    for name in _SHELL_MODULES:
        try:
            module = importlib.import_module(name)
        except ImportError:
            continue
        register = getattr(module, "register_page", None)
        if callable(register):
            register_pages(register)
            return True
        for attr in ("default_page_registry", "page_registry", "PAGE_REGISTRY"):
            registry = getattr(module, attr, None)
            if registry is None:
                continue
            if callable(registry) and not isinstance(registry, type):
                try:
                    registry = registry()
                except TypeError:
                    continue
            method = getattr(registry, "register_page", None)
            if callable(method):
                register_pages(method)
                return True
    return False


__all__ = [
    "AppearanceSettingsPage",
    "NewFigureSettingsPage",
    "SettingsPageWidget",
    "SettingsUiPageSpec",
    "WorkspaceSettingsPage",
    "appearance_page_spec",
    "builtin_page_specs",
    "make_appearance_factory",
    "make_new_figure_factory",
    "make_workspace_factory",
    "new_figure_page_spec",
    "register_b_pages",
    "register_pages",
    "try_register_with_shell",
    "workspace_page_spec",
]
