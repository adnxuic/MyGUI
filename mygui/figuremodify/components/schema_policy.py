"""Immutable schema-v10 through v23 Figure compatibility policy.

This table is the internal owner of component-introduction versions and
version-specific validation contracts. Public ``validate_v10_figure`` through
``validate_v23_figure`` names stay on ``serialization``; they look up a policy
and run pure validators. The table is not a second business-state store.
"""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping

from .models import ComponentKind


MIN_FIGURE_SCHEMA_VERSION = 10
CURRENT_FIGURE_SCHEMA_VERSION = 23

COLOR_PROPERTIES = frozenset(
    {
        "color",
        "facecolor",
        "edgecolor",
        "markerfacecolor",
        "markeredgecolor",
        "gapcolor",
        "region_color",
        "region_facecolor",
        "outline_color",
    }
)

KIND_INTRODUCED_AT: Mapping[ComponentKind, int] = MappingProxyType(
    {
        ComponentKind.COLORBAR: 11,
        ComponentKind.REFERENCE_MARKS: 12,
        ComponentKind.REFERENCE_GUIDE: 13,
        ComponentKind.FIELD_2D: 16,
        ComponentKind.ANNOTATION: 17,
        ComponentKind.ERRORBAR: 20,
        ComponentKind.SECONDARY_AXIS: 23,
    }
)

KIND_REJECTION_MESSAGES: Mapping[ComponentKind, str] = MappingProxyType(
    {
        ComponentKind.COLORBAR: "Colorbar is not part of schema v{version}.",
        ComponentKind.REFERENCE_MARKS: (
            "Reference Marks is not part of schema v{version}."
        ),
        ComponentKind.REFERENCE_GUIDE: (
            "Reference Guides are not part of schema v{version}."
        ),
        ComponentKind.FIELD_2D: "FIELD_2D is not part of schema v{version}.",
        ComponentKind.ANNOTATION: "Annotation is not part of schema v{version}.",
        ComponentKind.ERRORBAR: "Error Bar is not part of schema v{version}.",
        ComponentKind.SECONDARY_AXIS: (
            "Secondary Axis is not part of schema v{version}."
        ),
    }
)


@dataclass(frozen=True, slots=True)
class FigureSchemaPolicy:
    """Describe one exact Figure schema version's compatibility contracts."""

    version: int
    kind_introduced_at: Mapping[ComponentKind, int]
    kind_rejection_messages: Mapping[ComponentKind, str]
    requires_fit_input_range: bool
    forbids_fit_input_range: bool
    requires_axes_geometry: bool
    forbids_axes_geometry: bool
    allows_index_locator: bool
    allows_format_str_formatter: bool
    tick_label_fontfamily_string_only: bool
    axes_persists_in_layout: bool
    injects_missing_y_lower_reserve: bool
    reference_marks_positions_only: bool
    errorbar_v20_properties: bool
    colorbar_allows_field_2d_source: bool
    twin_axes_require_identical_geometry: bool


def _policy_for_version(version: int) -> FigureSchemaPolicy:
    return FigureSchemaPolicy(
        version=version,
        kind_introduced_at=KIND_INTRODUCED_AT,
        kind_rejection_messages=KIND_REJECTION_MESSAGES,
        requires_fit_input_range=version >= 18,
        forbids_fit_input_range=version < 18,
        requires_axes_geometry=version >= 19,
        forbids_axes_geometry=version < 19,
        allows_index_locator=version >= 22,
        allows_format_str_formatter=version >= 22,
        tick_label_fontfamily_string_only=version >= 14,
        axes_persists_in_layout=version < 19,
        injects_missing_y_lower_reserve=version < 15,
        reference_marks_positions_only=version < 15,
        errorbar_v20_properties=version < 21,
        colorbar_allows_field_2d_source=version >= 16,
        twin_axes_require_identical_geometry=version >= 19,
    )


FIGURE_SCHEMA_POLICIES: Mapping[int, FigureSchemaPolicy] = MappingProxyType(
    {
        version: _policy_for_version(version)
        for version in range(MIN_FIGURE_SCHEMA_VERSION, CURRENT_FIGURE_SCHEMA_VERSION + 1)
    }
)


def figure_schema_policy(version: int) -> FigureSchemaPolicy:
    """Return the immutable policy for one supported Figure schema version."""

    try:
        return FIGURE_SCHEMA_POLICIES[version]
    except KeyError as exc:
        raise ValueError(
            f"Unsupported Figure schema version {version!r}; expected "
            f"{MIN_FIGURE_SCHEMA_VERSION}-{CURRENT_FIGURE_SCHEMA_VERSION}."
        ) from exc
