"""Controller-free inputs for fixed scientific Axes layout templates."""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap, QRegion
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)
from mygui.resources import icon_directory, icon_path as resolve_icon_path

from mygui.figuremodify.axes_layout import (
    AxesCellSpec,
    AxesLayoutSpec,
    AxesViewSpec,
    ShareMode,
)
from mygui.widgets.common_widget.min_widget.py_colorchoice_widgets import (
    ColorChoiceWidget,
)
from mygui.widgets.theme import COLORS


_CONFIG_PATH = Path(__file__).resolve().parent.parent / "available_layout.json"
_ICON_DIRECTORY = icon_directory("layout_images")
_EXPECTED_PRESET_KEYS = (
    "single",
    "horizontal_compare",
    "vertical_stack",
    "grid_2x2",
    "grid_3x3",
    "primary_right_y",
    "main_residual",
)


@dataclass(frozen=True, slots=True)
class AxesLayoutPreset:
    """One validated, UI-only fixed layout template."""

    key: str
    label: str
    toolbar_label: str
    icon: str
    nrows: int
    ncols: int
    width_ratios: tuple[float, ...]
    height_ratios: tuple[float, ...]
    share_x: ShareMode = ShareMode.NONE
    share_y: ShareMode = ShareMode.NONE
    share_toggle: str | None = None
    outer_x_labels: bool = False
    outer_y_labels: bool = False
    right_y: bool = False

    @property
    def icon_path(self) -> str:
        """Return the resolved path used by the Qt resource callers."""

        return resolve_icon_path(f"layout_images/{self.icon}")

    @property
    def cell_count(self) -> int:
        """Return the number of primary Axes created by this template."""

        return self.nrows * self.ncols

    def effective_sharing(self, enabled: bool = True) -> tuple[ShareMode, ShareMode]:
        """Resolve the optional share switch without changing the preset."""

        share_x, share_y = self.share_x, self.share_y
        if not enabled and self.share_toggle == "x":
            share_x = ShareMode.NONE
        elif not enabled and self.share_toggle == "y":
            share_y = ShareMode.NONE
        return share_x, share_y

    def summary(self, *, sharing_enabled: bool = True) -> str:
        """Build the compact relationship summary shown in the dialog."""

        share_x, share_y = self.effective_sharing(sharing_enabled)
        relationships = []
        if self.right_y:
            relationships.append("primary + right Y")
        else:
            if share_x is not ShareMode.NONE:
                relationships.append("shared X")
            if share_y is not ShareMode.NONE:
                relationships.append("shared Y")
        if not relationships:
            relationships.append(
                "single Axes" if self.cell_count == 1 else "independent Axes"
            )
        return f"{self.nrows} × {self.ncols} · {' · '.join(relationships)}"


def _positive_ratios(value, count: int, name: str) -> tuple[float, ...]:
    if value is None:
        return (1.0,) * count
    if not isinstance(value, list) or len(value) != count:
        raise ValueError(f"Layout preset {name} must contain {count} values.")
    ratios = tuple(float(item) for item in value)
    if any(item <= 0 for item in ratios):
        raise ValueError(f"Layout preset {name} values must be positive.")
    return ratios


def normalized_layout_icon(
    icon_path: str,
    *,
    canvas_size: int = 40,
    visual_size: int | None = None,
    tint: str | QColor | None = None,
) -> QIcon:
    """Crop SVG padding, optionally tint it, and center it consistently."""

    canvas_size = max(1, int(canvas_size))
    visual_size = max(1, int(visual_size or round(canvas_size * 0.85)))
    render_size = canvas_size * 4
    source = QIcon(str(icon_path)).pixmap(render_size, render_size)
    if source.isNull():
        return QIcon(str(icon_path))
    bounds = QRegion(source.mask()).boundingRect()
    if not bounds.isValid() or bounds.isEmpty():
        return QIcon(str(icon_path))

    cropped = source.copy(bounds)
    target_extent = visual_size * 4
    scaled = cropped.scaled(
        target_extent,
        target_extent,
        Qt.KeepAspectRatio,
        Qt.SmoothTransformation,
    )
    if tint is not None:
        tint_color = QColor(tint)
        if not tint_color.isValid():
            raise ValueError(f"Invalid layout icon tint: {tint!r}")
        tint_painter = QPainter(scaled)
        tint_painter.setCompositionMode(QPainter.CompositionMode_SourceIn)
        tint_painter.fillRect(scaled.rect(), tint_color)
        tint_painter.end()
    canvas = QPixmap(render_size, render_size)
    canvas.fill(Qt.transparent)
    painter = QPainter(canvas)
    painter.drawPixmap(
        (render_size - scaled.width()) // 2,
        (render_size - scaled.height()) // 2,
        scaled,
    )
    painter.end()
    return QIcon(canvas)


