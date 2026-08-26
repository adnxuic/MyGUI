"""Immutable application-settings snapshots and commit results.

These types are application preferences, not ``ComponentState``. They must not
enter schema v15 project files.
"""

from __future__ import annotations

from dataclasses import dataclass, field, fields
from enum import StrEnum
from types import MappingProxyType
from typing import Any, Mapping


class ThemeMode(StrEnum):
    """Closed appearance theme policy. Applied at runtime by ThemeService."""

    SYSTEM = "system"
    LIGHT = "light"
    DARK = "dark"


class Density(StrEnum):
    """Closed UI density policy."""

    COMPACT = "compact"
    STANDARD = "standard"
    COMFORTABLE = "comfortable"


class SettingEffect(StrEnum):
    """Closed set of when a persisted setting takes effect."""

    LIVE_REVERSIBLE = "live_reversible"
    NEXT_USE = "next_use"
    RESTART_REQUIRED = "restart_required"


class SettingEditorKind(StrEnum):
    """Closed editor contracts for settings. Never ``json``."""

    BOOL = "bool"
    INT = "int"
    NUMBER = "number"
    ENUM = "enum"
    TEXT = "text"
    COLOR = "color"
    DIRECTORY = "directory"
    WORKSPACE_LAYOUT = "workspace_layout"
    PAD_INCHES = "pad_inches"
    EXPORT_METADATA = "export_metadata"
    ACTION = "action"
    INHERITABLE_COLOR = "inheritable_color"
    INHERITABLE_ENUM = "inheritable_enum"
    INHERITABLE_NUMBER = "inheritable_number"
    INHERITABLE_TEXT = "inheritable_text"
    INHERITABLE_BOOL = "inheritable_bool"
    INHERITABLE_OPTIONAL_NUMBER = "inheritable_optional_number"


class DefaultValueMode(StrEnum):
    """Whether a Components default inherits or overrides the style/palette."""

    INHERIT = "inherit"
    OVERRIDE = "override"


class InheritSource(StrEnum):
    """Where an inherited Components default is resolved at creation time."""

    FIGURE_STYLE = "figure_style"
    AXES_PALETTE = "axes_palette"
    NONE = "none"


@dataclass(frozen=True, slots=True)
class InheritableValue:
    """One Components default. Inherit still stores the last custom value."""

    mode: DefaultValueMode = DefaultValueMode.INHERIT
    value: Any = None

    def __post_init__(self) -> None:
        mode = self.mode
        if not isinstance(mode, DefaultValueMode):
            object.__setattr__(self, "mode", DefaultValueMode(mode))


class SettingsHealth(StrEnum):
    """Health of the in-memory snapshot versus runtime/storage.

    Storage ``DocumentHealth`` maps onto this set without collapsing
    ``READ_ONLY_FUTURE`` into ``DEGRADED``. Writes are allowed only for
    ``OK`` and ``DEGRADED``.
    """

    OK = "ok"
    DEGRADED = "degraded"
    UNCERTAIN = "uncertain"
    READ_ONLY_FUTURE = "read_only_future"
    RECOVERY_REQUIRED = "recovery_required"


class WorkspaceExplorerMode(StrEnum):
    """v2 Explorer page identity. Matches the existing workbench strings."""

    TABLE = "table"
    COMPONENTS = "components"


class ExportFormatPreference(StrEnum):
    """Closed export formats matching figureExport/v1 wire values."""

    PNG = "png"
    JPEG = "jpeg"
    TIFF = "tiff"
    WEBP = "webp"
    PDF = "pdf"
    SVG = "svg"


class ExportBBoxInches(StrEnum):
    """Cropping policy stored independently of the live Figure."""

    FIGURE = "figure"
    TIGHT = "tight"


class PadInchesKind(StrEnum):
    """Tagged pad-inches policy. Not free-form JSON."""

    NUMERIC = "numeric"
    LAYOUT = "layout"


class JpegSubsampling(StrEnum):
    """Closed JPEG chroma choices from the export window."""

    AUTO = "auto"
    FOUR_FOUR_FOUR = "4:4:4"
    FOUR_TWO_TWO = "4:2:2"
    FOUR_TWO_ZERO = "4:2:0"


