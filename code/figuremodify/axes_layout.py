"""Typed specifications and helpers for Figure subplot layouts.

The objects in this module deliberately have no Qt imports.  Dialogs collect
values into :class:`AxesLayoutSpec`; the Canvas and domain services are the only
code allowed to turn those values into Matplotlib artists and Component state.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import math
from typing import Any, Iterable
from uuid import NAMESPACE_URL, uuid4, uuid5


class ShareMode(str, Enum):
    """Describe how primary Axes in a regular grid share one dimension."""

    NONE = "none"
    ALL = "all"
    ROW = "row"
    COLUMN = "column"


class AxesLayer(str, Enum):
    """Describe the only supported layers in one regular-grid cell."""

    PRIMARY = "primary"
    RIGHT_Y = "right_y"


ALLOWED_SCALES = ("linear", "log", "symlog", "logit")


def _finite(value: Any, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a finite number.")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{name} must be a finite number.")
    return result


def _positive(value: Any, name: str) -> float:
    result = _finite(value, name)
    if result <= 0:
        raise ValueError(f"{name} must be greater than zero.")
    return result


def _limit(value: tuple[float, float] | None, name: str):
    if value is None:
        return None
    if not isinstance(value, (tuple, list)) or len(value) != 2:
        raise ValueError(f"{name} must contain two numbers or be automatic.")
    lower = _finite(value[0], f"{name} minimum")
    upper = _finite(value[1], f"{name} maximum")
    if lower == upper:
        raise ValueError(f"{name} minimum and maximum must differ.")
    return (lower, upper)


@dataclass(frozen=True, slots=True)
class AxesViewSpec:
    """Common creation/edit values for one concrete Matplotlib Axes."""

    xlim: tuple[float, float] | None = None
    ylim: tuple[float, float] | None = None
    xscale: str = "linear"
    yscale: str = "linear"
    invert_x: bool = False
    invert_y: bool = False
    aspect: str | float = "auto"
    facecolor: str | None = None
    x_major_grid: bool = False
    x_minor_grid: bool = False
    y_major_grid: bool = False
    y_minor_grid: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "xlim", _limit(self.xlim, "X range"))
        object.__setattr__(self, "ylim", _limit(self.ylim, "Y range"))
        if self.xscale not in ALLOWED_SCALES:
            raise ValueError(f"Unsupported X scale: {self.xscale!r}.")
        if self.yscale not in ALLOWED_SCALES:
            raise ValueError(f"Unsupported Y scale: {self.yscale!r}.")
        if isinstance(self.aspect, str):
            if self.aspect not in {"auto", "equal"}:
                raise ValueError("Aspect must be auto, equal, or a positive number.")
        else:
            object.__setattr__(self, "aspect", _positive(self.aspect, "Aspect"))
        if self.facecolor is not None and not str(self.facecolor).strip():
            raise ValueError("Axes background color must not be empty.")

    @property
    def autoscalex_on(self) -> bool:
        return self.xlim is None

    @property
    def autoscaley_on(self) -> bool:
        return self.ylim is None


@dataclass(frozen=True, slots=True)
class AxesCellSpec:
    """Describe an occupied regular-grid cell and its optional right Y layer."""

    row: int
    column: int
    primary: AxesViewSpec = field(default_factory=AxesViewSpec)
    right_y: AxesViewSpec | None = None
    merge_legend: bool = False

    def __post_init__(self) -> None:
        if isinstance(self.row, bool) or not isinstance(self.row, int) or self.row < 0:
            raise ValueError("Cell row must be a non-negative integer.")
        if (
            isinstance(self.column, bool)
            or not isinstance(self.column, int)
            or self.column < 0
        ):
            raise ValueError("Cell column must be a non-negative integer.")
        if self.merge_legend and self.right_y is None:
            raise ValueError("A merged legend requires a right Y Axes.")


@dataclass(frozen=True, slots=True)
class AxesLayoutSpec:
    """Complete controller-free request for one regular-grid layout operation."""

    nrows: int
    ncols: int
    cells: tuple[AxesCellSpec, ...]
    width_ratios: tuple[float, ...] | None = None
    height_ratios: tuple[float, ...] | None = None
    left: float = 0.125
    right: float = 0.9
    bottom: float = 0.11
    top: float = 0.88
    wspace: float = 0.2
    hspace: float = 0.2
    share_x: ShareMode = ShareMode.NONE
    share_y: ShareMode = ShareMode.NONE
    outer_x_labels: bool = False
    outer_y_labels: bool = False
    constrained_layout: bool = False
    layout_id: str | None = None

    def __post_init__(self) -> None:
        for name, value in (("Rows", self.nrows), ("Columns", self.ncols)):
            if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 6:
                raise ValueError(f"{name} must be between 1 and 6.")
        cells = tuple(self.cells)
        if not cells:
            raise ValueError("A layout must contain at least one Axes cell.")
        object.__setattr__(self, "cells", cells)
        positions = {(cell.row, cell.column) for cell in cells}
        if len(positions) != len(cells):
            raise ValueError("A layout cannot define the same cell twice.")
        if any(row >= self.nrows or column >= self.ncols for row, column in positions):
            raise ValueError("An occupied cell lies outside the layout grid.")
        object.__setattr__(self, "share_x", ShareMode(self.share_x))
        object.__setattr__(self, "share_y", ShareMode(self.share_y))

        width_ratios = self.width_ratios or (1.0,) * self.ncols
        height_ratios = self.height_ratios or (1.0,) * self.nrows
        if len(width_ratios) != self.ncols:
            raise ValueError("Width ratios must match the number of columns.")
        if len(height_ratios) != self.nrows:
            raise ValueError("Height ratios must match the number of rows.")
        object.__setattr__(
            self,
            "width_ratios",
            tuple(_positive(value, "Width ratio") for value in width_ratios),
        )
        object.__setattr__(
            self,
            "height_ratios",
            tuple(_positive(value, "Height ratio") for value in height_ratios),
        )

        left = _finite(self.left, "Left margin")
        right = _finite(self.right, "Right margin")
        bottom = _finite(self.bottom, "Bottom margin")
        top = _finite(self.top, "Top margin")
        if not 0 <= left < right <= 1:
            raise ValueError("Layout margins require 0 <= left < right <= 1.")
        if not 0 <= bottom < top <= 1:
            raise ValueError("Layout margins require 0 <= bottom < top <= 1.")
        object.__setattr__(self, "left", left)
        object.__setattr__(self, "right", right)
        object.__setattr__(self, "bottom", bottom)
        object.__setattr__(self, "top", top)
        object.__setattr__(self, "wspace", _finite(self.wspace, "Horizontal spacing"))
        object.__setattr__(self, "hspace", _finite(self.hspace, "Vertical spacing"))
        if self.wspace < 0 or self.hspace < 0:
            raise ValueError("Layout spacing cannot be negative.")
        if self.layout_id is not None and not str(self.layout_id).strip():
            raise ValueError("Layout id must not be empty.")

    @classmethod
    def grid(
        cls,
        nrows: int,
        ncols: int,
        *,
        slots: Iterable[int] | None = None,
        cell_view: AxesViewSpec | None = None,
        **kwargs: Any,
    ) -> "AxesLayoutSpec":
        """Build a regular primary-only grid using one-based subplot slots."""

        selected = tuple(slots or range(1, int(nrows) * int(ncols) + 1))
        if not selected or len(set(selected)) != len(selected):
            raise ValueError("Subplot slots are invalid.")
        cells = []
        for slot in selected:
            if isinstance(slot, bool) or not isinstance(slot, int):
                raise ValueError("Subplot slots must be integers.")
            if not 1 <= slot <= int(nrows) * int(ncols):
                raise ValueError("Subplot slots are invalid.")
            index = slot - 1
            cells.append(
                AxesCellSpec(
                    index // int(ncols),
                    index % int(ncols),
                    primary=cell_view or AxesViewSpec(),
                )
            )
        return cls(int(nrows), int(ncols), tuple(cells), **kwargs)

    def resolved_layout_id(self) -> str:
        return str(self.layout_id or uuid4())

    def layout_definition(self, layout_id: str | None = None) -> dict[str, Any]:
        """Return the schema-v9 Figure-level geometry record."""

        return {
            "id": str(layout_id or self.resolved_layout_id()),
            "nrows": int(self.nrows),
            "ncols": int(self.ncols),
            "width_ratios": [float(value) for value in self.width_ratios or ()],
            "height_ratios": [float(value) for value in self.height_ratios or ()],
            "margins": {
                "left": float(self.left),
                "right": float(self.right),
                "bottom": float(self.bottom),
                "top": float(self.top),
            },
            "spacing": {
                "wspace": float(self.wspace),
                "hspace": float(self.hspace),
            },
        }


def stable_layout_id(project_id: str, legacy_group: int) -> str:
    """Return a deterministic layout id for a migrated v8 layout group."""

    return str(
        uuid5(
            NAMESPACE_URL,
            f"mygui-project:{str(project_id).strip()}:layout:{int(legacy_group)}",
        )
    )


def stable_share_group(layout_id: str, dimension: str, key: str) -> str:
    """Return a deterministic relationship id within one layout."""

    return str(
        uuid5(
            NAMESPACE_URL,
            f"mygui-layout:{layout_id}:share-{dimension}:{key}",
        )
    )


def share_group_for_cell(
    layout_id: str,
    dimension: str,
    mode: ShareMode,
    row: int,
    column: int,
) -> str | None:
    """Resolve a stable group id for one primary cell and sharing policy."""

    mode = ShareMode(mode)
    if mode is ShareMode.NONE:
        return None
    if mode is ShareMode.ALL:
        key = "all"
    elif mode is ShareMode.ROW:
        key = f"row-{row}"
    else:
        key = f"column-{column}"
    return stable_share_group(layout_id, dimension, key)


def subplot_record(
    layout_id: str,
    row: int,
    column: int,
    *,
    layer: AxesLayer = AxesLayer.PRIMARY,
    share_x_group: str | None = None,
    share_y_group: str | None = None,
) -> dict[str, Any]:
    """Build one canonical schema-v9 Axes layout record."""

    return {
        "layout_id": str(layout_id),
        "row": int(row),
        "column": int(column),
        "layer": AxesLayer(layer).value,
        "share_x_group": (
            str(share_x_group) if share_x_group is not None else None
        ),
        "share_y_group": (
            str(share_y_group) if share_y_group is not None else None
        ),
    }


def layout_definition_to_spec(
    definition: dict[str, Any],
    cells: Iterable[AxesCellSpec],
    **kwargs: Any,
) -> AxesLayoutSpec:
    """Build an editable spec from one validated persisted layout record."""

    margins = dict(definition["margins"])
    spacing = dict(definition["spacing"])
    return AxesLayoutSpec(
        int(definition["nrows"]),
        int(definition["ncols"]),
        tuple(cells),
        width_ratios=tuple(definition["width_ratios"]),
        height_ratios=tuple(definition["height_ratios"]),
        left=float(margins["left"]),
        right=float(margins["right"]),
        bottom=float(margins["bottom"]),
        top=float(margins["top"]),
        wspace=float(spacing["wspace"]),
        hspace=float(spacing["hspace"]),
        layout_id=str(definition["id"]),
        **kwargs,
    )
