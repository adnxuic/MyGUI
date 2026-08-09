"""Host Matplotlib figures and register their editable components."""

from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Optional
from Qt_core import *

from code.widgets.fig_control_window.figure_inspector import (
    FigureInspectorPanel,
)
from code.widgets.fig_control_window.component_editors import (
    ComponentEditorManager,
    EditorContext,
    EditorRegistry,
    MessagePresenter,
    register_production_profiles,
)
from code.figuremodify.component_services import (
    AxesCommandService,
    ChartDataService,
    ComponentDeletionService,
    ComponentDependencySnapshot,
    ComponentDependencyService,
    DeleteReason,
    DeletionRequest,
    FitService,
    FunctionCurveService,
    InterpolationService,
    TextRenderService,
)
from code.widgets.figure_canvas.deletion_coordinator import DeletionCoordinator
from code.figuremodify.components import (
    AxesController,
    ComponentEvent,
    ComponentEventKind,
    ComponentKind,
    ComponentRegistry,
    ComponentRole,
    ComponentState,
    DataPlotController,
    DeletionPolicy,
    FigureController,
    FitCurveController,
    FunctionCurveController,
    InterpolationController,
    ImageInAxesController,
    LineController,
    ScatterController,
    TextController,
    UpdateImpact,
    ZoomInAxesController,
    create_semantic_children,
    decode_in_axes_image,
)
from code.figuremodify.components.serialization import (
    deterministic_component_id,
    migrate_v8_figure_to_v9,
    normalize_v9_figure,
    validate_v9_figure,
)
from code.figuremodify.axes_layout import AxesLayoutSpec
from code.figuremodify.axes_layout_service import AxesLayoutService
from code.figuremodify.in_axes import (
    ImageInAxesCreateSpec,
    InAxesCreateSpec,
    InAxesService,
    ZoomInAxesCreateSpec,
)

from code import tex_config
from code import status_messages
from code.database import (
    ColumnRef,
    ColumnType,
    DataPreprocessSpec,
    TableChangeSet,
    TableRepository,
    resolve_preprocessed_pair,
    validate_component_name,
)
from code.database.table_document import new_id
from code.database.interpolate_func import DEFAULT_INTERPOLATION_SAMPLES, interpolate_curve
from code.database.safe_expression import evaluate_curve_expression
from code.widgets.common_widget.min_widget.color_library import ColorLibrary
from code.figuremodify.style_base.color_models import (
    ColorCycleState,
    ColorSelection,
    normalize_color,
)
from code.figuremodify.style_base.creation_defaults import (
    ComponentCreationDefaults,
    resolve_component_creation_defaults,
)

import matplotlib as mpl
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.backends.backend_qtagg import (
    NavigationToolbar2QT as NavigationToolbar,
)
from matplotlib.figure import Figure
from matplotlib.axes import Axes
from matplotlib import style as mpl_style

import numpy as np
mpl.use("QtAgg")


@dataclass(frozen=True, slots=True)
class ChartBatchCreationResult:
    """Transient result returned after one atomic chart creation batch."""

    component_ids: tuple[str, ...]
    artists: tuple[Any, ...]
    colors: tuple[str, ...]
    excluded_counts: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class _PreparedChartSeries:
    x_ref: ColumnRef
    y_ref: ColumnRef
    x: Any
    y: Any
    label: str
    color: str
    excluded_count: int


