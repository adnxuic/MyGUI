"""Implement reusable appearance and text editor sections."""

from __future__ import annotations

from collections.abc import Callable, Iterable

from PySide6.QtCore import QSignalBlocker, QSize, Qt
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QSizePolicy,
    QSpinBox,
    QToolBox,
    QVBoxLayout,
    QWidget,
)

from mygui import status_messages, tex_config
from mygui.database import ColumnRef
from mygui.figuremodify.components import ComponentKind, ComponentMutation
from mygui.figuremodify.in_axes import embedded_image_data
from mygui.widgets.common_widget.min_widget.py_colorchoice_widgets import (
    choose_palette,
)

from .base import ComponentEditorBase
from .common import DebouncedTextBinding
from .inputs import DataReferenceInput
from .inspector import EditorSection
from .lifecycle import CallbackLifecycle


ApplyProperties = Callable[[dict[str, object]], object]
ApplyReferences = Callable[
    [object, ColumnRef, ColumnRef, dict[str, str], str],
    object,
]


class DataReferenceSection(QWidget, EditorSection):
    """Shared X/Y selector with a role-specific atomic commit strategy."""

    def __init__(
        self,
        controller,
        *,
        context,
        apply_references: ApplyReferences,
        success_message: Callable[[str], str] | str,
        parent=None,
    ):
        super().__init__(parent)
        self.controller = controller
        self.context = context
        self._apply_references = apply_references
        self._success_message = success_message

        data = controller.read_state().data
        x_ref = ColumnRef.from_dict(data["x_ref"])
        y_ref = ColumnRef.from_dict(data["y_ref"])
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.data_choice_widget = DataReferenceInput(
            context.repository,
            x_ref.project_id,
            parent=self,
        )
        self.data_choice_widget.set_refs(x_ref, y_ref)
        self.data_choice_widget.set_preprocess(data["preprocess"])
        layout.addWidget(self.data_choice_widget)
        self.x_data_input = self.data_choice_widget.x_data_input
        self.y_data_input = self.data_choice_widget.y_data_input
        self.data_choice_widget.refs_connect(
            self.x_data_change,
            self.y_data_change,
        )
        self.data_choice_widget.expressions_connect(
            self.x_expression_change,
            self.y_expression_change,
        )

    def _message(self, axis: str) -> str:
        if callable(self._success_message):
            return self._success_message(axis)
        return str(self._success_message)

    def _apply(self, axis: str) -> bool:
        data = self.controller.read_state().data
        x_ref = self.data_choice_widget.get_x_ref()
        y_ref = self.data_choice_widget.get_y_ref()
        x_ref = x_ref or ColumnRef.from_dict(data["x_ref"])
        y_ref = y_ref or ColumnRef.from_dict(data["y_ref"])
        result = self._apply_references(
            self.controller,
            x_ref,
            y_ref,
            self.data_choice_widget.preprocess_values(),
            axis,
        )
        if not self.context.messages.present(
            result,
            success=self._message(axis),
        ):
            self.sync_from_controller()
            return False
        return True

    def x_data_change(self, *_args) -> bool:
        """Apply the x data change emitted by the corresponding control."""

        return self._apply("x")

    def y_data_change(self, *_args) -> bool:
        """Apply the y data change emitted by the corresponding control."""

        return self._apply("y")

    def x_expression_change(self) -> bool:
        """Apply the completed X preprocessing expression edit."""

        return self._apply("x")

    def y_expression_change(self) -> bool:
        """Apply the completed Y preprocessing expression edit."""

        return self._apply("y")

    def sync_from_controller(self) -> None:
        """Refresh controls from authoritative Controller state."""

        data = self.controller.read_state().data
        self.data_choice_widget.set_refs(
            ColumnRef.from_dict(data["x_ref"]),
            ColumnRef.from_dict(data["y_ref"]),
        )
        self.data_choice_widget.set_preprocess(data["preprocess"])

    def dispose(self) -> None:
        """Disconnect callbacks and release resources owned by this object."""

        self.data_choice_widget.dispose()