class TiffCompression(StrEnum):
    """Closed TIFF compression choices from the export window."""

    NONE = "none"
    PACKBITS = "packbits"
    LZW = "lzw"
    ADOBE_DEFLATE = "adobe_deflate"


@dataclass(frozen=True, slots=True)
class PadInchesValue:
    """Closed tagged pad-inches value for tight cropping."""

    kind: PadInchesKind = PadInchesKind.NUMERIC
    inches: float | None = 0.1

    def to_savefig(self) -> float | str:
        """Return the Matplotlib ``pad_inches`` argument."""

        if self.kind is PadInchesKind.LAYOUT:
            return "layout"
        return float(self.inches if self.inches is not None else 0.1)


@dataclass(frozen=True, slots=True)
class ExportMetadata:
    """Closed tagged metadata map. Empty strings are omitted."""

    fields: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        cleaned = {
            str(key): str(value)
            for key, value in dict(self.fields).items()
            if str(value).strip()
        }
        object.__setattr__(self, "fields", MappingProxyType(cleaned))


@dataclass(frozen=True, slots=True)
class WorkspaceLayoutPayload:
    """Typed workspaceLayout v2 payload. Not editable JSON."""

    version: int = 2
    outer_splitter_sizes: tuple[int, int] = (45, 55)
    inner_splitter_sizes: tuple[int, int] = (420, 240)
    explorer_mode: WorkspaceExplorerMode = WorkspaceExplorerMode.TABLE
    explorer_visible: bool = True


DEFAULT_WORKSPACE_LAYOUT = WorkspaceLayoutPayload()


@dataclass(frozen=True, slots=True)
class AppearanceSettings:
    """Appearance page. Fresh installs are System / 9 pt / Standard."""

    theme_mode: ThemeMode = ThemeMode.SYSTEM
    ui_font_point_size: int = 9
    density: Density = Density.STANDARD


@dataclass(frozen=True, slots=True)
class WorkspaceSettings:
    """Workspace page. Layout restore is opt-out via ``remember_layout``."""

    remember_layout: bool = True
    layout: WorkspaceLayoutPayload = field(
        default_factory=lambda: DEFAULT_WORKSPACE_LAYOUT
    )


@dataclass(frozen=True, slots=True)
class NewFigureSettings:
    """Application defaults for Style creation/import. Not project state."""

    width_in: float = 6.4
    height_in: float = 4.8
    document_dpi: float = 100.0


def _inherit(value: Any) -> InheritableValue:
    return InheritableValue(mode=DefaultValueMode.INHERIT, value=value)


@dataclass(frozen=True, slots=True)
class LineComponentDefaults:
    """NEXT_USE Line appearance for Function Curve, Plot, Fit, Interpolation."""

    color: InheritableValue = field(default_factory=lambda: _inherit("#1F77B4"))
    linestyle: InheritableValue = field(default_factory=lambda: _inherit("-"))
    linewidth: InheritableValue = field(default_factory=lambda: _inherit(1.5))
    marker: InheritableValue = field(default_factory=lambda: _inherit("None"))
    markersize: InheritableValue = field(default_factory=lambda: _inherit(6.0))
    markeredgewidth: InheritableValue = field(
        default_factory=lambda: _inherit(1.0)
    )


@dataclass(frozen=True, slots=True)
class ScatterComponentDefaults:
    """NEXT_USE Scatter appearance for ordinary Scatter creation."""

    color: InheritableValue = field(default_factory=lambda: _inherit("#1F77B4"))
    marker: InheritableValue = field(default_factory=lambda: _inherit("o"))
    size: InheritableValue = field(default_factory=lambda: _inherit(36.0))
    linewidth: InheritableValue = field(default_factory=lambda: _inherit(1.0))