class PyFigureCanvas(QWidget):
    """Provide the py figure canvas Qt widget."""

    componentSelectionChanged = Signal(str)

    def __init__(self, parent=None, width=4, height=3, dpi=200, style=None,
                 repository: TableRepository | None = None, project_id: str | None = None,
                 project_name: str | None = None, project_path: str | None = None,
                 color_library: ColorLibrary | None = None,
                 component_tree: dict[str, Any] | None = None):
        super().__init__(parent)
        self.figure_window = parent if hasattr(parent, "current_canva") else None
        if repository is None or project_id is None:
            raise ValueError("PyFigureCanvas requires a repository and project id.")
        self.repository = repository
        self.project_id = project_id
        self.style = style
        self.project_name = project_name or ""
        self.project_table_name = self.project_name
        self.project_path = project_path
        self._disposed = False
        self._restoring_component_tree_now = False
        self._selection_repair_pending = False
        self.color_library = color_library or ColorLibrary(parent=self)
        if isinstance(component_tree, dict):
            axes_records = [
                item
                for item in component_tree.get("components", ())
                if isinstance(item, dict) and item.get("kind") == "axes"
            ]
            if axes_records and "layout_group" in axes_records[0].get(
                "data", {}
            ).get("subplot", {}):
                component_tree = migrate_v8_figure_to_v9(
                    component_tree,
                    project_id,
                )
        self._component_id_overrides = self._component_paths_from_tree(
            component_tree
        )
        self._allocated_component_ids: set[str] = set()
        self._restore_component_tree = (
            deepcopy(component_tree)
            if isinstance(component_tree, dict)
            else None
        )
        with mpl_style.context(style):
            self.fig = Figure(figsize=(width, height), dpi=dpi)
        # QtAgg scales ``Figure.dpi`` to the active screen's device pixel
        # ratio.  Keep the user/project DPI separate so that moving the
        # window between screens cannot change exports or project files.
        self._document_dpi = float(self.fig.dpi)
        self.component_registry = ComponentRegistry()
        self.editor_registry = EditorRegistry()
        register_production_profiles(self.editor_registry)
        self.editor_registry.validate_production_profiles()
        self.component_editor_registry = self.editor_registry
        self.axes_commands = AxesCommandService(self.component_registry)
        self.axes_layout_service = AxesLayoutService(self)
        self.function_curve_service = FunctionCurveService(
            self.component_registry
        )
        self.chart_data_service = ChartDataService(
            self.repository,
            self.component_registry,
        )
        self.interpolation_service = InterpolationService(
            self.repository,
            self.component_registry,
        )
        self.chart_data_service.interpolation_service = (
            self.interpolation_service
        )
        self.fit_service = FitService(
            self.repository,
            self.component_registry,
        )
        self.text_render_service = TextRenderService(
            self.component_registry
        )
        self.in_axes_service = InAxesService(
            self.component_registry,
            warning_callback=status_messages.show_warning,
        )
        self.message_presenter = MessagePresenter(
            self.component_registry
        )
        self.component_editor_manager = ComponentEditorManager(
            self.component_registry,
            self.editor_registry,
        )
        self.deletion_service = ComponentDeletionService(
            self.component_registry
        )
        self.deletion_coordinator = DeletionCoordinator(self)
        self.dependency_service = ComponentDependencyService(
            self.component_registry,
            restore_state=self._restore_component_state,
            deletion_service=self.deletion_service,
        )
        self.editor_context = EditorContext(
            registry=self.component_registry,
            color_library=self.color_library,
            messages=self.message_presenter,
            editor_manager=self.component_editor_manager,
            axes_commands=self.axes_commands,
            axes_layout=self.axes_layout_service,
            function_curves=self.function_curve_service,
            chart_data=self.chart_data_service,
            interpolation=self.interpolation_service,
            fitting=self.fit_service,
            text_rendering=self.text_render_service,
            in_axes=self.in_axes_service,
            dependency_service=self.dependency_service,
            delete_command=self.delete_components,
        )
        self.root_component_id = self._component_id("figure")
        source_root = self._source_component_state(self.root_component_id)
        if source_root is None:
            root_properties = FigureController.default_properties()
            root_properties.update({
                "name": self.project_name,
                "style": str(self.style or "default"),
                "dpi": self._document_dpi,
                "size_inches": [
                    float(value) for value in self.fig.get_size_inches()
                ],
            })
            root_state = ComponentState(
                id=self.root_component_id,
                kind=ComponentKind.FIGURE,
                role=ComponentRole.FIGURE,
                order=0,
                selector={"scope": "figure"},
                properties=root_properties,
                data={"layouts": []},
            )
        else:
            root_state = source_root
        self.component_registry.register(
            FigureController(root_state),
            target=self.fig,
        )
        self._axes_component_ids: dict[Axes, str] = {}

        self.figure_inspector: Optional[FigureInspectorPanel] = None

        self.current_axes_component_id: str | None = None
        self.current_component_id: str | None = None
        self._selection_unsubscribe = self.component_registry.subscribe(
            self._component_selection_event,
            kinds=(ComponentEventKind.REMOVED,),
        )
        self.repository.transaction_committed.connect(self._table_changed)

        self.canva = FigureCanvasQTAgg(self.fig)
        size_inches = self.fig.get_size_inches()
        self.canva.setFixedSize(
            round(float(size_inches[0]) * self._document_dpi),
            round(float(size_inches[1]) * self._document_dpi),
        )
        root_controller = self.component_registry.get(
            self.root_component_id
        )
        if isinstance(root_controller, FigureController):
            root_controller.set_property_callback(
                self._sync_figure_property
            )

        # Add scroll area
        self.scroArea = QScrollArea()
        self.scroArea.setWidget(self.canva)
        self.scroArea.setAlignment(Qt.AlignCenter)
        self.scroArea.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)  # Set scroll bar visibility policy
        self.scroArea.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)  # Set scroll bar visibility policy

        layout = QVBoxLayout()

        toolbox = NavigationToolbar(self.canva, self)

        layout.addWidget(toolbox)
        layout.addWidget(self.scroArea)

        self.setLayout(layout)

    @property
    def current_axes(self) -> Axes | None:
        """Resolve the selected Axes from the Registry, never a mirror."""

        component_id = self.current_axes_component_id
        if component_id is None or component_id not in self.component_registry:
            return None
        target = self.component_registry.resolve_target(component_id)
        return target if isinstance(target, Axes) else None

    @property
    def current_axes_controller(self) -> AxesController | None:
        """Return the current axes controller."""

        component_id = self.current_axes_component_id
        if component_id is None or component_id not in self.component_registry:
            return None
        controller = self.component_registry.get(component_id)
        return controller if isinstance(controller, AxesController) else None

    @property
    def document_dpi(self) -> float:
        """The project/export DPI, independent of the screen pixel ratio."""
        try:
            state = self.component_registry.get(
                self.root_component_id
            ).read_state()
            return float(state.properties["dpi"])
        except Exception:
            return self._document_dpi

    def _sync_figure_property(self, key: str, value: Any) -> None:
        """Keep host metadata and the Qt canvas aligned with Figure state."""

        if key == "name":
            name = validate_component_name(value, "Project name")
            existing = self.repository.project_by_name(
                name,
                required=False,
            )
            if existing is not None and existing.id != self.project_id:
                raise ValueError(f"Project already exists: {name}")
            project = self.repository.project(self.project_id)
            if project.name != name:
                project.name = name
                self.repository.record_change(
                    TableChangeSet(
                        self.project_id,
                        metadata_changed=True,
                        reason="rename-project",
                    )
                )
            self.project_name = name
            self.project_table_name = name
            owner = self.parent()
            while owner is not None and not hasattr(owner, "tabwindow"):
                owner = owner.parent()
            tabwindow = getattr(owner, "tabwindow", None)
            if tabwindow is not None:
                index = tabwindow.indexOf(self)
                if index >= 0:
                    tabwindow.setTabText(index, name)
            return
        if key == "style":
            self.style = str(value)
            return
        if key == "dpi":
            self._document_dpi = float(value)
        if key in {"dpi", "size_inches"}:
            size_inches = self.fig.get_size_inches()
            self.canva.setFixedSize(
                round(float(size_inches[0]) * self._document_dpi),
                round(float(size_inches[1]) * self._document_dpi),
            )

    @property
    def component_style(self) -> str:
        """Return the style mapping for a component."""

        try:
            state = self.component_registry.get(
                self.root_component_id
            ).read_state()
            return str(state.properties["style"] or "default")
        except Exception:
            return str(self.style or "default")

    def component_creation_defaults(self) -> ComponentCreationDefaults:
        """Resolve creation defaults from the current Figure style."""

        return resolve_component_creation_defaults(self.component_style)

    def creation_color_cycle(self) -> ColorCycleState:
        """Preview the active user palette or current style color cycle."""

        axes_id = self.current_axes_component_id
        if axes_id is None:
            raise ValueError("Select an axes before choosing a chart color.")
        defaults = self.component_creation_defaults()
        return self.axes_commands.preview_color_cycle(
            axes_id,
            defaults.chart_palette,
            self._next_axes_color_index(axes_id),
        )

    def _next_axes_color_index(self, axes_id: str) -> int:
        """Return the per-Axes preview cursor without consuming it."""

        return sum(
            controller.state.kind in {
                ComponentKind.LINE,
                ComponentKind.SCATTER,
            }
            for controller in self.component_registry.children(axes_id)
        )

    def _component_id(self, semantic_path: str) -> str:
        candidate = self._component_id_overrides.get(
            semantic_path,
            deterministic_component_id(self.project_id, semantic_path),
        )
        while (
            candidate in self._allocated_component_ids
            or (
                hasattr(self, "component_registry")
                and candidate in self.component_registry
            )
        ):
            candidate = new_id()
        self._allocated_component_ids.add(candidate)
        return candidate

    @staticmethod
    def _component_paths_from_tree(
        component_tree: dict[str, Any] | None,
    ) -> dict[str, str]:
        """Map fixed semantic paths to IDs from a validated v6 tree."""

        if not isinstance(component_tree, dict):
            return {}
        raw_components = component_tree.get("components")
        root_id = component_tree.get("root_component_id")
        if not isinstance(raw_components, list) or not isinstance(root_id, str):
            return {}
        components = [
            item for item in raw_components if isinstance(item, dict)
        ]
        children: dict[str | None, list[dict[str, Any]]] = {}
        for component in components:
            children.setdefault(component.get("parent_id"), []).append(component)

        paths: dict[str, str] = {"figure": root_id}
        axes_components = sorted(
            (
                item
                for item in components
                if item.get("kind") == ComponentKind.AXES.value
                and item.get("parent_id") == root_id
            ),
            key=lambda item: int(item.get("selector", {}).get("index", 0)),
        )
        for fallback_index, axes_component in enumerate(axes_components):
            selector = axes_component.get("selector", {})
            axes_index = int(selector.get("index", fallback_index))
            axes_id = axes_component.get("id")
            if not isinstance(axes_id, str):
                continue
            axes_path = f"figure/axes/{axes_index}"
            paths[axes_path] = axes_id
            direct = children.get(axes_id, [])
            axis_ids: dict[str, str] = {}
            for component in direct:
                component_id = component.get("id")
                kind = component.get("kind")
                role = component.get("role")
                component_selector = component.get("selector", {})
                if not isinstance(component_id, str):
                    continue
                if kind == ComponentKind.AXIS.value:
                    axis_name = component_selector.get("axis")
                    if axis_name in {"x", "y"}:
                        axis_ids[axis_name] = component_id
                        paths[f"{axes_path}/axis/{axis_name}"] = component_id
                elif kind == ComponentKind.SPINE.value:
                    name = component_selector.get("name")
                    if name in {"left", "right", "top", "bottom"}:
                        paths[f"{axes_path}/spine/{name}"] = component_id
                elif role == ComponentRole.TITLE.value:
                    paths[f"{axes_path}/title"] = component_id
                elif kind == ComponentKind.LEGEND.value:
                    paths[f"{axes_path}/legend"] = component_id

            for axis_name, axis_id in axis_ids.items():
                for component in children.get(axis_id, []):
                    component_id = component.get("id")
                    kind = component.get("kind")
                    role = component.get("role")
                    selector = component.get("selector", {})
                    if not isinstance(component_id, str):
                        continue
                    if role == f"{axis_name}_label":
                        paths[f"{axes_path}/axis/{axis_name}/label"] = component_id
                        continue
                    level = selector.get("level")
                    if level not in {"major", "minor"}:
                        continue
                    if kind == ComponentKind.TICK_GROUP.value:
                        tick_path = (
                            f"{axes_path}/axis/{axis_name}/tick/{level}"
                        )
                        paths[tick_path] = component_id
                        label = next(
                            (
                                item
                                for item in children.get(component_id, [])
                                if item.get("kind")
                                == ComponentKind.TICK_LABEL_GROUP.value
                            ),
                            None,
                        )
                        if label is not None and isinstance(label.get("id"), str):
                            paths[f"{tick_path}/label"] = label["id"]
                    elif kind == ComponentKind.GRID.value:
                        paths[
                            f"{axes_path}/axis/{axis_name}/grid/{level}"
                        ] = component_id
        return paths

    def _source_component_state(
        self, component_id: str
    ) -> ComponentState | None:
        tree = self._restore_component_tree
        if not isinstance(tree, dict):
            return None
        for raw_state in tree.get("components", []):
            if (
                isinstance(raw_state, dict)
                and raw_state.get("id") == component_id
            ):
                return ComponentState.from_dict(raw_state)
        return None

    def _axes_controller_map(self, axes_id: str) -> dict[str, Any]:
        controllers: dict[str, Any] = {
            "axes": self.component_registry.get(axes_id),
        }
        for controller in self.component_registry.descendants(axes_id):
            state = controller.state
            selector = state.selector
            if state.kind is ComponentKind.AXIS:
                controllers[f"axis:{selector.get('axis')}"] = controller
            elif state.kind is ComponentKind.SPINE:
                controllers[f"spine:{selector.get('name')}"] = controller
            elif state.kind is ComponentKind.TEXT:
                if state.role is ComponentRole.X_LABEL:
                    controllers["label:x"] = controller
                elif state.role is ComponentRole.Y_LABEL:
                    controllers["label:y"] = controller
                elif state.role is ComponentRole.TITLE:
                    controllers["title"] = controller
            elif state.kind is ComponentKind.LEGEND:
                controllers["legend"] = controller
        return controllers

    def _register_axes_components(
        self,
        axe: Axes,
        axes_index: int,
        *,
        subplot: dict[str, Any],
    ) -> tuple[str, dict[str, Any]]:
        axes_path = f"figure/axes/{axes_index}"
        axes_id = self._component_id(axes_path)
        axes_state = ComponentState(
            id=axes_id,
            kind=ComponentKind.AXES,
            role=ComponentRole.AXES,
            parent_id=self.root_component_id,
            order=axes_index,
            selector={"index": axes_index},
            properties={
                "xlim": [float(value) for value in axe.get_xlim()],
                "ylim": [float(value) for value in axe.get_ylim()],
                "xscale": axe.get_xscale(),
                "yscale": axe.get_yscale(),
                "autoscalex_on": bool(axe.get_autoscalex_on()),
                "autoscaley_on": bool(axe.get_autoscaley_on()),
                "color_cycle": None,
            },
            data={"subplot": deepcopy(subplot)},
        )
        axes_controller = AxesController(axes_state, target=axe)
        axes_controller.sync_from_target(strict=True)
        self.component_registry.register(
            axes_controller,
            target=axe,
        )
        create_semantic_children(
            self.component_registry,
            axes_id,
            axe,
            path=axes_path,
            id_factory=self._component_id,
        )
        self._axes_component_ids[axe] = axes_id
        return axes_id, self._axes_controller_map(axes_id)

    def _register_chart_controller(
        self,
        controller_type,
        component_id: str,
        role: ComponentRole,
        artist,
        order: int,
        properties: dict[str, Any],
        data: dict[str, Any],
    ):
        axes_id = self._axes_component_ids[self.current_axes]
        state = ComponentState(
            id=component_id,
            kind=(
                ComponentKind.SCATTER
                if role is ComponentRole.SCATTER
                else ComponentKind.LINE
            ),
            role=role,
            parent_id=axes_id,
            order=int(order),
            selector={"object_id": component_id},
            properties=properties,
            data=data,
        )
        controller = controller_type(state, target=artist)
        controller.sync_from_target()
        self.component_registry.register(controller, target=artist)
        artist.set_gid(component_id)
        self.component_registry.request_update(
            artist.axes,
            UpdateImpact.AUTOSCALE,
        )
        return controller

    def _register_text_controller(
        self,
        component_id: str,
        text_artist,
        *,
        parent_id: str,
        order: int,
        scope: str,
    ):
        state = ComponentState(
            id=component_id,
            kind=ComponentKind.TEXT,
            role=ComponentRole.TEXT,
            parent_id=parent_id,
            order=int(order),
            selector={"object_id": component_id, "scope": scope},
            properties={
                "position": [
                    float(value) for value in text_artist.get_position()
                ],
                "text": text_artist.get_text(),
                "fontfamily": list(text_artist.get_fontfamily()),
                "fontsize": float(text_artist.get_fontsize()),
                "usetex": bool(text_artist.get_usetex()),
                "visible": bool(text_artist.get_visible()),
            },
        )
        controller = TextController(state, target=text_artist)
        controller.sync_from_target()
        self.component_registry.register(controller, target=text_artist)
        text_artist.set_gid(component_id)
        return controller

    def set_figure_inspector(
        self,
        figure_inspector: FigureInspectorPanel,
    ) -> None:
        """Set figure inspector."""

        self.figure_inspector = figure_inspector
        self.select_component(self.root_component_id)

    def select_component(self, component_id: str) -> bool:
        """Select one Component and show exactly its own Inspector."""

        component_id = str(component_id)
        if component_id not in self.component_registry:
            return False
        previous_component_id = self.current_component_id
        previous_axes_id = self.current_axes_component_id
        inspector_existed = (
            self.figure_inspector is not None
            and self.figure_inspector.inspector(component_id) is not None
        )
        try:
            if (
                self.figure_inspector is not None
                and not self.figure_inspector.show_component(component_id)
            ):
                raise RuntimeError(
                    f"Inspector for component {component_id!r} is unavailable."
                )
        except Exception as exc:
            self.current_component_id = previous_component_id
            self.current_axes_component_id = previous_axes_id
            if self.figure_inspector is not None:
                if not inspector_existed:
                    self.figure_inspector.remove_component_inspector(
                        component_id
                    )
                if (
                    previous_component_id is not None
                    and previous_component_id in self.component_registry
                ):
                    try:
                        self.figure_inspector.show_component(
                            previous_component_id
                        )
                    except Exception:
                        pass
            status_messages.show_error(str(exc))
            return False
        axes_id = self._axes_ancestor_id(component_id)
        if axes_id is not None:
            self.current_axes_component_id = axes_id
        self.current_component_id = component_id
        if component_id != previous_component_id:
            self.componentSelectionChanged.emit(component_id)
        return True

    def _axes_ancestor_id(self, component_id: str) -> str | None:
        controller = self.component_registry.ancestor(
            component_id,
            kind=ComponentKind.AXES,
        )
        return controller.component_id if controller is not None else None

    def _component_selection_event(self, event: ComponentEvent) -> None:
        if event.component_id != self.current_component_id:
            return
        self.current_component_id = None
        if self._selection_repair_pending:
            return
        self._selection_repair_pending = True
        QTimer.singleShot(0, self._repair_component_selection)

    def _repair_component_selection(self) -> None:
        self._selection_repair_pending = False
        if self._disposed:
            return
        if (
            self.current_component_id is not None
            and self.current_component_id in self.component_registry
        ):
            return
        target = (
            self.current_axes_component_id
            if self.current_axes_component_id in self.component_registry
            else self.root_component_id
        )
        if target in self.component_registry:
            self.select_component(target)

    def update_current_axes(self, component) -> None:
        """Select an Axes by Controller/ID/artist and show its Inspector."""

        if isinstance(component, AxesController):
            controller = component
        elif isinstance(component, str):
            controller = self.component_registry.get(component)
        elif isinstance(component, Axes):
            controller = self.component_registry.get(
                self._axes_component_ids[component]
            )
        else:
            raise TypeError("Current axes must be an Axes Controller, ID, or artist.")
        if not isinstance(controller, AxesController):
            raise TypeError("The selected component is not an Axes.")
        self.select_component(controller.component_id)

    def set_current_axes_by_index(self, axes_index: int):
        """Set current axes by index."""

        try:
            controller = self.component_registry.find_one(
                kind=ComponentKind.AXES,
                selector={"index": int(axes_index)},
            )
        except Exception as exc:
            raise IndexError(f"Invalid axes index: {axes_index}") from exc
        self.update_current_axes(controller)

    def delete_axes(self, axes_id: str) -> bool:
        """Delete an Axes through the unified deletion coordinator."""

        return self.delete_components(
            (axes_id,),
            anchor_id=axes_id,
            reason=DeleteReason.AXES,
            role_label="axes",
        )

    def redraw(self):
        """Schedule a coalesced canvas redraw."""

        self.fig.canvas.draw()

    def cancel_pending_draw(self):
        """Cancel a queued redraw that has not reached the canvas yet."""

        if hasattr(self.canva, "_draw_pending"):
            self.canva._draw_pending = False

    def dispose(self) -> None:
        """Idempotently detach project callbacks and editor resources."""

        if self._disposed:
            return
        self._disposed = True
        self.cancel_pending_draw()
        try:
            self.repository.transaction_committed.disconnect(self._table_changed)
        except (RuntimeError, TypeError):
            pass
        if self._selection_unsubscribe is not None:
            self._selection_unsubscribe()
            self._selection_unsubscribe = None
        self.message_presenter.close()
        self.component_editor_manager.close()
        self.axes_layout_service.dispose()
        self.in_axes_service.dispose()

    def closeEvent(self, event):
        """Handle Qt close events and release owned resources."""

        self.dispose()
        super().closeEvent(event)

    def _table_changed(self, changes: TableChangeSet):
        if changes.project_id != self.project_id:
            return
        results = self.chart_data_service.refresh_affected(
            changes.changed_columns
        )
        failures = [result for result in results if not result.ok]
        warnings = [
            result
            for result in results
            if result.ok and result.notices
        ]
        if failures:
            self.message_presenter.present(failures[0])
        elif warnings:
            self.message_presenter.present(warnings[0])

    def create_component_editor(self, component_id: str, *, parent=None):
        """Create a schema-driven runtime editor with the shared color library."""

        return self.component_editor_manager.create(
            component_id,
            context=self.editor_context,
            parent=parent,
        )

    def _claim_color_order(self, preferred: int | None = None) -> int:
        if preferred is not None:
            return max(0, int(preferred))
        if self.current_axes_component_id is None:
            raise ValueError("Select an axes before adding a chart.")
        orders = [
            controller.state.order
            for controller in self.component_registry.query()
            if controller.state.kind in {
                ComponentKind.LINE,
                ComponentKind.SCATTER,
            }
        ]
        return max(orders, default=-1) + 1

    def _next_child_order(
        self,
        parent_id: str,
        *,
        kind: ComponentKind | None = None,
    ) -> int:
        orders = [
            controller.state.order
            for controller in self.component_registry.query(
                parent_id=parent_id
            )
            if kind is None or controller.state.kind is kind
        ]
        return max(orders, default=-1) + 1

    def _select_created_component(self, controller) -> None:
        """Lazily materialize and select a newly committed component."""

        if self._restoring_component_tree_now or self.figure_inspector is None:
            return
        if not self.select_component(controller.component_id):
            raise RuntimeError(
                f"Could not open Inspector for {controller.component_id!r}."
            )

    @staticmethod
    def _remove_created_artist(artist) -> None:
        try:
            artist.remove()
        except (RuntimeError, ValueError):
            pass

    def _prepare_created_component(self, controller, transaction) -> None:
        """Verify lazy Inspector construction before Registry publication."""

        if self._restoring_component_tree_now or self.figure_inspector is None:
            return
        previous_component_id = self.current_component_id
        if not self.figure_inspector.show_component(controller.component_id):
            raise RuntimeError(
                f"Inspector for {controller.component_id!r} is unavailable."
            )

        def rollback_inspector() -> None:
            self.figure_inspector.remove_component_inspector(
                controller.component_id
            )
            if (
                previous_component_id is not None
                and previous_component_id in self.component_registry
            ):
                self.figure_inspector.show_component(previous_component_id)

        transaction.on_rollback(rollback_inspector)

    def _normalize_batch_refs(
        self,
        x_ref: ColumnRef,
        y_refs,
    ) -> tuple[ColumnRef, tuple[ColumnRef, ...]]:
        if not isinstance(x_ref, ColumnRef):
            raise ValueError("Please select X Data.")
        normalized_y = tuple(y_refs)
        if not normalized_y:
            raise ValueError("Please select at least one Y Data column.")
        if any(not isinstance(ref, ColumnRef) for ref in normalized_y):
            raise ValueError("Every Y Data selection must be a column reference.")
        if len(set(normalized_y)) != len(normalized_y):
            raise ValueError("Duplicate Y Data selections are not allowed.")
        if x_ref.project_id != self.project_id:
            raise ValueError("X Data must belong to the current project.")
        if not self.repository.has_ref(x_ref):
            raise ValueError("X Data column was removed.")
        x_column = self.repository.sheet(
            x_ref.project_id, x_ref.sheet_id
        ).column(x_ref.column_id)
        if x_column.type not in {ColumnType.NUMBER, ColumnType.DATETIME}:
            raise ValueError("X Data must be numeric or date/time.")
        for index, ref in enumerate(normalized_y, start=1):
            if ref.project_id != self.project_id:
                raise ValueError(
                    f"Y Data selection {index} must belong to the current project."
                )
            if not self.repository.has_ref(ref):
                raise ValueError(f"Y Data selection {index} was removed.")
            column = self.repository.sheet(
                ref.project_id, ref.sheet_id
            ).column(ref.column_id)
            if column.type is not ColumnType.NUMBER:
                raise ValueError(
                    f"Y Data selection {index} must be numeric."
                )
        return x_ref, normalized_y

    def _batch_series_labels(
        self,
        y_refs: tuple[ColumnRef, ...],
    ) -> tuple[str, ...]:
        names = tuple(
            str(
                self.repository.sheet(ref.project_id, ref.sheet_id)
                .column(ref.column_id)
                .name
            )
            for ref in y_refs
        )
        counts = {
            name.casefold(): sum(
                candidate.casefold() == name.casefold()
                for candidate in names
            )
            for name in names
        }
        labels = []
        for ref, name in zip(y_refs, names):
            if counts[name.casefold()] == 1:
                labels.append(name)
                continue
            sheet = self.repository.sheet(ref.project_id, ref.sheet_id)
            labels.append(f"{sheet.name}/{name}")
        return tuple(labels)

    def _batch_color_plan(
        self,
        selection: ColorSelection,
        count: int,
    ) -> tuple[tuple[str, ...], dict[str, Any] | None, bool]:
        if not isinstance(selection, ColorSelection):
            raise TypeError("Batch chart color must be a ColorSelection.")
        if selection.palette is None:
            return (
                tuple(selection.color for _index in range(count)),
                None,
                False,
            )
        axes_id = self.current_axes_component_id
        if axes_id is None:
            raise ValueError("Select an axes before adding charts.")
        cycle = self.axes_commands.cycle_state(axes_id)
        colors: list[str] = []
        next_selection = selection
        for index in range(count):
            if index:
                next_selection = cycle.peek()
            colors.append(next_selection.color)
            cycle.commit(next_selection)
        return tuple(colors), cycle.to_dict(), True

    def _prepare_data_batch(
        self,
        x_ref: ColumnRef,
        y_refs,
        preprocess: DataPreprocessSpec | dict[str, Any] | None,
        color_selection: ColorSelection,
        *,
        preserve_gaps: bool,
    ) -> tuple[
        tuple[_PreparedChartSeries, ...],
        dict[str, Any] | None,
        bool,
    ]:
        x_ref, normalized_y = self._normalize_batch_refs(x_ref, y_refs)
        spec = DataPreprocessSpec.from_dict(preprocess)
        labels = self._batch_series_labels(normalized_y)
        resolved = []
        for y_ref, label in zip(normalized_y, labels):
            try:
                pair = resolve_preprocessed_pair(
                    self.repository,
                    x_ref,
                    y_ref,
                    spec,
                    preserve_gaps=preserve_gaps,
                )
                if not pair.valid_mask.any():
                    raise ValueError(
                        "X Data and Y Data have no valid row pairs after "
                        "preprocessing."
                    )
            except Exception as exc:
                raise ValueError(f"{label}: {exc}") from exc
            resolved.append((y_ref, label, pair))
        colors, final_cycle, commit_cycle = self._batch_color_plan(
            color_selection,
            len(resolved),
        )
        prepared = tuple(
            _PreparedChartSeries(
                x_ref=x_ref,
                y_ref=y_ref,
                x=pair.x,
                y=pair.y,
                label=label,
                color=color,
                excluded_count=pair.excluded_count,
            )
            for (y_ref, label, pair), color in zip(resolved, colors)
        )
        return prepared, final_cycle, commit_cycle

    def _stage_plot(
        self,
        transaction,
        series: _PreparedChartSeries,
        *,
        style,
        size,
        linewidth: float | None,
        preprocess: DataPreprocessSpec,
        object_id: str | None = None,
        color_order: int | None = None,
    ):
        object_id = object_id or new_id()
        plot_kwargs = {
            "linestyle": style,
            "markersize": size,
            "color": series.color,
            "label": series.label,
        }
        if linewidth is not None:
            plot_kwargs["linewidth"] = float(linewidth)
        with mpl_style.context(self.component_style):
            line, = self.current_axes.plot(series.x, series.y, **plot_kwargs)
        transaction.on_rollback(
            lambda line=line: self._remove_created_artist(line)
        )
        component_order = self._claim_color_order(color_order)
        controller = self._register_chart_controller(
            DataPlotController,
            object_id,
            ComponentRole.DATA_PLOT,
            line,
            component_order,
            {
                "linestyle": line.get_linestyle(),
                "markersize": float(line.get_markersize()),
                "color": series.color,
                "label": series.label,
            },
            {
                "x_ref": series.x_ref.to_dict(),
                "y_ref": series.y_ref.to_dict(),
                "preprocess": preprocess.to_dict(),
            },
        )
        self._prepare_created_component(controller, transaction)
        return line, controller

    def _stage_scatter(
        self,
        transaction,
        series: _PreparedChartSeries,
        *,
        size,
        marker,
        preprocess: DataPreprocessSpec,
        object_id: str | None = None,
        color_order: int | None = None,
    ):
        object_id = object_id or new_id()
        with mpl_style.context(self.component_style):
            scatter = self.current_axes.scatter(
                series.x,
                series.y,
                s=size,
                c=series.color,
                marker=marker,
                label=series.label,
            )
        transaction.on_rollback(
            lambda scatter=scatter: self._remove_created_artist(scatter)
        )
        component_order = self._claim_color_order(color_order)
        controller = self._register_chart_controller(
            ScatterController,
            object_id,
            ComponentRole.SCATTER,
            scatter,
            component_order,
            {
                "color": series.color,
                "edgecolor": series.color,
                "size": float(size),
                "marker": marker,
                "label": series.label,
            },
            {
                "x_ref": series.x_ref.to_dict(),
                "y_ref": series.y_ref.to_dict(),
                "preprocess": preprocess.to_dict(),
            },
        )
        self._prepare_created_component(controller, transaction)
        return scatter, controller

    def _stage_interpolation(
        self,
        transaction,
        series: _PreparedChartSeries,
        *,
        method,
        k: int,
        samples: int,
        lam: float | None,
        lam_auto: bool,
        preprocess: DataPreprocessSpec,
        object_id: str | None = None,
        color_order: int | None = None,
    ):
        object_id = object_id or new_id()
        with mpl_style.context(self.component_style):
            line, = self.current_axes.plot(
                series.x,
                series.y,
                color=series.color,
                label=series.label,
            )
        transaction.on_rollback(
            lambda line=line: self._remove_created_artist(line)
        )
        component_order = self._claim_color_order(color_order)
        controller = self._register_chart_controller(
            InterpolationController,
            object_id,
            ComponentRole.INTERPOLATION,
            line,
            component_order,
            {
                "linestyle": line.get_linestyle(),
                "color": series.color,
                "label": series.label,
            },
            {
                "x_ref": series.x_ref.to_dict(),
                "y_ref": series.y_ref.to_dict(),
                "preprocess": preprocess.to_dict(),
                "method": method,
                "k": int(k),
                "samples": int(samples),
                "lam": None if lam is None else float(lam),
                "lam_auto": bool(lam_auto),
            },
        )
        self._prepare_created_component(controller, transaction)
        return line, controller

    def _commit_chart_batch(
        self,
        prepared: tuple[_PreparedChartSeries, ...],
        stage,
        *,
        final_cycle: dict[str, Any] | None,
        commit_cycle: bool,
    ) -> ChartBatchCreationResult:
        axes_id = self.current_axes_component_id
        axes_controller = self.current_axes_controller
        if axes_id is None or axes_controller is None or self.current_axes is None:
            raise ValueError("Select an axes before adding charts.")
        artists = []
        controllers = []
        with self.component_registry.registration_transaction() as transaction:
            transaction.watch_existing(axes_id)
            for series in prepared:
                artist, controller = stage(transaction, series)
                artists.append(artist)
                controllers.append(controller)
            if commit_cycle:
                change = axes_controller.set_property(
                    "color_cycle", final_cycle
                )
                if not change.ok:
                    raise ValueError(
                        change.message or "Could not commit the chart color cycle."
                    )
        self._select_created_component(controllers[-1])
        self.redraw()
        colors = tuple(series.color for series in prepared)
        self.color_library.record_recent_many(colors)
        return ChartBatchCreationResult(
            component_ids=tuple(
                controller.component_id for controller in controllers
            ),
            artists=tuple(artists),
            colors=colors,
            excluded_counts=tuple(
                series.excluded_count for series in prepared
            ),
        )

    def delete_component_group(
        self,
        component_ids,
        role_label: str = "component",
    ) -> bool:
        """Delete selected components through the single production entry."""

        ids = tuple(dict.fromkeys(str(item) for item in component_ids))
        return self.delete_components(
            ids,
            anchor_id=ids[0] if ids else None,
            reason=(DeleteReason.SINGLE if len(ids) == 1 else DeleteReason.BATCH),
            role_label=role_label,
        )

    def delete_components(
        self,
        component_ids,
        *,
        anchor_id: str | None = None,
        reason: DeleteReason | str = DeleteReason.PROGRAMMATIC,
        role_label: str = "component",
    ) -> bool:
        """Submit a stable-ID deletion request to the Canvas coordinator."""

        request = DeletionRequest(
            tuple(str(item) for item in component_ids),
            anchor_id=anchor_id,
            reason=DeleteReason(reason),
        )
        return self.deletion_coordinator.delete(
            request,
            role_label=role_label,
        )

    # Add axes
    def add_axes(
        self,
        nrows=1,
        ncols=1,
        slots: list[int] | tuple[int, ...] | None = None,
    ):
        """Add a compatibility regular grid through the layout service."""

        return self.create_axes_layout(
            AxesLayoutSpec.grid(
                int(nrows),
                int(ncols),
                slots=(tuple(int(slot) for slot in slots) if slots is not None else None),
                cell_view=self.axes_layout_service.creation_view_defaults(),
                constrained_layout=bool(self.fig.get_constrained_layout()),
            )
        )

    def create_axes_layout(self, spec: AxesLayoutSpec) -> tuple[str, ...]:
        """Create a validated Axes layout through the domain service."""

        return self.axes_layout_service.create(spec)

    def update_axes_layout(self, spec: AxesLayoutSpec) -> tuple[str, ...]:
        """Safely update geometry for an existing persisted layout."""

        return self.axes_layout_service.update_geometry(spec)

    # Add custom curve
    def add_curve(self, func_text: str, x_start: float, x_stop: float, style, color, label: str,
                  color_order: int | None = None,
                  object_id: str | None = None):
        """Add curve."""

        color = normalize_color(color)
        object_id = object_id or new_id()
        x = np.linspace(x_start, x_stop, 1000)
        y = evaluate_curve_expression(func_text, x)
        with self.component_registry.registration_transaction() as transaction:
            with mpl_style.context(self.component_style):
                line, = self.current_axes.plot(x, y, ls=style, color=color, label=label)
            transaction.on_rollback(
                lambda: self._remove_created_artist(line)
            )
            component_order = self._claim_color_order(color_order)
            controller = self._register_chart_controller(
                FunctionCurveController,
                object_id,
                ComponentRole.FUNCTION_CURVE,
                line,
                component_order,
                {
                    "linestyle": line.get_linestyle(),
                    "color": color,
                    "label": label,
                },
                {
                    "expression": func_text,
                    "x_start": float(x_start),
                    "x_stop": float(x_stop),
                },
            )
            self._prepare_created_component(controller, transaction)
        self._select_created_component(controller)
        self.redraw()
        return line

    def add_component_line(
        self,
        x,
        y,
        style="-",
        color="black",
        label="",
        *,
        object_id: str | None = None,
        color_order: int | None = None,
    ):
        """Restore/register a generic Line component without a visible panel."""

        color = normalize_color(color)
        object_id = object_id or new_id()
        with self.component_registry.registration_transaction() as transaction:
            with mpl_style.context(self.component_style):
                line, = self.current_axes.plot(
                    np.asarray(x),
                    np.asarray(y),
                    linestyle=style,
                    color=color,
                    label=label,
                )
            transaction.on_rollback(
                lambda: self._remove_created_artist(line)
            )
            component_order = self._claim_color_order(color_order)
            controller = self._register_chart_controller(
                LineController,
                object_id,
                ComponentRole.LINE,
                line,
                component_order,
                {
                    "linestyle": line.get_linestyle(),
                    "color": color,
                    "label": label,
                },
                {
                    "x": np.asarray(x).tolist(),
                    "y": np.asarray(y).tolist(),
                },
            )
            self._prepare_created_component(controller, transaction)
        self._select_created_component(controller)
        self.redraw()
        return line

    # Add line plot
    def add_plot(self, x, y, style, size, color, label, x_ref: ColumnRef, y_ref: ColumnRef,
                 object_id: str | None = None,
                 color_order: int | None = None,
                 *, linewidth: float | None = None,
                 preprocess: DataPreprocessSpec | dict[str, Any] | None = None):
        """Add plot."""

        preprocess = DataPreprocessSpec.from_dict(preprocess)
        pair = resolve_preprocessed_pair(
            self.repository,
            x_ref,
            y_ref,
            preprocess,
            preserve_gaps=True,
        )
        series = _PreparedChartSeries(
            x_ref=x_ref,
            y_ref=y_ref,
            x=pair.x,
            y=pair.y,
            label=str(label),
            color=normalize_color(color),
            excluded_count=pair.excluded_count,
        )
        axes_id = self.current_axes_component_id
        if axes_id is None:
            raise ValueError("Select an axes before adding a chart.")
        with self.component_registry.registration_transaction() as transaction:
            transaction.watch_existing(axes_id)
            line, controller = self._stage_plot(
                transaction,
                series,
                style=style,
                size=size,
                linewidth=linewidth,
                preprocess=preprocess,
                object_id=object_id,
                color_order=color_order,
            )
        self._select_created_component(controller)
        self.redraw()
        return line

    def add_plots(
        self,
        x_ref: ColumnRef,
        y_refs,
        *,
        style,
        size,
        linewidth: float | None,
        preprocess: DataPreprocessSpec | dict[str, Any] | None,
        color_selection: ColorSelection,
    ) -> ChartBatchCreationResult:
        """Atomically create one Plot component for every selected Y column."""

        spec = DataPreprocessSpec.from_dict(preprocess)
        prepared, final_cycle, commit_cycle = self._prepare_data_batch(
            x_ref,
            y_refs,
            spec,
            color_selection,
            preserve_gaps=True,
        )
        return self._commit_chart_batch(
            prepared,
            lambda transaction, series: self._stage_plot(
                transaction,
                series,
                style=style,
                size=size,
                linewidth=linewidth,
                preprocess=spec,
            ),
            final_cycle=final_cycle,
            commit_cycle=commit_cycle,
        )

    # Add scatter plot
    def add_scatter(self, x, y, size, color, marker, label, x_ref: ColumnRef, y_ref: ColumnRef,
                    object_id: str | None = None,
                    color_order: int | None = None,
                    preprocess: DataPreprocessSpec | dict[str, Any] | None = None):
        """Add scatter."""

        preprocess = DataPreprocessSpec.from_dict(preprocess)
        pair = resolve_preprocessed_pair(
            self.repository,
            x_ref,
            y_ref,
            preprocess,
            preserve_gaps=False,
        )
        series = _PreparedChartSeries(
            x_ref=x_ref,
            y_ref=y_ref,
            x=pair.x,
            y=pair.y,
            label=str(label),
            color=normalize_color(color),
            excluded_count=pair.excluded_count,
        )
        axes_id = self.current_axes_component_id
        if axes_id is None:
            raise ValueError("Select an axes before adding a chart.")
        with self.component_registry.registration_transaction() as transaction:
            transaction.watch_existing(axes_id)
            scatter, controller = self._stage_scatter(
                transaction,
                series,
                size=size,
                marker=marker,
                preprocess=preprocess,
                object_id=object_id,
                color_order=color_order,
            )
        self._select_created_component(controller)
        self.redraw()
        return scatter

    def add_scatters(
        self,
        x_ref: ColumnRef,
        y_refs,
        *,
        size,
        marker,
        preprocess: DataPreprocessSpec | dict[str, Any] | None,
        color_selection: ColorSelection,
    ) -> ChartBatchCreationResult:
        """Atomically create one Scatter component for every selected Y."""

        spec = DataPreprocessSpec.from_dict(preprocess)
        prepared, final_cycle, commit_cycle = self._prepare_data_batch(
            x_ref,
            y_refs,
            spec,
            color_selection,
            preserve_gaps=False,
        )
        return self._commit_chart_batch(
            prepared,
            lambda transaction, series: self._stage_scatter(
                transaction,
                series,
                size=size,
                marker=marker,
                preprocess=spec,
            ),
            final_cycle=final_cycle,
            commit_cycle=commit_cycle,
        )

    # Add fit curve
    def add_fit_curve(self, x, y, color, label, x_ref: ColumnRef, y_ref: ColumnRef,
                      engine: str = "Python", fit_type=None,
                      fit_options=None, fit_result=None, expression: str = "",
                      x_start: float | None = None, x_stop: float | None = None,
                      style: str | None = None, object_id: str | None = None,
                      color_order: int | None = None,
                      preprocess: DataPreprocessSpec | dict[str, Any] | None = None):
        """Add fit curve."""

        preprocess = DataPreprocessSpec.from_dict(preprocess)
        pair = resolve_preprocessed_pair(
            self.repository,
            x_ref,
            y_ref,
            preprocess,
            preserve_gaps=False,
        )
        x, y = pair.x, pair.y
        if engine not in {"Python", "Matlab"}:
            raise ValueError(f"Unsupported fitting engine: {engine}")

        color = normalize_color(color)
        object_id = object_id or new_id()
        x_array = np.asarray(x, dtype=float)
        y_array = np.asarray(y, dtype=float)
        if x_array.size:
            default_x_start = float(np.min(x_array))
            default_x_stop = float(np.max(x_array))
        else:
            default_x_start = 0.0
            default_x_stop = 1.0
        x_start = default_x_start if x_start is None else float(x_start)
        x_stop = default_x_stop if x_stop is None else float(x_stop)

        line_x = x_array
        line_y = y_array
        if expression:
            try:
                line_x = np.linspace(x_start, x_stop, 1000)
                line_y = evaluate_curve_expression(expression, line_x)
            except ValueError:
                status_messages.show_error("Saved fit expression could not be restored; showing source data.")
                expression = ""

        plot_kwargs = {"color": color, "label": label}
        if style is not None:
            plot_kwargs["linestyle"] = style
        with self.component_registry.registration_transaction() as transaction:
            with mpl_style.context(self.component_style):
                line, = self.current_axes.plot(
                    line_x,
                    line_y,
                    **plot_kwargs,
                )
            transaction.on_rollback(
                lambda: self._remove_created_artist(line)
            )
            component_order = self._claim_color_order(color_order)
            controller = self._register_chart_controller(
                FitCurveController,
                object_id,
                ComponentRole.FIT_CURVE,
                line,
                component_order,
                {
                    "linestyle": line.get_linestyle(),
                    "color": color,
                    "label": label,
                },
                {
                    "x_ref": x_ref.to_dict(),
                    "y_ref": y_ref.to_dict(),
                    "preprocess": preprocess.to_dict(),
                    "engine": engine,
                    "fit_type": deepcopy(fit_type),
                    "fit_options": deepcopy(fit_options),
                    "fit_result": deepcopy(fit_result),
                    "expression": expression or "",
                    "x_start": float(x_start),
                    "x_stop": float(x_stop),
                },
            )
            self._prepare_created_component(controller, transaction)
        self._select_created_component(controller)
        self.redraw()
        return line

    # Add interpolation curve
    def add_interpolate_curve(self, x, y, x_ref: ColumnRef, y_ref: ColumnRef, method, k=3, label='interpolate',
                              color='black',
                              samples=DEFAULT_INTERPOLATION_SAMPLES,
                              lam=None, lam_auto=True, object_id: str | None = None,
                              color_order: int | None = None, allow_empty: bool = False,
                              preprocess: DataPreprocessSpec | dict[str, Any] | None = None,
                              announce: bool = True):
        """Add interpolate curve."""

        preprocess = DataPreprocessSpec.from_dict(preprocess)
        pair = resolve_preprocessed_pair(
            self.repository,
            x_ref,
            y_ref,
            preprocess,
            preserve_gaps=False,
        )
        x, y = pair.x, pair.y
        color = normalize_color(color)
        x_values = np.asarray(x)
        y_values = np.asarray(y)
        if allow_empty and (x_values.size == 0 or y_values.size == 0):
            x_new = np.asarray([], dtype=float)
            y_new = np.asarray([], dtype=float)
        else:
            try:
                x_new, y_new = interpolate_curve(
                    x_values,
                    y_values,
                    method,
                    k=k,
                    samples=samples,
                    lam=lam,
                    lam_auto=lam_auto,
                )
            except ValueError as exc:
                if not allow_empty:
                    status_messages.show_error(str(exc))
                    return None
                x_new = np.asarray([], dtype=float)
                y_new = np.asarray([], dtype=float)
                status_messages.show_warning(
                    "Interpolation could not be recomputed from the "
                    f"current source data ({exc}); an empty component "
                    "was restored."
                )
        series = _PreparedChartSeries(
            x_ref=x_ref,
            y_ref=y_ref,
            x=x_new,
            y=y_new,
            label=str(label),
            color=color,
            excluded_count=pair.excluded_count,
        )
        axes_id = self.current_axes_component_id
        if axes_id is None:
            raise ValueError("Select an axes before adding a chart.")
        with self.component_registry.registration_transaction() as transaction:
            transaction.watch_existing(axes_id)
            line, controller = self._stage_interpolation(
                transaction,
                series,
                method=method,
                k=k,
                samples=samples,
                lam=lam,
                lam_auto=lam_auto,
                preprocess=preprocess,
                object_id=object_id,
                color_order=color_order,
            )
        self._select_created_component(controller)
        self.redraw()
        if announce:
            if x_new.size:
                status_messages.show_success("Interpolation curve created.")
            else:
                status_messages.show_warning(
                    "Interpolation curve has no valid data yet; its editor and style were kept."
                )
        return line

    def add_interpolate_curves(
        self,
        x_ref: ColumnRef,
        y_refs,
        *,
        method,
        color_selection: ColorSelection,
        k: int = 3,
        samples: int = DEFAULT_INTERPOLATION_SAMPLES,
        lam: float | None = None,
        lam_auto: bool = True,
        preprocess: DataPreprocessSpec | dict[str, Any] | None = None,
    ) -> ChartBatchCreationResult:
        """Atomically create one interpolation component for every Y."""

        spec = DataPreprocessSpec.from_dict(preprocess)
        sources, final_cycle, commit_cycle = self._prepare_data_batch(
            x_ref,
            y_refs,
            spec,
            color_selection,
            preserve_gaps=False,
        )
        prepared = []
        for series in sources:
            try:
                x_new, y_new = interpolate_curve(
                    np.asarray(series.x),
                    np.asarray(series.y),
                    method,
                    k=k,
                    samples=samples,
                    lam=lam,
                    lam_auto=lam_auto,
                )
            except Exception as exc:
                raise ValueError(f"{series.label}: {exc}") from exc
            prepared.append(
                _PreparedChartSeries(
                    x_ref=series.x_ref,
                    y_ref=series.y_ref,
                    x=x_new,
                    y=y_new,
                    label=series.label,
                    color=series.color,
                    excluded_count=series.excluded_count,
                )
            )
        return self._commit_chart_batch(
            tuple(prepared),
            lambda transaction, series: self._stage_interpolation(
                transaction,
                series,
                method=method,
                k=k,
                samples=samples,
                lam=lam,
                lam_auto=lam_auto,
                preprocess=spec,
            ),
            final_cycle=final_cycle,
            commit_cycle=commit_cycle,
        )

    # Add text
    @staticmethod
    def _resolve_text_usetex(usetex: bool | None) -> bool:
        if usetex is None:
            return tex_config.is_tex_enabled()
        return bool(usetex) and tex_config.is_tex_enabled()

    def add_text(self, x: float, y: float, text: str, fontfamily: str, fontsize: float,
                 usetex: bool | None = None,
                 object_id: str | None = None):
        """Add text."""

        desired_usetex = self._resolve_text_usetex(usetex)
        with mpl_style.context(self.component_style):
            text_artist = self.current_axes.text(
                x,
                y,
                text,
                family=fontfamily,
                fontsize=fontsize,
                transform=self.current_axes.transAxes,
                usetex=False,
            )
        object_id = object_id or new_id()
        parent_id = self.current_axes_component_id
        with self.component_registry.registration_transaction() as transaction:
            transaction.on_rollback(
                lambda: self._remove_created_artist(text_artist)
            )
            controller = self._register_text_controller(
                object_id,
                text_artist,
                parent_id=parent_id,
                order=self._next_child_order(
                    parent_id,
                    kind=ComponentKind.TEXT,
                ),
                scope="axes",
            )
            result = self.text_render_service.apply(
                controller,
                {"usetex": desired_usetex},
            )
            self._prepare_created_component(controller, transaction)
        if not result.ok or result.notices:
            self.message_presenter.present(result)
        self._select_created_component(controller)
        self.redraw()
        return text_artist

    def add_global_text(self, x: float, y: float, text: str, fontfamily: str, fontsize: float,
                        usetex: bool | None = None,
                        object_id: str | None = None):
        """Add global text."""

        desired_usetex = self._resolve_text_usetex(usetex)
        with mpl_style.context(self.component_style):
            text_artist = self.fig.text(
                x,
                y,
                text,
                family=fontfamily,
                fontsize=fontsize,
                usetex=False,
            )
        object_id = object_id or new_id()
        with self.component_registry.registration_transaction() as transaction:
            transaction.on_rollback(
                lambda: self._remove_created_artist(text_artist)
            )
            controller = self._register_text_controller(
                object_id,
                text_artist,
                parent_id=self.root_component_id,
                order=self._next_child_order(
                    self.root_component_id,
                    kind=ComponentKind.TEXT,
                ),
                scope="figure",
            )
            result = self.text_render_service.apply(
                controller,
                {"usetex": desired_usetex},
            )
            self._prepare_created_component(controller, transaction)
        if not result.ok or result.notices:
            self.message_presenter.present(result)
        if self.figure_inspector is not None:
            self._select_created_component(controller)
        self.redraw()
        return text_artist

    def add_in_axes(
        self,
        spec: InAxesCreateSpec,
        *,
        object_id: str | None = None,
    ) -> Axes:
        """Create one Zoom or embedded-image child Axes Element atomically."""

        parent_axes = self.current_axes
        parent_id = self.current_axes_component_id
        if parent_axes is None or parent_id is None:
            raise ValueError("Select an axes before creating an in_axes Element.")
        if isinstance(spec, ZoomInAxesCreateSpec):
            role = ComponentRole.IN_AXES_ZOOM
            controller_type = ZoomInAxesController
            properties = spec.properties()
            data: dict[str, Any] = {}
        elif isinstance(spec, ImageInAxesCreateSpec):
            role = ComponentRole.IN_AXES_IMAGE
            controller_type = ImageInAxesController
            properties = spec.properties()
            data = spec.data()
            decode_in_axes_image(data)
        else:
            raise TypeError("add_in_axes requires a Zoom or Image creation spec.")

        component_id = object_id or new_id()
        state = ComponentState(
            id=component_id,
            kind=ComponentKind.IN_AXES,
            role=role,
            parent_id=parent_id,
            order=self._next_child_order(
                parent_id,
                kind=ComponentKind.IN_AXES,
            ),
            selector={"object_id": component_id},
            properties=properties,
            data=data,
        )
        controller = None
        mirrored = None
        with self.component_registry.registration_transaction() as transaction:
            with mpl_style.context(self.component_style):
                runtime = self.in_axes_service.create_runtime(
                    parent_axes,
                    tuple(properties["bounds"]),
                    zorder=float(properties["zorder"]),
                )
            transaction.on_rollback(
                lambda target=runtime: self.in_axes_service.destroy_runtime(target)
            )
            controller = controller_type(state, target=runtime)
            initial = controller.apply_state(state)
            if not initial.ok:
                raise ValueError(initial.message)
            if isinstance(controller, ZoomInAxesController):
                self.in_axes_service.add_zoom_indicator(runtime, properties)
            controller.sync_from_target(strict=True)
            self.component_registry.register(controller, target=runtime)
            self.in_axes_service.register_runtime(component_id, runtime)
            transaction.on_rollback(
                lambda target=component_id: self.in_axes_service.unregister_runtime(target)
            )
            if isinstance(controller, ZoomInAxesController):
                mirrored = self.in_axes_service.refresh_zoom(controller)
            self._prepare_created_component(controller, transaction)

        self._select_created_component(controller)
        if not self._restoring_component_tree_now:
            self.redraw()
            if role is ComponentRole.IN_AXES_ZOOM and mirrored == 0:
                status_messages.show_warning(
                    "Zoom inset created, but the parent Axes has no visible "
                    "Line or Scatter components yet."
                )
            elif role is ComponentRole.IN_AXES_ZOOM:
                status_messages.show_success("Zoom inset created.")
            else:
                status_messages.show_success("Image inset created.")
        return runtime.axes

    def save(self, filename, dpi=None):
        """Save the current figure through the selected destination."""

        if dpi is None:
            save_dpi = self.document_dpi
        else:
            save_dpi = dpi
        with mpl_style.context(self.component_style):
            self.fig.savefig(filename, dpi=save_dpi)

    def dependent_records(self, refs: set[ColumnRef]) -> ComponentDependencySnapshot:
        """Return Controller snapshots for table-deletion undo."""

        return self.dependency_service.capture(
            refs,
            selected_component_id=self.current_component_id,
        )

    def _restore_component_state(self, state: ComponentState):
        """Materialize one dynamic v7 component and reapply its full state."""

        if state.id in self.component_registry:
            return self.component_registry.get(state.id)
        if state.parent_id != self.root_component_id:
            parent = self.component_registry.get(state.parent_id)
            if not isinstance(parent, AxesController):
                raise ValueError(
                    f"Dynamic component {state.id!r} requires an Axes parent."
                )
            self.update_current_axes(parent)

        properties = state.properties
        data = state.data
        role = state.role
        if role is ComponentRole.IN_AXES_ZOOM:
            self.add_in_axes(
                ZoomInAxesCreateSpec(
                    bounds=tuple(properties["bounds"]),
                    xlim=tuple(properties["xlim"]),
                    ylim=tuple(properties["ylim"]),
                    facecolor=properties["facecolor"],
                    edgecolor=properties["edgecolor"],
                    linewidth=properties["linewidth"],
                    indicator_color=properties["indicator_color"],
                    indicator_linestyle=properties["indicator_linestyle"],
                    indicator_linewidth=properties["indicator_linewidth"],
                    indicator_alpha=properties["indicator_alpha"],
                    visible=properties["visible"],
                    zorder=properties["zorder"],
                    frameon=properties["frameon"],
                    ticks_visible=properties["ticks_visible"],
                    region_visible=properties["region_visible"],
                    connectors_visible=properties["connectors_visible"],
                ),
                object_id=state.id,
            )
        elif role is ComponentRole.IN_AXES_IMAGE:
            self.add_in_axes(
                ImageInAxesCreateSpec(
                    bounds=tuple(properties["bounds"]),
                    filename=data["filename"],
                    mime_type=data["mime_type"],
                    payload_base64=data["payload_base64"],
                    facecolor=properties["facecolor"],
                    edgecolor=properties["edgecolor"],
                    linewidth=properties["linewidth"],
                    opacity=properties["opacity"],
                    fit_mode=properties["fit_mode"],
                    interpolation=properties["interpolation"],
                    visible=properties["visible"],
                    zorder=properties["zorder"],
                    frameon=properties["frameon"],
                ),
                object_id=state.id,
            )
        elif role is ComponentRole.FUNCTION_CURVE:
            self.add_curve(
                data["expression"],
                data["x_start"],
                data["x_stop"],
                properties.get("linestyle", "-"),
                properties.get("color", "black"),
                properties.get("label", ""),
                object_id=state.id,
                color_order=state.order,
            )
        elif role is ComponentRole.LINE:
            self.add_component_line(
                data.get("x", []),
                data.get("y", []),
                properties.get("linestyle", "-"),
                properties.get("color", "black"),
                properties.get("label", ""),
                object_id=state.id,
                color_order=state.order,
            )
        elif role in {
            ComponentRole.DATA_PLOT,
            ComponentRole.SCATTER,
            ComponentRole.INTERPOLATION,
            ComponentRole.FIT_CURVE,
        }:
            x_ref = ColumnRef.from_dict(data["x_ref"])
            y_ref = ColumnRef.from_dict(data["y_ref"])
            preprocess = DataPreprocessSpec.from_dict(data["preprocess"])
            pair = resolve_preprocessed_pair(
                self.repository,
                x_ref,
                y_ref,
                preprocess,
                preserve_gaps=role is ComponentRole.DATA_PLOT,
            )
            if role is ComponentRole.DATA_PLOT:
                self.add_plot(
                    pair.x,
                    pair.y,
                    properties.get("linestyle", "-"),
                    properties.get("markersize", 2.0),
                    properties.get("color", "black"),
                    properties.get("label", ""),
                    x_ref,
                    y_ref,
                    object_id=state.id,
                    color_order=state.order,
                    preprocess=preprocess,
                )
            elif role is ComponentRole.SCATTER:
                self.add_scatter(
                    pair.x,
                    pair.y,
                    properties.get("size", 20.0),
                    properties.get("color", "black"),
                    properties.get("marker", "o"),
                    properties.get("label", ""),
                    x_ref,
                    y_ref,
                    object_id=state.id,
                    color_order=state.order,
                    preprocess=preprocess,
                )
            elif role is ComponentRole.INTERPOLATION:
                self.add_interpolate_curve(
                    pair.x,
                    pair.y,
                    x_ref,
                    y_ref,
                    data["method"],
                    k=data.get("k", 3),
                    label=properties.get("label", "interpolate"),
                    color=properties.get("color", "black"),
                    samples=data.get(
                        "samples",
                        DEFAULT_INTERPOLATION_SAMPLES,
                    ),
                    lam=data.get("lam"),
                    lam_auto=data.get("lam_auto", True),
                    object_id=state.id,
                    color_order=state.order,
                    allow_empty=True,
                    preprocess=preprocess,
                    announce=False,
                )
            else:
                self.add_fit_curve(
                    pair.x,
                    pair.y,
                    properties.get("color", "black"),
                    properties.get("label", "fitting"),
                    x_ref,
                    y_ref,
                    engine=data.get("engine", "Python"),
                    fit_type=data.get("fit_type"),
                    fit_options=data.get("fit_options"),
                    fit_result=data.get("fit_result"),
                    expression=data.get("expression", ""),
                    x_start=data.get("x_start"),
                    x_stop=data.get("x_stop"),
                    style=properties.get("linestyle", "solid"),
                    object_id=state.id,
                    color_order=state.order,
                    preprocess=preprocess,
                )
        elif role is ComponentRole.TEXT:
            position = properties.get("position", (0.0, 0.0))
            family = properties.get("fontfamily", "sans-serif")
            if isinstance(family, (list, tuple)):
                family = family[0] if family else "sans-serif"
            kwargs = dict(
                x=float(position[0]),
                y=float(position[1]),
                text=properties.get("text", ""),
                fontfamily=family,
                fontsize=properties.get("fontsize", 10.0),
                usetex=properties.get("usetex", False),
                object_id=state.id,
            )
            if state.parent_id == self.root_component_id:
                self.add_global_text(**kwargs)
            else:
                self.add_text(**kwargs)
        else:
            raise ValueError(
                f"Cannot materialize dynamic component role {role.value!r}."
            )

        controller = self.component_registry.get(state.id)
        change = controller.apply_state(state)
        if not change.ok:
            self.component_registry.delete(state.id)
            raise ValueError(change.message)
        return controller

    def remove_data_dependents(
        self,
        snapshots: ComponentDependencySnapshot,
        request: DeletionRequest | None = None,
    ) -> bool:
        """Remove components captured before a table mutation."""

        if request is None:
            request = self.prepare_data_dependents(snapshots)
        ids = request.component_ids
        if not ids:
            return True
        return self.deletion_coordinator.delete(
            request,
            role_label="dependent",
            present_success=False,
        )

    def prepare_data_dependents(
        self,
        snapshots: ComponentDependencySnapshot,
    ) -> DeletionRequest:
        """Preflight one Canvas before any cross-Canvas commit begins."""

        expected = tuple(state.id for state in snapshots.component_states)
        missing = [
            component_id
            for component_id in expected
            if component_id not in self.component_registry
        ]
        if missing:
            raise ValueError(
                "Dependent components changed before deletion: "
                + ", ".join(missing)
            )
        request = DeletionRequest(
            expected,
            anchor_id=expected[0] if expected else None,
            reason=DeleteReason.DATA_DEPENDENCY,
        )
        self.deletion_service.prepare(request)
        return request

    def restore_data_dependents(
        self,
        snapshots: ComponentDependencySnapshot,
    ) -> None:
        """Restore components captured before a table mutation."""

        try:
            self.dependency_service.restore_states(snapshots)
            target = snapshots.selected_component_id
            if target is not None and target in self.component_registry:
                self.select_component(target)
        finally:
            self.message_presenter.discard_pending()

    def restore_component_tree(
        self,
        component_tree: dict[str, Any] | None = None,
    ) -> None:
        """Materialize and apply a validated v7 component tree directly."""

        self._restoring_component_tree_now = True
        try:
            with (
                self.component_registry.batch_events(),
                self.in_axes_service.suspend_refresh(),
            ):
                self._restore_component_tree_impl(component_tree)
        finally:
            self._restoring_component_tree_now = False
        target = (
            self.current_axes_component_id
            if self.current_axes_component_id in self.component_registry
            else self.root_component_id
        )
        if (
            self.figure_inspector is not None
            and target in self.component_registry
        ):
            self.select_component(target)

    def _restore_component_tree_impl(
        self,
        component_tree: dict[str, Any] | None = None,
    ) -> None:
        """Perform the materialization while creation selection is paused."""

        source = component_tree or self._restore_component_tree
        if not isinstance(source, dict):
            return
        source = normalize_v9_figure(source)
        states = [
            ComponentState.from_dict(raw_state)
            for raw_state in source["components"]
        ]
        axes_states = sorted(
            (
                state
                for state in states
                if state.kind is ComponentKind.AXES
            ),
            key=lambda state: int(state.selector["index"]),
        )
        self.axes_layout_service.materialize(axes_states)

        dynamic_states = [
            state
            for state in states
            if (
                state.role
                in {
                    ComponentRole.LINE,
                    ComponentRole.FUNCTION_CURVE,
                    ComponentRole.DATA_PLOT,
                    ComponentRole.FIT_CURVE,
                    ComponentRole.INTERPOLATION,
                    ComponentRole.SCATTER,
                }
                or (
                    state.kind is ComponentKind.TEXT
                    and state.role is ComponentRole.TEXT
                )
            )
        ]
        for state in sorted(
            dynamic_states,
            key=lambda item: (
                int(item.selector.get("axes_index", -1)),
                item.order,
                item.id,
            ),
        ):
            self._restore_component_state(state)

        in_axes_states = [
            state
            for state in states
            if state.kind is ComponentKind.IN_AXES
        ]
        for state in sorted(
            in_axes_states,
            key=lambda item: (item.parent_id or "", item.order, item.id),
        ):
            self._restore_component_state(state)

        self.apply_component_tree(source)

    def apply_component_tree(
        self, component_tree: dict[str, Any] | None
    ) -> None:
        """Apply all v7 states after their Matplotlib targets exist."""

        if not isinstance(component_tree, dict):
            return
        states = [
            ComponentState.from_dict(raw_state)
            for raw_state in component_tree.get("components", [])
        ]
        source_by_id = {state.id: state for state in states}
        runtime_ids = {
            controller.component_id
            for controller in self.component_registry.query()
        }
        missing = sorted(set(source_by_id) - runtime_ids)
        unexpected = sorted(runtime_ids - set(source_by_id))
        if missing or unexpected:
            details = []
            if missing:
                details.append("missing " + ", ".join(missing))
            if unexpected:
                details.append("unexpected " + ", ".join(unexpected))
            raise ValueError(
                "Project components could not be restored: "
                + "; ".join(details)
            )

        figure_states = [
            state for state in states
            if state.kind is ComponentKind.FIGURE
        ]
        axes_states = [
            state for state in states
            if state.kind is ComponentKind.AXES
        ]
        legend_states = [
            state for state in states
            if state.kind is ComponentKind.LEGEND
        ]
        body_states = [
            state for state in states
            if state.kind not in {
                ComponentKind.FIGURE,
                ComponentKind.AXES,
                ComponentKind.LEGEND,
            }
        ]
        in_axes_states = [
            state
            for state in body_states
            if state.kind is ComponentKind.IN_AXES
        ]
        body_states = [
            state
            for state in body_states
            if state.kind is not ComponentKind.IN_AXES
        ]
        tex_fallback = False

        def apply_states(values: list[ComponentState]) -> None:
            nonlocal tex_fallback
            with self.component_registry.batch_updates():
                for source_state in sorted(
                    values,
                    key=lambda item: (item.order, item.id),
                ):
                    controller = self.component_registry.get(source_state.id)
                    candidate = source_state
                    if (
                        source_state.kind is ComponentKind.TEXT
                        and source_state.properties.get("usetex")
                        and not tex_config.is_tex_enabled()
                    ):
                        properties = dict(source_state.properties)
                        properties["usetex"] = False
                        candidate = source_state.clone(properties=properties)
                        tex_fallback = True
                    change = controller.apply_state(candidate)
                    if not change.ok:
                        raise ValueError(
                            f"Could not restore component {source_state.id}: "
                            f"{change.message}"
                        )

        apply_states(figure_states)
        if figure_states:
            root_properties = figure_states[0].properties
            self._document_dpi = float(
                root_properties.get("dpi", self._document_dpi)
            )
            self.style = str(root_properties.get("style", self.style or "default"))

        # Apply containers/semantics first.  Chart labels and persisted raw
        # data are then allowed to refresh limits and legends once.
        apply_states(axes_states)
        apply_states(body_states)

        # Raw Line/Scatter data can autoscale the Axes.  Reapply the persisted
        # Axes range after that update has been coalesced.
        apply_states(axes_states)
        apply_states(in_axes_states)
        self.in_axes_service.refresh_all_zoom()

        for legend_state in legend_states:
            controller = self.component_registry.get(legend_state.id)
            try:
                controller.resolve_target()
            except Exception:
                parent = self.component_registry.resolve_target(
                    legend_state.parent_id
                )
                if isinstance(parent, Axes) and bool(
                    legend_state.properties.get("visible", True)
                ):
                    handles, labels = parent.get_legend_handles_labels()
                    legend = parent.legend(handles, labels)
                    self.component_registry.locator.bind(
                        legend_state.id,
                        legend,
                    )
        apply_states(legend_states)
        self.axes_layout_service.restore_runtime_relationships(refresh=True)
        self.component_registry.validate_tree()
        if tex_fallback:
            status_messages.show_warning(
                "TeX text was restored with Matplotlib text rendering "
                "because TeX is not enabled."
            )

        self.redraw()

    def set_project_name(self, name: str):
        """Set project name."""

        controller = self.component_registry.get(self.root_component_id)
        change = controller.set_property("name", name)
        if not change.ok:
            raise ValueError(change.message)

    @staticmethod
    def _json_component_value(value):
        if isinstance(value, dict):
            return {
                str(key): PyFigureCanvas._json_component_value(item)
                for key, item in value.items()
            }
        if isinstance(value, (list, tuple)):
            return [
                PyFigureCanvas._json_component_value(item)
                for item in value
            ]
        if isinstance(value, np.ndarray):
            return PyFigureCanvas._json_component_value(value.tolist())
        if isinstance(value, np.generic):
            return value.item()
        return value

    def component_snapshot(self) -> dict[str, Any]:
        """Return the canonical v9 component tree used by persistence."""

        components = []
        for controller in self.component_registry.query():
            try:
                state = controller.read_state()
            except Exception:
                state = controller.state
            properties = controller.default_properties()
            properties.update(state.properties)
            state = state.clone(properties=properties)
            components.append(
                self._json_component_value(
                    state.clone(properties=properties).to_dict()
                )
            )
        snapshot = {
            "root_component_id": self.root_component_id,
            "components": components,
        }
        return normalize_v9_figure(snapshot)

    def validate_component_snapshot(self) -> dict[str, Any]:
        """Validate and return the current complete schema-v9 Figure tree."""

        snapshot = self.component_snapshot()
        project = self.repository.project(self.project_id)
        available_refs = {
            ColumnRef(project.id, sheet.id, column.id): column.type
            for sheet in project.sheets.values()
            for column in sheet.columns
        }
        validate_v9_figure(
            snapshot,
            available_refs,
            self.project_id,
            self.project_name,
        )
        return snapshot
