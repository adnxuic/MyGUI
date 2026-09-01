"""Immutable, non-persisted Canvas creation requests.

Public ``add_*`` methods normalize caller arguments into these records and
delegate. They are not project, template, or settings schema.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from mygui.database import ColumnRef, DataPreprocessSpec, FitInputRangeSpec
from mygui.database.interpolate_func import DEFAULT_INTERPOLATION_SAMPLES
from mygui.figuremodify.components import FitEngine
from mygui.figuremodify.style_base.color_models import ColorCycleState, ColorSelection


@dataclass(frozen=True, slots=True)
class PlotCreateRequest:
    x: Any
    y: Any
    style: Any
    size: Any
    color: Any
    label: Any
    x_ref: ColumnRef
    y_ref: ColumnRef
    object_id: str | None = None
    color_order: int | None = None
    linewidth: float | None = None
    preprocess: DataPreprocessSpec | dict[str, Any] | None = None
    marker: Any = None
    markeredgewidth: float | None = None
    color_selection: ColorSelection | None = None
    preview_cycle: ColorCycleState | None = None


@dataclass(frozen=True, slots=True)
class PlotBatchCreateRequest:
    x_ref: ColumnRef
    y_refs: Any
    style: Any
    size: Any
    linewidth: float | None
    preprocess: DataPreprocessSpec | dict[str, Any] | None
    color_selection: ColorSelection
    record_recent: bool = True
    marker: Any = None
    markeredgewidth: float | None = None


@dataclass(frozen=True, slots=True)
class ScatterCreateRequest:
    x: Any
    y: Any
    size: Any
    color: Any
    marker: Any
    label: Any
    x_ref: ColumnRef
    y_ref: ColumnRef
    object_id: str | None = None
    color_order: int | None = None
    preprocess: DataPreprocessSpec | dict[str, Any] | None = None
    color_ref: ColumnRef | None = None
    size_ref: ColumnRef | None = None
    color_mapping: dict[str, Any] | None = None
    size_mapping: dict[str, Any] | None = None
    linewidth: float | None = None
    color_selection: ColorSelection | None = None
    preview_cycle: ColorCycleState | None = None


@dataclass(frozen=True, slots=True)
class ScatterBatchCreateRequest:
    x_ref: ColumnRef
    y_refs: Any
    size: Any
    marker: Any
    preprocess: DataPreprocessSpec | dict[str, Any] | None
    color_selection: ColorSelection
    color_ref: ColumnRef | None = None
    size_ref: ColumnRef | None = None
    color_mapping: dict[str, Any] | None = None
    size_mapping: dict[str, Any] | None = None
    record_recent: bool = True
    linewidth: float | None = None


@dataclass(frozen=True, slots=True)
class CurveCreateRequest:
    func_text: str
    x_start: float
    x_stop: float
    style: Any
    color: Any
    label: str
    color_order: int | None = None
    object_id: str | None = None
    color_selection: ColorSelection | None = None
    preview_cycle: ColorCycleState | None = None
    linewidth: float | None = None
    marker: str | None = None
    markersize: float | None = None
    markeredgewidth: float | None = None


@dataclass(frozen=True, slots=True)
class LineCreateRequest:
    x: Any
    y: Any
    style: str = "-"
    color: str = "black"
    label: str = ""
    object_id: str | None = None
    color_order: int | None = None


@dataclass(frozen=True, slots=True)
class ErrorBarCreateRequest:
    x_ref: ColumnRef
    y_ref: ColumnRef
    label: str
    xerr: dict[str, Any] | None = None
    yerr: dict[str, Any] | None = None
    preprocess: DataPreprocessSpec | dict[str, Any] | None = None
    object_id: str | None = None
    color_order: int | None = None
    color: Any = None
    color_selection: ColorSelection | None = None
    preview_cycle: ColorCycleState | None = None
    linestyle: Any = None
    linewidth: Any = None
    marker: Any = None
    markersize: Any = None
    markeredgewidth: Any = None
    markerfacecoloralt: Any = None
    fillstyle: Any = None
    drawstyle: Any = None
    antialiased: Any = None
    ecolor: Any = None
    elinewidth: Any = None
    capsize: Any = None
    capthick: Any = None
    error_linestyle: Any = None
    error_capstyle: Any = None
    error_antialiased: Any = None
    errorevery: Any = None
    lolims: Any = None
    uplims: Any = None
    xlolims: Any = None
    xuplims: Any = None
    barsabove: Any = None


@dataclass(frozen=True, slots=True)
class FitCurveCreateRequest:
    x: Any
    y: Any
    color: Any
    label: Any
    x_ref: ColumnRef
    y_ref: ColumnRef
    engine: FitEngine | str = FitEngine.PYTHON
    fit_type: Any = None
    fit_options: Any = None
    fit_result: Any = None
    expression: str = ""
    x_start: float | None = None
    x_stop: float | None = None
    style: str | None = None
    object_id: str | None = None
    color_order: int | None = None
    preprocess: DataPreprocessSpec | dict[str, Any] | None = None
    fit_input_range: FitInputRangeSpec | dict[str, Any] | None = None
    color_selection: ColorSelection | None = None
    preview_cycle: ColorCycleState | None = None
    linewidth: float | None = None
    marker: str | None = None
    markersize: float | None = None
    markeredgewidth: float | None = None


@dataclass(frozen=True, slots=True)
class InterpolationCreateRequest:
    x: Any
    y: Any
    x_ref: ColumnRef
    y_ref: ColumnRef
    method: Any
    k: int = 3
    label: str = "interpolate"
    color: str = "black"
    samples: int = DEFAULT_INTERPOLATION_SAMPLES
    lam: float | None = None
    lam_auto: bool = True
    object_id: str | None = None
    color_order: int | None = None
    allow_empty: bool = False
    preprocess: DataPreprocessSpec | dict[str, Any] | None = None
    announce: bool = True
    color_selection: ColorSelection | None = None
    preview_cycle: ColorCycleState | None = None
    linestyle: Any = None
    linewidth: float | None = None
    marker: Any = None
    markersize: float | None = None
    markeredgewidth: float | None = None


@dataclass(frozen=True, slots=True)
class InterpolationBatchCreateRequest:
    x_ref: ColumnRef
    y_refs: Any
    method: Any
    color_selection: ColorSelection
    k: int = 3
    samples: int = DEFAULT_INTERPOLATION_SAMPLES
    lam: float | None = None
    lam_auto: bool = True
    preprocess: DataPreprocessSpec | dict[str, Any] | None = None
    linestyle: Any = None
    linewidth: float | None = None
    marker: Any = None
    markersize: float | None = None
    markeredgewidth: float | None = None


@dataclass(frozen=True, slots=True)
class AnnotationCreateRequest:
    properties: dict[str, Any] | None = None
    axes_id: str | None = None
    object_id: str | None = None
    component_order: int | None = None
    announce: bool = True


@dataclass(frozen=True, slots=True)
class InAxesElementCreateRequest:
    spec: Any
    object_id: str | None = None


@dataclass(frozen=True, slots=True)
class Field2DCreateRequest:
    role: Any
    display_name: str
    x_ref: ColumnRef | dict[str, Any]
    y_ref: ColumnRef | dict[str, Any]
    z_ref: ColumnRef | dict[str, Any]
    properties: dict[str, Any] | None
    object_id: str | None
    color_order: int | None
    announce: bool


@dataclass(frozen=True, slots=True)
class ColorbarCreateRequest:
    source_component_id: str
    properties: dict[str, Any] | None = None
    object_id: str | None = None
    component_order: int | None = None
    announce: bool = True
    location: str = "right"


@dataclass(frozen=True, slots=True)
class SecondaryAxisElementRequest:
    spec: Any
    axes_id: str | None = None
    object_id: str | None = None
    component_order: int | None = None
    announce: bool = True
    allow_invalid_domain: bool = False


@dataclass(frozen=True, slots=True)
class ReferenceMarksCreateRequest:
    positions: Any
    properties: dict[str, Any] | None = None
    object_id: str | None = None
    component_order: int | None = None
    announce: bool = True
    position_ref: Any = None
    placement: Any = None


@dataclass(frozen=True, slots=True)
class ReferenceGuideCreateRequest:
    role: Any
    properties: dict[str, Any] | None = None
    object_id: str | None = None
    component_order: int | None = None
    announce: bool = True


@dataclass(frozen=True, slots=True)
class TextCreateRequest:
    x: float
    y: float
    text: str
    fontfamily: str
    fontsize: float
    usetex: bool | None = None
    object_id: str | None = None
    color: Any = None
    fontweight: Any = None
    fontstyle: Any = None
    scope: str = "axes"