class PropertySection(ComponentEditorBase, EditorSection):
    """A reusable subset of a Controller's PropertySpec form."""

    def __init__(
        self,
        controller,
        *,
        context,
        property_keys: Iterable[str] | None = None,
        apply_properties: ApplyProperties | None = None,
        parent: QWidget | None = None,
    ):
        self._apply_properties = apply_properties
        specs = controller.property_specs()
        if property_keys is None:
            selected = list(specs.values())
        else:
            selected = [
                specs[key]
                for key in property_keys
                if key in specs
            ]
        super().__init__(
            controller,
            context=context,
            color_library=context.color_library,
            property_specs=selected,
            parent=parent,
        )

    def _set_controller_property(self, key: str, value):
        if self._apply_properties is None:
            return super()._set_controller_property(key, value)
        return self._apply_properties({key: value})

    def _success_message(self, key: str, label: str) -> str:
        state = self.controller.state
        if state.kind is ComponentKind.SPINE and key == "visible":
            side = str(state.selector.get("name", "spine")).title()
            return f"{side} spine visibility updated."
        return super()._success_message(key, label)

    def flush_text(self, key: str) -> bool:
        """Commit pending text after the edit-coalescing delay."""

        binding = self._text_bindings.get(key)
        return True if binding is None else binding.flush()

    def dispose(self) -> None:
        """Disconnect callbacks and release resources owned by this object."""

        for binding in self._text_bindings.values():
            binding.cancel()


class AxesLayoutSection(QWidget, EditorSection):
    """Show immutable Axes relationships and open safe geometry editing."""

    def __init__(self, controller, *, context, parent=None):
        super().__init__(parent)
        self.controller = controller
        self.context = context
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.summary_label = QLabel(self)
        self.summary_label.setWordWrap(True)
        layout.addWidget(self.summary_label)
        self.edit_button = QPushButton("Edit layout geometry…", self)
        self.edit_button.clicked.connect(self.edit_layout)
        layout.addWidget(self.edit_button)
        self.sync_from_controller()

    def sync_from_controller(self) -> None:
        """Refresh the persisted relationship summary."""

        subplot = self.controller.state.data.get("subplot", {})
        layer = "Right Y" if subplot.get("layer") == "right_y" else "Primary"
        shared = []
        if subplot.get("share_x_group"):
            shared.append("shared X")
        if subplot.get("share_y_group"):
            shared.append("shared Y")
        relationship = ", ".join(shared) if shared else "independent axes"
        self.summary_label.setText(
            f"Cell {int(subplot.get('row', 0)) + 1}, "
            f"{int(subplot.get('column', 0)) + 1} · {layer} · {relationship}.\n"
            "Cell occupancy, sharing, and twin relationships are fixed after creation."
        )

    def edit_layout(self) -> None:
        """Open the shared layout dialog for this Axes' stable layout id."""

        subplot = self.controller.state.data.get("subplot", {})
        layout_id = subplot.get("layout_id")
        if not layout_id:
            status_messages.show_error("This Axes has no editable layout record.")
            return
        try:
            from mygui.widgets.title_bar.titlebar_dialog.py_title_bar_dialog import (
                PyLayoutDialog,
            )

            canvas = self.context.axes_layout.canvas
            figure_window = canvas.figure_window
            if figure_window is None:
                raise ValueError("The Figure window is unavailable.")
            dialog = PyLayoutDialog(
                "Edit Axes layout",
                figure_window,
                parent=self,
                layout_id=str(layout_id),
            )
            dialog.exec()
        except Exception as exc:
            status_messages.show_error(str(exc))


class ImageInAxesSourceSection(QWidget, EditorSection):
    """Replace one embedded image through the authoritative inset Service."""

    IMAGE_FILTER = (
        "Raster images (*.png *.jpg *.jpeg *.bmp *.tif *.tiff);;"
        "All files (*)"
    )

    def __init__(self, controller, *, context, parent=None):
        super().__init__(parent)
        self.controller = controller
        self.context = context
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.filename_label = QLabel(self)
        self.filename_label.setWordWrap(True)
        self.filename_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        layout.addWidget(self.filename_label)
        self.replace_button = QPushButton("Replace image…", self)
        self.replace_button.clicked.connect(self.replace_image)
        layout.addWidget(self.replace_button)
        self.sync_from_controller()

    def replace_image(self) -> bool:
        """Choose, validate, embed, and apply a replacement raster image."""

        filename, _selected_filter = QFileDialog.getOpenFileName(
            self,
            "Replace inset image",
            "",
            self.IMAGE_FILTER,
        )
        if not filename:
            return False
        try:
            data = embedded_image_data(filename)
            result = self.context.in_axes.replace_image(
                self.controller,
                data,
            )
        except Exception as exc:
            status_messages.show_error(str(exc))
            self.sync_from_controller()
            return False
        if not self.context.messages.present(
            result,
            success="Inset image replaced.",
        ):
            self.sync_from_controller()
            return False
        self.sync_from_controller()
        return True

    def sync_from_controller(self) -> None:
        """Refresh the displayed embedded source filename."""

        filename = str(
            self.controller.read_state().data.get("filename", "")
        )
        self.filename_label.setText(
            f"Embedded source: {filename or '(unnamed image)'}"
        )

    def dispose(self) -> None:
        """Disconnect this section's local signal idempotently."""

        try:
            self.replace_button.clicked.disconnect(self.replace_image)
        except (RuntimeError, TypeError):
            pass


