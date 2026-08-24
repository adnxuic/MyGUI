"""Pure-data Figure export model, validation, and application preferences."""

from __future__ import annotations

import logging
import os
import re
import tempfile
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field, replace
from enum import StrEnum
from pathlib import Path
from typing import Any

from PySide6.QtCore import QSettings


LOGGER = logging.getLogger(__name__)

SETTINGS_GROUP = "figureExport"
SETTINGS_VERSION = 1
INCH_TO_CM = 2.54
MIN_DPI = 1.0
MAX_DPI = 10_000.0
DEFAULT_PAD_INCHES = 0.1
PNG_METADATA_KEYS = (
    "Title",
    "Author",
    "Description",
    "Copyright",
    "Software",
    "Comment",
)
PDF_METADATA_KEYS = ("Title", "Author", "Subject", "Keywords", "Creator")
SVG_METADATA_KEYS = ("Title", "Creator", "Description", "Keywords", "Rights")
JPEG_SUBSAMPLING_CHOICES = ("auto", "4:4:4", "4:2:2", "4:2:0")
TIFF_COMPRESSION_CHOICES = ("none", "packbits", "lzw", "adobe_deflate")
_HEX_COLOR = re.compile(
    r"^#(?:[0-9A-Fa-f]{3}|[0-9A-Fa-f]{4}|[0-9A-Fa-f]{6}|[0-9A-Fa-f]{8})$"
)
_UNSAFE_FILENAME = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


class ExportFormat(StrEnum):
    """Closed set of Figure export formats supported by Matplotlib 3.9.0."""

    PNG = "png"
    JPEG = "jpeg"
    TIFF = "tiff"
    WEBP = "webp"
    PDF = "pdf"
    SVG = "svg"

    @property
    def extensions(self) -> tuple[str, ...]:
        """Return the legal lowercase extensions, including aliases."""

        if self is ExportFormat.JPEG:
            return (".jpg", ".jpeg")
        if self is ExportFormat.TIFF:
            return (".tif", ".tiff")
        return (f".{self.value}",)

    @property
    def canonical_extension(self) -> str:
        """Return the generated default extension for this format."""

        return self.extensions[0]

    @property
    def display_name(self) -> str:
        """Return the UI label."""

        return {
            ExportFormat.PNG: "PNG",
            ExportFormat.JPEG: "JPEG",
            ExportFormat.TIFF: "TIFF",
            ExportFormat.WEBP: "WebP",
            ExportFormat.PDF: "PDF",
            ExportFormat.SVG: "SVG",
        }[self]

    @property
    def supports_transparency(self) -> bool:
        """Return whether Matplotlib can write an alpha channel."""

        return self is not ExportFormat.JPEG

    @property
    def supports_metadata(self) -> bool:
        """Return whether Matplotlib 3.9.0 embeds metadata for this format."""

        return self in {ExportFormat.PNG, ExportFormat.PDF, ExportFormat.SVG}

    @property
    def is_raster(self) -> bool:
        """Return whether the format is a raster image."""

        return self in {
            ExportFormat.PNG,
            ExportFormat.JPEG,
            ExportFormat.TIFF,
            ExportFormat.WEBP,
        }

    @property
    def is_vector(self) -> bool:
        """Return whether the format is a vector graphic."""

        return not self.is_raster

    @property
    def metadata_keys(self) -> tuple[str, ...]:
        """Return the keys the export window may send for this format."""

        return {
            ExportFormat.PNG: PNG_METADATA_KEYS,
            ExportFormat.PDF: PDF_METADATA_KEYS,
            ExportFormat.SVG: SVG_METADATA_KEYS,
        }.get(self, ())

    @classmethod
    def from_extension(cls, suffix: str) -> ExportFormat:
        """Resolve a file extension, including JPEG/TIFF aliases."""

        normalized = suffix if suffix.startswith(".") else f".{suffix}"
        normalized = normalized.lower()
        for member in cls:
            if normalized in member.extensions:
                return member
        raise ValueError(f"Unsupported export extension: {suffix}")

    @classmethod
    def from_path(cls, path: str | Path) -> ExportFormat:
        """Resolve the format from a destination path."""

        return cls.from_extension(Path(path).suffix)


