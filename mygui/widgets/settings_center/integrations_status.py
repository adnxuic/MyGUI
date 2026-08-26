"""Read-only TeX/MATLAB probes for the Integrations settings page.

These helpers never enable TeX, never start MATLAB or MCR, and never persist
session enablement or connection state.
"""

from __future__ import annotations

import importlib
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class IntegrationStatus:
    """Availability, this-session state, and a short diagnostic summary."""

    available: bool
    session_state: str
    diagnostic_summary: str


def tex_integration_status() -> IntegrationStatus:
    """Probe TeX with PATH lookup and the current session rcParams only."""

    from mygui import tex_config

    available = bool(tex_config.has_tex_engine())
    enabled = bool(tex_config.is_tex_enabled())
    if available:
        summary = (
            "A TeX executable was found on PATH. Enablement and preamble stay "
            "on the TeX panel for this session and are not application settings."
        )
    else:
        summary = (
            "No TeX executable was found on PATH. Ordinary Matplotlib text "
            "remains available. This page does not start TeX."
        )
    return IntegrationStatus(
        available=available,
        session_state="Enabled this session" if enabled else "Disabled this session",
        diagnostic_summary=summary,
    )


def matlab_integration_status() -> IntegrationStatus:
    """Probe MATLAB by importing the Python runtime module only."""

    from mygui.database import matlab_adapter

    available, import_summary = _matlab_runtime_importable()
    connected = bool(matlab_adapter.is_matlab_enabled())
    if available:
        summary = (
            f"{import_summary} Connection stays on the MATLAB panel for this "
            "session and is not an application setting. This page does not "
            "start MATLAB or MCR."
        )
    else:
        summary = (
            f"{import_summary} Fitting can still use SciPy. This page does "
            "not start MATLAB or MCR."
        )
    return IntegrationStatus(
        available=available,
        session_state=(
            "Connected this session" if connected else "Not connected this session"
        ),
        diagnostic_summary=summary,
    )


def _matlab_runtime_importable() -> tuple[bool, str]:
    try:
        module = importlib.import_module("matlab")
    except Exception as exc:
        return False, f"MATLAB Python runtime is not available ({exc})."
    if not callable(getattr(module, "double", None)):
        origin = getattr(module, "__file__", None) or repr(module)
        return (
            False,
            f"Imported matlab module is not MathWorks runtime ({origin}).",
        )
    return True, "MATLAB Python runtime is importable."
