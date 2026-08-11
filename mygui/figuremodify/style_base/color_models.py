"""Define color palettes, selections, and ordered color-cycle state."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from functools import lru_cache
from typing import Any

from matplotlib.colors import to_hex, to_rgba

from mygui.figuremodify.style_base.color_base import color_combi_dict


DEFAULT_COLOR = "#000000"


class PaletteSource(StrEnum):
    """Stable wire values describing where a palette originated."""

    BUILTIN = "builtin"
    CUSTOM = "custom"
    MATPLOTLIB_STYLE = "matplotlib-style"


def normalize_color(value: Any) -> str:
    """Return a Matplotlib color as canonical ``#RRGGBB``/``#RRGGBBAA``."""
    try:
        rgba = to_rgba(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Invalid color: {value!r}") from exc
    keep_alpha = rgba[3] < 1.0
    return to_hex(rgba, keep_alpha=keep_alpha).upper()


@dataclass(frozen=True, slots=True)
class PaletteDefinition:
    """Represent the application's palette definition."""

    id: str
    name: str
    colors: tuple[str, ...]
    category: str = ""
    source: PaletteSource | str = PaletteSource.BUILTIN

    def __post_init__(self):
        palette_id = str(self.id).strip()
        name = str(self.name).strip()
        colors = tuple(normalize_color(color) for color in self.colors)
        if not palette_id:
            raise ValueError("Palette id must not be empty.")
        if not name:
            raise ValueError("Palette name must not be empty.")
        if not colors:
            raise ValueError("A palette must contain at least one color.")
        object.__setattr__(self, "id", palette_id)
        object.__setattr__(self, "name", name)
        object.__setattr__(self, "colors", colors)
        object.__setattr__(self, "category", str(self.category).strip())
        source = str(self.source).strip() or PaletteSource.BUILTIN.value
        object.__setattr__(self, "source", PaletteSource(source))

    @property
    def display_name(self) -> str:
        """Return the display name."""

        if self.category and self.category != self.name:
            return f"{self.category} · {self.name}"
        return self.name

    def to_dict(self) -> dict[str, Any]:
        """Convert this object to dict."""

        return {
            "id": self.id,
            "name": self.name,
            "category": self.category,
            "source": self.source.value,
            "colors": list(self.colors),
        }

    @classmethod
    def from_dict(cls, value: Any, *, source: str | None = None) -> "PaletteDefinition":
        """Build an instance from dict."""

        if not isinstance(value, dict):
            raise ValueError("Palette state must be an object.")
        return cls(
            id=value.get("id", ""),
            name=value.get("name", ""),
            category=value.get("category", ""),
            source=source or value.get("source", PaletteSource.BUILTIN.value),
            colors=tuple(value.get("colors", ())),
        )


@dataclass(frozen=True, slots=True)
class ColorSelection:
    """Represent the application's color selection."""

    color: str
    palette: PaletteDefinition | None = None
    palette_index: int | None = None

    def __post_init__(self):
        color = normalize_color(self.color)
        object.__setattr__(self, "color", color)
        if self.palette is None:
            object.__setattr__(self, "palette_index", None)
            return
        if self.palette_index is None:
            raise ValueError("Palette selections require an index.")
        index = int(self.palette_index)
        if not 0 <= index < len(self.palette.colors):
            raise ValueError("Palette selection index is out of range.")
        if color != self.palette.colors[index]:
            raise ValueError("Palette selection color does not match its index.")
        object.__setattr__(self, "palette_index", index)


class ColorCycleState:
    """Per-axes color sequence with explicit preview/commit semantics."""

    def __init__(self, palette: PaletteDefinition | None = None, next_index: int = 0):
        self.palette: PaletteDefinition | None = None
        self.next_index = 0
        if palette is not None:
            self.activate(palette, next_index)

    @property
    def active_palette(self) -> PaletteDefinition | None:
        """Return the palette currently used by the color cycle."""

        return self.palette

    def reset(self) -> None:
        """Restore the initial state."""

        self.palette = None
        self.next_index = 0

    def activate(self, palette: PaletteDefinition, next_index: int = 0) -> None:
        """Activate a palette and reset its per-axes cursor."""

        if not isinstance(palette, PaletteDefinition):
            raise TypeError("palette must be a PaletteDefinition.")
        self.palette = palette
        self.next_index = int(next_index) % len(palette.colors)

    def peek(self) -> ColorSelection:
        """Preview the next color without advancing the cycle."""

        if self.palette is None:
            return ColorSelection(DEFAULT_COLOR)
        index = self.next_index % len(self.palette.colors)
        return ColorSelection(self.palette.colors[index], self.palette, index)

    def commit(self, selection: ColorSelection) -> None:
        """Advance only palette-backed selections; custom single colors are one-off."""
        if not isinstance(selection, ColorSelection):
            raise TypeError("selection must be a ColorSelection.")
        if selection.palette is None:
            return
        self.palette = selection.palette
        self.next_index = (int(selection.palette_index) + 1) % len(selection.palette.colors)

    def commit_palette_for_count(self, palette: PaletteDefinition, object_count: int) -> None:
        """Commit palette for count."""

        self.activate(palette, int(object_count) % len(palette.colors))

    def to_dict(self) -> dict[str, Any] | None:
        """Convert this object to dict."""

        if self.palette is None:
            return None
        return {
            "palette": self.palette.to_dict(),
            "next_index": int(self.next_index),
        }

    @classmethod
    def from_dict(cls, value: Any) -> "ColorCycleState":
        """Build an instance from dict."""

        if value is None:
            return cls()
        if not isinstance(value, dict):
            raise ValueError("Color cycle state must be an object or null.")
        palette = PaletteDefinition.from_dict(value.get("palette"))
        try:
            next_index = int(value.get("next_index", 0))
        except (TypeError, ValueError, OverflowError) as exc:
            raise ValueError("Color cycle next_index must be an integer.") from exc
        if not 0 <= next_index < len(palette.colors):
            raise ValueError("Color cycle next_index is out of range.")
        return cls(palette, next_index)


@lru_cache(maxsize=1)
def builtin_palettes() -> tuple[PaletteDefinition, ...]:
    """Return the built-in palette definitions."""

    palettes: list[PaletteDefinition] = []
    for category_index, (category, definitions) in enumerate(color_combi_dict.items()):
        if not isinstance(definitions, dict):
            continue
        for palette_index, (name, colors) in enumerate(definitions.items(), start=1):
            palettes.append(
                PaletteDefinition(
                    id=f"builtin:{category_index}:{palette_index:02d}",
                    name=name,
                    category=category,
                    colors=tuple(colors),
                )
            )
    return tuple(palettes)


@lru_cache(maxsize=1)
def builtin_palette_map() -> dict[str, PaletteDefinition]:
    """Return built-in palettes keyed by name."""

    return {palette.id: palette for palette in builtin_palettes()}


def all_single_colors() -> tuple[str, ...]:
    """Return all distinct colors from the built-in palettes."""

    for definitions in color_combi_dict.values():
        if not isinstance(definitions, dict):
            return tuple(normalize_color(color) for color in definitions)
    return ()