@dataclass(frozen=True, slots=True)
class FigureExportContext:
    """Canvas-owned export summary. Presentation code never reads canvas.fig."""

    project_name: str
    document_dpi: float
    width_inches: float
    height_inches: float

    @property
    def width_cm(self) -> float:
        """Return the Figure width in centimetres."""

        return float(self.width_inches) * INCH_TO_CM

    @property
    def height_cm(self) -> float:
        """Return the Figure height in centimetres."""

        return float(self.height_inches) * INCH_TO_CM

    def nominal_pixels(self, dpi: float) -> tuple[int, int]:
        """Return the Figure-bounds pixel size at the requested DPI."""

        return (
            round(float(self.width_inches) * float(dpi)),
            round(float(self.height_inches) * float(dpi)),
        )

    def default_stem(self) -> str:
        """Return a filesystem-safe stem derived from the project name."""

        stem = _UNSAFE_FILENAME.sub("_", str(self.project_name).strip())
        stem = stem.strip(" .")
        return stem or "figure"

    def default_path(self, fmt: ExportFormat, directory: str = "") -> Path:
        """Return the generated destination for one format."""

        name = f"{self.default_stem()}{fmt.canonical_extension}"
        if directory:
            return Path(directory) / name
        return Path(name)


@dataclass(frozen=True, slots=True)
class FigureExportOptions:
    """User-facing savefig options plus per-format encoding and metadata."""

    dpi: float = 100.0
    use_project_dpi: bool = True
    transparent: bool = False
    facecolor: str = "auto"
    edgecolor: str = "auto"
    bbox_inches: str | None = None
    pad_inches: float | str = DEFAULT_PAD_INCHES
    png_compress_level: int = 6
    png_optimize: bool = False
    jpeg_quality: int = 75
    jpeg_optimize: bool = False
    jpeg_progressive: bool = False
    jpeg_subsampling: str = "auto"
    tiff_compression: str = "none"
    webp_lossless: bool = False
    webp_quality: int = 80
    webp_alpha_quality: int = 100
    webp_method: int = 4
    webp_exact: bool = False
    metadata: Mapping[str, str] = field(default_factory=dict)

    @classmethod
    def defaults(cls, *, dpi: float) -> FigureExportOptions:
        """Return backend-compatible defaults at the given DPI."""

        return cls(dpi=float(dpi), use_project_dpi=True)


