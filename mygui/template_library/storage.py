"""Atomic repository-local storage for reusable chart templates."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
import json
import logging
import os
from pathlib import Path
import shutil
import tempfile
from uuid import uuid4
from uuid import UUID

from mygui.resource_limits import load_resource_limits
from mygui.resources import REPOSITORY_ROOT

from .models import ChartTemplate, TemplateLibraryEntry
from .schema import (
    TEMPLATE_FILE_SUFFIX,
    parse_template_record,
    template_to_dict,
    validate_template,
    validate_template_name,
)


LOGGER = logging.getLogger(__name__)
DEFAULT_TEMPLATE_DIRECTORY = REPOSITORY_ROOT / "template"


def utc_now_text() -> str:
    """Return a stable UTC timestamp for template metadata."""

    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _reject_json_constant(value: str) -> None:
    raise ValueError(f"Invalid JSON numeric constant: {value}.")


class TemplateLibrary:
    """Own all reads and writes under the repository template directory."""

    def __init__(self, root: str | Path | None = None):
        self.root = Path(root) if root is not None else DEFAULT_TEMPLATE_DIRECTORY

    def path_for(self, template_id: str) -> Path:
        """Return the stable UUID-backed path for one template."""

        try:
            canonical = str(UUID(str(template_id)))
        except (TypeError, ValueError, AttributeError) as exc:
            raise ValueError("Template id must be a UUID.") from exc
        if canonical != str(template_id).casefold():
            raise ValueError("Template id must be a canonical UUID.")
        return self.root / f"{canonical}{TEMPLATE_FILE_SUFFIX}"

    def _read_path(self, path: Path) -> ChartTemplate:
        limits = load_resource_limits()
        if path.stat().st_size > limits.max_template_bytes:
            raise ValueError("Template file exceeds the configured file-size budget.")
        with path.open("r", encoding="utf-8-sig") as handle:
            value = json.load(handle, parse_constant=_reject_json_constant)
        return parse_template_record(value)

    def entries(self) -> tuple[TemplateLibraryEntry, ...]:
        """List valid and corrupt records without letting one file break startup."""

        if not self.root.is_dir():
            return ()
        result: list[TemplateLibraryEntry] = []
        for path in sorted(self.root.glob(f"*{TEMPLATE_FILE_SUFFIX}")):
            try:
                template = self._read_path(path)
                if path.name != self.path_for(template.metadata.id).name:
                    raise ValueError("Template filename and metadata id do not match.")
                result.append(TemplateLibraryEntry(path, template))
            except Exception as exc:
                result.append(TemplateLibraryEntry(path, None, str(exc)))
        return tuple(result)

    def templates(self) -> tuple[ChartTemplate, ...]:
        """Return valid templates sorted by display name."""

        values = [entry.template for entry in self.entries() if entry.template is not None]
        return tuple(sorted(values, key=lambda item: item.metadata.name.casefold()))

    def get(self, template_id: str) -> ChartTemplate:
        """Read one template by stable identifier."""

        template = self._read_path(self.path_for(template_id))
        if template.metadata.id != template_id:
            raise ValueError("Template filename and metadata id do not match.")
        return template

    def _assert_unique_name(self, name: str, *, exclude_id: str | None = None) -> None:
        folded = validate_template_name(name).casefold()
        for template in self.templates():
            if template.metadata.id != exclude_id and template.metadata.name.casefold() == folded:
                raise ValueError(f"Template name already exists: {name}")

    def unique_imported_name(self, preferred: str, *, exclude_id: str | None = None) -> str:
        """Return a case-insensitively unique Imported display name."""

        occupied = {
            item.metadata.name.casefold()
            for item in self.templates()
            if item.metadata.id != exclude_id
        }
        base = validate_template_name(preferred)
        if base.casefold() not in occupied:
            return base
        suffix = 1
        marker = " Imported"
        candidate = f"{base[:80 - len(marker)]}{marker}"
        while candidate.casefold() in occupied:
            marker = f" Imported {suffix}"
            candidate = f"{base[:80 - len(marker)]}{marker}"
            suffix += 1
        return candidate

    def save(self, template: ChartTemplate, *, replace_existing: bool = False) -> Path:
        """Atomically create or explicitly replace one template file."""

        validate_template(template)
        self._assert_unique_name(template.metadata.name, exclude_id=template.metadata.id if replace_existing else None)
        path = self.path_for(template.metadata.id)
        if path.exists() and not replace_existing:
            raise FileExistsError(f"Template already exists: {template.metadata.name}")
        payload = json.dumps(
            template_to_dict(template),
            ensure_ascii=False,
            indent=2,
            allow_nan=False,
        ).encode("utf-8")
        if len(payload) > load_resource_limits().max_template_bytes:
            raise ValueError("Template exceeds the configured file-size budget.")
        self.root.mkdir(parents=True, exist_ok=True)
        temp_name: str | None = None
        try:
            with tempfile.NamedTemporaryFile(
                "wb", dir=self.root, delete=False, suffix=".tmp"
            ) as handle:
                temp_name = handle.name
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_name, path)
            temp_name = None
        finally:
            if temp_name and os.path.exists(temp_name):
                try:
                    os.unlink(temp_name)
                except OSError:
                    LOGGER.exception("Unable to remove temporary template file %s", temp_name)
        return path

    def rename(self, template_id: str, name: str) -> ChartTemplate:
        """Rename one template without changing its stable file name."""

        template = self.get(template_id)
        name = validate_template_name(name)
        self._assert_unique_name(name, exclude_id=template_id)
        updated = replace(
            template,
            metadata=replace(template.metadata, name=name, updated_at=utc_now_text()),
        )
        self.save(updated, replace_existing=True)
        return updated

    def save_notes(self, template_id: str, notes: str) -> ChartTemplate:
        """Atomically replace only one template's notes."""

        template = self.get(template_id)
        updated = replace(
            template,
            metadata=replace(template.metadata, notes=str(notes), updated_at=utc_now_text()),
        )
        self.save(updated, replace_existing=True)
        return updated

    def duplicate(self, template_id: str, name: str | None = None) -> ChartTemplate:
        """Create a distinct template with fresh identity and timestamps."""

        source = self.get(template_id)
        target_name = self.unique_imported_name(name or f"{source.metadata.name} Copy")
        now = utc_now_text()
        copy = replace(
            source,
            metadata=replace(
                source.metadata,
                id=str(uuid4()),
                name=target_name,
                created_at=now,
                updated_at=now,
            ),
        )
        self.save(copy)
        return copy

    def delete(self, template_id: str) -> None:
        """Delete exactly one validated stable template path."""

        path = self.path_for(template_id)
        if path.exists():
            path.unlink()

    def export_template(self, template_id: str, destination: str | Path) -> Path:
        """Export a validated template without mutating the library."""

        source = self.path_for(template_id)
        self.get(template_id)
        target = Path(destination)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        return target

    def import_template(self, source: str | Path, *, replace_same_id: bool = False) -> ChartTemplate:
        """Validate and import one external template with documented conflict rules."""

        source_path = Path(source)
        template = self._read_path(source_path)
        destination = self.path_for(template.metadata.id)
        if destination.exists() and not replace_same_id:
            raise FileExistsError(
                f"Template id already exists: {template.metadata.id}; confirmation is required."
            )
        target_name = self.unique_imported_name(
            template.metadata.name,
            exclude_id=template.metadata.id if replace_same_id else None,
        )
        if target_name != template.metadata.name:
            template = replace(
                template,
                metadata=replace(template.metadata, name=target_name, updated_at=utc_now_text()),
            )
        self.save(template, replace_existing=replace_same_id)
        return template

    def ensure_directory(self) -> Path:
        """Create and return the template directory for an explicit Open action."""

        self.root.mkdir(parents=True, exist_ok=True)
        return self.root