@dataclass(frozen=True, slots=True)
class TextComponentDefaults:
    """NEXT_USE free-Text appearance. Title and axis labels are excluded."""

    fontfamily: InheritableValue = field(
        default_factory=lambda: _inherit("sans-serif")
    )
    fontsize: InheritableValue = field(default_factory=lambda: _inherit(10.0))
    color: InheritableValue = field(default_factory=lambda: _inherit("#000000"))
    fontweight: InheritableValue = field(
        default_factory=lambda: _inherit("normal")
    )
    fontstyle: InheritableValue = field(
        default_factory=lambda: _inherit("normal")
    )


@dataclass(frozen=True, slots=True)
class SpineSideDefaults:
    """NEXT_USE appearance for one Axes spine."""

    visible: InheritableValue = field(default_factory=lambda: _inherit(True))
    color: InheritableValue = field(default_factory=lambda: _inherit("#000000"))
    linewidth: InheritableValue = field(default_factory=lambda: _inherit(0.8))
    linestyle: InheritableValue = field(default_factory=lambda: _inherit("-"))


@dataclass(frozen=True, slots=True)
class AxesSpineDefaults:
    """NEXT_USE appearance for the four standard Axes spines."""

    left: SpineSideDefaults = field(default_factory=SpineSideDefaults)
    right: SpineSideDefaults = field(default_factory=SpineSideDefaults)
    top: SpineSideDefaults = field(default_factory=SpineSideDefaults)
    bottom: SpineSideDefaults = field(default_factory=SpineSideDefaults)


def _tick_defaults(*, major: bool) -> "TickDefaults":
    return TickDefaults(
        primary_visible=_inherit(major),
        secondary_visible=_inherit(False),
        direction=_inherit("out"),
        length=_inherit(3.5 if major else 2.0),
        width=_inherit(0.8 if major else 0.6),
        color=_inherit("#000000"),
    )


def _tick_label_defaults(*, major: bool) -> "TickLabelDefaults":
    return TickLabelDefaults(
        primary_visible=_inherit(major),
        secondary_visible=_inherit(False),
        color=_inherit("#000000"),
        fontfamily=_inherit("sans-serif"),
        fontsize=_inherit(10.0),
        fontweight=_inherit("normal"),
        fontstyle=_inherit("normal"),
        rotation=_inherit(0.0),
        pad=_inherit(3.5 if major else 3.4),
    )


def _grid_defaults() -> "GridDefaults":
    return GridDefaults(
        visible=_inherit(False),
        color=_inherit("#B0B0B0"),
        linestyle=_inherit("-"),
        linewidth=_inherit(0.8),
        alpha=_inherit(None),
    )


@dataclass(frozen=True, slots=True)
class TickDefaults:
    """NEXT_USE Tick group appearance for one axis level."""

    primary_visible: InheritableValue = field(
        default_factory=lambda: _inherit(True)
    )
    secondary_visible: InheritableValue = field(
        default_factory=lambda: _inherit(False)
    )
    direction: InheritableValue = field(default_factory=lambda: _inherit("out"))
    length: InheritableValue = field(default_factory=lambda: _inherit(3.5))
    width: InheritableValue = field(default_factory=lambda: _inherit(0.8))
    color: InheritableValue = field(default_factory=lambda: _inherit("#000000"))


@dataclass(frozen=True, slots=True)
class TickLabelDefaults:
    """NEXT_USE Tick Label appearance for one axis level."""

    primary_visible: InheritableValue = field(
        default_factory=lambda: _inherit(True)
    )
    secondary_visible: InheritableValue = field(
        default_factory=lambda: _inherit(False)
    )
    color: InheritableValue = field(default_factory=lambda: _inherit("#000000"))
    fontfamily: InheritableValue = field(
        default_factory=lambda: _inherit("sans-serif")
    )
    fontsize: InheritableValue = field(default_factory=lambda: _inherit(10.0))
    fontweight: InheritableValue = field(
        default_factory=lambda: _inherit("normal")
    )
    fontstyle: InheritableValue = field(
        default_factory=lambda: _inherit("normal")
    )
    rotation: InheritableValue = field(default_factory=lambda: _inherit(0.0))
    pad: InheritableValue = field(default_factory=lambda: _inherit(3.5))


