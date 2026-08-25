"""Axes palette Inspector section."""

from __future__ import annotations


from PySide6.QtCore import QSignalBlocker, QSize, Qt
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from mygui.figuremodify.style_base.color_models import PaletteSource
from mygui.widgets.common_widget.min_widget.py_colorchoice_widgets import (
    choose_palette,
)

from ..context import perform_editor_action
from ..inspector import EditorSection
from ..lifecycle import CallbackLifecycle

class PaletteSection(QWidget, EditorSection):
    """Show and switch the effective palette for an Axes."""

    STYLE_MODE = "style"
    USER_MODE = "user"

    def __init__(self, controller, *, context, parent=None):
        super().__init__(parent)
        self.controller = controller
        self.context = context
        self._disposed = False
        self._lifecycle = CallbackLifecycle()

        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(6)

        current_layout = QHBoxLayout()
        current_layout.setContentsMargins(0, 0, 0, 0)
        current_layout.addWidget(QLabel("Current:", self))
        self.current_palette_label = QLabel(self)
        self.current_palette_label.setWordWrap(True)
        self.current_palette_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        current_layout.addWidget(self.current_palette_label, 1)
        self.layout.addLayout(current_layout)

        self.palette_preview = _PalettePreview(self)
        self.layout.addWidget(self.palette_preview)

        controls_layout = QHBoxLayout()
        controls_layout.setContentsMargins(0, 0, 0, 0)
        controls_layout.addWidget(QLabel("Source:", self))
        self.source_input = QComboBox(self)
        self.source_input.setAccessibleName("Axes palette source")
        self.source_input.addItem("Style default", self.STYLE_MODE)
        self.source_input.addItem("User-selected", self.USER_MODE)
        self.source_input.currentIndexChanged.connect(
            self._source_changed
        )
        controls_layout.addWidget(self.source_input, 1)
        self.button = QPushButton("Choose…", self)
        self.button.setAccessibleName(
            "Choose and apply a user color palette to axes"
        )
        self.button.clicked.connect(self.choose_and_apply_palette)
        controls_layout.addWidget(self.button)
        self.layout.addLayout(controls_layout)

        figure_id = self.controller.state.parent_id
        self._unsubscribe = self.context.registry.subscribe(
            self._component_event,
            kinds=("changed",),
        )
        self._lifecycle.add(self._unsubscribe)
        try:
            self._figure_id = figure_id
            self.sync_from_controller()
        except Exception:
            self._lifecycle.close()
            raise

    def _component_event(self, event) -> None:
        if (
            not self._disposed
            and event.component_id == self._figure_id
        ):
            self.sync_from_controller()

    @staticmethod
    def _user_palette_description(palette) -> str:
        if palette.source is PaletteSource.CUSTOM:
            kind = "Custom palette"
        elif palette.source is PaletteSource.BUILTIN:
            kind = "Built-in palette"
        else:
            kind = "Selected palette"
        return f"{kind} · {palette.name}"

    def sync_from_controller(self) -> None:
        """Refresh source, palette name and colors from authoritative state."""

        status = self.context.axes_commands.palette_status(
            self.controller.component_id
        )
        if status.uses_style_default:
            description = f"Style default · {status.figure_style}"
            mode = self.STYLE_MODE
        else:
            description = self._user_palette_description(status.palette)
            mode = self.USER_MODE

        blocker = QSignalBlocker(self.source_input)
        try:
            self.source_input.setCurrentIndex(
                self.source_input.findData(mode)
            )
        finally:
            del blocker
        self.button.setEnabled(mode == self.USER_MODE)
        self.current_palette_label.setText(description)
        self.current_palette_label.setToolTip(description)
        self.palette_preview.set_colors(status.palette.colors)

    def _source_changed(self, _index: int) -> None:
        mode = self.source_input.currentData()
        status = self.context.axes_commands.palette_status(
            self.controller.component_id
        )
        if mode == self.STYLE_MODE:
            if not status.uses_style_default:
                self.use_style_default()
            return
        if status.uses_style_default:
            self.choose_and_apply_palette()

    def _apply_palette(self, palette, *, success: str) -> bool:
        controllers = self.context.registry.query(
            capabilities={"color", "data"},
            parent_id=self.controller.component_id,
            recursive=True,
        )
        result = perform_editor_action(self.context,
            "Apply Axes Palette",
            lambda: self.context.axes_commands.apply_palette(
                self.controller.component_id,
                palette,
            ),
        )
        if not self.context.messages.present(result, success=success):
            self.sync_from_controller()
            return False
        if controllers:
            self.context.color_library.record_recent_many(
                palette.colors[index % len(palette.colors)]
                for index in range(len(controllers))
            )
        self.sync_from_controller()
        return True

    def use_style_default(self) -> bool:
        """Apply the current Figure style palette to this Axes."""

        status = self.context.axes_commands.palette_status(
            self.controller.component_id
        )
        style_palette = self.context.axes_commands.style_palette(
            self.controller.component_id
        )
        controllers = self.context.registry.query(
            capabilities={"color", "data"},
            parent_id=self.controller.component_id,
            recursive=True,
        )
        return self._apply_palette(
            style_palette,
            success=(
                f"Applied the {status.figure_style} style palette to "
                f"{len(controllers)} chart objects."
            ),
        )

    def choose_and_apply_palette(self):
        """Choose and apply a user-selected palette."""

        status = self.context.axes_commands.palette_status(
            self.controller.component_id
        )
        initial_palette = (
            None if status.uses_style_default else status.palette
        )
        palette = choose_palette(
            self,
            self.context.color_library,
            initial_palette,
        )
        if palette is None:
            self.sync_from_controller()
            return False
        controllers = self.context.registry.query(
            capabilities={"color", "data"},
            parent_id=self.controller.component_id,
            recursive=True,
        )
        return self._apply_palette(
            palette,
            success=(
                f"Applied {palette.display_name} to "
                f"{len(controllers)} chart objects."
            ),
        )

    def dispose(self) -> None:
        """Detach the Figure-style event callback."""

        if self._disposed:
            return
        self._disposed = True
        self._lifecycle.close()