@dataclass(frozen=True, slots=True)
class FigureExportRequest:
    """Target path plus complete, format-validated export options."""

    path: Path
    format: ExportFormat
    options: FigureExportOptions

    def __post_init__(self) -> None:
        object.__setattr__(self, "path", Path(self.path))
        object.__setattr__(self, "format", ExportFormat(self.format))
        self.validate()

    def validate(self) -> None:
        """Reject paths, ranges, and format capabilities Matplotlib cannot honor."""

        destination = self.path
        if destination.exists() and destination.is_dir():
            raise ValueError("Export path must be a file, not a directory.")
        if not destination.name:
            raise ValueError("Export path must include a file name.")
        suffix = destination.suffix.lower()
        if suffix not in self.format.extensions:
            expected = ", ".join(self.format.extensions)
            raise ValueError(
                f"{self.format.display_name} exports require a "
                f"{expected} filename."
            )
        dpi = float(self.options.dpi)
        if not (dpi == dpi) or dpi < MIN_DPI or dpi > MAX_DPI:
            raise ValueError(
                f"DPI must be a finite value from {MIN_DPI:g} to {MAX_DPI:g}."
            )
        if self.options.transparent and not self.format.supports_transparency:
            raise ValueError("JPEG does not support transparent backgrounds.")
        _validate_color(self.options.facecolor, "Background color")
        _validate_color(self.options.edgecolor, "Border color")
        if self.options.bbox_inches not in (None, "tight"):
            raise ValueError("Cropping must be Figure bounds or Tight contents.")
        pad = self.options.pad_inches
        if pad != "layout":
            try:
                pad_value = float(pad)
            except (TypeError, ValueError) as exc:
                raise ValueError(
                    "Padding must be a finite number of inches or layout."
                ) from exc
            if not (pad_value == pad_value) or pad_value < 0:
                raise ValueError("Padding must be a non-negative number of inches.")
        _validate_int_range(
            self.options.png_compress_level, 0, 9, "PNG compression level"
        )
        _validate_int_range(self.options.jpeg_quality, 0, 95, "JPEG quality")
        if self.options.jpeg_subsampling not in JPEG_SUBSAMPLING_CHOICES:
            raise ValueError("JPEG chroma subsampling is not supported.")
        if self.options.tiff_compression not in TIFF_COMPRESSION_CHOICES:
            raise ValueError("TIFF compression is not supported.")
        _validate_int_range(self.options.webp_quality, 0, 100, "WebP quality")
        _validate_int_range(
            self.options.webp_alpha_quality, 0, 100, "WebP alpha quality"
        )
        _validate_int_range(self.options.webp_method, 0, 6, "WebP method")
        _validate_metadata(self.format, self.options.metadata)

    def filtered_metadata(self) -> dict[str, str]:
        """Return non-empty metadata keys that this format may receive."""

        allowed = set(self.format.metadata_keys)
        result: dict[str, str] = {}
        for key, value in self.options.metadata.items():
            text = str(value).strip()
            if not text or key not in allowed:
                continue
            result[str(key)] = text
        return result

    def pil_kwargs(self) -> dict[str, Any] | None:
        """Return Pillow kwargs for raster formats, otherwise None."""

        fmt = self.format
        if fmt is ExportFormat.PNG:
            if self.options.png_optimize:
                return {"optimize": True}
            return {"compress_level": int(self.options.png_compress_level)}
        if fmt is ExportFormat.JPEG:
            kwargs: dict[str, Any] = {
                "quality": int(self.options.jpeg_quality),
                "optimize": bool(self.options.jpeg_optimize),
                "progressive": bool(self.options.jpeg_progressive),
            }
            if self.options.jpeg_subsampling != "auto":
                kwargs["subsampling"] = {
                    "4:4:4": 0,
                    "4:2:2": 1,
                    "4:2:0": 2,
                }[self.options.jpeg_subsampling]
            return kwargs
        if fmt is ExportFormat.TIFF:
            if self.options.tiff_compression == "none":
                return None
            return {
                "compression": {
                    "packbits": "packbits",
                    "lzw": "tiff_lzw",
                    "adobe_deflate": "tiff_adobe_deflate",
                }[self.options.tiff_compression]
            }
        if fmt is ExportFormat.WEBP:
            return {
                "lossless": bool(self.options.webp_lossless),
                "quality": int(self.options.webp_quality),
                "alpha_quality": int(self.options.webp_alpha_quality),
                "method": int(self.options.webp_method),
                "exact": bool(self.options.webp_exact),
            }
        return None

    def savefig_kwargs(self) -> dict[str, Any]:
        """Return explicit kwargs for Figure.savefig / print_figure."""

        kwargs: dict[str, Any] = {
            "dpi": float(self.options.dpi),
            "format": self.format.value,
            "transparent": bool(self.options.transparent),
            "facecolor": self.options.facecolor,
            "edgecolor": self.options.edgecolor,
            "bbox_inches": (
                "tight" if self.options.bbox_inches == "tight" else False
            ),
        }
        if self.options.bbox_inches == "tight":
            kwargs["pad_inches"] = self.options.pad_inches
        metadata = self.filtered_metadata()
        if metadata:
            kwargs["metadata"] = metadata
        pil_kwargs = self.pil_kwargs()
        if pil_kwargs:
            kwargs["pil_kwargs"] = pil_kwargs
        return kwargs


