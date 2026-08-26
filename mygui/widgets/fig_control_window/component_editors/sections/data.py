"""Data-reference and source-binding Inspector sections."""

from __future__ import annotations

import json
from collections.abc import Callable

from PySide6.QtCore import QSignalBlocker, Qt
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from mygui import status_messages
from mygui.database import ColumnRef, ColumnType, TableChangeSet
from mygui.figuremodify.in_axes import embedded_image_data

from ..common import (
    format_number_sequence,
    parse_number_sequence,
)
from ..context import perform_editor_action
from ..inputs import DataReferenceInput, Field2DDataReferenceInput
from ..inspector import EditorSection
from ._types import ApplyReferences
from .property import PropertySection

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
        result = perform_editor_action(self.context,
            f"Change {self.controller.state.role.value.replace('_', ' ').title()} Data Source",
            lambda: self._apply_references(
                self.controller,
                x_ref,
                y_ref,
                self.data_choice_widget.preprocess_values(),
                axis,
            ),
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


class RawXYDataSection(QWidget, EditorSection):
    """Atomically edit the finite raw X/Y arrays owned by a generic Line."""

    DATA_KEYS = ("x", "y")

    def __init__(self, controller, *, context, parent=None):
        super().__init__(parent)
        self.controller = controller
        self.context = context
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.x_input = QPlainTextEdit(self)
        self.y_input = QPlainTextEdit(self)
        self.x_input.setPlaceholderText("X JSON array, for example [0, 1, 2]")
        self.y_input.setPlaceholderText("Y JSON array, for example [1, 4, 9]")
        self.apply_button = QPushButton("Apply X/Y data", self)
        layout.addWidget(QLabel("X values", self))
        layout.addWidget(self.x_input)
        layout.addWidget(QLabel("Y values", self))
        layout.addWidget(self.y_input)
        layout.addWidget(self.apply_button)
        self.apply_button.clicked.connect(self.apply_data)
        self.sync_from_controller()

    @staticmethod
    def _parse(text: str, axis: str) -> list[float]:
        value = json.loads(text or "[]")
        if not isinstance(value, list):
            raise ValueError(f"{axis} data must be a JSON array.")
        return value

    def apply_data(self) -> bool:
        """Submit both arrays as one Controller mutation."""

        try:
            x_values = self._parse(self.x_input.toPlainText(), "X")
            y_values = self._parse(self.y_input.toPlainText(), "Y")
            result = perform_editor_action(self.context,
                "Change Line Data",
                lambda: self.controller.set_xy_data(
                    x_values,
                    y_values,
                    persist=True,
                ),
            )
        except Exception as exc:
            status_messages.show_error(str(exc))
            self.sync_from_controller()
            return False
        if not self.context.messages.present(
            result,
            success="Line X/Y data updated.",
        ):
            self.sync_from_controller()
            return False
        return True

    def sync_from_controller(self) -> None:
        """Refresh both inputs from the authoritative Controller state."""

        data = self.controller.read_state().data
        blockers = [QSignalBlocker(self.x_input), QSignalBlocker(self.y_input)]
        try:
            self.x_input.setPlainText(json.dumps(data.get("x", [])))
            self.y_input.setPlainText(json.dumps(data.get("y", [])))
        finally:
            del blockers

    def dispose(self) -> None:
        """Disconnect the local action idempotently."""

        try:
            self.apply_button.clicked.disconnect(self.apply_data)
        except (RuntimeError, TypeError):
            pass


class ReferenceMarksDataSection(QWidget, EditorSection):
    """Edit the authoritative ordered Reflection Positions sequence."""

    DATA_KEYS = ("positions", "position_ref", "placement")

    def __init__(self, controller, *, context, parent=None):
        super().__init__(parent)
        self.controller = controller
        self.context = context
        self.repository = context.repository
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.positions_input = QLineEdit(self)
        self.positions_input.setPlaceholderText(
            "Comma or space separated reflection positions"
        )
        self.position_ref_input = QComboBox(self)
        self.apply_button = QPushButton("Apply data", self)
        self.placement_label = QLabel(self)
        self.placement_label.setWordWrap(True)
        self.convert_button = QPushButton("Convert to fixed position", self)
        layout.addWidget(self.positions_input)
        layout.addWidget(self.position_ref_input)
        layout.addWidget(self.apply_button)
        layout.addWidget(self.placement_label)
        layout.addWidget(self.convert_button)
        self.apply_button.clicked.connect(self.apply_data)
        self.convert_button.clicked.connect(self.convert_to_fixed)
        self.sync_from_controller()

    def _project_id(self) -> str | None:
        service = self.context.reference_marks
        return getattr(service, "project_id", None)

    def _populate_refs(self, current: ColumnRef | None) -> None:
        blocker = QSignalBlocker(self.position_ref_input)
        self.position_ref_input.clear()
        self.position_ref_input.addItem("(None)", None)
        project_id = self._project_id()
        if project_id is not None and project_id in self.repository.projects:
            for ref in self.repository.iter_column_refs(
                project_id, {ColumnType.NUMBER}
            ):
                self.position_ref_input.addItem(
                    self.repository.ref_label(ref), ref
                )
        target = 0
        if current is not None:
            for index in range(1, self.position_ref_input.count()):
                if self.position_ref_input.itemData(index, Qt.UserRole) == current:
                    target = index
                    break
        self.position_ref_input.setCurrentIndex(target)
        del blocker

    def apply_data(self) -> bool:
        """Submit positions and the Number-column ref through the Service."""

        try:
            positions = parse_number_sequence(self.positions_input.text())
            raw_ref = self.position_ref_input.currentData(Qt.UserRole)
            position_ref = raw_ref if isinstance(raw_ref, ColumnRef) else None
            service = self.context.reference_marks
            if service is None:
                raise RuntimeError("Reference Marks service is unavailable.")
            result = perform_editor_action(
                self.context,
                "Change Reflection Positions Data",
                lambda: service.update_data(
                    self.controller,
                    positions,
                    position_ref.to_dict() if position_ref is not None else None,
                ),
            )
        except Exception as exc:
            status_messages.show_error(str(exc))
            self.sync_from_controller()
            return False
        if not self.context.messages.present(
            result,
            success="Reflection positions updated.",
        ):
            self.sync_from_controller()
            return False
        return True

    def sync_from_controller(self) -> None:
        """Refresh from committed ComponentState data."""

        data = self.controller.read_state().data
        positions = data.get("positions", [])
        raw = data.get("position_ref")
        current = None
        if raw is not None:
            try:
                current = ColumnRef.from_dict(raw)
            except (TypeError, ValueError):
                current = None
        blocker = QSignalBlocker(self.positions_input)
        self.positions_input.setText(format_number_sequence(positions))
        del blocker
        self._populate_refs(current)
        self._sync_placement(data)

    def _ref_text(self, raw) -> str:
        if raw is None:
            return "(none)"
        try:
            ref = raw if isinstance(raw, ColumnRef) else ColumnRef.from_dict(raw)
        except (TypeError, ValueError):
            return "(invalid)"
        if self._project_id() is None:
            return str(ref.column_id)
        return self.repository.ref_label(ref)

    def _sync_placement(self, data: dict) -> None:
        placement = data.get("placement") or {"kind": "fixed"}
        automatic = placement.get("kind") == "between_table_ranges"
        if not automatic:
            self.placement_label.setText("Placement: fixed Axes baseline.")
            self.convert_button.setEnabled(False)
            return
        lower = self._ref_text(placement.get("lower_ref"))
        upper_refs = placement.get("upper_refs") or ()
        upper = ", ".join(self._ref_text(item) for item in upper_refs)
        self.placement_label.setText(
            "Automatic placement sources:\n"
            f"Lower range: {lower}\n"
            f"Upper ranges: {upper}"
        )
        self.convert_button.setEnabled(True)

    def convert_to_fixed(self) -> bool:
        """Store the current baseline and height as a fixed placement."""

        try:
            service = self.context.reference_marks
            if service is None:
                raise RuntimeError("Reference Marks service is unavailable.")
            result = perform_editor_action(
                self.context,
                "Convert Reflection Positions to Fixed",
                lambda: service.convert_to_fixed_placement(self.controller),
            )
        except Exception as exc:
            status_messages.show_error(str(exc))
            self.sync_from_controller()
            return False
        if not self.context.messages.present(
            result,
            success="Reflection placement converted to fixed.",
        ):
            self.sync_from_controller()
            return False
        self.sync_from_controller()
        return True

    def dispose(self) -> None:
        """Disconnect the local submit callback idempotently."""

        try:
            self.apply_button.clicked.disconnect(self.apply_data)
        except (RuntimeError, TypeError):
            pass
        try:
            self.convert_button.clicked.disconnect(self.convert_to_fixed)
        except (RuntimeError, TypeError):
            pass
class ScatterMappingSection(QWidget, EditorSection):
    """Edit optional Scatter color/size references through ChartDataService."""

    DATA_KEYS = ("color_ref", "size_ref")
    PROPERTY_KEYS = ("color_mapping", "size_mapping")

    def __init__(self, controller, *, context, parent=None):
        super().__init__(parent)
        self.controller = controller
        self.context = context
        self.repository = context.repository
        self._disposed = False
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        color_row = QHBoxLayout()
        size_row = QHBoxLayout()
        self.color_input = QComboBox(self)
        self.size_input = QComboBox(self)
        color_row.addWidget(QLabel("Color data:", self))
        color_row.addWidget(self.color_input)
        size_row.addWidget(QLabel("Size data:", self))
        size_row.addWidget(self.size_input)
        layout.addLayout(color_row)
        layout.addLayout(size_row)
        self._mapping_properties = PropertySection(
            controller,
            context=context,
            property_keys=self.PROPERTY_KEYS,
            apply_properties=self._apply_property,
            parent=self,
        )
        layout.addWidget(self._mapping_properties)
        self.repository.transaction_committed.connect(self._repository_changed)
        self.color_input.currentIndexChanged.connect(self._refs_changed)
        self.size_input.currentIndexChanged.connect(self._refs_changed)
        self.sync_from_controller()

    def _project_id(self) -> str | None:
        data = self.controller.read_state().data
        value = data.get("x_ref")
        return str(value.get("project_id")) if isinstance(value, dict) else None

    @staticmethod
    def _current_ref(combo: QComboBox) -> ColumnRef | None:
        value = combo.currentData(Qt.UserRole)
        return value if isinstance(value, ColumnRef) else None

    def _populate(self, combo: QComboBox, current: ColumnRef | None) -> None:
        blocker = QSignalBlocker(combo)
        combo.clear()
        combo.addItem("None", None)
        project_id = self._project_id()
        if project_id is not None and project_id in self.repository.projects:
            for ref in self.repository.iter_column_refs(
                project_id,
                {ColumnType.NUMBER},
            ):
                combo.addItem(self.repository.ref_label(ref), ref)
        target = 0
        if current is not None:
            for index in range(1, combo.count()):
                if combo.itemData(index, Qt.UserRole) == current:
                    target = index
                    break
        combo.setCurrentIndex(target)
        del blocker

    def _apply(self, *, property_patch=None) -> object:
        properties = self.controller.read_state().properties
        color_mapping = properties["color_mapping"]
        size_mapping = properties["size_mapping"]
        for key, value in (property_patch or {}).items():
            if key == "color_mapping":
                color_mapping = value
            elif key == "size_mapping":
                size_mapping = value
        return self.context.chart_data.configure_scatter_mapping(
            self.controller,
            color_ref=self._current_ref(self.color_input),
            size_ref=self._current_ref(self.size_input),
            color_mapping=color_mapping,
            size_mapping=size_mapping,
        )

    def _apply_property(self, properties):
        return self._apply(property_patch=properties)

    def _refs_changed(self, *_args) -> bool:
        if self._disposed:
            return False
        result = perform_editor_action(self.context,
            "Change Scatter Mapping Sources",
            self._apply,
        )
        if not self.context.messages.present(
            result,
            success="Scatter mapping updated.",
        ):
            self.sync_from_controller()
            return False
        return True

    def _repository_changed(self, changes: TableChangeSet) -> None:
        if self._disposed or changes.project_id != self._project_id():
            return
        if changes.structure_changed or changes.metadata_changed:
            self.sync_from_controller()

    @staticmethod
    def _ref(value) -> ColumnRef | None:
        return ColumnRef.from_dict(value) if isinstance(value, dict) else None

    def sync_from_controller(self) -> None:
        """Refresh refs and mapping specs from Controller state."""

        data = self.controller.read_state().data
        self._populate(self.color_input, self._ref(data.get("color_ref")))
        self._populate(self.size_input, self._ref(data.get("size_ref")))
        self._mapping_properties.sync_from_controller()

    def dispose(self) -> None:
        """Detach repository and local Qt callbacks idempotently."""

        if self._disposed:
            return
        self._disposed = True
        try:
            self.repository.transaction_committed.disconnect(
                self._repository_changed
            )
        except (RuntimeError, TypeError):
            pass
        for combo in (self.color_input, self.size_input):
            try:
                combo.currentIndexChanged.disconnect(self._refs_changed)
            except (RuntimeError, TypeError):
                pass
        self._mapping_properties.dispose()


class Field2DDataSection(QWidget, EditorSection):
    """Submit X/Y/Z column references as one FIELD_2D transaction."""

    def __init__(self, controller, *, context, parent=None):
        super().__init__(parent)
        self.controller = controller
        self.context = context
        data = controller.read_state().data
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.data_choice_widget = Field2DDataReferenceInput(
            context.repository,
            ColumnRef.from_dict(data["x_ref"]).project_id,
            parent=self,
        )
        self.data_choice_widget.set_refs(
            ColumnRef.from_dict(data["x_ref"]),
            ColumnRef.from_dict(data["y_ref"]),
            ColumnRef.from_dict(data["z_ref"]),
        )
        layout.addWidget(self.data_choice_widget)
        self.data_choice_widget.refs_connect(self._refs_changed)

    def _refs_changed(self, *_args) -> bool:
        x_ref = self.data_choice_widget.get_x_ref()
        y_ref = self.data_choice_widget.get_y_ref()
        z_ref = self.data_choice_widget.get_z_ref()
        if x_ref is None or y_ref is None or z_ref is None:
            return False
        result = perform_editor_action(
            self.context,
            (
                "Change "
                f"{self.controller.state.role.value.replace('_', ' ').title()} "
                "Data Source"
            ),
            lambda: self.context.field_2d.set_refs(
                self.controller,
                x_ref,
                y_ref,
                z_ref,
            ),
        )
        if not self.context.messages.present(
            result,
            success="FIELD_2D data source updated.",
        ):
            self.sync_from_controller()
            return False
        return True

    def sync_from_controller(self) -> None:
        data = self.controller.read_state().data
        self.data_choice_widget.set_refs(
            ColumnRef.from_dict(data["x_ref"]),
            ColumnRef.from_dict(data["y_ref"]),
            ColumnRef.from_dict(data["z_ref"]),
        )

    def dispose(self) -> None:
        self.data_choice_widget.dispose()


class ColorbarSourceSection(QWidget, EditorSection):
    """Display the immutable stable source relationship of a Colorbar."""

    def __init__(self, controller, *, context, parent=None):
        super().__init__(parent)
        self.controller = controller
        self.context = context
        self._disposed = False
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.summary_label = QLabel(self)
        self.summary_label.setWordWrap(True)
        self.summary_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        layout.addWidget(self.summary_label)
        self._unsubscribe = context.registry.subscribe(self._component_event)
        self.sync_from_controller()

    def _component_event(self, event) -> None:
        if self._disposed:
            return
        source_id = self.controller.state.data.get("source_component_id")
        if event.component_id == source_id:
            self.sync_from_controller()

    def sync_from_controller(self) -> None:
        """Refresh the source label without creating a second source state."""

        source_id = str(
            self.controller.state.data.get("source_component_id", "")
        )
        if not source_id or source_id not in self.context.registry:
            self.summary_label.setText("Source unavailable")
            return
        source = self.context.registry.get(source_id).state
        label = str(source.properties.get("label", "")).strip()
        role = source.role.value.replace("_", " ").title()
        preview = label or f"{role} {source_id[:8]}"
        self.summary_label.setText(
            f"{preview}\nStable component id: {source_id}\n"
            "The source owns the colormap, norm, limits, and scalar data."
        )

    def dispose(self) -> None:
        """Detach the Registry subscription idempotently."""

        if self._disposed:
            return
        self._disposed = True
        self._unsubscribe()
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
            result = perform_editor_action(self.context,
                "Replace Inset Image",
                lambda: self.context.in_axes.replace_image(
                    self.controller,
                    data,
                ),
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
