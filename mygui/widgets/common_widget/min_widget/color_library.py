"""Persist custom, favorite, and recently used color palettes."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import uuid4

from PySide6.QtCore import QObject, Signal

from mygui.application_settings.storage.types import (
    DocumentHealth,
)

from mygui.figuremodify.style_base.color_models import (
    PaletteDefinition,
    PaletteSource,
    builtin_palette_map,
    builtin_palettes,
    normalize_color,
)


class ColorLibraryStoreError(RuntimeError):
    """Raised when a color-library mutation could not be made durable."""


@dataclass(frozen=True, slots=True)
class ColorLibraryCounts:
    """Persisted color-library data counts. Built-in palettes are excluded."""

    recent_colors: int = 0
    favorite_colors: int = 0
    favorite_palettes: int = 0
    custom_palettes: int = 0


class ColorLibrary(QObject):
    """Application-level recent, favorite, and custom color preferences."""

    changed = Signal()

    SETTINGS_GROUP = "colorLibrary"
    SETTINGS_VERSION = 1
    RECENT_LIMIT = 20

    def __init__(self, settings=None, parent: QObject | None = None, *, document=None):
        super().__init__(parent)
        self._document = _resolve_color_document(settings, document)
        self.recent_colors: list[str] = []
        self.favorite_colors: list[str] = []
        self.favorite_palette_ids: list[str] = []
        self.custom_palettes: dict[str, PaletteDefinition] = {}
        self._load_warning = False
        self._health = DocumentHealth.NORMAL
        self._diagnostics: tuple[str, ...] = ()
        self._payload_applied = False
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
        if self._document is None:
            return
        try:
            loaded = self._document.load()
        except Exception:
            self._load_warning = True
            return
        payload = getattr(loaded, "payload", None)
        health = getattr(loaded, "health", None)
        diagnostics = tuple(getattr(loaded, "diagnostics", ()) or ())
        self._diagnostics = diagnostics
        if isinstance(health, DocumentHealth):
            self._health = health
        elif health is not None:
            try:
                self._health = DocumentHealth(str(getattr(health, "value", health)))
            except ValueError:
                self._health = DocumentHealth.NORMAL
        notes = " ".join(str(item) for item in diagnostics).casefold()
        if getattr(loaded, "error", None) or any(
            token in notes
            for token in ("invalid", "unknown version", "failed", "empty state", "corrupt")
        ):
            self._load_warning = True
        if payload is None:
            if self._health in {
                DocumentHealth.RECOVERY_REQUIRED,
                DocumentHealth.READ_ONLY_FUTURE,
                DocumentHealth.WRITE_UNCERTAIN,
            }:
                self._load_warning = True
                return
            payload = {}
        if not isinstance(payload, dict):
            payload = {}
        self._apply_payload(payload)
        self._payload_applied = True

    def document_health(self) -> DocumentHealth:
        """Return the last dual-slot load health for this library."""

        return self._health

    def writable(self) -> bool:
        """Return whether Clear/Reset may commit the color document."""

        return self._health in {DocumentHealth.NORMAL, DocumentHealth.DEGRADED}

    def diagnostics(self) -> tuple[str, ...]:
        return self._diagnostics

    def payload_applied(self) -> bool:
        return self._payload_applied

    def reload(self) -> None:
        """Reload lists from the document without emitting ``changed``."""

        self.recent_colors = []
        self.favorite_colors = []
        self.favorite_palette_ids = []
        self.custom_palettes = {}
        self._payload_applied = False
        self._load()

    def _apply_payload(self, payload: dict) -> None:
        self.recent_colors = self._deduplicate_colors(
            payload.get("recent_colors"), limit=self.RECENT_LIMIT
        )
        self.favorite_colors = self._deduplicate_colors(payload.get("favorite_colors"))
        self.custom_palettes = {}
        self.favorite_palette_ids = []

        custom_names: set[str] = set()
        for raw_palette in payload.get("custom_palettes", ()) or ():
            try:
                palette = PaletteDefinition.from_dict(
                    raw_palette,
                    source=PaletteSource.CUSTOM,
                )
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
        for palette_id in payload.get("favorite_palette_ids", ()) or ():
            palette_id = str(palette_id)
            if palette_id in available_ids and palette_id not in self.favorite_palette_ids:
                self.favorite_palette_ids.append(palette_id)

    def _payload(
        self,
        *,
        recent_colors: list[str] | None = None,
        favorite_colors: list[str] | None = None,
        favorite_palette_ids: list[str] | None = None,
        custom_palettes: dict[str, PaletteDefinition] | None = None,
    ) -> dict:
        palettes = self.custom_palettes if custom_palettes is None else custom_palettes
        return {
            "recent_colors": list(
                self.recent_colors if recent_colors is None else recent_colors
            ),
            "favorite_colors": list(
                self.favorite_colors if favorite_colors is None else favorite_colors
            ),
            "favorite_palette_ids": list(
                self.favorite_palette_ids
                if favorite_palette_ids is None
                else favorite_palette_ids
            ),
            "custom_palettes": [palette.to_dict() for palette in palettes.values()],
        }

    def _commit_payload(self, payload: dict) -> bool:
        if self._document is None:
            return True
        try:
            result = self._document.commit(payload)
        except Exception:
            return False
        return _commit_succeeded(result)

    def _publish(
        self,
        *,
        recent_colors: list[str] | None = None,
        favorite_colors: list[str] | None = None,
        favorite_palette_ids: list[str] | None = None,
        custom_palettes: dict[str, PaletteDefinition] | None = None,
    ) -> bool:
        if self._document is not None and not self.writable():
            return False
        payload = self._payload(
            recent_colors=recent_colors,
            favorite_colors=favorite_colors,
            favorite_palette_ids=favorite_palette_ids,
            custom_palettes=custom_palettes,
        )
        if not self._commit_payload(payload):
            return False
        if recent_colors is not None:
            self.recent_colors = recent_colors
        if favorite_colors is not None:
            self.favorite_colors = favorite_colors
        if favorite_palette_ids is not None:
            self.favorite_palette_ids = favorite_palette_ids
        if custom_palettes is not None:
            self.custom_palettes = custom_palettes
        self.changed.emit()
        return True

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
        next_recent = recent[: self.RECENT_LIMIT]
        self._publish(recent_colors=next_recent)
        return normalized_colors

    def is_favorite_color(self, color) -> bool:
        """Return whether favorite color."""

        return normalize_color(color) in self.favorite_colors

    def toggle_favorite_color(self, color) -> bool:
        """Toggle favorite color."""

        normalized = normalize_color(color)
        currently = normalized in self.favorite_colors
        next_favorites = list(self.favorite_colors)
        if currently:
            next_favorites.remove(normalized)
            desired = False
        else:
            next_favorites.append(normalized)
            desired = True
        if not self._publish(favorite_colors=next_favorites):
            return currently
        return desired

    def is_favorite_palette(self, palette_id: str) -> bool:
        """Return whether favorite palette."""

        return str(palette_id) in self.favorite_palette_ids

    def toggle_favorite_palette(self, palette_id: str) -> bool:
        """Toggle favorite palette."""

        palette_id = str(palette_id)
        if self.palette(palette_id) is None:
            raise ValueError(f"Unknown palette: {palette_id}")
        currently = palette_id in self.favorite_palette_ids
        next_ids = list(self.favorite_palette_ids)
        if currently:
            next_ids.remove(palette_id)
            desired = False
        else:
            next_ids.append(palette_id)
            desired = True
        if not self._publish(favorite_palette_ids=next_ids):
            return currently
        return desired

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
            category="Custom",
            source=PaletteSource.CUSTOM,
            colors=self._validate_custom_colors(colors),
        )
        next_palettes = dict(self.custom_palettes)
        next_palettes[palette.id] = palette
        if not self._publish(custom_palettes=next_palettes):
            raise ColorLibraryStoreError("Color library could not be saved.")
        return palette

    def update_custom_palette(self, palette_id: str, name: str, colors) -> PaletteDefinition:
        """Update custom palette."""

        current = self.custom_palettes.get(str(palette_id))
        if current is None:
            raise ValueError(f"Unknown custom palette: {palette_id}")
        palette = PaletteDefinition(
            id=current.id,
            name=self._validate_custom_name(name, exclude_id=current.id),
            category="Custom",
            source=PaletteSource.CUSTOM,
            colors=self._validate_custom_colors(colors),
        )
        next_palettes = dict(self.custom_palettes)
        next_palettes[palette.id] = palette
        if not self._publish(custom_palettes=next_palettes):
            raise ColorLibraryStoreError("Color library could not be saved.")
        return palette

    def delete_custom_palette(self, palette_id: str) -> bool:
        """Delete custom palette."""

        palette_id = str(palette_id)
        if palette_id not in self.custom_palettes:
            return False
        next_palettes = dict(self.custom_palettes)
        next_palettes.pop(palette_id)
        next_ids = [item for item in self.favorite_palette_ids if item != palette_id]
        if not self._publish(
            favorite_palette_ids=next_ids,
            custom_palettes=next_palettes,
        ):
            return False
        return True

    def counts(self) -> ColorLibraryCounts:
        """Return persisted data counts. Built-in palettes are not counted."""

        return ColorLibraryCounts(
            recent_colors=len(self.recent_colors),
            favorite_colors=len(self.favorite_colors),
            favorite_palettes=len(self.favorite_palette_ids),
            custom_palettes=len(self.custom_palettes),
        )

    def clear_recent_colors(self) -> bool:
        """Clear recent colors. Favorites and custom palettes are kept."""

        if not self.recent_colors:
            return True
        return self._publish(recent_colors=[])

    def reset_library(self) -> bool:
        """Clear recents, favorites, and custom palettes. Built-ins remain."""

        return self._publish(
            recent_colors=[],
            favorite_colors=[],
            favorite_palette_ids=[],
            custom_palettes={},
        )


def _commit_succeeded(result) -> bool:
    if result is None:
        return False
    ok = getattr(result, "ok", None)
    if ok is None:
        ok = getattr(result, "success", False)
    return bool(ok)


def _resolve_color_document(settings, document):
    if document is not None:
        return document
    if settings is None:
        return None
    if callable(getattr(settings, "load", None)) and callable(
        getattr(settings, "commit", None)
    ):
        return settings
    from mygui.application_settings.storage import create_settings_backend

    # Tests may still pass a QSettings store. Production ColorLibrary receives
    # backend.color_library_settings_port() and must not wrap a second backend.
    return create_settings_backend(settings).color_library_settings_port()