@lru_cache(maxsize=1)
def axes_layout_presets() -> tuple[AxesLayoutPreset, ...]:
    """Load and validate the seven fixed layout templates."""

    with _CONFIG_PATH.open("r", encoding="utf-8") as stream:
        payload = json.load(stream)
    if not isinstance(payload, dict) or tuple(payload) != _EXPECTED_PRESET_KEYS:
        raise ValueError(
            "available_layout.json must define the seven fixed templates in order."
        )

    presets = []
    for key, raw in payload.items():
        if not isinstance(raw, dict):
            raise ValueError(f"Layout preset {key!r} must be an object.")
        label = str(raw.get("label", "")).strip()
        toolbar_label = str(raw.get("toolbar_label", "")).strip()
        icon = str(raw.get("icon", "")).strip()
        if not label:
            raise ValueError(f"Layout preset {key!r} requires a label.")
        if not toolbar_label:
            raise ValueError(f"Layout preset {key!r} requires a toolbar label.")
        if not icon or Path(icon).name != icon or not icon.lower().endswith(".svg"):
            raise ValueError(f"Layout preset {key!r} has an invalid icon name.")
        if not (_ICON_DIRECTORY / icon).is_file():
            raise ValueError(f"Layout preset icon does not exist: {icon}")

        nrows, ncols = int(raw.get("rows", 0)), int(raw.get("columns", 0))
        if not 1 <= nrows <= 6 or not 1 <= ncols <= 6:
            raise ValueError(f"Layout preset {key!r} has invalid dimensions.")
        try:
            share_x = ShareMode(str(raw.get("share_x", ShareMode.NONE.value)))
            share_y = ShareMode(str(raw.get("share_y", ShareMode.NONE.value)))
        except ValueError as exc:
            raise ValueError(f"Layout preset {key!r} has an invalid share mode.") from exc
        if share_x not in (ShareMode.NONE, ShareMode.ALL) or share_y not in (
            ShareMode.NONE,
            ShareMode.ALL,
        ):
            raise ValueError("Fixed layout templates support only none/all sharing.")

        share_toggle = raw.get("share_toggle")
        if share_toggle not in (None, "x", "y"):
            raise ValueError(f"Layout preset {key!r} has an invalid share toggle.")
        if share_toggle == "x" and share_x is not ShareMode.ALL:
            raise ValueError(f"Layout preset {key!r} must share X by default.")
        if share_toggle == "y" and share_y is not ShareMode.ALL:
            raise ValueError(f"Layout preset {key!r} must share Y by default.")

        right_y = bool(raw.get("right_y", False))
        if right_y and (nrows, ncols) != (1, 1):
            raise ValueError("The fixed right-Y template must use a 1 × 1 grid.")
        outer_x = bool(raw.get("outer_x_labels", False))
        outer_y = bool(raw.get("outer_y_labels", False))
        if outer_x and share_x is ShareMode.NONE:
            raise ValueError(f"Layout preset {key!r} hides X labels without sharing X.")
        if outer_y and share_y is ShareMode.NONE:
            raise ValueError(f"Layout preset {key!r} hides Y labels without sharing Y.")

        presets.append(
            AxesLayoutPreset(
                key=key,
                label=label,
                toolbar_label=toolbar_label,
                icon=icon,
                nrows=nrows,
                ncols=ncols,
                width_ratios=_positive_ratios(
                    raw.get("width_ratios"), ncols, f"{key}.width_ratios"
                ),
                height_ratios=_positive_ratios(
                    raw.get("height_ratios"), nrows, f"{key}.height_ratios"
                ),
                share_x=share_x,
                share_y=share_y,
                share_toggle=share_toggle,
                outer_x_labels=outer_x,
                outer_y_labels=outer_y,
                right_y=right_y,
            )
        )
    return tuple(presets)


