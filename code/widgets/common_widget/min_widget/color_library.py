"""Persist custom, favorite, and recently used color palettes."""

from __future__ import annotations

import json
from uuid import uuid4

from Qt_core import QObject, QSettings, Signal

from code.figuremodify.style_base.color_models import (
    PaletteDefinition,
    builtin_palette_map,
    builtin_palettes,
    normalize_color,
)


class ColorLibrary(QObject):
    """Application-level recent, favorite, and custom color preferences."""

    changed = Signal()

    SETTINGS_GROUP = "colorLibrary"
    SETTINGS_VERSION = 1
    RECENT_LIMIT = 20

    def __init__(self, settings: QSettings | None = None, parent: QObject | None = None):
        super().__init__(parent)
        self.settings = settings
        self.recent_colors: list[str] = []
        self.favorite_colors: list[str] = []
        self.favorite_palette_ids: list[str] = []
        self.custom_palettes: dict[str, PaletteDefinition] = {}
        self._load_warning = False
        self._load()

    @staticmethod
    def _deduplicate_colors(values, *, limit: int | None = None) -> list[str]:
        result: list[str] = []
        for value in values if isinstance(values, (list, tuple)) else ():
            try:
                color = normalize_color(value)
            except ValueError:
                continue
            if color not in result:
                result.append(color)
            if limit is not None and len(result) >= limit:
                break
        return result

    def _load(self) -> None:
        if self.settings is None:
            return
        self.settings.beginGroup(self.SETTINGS_GROUP)
        try:
            try:
                version = int(self.settings.value("version", 0))
            except (TypeError, ValueError, OverflowError):
                version = 0
            raw_state = self.settings.value("state", "")
        finally:
            self.settings.endGroup()
        if not raw_state:
            return
        if version != self.SETTINGS_VERSION:
            self._load_warning = True
            return
        try:
            state = json.loads(str(raw_state))
            if not isinstance(state, dict):
                raise ValueError("Color library state must be an object.")
        except (TypeError, ValueError, json.JSONDecodeError):
            self._load_warning = True
            return

        self.recent_colors = self._deduplicate_colors(
            state.get("recent_colors"), limit=self.RECENT_LIMIT
        )
        self.favorite_colors = self._deduplicate_colors(state.get("favorite_colors"))

        custom_names: set[str] = set()
        for raw_palette in state.get("custom_palettes", ()):
            try:
                palette = PaletteDefinition.from_dict(raw_palette, source="custom")
                if not 2 <= len(palette.colors) <= 12:
                    raise ValueError("Custom palettes require 2-12 colors.")
                normalized_name = palette.name.casefold()
                if normalized_name in custom_names or palette.id in self.custom_palettes:
                    raise ValueError("Duplicate custom palette.")
            except (TypeError, ValueError):
                self._load_warning = True
                continue
            custom_names.add(normalized_name)
            self.custom_palettes[palette.id] = palette

        available_ids = set(builtin_palette_map()) | set(self.custom_palettes)
        for palette_id in state.get("favorite_palette_ids", ()):
            palette_id = str(palette_id)
            if palette_id in available_ids and palette_id not in self.favorite_palette_ids:
                self.favorite_palette_ids.append(palette_id)

    def _save(self) -> None:
        if self.settings is None:
            return
        state = {
            "recent_colors": list(self.recent_colors),
            "favorite_colors": list(self.favorite_colors),
            "favorite_palette_ids": list(self.favorite_palette_ids),
            "custom_palettes": [
                palette.to_dict() for palette in self.custom_palettes.values()
            ],
        }
        self.settings.beginGroup(self.SETTINGS_GROUP)
        try:
            self.settings.setValue("version", self.SETTINGS_VERSION)
            self.settings.setValue("state", json.dumps(state, ensure_ascii=False))
        finally:
            self.settings.endGroup()
        self.settings.sync()

    def _commit_change(self) -> None:
        self._save()
        self.changed.emit()

    def consume_load_warning(self) -> bool:
        """Return and clear load warning."""

        warning = self._load_warning
        self._load_warning = False
        return warning

    def palettes(self) -> tuple[PaletteDefinition, ...]:
        """Return the available palettes."""

        return builtin_palettes() + tuple(self.custom_palettes.values())

    def palette(self, palette_id: str) -> PaletteDefinition | None:
        """Return the requested palette."""

        return builtin_palette_map().get(palette_id) or self.custom_palettes.get(palette_id)

    def favorite_palettes(self) -> tuple[PaletteDefinition, ...]:
        """Return the available favorite palettes."""

        return tuple(
            palette
            for palette_id in self.favorite_palette_ids
            if (palette := self.palette(palette_id)) is not None
        )

    def record_recent(self, color) -> str:
        """Record recent."""

        normalized = normalize_color(color)
        self.record_recent_many((normalized,))
        return normalized

    def record_recent_many(self, colors) -> tuple[str, ...]:
        """Record recent many."""

        normalized_colors = tuple(normalize_color(color) for color in colors)
        recent = list(self.recent_colors)
        for normalized in normalized_colors:
            recent = [normalized, *(value for value in recent if value != normalized)]
        self.recent_colors = recent[: self.RECENT_LIMIT]
        self._commit_change()
        return normalized_colors

    def is_favorite_color(self, color) -> bool:
        """Return whether favorite color."""

        return normalize_color(color) in self.favorite_colors

    def toggle_favorite_color(self, color) -> bool:
        """Toggle favorite color."""

        normalized = normalize_color(color)
        if normalized in self.favorite_colors:
            self.favorite_colors.remove(normalized)
            favorite = False
        else:
            self.favorite_colors.append(normalized)
            favorite = True
        self._commit_change()
        return favorite

    def is_favorite_palette(self, palette_id: str) -> bool:
        """Return whether favorite palette."""

        return str(palette_id) in self.favorite_palette_ids

    def toggle_favorite_palette(self, palette_id: str) -> bool:
        """Toggle favorite palette."""

        palette_id = str(palette_id)
        if self.palette(palette_id) is None:
            raise ValueError(f"Unknown palette: {palette_id}")
        if palette_id in self.favorite_palette_ids:
            self.favorite_palette_ids.remove(palette_id)
            favorite = False
        else:
            self.favorite_palette_ids.append(palette_id)
            favorite = True
        self._commit_change()
        return favorite

    def _validate_custom_name(self, name: str, *, exclude_id: str | None = None) -> str:
        name = str(name).strip()
        if not name:
            raise ValueError("Custom palette name must not be empty.")
        normalized = name.casefold()
        for palette in self.custom_palettes.values():
            if palette.id != exclude_id and palette.name.casefold() == normalized:
                raise ValueError(f"Custom palette already exists: {name}")
        return name

    @staticmethod
    def _validate_custom_colors(colors) -> tuple[str, ...]:
        normalized = tuple(normalize_color(color) for color in colors)
        if not 2 <= len(normalized) <= 12:
            raise ValueError("Custom palettes require 2-12 colors.")
        return normalized

    def create_custom_palette(self, name: str, colors) -> PaletteDefinition:
        """Create custom palette."""

        palette = PaletteDefinition(
            id=f"custom:{uuid4()}",
            name=self._validate_custom_name(name),
            category="自定义配色",
            source="custom",
            colors=self._validate_custom_colors(colors),
        )
        self.custom_palettes[palette.id] = palette
        self._commit_change()
        return palette

    def update_custom_palette(self, palette_id: str, name: str, colors) -> PaletteDefinition:
        """Update custom palette."""

        current = self.custom_palettes.get(str(palette_id))
        if current is None:
            raise ValueError(f"Unknown custom palette: {palette_id}")
        palette = PaletteDefinition(
            id=current.id,
            name=self._validate_custom_name(name, exclude_id=current.id),
            category="自定义配色",
            source="custom",
            colors=self._validate_custom_colors(colors),
        )
        self.custom_palettes[palette.id] = palette
        self._commit_change()
        return palette

    def delete_custom_palette(self, palette_id: str) -> bool:
        """Delete custom palette."""

        palette_id = str(palette_id)
        if self.custom_palettes.pop(palette_id, None) is None:
            return False
        try:
            self.favorite_palette_ids.remove(palette_id)
        except ValueError:
            pass
        self._commit_change()
        return True