@dataclass(frozen=True, slots=True)
class GridDefaults:
    """NEXT_USE Grid appearance for one axis level."""

    visible: InheritableValue = field(default_factory=lambda: _inherit(False))
    color: InheritableValue = field(default_factory=lambda: _inherit("#B0B0B0"))
    linestyle: InheritableValue = field(default_factory=lambda: _inherit("-"))
    linewidth: InheritableValue = field(default_factory=lambda: _inherit(0.8))
    alpha: InheritableValue = field(default_factory=lambda: _inherit(None))


@dataclass(frozen=True, slots=True)
class AxisLevelDefaults:
    """Ticks, tick labels, and grid for one major/minor level."""

    ticks: TickDefaults = field(default_factory=TickDefaults)
    tick_labels: TickLabelDefaults = field(default_factory=TickLabelDefaults)
    grid: GridDefaults = field(default_factory=GridDefaults)


def _axis_level_defaults(*, major: bool) -> AxisLevelDefaults:
    return AxisLevelDefaults(
        ticks=_tick_defaults(major=major),
        tick_labels=_tick_label_defaults(major=major),
        grid=_grid_defaults(),
    )


@dataclass(frozen=True, slots=True)
class AxisAppearanceDefaults:
    """NEXT_USE X or Y appearance. Major and minor are independent."""

    major: AxisLevelDefaults = field(
        default_factory=lambda: _axis_level_defaults(major=True)
    )
    minor: AxisLevelDefaults = field(
        default_factory=lambda: _axis_level_defaults(major=False)
    )


@dataclass(frozen=True, slots=True)
class AxesComponentDefaults:
    """Settings → Axes Components. Affects later ordinary Axes creation only."""

    facecolor: InheritableValue = field(
        default_factory=lambda: _inherit("#FFFFFF")
    )
    frameon: InheritableValue = field(default_factory=lambda: _inherit(True))
    axisbelow: InheritableValue = field(
        default_factory=lambda: _inherit("line")
    )
    spines: AxesSpineDefaults = field(default_factory=AxesSpineDefaults)
    x: AxisAppearanceDefaults = field(default_factory=AxisAppearanceDefaults)
    y: AxisAppearanceDefaults = field(default_factory=AxisAppearanceDefaults)


def axes_defaults_to_values(
    axes: AxesComponentDefaults,
) -> dict[str, InheritableValue]:
    """Flatten nested Axes defaults onto dotted ``components.axes.*`` keys."""

    values: dict[str, InheritableValue] = {
        "components.axes.facecolor": axes.facecolor,
        "components.axes.frameon": axes.frameon,
        "components.axes.axisbelow": axes.axisbelow,
    }
    for side in ("left", "right", "top", "bottom"):
        spine = getattr(axes.spines, side)
        for item in fields(SpineSideDefaults):
            values[f"components.axes.spines.{side}.{item.name}"] = getattr(
                spine, item.name
            )
    for axis_name in ("x", "y"):
        axis = getattr(axes, axis_name)
        for level_name in ("major", "minor"):
            level = getattr(axis, level_name)
            for group_name in ("ticks", "tick_labels", "grid"):
                group = getattr(level, group_name)
                prefix = f"components.axes.{axis_name}.{level_name}.{group_name}"
                for item in fields(type(group)):
                    values[f"{prefix}.{item.name}"] = getattr(group, item.name)
    return values


def _group_from_values(cls, prefix: str, values: Mapping[str, Any]):
    return cls(
        **{item.name: values[f"{prefix}.{item.name}"] for item in fields(cls)}
    )


