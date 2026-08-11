"""Central configurable budgets for untrusted files and embedded payloads."""

from __future__ import annotations

from dataclasses import dataclass, fields
import os
from typing import Mapping


_MIB = 1024 * 1024


@dataclass(frozen=True, slots=True)
class ResourceLimits:
    """Application resource budgets, configurable through ``MYGUI_*`` env vars."""

    max_project_bytes: int = 64 * _MIB
    max_json_depth: int = 64
    max_json_values: int = 1_000_000
    max_project_components: int = 20_000
    max_image_bytes: int = 16 * _MIB
    max_image_pixels: int = 25_000_000
    max_image_dimension: int = 16_384
    max_text_bytes: int = 64 * _MIB
    max_excel_bytes: int = 64 * _MIB
    max_excel_uncompressed_bytes: int = 512 * _MIB
    max_excel_sheets: int = 256
    max_excel_cells: int = 2_000_000
    max_external_input_bytes: int = 16 * _MIB
    max_external_output_bytes: int = 8 * _MIB

    def __post_init__(self) -> None:
        for field in fields(self):
            if getattr(self, field.name) <= 0:
                raise ValueError(f"Resource limit {field.name} must be positive.")


DEFAULT_RESOURCE_LIMITS = ResourceLimits()

_HARD_CAPS = ResourceLimits(
    max_project_bytes=256 * _MIB,
    max_json_depth=128,
    max_json_values=5_000_000,
    max_project_components=100_000,
    max_image_bytes=64 * _MIB,
    max_image_pixels=50_000_000,
    max_image_dimension=32_768,
    max_text_bytes=256 * _MIB,
    max_excel_bytes=256 * _MIB,
    max_excel_uncompressed_bytes=1024 * _MIB,
    max_excel_sheets=1024,
    max_excel_cells=10_000_000,
    max_external_input_bytes=64 * _MIB,
    max_external_output_bytes=32 * _MIB,
)


def load_resource_limits(
    environ: Mapping[str, str] | None = None,
) -> ResourceLimits:
    """Load validated overrides such as ``MYGUI_MAX_PROJECT_BYTES``."""

    source = os.environ if environ is None else environ
    values: dict[str, int] = {}
    for field in fields(DEFAULT_RESOURCE_LIMITS):
        name = field.name
        environment_name = f"MYGUI_{name.upper()}"
        raw = source.get(environment_name)
        default = getattr(DEFAULT_RESOURCE_LIMITS, name)
        hard_cap = getattr(_HARD_CAPS, name)
        if raw is None:
            values[name] = default
            continue
        try:
            parsed = int(raw)
        except (TypeError, ValueError) as exc:
            raise ValueError(
                f"{environment_name} must be a positive integer."
            ) from exc
        if parsed <= 0 or parsed > hard_cap:
            raise ValueError(
                f"{environment_name} must be between 1 and {hard_cap}."
            )
        values[name] = parsed
    return ResourceLimits(**values)


def validate_json_budget(
    value,
    *,
    limits: ResourceLimits,
) -> None:
    """Reject excessively deep or broad decoded JSON before schema validation."""

    stack = [(value, 1)]
    visited_values = 0
    while stack:
        current, depth = stack.pop()
        if depth > limits.max_json_depth:
            raise ValueError(
                f"Project JSON exceeds the maximum depth of {limits.max_json_depth}."
            )
        visited_values += 1
        if visited_values > limits.max_json_values:
            raise ValueError(
                "Project JSON exceeds the configured value-count budget."
            )
        if isinstance(current, dict):
            stack.extend((item, depth + 1) for item in current.values())
        elif isinstance(current, list):
            stack.extend((item, depth + 1) for item in current)

    if isinstance(value, dict):
        figure = value.get("figure")
        if isinstance(figure, dict):
            components = figure.get("components")
            if (
                isinstance(components, list)
                and len(components) > limits.max_project_components
            ):
                raise ValueError(
                    "Project exceeds the configured Figure component budget."
                )
