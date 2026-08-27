"""Resolve the closed dynamic-text vocabulary used by templates."""

from __future__ import annotations

from pathlib import Path
import re
from typing import Any

from .models import ChartTemplate, TemplateBindingPlan
from .schema import allowed_tokens


_TOKEN_RE = re.compile(r"\{\{([a-z0-9_.-]+)\}\}")


def token_values(
    template: ChartTemplate,
    binding: TemplateBindingPlan,
    *,
    project_name: str,
    source_file: str | Path,
) -> dict[str, str]:
    """Return values for every allowed token in one application."""

    source = Path(source_file)
    values = {
        "project_name": project_name,
        "source_file_name": source.name,
        "source_file_stem": source.stem,
    }
    binding_by_slot = {item.slot_id: item for item in binding.sheets}
    for sheet in template.data_contract.sheets:
        sheet_binding = binding_by_slot[sheet.id]
        values[f"sheet.{sheet.id}.name"] = sheet_binding.imported_name
        columns = {item.slot_id: item for item in sheet_binding.columns}
        for column in sheet.columns:
            values[f"column.{column.id}.name"] = columns[column.id].imported_name
    if set(values) != set(allowed_tokens(template.data_contract)):
        raise ValueError("Template variable mapping is incomplete.")
    return values


def resolve_tokens(value: Any, values: dict[str, str]) -> Any:
    """Resolve all tokens recursively, rejecting any unknown or malformed token."""

    if isinstance(value, str):
        def replace(match):
            token = match.group(1)
            if token not in values:
                raise ValueError(f"Unknown template variable: {token}")
            return values[token]

        result = _TOKEN_RE.sub(replace, value)
        if "{{" in result or "}}" in result:
            raise ValueError("Malformed template variable.")
        return result
    if isinstance(value, dict):
        return {key: resolve_tokens(item, values) for key, item in value.items()}
    if isinstance(value, list):
        return [resolve_tokens(item, values) for item in value]
    return value