class LineAppearanceSection(QWidget, EditorSection):
    """The single shared appearance editor for every LineController role."""

    BASIC_KEYS = (
        "label",
        "visible",
        "color",
        "linestyle",
        "linewidth",
    )
    MARKER_KEYS = (
        "marker",
        "markersize",
        "markerfacecolor",
        "markeredgecolor",
        "markeredgewidth",
    )
    ADVANCED_KEYS = ("alpha", "zorder")
    PROPERTY_KEYS = BASIC_KEYS + MARKER_KEYS + ADVANCED_KEYS

    def __init__(self, controller, *, context, parent=None):
        super().__init__(parent)
        self.controller = controller
        self.context = context
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.toolbox = QToolBox(self)

        self._base = PropertySection(
            controller,
            context=context,
            property_keys=self.BASIC_KEYS,
            parent=self,
        )
        self._marker = PropertySection(
            controller,
            context=context,
            property_keys=self.MARKER_KEYS,
            parent=self,
        )
        self._advanced = PropertySection(
            controller,
            context=context,
            property_keys=self.ADVANCED_KEYS,
            parent=self,
        )
        self.toolbox.addItem(self._base, "Basic")
        self.toolbox.addItem(self._marker, "Marker")
        self.toolbox.addItem(self._advanced, "Advanced")
        self.layout.addWidget(self.toolbox)

    def editor(self, key: str):
        """Return the editor widget used for the property."""

        for section in (self._base, self._marker, self._advanced):
            try:
                return section.editor(key)
            except KeyError:
                continue
        raise KeyError(key)

    def editors(self):
        """Return the available editors."""

        result = {}
        for section in (self._base, self._marker, self._advanced):
            result.update(section.editors())
        return result

    def flush_text(self, key: str) -> bool:
        """Commit pending text after the edit-coalescing delay."""

        for section in (self._base, self._marker, self._advanced):
            if key in section.editors():
                return section.flush_text(key)
        raise KeyError(key)

    def sync_from_controller(self) -> None:
        """Refresh controls from authoritative Controller state."""

        self._base.sync_from_controller()
        self._marker.sync_from_controller()
        self._advanced.sync_from_controller()

    def dispose(self) -> None:
        """Disconnect callbacks and release resources owned by this object."""

        self._base.dispose()
        self._marker.dispose()
        self._advanced.dispose()


class ScatterAppearanceSection(QWidget, EditorSection):
    """Provide the scatter appearance section Qt widget."""

    BASIC_KEYS = (
        "label",
        "visible",
        "color",
        "edgecolor",
        "marker",
        "size",
        "linewidth",
    )
    ADVANCED_KEYS = ("alpha", "zorder")
    PROPERTY_KEYS = BASIC_KEYS + ADVANCED_KEYS

    def __init__(self, controller, *, context, parent=None):
        super().__init__(parent)
        self.controller = controller
        self.context = context
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.toolbox = QToolBox(self)
        self._base = PropertySection(
            controller,
            context=context,
            property_keys=self.BASIC_KEYS,
            parent=self,
        )
        self._advanced = PropertySection(
            controller,
            context=context,
            property_keys=self.ADVANCED_KEYS,
            parent=self,
        )
        self.toolbox.addItem(self._base, "Basic")
        self.toolbox.addItem(self._advanced, "Advanced")
        self.layout.addWidget(self.toolbox)

    def editor(self, key: str):
        """Return the editor widget used for the property."""

        for section in (self._base, self._advanced):
            try:
                return section.editor(key)
            except KeyError:
                continue
        raise KeyError(key)

    def editors(self):
        """Return the available editors."""

        result = {}
        result.update(self._base.editors())
        result.update(self._advanced.editors())
        return result

    def flush_text(self, key: str) -> bool:
        """Commit pending text after the edit-coalescing delay."""

        for section in (self._base, self._advanced):
            if key in section.editors():
                return section.flush_text(key)
        raise KeyError(key)

    def sync_from_controller(self) -> None:
        """Refresh controls from authoritative Controller state."""

        self._base.sync_from_controller()
        self._advanced.sync_from_controller()

    def dispose(self) -> None:
        """Disconnect callbacks and release resources owned by this object."""

        self._base.dispose()
        self._advanced.dispose()


