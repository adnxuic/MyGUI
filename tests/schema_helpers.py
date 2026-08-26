"""Helpers for constructing predecessor schema snapshots from current saves."""

from __future__ import annotations

from copy import deepcopy
from typing import Any


def as_schema_v15(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Drop v16-only FIELD_2D records so a current snapshot can validate as v15."""

    payload = deepcopy(snapshot)
    payload["schema_version"] = 15
    figure = payload.get("figure") or {}
    components = []
    removed_ids: set[str] = set()
    for component in figure.get("components") or []:
        if component.get("kind") == "field_2d":
            removed_ids.add(str(component.get("id")))
            continue
        components.append(component)
    if removed_ids:
        kept = []
        for component in components:
            if (
                component.get("kind") == "colorbar"
                and str((component.get("data") or {}).get("source_component_id"))
                in removed_ids
            ):
                continue
            kept.append(component)
        components = kept
    if isinstance(figure, dict):
        figure["components"] = components
    return payload


def as_schema_v14(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Strip v15-only fields so a current snapshot can validate as schema v14."""

    payload = as_schema_v15(snapshot)
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
