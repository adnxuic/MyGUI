"""Stable dotted keys and page ids for persisted application settings."""

from __future__ import annotations

PAGE_APPEARANCE = "appearance"
PAGE_WORKSPACE = "workspace"
PAGE_NEW_FIGURE = "new_figure"
PAGE_COMPONENTS = "components"
PAGE_AXES_COMPONENTS = "axes_components"
PAGE_EXPORT = "export"
PAGE_INTEGRATIONS = "integrations"
PAGE_MAINTENANCE = "maintenance"

APPEARANCE_THEME_MODE = "appearance.theme_mode"
APPEARANCE_UI_FONT_POINT_SIZE = "appearance.ui_font_point_size"
APPEARANCE_DENSITY = "appearance.density"

WORKSPACE_REMEMBER_LAYOUT = "workspace.remember_layout"
WORKSPACE_LAYOUT = "workspace.layout"

NEW_FIGURE_WIDTH_IN = "new_figure.width_in"
NEW_FIGURE_HEIGHT_IN = "new_figure.height_in"
NEW_FIGURE_DOCUMENT_DPI = "new_figure.document_dpi"

COMPONENTS_LINE_COLOR = "components.line.color"
COMPONENTS_LINE_LINESTYLE = "components.line.linestyle"
COMPONENTS_LINE_LINEWIDTH = "components.line.linewidth"
COMPONENTS_LINE_MARKER = "components.line.marker"
COMPONENTS_LINE_MARKERSIZE = "components.line.markersize"
COMPONENTS_LINE_MARKEREDGEWIDTH = "components.line.markeredgewidth"
COMPONENTS_SCATTER_COLOR = "components.scatter.color"
COMPONENTS_SCATTER_MARKER = "components.scatter.marker"
COMPONENTS_SCATTER_SIZE = "components.scatter.size"
COMPONENTS_SCATTER_LINEWIDTH = "components.scatter.linewidth"
COMPONENTS_TEXT_FONTFAMILY = "components.text.fontfamily"
COMPONENTS_TEXT_FONTSIZE = "components.text.fontsize"
COMPONENTS_TEXT_COLOR = "components.text.color"
COMPONENTS_TEXT_FONTWEIGHT = "components.text.fontweight"
COMPONENTS_TEXT_FONTSTYLE = "components.text.fontstyle"

EXPORT_FORMAT = "export.format"
EXPORT_LAST_DIRECTORY = "export.last_directory"
EXPORT_USE_PROJECT_DPI = "export.use_project_dpi"
EXPORT_CUSTOM_DPI = "export.custom_dpi"
EXPORT_TRANSPARENT = "export.transparent"
EXPORT_FACECOLOR = "export.facecolor"
EXPORT_EDGECOLOR = "export.edgecolor"
EXPORT_BBOX_INCHES = "export.bbox_inches"
EXPORT_PAD_INCHES = "export.pad_inches"
EXPORT_PNG_COMPRESS_LEVEL = "export.png_compress_level"
EXPORT_PNG_OPTIMIZE = "export.png_optimize"
EXPORT_JPEG_QUALITY = "export.jpeg_quality"
EXPORT_JPEG_OPTIMIZE = "export.jpeg_optimize"
EXPORT_JPEG_PROGRESSIVE = "export.jpeg_progressive"
EXPORT_JPEG_SUBSAMPLING = "export.jpeg_subsampling"
EXPORT_TIFF_COMPRESSION = "export.tiff_compression"
EXPORT_WEBP_LOSSLESS = "export.webp_lossless"
EXPORT_WEBP_QUALITY = "export.webp_quality"
EXPORT_WEBP_ALPHA_QUALITY = "export.webp_alpha_quality"
EXPORT_WEBP_METHOD = "export.webp_method"
EXPORT_WEBP_EXACT = "export.webp_exact"
EXPORT_METADATA = "export.metadata"

PAGE_IDS = (
    PAGE_APPEARANCE,
    PAGE_WORKSPACE,
    PAGE_NEW_FIGURE,
    PAGE_COMPONENTS,
    PAGE_AXES_COMPONENTS,
    PAGE_EXPORT,
)

GENERAL_COMPONENT_KEYS = (
    COMPONENTS_LINE_COLOR,
    COMPONENTS_LINE_LINESTYLE,
    COMPONENTS_LINE_LINEWIDTH,
    COMPONENTS_LINE_MARKER,
    COMPONENTS_LINE_MARKERSIZE,
    COMPONENTS_LINE_MARKEREDGEWIDTH,
    COMPONENTS_SCATTER_COLOR,
    COMPONENTS_SCATTER_MARKER,
    COMPONENTS_SCATTER_SIZE,
    COMPONENTS_SCATTER_LINEWIDTH,
    COMPONENTS_TEXT_FONTFAMILY,
    COMPONENTS_TEXT_FONTSIZE,
    COMPONENTS_TEXT_COLOR,
    COMPONENTS_TEXT_FONTWEIGHT,
    COMPONENTS_TEXT_FONTSTYLE,
)

AXES_SPINE_SIDES = ("left", "right", "top", "bottom")
AXES_SPINE_FIELDS = ("visible", "color", "linewidth", "linestyle")
AXES_AXIS_NAMES = ("x", "y")
AXES_LEVELS = ("major", "minor")
AXES_TICK_FIELDS = (
    "primary_visible",
    "secondary_visible",
    "direction",
    "length",
    "width",
    "color",
)
AXES_TICK_LABEL_FIELDS = (
    "primary_visible",
    "secondary_visible",
    "color",
    "fontfamily",
    "fontsize",
    "fontweight",
    "fontstyle",
    "rotation",
    "pad",
)
AXES_GRID_FIELDS = ("visible", "color", "linestyle", "linewidth", "alpha")