class TextContentSection(QWidget, EditorSection):
    """Provide the text content section Qt widget."""

    def __init__(
        self,
        controller,
        *,
        context,
        property_key: str = "text",
        apply_properties: ApplyProperties | None = None,
        parent=None,
    ):
        super().__init__(parent)
        self.controller = controller
        self.context = context
        self.property_key = property_key
        self._apply_properties = apply_properties
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.text_content = QPlainTextEdit(self)
        self.text_content.setPlaceholderText("Text content")
        self.text_content.setPlainText(
            str(controller.read_state().properties[property_key])
        )
        self.layout.addWidget(self.text_content)
        self._text_binding = DebouncedTextBinding(
            self.text_content,
            self._apply_text_content,
            delay_ms=250,
            result_presenter=lambda result: context.messages.present(
                result,
                success="Text content updated.",
            ),
            parent=self,
        )

    def _apply_text_content(self, content: str):
        patch = {self.property_key: content}
        if self._apply_properties is not None:
            return self._apply_properties(patch)
        return self.controller.apply_mutation(
            ComponentMutation(
                self.controller.component_id,
                properties=patch,
            )
        )

    def set_text_content(self):
        """Set text content."""

        return self._text_binding.flush()

    def sync_from_controller(self) -> None:
        """Refresh controls from authoritative Controller state."""

        value = self.controller.read_state().properties[self.property_key]
        self._text_binding.set_text(str(value))

    def dispose(self) -> None:
        """Disconnect callbacks and release resources owned by this object."""

        self._text_binding.cancel()


class TextTypographySection(PropertySection):
    """Edit the text typography properties of a component."""

    DEFAULT_KEYS = (
        "fontfamily",
        "fontsize",
        "fontweight",
        "fontstyle",
        "color",
        "alpha",
    )

    def __init__(
        self,
        controller,
        *,
        context,
        property_keys: Iterable[str] | None = None,
        apply_properties: ApplyProperties | None = None,
        parent=None,
    ):
        super().__init__(
            controller,
            context=context,
            property_keys=property_keys or self.DEFAULT_KEYS,
            apply_properties=apply_properties,
            parent=parent,
        )
        if "fontfamily" in self.editors():
            self.font_input = self.editor("fontfamily")
        if "fontsize" in self.editors():
            self.font_size_input = self.editor("fontsize")

    def set_text_font(self, font: str):
        """Set text font."""

        return self.apply_property("fontfamily", str(font))

    def set_text_fontsize(self, size):
        """Set text fontsize."""

        return self.apply_property("fontsize", float(size))


class TextTransformSection(PropertySection):
    """Edit the text transform properties of a component."""

    KEYS = (
        "rotation",
        "horizontalalignment",
        "verticalalignment",
    )

    def __init__(self, controller, *, context, apply_properties, parent=None):
        super().__init__(
            controller,
            context=context,
            property_keys=self.KEYS,
            apply_properties=apply_properties,
            parent=parent,
        )


class TextPositionSection(PropertySection):
    """Edit the text position properties of a component."""

    KEYS = ("position", "visible")

    def __init__(self, controller, *, context, apply_properties, parent=None):
        super().__init__(
            controller,
            context=context,
            property_keys=self.KEYS,
            apply_properties=apply_properties,
            parent=parent,
        )
        position = self.editor("position")
        self.text_x_pos, self.text_y_pos = position.inputs

    def set_xy_position(self, *_args):
        """Set xy position."""

        return self.apply_property(
            "position",
            (self.text_x_pos.value(), self.text_y_pos.value()),
        )


