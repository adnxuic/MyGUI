"""Helpers for constructing predecessor schema snapshots from current saves."""

from __future__ import annotations

from copy import deepcopy
from typing import Any


def as_schema_v14(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Strip v15-only fields so a current snapshot can validate as schema v14."""

    payload = deepcopy(snapshot)
    payload["schema_version"] = 14
    figure = payload.get("figure") or {}
    for component in figure.get("components") or []:
        kind = component.get("kind")
        if kind == "axes":
            properties = component.get("properties")
            if isinstance(properties, dict):
                properties.pop("y_lower_reserve", None)
        elif kind == "reference_marks":
            data = component.get("data")
            if isinstance(data, dict):
                data.pop("position_ref", None)
                data.pop("placement", None)
    return payload