class _PalettePreview(QWidget):
    """Compact read-only strip for the colors in one palette."""

    MIN_SWATCH_WIDTH = 36
    ROW_HEIGHT = 20

    def __init__(self, parent=None):
        super().__init__(parent)
        self._colors: tuple[str, ...] = ()
        policy = QSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Preferred,
        )
        policy.setHeightForWidth(True)
        self.setSizePolicy(policy)
        self.setMinimumHeight(self.ROW_HEIGHT + 2)
        self.setAccessibleName("Current axes palette colors")

    def set_colors(self, colors) -> None:
        """Set the canonical colors displayed by this preview."""

        self._colors = tuple(str(color) for color in colors)
        self.setToolTip(", ".join(self._colors))
        self.setAccessibleDescription(self.toolTip())
        self.updateGeometry()
        self.update()

    def colors(self) -> tuple[str, ...]:
        """Return the displayed colors for tests and accessibility tooling."""

        return self._colors

    def _column_count(self, width: int) -> int:
        if not self._colors:
            return 1
        inner_width = max(1, int(width) - 2)
        return min(
            len(self._colors),
            max(1, inner_width // self.MIN_SWATCH_WIDTH),
        )

    def row_count_for_width(self, width: int) -> int:
        """Return the rows required without shrinking swatches excessively."""

        if not self._colors:
            return 1
        columns = self._column_count(width)
        return (
            len(self._colors) + columns - 1
        ) // columns

    def hasHeightForWidth(self) -> bool:
        """Tell Qt layouts that narrow previews need additional rows."""

        return True

    def heightForWidth(self, width: int) -> int:
        """Return the wrapped preview height for ``width``."""

        return (
            self.row_count_for_width(width) * self.ROW_HEIGHT + 2
        )

    def sizeHint(self) -> QSize:
        """Return a useful default size for one-row palettes."""

        width = max(
            180,
            len(self._colors) * self.MIN_SWATCH_WIDTH + 2,
        )
        return QSize(width, self.heightForWidth(width))

    def minimumSizeHint(self) -> QSize:
        """Allow narrow Inspectors while preserving readable swatches."""

        width = self.MIN_SWATCH_WIDTH * 3 + 2
        return QSize(width, self.heightForWidth(width))

    def paintEvent(self, event) -> None:
        """Paint wrapped color blocks and a neutral outline."""

        del event
        painter = QPainter(self)
        rect = self.rect().adjusted(1, 1, -1, -1)
        if self._colors and rect.width() > 0:
            painter.setPen(Qt.PenStyle.NoPen)
            count = len(self._colors)
            columns = self._column_count(self.width())
            rows = self.row_count_for_width(self.width())
            for index, color in enumerate(self._colors):
                row = index // columns
                column = index % columns
                row_start = row * columns
                row_items = min(columns, count - row_start)
                left = rect.left() + round(
                    rect.width() * column / row_items
                )
                right = rect.left() + round(
                    rect.width() * (column + 1) / row_items
                )
                top = rect.top() + round(
                    rect.height() * row / rows
                )
                bottom = rect.top() + round(
                    rect.height() * (row + 1) / rows
                )
                painter.fillRect(
                    left,
                    top,
                    max(1, right - left),
                    max(1, bottom - top),
                    QColor(color),
                )
        painter.setPen(self.palette().mid().color())
        painter.drawRect(rect)