def compatible_export_request(
    filename: str | Path,
    *,
    dpi: float,
) -> FigureExportRequest:
    """Build the default request used by PyFigureCanvas.save()."""

    path = Path(filename)
    fmt = ExportFormat.from_path(path)
    return FigureExportRequest(
        path=path,
        format=fmt,
        options=FigureExportOptions.defaults(dpi=dpi),
    )


def path_matches_format(path: str | Path, fmt: ExportFormat) -> bool:
    """Return whether the path uses a legal extension for the format."""

    suffix = Path(path).suffix.lower()
    return suffix in fmt.extensions


def extension_error(path: str | Path, fmt: ExportFormat) -> str | None:
    """Return an inline path error, or None when the path is legal."""

    destination = Path(path)
    if not str(path).strip() or not destination.name:
        return "Choose a destination file."
    if destination.suffix.lower() not in fmt.extensions:
        expected = ", ".join(fmt.extensions)
        return f"{fmt.display_name} files must use {expected}."
    return None


def with_format_extension(path: str | Path, fmt: ExportFormat) -> Path:
    """Keep a matching alias, otherwise replace the suffix with the default."""

    destination = Path(path)
    if destination.suffix.lower() in fmt.extensions:
        return destination
    if destination.name in {"", ".", ".."}:
        return Path(f"figure{fmt.canonical_extension}")
    name = destination.name
    if destination.suffix:
        name = destination.stem or destination.name
    return destination.with_name(f"{name}{fmt.canonical_extension}")


def publish_export_file(
    destination: Path,
    writer: Callable[[Path], None],
) -> None:
    """Write beside the destination, then atomically replace it."""

    destination = Path(destination)
    parent = destination.parent if str(destination.parent) else Path(".")
    if not parent.exists():
        raise FileNotFoundError(f"Export directory does not exist: {parent}")
    if not parent.is_dir():
        raise NotADirectoryError(f"Export directory is not a folder: {parent}")
    temp_name: str | None = None
    try:
        handle, temp_name = tempfile.mkstemp(
            prefix=f".{destination.name}.",
            suffix=".tmp",
            dir=str(parent),
        )
        os.close(handle)
        writer(Path(temp_name))
        if not os.path.isfile(temp_name) or os.path.getsize(temp_name) <= 0:
            raise RuntimeError("Export produced an empty file.")
        os.replace(temp_name, os.fspath(destination))
        temp_name = None
    finally:
        if temp_name is not None and os.path.exists(temp_name):
            try:
                os.unlink(temp_name)
            except OSError:
                LOGGER.exception(
                    "Unable to remove temporary export file %s", temp_name
                )


@dataclass(frozen=True, slots=True)
class FigureExportPreferences:
    """Versioned application export preferences. Never stores a full filename."""

    last_directory: str = ""
    format: ExportFormat = ExportFormat.PNG
    options: FigureExportOptions = field(
        default_factory=lambda: FigureExportOptions.defaults(dpi=100.0)
    )

    @classmethod
    def defaults(cls, *, dpi: float = 100.0) -> FigureExportPreferences:
        """Return backend-compatible preferences."""

        return cls(options=FigureExportOptions.defaults(dpi=dpi))