def axes_layout_preset(key: str) -> AxesLayoutPreset:
    """Resolve one fixed layout template by its stable key."""

    wanted = str(key)
    for preset in axes_layout_presets():
        if preset.key == wanted:
            return preset
    raise ValueError(f"Unknown Axes layout preset: {wanted}")


class AxesLayoutInput(QWidget):
    """Collect one validated :class:`AxesLayoutSpec` without Controllers."""

    validity_changed = Signal(bool, str)

    def __init__(
        self,
        *,
        color_library,
        preset_key: str | None = "single",
        default_view: AxesViewSpec | None = None,
        edit_definition: dict | None = None,
        occupied_cells: set[tuple[int, int]] | None = None,
        twin_cells: set[tuple[int, int]] | None = None,
        relationship_summary: str | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._editing = edit_definition is not None
        self._edit_definition = edit_definition
        self._preset = None if self._editing else axes_layout_preset(preset_key or "")
        self._color_library = color_library
        self._occupied_cells = set(occupied_cells or ())
        self._twin_cells = set(twin_cells or ())
        default_view = default_view or AxesViewSpec()

        if self._editing:
            self._nrows = int(edit_definition["nrows"])
            self._ncols = int(edit_definition["ncols"])
            if not self._occupied_cells:
                raise ValueError("The editable layout has no primary Axes cells.")
        else:
            self._nrows = self._preset.nrows
            self._ncols = self._preset.ncols
            self._occupied_cells = {
                (row, column)
                for row in range(self._nrows)
                for column in range(self._ncols)
            }

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.addWidget(
            self._header(
                relationship_summary
                if self._editing
                else self._preset.summary(sharing_enabled=True)
            )
        )

        layout_page = QWidget(self)
        layout_body = QVBoxLayout(layout_page)
        layout_body.setContentsMargins(0, 8, 0, 0)

        self.share_toggle_input: QCheckBox | None = None
        self.merge_legend_input: QCheckBox | None = None
        if not self._editing and self._preset.share_toggle is not None:
            dimension = self._preset.share_toggle.upper()
            self.share_toggle_input = QCheckBox(
                f"Share {dimension} axis", layout_page
            )
            self.share_toggle_input.setObjectName(
                f"layout_share_{self._preset.share_toggle}_toggle"
            )
            self.share_toggle_input.setChecked(True)
            self.share_toggle_input.toggled.connect(self._sync_template_summary)
            layout_body.addWidget(self.share_toggle_input)

        if not self._editing and self._preset.right_y:
            self.merge_legend_input = QCheckBox(
                "Merge primary and right-Y entries in the primary legend",
                layout_page,
            )
            layout_body.addWidget(self.merge_legend_input)

        self._build_geometry_group(layout_page, layout_body)
        self.validation_label = QLabel(layout_page)
        self.validation_label.setObjectName("layout_validation_message")
        self.validation_label.setWordWrap(True)
        self.validation_label.setStyleSheet("color: #c0392b;")
        layout_body.addWidget(self.validation_label)
        layout_body.addStretch(1)

        self.tabs: QTabWidget | None = None
        if self._editing:
            root.addWidget(layout_page)
        else:
            self.tabs = QTabWidget(self)
            self.tabs.addTab(layout_page, "Layout")
            axes_page = QWidget(self.tabs)
            self._build_axes_page(axes_page, default_view)
            self.tabs.addTab(axes_page, "Axes")
            root.addWidget(self.tabs)

        self._connect_validation_controls()
        self._sync_ranges()
        self.refresh_validation()

    def _header(self, summary: str | None) -> QWidget:
        header = QFrame(self)
        header.setObjectName("layout_template_header")
        row = QHBoxLayout(header)
        row.setContentsMargins(8, 8, 8, 8)

        icon_label = QLabel(header)
        icon_label.setObjectName("layout_template_icon")
        icon_label.setFixedSize(56, 56)
        icon_path = (
            resolve_icon_path("layout.svg")
            if self._editing
            else self._preset.icon_path
        )
        icon_label.setPixmap(
            normalized_layout_icon(
                icon_path,
                canvas_size=48,
                visual_size=40,
                tint=COLORS["text_primary"] if self._editing else None,
            ).pixmap(48, 48)
        )
        icon_label.setAlignment(Qt.AlignCenter)
        row.addWidget(icon_label)

        text = QWidget(header)
        text_layout = QVBoxLayout(text)
        text_layout.setContentsMargins(0, 0, 0, 0)
        title = QLabel(
            "Existing Axes layout" if self._editing else self._preset.label,
            text,
        )
        title_font = title.font()
        title_font.setBold(True)
        title.setFont(title_font)
        self.summary_label = QLabel(str(summary or "Persisted layout geometry"), text)
        self.summary_label.setWordWrap(True)
        text_layout.addWidget(title)
        text_layout.addWidget(self.summary_label)
        row.addWidget(text, 1)
        return header

    def _build_geometry_group(self, parent: QWidget, host: QVBoxLayout) -> None:
        self.geometry_group = QGroupBox("Advanced geometry", parent)
        self.geometry_group.setObjectName("layout_advanced_geometry")
        self.geometry_group.setCheckable(True)
        group_layout = QVBoxLayout(self.geometry_group)
        self.geometry_contents = QWidget(self.geometry_group)
        form = QFormLayout(self.geometry_contents)

        self.width_ratios_input = QLineEdit(self.geometry_contents)
        self.height_ratios_input = QLineEdit(self.geometry_contents)
        width_ratios, height_ratios = self._initial_ratios()
        self.width_ratios_input.setText(self._format_ratios(width_ratios))
        self.height_ratios_input.setText(self._format_ratios(height_ratios))
        self.width_ratios_input.setPlaceholderText(
            ", ".join("1" for _ in range(self._ncols))
        )
        self.height_ratios_input.setPlaceholderText(
            ", ".join("1" for _ in range(self._nrows))
        )
        form.addRow("Column width ratios", self.width_ratios_input)
        form.addRow("Row height ratios", self.height_ratios_input)

        margins = QWidget(self.geometry_contents)
        margins_grid = QGridLayout(margins)
        margins_grid.setContentsMargins(0, 0, 0, 0)
        self.left_input = self._fraction_input(margins, 0.125)
        self.right_input = self._fraction_input(margins, 0.9)
        self.bottom_input = self._fraction_input(margins, 0.11)
        self.top_input = self._fraction_input(margins, 0.88)
        for index, (label, control) in enumerate(
            (
                ("Left", self.left_input),
                ("Right", self.right_input),
                ("Bottom", self.bottom_input),
                ("Top", self.top_input),
            )
        ):
            margins_grid.addWidget(
                QLabel(label, margins), index // 2, (index % 2) * 2
            )
            margins_grid.addWidget(control, index // 2, (index % 2) * 2 + 1)
        form.addRow("Margins", margins)

        spacing = QWidget(self.geometry_contents)
        spacing_row = QHBoxLayout(spacing)
        spacing_row.setContentsMargins(0, 0, 0, 0)
        self.wspace_input = self._number_input(
            spacing, 0.2, minimum=0.0, maximum=5.0
        )
        self.hspace_input = self._number_input(
            spacing, 0.2, minimum=0.0, maximum=5.0
        )
        spacing_row.addWidget(QLabel("Horizontal", spacing))
        spacing_row.addWidget(self.wspace_input)
        spacing_row.addWidget(QLabel("Vertical", spacing))
        spacing_row.addWidget(self.hspace_input)
        form.addRow("Spacing", spacing)

        self.constrained_input = QCheckBox(
            "Use constrained layout", self.geometry_contents
        )
        form.addRow("Figure", self.constrained_input)
        group_layout.addWidget(self.geometry_contents)
        host.addWidget(self.geometry_group)

        if self._editing:
            self._load_definition(self._edit_definition)
        self.geometry_group.setChecked(self._editing)
        self.geometry_contents.setVisible(self._editing)
        self.geometry_group.toggled.connect(self.geometry_contents.setVisible)

    def _build_axes_page(self, axes_page: QWidget, default_view: AxesViewSpec) -> None:
        axes_form = QFormLayout(axes_page)
        self.auto_x_input, self.xmin_input, self.xmax_input = self._range_input(
            axes_page, "X"
        )
        axes_form.addRow(
            "X range",
            self._range_row(
                axes_page, self.auto_x_input, self.xmin_input, self.xmax_input
            ),
        )
        self.auto_y_input, self.ymin_input, self.ymax_input = self._range_input(
            axes_page, "Y"
        )
        axes_form.addRow(
            "Y range",
            self._range_row(
                axes_page, self.auto_y_input, self.ymin_input, self.ymax_input
            ),
        )
        self.xscale_input = self._scale_combo(axes_page)
        self.yscale_input = self._scale_combo(axes_page)
        scale_row = QWidget(axes_page)
        scale_layout = QHBoxLayout(scale_row)
        scale_layout.setContentsMargins(0, 0, 0, 0)
        scale_layout.addWidget(QLabel("X", scale_row))
        scale_layout.addWidget(self.xscale_input)
        scale_layout.addWidget(QLabel("Y", scale_row))
        scale_layout.addWidget(self.yscale_input)
        axes_form.addRow("Scale", scale_row)

        self.invert_x_input = QCheckBox("Invert X", axes_page)
        self.invert_y_input = QCheckBox("Invert Y", axes_page)
        inversion = QWidget(axes_page)
        inversion_row = QHBoxLayout(inversion)
        inversion_row.setContentsMargins(0, 0, 0, 0)
        inversion_row.addWidget(self.invert_x_input)
        inversion_row.addWidget(self.invert_y_input)
        axes_form.addRow("Direction", inversion)

        self.aspect_input = QComboBox(axes_page)
        self.aspect_input.addItems(("auto", "equal"))
        axes_form.addRow("Aspect", self.aspect_input)
        self.facecolor_override = QCheckBox("Override style background", axes_page)
        axes_form.addRow("Background", self.facecolor_override)
        self.facecolor_input = ColorChoiceWidget(
            color=default_view.facecolor or "#ffffff",
            color_library=self._color_library,
            auto_record_recent=False,
            parent=axes_page,
        )
        self.facecolor_input.setEnabled(False)
        axes_form.addRow("Color", self.facecolor_input)

        self.x_major_grid_input = QCheckBox("X major", axes_page)
        self.x_minor_grid_input = QCheckBox("X minor", axes_page)
        self.y_major_grid_input = QCheckBox("Y major", axes_page)
        self.y_minor_grid_input = QCheckBox("Y minor", axes_page)
        self.x_major_grid_input.setChecked(default_view.x_major_grid)
        self.x_minor_grid_input.setChecked(default_view.x_minor_grid)
        self.y_major_grid_input.setChecked(default_view.y_major_grid)
        self.y_minor_grid_input.setChecked(default_view.y_minor_grid)
        grid_row = QWidget(axes_page)
        grid_layout = QHBoxLayout(grid_row)
        grid_layout.setContentsMargins(0, 0, 0, 0)
        for control in (
            self.x_major_grid_input,
            self.x_minor_grid_input,
            self.y_major_grid_input,
            self.y_minor_grid_input,
        ):
            grid_layout.addWidget(control)
        axes_form.addRow("Grid", grid_row)

        self.xscale_input.setCurrentText(default_view.xscale)
        self.yscale_input.setCurrentText(default_view.yscale)
        self.aspect_input.setCurrentText(str(default_view.aspect))
        self.invert_x_input.setChecked(default_view.invert_x)
        self.invert_y_input.setChecked(default_view.invert_y)
        self._load_range_defaults(
            self.auto_x_input,
            self.xmin_input,
            self.xmax_input,
            default_view.xlim,
        )
        self._load_range_defaults(
            self.auto_y_input,
            self.ymin_input,
            self.ymax_input,
            default_view.ylim,
        )

        self.facecolor_override.toggled.connect(self.facecolor_input.setEnabled)
        self.auto_x_input.toggled.connect(self._sync_ranges)
        self.auto_y_input.toggled.connect(self._sync_ranges)

        if self._preset.right_y:
            right_group = QGroupBox("Right Y Axes", axes_page)
            right_form = QFormLayout(right_group)
            (
                self.right_auto_y_input,
                self.right_ymin_input,
                self.right_ymax_input,
            ) = self._range_input(right_group, "Right Y")
            right_form.addRow(
                "Y range",
                self._range_row(
                    right_group,
                    self.right_auto_y_input,
                    self.right_ymin_input,
                    self.right_ymax_input,
                ),
            )
            self.right_yscale_input = self._scale_combo(right_group)
            right_form.addRow("Y scale", self.right_yscale_input)
            self.right_invert_y_input = QCheckBox("Invert Y", right_group)
            right_form.addRow("Direction", self.right_invert_y_input)
            axes_form.addRow(right_group)
            self.right_auto_y_input.toggled.connect(self._sync_ranges)

    def _connect_validation_controls(self) -> None:
        self.width_ratios_input.textChanged.connect(self.refresh_validation)
        self.height_ratios_input.textChanged.connect(self.refresh_validation)
        for control in (
            self.left_input,
            self.right_input,
            self.bottom_input,
            self.top_input,
            self.wspace_input,
            self.hspace_input,
        ):
            control.valueChanged.connect(self.refresh_validation)
        if self.share_toggle_input is not None:
            self.share_toggle_input.toggled.connect(self.refresh_validation)

    def _initial_ratios(self) -> tuple[tuple[float, ...], tuple[float, ...]]:
        if self._editing:
            return (
                tuple(self._edit_definition["width_ratios"]),
                tuple(self._edit_definition["height_ratios"]),
            )
        return self._preset.width_ratios, self._preset.height_ratios

    @staticmethod
    def _format_ratios(values) -> str:
        return ", ".join(f"{float(value):g}" for value in values)

    @staticmethod
    def _number_input(parent, value, *, minimum=-1.0e12, maximum=1.0e12):
        control = QDoubleSpinBox(parent)
        control.setDecimals(6)
        control.setRange(float(minimum), float(maximum))
        control.setValue(float(value))
        return control

    @classmethod
    def _fraction_input(cls, parent, value):
        return cls._number_input(parent, value, minimum=0.0, maximum=1.0)

    @staticmethod
    def _scale_combo(parent):
        control = QComboBox(parent)
        control.addItems(("linear", "log", "symlog", "logit"))
        return control

    @classmethod
    def _range_input(cls, parent, _name):
        automatic = QCheckBox("Automatic", parent)
        automatic.setChecked(True)
        return automatic, cls._number_input(parent, 0.0), cls._number_input(parent, 1.0)

    @staticmethod
    def _range_row(parent, automatic, minimum, maximum):
        row = QWidget(parent)
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(automatic)
        layout.addWidget(minimum)
        layout.addWidget(maximum)
        return row

    @staticmethod
    def _load_range_defaults(automatic, minimum, maximum, limits) -> None:
        if limits is None:
            return
        automatic.setChecked(False)
        minimum.setValue(float(limits[0]))
        maximum.setValue(float(limits[1]))

    def _sync_ranges(self) -> None:
        if self._editing:
            return
        ranges = [
            (self.auto_x_input, self.xmin_input, self.xmax_input),
            (self.auto_y_input, self.ymin_input, self.ymax_input),
        ]
        if self._preset.right_y:
            ranges.append(
                (
                    self.right_auto_y_input,
                    self.right_ymin_input,
                    self.right_ymax_input,
                )
            )
        for automatic, minimum, maximum in ranges:
            minimum.setEnabled(not automatic.isChecked())
            maximum.setEnabled(not automatic.isChecked())

    def _sharing_enabled(self) -> bool:
        return (
            self.share_toggle_input is None
            or self.share_toggle_input.isChecked()
        )

    def _sync_template_summary(self) -> None:
        self.summary_label.setText(
            self._preset.summary(sharing_enabled=self._sharing_enabled())
        )

    def _load_definition(self, definition: dict) -> None:
        margins = definition["margins"]
        spacing = definition["spacing"]
        self.left_input.setValue(float(margins["left"]))
        self.right_input.setValue(float(margins["right"]))
        self.bottom_input.setValue(float(margins["bottom"]))
        self.top_input.setValue(float(margins["top"]))
        self.wspace_input.setValue(float(spacing["wspace"]))
        self.hspace_input.setValue(float(spacing["hspace"]))

    @staticmethod
    def _ratios(text: str, count: int, name: str) -> tuple[float, ...]:
        value = text.strip()
        if not value:
            return (1.0,) * count
        try:
            result = tuple(float(item.strip()) for item in value.split(","))
        except ValueError as exc:
            raise ValueError(f"{name} ratios must be comma-separated numbers.") from exc
        if len(result) != count:
            raise ValueError(f"{name} ratios require exactly {count} values.")
        return result

    def _primary_view(self) -> AxesViewSpec:
        return AxesViewSpec(
            xlim=(
                None
                if self.auto_x_input.isChecked()
                else (self.xmin_input.value(), self.xmax_input.value())
            ),
            ylim=(
                None
                if self.auto_y_input.isChecked()
                else (self.ymin_input.value(), self.ymax_input.value())
            ),
            xscale=self.xscale_input.currentText(),
            yscale=self.yscale_input.currentText(),
            invert_x=self.invert_x_input.isChecked(),
            invert_y=self.invert_y_input.isChecked(),
            aspect=self.aspect_input.currentText(),
            facecolor=(
                self.facecolor_input.color()
                if self.facecolor_override.isChecked()
                else None
            ),
            x_major_grid=self.x_major_grid_input.isChecked(),
            x_minor_grid=self.x_minor_grid_input.isChecked(),
            y_major_grid=self.y_major_grid_input.isChecked(),
            y_minor_grid=self.y_minor_grid_input.isChecked(),
        )

    def _right_view(self) -> AxesViewSpec:
        return AxesViewSpec(
            ylim=(
                None
                if self.right_auto_y_input.isChecked()
                else (self.right_ymin_input.value(), self.right_ymax_input.value())
            ),
            yscale=self.right_yscale_input.currentText(),
            invert_y=self.right_invert_y_input.isChecked(),
        )

    def spec(self) -> AxesLayoutSpec:
        """Return the current fixed-template or geometry-edit request."""

        if self._editing:
            primary = AxesViewSpec()
            cells = tuple(
                AxesCellSpec(
                    row,
                    column,
                    primary=primary,
                    right_y=(
                        AxesViewSpec()
                        if (row, column) in self._twin_cells
                        else None
                    ),
                )
                for row, column in sorted(self._occupied_cells)
            )
            share_x = share_y = ShareMode.NONE
            outer_x = outer_y = False
            layout_id = str(self._edit_definition["id"])
        else:
            primary = self._primary_view()
            right = self._right_view() if self._preset.right_y else None
            cells = tuple(
                AxesCellSpec(
                    row,
                    column,
                    primary=primary,
                    right_y=right,
                    merge_legend=(
                        bool(
                            self.merge_legend_input
                            and self.merge_legend_input.isChecked()
                        )
                    ),
                )
                for row, column in sorted(self._occupied_cells)
            )
            share_x, share_y = self._preset.effective_sharing(
                self._sharing_enabled()
            )
            outer_x = (
                self._preset.outer_x_labels and share_x is not ShareMode.NONE
            )
            outer_y = (
                self._preset.outer_y_labels and share_y is not ShareMode.NONE
            )
            layout_id = None

        return AxesLayoutSpec(
            self._nrows,
            self._ncols,
            cells,
            width_ratios=self._ratios(
                self.width_ratios_input.text(), self._ncols, "Column width"
            ),
            height_ratios=self._ratios(
                self.height_ratios_input.text(), self._nrows, "Row height"
            ),
            left=self.left_input.value(),
            right=self.right_input.value(),
            bottom=self.bottom_input.value(),
            top=self.top_input.value(),
            wspace=self.wspace_input.value(),
            hspace=self.hspace_input.value(),
            share_x=share_x,
            share_y=share_y,
            outer_x_labels=outer_x,
            outer_y_labels=outer_y,
            constrained_layout=self.constrained_input.isChecked(),
            layout_id=layout_id,
        )

    def refresh_validation(self, *_args) -> tuple[bool, str]:
        """Refresh inline validation and publish the Create/Apply state."""

        try:
            self.spec()
        except (TypeError, ValueError) as exc:
            valid, message = False, str(exc)
        else:
            valid, message = True, ""
        self.validation_label.setText(message)
        self.validation_label.setVisible(not valid)
        self.validity_changed.emit(valid, message)
        return valid, message

    @property
    def records_recent_color(self) -> bool:
        return bool(
            not self._editing
            and self.facecolor_override.isChecked()
        )

    @property
    def selected_color(self) -> str:
        return "" if self._editing else self.facecolor_input.color()


__all__ = [
    "AxesLayoutInput",
    "AxesLayoutPreset",
    "axes_layout_preset",
    "axes_layout_presets",
    "normalized_layout_icon",
]
