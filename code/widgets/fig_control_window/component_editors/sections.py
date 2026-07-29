"""Implement reusable appearance and text editor sections."""

from __future__ import annotations

from collections.abc import Callable, Iterable

from Qt_core import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QSignalBlocker,
    QSpinBox,
    QToolBox,
    QVBoxLayout,
    QWidget,
    Qt,
)

from code import status_messages, tex_config
from code.database import ColumnRef
from code.figuremodify.components import ComponentKind, ComponentMutation
from code.widgets.common_widget.min_widget.py_colorchoice_widgets import (
    choose_palette,
)

from .base import ComponentEditorBase
from .common import DebouncedTextBinding
from .inputs import DataReferenceInput
from .inspector import EditorSection


ApplyProperties = Callable[[dict[str, object]], object]
ApplyReferences = Callable[
    [object, ColumnRef, ColumnRef, str],
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
        layout.addWidget(self.data_choice_widget)
        self.x_data_input = self.data_choice_widget.x_data_input
        self.y_data_input = self.data_choice_widget.y_data_input
        self.data_choice_widget.refs_connect(
            self.x_data_change,
            self.y_data_change,
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

    def sync_from_controller(self) -> None:
        """Refresh controls from authoritative Controller state."""

        data = self.controller.read_state().data
        self.data_choice_widget.set_refs(
            ColumnRef.from_dict(data["x_ref"]),
            ColumnRef.from_dict(data["y_ref"]),
        )

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
        self.layout = QHBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.addWidget(QLabel("Render:", self))
        self.tex_render = QCheckBox("TeX", self)
        self.tex_render.setToolTip("Render this text with TeX")
        self.layout.addWidget(self.tex_render)
        self.layout.addStretch()
        self._listener = self._tex_state_changed
        tex_config.register_tex_state_listener(self._listener)
        self.tex_render.toggled.connect(self.set_tex_render)
        self._sync_tex_button()

    def _sync_tex_button(self):
        enabled = tex_config.is_tex_enabled()
        blocker = QSignalBlocker(self.tex_render)
        self.tex_render.setEnabled(enabled)
        self.tex_render.setChecked(
            enabled
            and bool(
                self.controller.read_state().properties.get(
                    "usetex",
                    False,
                )
            )
        )
        del blocker

    def _tex_state_changed(self, enabled: bool):
        if self._disposed:
            return
        if (
            not enabled
            and self.controller.read_state().properties.get("usetex")
        ):
            result = self.context.text_rendering.apply(
                self.controller,
                {"usetex": False},
            )
            self.context.messages.present(result)
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
        tex_config.unregister_tex_state_listener(self._listener)


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
        self.layout.addWidget(self.legend_position_combobox)
        self.layout.addLayout(row)
        self.layout.addLayout(ncols_row)

        self.visible_input.toggled.connect(
            lambda value: self._apply("visible", bool(value))
        )
        self.ncols_input.valueChanged.connect(
            lambda value: self._apply("ncols", int(value))
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
        )
        blockers = [QSignalBlocker(control) for control in controls]
        try:
            self.visible_input.setChecked(
                bool(properties.get("visible", False))
            )
            self.ncols_input.setValue(int(properties.get("ncols", 1)))
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
    """Provide the palette section Qt widget."""

    def __init__(self, controller, *, context, parent=None):
        super().__init__(parent)
        self.controller = controller
        self.context = context
        self.layout = QHBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.addWidget(QLabel("Palette:", self))
        self.button = QPushButton("Apply palette to axes", self)
        self.button.setAccessibleName("Apply color palette to axes")
        self.button.clicked.connect(self.choose_and_apply_palette)
        self.layout.addWidget(self.button)

    def choose_and_apply_palette(self):
        """Choose and apply palette."""

        cycle = self.context.axes_commands.cycle_state(
            self.controller.component_id
        )
        palette = choose_palette(
            self,
            self.context.color_library,
            cycle.active_palette,
        )
        if palette is None:
            return False
        controllers = self.context.registry.query(
            capabilities={"color", "data"},
            parent_id=self.controller.component_id,
            recursive=True,
        )
        result = self.context.axes_commands.apply_palette(
            self.controller.component_id,
            palette,
        )
        if not self.context.messages.present(
            result,
            success=(
                f"Applied {palette.display_name} to "
                f"{len(controllers)} chart objects."
            ),
        ):
            return False
        self.context.color_library.record_recent_many(
            palette.colors[index % len(palette.colors)]
            for index in range(len(controllers))
        )
        return True
