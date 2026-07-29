"""Host Matplotlib figures and register their editable components."""

from copy import deepcopy
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
    ComponentDependencyService,
    FitService,
    FunctionCurveService,
    InterpolationService,
    TextRenderService,
)
from code.figuremodify.components import (
    AxesController,
    ComponentKind,
    ComponentRegistry,
    ComponentRole,
    ComponentState,
    DataPlotController,
    FigureController,
    FitCurveController,
    FunctionCurveController,
    InterpolationController,
    LineController,
    ScatterController,
    TextController,
    UpdateImpact,
    create_semantic_children,
)
from code.figuremodify.components.serialization import (
    deterministic_component_id,
    normalize_v6_figure,
)

from code import tex_config
from code import status_messages
from code.database import (
    ColumnRef,
    TableChangeSet,
    TableRepository,
    validate_component_name,
)
from code.database.table_document import new_id
from code.database.interpolate_func import DEFAULT_INTERPOLATION_SAMPLES, interpolate_curve
from code.database.safe_expression import evaluate_curve_expression
from code.widgets.common_widget.min_widget.color_library import ColorLibrary
from code.figuremodify.style_base.color_models import (
    ColorCycleState,
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


class PyFigureCanvas(QWidget):
    """Provide the py figure canvas Qt widget."""

    def __init__(self, parent=None, width=4, height=3, dpi=200, style=None,
                 repository: TableRepository | None = None, project_id: str | None = None,
                 project_name: str | None = None, project_path: str | None = None,
                 color_library: ColorLibrary | None = None,
                 component_tree: dict[str, Any] | None = None):
        super().__init__(parent)
        if repository is None or project_id is None:
            raise ValueError("PyFigureCanvas requires a repository and project id.")
        self.repository = repository
        self.project_id = project_id
        self.style = style
        self.project_name = project_name or ""
        self.project_table_name = self.project_name
        self.project_path = project_path
        self.color_library = color_library or ColorLibrary(parent=self)
        self._component_id_overrides = self._component_paths_from_tree(
            component_tree
        )
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
        self.component_editor_registry = self.editor_registry
        self.axes_commands = AxesCommandService(self.component_registry)
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
        self.message_presenter = MessagePresenter(
            self.component_registry
        )
        self.component_editor_manager = ComponentEditorManager(
            self.component_registry,
            self.editor_registry,
        )
        self.dependency_service = ComponentDependencyService(
            self.component_registry,
            restore_state=self._restore_component_state,
        )
        self.editor_context = EditorContext(
            registry=self.component_registry,
            color_library=self.color_library,
            messages=self.message_presenter,
            editor_manager=self.component_editor_manager,
            axes_commands=self.axes_commands,
            function_curves=self.function_curve_service,
            chart_data=self.chart_data_service,
            interpolation=self.interpolation_service,
            fitting=self.fit_service,
            text_rendering=self.text_render_service,
            dependency_service=self.dependency_service,
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
            self._claim_color_order(),
        )

    def _component_id(self, semantic_path: str) -> str:
        return self._component_id_overrides.get(
            semantic_path,
            deterministic_component_id(self.project_id, semantic_path),
        )

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
        nrows: int,
        ncols: int,
        slot: int,
        layout_group: int,
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
                "color_cycle": None,
            },
            data={
                "subplot": {
                    "layout_group": int(layout_group),
                    "nrows": int(nrows),
                    "ncols": int(ncols),
                    "slot": int(slot),
                }
            },
        )
        self.component_registry.register(
            AxesController(axes_state),
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
        self.current_axes_component_id = controller.component_id
        if self.figure_inspector is not None:
            inspector = self.figure_inspector.find_axes_inspector(
                controller.resolve_target()
            )
            if inspector is not None:
                self.figure_inspector.show_axes_inspector(inspector)

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

    def redraw(self):
        """Schedule a coalesced canvas redraw."""

        self.fig.canvas.draw()

    def cancel_pending_draw(self):
        """Cancel a queued redraw that has not reached the canvas yet."""

        if hasattr(self.canva, "_draw_pending"):
            self.canva._draw_pending = False

    def closeEvent(self, event):
        """Handle Qt close events and release owned resources."""

        self.cancel_pending_draw()
        try:
            self.repository.transaction_committed.disconnect(self._table_changed)
        except RuntimeError:
            pass
        self.message_presenter.close()
        self.component_editor_manager.close()
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
        axes_id = self.current_axes_component_id
        if axes_id is None:
            raise ValueError("Select an axes before adding a chart.")
        orders = [
            controller.state.order
            for controller in self.component_registry.query(
                parent_id=axes_id,
                recursive=False,
            )
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

    def _add_visible_editor(
        self,
        controller,
        *,
        item_label: str,
    ):
        """Create and place a role-registered editor without string routing."""

        state = controller.state
        if state.parent_id == self.root_component_id:
            toolbox = self.figure_inspector.ensure_figure_element_toolbox(
                state.role,
                "text",
            )
        else:
            axes = self.component_registry.resolve_target(state.parent_id)
            axes_inspector = self.figure_inspector.find_axes_inspector(axes)
            if axes_inspector is None:
                raise RuntimeError("Axes Inspector is unavailable.")
            toolbox = axes_inspector.ensure_component_toolbox(
                state.kind,
                state.role,
                state.role.value.replace("_", " "),
            )

        editor = self.component_editor_manager.create(
            controller,
            context=self.editor_context,
            parent=toolbox,
            remover=toolbox.remove_inspector,
        )
        toolbox.add_inspector(editor, item_label)
        toolbox.setCurrentWidget(editor)
        return editor

    def _next_layout_group(self) -> int:
        """Return an unused layout group without assuming persisted IDs are dense."""

        layout_groups = []
        for controller in self.component_registry.query(
            kind=ComponentKind.AXES
        ):
            subplot = controller.state.data.get("subplot")
            if not isinstance(subplot, dict):
                continue
            layout_group = subplot.get("layout_group")
            if isinstance(layout_group, int) and not isinstance(
                layout_group, bool
            ):
                layout_groups.append(layout_group)
        return max(layout_groups, default=-1) + 1

    # Add axes
    def add_axes(
        self,
        nrows=1,
        ncols=1,
        slots: list[int] | tuple[int, ...] | None = None,
    ):
        """Add axes."""

        start_index = len(self.fig.axes)
        layout_group = self._next_layout_group()
        if slots is None:
            subplot_slots = list(range(1, int(nrows) * int(ncols) + 1))
        else:
            subplot_slots = [int(slot) for slot in slots]
            if (
                not subplot_slots
                or len(set(subplot_slots)) != len(subplot_slots)
                or any(
                    not 1 <= slot <= int(nrows) * int(ncols)
                    for slot in subplot_slots
                )
            ):
                raise ValueError("Subplot slots are invalid.")
        first_axes = None
        first_controller = None
        with mpl_style.context(self.component_style):
            for i, slot in enumerate(subplot_slots):
                axe = self.fig.add_subplot(nrows, ncols, slot)
                axes_index = start_index + i
                axes_id, _component_controllers = self._register_axes_components(
                    axe,
                    axes_index,
                    nrows=nrows,
                    ncols=ncols,
                    slot=slot,
                    layout_group=layout_group,
                )
                axes_controller = self.component_registry.get(axes_id)
                btn = self.figure_inspector.add_axes_inspector(
                    axes_controller,
                    self.editor_context,
                    self.color_library,
                )
                btn.clicked.connect(
                    lambda _checked=False, target_id=axes_id:
                    self.update_current_axes(target_id)
                )

                if i == 0:
                    first_axes = axe
                    first_controller = axes_controller

        if first_axes is not None:
            self.update_current_axes(first_controller)

        self.redraw()

    # Add custom curve
    def add_curve(self, func_text: str, x_start: float, x_stop: float, style, color, label: str,
                  color_order: int | None = None,
                  object_id: str | None = None):
        """Add curve."""

        color = normalize_color(color)
        object_id = object_id or new_id()
        x = np.linspace(x_start, x_stop, 1000)
        y = evaluate_curve_expression(func_text, x)
        with mpl_style.context(self.component_style):
            line, = self.current_axes.plot(x, y, ls=style, color=color, label=label)
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
        self._add_visible_editor(controller, item_label="curve")
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
        with mpl_style.context(self.component_style):
            line, = self.current_axes.plot(
                np.asarray(x),
                np.asarray(y),
                linestyle=style,
                color=color,
                label=label,
            )
        component_order = self._claim_color_order(color_order)
        self._register_chart_controller(
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
        self.redraw()
        return line

    # Add line plot
    def add_plot(self, x, y, style, size, color, label, x_ref: ColumnRef, y_ref: ColumnRef,
                 object_id: str | None = None,
                 color_order: int | None = None,
                 *, linewidth: float | None = None):
        """Add plot."""

        color = normalize_color(color)
        object_id = object_id or new_id()
        plot_kwargs = {
            "linestyle": style,
            "markersize": size,
            "color": color,
            "label": label,
        }
        if linewidth is not None:
            plot_kwargs["linewidth"] = float(linewidth)
        with mpl_style.context(self.component_style):
            line, = self.current_axes.plot(x, y, **plot_kwargs)
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
                "color": color,
                "label": label,
            },
            {
                "x_ref": x_ref.to_dict(),
                "y_ref": y_ref.to_dict(),
            },
        )
        self._add_visible_editor(controller, item_label="plot")
        self.redraw()
        return line

    # Add scatter plot
    def add_scatter(self, x, y, size, color, marker, label, x_ref: ColumnRef, y_ref: ColumnRef,
                    object_id: str | None = None,
                    color_order: int | None = None):
        """Add scatter."""

        color = normalize_color(color)
        object_id = object_id or new_id()
        with mpl_style.context(self.component_style):
            scatter = self.current_axes.scatter(x, y, s=size, c=color, marker=marker, label=label)
        component_order = self._claim_color_order(color_order)
        controller = self._register_chart_controller(
            ScatterController,
            object_id,
            ComponentRole.SCATTER,
            scatter,
            component_order,
            {
                "color": color,
                "edgecolor": color,
                "size": float(size),
                "marker": marker,
                "label": label,
            },
            {
                "x_ref": x_ref.to_dict(),
                "y_ref": y_ref.to_dict(),
            },
        )
        self._add_visible_editor(controller, item_label="scatter")
        self.redraw()
        return scatter

    # Add fit curve
    def add_fit_curve(self, x, y, color, label, x_ref: ColumnRef, y_ref: ColumnRef,
                      engine: str = "Python", fit_type=None,
                      fit_options=None, fit_result=None, expression: str = "",
                      x_start: float | None = None, x_stop: float | None = None,
                      style: str | None = None, object_id: str | None = None,
                      color_order: int | None = None):
        """Add fit curve."""

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
        with mpl_style.context(self.component_style):
            line, = self.current_axes.plot(line_x, line_y, **plot_kwargs)
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
                "engine": engine,
                "fit_type": deepcopy(fit_type),
                "fit_options": deepcopy(fit_options),
                "fit_result": deepcopy(fit_result),
                "expression": expression or "",
                "x_start": float(x_start),
                "x_stop": float(x_stop),
            },
        )
        self._add_visible_editor(
            controller,
            item_label="fitting",
        )
        self.redraw()
        return line

    # Add interpolation curve
    def add_interpolate_curve(self, x, y, x_ref: ColumnRef, y_ref: ColumnRef, method, k=3, label='interpolate',
                              color='black',
                              samples=DEFAULT_INTERPOLATION_SAMPLES,
                              lam=None, lam_auto=True, object_id: str | None = None,
                              color_order: int | None = None, allow_empty: bool = False):
        """Add interpolate curve."""

        color = normalize_color(color)
        with mpl_style.context(self.component_style):
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
            line, = self.current_axes.plot(x_new, y_new, color=color, label=label)
        object_id = object_id or new_id()
        component_order = self._claim_color_order(color_order)
        controller = self._register_chart_controller(
            InterpolationController,
            object_id,
            ComponentRole.INTERPOLATION,
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
                "method": method,
                "k": int(k),
                "samples": int(samples),
                "lam": None if lam is None else float(lam),
                "lam_auto": bool(lam_auto),
            },
        )
        self._add_visible_editor(controller, item_label="interpolate")
        self.redraw()
        if x_new.size:
            status_messages.show_success("Interpolation curve created.")
        else:
            status_messages.show_warning(
                "Interpolation curve has no valid data yet; its editor and style were kept."
            )
        return line

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
        if not result.ok or result.notices:
            self.message_presenter.present(result)
        self._add_visible_editor(controller, item_label="text")
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
        if not result.ok or result.notices:
            self.message_presenter.present(result)
        if self.figure_inspector is not None:
            self._add_visible_editor(controller, item_label="text")
            self.figure_inspector.show_figure_elements()
        self.redraw()
        return text_artist

    def save(self, filename, dpi=None):
        """Save the current figure through the selected destination."""

        if dpi is None:
            save_dpi = self.document_dpi
        else:
            save_dpi = dpi
        with mpl_style.context(self.component_style):
            self.fig.savefig(filename, dpi=save_dpi)

    def dependent_records(self, refs: set[ColumnRef]) -> list[ComponentState]:
        """Return Controller snapshots for table-deletion undo."""

        return self.dependency_service.dependent_states(refs)

    def _restore_component_state(self, state: ComponentState):
        """Materialize one dynamic v6 component and reapply its full state."""

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
        if role is ComponentRole.FUNCTION_CURVE:
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
            pair = (
                self.repository.line_pair(x_ref, y_ref)
                if role is ComponentRole.DATA_PLOT
                else self.repository.valid_pair(x_ref, y_ref)
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
        snapshots: list[ComponentState],
    ) -> None:
        """Remove components captured before a table mutation."""

        self.dependency_service.delete_states(snapshots)

    def restore_data_dependents(
        self,
        snapshots: list[ComponentState],
    ) -> None:
        """Restore components captured before a table mutation."""

        self.dependency_service.restore_states(snapshots)

    def restore_component_tree(
        self,
        component_tree: dict[str, Any] | None = None,
    ) -> None:
        """Materialize and apply a validated v6 component tree directly."""

        source = component_tree or self._restore_component_tree
        if not isinstance(source, dict):
            return
        source = normalize_v6_figure(source)
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
        grouped: dict[int, list[ComponentState]] = {}
        for state in axes_states:
            subplot = state.data["subplot"]
            grouped.setdefault(
                int(subplot["layout_group"]),
                [],
            ).append(state)
        for _group, group_states in sorted(
            grouped.items(),
            key=lambda item: min(
                int(state.selector["index"])
                for state in item[1]
            ),
        ):
            first = group_states[0].data["subplot"]
            ordered_group = sorted(
                group_states,
                key=lambda state: int(state.selector["index"]),
            )
            self.add_axes(
                int(first["nrows"]),
                int(first["ncols"]),
                slots=[
                    int(state.data["subplot"]["slot"])
                    for state in ordered_group
                ],
            )

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

        self.apply_component_tree(source)

    def apply_component_tree(
        self, component_tree: dict[str, Any] | None
    ) -> None:
        """Apply all v6 states after their Matplotlib targets exist."""

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
        """Return the v6 component tree used by project persistence."""

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
        return normalize_v6_figure(snapshot)
