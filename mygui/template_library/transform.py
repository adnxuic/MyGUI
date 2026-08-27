"""Extract templates and remap their local identities for application."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from mygui.database import ColumnRef
from mygui.figuremodify.components import ComponentRole
from mygui.figuremodify.components.serialization import normalize_v17_figure

from .models import (
    ChartTemplate,
    TemplateColumnSlot,
    TemplateDataContract,
    TemplateMetadata,
    TemplateSheetSlot,
)
from .schema import (
    TEMPLATE_MATCH_ALGORITHM_VERSION,
    TEMPLATE_PROJECT_ID,
    validate_template,
    validate_template_name,
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _column_refs(value: Any) -> list[ColumnRef]:
    result: list[ColumnRef] = []
    if isinstance(value, dict):
        if set(value) == {"project_id", "sheet_id", "column_id"}:
            result.append(ColumnRef.from_dict(value))
        else:
            for item in value.values():
                result.extend(_column_refs(item))
    elif isinstance(value, list):
        for item in value:
            result.extend(_column_refs(item))
    return result


def _replace_refs(value: Any, mapping: dict[ColumnRef, ColumnRef]) -> Any:
    if isinstance(value, dict):
        if set(value) == {"project_id", "sheet_id", "column_id"}:
            source = ColumnRef.from_dict(value)
            try:
                return mapping[source].to_dict()
            except KeyError as exc:
                raise ValueError("Figure contains a data reference outside its project.") from exc
        return {key: _replace_refs(item, mapping) for key, item in value.items()}
    if isinstance(value, list):
        return [_replace_refs(item, mapping) for item in value]
    return deepcopy(value)


def _remap_figure_ids(figure: dict[str, Any]) -> dict[str, Any]:
    """Generate new component, layout, and sharing identities."""

    result = deepcopy(figure)
    component_ids = {
        component["id"]: str(uuid4()) for component in result["components"]
    }
    root = next(
        component
        for component in result["components"]
        if component["id"] == result["root_component_id"]
    )
    layouts = root["data"]["layouts"]
    layout_ids = {layout["id"]: str(uuid4()) for layout in layouts}
    share_ids: dict[str, str] = {}
    for component in result["components"]:
        old_id = component["id"]
        component["id"] = component_ids[old_id]
        if component["parent_id"] is not None:
            component["parent_id"] = component_ids[component["parent_id"]]
        selector = component["selector"]
        if selector.get("object_id") == old_id:
            selector["object_id"] = component_ids[old_id]
        data = component["data"]
        if "source_component_id" in data:
            data["source_component_id"] = component_ids[data["source_component_id"]]
        subplot = data.get("subplot")
        if isinstance(subplot, dict):
            subplot["layout_id"] = layout_ids[subplot["layout_id"]]
            for key in ("share_x_group", "share_y_group"):
                group = subplot.get(key)
                if group is not None:
                    subplot[key] = share_ids.setdefault(group, str(uuid4()))
    for layout in layouts:
        layout["id"] = layout_ids[layout["id"]]
    result["root_component_id"] = component_ids[result["root_component_id"]]

    identity_map = {**component_ids, **layout_ids, **share_ids}

    def replace_identity(value):
        if isinstance(value, str):
            return identity_map.get(value, value)
        if isinstance(value, dict):
            return {key: replace_identity(item) for key, item in value.items()}
        if isinstance(value, list):
            return [replace_identity(item) for item in value]
        return value

    for component in result["components"]:
        component["selector"] = replace_identity(component["selector"])
        component["properties"] = replace_identity(component["properties"])
        component["data"] = replace_identity(component["data"])
    return result


def remap_template_figure(
    template: ChartTemplate,
    *,
    project_id: str,
    column_refs: dict[str, ColumnRef],
) -> dict[str, Any]:
    """Return a fresh runtime Figure tree for one matched application."""

    ref_map = {
        ColumnRef(TEMPLATE_PROJECT_ID, sheet.id, column.id): column_refs[column.id]
        for sheet in template.data_contract.sheets
        for column in sheet.columns
    }
    result = _remap_figure_ids(template.figure)
    result = _replace_refs(result, ref_map)
    for ref in _column_refs(result):
        if ref.project_id != project_id:
            raise ValueError("Template application produced a foreign project reference.")
    return result


class TemplateExtractor:
    """Extract reusable state from authoritative Canvas and Repository snapshots."""

    def __init__(self, repository):
        self.repository = repository

    def extract(
        self,
        canvas,
        *,
        name: str,
        notes: str = "",
        template_id: str | None = None,
        created_at: str | None = None,
        dynamic_text_overrides: dict[tuple[str, str], str] | None = None,
    ) -> ChartTemplate:
        """Extract a complete Figure without copying Table cell values."""

        if canvas is None:
            raise ValueError("Select a Figure before extracting a template.")
        project = self.repository.project(canvas.project_id)
        figure = normalize_v17_figure(canvas.component_snapshot())
        for component in figure["components"]:
            for (component_id, property_name), value in dict(
                dynamic_text_overrides or {}
            ).items():
                if component_id != component["id"]:
                    continue
                if property_name not in component["properties"] or not isinstance(
                    component["properties"][property_name], str
                ):
                    raise ValueError(
                        f"Dynamic text target no longer exists: {component_id}/{property_name}"
                    )
                component["properties"][property_name] = str(value)
        referenced = []
        seen: set[ColumnRef] = set()
        for component in figure["components"]:
            for ref in _column_refs(component["data"]):
                if ref.project_id != project.id:
                    raise ValueError("Figure contains a data reference outside the current project.")
                if ref not in seen:
                    referenced.append(ref)
                    seen.add(ref)

        sheet_slots: list[TemplateSheetSlot] = []
        ref_mapping: dict[ColumnRef, ColumnRef] = {}
        refs_by_sheet = {sheet_id: [] for sheet_id in project.sheets}
        for ref in referenced:
            refs_by_sheet.setdefault(ref.sheet_id, []).append(ref)
        for sheet in project.sheets.values():
            sheet_refs = refs_by_sheet.get(sheet.id, [])
            if not sheet_refs:
                continue
            sheet_slot_id = str(uuid4())
            column_slots: list[TemplateColumnSlot] = []
            requested_ids = {ref.column_id for ref in sheet_refs}
            for column in sheet.columns:
                if column.id not in requested_ids:
                    continue
                if column.type.value == "auto":
                    raise ValueError(
                        f"Referenced column {sheet.name}/{column.name} has no resolved type."
                    )
                column_slot_id = str(uuid4())
                column_slots.append(
                    TemplateColumnSlot(column_slot_id, column.name, column.type)
                )
                source_ref = ColumnRef(project.id, sheet.id, column.id)
                ref_mapping[source_ref] = ColumnRef(
                    TEMPLATE_PROJECT_ID, sheet_slot_id, column_slot_id
                )
            sheet_slots.append(
                TemplateSheetSlot(sheet_slot_id, sheet.name, tuple(column_slots))
            )

        local_figure = _remap_figure_ids(figure)
        local_figure = _replace_refs(local_figure, ref_mapping)
        root = next(
            component
            for component in local_figure["components"]
            if component["id"] == local_figure["root_component_id"]
        )
        root["properties"]["name"] = "{{project_name}}"
        unconfigured_fits: list[str] = []
        for component in local_figure["components"]:
            if component["role"] != ComponentRole.FIT_CURVE.value:
                continue
            data = component["data"]
            fit_type = data.get("fit_type")
            fit_options = data.get("fit_options")
            if (
                not isinstance(fit_type, str)
                or not fit_type.strip()
                or (fit_options is not None and not isinstance(fit_options, dict))
            ):
                unconfigured_fits.append(
                    str(component.get("properties", {}).get("label") or component["id"])
                )
                continue
            data["fit_result"] = None
            data["expression"] = ""
            data["x_start"] = 0.0
            data["x_stop"] = 1.0
        if unconfigured_fits:
            raise ValueError(
                "Configure and run these Fit components before extracting: "
                + ", ".join(unconfigured_fits)
            )

        now = _now()
        metadata = TemplateMetadata(
            id=template_id or str(uuid4()),
            name=validate_template_name(name),
            notes=str(notes),
            created_at=created_at or now,
            updated_at=now,
        )
        template = ChartTemplate(
            metadata,
            TemplateDataContract(
                TEMPLATE_MATCH_ALGORITHM_VERSION,
                True,
                tuple(sheet_slots),
            ),
            local_figure,
        )
        validate_template(template)
        return template

    def update(
        self,
        existing: ChartTemplate,
        canvas,
        *,
        dynamic_text_overrides: dict[tuple[str, str], str] | None = None,
    ) -> ChartTemplate:
        """Replace blueprint/contract while preserving ID, name, notes, and creation."""

        return self.extract(
            canvas,
            name=existing.metadata.name,
            notes=existing.metadata.notes,
            template_id=existing.metadata.id,
            created_at=existing.metadata.created_at,
            dynamic_text_overrides=dynamic_text_overrides,
        )


def template_content_summary(template: ChartTemplate) -> dict[str, int | bool]:
    """Return non-sensitive counts and embedded/manual-content warning state."""

    components = template.figure["components"]
    fit_count = sum(item["role"] == ComponentRole.FIT_CURVE.value for item in components)
    embedded = any(
        item["role"] in {"line", "reflection_positions", "in_axes_image"}
        for item in components
    )
    return {
        "components": len(components),
        "fits": fit_count,
        "sheets": len(template.data_contract.sheets),
        "columns": sum(len(sheet.columns) for sheet in template.data_contract.sheets),
        "contains_embedded_content": embedded,
    }