def load_figure_export_preferences(
    settings: QSettings | None,
    *,
    document_dpi: float,
) -> FigureExportPreferences:
    """Load preferences, falling back field-by-field to safe defaults."""

    defaults = FigureExportPreferences.defaults(dpi=document_dpi)
    if settings is None:
        return defaults
    settings.beginGroup(SETTINGS_GROUP)
    try:
        version = _read_int(settings.value("version"), 0)
        if version != SETTINGS_VERSION:
            return defaults
        fmt = _read_format(settings.value("format"), defaults.format)
        last_directory = _read_directory(settings.value("lastDirectory"))
        options = FigureExportOptions(
            dpi=_read_dpi(settings.value("dpi"), document_dpi),
            use_project_dpi=_read_bool(
                settings.value("useProjectDpi"), defaults.options.use_project_dpi
            ),
            transparent=_read_bool(
                settings.value("transparent"), defaults.options.transparent
            ),
            facecolor=_read_color(
                settings.value("facecolor"), defaults.options.facecolor
            ),
            edgecolor=_read_color(
                settings.value("edgecolor"), defaults.options.edgecolor
            ),
            bbox_inches=_read_bbox(settings.value("bboxInches")),
            pad_inches=_read_pad(
                settings.value("padInches"), defaults.options.pad_inches
            ),
            png_compress_level=_read_int_range(
                settings.value("pngCompressLevel"),
                0,
                9,
                defaults.options.png_compress_level,
            ),
            png_optimize=_read_bool(
                settings.value("pngOptimize"), defaults.options.png_optimize
            ),
            jpeg_quality=_read_int_range(
                settings.value("jpegQuality"), 0, 95, defaults.options.jpeg_quality
            ),
            jpeg_optimize=_read_bool(
                settings.value("jpegOptimize"), defaults.options.jpeg_optimize
            ),
            jpeg_progressive=_read_bool(
                settings.value("jpegProgressive"),
                defaults.options.jpeg_progressive,
            ),
            jpeg_subsampling=_read_choice(
                settings.value("jpegSubsampling"),
                JPEG_SUBSAMPLING_CHOICES,
                defaults.options.jpeg_subsampling,
            ),
            tiff_compression=_read_choice(
                settings.value("tiffCompression"),
                TIFF_COMPRESSION_CHOICES,
                defaults.options.tiff_compression,
            ),
            webp_lossless=_read_bool(
                settings.value("webpLossless"), defaults.options.webp_lossless
            ),
            webp_quality=_read_int_range(
                settings.value("webpQuality"), 0, 100, defaults.options.webp_quality
            ),
            webp_alpha_quality=_read_int_range(
                settings.value("webpAlphaQuality"),
                0,
                100,
                defaults.options.webp_alpha_quality,
            ),
            webp_method=_read_int_range(
                settings.value("webpMethod"), 0, 6, defaults.options.webp_method
            ),
            webp_exact=_read_bool(
                settings.value("webpExact"), defaults.options.webp_exact
            ),
            metadata=_read_metadata(settings),
        )
        if not fmt.supports_transparency:
            options = replace(options, transparent=False)
        return FigureExportPreferences(
            last_directory=last_directory,
            format=fmt,
            options=options,
        )
    finally:
        settings.endGroup()


def save_figure_export_preferences(
    settings: QSettings | None,
    preferences: FigureExportPreferences,
) -> None:
    """Persist preferences after a successful export and sync the store."""

    if settings is None:
        return
    options = preferences.options
    settings.beginGroup(SETTINGS_GROUP)
    try:
        settings.setValue("version", SETTINGS_VERSION)
        settings.setValue("lastDirectory", preferences.last_directory)
        settings.setValue("format", preferences.format.value)
        settings.setValue("dpi", float(options.dpi))
        settings.setValue("useProjectDpi", bool(options.use_project_dpi))
        settings.setValue("transparent", bool(options.transparent))
        settings.setValue("facecolor", options.facecolor)
        settings.setValue("edgecolor", options.edgecolor)
        settings.setValue(
            "bboxInches", options.bbox_inches or "figure"
        )
        settings.setValue("padInches", options.pad_inches)
        settings.setValue("pngCompressLevel", int(options.png_compress_level))
        settings.setValue("pngOptimize", bool(options.png_optimize))
        settings.setValue("jpegQuality", int(options.jpeg_quality))
        settings.setValue("jpegOptimize", bool(options.jpeg_optimize))
        settings.setValue("jpegProgressive", bool(options.jpeg_progressive))
        settings.setValue("jpegSubsampling", options.jpeg_subsampling)
        settings.setValue("tiffCompression", options.tiff_compression)
        settings.setValue("webpLossless", bool(options.webp_lossless))
        settings.setValue("webpQuality", int(options.webp_quality))
        settings.setValue("webpAlphaQuality", int(options.webp_alpha_quality))
        settings.setValue("webpMethod", int(options.webp_method))
        settings.setValue("webpExact", bool(options.webp_exact))
        settings.beginGroup("metadata")
        try:
            settings.remove("")
            for key, value in options.metadata.items():
                text = str(value)
                if text.strip():
                    settings.setValue(key, text)
        finally:
            settings.endGroup()
    finally:
        settings.endGroup()
    settings.sync()