COMPONENTS_AXES_FACECOLOR = "components.axes.facecolor"
COMPONENTS_AXES_FRAMEON = "components.axes.frameon"
COMPONENTS_AXES_AXISBELOW = "components.axes.axisbelow"


def _axes_component_keys() -> tuple[str, ...]:
    keys = [
        COMPONENTS_AXES_FACECOLOR,
        COMPONENTS_AXES_FRAMEON,
        COMPONENTS_AXES_AXISBELOW,
    ]
    for side in AXES_SPINE_SIDES:
        for field in AXES_SPINE_FIELDS:
            keys.append(f"components.axes.spines.{side}.{field}")
    for axis in AXES_AXIS_NAMES:
        for level in AXES_LEVELS:
            for field in AXES_TICK_FIELDS:
                keys.append(f"components.axes.{axis}.{level}.ticks.{field}")
            for field in AXES_TICK_LABEL_FIELDS:
                keys.append(f"components.axes.{axis}.{level}.tick_labels.{field}")
            for field in AXES_GRID_FIELDS:
                keys.append(f"components.axes.{axis}.{level}.grid.{field}")
    return tuple(keys)


AXES_COMPONENT_KEYS = _axes_component_keys()
if len(AXES_COMPONENT_KEYS) != 99:
    raise RuntimeError(
        f"AXES_COMPONENT_KEYS must contain 99 fields; got {len(AXES_COMPONENT_KEYS)}."
    )

COMPONENT_KEYS = (*GENERAL_COMPONENT_KEYS, *AXES_COMPONENT_KEYS)

PERSISTENT_KEYS = (
    APPEARANCE_THEME_MODE,
    APPEARANCE_UI_FONT_POINT_SIZE,
    APPEARANCE_DENSITY,
    WORKSPACE_REMEMBER_LAYOUT,
    WORKSPACE_LAYOUT,
    NEW_FIGURE_WIDTH_IN,
    NEW_FIGURE_HEIGHT_IN,
    NEW_FIGURE_DOCUMENT_DPI,
    *COMPONENT_KEYS,
    EXPORT_FORMAT,
    EXPORT_LAST_DIRECTORY,
    EXPORT_USE_PROJECT_DPI,
    EXPORT_CUSTOM_DPI,
    EXPORT_TRANSPARENT,
    EXPORT_FACECOLOR,
    EXPORT_EDGECOLOR,
    EXPORT_BBOX_INCHES,
    EXPORT_PAD_INCHES,
    EXPORT_PNG_COMPRESS_LEVEL,
    EXPORT_PNG_OPTIMIZE,
    EXPORT_JPEG_QUALITY,
    EXPORT_JPEG_OPTIMIZE,
    EXPORT_JPEG_PROGRESSIVE,
    EXPORT_JPEG_SUBSAMPLING,
    EXPORT_TIFF_COMPRESSION,
    EXPORT_WEBP_LOSSLESS,
    EXPORT_WEBP_QUALITY,
    EXPORT_WEBP_ALPHA_QUALITY,
    EXPORT_WEBP_METHOD,
    EXPORT_WEBP_EXACT,
    EXPORT_METADATA,
)

KEYS_BY_PAGE = {
    PAGE_APPEARANCE: (
        APPEARANCE_THEME_MODE,
        APPEARANCE_UI_FONT_POINT_SIZE,
        APPEARANCE_DENSITY,
    ),
    PAGE_WORKSPACE: (
        WORKSPACE_REMEMBER_LAYOUT,
        WORKSPACE_LAYOUT,
    ),
    PAGE_NEW_FIGURE: (
        NEW_FIGURE_WIDTH_IN,
        NEW_FIGURE_HEIGHT_IN,
        NEW_FIGURE_DOCUMENT_DPI,
    ),
    PAGE_COMPONENTS: GENERAL_COMPONENT_KEYS,
    PAGE_AXES_COMPONENTS: AXES_COMPONENT_KEYS,
    PAGE_EXPORT: (
        EXPORT_FORMAT,
        EXPORT_LAST_DIRECTORY,
        EXPORT_USE_PROJECT_DPI,
        EXPORT_CUSTOM_DPI,
        EXPORT_TRANSPARENT,
        EXPORT_FACECOLOR,
        EXPORT_EDGECOLOR,
        EXPORT_BBOX_INCHES,
        EXPORT_PAD_INCHES,
        EXPORT_PNG_COMPRESS_LEVEL,
        EXPORT_PNG_OPTIMIZE,
        EXPORT_JPEG_QUALITY,
        EXPORT_JPEG_OPTIMIZE,
        EXPORT_JPEG_PROGRESSIVE,
        EXPORT_JPEG_SUBSAMPLING,
        EXPORT_TIFF_COMPRESSION,
        EXPORT_WEBP_LOSSLESS,
        EXPORT_WEBP_QUALITY,
        EXPORT_WEBP_ALPHA_QUALITY,
        EXPORT_WEBP_METHOD,
        EXPORT_WEBP_EXACT,
        EXPORT_METADATA,
    ),
}
