"""Density bands and the font-metric floor for control heights."""

from __future__ import annotations

import math
from dataclasses import dataclass

from .models import Density, DensityMetrics


@dataclass(frozen=True, slots=True)
class DensityBand:
    """Closed logical-pixel band before the font-metric floor."""

    spacing_xs: int
    spacing_sm: int
    spacing_md: int
    spacing_lg: int
    spacing_xl: int
    rail: int
    button: int
    bottom: int
    command: int
    gallery: int
    table_row: int
    table_header: int
    tree: int
    control: int
    vertical_padding: int


# vertical_padding is 2 × spacing_xs so rows keep the density grammar.
DENSITY_BANDS: dict[Density, DensityBand] = {
    Density.COMPACT: DensityBand(
        spacing_xs=3,
        spacing_sm=6,
        spacing_md=9,
        spacing_lg=12,
        spacing_xl=18,
        rail=40,
        button=36,
        bottom=24,
        command=42,
        gallery=64,
        table_row=22,
        table_header=38,
        tree=22,
        control=26,
        vertical_padding=6,
    ),
    Density.STANDARD: DensityBand(
        spacing_xs=4,
        spacing_sm=8,
        spacing_md=12,
        spacing_lg=16,
        spacing_xl=24,
        rail=44,
        button=40,
        bottom=28,
        command=48,
        gallery=72,
        table_row=24,
        table_header=44,
        tree=26,
        control=30,
        vertical_padding=8,
    ),
    Density.COMFORTABLE: DensityBand(
        spacing_xs=5,
        spacing_sm=10,
        spacing_md=15,
        spacing_lg=20,
        spacing_xl=30,
        rail=52,
        button=48,
        bottom=34,
        command=56,
        gallery=84,
        table_row=30,
        table_header=52,
        tree=32,
        control=36,
        vertical_padding=10,
    ),
}


def build_density_metrics(density: Density, font_height: int) -> DensityMetrics:
    """Return band sizes floored by ``ceil(font_height) + vertical_padding``."""

    band = DENSITY_BANDS[density]
    floor = int(math.ceil(font_height)) + band.vertical_padding

    def height(value: int) -> int:
        return max(value, floor)

    return DensityMetrics(
        spacing_xs=band.spacing_xs,
        spacing_sm=band.spacing_sm,
        spacing_md=band.spacing_md,
        spacing_lg=band.spacing_lg,
        spacing_xl=band.spacing_xl,
        rail=height(band.rail),
        button=height(band.button),
        bottom=height(band.bottom),
        command=height(band.command),
        gallery=height(band.gallery),
        table_row=height(band.table_row),
        table_header=height(band.table_header),
        tree=height(band.tree),
        control=height(band.control),
        vertical_padding=band.vertical_padding,
        font_height=int(math.ceil(font_height)),
    )