def _validate_color(value: str, label: str) -> None:
    if value == "auto":
        return
    if not isinstance(value, str) or not _HEX_COLOR.match(value):
        raise ValueError(f"{label} must be the current Figure color or a hex color.")


def _validate_int_range(value: int, minimum: int, maximum: int, label: str) -> None:
    try:
        number = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} must be an integer.") from exc
    if number != value or number < minimum or number > maximum:
        raise ValueError(f"{label} must be between {minimum} and {maximum}.")


def _validate_metadata(fmt: ExportFormat, metadata: Mapping[str, str]) -> None:
    if not metadata:
        return
    allowed = set(fmt.metadata_keys)
    for key, value in metadata.items():
        if not str(value).strip():
            continue
        if key not in allowed:
            raise ValueError(
                f"{fmt.display_name} does not support metadata key {key}."
            )
        if fmt is ExportFormat.PNG:
            _validate_png_metadata_item(str(key), str(value))


def _validate_png_metadata_item(key: str, value: str) -> None:
    if len(key) >= 79:
        raise ValueError("PNG metadata keys must be shorter than 79 characters.")
    try:
        key.encode("latin-1")
        value.encode("latin-1")
    except UnicodeEncodeError as exc:
        raise ValueError(
            "PNG metadata keys and values must be Latin-1 text."
        ) from exc


def _read_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError, OverflowError):
        return default


def _read_int_range(value: Any, minimum: int, maximum: int, default: int) -> int:
    number = _read_int(value, default)
    if number < minimum or number > maximum:
        return default
    return number


def _read_bool(value: Any, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, int) and value in (0, 1):
        return bool(value)
    if isinstance(value, str):
        normalized = value.strip().casefold()
        if normalized in {"true", "1", "yes"}:
            return True
        if normalized in {"false", "0", "no"}:
            return False
    return default


def _read_dpi(value: Any, default: float) -> float:
    try:
        dpi = float(value)
    except (TypeError, ValueError, OverflowError):
        return float(default)
    if not (dpi == dpi) or dpi < MIN_DPI or dpi > MAX_DPI:
        return float(default)
    return dpi


def _read_format(value: Any, default: ExportFormat) -> ExportFormat:
    try:
        return ExportFormat(str(value).strip().lower())
    except (TypeError, ValueError):
        return default


def _read_directory(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    path = Path(text)
    if path.is_dir():
        return str(path)
    return ""


def _read_color(value: Any, default: str) -> str:
    text = str(value or "").strip()
    if text == "auto" or _HEX_COLOR.match(text):
        return text
    return default


def _read_bbox(value: Any) -> str | None:
    text = str(value or "").strip().casefold()
    if text == "tight":
        return "tight"
    return None


def _read_pad(value: Any, default: float | str) -> float | str:
    if str(value).strip().casefold() == "layout":
        return "layout"
    try:
        pad = float(value)
    except (TypeError, ValueError, OverflowError):
        return default
    if not (pad == pad) or pad < 0:
        return default
    return pad


def _read_choice(value: Any, choices: tuple[str, ...], default: str) -> str:
    text = str(value or "").strip()
    if text in choices:
        return text
    return default


def _read_metadata(settings: QSettings) -> dict[str, str]:
    settings.beginGroup("metadata")
    try:
        result: dict[str, str] = {}
        for key in settings.childKeys():
            text = str(settings.value(key, "") or "")
            if text.strip():
                result[str(key)] = text
        return result
    finally:
        settings.endGroup()
