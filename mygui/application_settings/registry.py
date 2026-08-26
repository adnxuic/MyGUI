"""Typed settings registry. New persisted keys must be declared here."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from typing import Any

from .errors import SettingsValidationError
from .keys import (
    APPEARANCE_DENSITY,
    APPEARANCE_THEME_MODE,
    APPEARANCE_UI_FONT_POINT_SIZE,
    EXPORT_BBOX_INCHES,
    EXPORT_CUSTOM_DPI,
    EXPORT_EDGECOLOR,
    EXPORT_FACECOLOR,
    EXPORT_FORMAT,
    EXPORT_JPEG_OPTIMIZE,
    EXPORT_JPEG_PROGRESSIVE,
    EXPORT_JPEG_QUALITY,
    EXPORT_JPEG_SUBSAMPLING,
    EXPORT_LAST_DIRECTORY,
    EXPORT_METADATA,
    EXPORT_PAD_INCHES,
    EXPORT_PNG_COMPRESS_LEVEL,
    EXPORT_PNG_OPTIMIZE,
    EXPORT_TIFF_COMPRESSION,
    EXPORT_TRANSPARENT,
    EXPORT_USE_PROJECT_DPI,
    EXPORT_WEBP_ALPHA_QUALITY,
    EXPORT_WEBP_EXACT,
    EXPORT_WEBP_LOSSLESS,
    EXPORT_WEBP_METHOD,
    EXPORT_WEBP_QUALITY,
    KEYS_BY_PAGE,
    NEW_FIGURE_DOCUMENT_DPI,
    NEW_FIGURE_HEIGHT_IN,
    NEW_FIGURE_WIDTH_IN,
    PAGE_APPEARANCE,
    PAGE_EXPORT,
    PAGE_IDS,
    PAGE_NEW_FIGURE,
    PAGE_WORKSPACE,
    PERSISTENT_KEYS,
    WORKSPACE_LAYOUT,
    WORKSPACE_REMEMBER_LAYOUT,
)
from .models import (
    DEFAULT_WORKSPACE_LAYOUT,
    Density,
    ExportBBoxInches,
    ExportFormatPreference,
    ExportMetadata,
    JpegSubsampling,
    PadInchesValue,
    SettingEditorKind,
    SettingEffect,
    ThemeMode,
    TiffCompression,
    WorkspaceLayoutPayload,
)
from .values import (
    DEFAULT_UI_FONT_PT,
    MAX_DOCUMENT_DPI,
    MAX_FIGURE_INCHES,
    MAX_UI_FONT_PT,
    MIN_DOCUMENT_DPI,
    MIN_FIGURE_INCHES,
    MIN_UI_FONT_PT,
    always_true,
    export_metadata_to_wire,
    normalize_bbox_inches,
    normalize_bool,
    normalize_density,
    normalize_directory,
    normalize_document_dpi,
    normalize_export_color,
    normalize_export_format,
    normalize_export_metadata,
    normalize_figure_inches,
    normalize_jpeg_quality,
    normalize_jpeg_subsampling,
    normalize_pad_inches,
    normalize_png_compress_level,
    normalize_theme_mode,
    normalize_tiff_compression,
    normalize_ui_font_point_size,
    normalize_webp_method,
    normalize_webp_quality,
    normalize_workspace_layout,
    pad_inches_to_wire,
    validate_bbox_inches,
    validate_density,
    validate_directory,
    validate_document_dpi,
    validate_export_color,
    validate_export_format,
    validate_export_metadata,
    validate_figure_inches,
    validate_jpeg_quality,
    validate_jpeg_subsampling,
    validate_pad_inches,
    validate_png_compress_level,
    validate_theme_mode,
    validate_tiff_compression,
    validate_ui_font_point_size,
    validate_webp_method,
    validate_webp_quality,
    validate_workspace_layout,
    workspace_layout_to_wire,
)

Normalizer = Callable[[Any], Any]
Validator = Callable[[Any], bool]


@dataclass(frozen=True, slots=True)
class SettingSpec:
    """Description of one application setting. Persistent keys are closed."""

    key: str
    value_type: type | tuple[type, ...]
    default: Any
    page_id: str
    effect: SettingEffect
    editor: SettingEditorKind
    normalizer: Normalizer
    validator: Validator
    migration: str
    persistent: bool = True
    choices: tuple[Any, ...] | None = None
    minimum: float | int | None = None
    maximum: float | int | None = None
    label: str | None = None
    tooltip: str | None = None
    allow_none: bool = False
    to_wire: Callable[[Any], Any] | None = None
    include_in_page_restore: bool = True
    include_in_reset_all: bool = True

    def __post_init__(self) -> None:
        if not self.key or not isinstance(self.key, str):
            raise SettingsValidationError("SettingSpec key must be a non-empty string.")
        if self.editor is SettingEditorKind.ACTION and self.persistent:
            raise SettingsValidationError(
                f"Setting {self.key!r} cannot be a persistent JSON or action field."
            )
        if self.persistent:
            if self.normalizer is None or self.validator is None:
                raise SettingsValidationError(
                    f"Setting {self.key!r} must declare a normalizer and validator."
                )
            if not self.migration:
                raise SettingsValidationError(
                    f"Setting {self.key!r} must declare a migration contract."
                )
        if self.choices is not None:
            object.__setattr__(self, "choices", tuple(self.choices))
        if not isinstance(self.effect, SettingEffect):
            object.__setattr__(self, "effect", SettingEffect(self.effect))
        if not isinstance(self.editor, SettingEditorKind):
            object.__setattr__(self, "editor", SettingEditorKind(self.editor))

    def normalize(self, value: Any) -> Any:
        """Normalize and validate one value for this specification."""

        if value is None:
            if self.allow_none:
                return None
            raise SettingsValidationError(f"Setting {self.key!r} cannot be null.")
        try:
            normalized = self.normalizer(value)
        except SettingsValidationError:
            raise
        except Exception as exc:
            raise SettingsValidationError(
                f"Setting {self.key!r} is invalid: {exc}"
            ) from exc

        expected = self.value_type
        expected_types = expected if isinstance(expected, tuple) else (expected,)
        if bool not in expected_types and isinstance(normalized, bool):
            raise SettingsValidationError(f"Setting {self.key!r} has the wrong type.")
        if float in expected_types and isinstance(normalized, (int, float)):
            if isinstance(normalized, bool):
                raise SettingsValidationError(
                    f"Setting {self.key!r} has the wrong type."
                )
            normalized = float(normalized)
        elif int in expected_types and isinstance(normalized, int):
            if isinstance(normalized, bool) and bool not in expected_types:
                raise SettingsValidationError(
                    f"Setting {self.key!r} has the wrong type."
                )
            if not isinstance(normalized, bool):
                normalized = int(normalized)
        if not isinstance(normalized, expected_types):
            expected_names = ", ".join(item.__name__ for item in expected_types)
            raise SettingsValidationError(
                f"Setting {self.key!r} must be {expected_names}; "
                f"got {type(normalized).__name__}."
            )
        if self.choices is not None and normalized not in self.choices:
            raise SettingsValidationError(
                f"Setting {self.key!r} must be one of {self.choices!r}."
            )
        if (
            self.minimum is not None
            and isinstance(normalized, (int, float))
            and not isinstance(normalized, bool)
            and normalized < self.minimum
        ):
            raise SettingsValidationError(
                f"Setting {self.key!r} must be at least {self.minimum}."
            )
        if (
            self.maximum is not None
            and isinstance(normalized, (int, float))
            and not isinstance(normalized, bool)
            and normalized > self.maximum
        ):
            raise SettingsValidationError(
                f"Setting {self.key!r} must be at most {self.maximum}."
            )
        try:
            valid = self.validator(normalized)
        except SettingsValidationError:
            raise
        except Exception as exc:
            raise SettingsValidationError(
                f"Setting {self.key!r} is invalid: {exc}"
            ) from exc
        if valid is False:
            raise SettingsValidationError(
                f"Setting {self.key!r} failed validation."
            )
        return normalized

    def wire_value(self, value: Any) -> Any:
        """Return a JSON-safe payload fragment for this setting."""

        if self.to_wire is not None:
            return self.to_wire(value)
        if hasattr(value, "value") and not isinstance(value, (str, bytes)):
            return value.value
        return value


@dataclass(frozen=True, slots=True)
class SettingsPageSpec:
    """One settings page and the keys it owns."""

    page_id: str
    title: str
    setting_keys: tuple[str, ...]


def _enum_wire(value: Any) -> str:
    return value.value if hasattr(value, "value") else str(value)


def _spec(
    key: str,
    value_type: type | tuple[type, ...],
    default: Any,
    *,
    page_id: str,
    effect: SettingEffect,
    editor: SettingEditorKind,
    normalizer: Normalizer,
    validator: Validator,
    migration: str,
    choices: tuple[Any, ...] | None = None,
    minimum: float | int | None = None,
    maximum: float | int | None = None,
    label: str | None = None,
    to_wire: Callable[[Any], Any] | None = None,
    include_in_page_restore: bool = True,
    include_in_reset_all: bool = True,
) -> SettingSpec:
    return SettingSpec(
        key=key,
        value_type=value_type,
        default=default,
        page_id=page_id,
        effect=effect,
        editor=editor,
        normalizer=normalizer,
        validator=validator,
        migration=migration,
        choices=choices,
        minimum=minimum,
        maximum=maximum,
        label=label,
        to_wire=to_wire,
        include_in_page_restore=include_in_page_restore,
        include_in_reset_all=include_in_reset_all,
    )


def _production_specs() -> tuple[SettingSpec, ...]:
    appearance_live = SettingEffect.LIVE_REVERSIBLE
    next_use = SettingEffect.NEXT_USE
    return (
        _spec(
            APPEARANCE_THEME_MODE,
            ThemeMode,
            ThemeMode.SYSTEM,
            page_id=PAGE_APPEARANCE,
            effect=appearance_live,
            editor=SettingEditorKind.ENUM,
            normalizer=normalize_theme_mode,
            validator=validate_theme_mode,
            migration="identity; legacy Light is storage-owned",
            choices=tuple(ThemeMode),
            label="Theme",
            to_wire=_enum_wire,
        ),
        _spec(
            APPEARANCE_UI_FONT_POINT_SIZE,
            int,
            DEFAULT_UI_FONT_PT,
            page_id=PAGE_APPEARANCE,
            effect=appearance_live,
            editor=SettingEditorKind.INT,
            normalizer=normalize_ui_font_point_size,
            validator=validate_ui_font_point_size,
            migration="identity",
            minimum=MIN_UI_FONT_PT,
            maximum=MAX_UI_FONT_PT,
            label="UI font size",
        ),
        _spec(
            APPEARANCE_DENSITY,
            Density,
            Density.STANDARD,
            page_id=PAGE_APPEARANCE,
            effect=appearance_live,
            editor=SettingEditorKind.ENUM,
            normalizer=normalize_density,
            validator=validate_density,
            migration="identity",
            choices=tuple(Density),
            label="Density",
            to_wire=_enum_wire,
        ),
        _spec(
            WORKSPACE_REMEMBER_LAYOUT,
            bool,
            True,
            page_id=PAGE_WORKSPACE,
            effect=next_use,
            editor=SettingEditorKind.BOOL,
            normalizer=normalize_bool,
            validator=always_true,
            migration="identity",
            label="Remember workspace layout",
        ),
        _spec(
            WORKSPACE_LAYOUT,
            WorkspaceLayoutPayload,
            DEFAULT_WORKSPACE_LAYOUT,
            page_id=PAGE_WORKSPACE,
            effect=next_use,
            editor=SettingEditorKind.WORKSPACE_LAYOUT,
            normalizer=normalize_workspace_layout,
            validator=validate_workspace_layout,
            migration="workspace_layout_v1_v2; storage migrates tableVisible",
            label="Workspace layout",
            to_wire=workspace_layout_to_wire,
            include_in_page_restore=False,
            include_in_reset_all=False,
        ),
        _spec(
            NEW_FIGURE_WIDTH_IN,
            float,
            6.4,
            page_id=PAGE_NEW_FIGURE,
            effect=next_use,
            editor=SettingEditorKind.NUMBER,
            normalizer=normalize_figure_inches,
            validator=validate_figure_inches,
            migration="identity",
            minimum=MIN_FIGURE_INCHES,
            maximum=MAX_FIGURE_INCHES,
            label="Default Figure width (in)",
        ),
        _spec(
            NEW_FIGURE_HEIGHT_IN,
            float,
            4.8,
            page_id=PAGE_NEW_FIGURE,
            effect=next_use,
            editor=SettingEditorKind.NUMBER,
            normalizer=normalize_figure_inches,
            validator=validate_figure_inches,
            migration="identity",
            minimum=MIN_FIGURE_INCHES,
            maximum=MAX_FIGURE_INCHES,
            label="Default Figure height (in)",
        ),
        _spec(
            NEW_FIGURE_DOCUMENT_DPI,
            float,
            100.0,
            page_id=PAGE_NEW_FIGURE,
            effect=next_use,
            editor=SettingEditorKind.NUMBER,
            normalizer=normalize_document_dpi,
            validator=validate_document_dpi,
            migration="identity",
            minimum=MIN_DOCUMENT_DPI,
            maximum=MAX_DOCUMENT_DPI,
            label="Default document DPI",
        ),
        _spec(
            EXPORT_FORMAT,
            ExportFormatPreference,
            ExportFormatPreference.PNG,
            page_id=PAGE_EXPORT,
            effect=next_use,
            editor=SettingEditorKind.ENUM,
            normalizer=normalize_export_format,
            validator=validate_export_format,
            migration="figureExport/v1",
            choices=tuple(ExportFormatPreference),
            label="Format",
            to_wire=_enum_wire,
        ),
        _spec(
            EXPORT_LAST_DIRECTORY,
            str,
            "",
            page_id=PAGE_EXPORT,
            effect=next_use,
            editor=SettingEditorKind.DIRECTORY,
            normalizer=normalize_directory,
            validator=validate_directory,
            migration="figureExport/v1 lastDirectory",
            label="Last directory",
        ),
        _spec(
            EXPORT_USE_PROJECT_DPI,
            bool,
            True,
            page_id=PAGE_EXPORT,
            effect=next_use,
            editor=SettingEditorKind.BOOL,
            normalizer=normalize_bool,
            validator=always_true,
            migration="figureExport/v1 useProjectDpi strategy only",
            label="Use project DPI",
        ),
        _spec(
            EXPORT_CUSTOM_DPI,
            float,
            100.0,
            page_id=PAGE_EXPORT,
            effect=next_use,
            editor=SettingEditorKind.NUMBER,
            normalizer=normalize_document_dpi,
            validator=validate_document_dpi,
            migration="figureExport/v1 dpi independent of strategy",
            minimum=MIN_DOCUMENT_DPI,
            maximum=MAX_DOCUMENT_DPI,
            label="Custom DPI",
        ),
        _spec(
            EXPORT_TRANSPARENT,
            bool,
            False,
            page_id=PAGE_EXPORT,
            effect=next_use,
            editor=SettingEditorKind.BOOL,
            normalizer=normalize_bool,
            validator=always_true,
            migration="figureExport/v1",
            label="Transparent background",
        ),
        _spec(
            EXPORT_FACECOLOR,
            str,
            "auto",
            page_id=PAGE_EXPORT,
            effect=next_use,
            editor=SettingEditorKind.COLOR,
            normalizer=normalize_export_color,
            validator=validate_export_color,
            migration="figureExport/v1",
            label="Background color",
        ),
        _spec(
            EXPORT_EDGECOLOR,
            str,
            "auto",
            page_id=PAGE_EXPORT,
            effect=next_use,
            editor=SettingEditorKind.COLOR,
            normalizer=normalize_export_color,
            validator=validate_export_color,
            migration="figureExport/v1",
            label="Border color",
        ),
        _spec(
            EXPORT_BBOX_INCHES,
            ExportBBoxInches,
            ExportBBoxInches.FIGURE,
            page_id=PAGE_EXPORT,
            effect=next_use,
            editor=SettingEditorKind.ENUM,
            normalizer=normalize_bbox_inches,
            validator=validate_bbox_inches,
            migration="figureExport/v1 bboxInches",
            choices=tuple(ExportBBoxInches),
            label="Figure bounds",
            to_wire=_enum_wire,
        ),
        _spec(
            EXPORT_PAD_INCHES,
            PadInchesValue,
            PadInchesValue(),
            page_id=PAGE_EXPORT,
            effect=next_use,
            editor=SettingEditorKind.PAD_INCHES,
            normalizer=normalize_pad_inches,
            validator=validate_pad_inches,
            migration="figureExport/v1 padInches tagged",
            label="Padding",
            to_wire=pad_inches_to_wire,
        ),
        _spec(
            EXPORT_PNG_COMPRESS_LEVEL,
            int,
            6,
            page_id=PAGE_EXPORT,
            effect=next_use,
            editor=SettingEditorKind.INT,
            normalizer=normalize_png_compress_level,
            validator=validate_png_compress_level,
            migration="figureExport/v1",
            minimum=0,
            maximum=9,
            label="PNG compression level",
        ),
        _spec(
            EXPORT_PNG_OPTIMIZE,
            bool,
            False,
            page_id=PAGE_EXPORT,
            effect=next_use,
            editor=SettingEditorKind.BOOL,
            normalizer=normalize_bool,
            validator=always_true,
            migration="figureExport/v1",
            label="PNG Optimize",
        ),
        _spec(
            EXPORT_JPEG_QUALITY,
            int,
            75,
            page_id=PAGE_EXPORT,
            effect=next_use,
            editor=SettingEditorKind.INT,
            normalizer=normalize_jpeg_quality,
            validator=validate_jpeg_quality,
            migration="figureExport/v1",
            minimum=0,
            maximum=95,
            label="JPEG quality",
        ),
        _spec(
            EXPORT_JPEG_OPTIMIZE,
            bool,
            False,
            page_id=PAGE_EXPORT,
            effect=next_use,
            editor=SettingEditorKind.BOOL,
            normalizer=normalize_bool,
            validator=always_true,
            migration="figureExport/v1",
            label="JPEG Optimize",
        ),
        _spec(
            EXPORT_JPEG_PROGRESSIVE,
            bool,
            False,
            page_id=PAGE_EXPORT,
            effect=next_use,
            editor=SettingEditorKind.BOOL,
            normalizer=normalize_bool,
            validator=always_true,
            migration="figureExport/v1",
            label="JPEG Progressive",
        ),
        _spec(
            EXPORT_JPEG_SUBSAMPLING,
            JpegSubsampling,
            JpegSubsampling.AUTO,
            page_id=PAGE_EXPORT,
            effect=next_use,
            editor=SettingEditorKind.ENUM,
            normalizer=normalize_jpeg_subsampling,
            validator=validate_jpeg_subsampling,
            migration="figureExport/v1",
            choices=tuple(JpegSubsampling),
            label="JPEG chroma",
            to_wire=_enum_wire,
        ),
        _spec(
            EXPORT_TIFF_COMPRESSION,
            TiffCompression,
            TiffCompression.NONE,
            page_id=PAGE_EXPORT,
            effect=next_use,
            editor=SettingEditorKind.ENUM,
            normalizer=normalize_tiff_compression,
            validator=validate_tiff_compression,
            migration="figureExport/v1",
            choices=tuple(TiffCompression),
            label="TIFF compression",
            to_wire=_enum_wire,
        ),
        _spec(
            EXPORT_WEBP_LOSSLESS,
            bool,
            False,
            page_id=PAGE_EXPORT,
            effect=next_use,
            editor=SettingEditorKind.BOOL,
            normalizer=normalize_bool,
            validator=always_true,
            migration="figureExport/v1",
            label="WebP lossless",
        ),
        _spec(
            EXPORT_WEBP_QUALITY,
            int,
            80,
            page_id=PAGE_EXPORT,
            effect=next_use,
            editor=SettingEditorKind.INT,
            normalizer=normalize_webp_quality,
            validator=validate_webp_quality,
            migration="figureExport/v1",
            minimum=0,
            maximum=100,
            label="WebP quality",
        ),
        _spec(
            EXPORT_WEBP_ALPHA_QUALITY,
            int,
            100,
            page_id=PAGE_EXPORT,
            effect=next_use,
            editor=SettingEditorKind.INT,
            normalizer=normalize_webp_quality,
            validator=validate_webp_quality,
            migration="figureExport/v1",
            minimum=0,
            maximum=100,
            label="WebP alpha quality",
        ),
        _spec(
            EXPORT_WEBP_METHOD,
            int,
            4,
            page_id=PAGE_EXPORT,
            effect=next_use,
            editor=SettingEditorKind.INT,
            normalizer=normalize_webp_method,
            validator=validate_webp_method,
            migration="figureExport/v1",
            minimum=0,
            maximum=6,
            label="WebP method",
        ),
        _spec(
            EXPORT_WEBP_EXACT,
            bool,
            False,
            page_id=PAGE_EXPORT,
            effect=next_use,
            editor=SettingEditorKind.BOOL,
            normalizer=normalize_bool,
            validator=always_true,
            migration="figureExport/v1",
            label="WebP exact",
        ),
        _spec(
            EXPORT_METADATA,
            ExportMetadata,
            ExportMetadata(),
            page_id=PAGE_EXPORT,
            effect=next_use,
            editor=SettingEditorKind.EXPORT_METADATA,
            normalizer=normalize_export_metadata,
            validator=validate_export_metadata,
            migration="figureExport/v1 metadata/*",
            label="Metadata",
            to_wire=export_metadata_to_wire,
        ),
    )


@dataclass(frozen=True, slots=True)
class SettingsRegistry:
    """Closed catalog of settings pages and persistent specs."""

    pages: tuple[SettingsPageSpec, ...]
    specs: tuple[SettingSpec, ...]
    _by_key: dict[str, SettingSpec] = field(
        default_factory=dict, init=False, repr=False, compare=False
    )

    def __post_init__(self) -> None:
        by_key: dict[str, SettingSpec] = {}
        for spec in self.specs:
            if spec.key in by_key:
                raise SettingsValidationError(
                    f"Duplicate SettingSpec key {spec.key!r}."
                )
            by_key[spec.key] = spec
        object.__setattr__(self, "_by_key", by_key)
        page_ids = [page.page_id for page in self.pages]
        if len(page_ids) != len(set(page_ids)):
            raise SettingsValidationError("Duplicate settings page id.")
        for page in self.pages:
            for key in page.setting_keys:
                spec = by_key.get(key)
                if spec is None:
                    raise SettingsValidationError(
                        f"Page {page.page_id!r} references unknown key {key!r}."
                    )
                if spec.page_id != page.page_id:
                    raise SettingsValidationError(
                        f"Setting {key!r} is registered on page {spec.page_id!r}."
                    )

    def spec(self, key: str) -> SettingSpec:
        try:
            return self._by_key[key]
        except KeyError as exc:
            raise SettingsValidationError(f"Unknown setting {key!r}.") from exc

    def persistent_specs(self) -> tuple[SettingSpec, ...]:
        return tuple(spec for spec in self.specs if spec.persistent)

    def defaults(self) -> dict[str, Any]:
        return {spec.key: spec.default for spec in self.persistent_specs()}

    def defaults_for_page(self, page_id: str) -> dict[str, Any]:
        return {
            spec.key: spec.default
            for spec in self.persistent_specs()
            if spec.page_id == page_id
        }

    def restore_defaults_for_page(self, page_id: str) -> dict[str, Any]:
        """Defaults Restore page defaults may stage. Hidden layout is excluded."""

        return {
            spec.key: spec.default
            for spec in self.persistent_specs()
            if spec.page_id == page_id and spec.include_in_page_restore
        }

    def reset_all_defaults(self) -> dict[str, Any]:
        """Built-in defaults Reset-all may stage. Color library and layout excluded."""

        return {
            spec.key: spec.default
            for spec in self.persistent_specs()
            if spec.include_in_reset_all
        }

    def page(self, page_id: str) -> SettingsPageSpec:
        for page in self.pages:
            if page.page_id == page_id:
                return page
        raise SettingsValidationError(f"Unknown settings page {page_id!r}.")

    def keys(self) -> tuple[str, ...]:
        return tuple(spec.key for spec in self.persistent_specs())


def production_settings_pages() -> tuple[SettingsPageSpec, ...]:
    titles = {
        PAGE_APPEARANCE: "Appearance",
        PAGE_WORKSPACE: "Workspace",
        PAGE_NEW_FIGURE: "New Figure",
        PAGE_EXPORT: "Export",
    }
    return tuple(
        SettingsPageSpec(
            page_id=page_id,
            title=titles[page_id],
            setting_keys=KEYS_BY_PAGE[page_id],
        )
        for page_id in PAGE_IDS
    )


def production_settings_registry() -> SettingsRegistry:
    """Return the frozen production catalog for the four persisted pages."""

    registry = SettingsRegistry(
        pages=production_settings_pages(),
        specs=_production_specs(),
    )
    declared = tuple(spec.key for spec in registry.persistent_specs())
    if declared != PERSISTENT_KEYS:
        missing = set(PERSISTENT_KEYS) - set(declared)
        extra = set(declared) - set(PERSISTENT_KEYS)
        raise SettingsValidationError(
            f"Production settings keys mismatch. missing={sorted(missing)} "
            f"extra={sorted(extra)}"
        )
    return registry


def iter_live_keys(registry: SettingsRegistry, keys: Iterable[str]) -> frozenset[str]:
    return frozenset(
        key
        for key in keys
        if registry.spec(key).effect is SettingEffect.LIVE_REVERSIBLE
    )