class TextRenderSection(QWidget, EditorSection):
    """Provide the text render section Qt widget."""

    def __init__(self, controller, *, context, parent=None):
        super().__init__(parent)
        self.controller = controller
        self.context = context
        self._disposed = False
        self._lifecycle = CallbackLifecycle()
        self.layout = QHBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.addWidget(QLabel("Render:", self))
        self.tex_render = QCheckBox("TeX", self)
        self.tex_render.setToolTip("Render this text with TeX")
        self.layout.addWidget(self.tex_render)
        self.layout.addStretch()
        self._listener = self._tex_state_changed
        tex_config.register_tex_state_listener(self._listener)
        self._lifecycle.add(
            lambda: tex_config.unregister_tex_state_listener(
                self._listener
            )
        )
        try:
            self.tex_render.toggled.connect(self.set_tex_render)
            self._sync_tex_button()
        except Exception:
            self._lifecycle.close()
            raise

    def _sync_tex_button(self):
        enabled = tex_config.is_tex_enabled()
        blocker = QSignalBlocker(self.tex_render)
        self.tex_render.setEnabled(enabled)
        self.tex_render.setChecked(
            bool(
                self.controller.read_state().properties.get(
                    "usetex", False
                )
            )
        )
        del blocker

    def _tex_state_changed(self, enabled: bool):
        if self._disposed:
            return
        result = self.context.text_rendering.apply_tex_availability(enabled)
        if not result.committed:
            status_messages.show_warning(result.message)
        self._sync_tex_button()

    def set_tex_render(self, state):
        """Set tex render."""

        if self._disposed:
            return False
        checked = (
            bool(state)
            if isinstance(state, bool)
            else state in {Qt.Checked, Qt.CheckState.Checked}
        )
        if checked and not tex_config.is_tex_enabled():
            status_messages.show_error(
                "Enable TeX before using TeX rendering for this text."
            )
            self._sync_tex_button()
            return False
        result = self.context.text_rendering.apply(
            self.controller,
            {"usetex": checked},
        )
        if not self.context.messages.present(
            result,
            success=(
                "Text TeX rendering enabled."
                if checked
                else "Text TeX rendering disabled."
            ),
        ):
            self._sync_tex_button()
            return False
        return True

    def sync_from_controller(self) -> None:
        """Refresh controls from authoritative Controller state."""

        self._sync_tex_button()

    def dispose(self) -> None:
        """Disconnect callbacks and release resources owned by this object."""

        if self._disposed:
            return
        self._disposed = True
        self._lifecycle.close()


