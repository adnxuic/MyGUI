"""Immutable application-settings snapshots and commit results.

These types are application preferences, not ``ComponentState``. They must not
enter schema v15 project files.
"""

from __future__ import annotations

from dataclasses import dataclass, field
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