def axes_defaults_from_values(values: Mapping[str, Any]) -> AxesComponentDefaults:
    """Rebuild nested Axes defaults from a complete dotted-key mapping."""

    def axis(name: str) -> AxisAppearanceDefaults:
        return AxisAppearanceDefaults(
            major=AxisLevelDefaults(
                ticks=_group_from_values(
                    TickDefaults, f"components.axes.{name}.major.ticks", values
                ),
                tick_labels=_group_from_values(
                    TickLabelDefaults,
                    f"components.axes.{name}.major.tick_labels",
                    values,
                ),
                grid=_group_from_values(
                    GridDefaults, f"components.axes.{name}.major.grid", values
                ),
            ),
            minor=AxisLevelDefaults(
                ticks=_group_from_values(
                    TickDefaults, f"components.axes.{name}.minor.ticks", values
                ),
                tick_labels=_group_from_values(
                    TickLabelDefaults,
                    f"components.axes.{name}.minor.tick_labels",
                    values,
                ),
                grid=_group_from_values(
                    GridDefaults, f"components.axes.{name}.minor.grid", values
                ),
            ),
        )

    return AxesComponentDefaults(
        facecolor=values["components.axes.facecolor"],
        frameon=values["components.axes.frameon"],
        axisbelow=values["components.axes.axisbelow"],
        spines=AxesSpineDefaults(
            left=_group_from_values(
                SpineSideDefaults, "components.axes.spines.left", values
            ),
            right=_group_from_values(
                SpineSideDefaults, "components.axes.spines.right", values
            ),
            top=_group_from_values(
                SpineSideDefaults, "components.axes.spines.top", values
            ),
            bottom=_group_from_values(
                SpineSideDefaults, "components.axes.spines.bottom", values
            ),
        ),
        x=axis("x"),
        y=axis("y"),
    )


@dataclass(frozen=True, slots=True)
class ComponentDefaultsSettings:
    """Settings → Components and Axes Components. Affects later creation only."""

    line: LineComponentDefaults = field(default_factory=LineComponentDefaults)
    scatter: ScatterComponentDefaults = field(
        default_factory=ScatterComponentDefaults
    )
    text: TextComponentDefaults = field(default_factory=TextComponentDefaults)
    axes: AxesComponentDefaults = field(default_factory=AxesComponentDefaults)


@dataclass(frozen=True, slots=True)
class ExportSettings:
    """figureExport/v1 preferences. ``use_project_dpi`` is a strategy flag."""

    format: ExportFormatPreference = ExportFormatPreference.PNG
    last_directory: str = ""
    use_project_dpi: bool = True
    custom_dpi: float = 100.0
    transparent: bool = False
    facecolor: str = "auto"
    edgecolor: str = "auto"
    bbox_inches: ExportBBoxInches = ExportBBoxInches.FIGURE
    pad_inches: PadInchesValue = field(default_factory=PadInchesValue)
    png_compress_level: int = 6
    png_optimize: bool = False
    jpeg_quality: int = 75
    jpeg_optimize: bool = False
    jpeg_progressive: bool = False
    jpeg_subsampling: JpegSubsampling = JpegSubsampling.AUTO
    tiff_compression: TiffCompression = TiffCompression.NONE
    webp_lossless: bool = False
    webp_quality: int = 80
    webp_alpha_quality: int = 100
    webp_method: int = 4
    webp_exact: bool = False
    metadata: ExportMetadata = field(default_factory=ExportMetadata)


@dataclass(frozen=True, slots=True)
class ApplicationSettingsSnapshot:
    """Immutable settings snapshot consumed by UI and later-phase ports."""

    appearance: AppearanceSettings = field(default_factory=AppearanceSettings)
    workspace: WorkspaceSettings = field(default_factory=WorkspaceSettings)
    new_figure: NewFigureSettings = field(default_factory=NewFigureSettings)
    components: ComponentDefaultsSettings = field(
        default_factory=ComponentDefaultsSettings
    )
    export: ExportSettings = field(default_factory=ExportSettings)
    revision: int = 0


@dataclass(frozen=True, slots=True)
class SettingsCommitResult:
    """Outcome of ``commit_patch``. Failures never emit a success event."""

    success: bool
    snapshot: ApplicationSettingsSnapshot
    error: str | None = None
    warning: str | None = None
    conflicts: tuple[str, ...] = ()
    health: SettingsHealth = SettingsHealth.OK
    recovered: bool = False
    event_emitted: bool = False


@dataclass(frozen=True, slots=True)
class SettingsDraftResult:
    """Outcome of ``reset_section``. Disk is not written."""

    success: bool
    session_revision: int
    dirty: Mapping[str, Any]
    error: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "dirty", MappingProxyType(dict(self.dirty)))