class LegendLocationSection(QWidget, EditorSection):
    """Provide the legend location section Qt widget."""

    PRESETS = (
        "best",
        "upper right",
        "upper left",
        "lower left",
        "lower right",
        "right",
        "center left",
        "center right",
        "lower center",
        "upper center",
        "center",
    )

    def __init__(self, controller, *, context, parent=None):
        super().__init__(parent)
        self.controller = controller
        self.context = context
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)

        self.visible_input = QCheckBox("Visible", self)
        self.legend_position_combobox = QComboBox(self)
        self.legend_position_combobox.addItems(self.PRESETS)
        self.legend_position_combobox.addItem("Custom coordinates")
        self.entry_scope_input = QComboBox(self)
        self.entry_scope_input.addItem("This Axes", "axes")
        self.entry_scope_input.addItem("Primary + right Y", "twin_pair")

        row = QHBoxLayout()
        self.legend_x_pos = QDoubleSpinBox(self)
        self.legend_y_pos = QDoubleSpinBox(self)
        for editor in (self.legend_x_pos, self.legend_y_pos):
            editor.setRange(-1e6, 1e6)
            editor.setDecimals(6)
            editor.setSingleStep(0.01)
        row.addWidget(QLabel("X:", self))
        row.addWidget(self.legend_x_pos)
        row.addWidget(QLabel("Y:", self))
        row.addWidget(self.legend_y_pos)

        ncols_row = QHBoxLayout()
        self.ncols_input = QSpinBox(self)
        self.ncols_input.setRange(1, 1000)
        ncols_row.addWidget(QLabel("Columns:", self))
        ncols_row.addWidget(self.ncols_input)

        self.layout.addWidget(self.visible_input)
        self.layout.addWidget(QLabel("Legend entries", self))
        self.layout.addWidget(self.entry_scope_input)
        self.layout.addWidget(self.legend_position_combobox)
        self.layout.addLayout(row)
        self.layout.addLayout(ncols_row)

        self.visible_input.toggled.connect(
            lambda value: self._apply("visible", bool(value))
        )
        self.ncols_input.valueChanged.connect(
            lambda value: self._apply("ncols", int(value))
        )
        self.entry_scope_input.currentIndexChanged.connect(
            lambda _index: self._apply(
                "entry_scope",
                self.entry_scope_input.currentData(),
            )
        )
        self.legend_position_combobox.currentTextChanged.connect(
            self.set_legend_position
        )
        self.legend_x_pos.valueChanged.connect(
            self.set_legend_xy_position
        )
        self.legend_y_pos.valueChanged.connect(
            self.set_legend_xy_position
        )
        self.sync_from_controller()

    def _ensure_target(self) -> None:
        try:
            self.controller.resolve_target()
            return
        except Exception:
            pass
        self.context.axes_commands.ensure_legend(
            self.controller.state.parent_id
        )

    def _apply(self, key: str, value):
        self._ensure_target()
        if key == "entry_scope":
            result = self.context.axes_layout.set_legend_scope(
                self.controller.state.parent_id,
                str(value),
            )
        else:
            result = self.controller.set_property(key, value)
        if not self.context.messages.present(
            result,
            success="Legend layout updated.",
        ):
            self.sync_from_controller()
            return False
        return True

    def _custom_selected(self) -> bool:
        return (
            self.legend_position_combobox.currentText()
            == "Custom coordinates"
        )

    def set_legend_position(self, *_args):
        """Set legend position."""

        custom = self._custom_selected()
        self.legend_x_pos.setEnabled(custom)
        self.legend_y_pos.setEnabled(custom)
        if custom:
            return self.set_legend_xy_position()
        return self._apply(
            "location",
            self.legend_position_combobox.currentText(),
        )

    def set_legend_xy_position(self, *_args):
        """Set legend xy position."""

        if not self._custom_selected():
            return True
        return self._apply(
            "location",
            (self.legend_x_pos.value(), self.legend_y_pos.value()),
        )

    def sync_from_controller(self) -> None:
        """Refresh controls from authoritative Controller state."""

        properties = self.controller.read_state().properties
        controls = (
            self.visible_input,
            self.legend_position_combobox,
            self.legend_x_pos,
            self.legend_y_pos,
            self.ncols_input,
            self.entry_scope_input,
        )
        blockers = [QSignalBlocker(control) for control in controls]
        try:
            self.visible_input.setChecked(
                bool(properties.get("visible", False))
            )
            self.ncols_input.setValue(int(properties.get("ncols", 1)))
            scope = str(properties.get("entry_scope", "axes"))
            self.entry_scope_input.setCurrentIndex(
                max(0, self.entry_scope_input.findData(scope))
            )
            axes = self.context.registry.get(self.controller.state.parent_id)
            subplot = axes.state.data.get("subplot", {})
            twin_available = False
            if subplot.get("layer") == "primary" and subplot.get("layout_id"):
                twin_available = any(
                    candidate.state.data.get("subplot", {}).get("layout_id")
                    == subplot.get("layout_id")
                    and candidate.state.data.get("subplot", {}).get("row")
                    == subplot.get("row")
                    and candidate.state.data.get("subplot", {}).get("column")
                    == subplot.get("column")
                    and candidate.state.data.get("subplot", {}).get("layer")
                    == "right_y"
                    for candidate in self.context.registry.query(
                        kind=ComponentKind.AXES
                    )
                )
            self.entry_scope_input.setEnabled(twin_available)
            location = properties.get("location", "best")
            if isinstance(location, (tuple, list)) and len(location) == 2:
                self.legend_position_combobox.setCurrentText(
                    "Custom coordinates"
                )
                self.legend_x_pos.setValue(float(location[0]))
                self.legend_y_pos.setValue(float(location[1]))
                custom = True
            else:
                text = str(location)
                if text not in self.PRESETS:
                    text = "best"
                self.legend_position_combobox.setCurrentText(text)
                custom = False
            self.legend_x_pos.setEnabled(custom)
            self.legend_y_pos.setEnabled(custom)
        finally:
            del blockers


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
        if palette.source == "custom":
            kind = "Custom palette"
        elif palette.source == "builtin":
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
        result = self.context.axes_commands.apply_palette(
            self.controller.component_id,
            palette,
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
