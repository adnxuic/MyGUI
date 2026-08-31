"""Host Matplotlib figures and register their editable components."""

from contextlib import contextmanager
import math
from copy import deepcopy
from functools import partial
from typing import Any, Optional
from PySide6.QtCore import QTimer, Qt, Signal
from PySide6.QtGui import QCursor
from PySide6.QtWidgets import (
    QApplication,
    QLabel,
    QMenu,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QStyle,
    QVBoxLayout,
    QWidget,
)

from mygui.widgets.fig_control_window.figure_inspector import (
    FigureInspectorPanel,
)
from mygui.widgets.fig_control_window.component_editors import (
    ComponentEditorManager,
    EditorContext,
    EditorRegistry,
    MessagePresenter,
    register_production_profiles,
)
from mygui.figuremodify.component_services import (
    AnnotationService,
    AxesCommandService,
    AxesGeometryService,
    AxisTickSettingsService,
    ChartDataService,
    ColorbarService,
    ColorConsumptionLedger,
    ComponentDeletionService,
    ComponentDependencySnapshot,
    ComponentDependencyService,
    DeleteReason,
    DeletionRequest,
    ErrorBarDataService,
    Field2DService,
    default_field_2d_properties,
    FitService,
    FunctionCurveService,
    InterpolationService,
    ReferenceGuideService,
    ReferenceMarksService,
    SecondaryAxisCreateSpec,
    SecondaryAxisService,
    TextRenderService,
    resolve_errorbar_data,
)
from mygui.figuremodify.history import FigureHistoryService
from mygui.widgets.figure_canvas.deletion_coordinator import DeletionCoordinator
from mygui.widgets.figure_canvas.project_metadata import ProjectMetadataPort
from mygui.widgets.figure_canvas.component_materializers import (
    ComponentMaterializerRegistry,
)
from mygui.widgets.figure_canvas.canvas_popout import (
    CanvasPopoutWindow as _CanvasPopoutWindow,
)
from mygui.widgets.figure_canvas.canvas_toolbar import (
    ProjectNavigationToolbar as _ProjectNavigationToolbar,
    history_command as _history_command,
)
from mygui.widgets.figure_canvas.chart_creation import (
    ChartBatchCreationResult,
    ChartCreationStager,
    PreparedChartSeries,
    PreparedErrorBarSeries,
)
from mygui.widgets.figure_canvas.canvas_materialize_handlers import (
    materialize_colorbar,
    materialize_data_plot,
    materialize_errorbar,
    materialize_field_2d,
    materialize_fit,
    materialize_function_curve,
    materialize_image_in_axes,
    materialize_interpolation,
    materialize_line,
    materialize_reference_band,
    materialize_reference_line,
    materialize_reference_marks,
    materialize_secondary_axis,
    materialize_scatter,
    materialize_annotation,
    materialize_text,
    materialize_zoom_in_axes,
    materializer_pair,
    register_canvas_materializers,
)
from mygui.widgets.figure_canvas.canvas_snapshot import (
    CanvasSnapshotApplier,
    component_paths_from_tree,
    json_component_value,
)
from mygui.figuremodify.components import (
    AnnotationController,
    AxesController,
    ComponentEvent,
    ComponentEventKind,
    ComponentKind,
    ComponentRegistry,
    ComponentRole,
    ComponentState,
    ColorbarController,
    SecondaryAxisController,
    ContourController,
    FigureController,
    FitCurveController,
    FitEngine,
    FunctionCurveController,
    HeatmapController,
    ImageInAxesController,
    LineController,
    ObserverFailure,
    PseudocolorController,
    ReferenceBandController,
    ReferenceLineController,
    ReferenceMarksController,
    ScatterController,
    TextController,
    UpdateImpact,
    ZoomInAxesController,
    create_semantic_children,
    decode_in_axes_image,
    validate_controller_contracts,
)
from mygui.figuremodify.services.annotation import annotation_artist_kwargs
from mygui.figuremodify.components.serialization import (
    deterministic_component_id,
    normalize_v23_figure,
    validate_v23_figure,
)
from mygui.figuremodify.axes_layout import AxesLayoutSpec
from mygui.figuremodify.axes_geometry import grid_geometry_record
from mygui.figuremodify.axes_layout_service import AxesLayoutService
from mygui.figuremodify.in_axes import (
    ImageInAxesCreateSpec,
    InAxesCreateSpec,
    InAxesService,
    ZoomInAxesCreateSpec,
)

from mygui import tex_config
from mygui import status_messages
from mygui.figure_export import (
    FigureExportContext,
    FigureExportRequest,
    compatible_export_request,
    publish_export_file,
)
from mygui.database import (
    ColumnRef,
    DataPreprocessSpec,
    FitInputRangeSpec,
    TableChangeSet,
    TableRepository,
    resolve_preprocessed_pair,
    select_fit_input_pair,
    validate_component_name,
)
from mygui.database.table_document import new_id
from mygui.database.interpolate_func import (
    DEFAULT_INTERPOLATION_SAMPLES,
    interpolate_curve,
)
from mygui.database.safe_expression import (
    GENERATED_FIT_EXPRESSION_LIMITS,
    evaluate_curve_expression,
)
from mygui.widgets.common_widget.min_widget.color_library import ColorLibrary
from mygui.figuremodify.style_base.color_models import (
    ColorCycleState,
    ColorSelection,
    normalize_color,
)
from mygui.figuremodify.style_base.creation_defaults import (
    ComponentCreationDefaults,
    resolve_component_creation_defaults,
)
from mygui.figuremodify.style_base.creation_preferences import (
    ResolvedAxesAppearance,
    ResolvedErrorBarAppearance,
    ResolvedLineAppearance,
    ResolvedScatterAppearance,
    ResolvedTextAppearance,
    resolve_errorbar_appearance,
    resolve_line_appearance,
    resolve_scatter_appearance,
    resolve_text_appearance,
)
from mygui.figuremodify.matplotlib_adapter import matplotlib_style_context

from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure
from matplotlib.axes import Axes

import numpy as np


class _ControllerAwareFigureCanvas(FigureCanvasQTAgg):
    """Run controller-owned runtime synchronization before each render."""

    def __init__(self, figure: Figure, *, before_draw) -> None:
        self._before_draw = before_draw
        self._synchronizing_before_draw = False
        super().__init__(figure)

    def set_before_draw(self, callback) -> None:
        self._before_draw = callback

    def draw(self) -> None:
        callback = self._before_draw
        if callable(callback) and not self._synchronizing_before_draw:
            self._synchronizing_before_draw = True
            try:
                callback()
            finally:
                self._synchronizing_before_draw = False
        super().draw()


class PyFigureCanvas(QWidget):
    """Provide the py figure canvas Qt widget."""

    componentSelectionChanged = Signal(str)
    exportRequested = Signal(object)

    def __init__(
        self,
        parent=None,
        width=4,
        height=3,
        dpi=200,
        style=None,
        repository: TableRepository | None = None,
        project_id: str | None = None,
        project_metadata: ProjectMetadataPort | None = None,
        project_path: str | None = None,
        color_library: ColorLibrary | None = None,
        component_tree: dict[str, Any] | None = None,
    ):
        super().__init__(parent)
        self.figure_window = parent if hasattr(parent, "current_canva") else None
        if repository is None or project_id is None:
            raise ValueError("PyFigureCanvas requires a repository and project id.")
        if project_metadata is None:
            raise ValueError("PyFigureCanvas requires project metadata services.")
        self.repository = repository
        self.project_id = str(project_id)
        self.repository.project(self.project_id)
        self.project_metadata = project_metadata
        self.style = style
        self.project_path = project_path
        self._disposed = False
        self._canvas_popout_window: _CanvasPopoutWindow | None = None
        self._canvas_focus_return: QWidget | None = None
        self._canvas_scroll_return: tuple[int, int] | None = None
        self._tex_render_listener = None
        self._restoring_component_tree_now = False
        self._selection_repair_pending = False
        if color_library is None:
            raise ValueError("PyFigureCanvas requires the shared ColorLibrary.")
        self.color_library = color_library
        self._component_id_overrides = self._component_paths_from_tree(
            component_tree
        )
        self._allocated_component_ids: set[str] = set()
        self._restore_component_tree = (
            deepcopy(component_tree)
            if isinstance(component_tree, dict)
            else None
        )
        with matplotlib_style_context(style):
            self.fig = Figure(figsize=(width, height), dpi=dpi)
        # QtAgg scales ``Figure.dpi`` to the active screen's device pixel
        # ratio.  Keep the user/project DPI separate so that moving the
        # window between screens cannot change exports or project files.
        self._document_dpi = float(self.fig.dpi)
        self.component_registry = ComponentRegistry()
        self._observer_failures: list[ObserverFailure] = []
        self._observer_warning_scheduled = False
        self.component_registry.set_observer_failure_handler(
            self._queue_observer_failures
        )
        self.component_materializers = ComponentMaterializerRegistry()
        materializer_contracts = validate_controller_contracts()
        self.editor_registry = EditorRegistry()
        register_production_profiles(self.editor_registry)
        self.axes_commands = AxesCommandService(self.component_registry)
        self.axes_layout_service = AxesLayoutService(self)
        self.axis_tick_settings_service = AxisTickSettingsService(
            self.component_registry,
            linked_axes=self.axes_layout_service.linked_axes,
        )
        self.axes_geometry_service = AxesGeometryService(self)
        self.function_curve_service = FunctionCurveService(
            self.component_registry
        )
        self.chart_data_service = ChartDataService(
            self.repository,
            self.component_registry,
        )
        self.errorbar_service = ErrorBarDataService(
            self.repository,
            self.component_registry,
        )
        self.colorbar_service = ColorbarService(
            self.component_registry,
            geometry_service=self.axes_geometry_service,
        )
        self.secondary_axis_service = SecondaryAxisService(
            self.component_registry,
            warning_callback=status_messages.show_warning,
        )
        self.field_2d_service = Field2DService(
            self.repository,
            self.component_registry,
            colorbar_service=self.colorbar_service,
        )
        self.reference_marks_service = ReferenceMarksService(
            self.component_registry,
            self.repository,
            self.project_id,
        )
        self.reference_guide_service = ReferenceGuideService(
            self.component_registry
        )
        self.chart_data_service.colorbar_service = self.colorbar_service
        self.interpolation_service = InterpolationService(
            self.repository,
            self.component_registry,
        )
        self.chart_data_service.interpolation_service = self.interpolation_service
        self.fit_service = FitService(
            self.repository,
            self.component_registry,
        )
        self.text_render_service = TextRenderService(
            self.component_registry
        )
        self.annotation_service = AnnotationService(
            self.component_registry,
            text_render_service=self.text_render_service,
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
        self.color_consumption_ledger = ColorConsumptionLedger()
        self._chart_stager = ChartCreationStager(self)
        self._snapshot_applier = CanvasSnapshotApplier(self)
        self.deletion_service = ComponentDeletionService(
            self.component_registry,
            color_ledger=self.color_consumption_ledger,
        )
        self.deletion_coordinator = DeletionCoordinator(self)
        self.figure_history = FigureHistoryService(
            repository=self.repository,
            project_id=self.project_id,
            canvas=self,
            registry=self.component_registry,
        )
        self._register_component_materializers(materializer_contracts)
        self.editor_registry.freeze()
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
            axis_ticks=self.axis_tick_settings_service,
            axes_layout=self.axes_layout_service,
            axes_geometry=self.axes_geometry_service,
            function_curves=self.function_curve_service,
            chart_data=self.chart_data_service,
            errorbars=self.errorbar_service,
            interpolation=self.interpolation_service,
            fitting=self.fit_service,
            text_rendering=self.text_render_service,
            colorbars=self.colorbar_service,
            secondary_axes=self.secondary_axis_service,
            field_2d=self.field_2d_service,
            reference_marks=self.reference_marks_service,
            reference_guides=self.reference_guide_service,
            annotations=self.annotation_service,
            in_axes=self.in_axes_service,
            dependency_service=self.dependency_service,
            delete_command=self.delete_components,
            history=self.figure_history,
            project_id=self.project_id,
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
        self.figure_inspector: Optional[FigureInspectorPanel] = None

        self.current_axes_component_id: str | None = None
        self.current_component_id: str | None = None
        self._selection_unsubscribe = self.component_registry.subscribe(
            self._component_selection_event,
            kinds=(ComponentEventKind.REMOVED,),
        )
        self.repository.transaction_committed.connect(self._table_changed)

        self.canva = _ControllerAwareFigureCanvas(
            self.fig,
            before_draw=self._synchronize_before_draw,
        )
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
        self._button_press_cid = self.canva.mpl_connect(
            "button_press_event",
            self._on_mpl_button_press,
        )

        # Add scroll area
        self.scroArea = QScrollArea()
        self.scroArea.setWidget(self.canva)
        self.scroArea.setAlignment(Qt.AlignCenter)
        self.scroArea.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)  # Set scroll bar visibility policy
        self.scroArea.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)  # Set scroll bar visibility policy

        self._canvas_content_stack = QStackedWidget(self)
        self._canvas_content_stack.setObjectName("figure_canvas_content_stack")
        self._canvas_popout_placeholder = QLabel(
            "Canvas is open in a separate window.",
            self._canvas_content_stack,
        )
        self._canvas_popout_placeholder.setObjectName(
            "figure_popout_placeholder"
        )
        self._canvas_popout_placeholder.setAlignment(Qt.AlignCenter)
        self._canvas_popout_placeholder.setWordWrap(True)
        self._canvas_content_stack.addWidget(self.scroArea)
        self._canvas_content_stack.addWidget(self._canvas_popout_placeholder)
        self._canvas_content_stack.setCurrentWidget(self.scroArea)

        layout = QVBoxLayout()

        toolbox = _ProjectNavigationToolbar(
            self.canva,
            self,
            self.figure_history,
        )
        self.navigation_toolbar = toolbox
        toolbox.setObjectName("figure_toolbar")
        toolbox.addSeparator()
        stack = self.repository.undo_stack(self.project_id)
        self.undo_action = stack.createUndoAction(self, "Undo")
        self.redo_action = stack.createRedoAction(self, "Redo")
        self.undo_action.setObjectName("figure_undo_action")
        self.redo_action.setObjectName("figure_redo_action")
        toolbox.addAction(self.undo_action)
        toolbox.addAction(self.redo_action)

        toolbar_spacer = QWidget(toolbox)
        toolbar_spacer.setObjectName("figure_toolbar_spacer")
        toolbar_spacer.setSizePolicy(
            QSizePolicy.Expanding,
            QSizePolicy.Preferred,
        )
        toolbox.addWidget(toolbar_spacer)
        popout_description = "Open canvas in large window"
        popout_icon = toolbox.style().standardIcon(
            QStyle.SP_TitleBarMaxButton
        )
        self.popout_action = toolbox.addAction(
            popout_icon,
            "Open Canvas Window",
        )
        self.popout_action.setObjectName("figure_popout_action")
        self.popout_action.setToolTip(popout_description)
        self.popout_action.setStatusTip(popout_description)
        self.popout_action.triggered.connect(self.open_canvas_window)
        popout_button = toolbox.widgetForAction(self.popout_action)
        if popout_button is not None:
            popout_button.setObjectName("figure_popout_button")
            popout_button.setAccessibleName(popout_description)
            popout_button.setToolTip(popout_description)

        layout.addWidget(toolbox)
        layout.addWidget(self._canvas_content_stack)

        self.setLayout(layout)
        self._tex_render_listener = self._tex_runtime_changed
        tex_config.register_tex_render_listener(self._tex_render_listener)

    @property
    def project_name(self) -> str:
        """Return the authoritative repository project name."""

        return self.repository.project(self.project_id).name

    def _canvas_window_title(self, project_name: str | None = None) -> str:
        """Return the native title for this project's Canvas window."""

        name = self.project_name if project_name is None else project_name
        return f"{name} — Canvas"

    def _canvas_scroll_position(self) -> tuple[int, int]:
        """Return the current Canvas viewport scroll offsets."""

        return (
            self.scroArea.horizontalScrollBar().value(),
            self.scroArea.verticalScrollBar().value(),
        )

    def _apply_canvas_scroll_position(
        self,
        position: tuple[int, int] | None,
    ) -> None:
        """Restore Canvas viewport scroll offsets when one was recorded."""

        if position is None or self._disposed:
            return
        try:
            self.scroArea.horizontalScrollBar().setValue(position[0])
            self.scroArea.verticalScrollBar().setValue(position[1])
        except RuntimeError:
            # The project was released before the queued restore ran.
            return

    def open_canvas_window(self) -> None:
        """Show the unique live Canvas in one maximized non-modal window."""

        if self._disposed:
            return
        existing = self._canvas_popout_window
        if existing is not None:
            if existing.isMinimized() or not existing.isVisible():
                existing.showMaximized()
            existing.raise_()
            existing.activateWindow()
            self.canva.setFocus(Qt.OtherFocusReason)
            return

        focus_widget = QApplication.focusWidget()
        if focus_widget is not None and (
            focus_widget is self or self.isAncestorOf(focus_widget)
        ):
            self._canvas_focus_return = focus_widget
        else:
            self._canvas_focus_return = None

        window = _CanvasPopoutWindow(self)
        window.setWindowTitle(self._canvas_window_title())
        self._canvas_popout_window = window
        source_size = self._canvas_content_stack.size()
        self._canvas_scroll_return = self._canvas_scroll_position()
        try:
            self._canvas_content_stack.setCurrentWidget(
                self._canvas_popout_placeholder
            )
            self._canvas_content_stack.removeWidget(self.scroArea)
            window.attach_content(self.scroArea)
            # Seed the geometry the window returns to when the user restores
            # it down from the initial maximized state.
            window.resize(
                max(640, source_size.width()),
                max(480, source_size.height()),
            )
            window.showMaximized()
            window.raise_()
            window.activateWindow()
            self.canva.setFocus(Qt.OtherFocusReason)
        except Exception:
            self._restore_canvas_from_popout(window)
            window.hide()
            raise

    def _restore_canvas_from_popout(
        self,
        window: _CanvasPopoutWindow,
    ) -> None:
        """Restore the unique Canvas scroll area to its project tab."""

        if window.canvas_returned:
            return
        content = window.release_content()
        if (
            content is None
            and self._canvas_content_stack.indexOf(self.scroArea) < 0
        ):
            content = self.scroArea
        scroll_return = self._canvas_scroll_return
        self._canvas_scroll_return = None
        if content is not None:
            if content is not self.scroArea:
                raise RuntimeError("The Canvas popout returned unknown content.")
            if self._canvas_content_stack.indexOf(content) < 0:
                self._canvas_content_stack.insertWidget(0, content)
            self._canvas_content_stack.setCurrentWidget(content)
            content.setVisible(True)
            self._apply_canvas_scroll_position(scroll_return)
            if scroll_return is not None:
                # The viewport regains its tab geometry, and with it the scroll
                # bars that define the offset ranges, only during the following
                # layout pass; restore again once those ranges are final.
                QTimer.singleShot(
                    0,
                    partial(self._apply_canvas_scroll_position, scroll_return),
                )

        if self._canvas_popout_window is window:
            self._canvas_popout_window = None
        if not self._disposed and self._canvas_focus_return is not None:
            try:
                self._canvas_focus_return.setFocus(Qt.OtherFocusReason)
            except RuntimeError:
                pass
        self._canvas_focus_return = None
        window.deleteLater()

    def _close_canvas_window(self) -> None:
        """Close and restore this project's Canvas popout idempotently."""

        window = self._canvas_popout_window
        if window is None:
            return
        window.close()
        if self._canvas_popout_window is window:
            self._restore_canvas_from_popout(window)
            window.hide()

    @property
    def current_axes(self) -> Axes | None:
        """Resolve the selected Axes from the Registry, never a mirror."""

        component_id = self.current_axes_component_id
        if component_id is None or component_id not in self.component_registry:
            return None
        target = self.component_registry.resolve_target(component_id)
        return target if isinstance(target, Axes) else None

    @property
    def has_current_axes(self) -> bool:
        """Return whether the authoritative Axes selection is usable."""

        component_id = self.current_axes_component_id
        if component_id is None or component_id not in self.component_registry:
            return False
        return (
            self.component_registry.get(component_id).state.kind
            is ComponentKind.AXES
        )

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
            self.project_metadata.apply_controller_name(
                self.project_id,
                name,
            )
            if self._canvas_popout_window is not None:
                self._canvas_popout_window.setWindowTitle(
                    self._canvas_window_title(name)
                )
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

    def _component_defaults_provider(self):
        window = self.figure_window
        if window is None:
            return None
        return getattr(window, "component_defaults_provider", None)

    def _read_component_defaults(self):
        """Read Components defaults at use time. Restore paths never call this."""

        if self._restoring_component_tree_now:
            return None
        provider = self._component_defaults_provider()
        if provider is None:
            return None
        try:
            return provider.current()
        except Exception:
            status_messages.show_warning(
                "Component creation defaults could not be read; "
                "using Figure style and Axes palette instead."
            )
            return None

    def _palette_selection_for_creation(self) -> ColorSelection:
        try:
            return self.creation_color_cycle().peek()
        except (TypeError, ValueError, AttributeError):
            return ColorSelection("#1F77B4")

    def _line_sync_properties(self, line, *, color: str, label: str) -> dict[str, Any]:
        return {
            "linestyle": line.get_linestyle(),
            "linewidth": float(line.get_linewidth()),
            "marker": line.get_marker(),
            "markersize": float(line.get_markersize()),
            "markeredgewidth": float(line.get_markeredgewidth()),
            "color": color,
            "label": label,
        }

    def _commit_resolved_line_color(
        self,
        resolved: ResolvedLineAppearance | ResolvedScatterAppearance,
        color_selection: ColorSelection | None,
        preview_cycle: ColorCycleState | None,
    ) -> tuple[ColorSelection | None, ColorCycleState | None]:
        commit_selection = color_selection
        if commit_selection is None and resolved.consume_palette:
            commit_selection = resolved.color_selection
        cycle = preview_cycle
        if cycle is None and resolved.consume_palette:
            try:
                cycle = self.creation_color_cycle()
            except (TypeError, ValueError, AttributeError):
                cycle = None
        return commit_selection, cycle

    def _user_line_plot_plan(
        self,
        *,
        label: str,
        color=None,
        color_selection: ColorSelection | None = None,
        preview_cycle: ColorCycleState | None = None,
        linestyle=None,
        linewidth=None,
        marker=None,
        markersize=None,
        markeredgewidth=None,
    ) -> tuple[dict[str, Any], str, ColorSelection | None, ColorCycleState | None]:
        """Resolve user-creation Line kwargs. Restore omits unspecified fields."""

        if self._restoring_component_tree_now:
            kwargs: dict[str, Any] = {"label": label}
            if linestyle is not None:
                kwargs["linestyle"] = linestyle
            if color is not None:
                kwargs["color"] = normalize_color(color)
            elif color_selection is not None:
                kwargs["color"] = color_selection.color
            if linewidth is not None:
                kwargs["linewidth"] = float(linewidth)
            if marker is not None:
                kwargs["marker"] = marker
            if markersize is not None:
                kwargs["markersize"] = float(markersize)
            if markeredgewidth is not None:
                kwargs["markeredgewidth"] = float(markeredgewidth)
            return kwargs, str(kwargs.get("color", "#000000")), color_selection, preview_cycle
        resolved = self._resolve_line_creation(
            settings=self._read_component_defaults(),
            color=color,
            color_selection=color_selection,
            linestyle=linestyle,
            linewidth=linewidth,
            marker=marker,
            markersize=markersize,
            markeredgewidth=markeredgewidth,
        )
        commit_selection, cycle = self._commit_resolved_line_color(
            resolved, color_selection, preview_cycle
        )
        return resolved.plot_kwargs(label=label), resolved.color, commit_selection, cycle

    def _shared_line_fields(
        self,
        *,
        linestyle=None,
        linewidth=None,
        marker=None,
        markersize=None,
        markeredgewidth=None,
    ) -> tuple[Any, float | None, Any, float | None, float | None]:
        """Resolve shared non-color Line fields once for a batch."""

        if self._restoring_component_tree_now:
            return linestyle, linewidth, marker, markersize, markeredgewidth
        resolved = self._resolve_line_creation(
            settings=self._read_component_defaults(),
            color="#000000",
            linestyle=linestyle,
            linewidth=linewidth,
            marker=marker,
            markersize=markersize,
            markeredgewidth=markeredgewidth,
        )
        return (
            resolved.linestyle,
            resolved.linewidth,
            resolved.marker,
            resolved.markersize,
            resolved.markeredgewidth,
        )

    def _resolve_line_creation(
        self,
        *,
        settings=None,
        color=None,
        color_selection: ColorSelection | None = None,
        linestyle=None,
        linewidth=None,
        marker=None,
        markersize=None,
        markeredgewidth=None,
    ) -> ResolvedLineAppearance:
        style = self.component_creation_defaults().line
        palette = self._palette_selection_for_creation()
        return resolve_line_appearance(
            style,
            settings,
            palette_selection=palette,
            color=color,
            color_selection=color_selection,
            linestyle=linestyle,
            linewidth=linewidth,
            marker=marker,
            markersize=markersize,
            markeredgewidth=markeredgewidth,
        )

    def _resolve_scatter_creation(
        self,
        *,
        settings=None,
        color=None,
        color_selection: ColorSelection | None = None,
        marker=None,
        size=None,
        linewidth=None,
    ) -> ResolvedScatterAppearance:
        style = self.component_creation_defaults().scatter
        palette = self._palette_selection_for_creation()
        return resolve_scatter_appearance(
            style,
            settings,
            palette_selection=palette,
            color=color,
            color_selection=color_selection,
            marker=marker,
            size=size,
            linewidth=linewidth,
        )

    def _resolve_errorbar_creation(
        self,
        *,
        settings=None,
        color=None,
        color_selection: ColorSelection | None = None,
        linestyle=None,
        linewidth=None,
        marker=None,
        markersize=None,
        markeredgewidth=None,
        markerfacecoloralt=None,
        fillstyle=None,
        drawstyle=None,
        antialiased=None,
        ecolor=None,
        elinewidth=None,
        capsize=None,
        capthick=None,
        error_linestyle=None,
        error_capstyle=None,
        error_antialiased=None,
        errorevery=None,
        lolims=None,
        uplims=None,
        xlolims=None,
        xuplims=None,
        barsabove=None,
    ) -> ResolvedErrorBarAppearance:
        defaults = self.component_creation_defaults()
        palette = self._palette_selection_for_creation()
        return resolve_errorbar_appearance(
            defaults.line,
            defaults.error_bar,
            settings,
            palette_selection=palette,
            color=color,
            color_selection=color_selection,
            linestyle=linestyle,
            linewidth=linewidth,
            marker=marker,
            markersize=markersize,
            markeredgewidth=markeredgewidth,
            markerfacecoloralt=markerfacecoloralt,
            fillstyle=fillstyle,
            drawstyle=drawstyle,
            antialiased=antialiased,
            ecolor=ecolor,
            elinewidth=elinewidth,
            capsize=capsize,
            capthick=capthick,
            error_linestyle=error_linestyle,
            error_capstyle=error_capstyle,
            error_antialiased=error_antialiased,
            errorevery=errorevery,
            lolims=lolims,
            uplims=uplims,
            xlolims=xlolims,
            xuplims=xuplims,
            barsabove=barsabove,
        )

    def _resolve_text_creation(
        self,
        *,
        settings=None,
        fontfamily=None,
        fontsize=None,
        color=None,
        fontweight=None,
        fontstyle=None,
    ) -> ResolvedTextAppearance:
        style = self.component_creation_defaults().text
        return resolve_text_appearance(
            style,
            settings,
            fontfamily=fontfamily,
            fontsize=fontsize,
            color=color,
            fontweight=fontweight,
            fontstyle=fontstyle,
        )

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
            controller.state.kind
            in {
                ComponentKind.LINE,
                ComponentKind.SCATTER,
                ComponentKind.ERRORBAR,
            }
            for controller in self.component_registry.children(axes_id)
        )

    def _component_id(self, semantic_path: str) -> str:
        candidate = self._component_id_overrides.get(
            semantic_path,
            deterministic_component_id(self.project_id, semantic_path),
        )
        while candidate in self._allocated_component_ids or (
            hasattr(self, "component_registry") and candidate in self.component_registry
        ):
            candidate = new_id()
        self._allocated_component_ids.add(candidate)
        return candidate

    @staticmethod
    def _component_paths_from_tree(
        component_tree: dict[str, Any] | None,
    ) -> dict[str, str]:
        """Map fixed semantic paths to IDs from a validated component tree."""

        return component_paths_from_tree(component_tree)

    def _source_component_state(
        self, component_id: str
    ) -> ComponentState | None:
        tree = self._restore_component_tree
        if not isinstance(tree, dict):
            return None
        for raw_state in tree.get("components", []):
            if isinstance(raw_state, dict) and raw_state.get("id") == component_id:
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
                "autoscalex_on": bool(axe.get_autoscalex_on()),
                "autoscaley_on": bool(axe.get_autoscaley_on()),
                "color_cycle": None,
            },
            data={
                "subplot": deepcopy(subplot),
                "geometry": grid_geometry_record(),
            },
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
        axes_id = self.current_axes_component_id
        if axes_id is None:
            raise ValueError("Select an axes before registering a chart.")
        if controller_type.KIND is None or role not in controller_type.ROLES:
            raise ValueError(
                f"Controller {controller_type.__name__} does not support "
                f"role {role.value}."
            )
        state = ComponentState(
            id=component_id,
            kind=controller_type.KIND,
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
                "coordinate_system": "figure" if scope == "figure" else "data",
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

    def update_current_axes(self, component_id: str) -> None:
        """Select an Axes by stable component ID and show its Inspector."""

        if not isinstance(component_id, str):
            raise TypeError("Current axes must be selected by component ID.")
        controller = self.component_registry.get(component_id)
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
        self.update_current_axes(controller.component_id)

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

    def _synchronize_before_draw(self) -> None:
        """Replay dynamic primary and Secondary Axis runtime styles."""

        self.axis_tick_settings_service.reapply_runtime_styles()
        self.secondary_axis_service.reapply_runtime_styles()

    def cancel_pending_draw(self):
        """Cancel a queued redraw that has not reached the canvas yet."""

        if hasattr(self.canva, "_draw_pending"):
            self.canva._draw_pending = False

    def dispose(self) -> None:
        """Idempotently detach project callbacks and editor resources."""

        if self._disposed:
            return
        self._disposed = True
        self._close_canvas_window()
        if self._tex_render_listener is not None:
            tex_config.unregister_tex_render_listener(
                self._tex_render_listener
            )
            self._tex_render_listener = None
        self.cancel_pending_draw()
        self.canva.set_before_draw(None)
        try:
            self.repository.transaction_committed.disconnect(self._table_changed)
        except (RuntimeError, TypeError):
            pass
        if self._selection_unsubscribe is not None:
            self._selection_unsubscribe()
            self._selection_unsubscribe = None
        if self._button_press_cid is not None:
            try:
                self.canva.mpl_disconnect(self._button_press_cid)
            except Exception:
                pass
            self._button_press_cid = None
        self.figure_history.dispose()
        self.message_presenter.close()
        self.component_registry.set_observer_failure_handler(None)
        self.component_editor_manager.close()
        self.axes_layout_service.dispose()
        self.axes_geometry_service.dispose()
        self.in_axes_service.dispose()

    def _tex_runtime_changed(
        self,
        change: tex_config.TexRuntimeChange,
    ) -> str | None:
        """Apply global TeX runtime changes through TextRenderService."""

        if self._disposed:
            return None
        result = self.text_render_service.apply_tex_availability(
            change.after.enabled,
            force=change.preamble_changed and change.after.enabled,
        )
        if not result.committed:
            self.message_presenter.discard_pending()
            return result.message
        return None

    def closeEvent(self, event):
        """Handle Qt close events and release owned resources."""

        self.dispose()
        super().closeEvent(event)

    def _table_changed(self, changes: TableChangeSet):
        if changes.project_id != self.project_id:
            return
        with self.figure_history.suspend_recording():
            results = self.chart_data_service.refresh_affected(
                changes.changed_columns
            )
            results.extend(
                self.errorbar_service.refresh_affected(
                    changes.changed_columns
                )
            )
            results.extend(
                self.field_2d_service.refresh_affected(
                    changes.changed_columns
                )
            )
            results.extend(
                self.reference_marks_service.refresh_affected(
                    changes.changed_columns
                )
            )
            pending_fits = self.fit_service.mark_sources_changed(
                changes.changed_columns
            )
        self._observer_failures.extend(
            self.chart_data_service.drain_observer_failures()
        )
        self._observer_failures.extend(
            self.errorbar_service.drain_observer_failures()
        )
        self._observer_failures.extend(
            self.field_2d_service.drain_observer_failures()
        )
        self._observer_failures.extend(
            self.fit_service.drain_observer_failures()
        )
        failures = [result for result in results if not result.ok]
        warnings = [
            result
            for result in results
            if result.ok and result.notices
        ]
        if failures or self._observer_failures:
            self.message_presenter.discard_pending()
            count = len(failures) + len(self._observer_failures)
            details = []
            if failures:
                details.append(failures[0].message or "component refresh rejected")
            if self._observer_failures:
                failure = self._observer_failures[0]
                details.append(
                    f"{failure.source} {failure.phase}: {failure.error}"
                )
            self._observer_failures.clear()
            self._observer_warning_scheduled = False
            status_messages.show_warning(
                f"{count} component refresh operation(s) reported a problem: "
                + "; ".join(details)
            )
        elif warnings:
            self.message_presenter.present(warnings[0])
        elif pending_fits:
            status_messages.show_warning(
                f"{len(pending_fits)} fit result(s) use changed source data; "
                "run fitting again to refresh them."
            )

    def _queue_observer_failures(
        self,
        failures: tuple[ObserverFailure, ...],
    ) -> None:
        """Coalesce Registry observer failures into one Canvas warning."""

        self._observer_failures.extend(failures)
        if self._observer_warning_scheduled:
            return
        self._observer_warning_scheduled = True
        QTimer.singleShot(0, self._flush_observer_failures)

    def _flush_observer_failures(self) -> None:
        self._observer_warning_scheduled = False
        if self._disposed or not self._observer_failures:
            return
        failures, self._observer_failures = self._observer_failures, []
        first = failures[0]
        component = (
            f" component={first.component_id}"
            if first.component_id is not None
            else ""
        )
        status_messages.show_warning(
            f"{len(failures)} component observer failure(s) were isolated; "
            f"source={first.source} phase={first.phase}{component}: "
            f"{first.error}"
        )

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
            if controller.state.kind
            in {
                ComponentKind.LINE,
                ComponentKind.SCATTER,
                ComponentKind.ERRORBAR,
                ComponentKind.FIELD_2D,
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

    def _finish_created_component(self, controller) -> None:
        """Publish selection and one redraw after a single creation commits."""

        if self._restoring_component_tree_now:
            return
        self._select_created_component(controller)
        self.redraw()

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
        return self._chart_stager.normalize_batch_refs(x_ref, y_refs)

    def _batch_series_labels(
        self,
        y_refs: tuple[ColumnRef, ...],
    ) -> tuple[str, ...]:
        return self._chart_stager.batch_series_labels(y_refs)

    def _batch_color_plan(
        self,
        selection: ColorSelection,
        count: int,
    ) -> tuple[
        tuple[str, ...],
        dict[str, Any] | None,
        bool,
        tuple[tuple[dict[str, Any] | None, dict[str, Any]], ...],
    ]:
        return self._chart_stager.batch_color_plan(selection, count)

    def _prepare_data_batch(
        self,
        x_ref: ColumnRef,
        y_refs,
        preprocess: DataPreprocessSpec | dict[str, Any] | None,
        color_selection: ColorSelection,
        *,
        preserve_gaps: bool,
        consume_palette: bool = True,
    ) -> tuple[
        tuple[PreparedChartSeries, ...],
        dict[str, Any] | None,
        bool,
        tuple[tuple[dict[str, Any] | None, dict[str, Any]], ...],
    ]:
        return self._chart_stager.prepare_data_batch(
            x_ref,
            y_refs,
            preprocess,
            color_selection,
            preserve_gaps=preserve_gaps,
            consume_palette=consume_palette,
        )

    def _stage_plot(
        self,
        transaction,
        series: PreparedChartSeries,
        *,
        style,
        size,
        linewidth: float | None,
        preprocess: DataPreprocessSpec,
        object_id: str | None = None,
        color_order: int | None = None,
        marker=None,
        markeredgewidth: float | None = None,
    ):
        return self._chart_stager.stage_plot(
            transaction,
            series,
            style=style,
            size=size,
            linewidth=linewidth,
            preprocess=preprocess,
            object_id=object_id,
            color_order=color_order,
            marker=marker,
            markeredgewidth=markeredgewidth,
        )

    def _stage_scatter(
        self,
        transaction,
        series: PreparedChartSeries,
        *,
        size,
        marker,
        preprocess: DataPreprocessSpec,
        color_ref: ColumnRef | None = None,
        size_ref: ColumnRef | None = None,
        color_mapping: dict[str, Any] | None = None,
        size_mapping: dict[str, Any] | None = None,
        object_id: str | None = None,
        color_order: int | None = None,
        linewidth: float | None = None,
    ):
        return self._chart_stager.stage_scatter(
            transaction,
            series,
            size=size,
            marker=marker,
            preprocess=preprocess,
            color_ref=color_ref,
            size_ref=size_ref,
            color_mapping=color_mapping,
            size_mapping=size_mapping,
            object_id=object_id,
            color_order=color_order,
            linewidth=linewidth,
        )

    def _stage_interpolation(
        self,
        transaction,
        series: PreparedChartSeries,
        *,
        method,
        k: int,
        samples: int,
        lam: float | None,
        lam_auto: bool,
        preprocess: DataPreprocessSpec,
        object_id: str | None = None,
        color_order: int | None = None,
        linestyle=None,
        linewidth: float | None = None,
        marker=None,
        markersize: float | None = None,
        markeredgewidth: float | None = None,
    ):
        return self._chart_stager.stage_interpolation(
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
            linestyle=linestyle,
            linewidth=linewidth,
            marker=marker,
            markersize=markersize,
            markeredgewidth=markeredgewidth,
        )

    def _stage_errorbar(
        self,
        transaction,
        series: PreparedErrorBarSeries,
        *,
        appearance: ResolvedErrorBarAppearance,
        object_id: str | None = None,
        color_order: int | None = None,
    ):
        return self._chart_stager.stage_errorbar(
            transaction,
            series,
            appearance=appearance,
            object_id=object_id,
            color_order=color_order,
        )

    def _commit_chart_batch(
        self,
        prepared: tuple[PreparedChartSeries, ...],
        stage,
        *,
        final_cycle: dict[str, Any] | None,
        commit_cycle: bool,
        color_transitions: tuple[tuple[dict[str, Any] | None, dict[str, Any]], ...],
        record_recent: bool = True,
    ) -> ChartBatchCreationResult:
        return self._chart_stager.commit_chart_batch(
            prepared,
            stage,
            final_cycle=final_cycle,
            commit_cycle=commit_cycle,
            color_transitions=color_transitions,
            record_recent=record_recent,
        )

    def _commit_single_creation_color(
        self,
        transaction,
        selection: ColorSelection | None,
        preview_cycle: ColorCycleState | None,
    ) -> tuple[dict[str, Any] | None, dict[str, Any]] | None:
        """Commit one previewed chart color inside component registration."""

        if selection is None:
            return None
        axes_id = self.current_axes_component_id
        if axes_id is None:
            raise ValueError("Select an axes before committing a chart color.")
        transaction.watch_existing(axes_id)
        before = deepcopy(
            self.component_registry.get(axes_id).state.properties.get("color_cycle")
        )
        change = self.axes_commands.commit_color_selection(
            axes_id,
            selection,
            preview_cycle=preview_cycle,
        )
        if not change.ok:
            raise ValueError(
                change.message or "Could not commit the chart color cycle."
            )
        after = self.component_registry.get(axes_id).state.properties.get("color_cycle")
        return (before, deepcopy(after)) if after is not None else None

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

        ids = tuple(str(item) for item in component_ids)
        reason = DeleteReason(reason)

        def operation() -> bool:
            request = DeletionRequest(
                ids,
                anchor_id=anchor_id,
                reason=reason,
            )
            return self.deletion_coordinator.delete(
                request,
                role_label=role_label,
            )

        if reason is DeleteReason.DATA_DEPENDENCY:
            with self.figure_history.suspend_recording():
                return operation()
        count = len(ids)
        label = str(role_label).replace("_", " ").title()
        text = f"Delete {label}" if count == 1 else f"Delete {count} {label} Components"
        return self.figure_history.perform(text, operation)

    @_history_command("Create Axes Layout", scan_all=True)
    def create_axes_layout(
        self,
        spec: AxesLayoutSpec,
        *,
        appearance: ResolvedAxesAppearance | None = None,
    ) -> tuple[str, ...]:
        """Create a validated Axes layout through the domain service."""

        return self.axes_layout_service.create(spec, appearance=appearance)

    @_history_command("Change Axes Layout", scan_all=True)
    def update_axes_layout(self, spec: AxesLayoutSpec) -> tuple[str, ...]:
        """Safely update geometry for an existing persisted layout."""

        return self.axes_layout_service.update_geometry(spec)

    # Add custom curve
    @_history_command("Create Function Curve")
    def add_curve(
        self,
        func_text: str,
        x_start: float,
        x_stop: float,
        style,
        color,
        label: str,
        color_order: int | None = None,
        object_id: str | None = None,
        *,
        color_selection: ColorSelection | None = None,
        preview_cycle: ColorCycleState | None = None,
        linewidth: float | None = None,
        marker: str | None = None,
        markersize: float | None = None,
        markeredgewidth: float | None = None,
    ):
        """Add curve."""

        object_id = object_id or new_id()
        x = np.linspace(x_start, x_stop, 1000)
        y = evaluate_curve_expression(func_text, x)
        plot_kwargs, resolved_color, commit_selection, preview_cycle = (
            self._user_line_plot_plan(
                label=label,
                color=color,
                color_selection=color_selection,
                preview_cycle=preview_cycle,
                linestyle=style,
                linewidth=linewidth,
                marker=marker,
                markersize=markersize,
                markeredgewidth=markeredgewidth,
            )
        )
        with self.component_registry.registration_transaction() as transaction:
            with matplotlib_style_context(self.component_style):
                (line,) = self.current_axes.plot(x, y, **plot_kwargs)
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
                self._line_sync_properties(
                    line, color=resolved_color, label=label
                ),
                {
                    "expression": func_text,
                    "x_start": float(x_start),
                    "x_stop": float(x_stop),
                },
            )
            self._prepare_created_component(controller, transaction)
            color_transition = self._commit_single_creation_color(
                transaction,
                commit_selection,
                preview_cycle,
            )
            axes_id = self.current_axes_component_id
        self._finish_created_component(controller)
        if color_transition is not None and axes_id is not None:
            self.color_consumption_ledger.record(
                axes_id,
                controller.component_id,
                *color_transition,
            )
            self.color_library.record_recent(resolved_color)
        return line

    @_history_command("Create Line")
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
            with matplotlib_style_context(self.component_style):
                (line,) = self.current_axes.plot(
                    np.asarray(x),
                    np.asarray(y),
                    linestyle=style,
                    color=color,
                    label=label,
                )
            transaction.on_rollback(lambda: self._remove_created_artist(line))
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
        self._finish_created_component(controller)
        return line

    # Add line plot
    @_history_command("Create Plot")
    def add_plot(
        self,
        x,
        y,
        style,
        size,
        color,
        label,
        x_ref: ColumnRef,
        y_ref: ColumnRef,
        object_id: str | None = None,
        color_order: int | None = None,
        *,
        linewidth: float | None = None,
        preprocess: DataPreprocessSpec | dict[str, Any] | None = None,
        marker=None,
        markeredgewidth: float | None = None,
        color_selection: ColorSelection | None = None,
        preview_cycle: ColorCycleState | None = None,
    ):
        """Add plot."""

        preprocess = DataPreprocessSpec.from_dict(preprocess)
        pair = resolve_preprocessed_pair(
            self.repository,
            x_ref,
            y_ref,
            preprocess,
            preserve_gaps=True,
        )
        if self._restoring_component_tree_now:
            resolved_color = normalize_color(color)
            resolved_style, resolved_size, resolved_lw = style, size, linewidth
            resolved_marker, resolved_mew = marker, markeredgewidth
            commit_selection = color_selection
        else:
            resolved = self._resolve_line_creation(
                settings=self._read_component_defaults(),
                color=color,
                color_selection=color_selection,
                linestyle=style,
                linewidth=linewidth,
                marker=marker,
                markersize=size,
                markeredgewidth=markeredgewidth,
            )
            resolved_color = resolved.color
            resolved_style = resolved.linestyle
            resolved_size = resolved.markersize
            resolved_lw = resolved.linewidth
            resolved_marker = resolved.marker
            resolved_mew = resolved.markeredgewidth
            commit_selection, preview_cycle = self._commit_resolved_line_color(
                resolved, color_selection, preview_cycle
            )
        series = PreparedChartSeries(
            x_ref=x_ref,
            y_ref=y_ref,
            x=pair.x,
            y=pair.y,
            label=str(label),
            color=resolved_color,
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
                style=resolved_style,
                size=resolved_size,
                linewidth=resolved_lw,
                preprocess=preprocess,
                object_id=object_id,
                color_order=color_order,
                marker=resolved_marker,
                markeredgewidth=resolved_mew,
            )
            color_transition = self._commit_single_creation_color(
                transaction,
                commit_selection,
                preview_cycle,
            )
        self._finish_created_component(controller)
        if color_transition is not None and axes_id is not None:
            self.color_consumption_ledger.record(
                axes_id,
                controller.component_id,
                *color_transition,
            )
            self.color_library.record_recent(resolved_color)
        return line

    @_history_command("Create Plots")
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
        record_recent: bool = True,
        marker=None,
        markeredgewidth: float | None = None,
    ) -> ChartBatchCreationResult:
        """Atomically create one Plot component for every selected Y column."""

        spec = DataPreprocessSpec.from_dict(preprocess)
        line_style, line_width, line_marker, line_size, line_mew = (
            self._shared_line_fields(
                linestyle=style,
                linewidth=linewidth,
                marker=marker,
                markersize=size,
                markeredgewidth=markeredgewidth,
            )
        )
        prepared, final_cycle, commit_cycle, transitions = self._prepare_data_batch(
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
                style=line_style,
                size=line_size,
                linewidth=line_width,
                preprocess=spec,
                marker=line_marker,
                markeredgewidth=line_mew,
            ),
            final_cycle=final_cycle,
            commit_cycle=commit_cycle,
            color_transitions=transitions,
            record_recent=record_recent,
        )

    # Add scatter plot
    @_history_command("Create Scatter")
    def add_scatter(
        self,
        x,
        y,
        size,
        color,
        marker,
        label,
        x_ref: ColumnRef,
        y_ref: ColumnRef,
        object_id: str | None = None,
        color_order: int | None = None,
        preprocess: DataPreprocessSpec | dict[str, Any] | None = None,
        *,
        color_ref: ColumnRef | None = None,
        size_ref: ColumnRef | None = None,
        color_mapping: dict[str, Any] | None = None,
        size_mapping: dict[str, Any] | None = None,
        linewidth: float | None = None,
        color_selection: ColorSelection | None = None,
        preview_cycle: ColorCycleState | None = None,
    ):
        """Add scatter."""

        preprocess = DataPreprocessSpec.from_dict(preprocess)
        pair = resolve_preprocessed_pair(
            self.repository,
            x_ref,
            y_ref,
            preprocess,
            preserve_gaps=False,
        )
        mapping_enabled = False
        if isinstance(color_mapping, dict):
            mapping_enabled = bool(color_mapping.get("enabled"))
        if self._restoring_component_tree_now:
            resolved_color = normalize_color(color)
            resolved_marker, resolved_size, resolved_lw = marker, size, linewidth
            commit_selection = None if mapping_enabled else color_selection
        else:
            resolved = self._resolve_scatter_creation(
                settings=self._read_component_defaults(),
                color=color,
                color_selection=None if mapping_enabled else color_selection,
                marker=marker,
                size=size,
                linewidth=linewidth,
            )
            resolved_color = resolved.color
            resolved_marker = resolved.marker
            resolved_size = resolved.size
            resolved_lw = resolved.linewidth
            if mapping_enabled:
                commit_selection = None
            else:
                commit_selection, preview_cycle = self._commit_resolved_line_color(
                    resolved, color_selection, preview_cycle
                )
        series = PreparedChartSeries(
            x_ref=x_ref,
            y_ref=y_ref,
            x=pair.x,
            y=pair.y,
            label=str(label),
            color=resolved_color,
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
                size=resolved_size,
                marker=resolved_marker,
                preprocess=preprocess,
                color_ref=color_ref,
                size_ref=size_ref,
                color_mapping=color_mapping,
                size_mapping=size_mapping,
                object_id=object_id,
                color_order=color_order,
                linewidth=resolved_lw,
            )
            color_transition = self._commit_single_creation_color(
                transaction,
                commit_selection,
                preview_cycle,
            )
        self._finish_created_component(controller)
        if color_transition is not None and axes_id is not None:
            self.color_consumption_ledger.record(
                axes_id,
                controller.component_id,
                *color_transition,
            )
            self.color_library.record_recent(resolved_color)
        return scatter

    @_history_command("Create Scatters")
    def add_scatters(
        self,
        x_ref: ColumnRef,
        y_refs,
        *,
        size,
        marker,
        preprocess: DataPreprocessSpec | dict[str, Any] | None,
        color_selection: ColorSelection,
        color_ref: ColumnRef | None = None,
        size_ref: ColumnRef | None = None,
        color_mapping: dict[str, Any] | None = None,
        size_mapping: dict[str, Any] | None = None,
        record_recent: bool = True,
        linewidth: float | None = None,
    ) -> ChartBatchCreationResult:
        """Atomically create one Scatter component for every selected Y."""

        spec = DataPreprocessSpec.from_dict(preprocess)
        color_spec = (
            ScatterController.property_specs()["color_mapping"].normalize(
                color_mapping
                if color_mapping is not None
                else ScatterController.default_properties()["color_mapping"]
            )
        )
        size_spec = (
            ScatterController.property_specs()["size_mapping"].normalize(
                size_mapping
                if size_mapping is not None
                else ScatterController.default_properties()["size_mapping"]
            )
        )
        if self._restoring_component_tree_now:
            resolved_marker, resolved_size, resolved_lw = marker, size, linewidth
        else:
            resolved = self._resolve_scatter_creation(
                settings=self._read_component_defaults(),
                color=color_selection.color,
                color_selection=color_selection,
                marker=marker,
                size=size,
                linewidth=linewidth,
            )
            resolved_marker = resolved.marker
            resolved_size = resolved.size
            resolved_lw = resolved.linewidth
        prepared, final_cycle, commit_cycle, transitions = self._prepare_data_batch(
            x_ref,
            y_refs,
            spec,
            color_selection,
            preserve_gaps=False,
            consume_palette=not color_spec["enabled"],
        )
        return self._commit_chart_batch(
            prepared,
            lambda transaction, series: self._stage_scatter(
                transaction,
                series,
                size=resolved_size,
                marker=resolved_marker,
                preprocess=spec,
                color_ref=color_ref,
                size_ref=size_ref,
                color_mapping=color_spec,
                size_mapping=size_spec,
                linewidth=resolved_lw,
            ),
            final_cycle=final_cycle,
            commit_cycle=commit_cycle,
            color_transitions=transitions,
            record_recent=record_recent,
        )

    # Add error bar
    @_history_command("Create Error Bar")
    def add_errorbar(
        self,
        x_ref: ColumnRef,
        y_ref: ColumnRef,
        label: str,
        xerr: dict[str, Any] | None = None,
        yerr: dict[str, Any] | None = None,
        preprocess: DataPreprocessSpec | dict[str, Any] | None = None,
        *,
        object_id: str | None = None,
        color_order: int | None = None,
        color=None,
        color_selection: ColorSelection | None = None,
        preview_cycle: ColorCycleState | None = None,
        linestyle=None,
        linewidth=None,
        marker=None,
        markersize=None,
        markeredgewidth=None,
        markerfacecoloralt=None,
        fillstyle=None,
        drawstyle=None,
        antialiased=None,
        ecolor=None,
        elinewidth=None,
        capsize=None,
        capthick=None,
        error_linestyle=None,
        error_capstyle=None,
        error_antialiased=None,
        errorevery=None,
        lolims=None,
        uplims=None,
        xlolims=None,
        xuplims=None,
        barsabove=None,
    ):
        """Create and publish one table-driven Error Bar atomically."""

        from mygui.figuremodify.components.property_values import (
            DEFAULT_ERROR_SPEC,
            normalize_error_spec,
        )

        preprocess_spec = DataPreprocessSpec.from_dict(preprocess)
        xerr_spec = normalize_error_spec(
            xerr if xerr is not None else deepcopy(DEFAULT_ERROR_SPEC)
        )
        yerr_spec = normalize_error_spec(
            yerr if yerr is not None else deepcopy(DEFAULT_ERROR_SPEC)
        )
        drawable = resolve_errorbar_data(
            self.repository,
            x_ref,
            y_ref,
            xerr_spec,
            yerr_spec,
            preprocess_spec,
        )
        if self._restoring_component_tree_now:
            resolved = ResolvedErrorBarAppearance(
                color=normalize_color(color),
                linestyle=(
                    deepcopy(linestyle)
                    if linestyle is not None
                    else {"kind": "preset", "value": "-"}
                ),
                linewidth=float(linewidth) if linewidth is not None else 1.5,
                marker=(
                    deepcopy(marker)
                    if marker is not None
                    else {"kind": "symbol", "value": "None"}
                ),
                markersize=float(markersize) if markersize is not None else 6.0,
                markeredgewidth=(
                    float(markeredgewidth) if markeredgewidth is not None else 1.0
                ),
                markerfacecoloralt=(
                    str(markerfacecoloralt)
                    if markerfacecoloralt is not None
                    else "none"
                ),
                fillstyle=str(fillstyle) if fillstyle is not None else "full",
                drawstyle=str(drawstyle) if drawstyle is not None else "default",
                antialiased=bool(antialiased) if antialiased is not None else True,
                ecolor=(
                    normalize_color(ecolor)
                    if ecolor is not None
                    else normalize_color(color)
                ),
                elinewidth=float(elinewidth) if elinewidth is not None else 1.5,
                capsize=float(capsize) if capsize is not None else 0.0,
                capthick=float(capthick) if capthick is not None else 1.0,
                error_linestyle=(
                    deepcopy(error_linestyle)
                    if error_linestyle is not None
                    else {"kind": "preset", "value": "-"}
                ),
                error_capstyle=(
                    None if error_capstyle is None else str(error_capstyle)
                ),
                error_antialiased=(
                    bool(error_antialiased) if error_antialiased is not None else True
                ),
                errorevery=(
                    deepcopy(errorevery) if errorevery is not None else {"kind": "all"}
                ),
                lolims=bool(lolims) if lolims is not None else False,
                uplims=bool(uplims) if uplims is not None else False,
                xlolims=bool(xlolims) if xlolims is not None else False,
                xuplims=bool(xuplims) if xuplims is not None else False,
                barsabove=bool(barsabove) if barsabove is not None else False,
                color_selection=(
                    color_selection
                    if color_selection is not None
                    else ColorSelection(normalize_color(color))
                ),
            )
            commit_selection = color_selection
        else:
            resolved = self._resolve_errorbar_creation(
                settings=self._read_component_defaults(),
                color=color,
                color_selection=color_selection,
                linestyle=linestyle,
                linewidth=linewidth,
                marker=marker,
                markersize=markersize,
                markeredgewidth=markeredgewidth,
                markerfacecoloralt=markerfacecoloralt,
                fillstyle=fillstyle,
                drawstyle=drawstyle,
                antialiased=antialiased,
                ecolor=ecolor,
                elinewidth=elinewidth,
                capsize=capsize,
                capthick=capthick,
                error_linestyle=error_linestyle,
                error_capstyle=error_capstyle,
                error_antialiased=error_antialiased,
                errorevery=errorevery,
                lolims=lolims,
                uplims=uplims,
                xlolims=xlolims,
                xuplims=xuplims,
                barsabove=barsabove,
            )
            commit_selection, preview_cycle = self._commit_resolved_line_color(
                resolved, color_selection, preview_cycle
            )
        series = PreparedErrorBarSeries(
            x_ref=x_ref,
            y_ref=y_ref,
            x=drawable.x,
            y=drawable.y,
            xerr=drawable.xerr,
            yerr=drawable.yerr,
            label=str(label),
            xerr_spec=xerr_spec,
            yerr_spec=yerr_spec,
            preprocess=preprocess_spec,
            excluded_count=0,
        )
        axes_id = self.current_axes_component_id
        if axes_id is None:
            raise ValueError("Select an axes before adding a chart.")
        with self.component_registry.registration_transaction() as transaction:
            transaction.watch_existing(axes_id)
            runtime, controller = self._stage_errorbar(
                transaction,
                series,
                appearance=resolved,
                object_id=object_id,
                color_order=color_order,
            )
            color_transition = self._commit_single_creation_color(
                transaction,
                commit_selection,
                preview_cycle,
            )
        self._finish_created_component(controller)
        if color_transition is not None and axes_id is not None:
            self.color_consumption_ledger.record(
                axes_id,
                controller.component_id,
                *color_transition,
            )
            self.color_library.record_recent(resolved.color)
        return runtime

    # Add fit curve
    @_history_command("Create Fit Curve")
    def add_fit_curve(
        self,
        x,
        y,
        color,
        label,
        x_ref: ColumnRef,
        y_ref: ColumnRef,
        engine: FitEngine | str = FitEngine.PYTHON,
        fit_type=None,
        fit_options=None,
        fit_result=None,
        expression: str = "",
        x_start: float | None = None,
        x_stop: float | None = None,
        style: str | None = None,
        object_id: str | None = None,
        color_order: int | None = None,
        preprocess: DataPreprocessSpec | dict[str, Any] | None = None,
        fit_input_range: FitInputRangeSpec | dict[str, Any] | None = None,
        *,
        color_selection: ColorSelection | None = None,
        preview_cycle: ColorCycleState | None = None,
        linewidth: float | None = None,
        marker: str | None = None,
        markersize: float | None = None,
        markeredgewidth: float | None = None,
    ):
        """Add fit curve."""

        preprocess = DataPreprocessSpec.from_dict(preprocess)
        input_range = FitInputRangeSpec.from_dict(fit_input_range)
        pair = resolve_preprocessed_pair(
            self.repository,
            x_ref,
            y_ref,
            preprocess,
            preserve_gaps=False,
        )
        selected = select_fit_input_pair(pair, input_range, require_data=False)
        x, y = selected.x, selected.y
        try:
            engine = FitEngine(engine)
        except ValueError as exc:
            raise ValueError(
                f"Unsupported fitting engine: {engine}"
            ) from exc

        object_id = object_id or new_id()
        x_array = np.asarray(x, dtype=float)
        y_array = np.asarray(y, dtype=float)
        x_start = selected.x_start if x_start is None else float(x_start)
        x_stop = selected.x_stop if x_stop is None else float(x_stop)

        line_x = x_array
        line_y = y_array
        if expression:
            try:
                line_x = np.linspace(x_start, x_stop, 1000)
                line_y = evaluate_curve_expression(
                    expression,
                    line_x,
                    limits=GENERATED_FIT_EXPRESSION_LIMITS,
                )
            except ValueError:
                status_messages.show_error("Saved fit expression could not be restored; showing source data.")
                expression = ""

        plot_kwargs, resolved_color, commit_selection, preview_cycle = (
            self._user_line_plot_plan(
                label=label,
                color=color,
                color_selection=color_selection,
                preview_cycle=preview_cycle,
                linestyle=style,
                linewidth=linewidth,
                marker=marker,
                markersize=markersize,
                markeredgewidth=markeredgewidth,
            )
        )
        with self.component_registry.registration_transaction() as transaction:
            with matplotlib_style_context(self.component_style):
                (line,) = self.current_axes.plot(
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
                self._line_sync_properties(
                    line, color=resolved_color, label=label
                ),
                {
                    "x_ref": x_ref.to_dict(),
                    "y_ref": y_ref.to_dict(),
                    "preprocess": preprocess.to_dict(),
                    "engine": engine.value,
                    "fit_type": deepcopy(fit_type),
                    "fit_options": deepcopy(fit_options),
                    "fit_result": deepcopy(fit_result),
                    "expression": expression or "",
                    "x_start": float(x_start),
                    "x_stop": float(x_stop),
                    "fit_input_range": input_range.to_dict(),
                },
            )
            self._prepare_created_component(controller, transaction)
            color_transition = self._commit_single_creation_color(
                transaction,
                commit_selection,
                preview_cycle,
            )
            axes_id = self.current_axes_component_id
        self._finish_created_component(controller)
        if color_transition is not None and axes_id is not None:
            self.color_consumption_ledger.record(
                axes_id,
                controller.component_id,
                *color_transition,
            )
            self.color_library.record_recent(resolved_color)
        return line

    # Add interpolation curve
    @_history_command("Create Interpolation")
    def add_interpolate_curve(
        self,
        x,
        y,
        x_ref: ColumnRef,
        y_ref: ColumnRef,
        method,
        k=3,
        label="interpolate",
        color="black",
        samples=DEFAULT_INTERPOLATION_SAMPLES,
        lam=None,
        lam_auto=True,
        object_id: str | None = None,
        color_order: int | None = None,
        allow_empty: bool = False,
        preprocess: DataPreprocessSpec | dict[str, Any] | None = None,
        announce: bool = True,
        *,
        color_selection: ColorSelection | None = None,
        preview_cycle: ColorCycleState | None = None,
        linestyle=None,
        linewidth: float | None = None,
        marker=None,
        markersize: float | None = None,
        markeredgewidth: float | None = None,
    ):
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
        if self._restoring_component_tree_now:
            resolved_color = normalize_color(color)
            line_style, line_width = linestyle, linewidth
            line_marker, line_ms, line_mew = marker, markersize, markeredgewidth
            commit_selection = color_selection
        else:
            resolved = self._resolve_line_creation(
                settings=self._read_component_defaults(),
                color=color,
                color_selection=color_selection,
                linestyle=linestyle,
                linewidth=linewidth,
                marker=marker,
                markersize=markersize,
                markeredgewidth=markeredgewidth,
            )
            resolved_color = resolved.color
            line_style = resolved.linestyle
            line_width = resolved.linewidth
            line_marker = resolved.marker
            line_ms = resolved.markersize
            line_mew = resolved.markeredgewidth
            commit_selection, preview_cycle = self._commit_resolved_line_color(
                resolved, color_selection, preview_cycle
            )
        series = PreparedChartSeries(
            x_ref=x_ref,
            y_ref=y_ref,
            x=x_new,
            y=y_new,
            label=str(label),
            color=resolved_color,
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
                linestyle=line_style,
                linewidth=line_width,
                marker=line_marker,
                markersize=line_ms,
                markeredgewidth=line_mew,
            )
            color_transition = self._commit_single_creation_color(
                transaction,
                commit_selection,
                preview_cycle,
            )
        self._finish_created_component(controller)
        if color_transition is not None and axes_id is not None:
            self.color_consumption_ledger.record(
                axes_id,
                controller.component_id,
                *color_transition,
            )
            self.color_library.record_recent(resolved_color)
        if announce and not self._restoring_component_tree_now:
            if x_new.size:
                status_messages.show_success("Interpolation curve created.")
            else:
                status_messages.show_warning(
                    "Interpolation curve has no valid data yet; its editor and style were kept."
                )
        return line

    @_history_command("Create Interpolations")
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
        linestyle=None,
        linewidth: float | None = None,
        marker=None,
        markersize: float | None = None,
        markeredgewidth: float | None = None,
    ) -> ChartBatchCreationResult:
        """Atomically create one interpolation component for every Y."""

        spec = DataPreprocessSpec.from_dict(preprocess)
        line_style, line_width, line_marker, line_ms, line_mew = (
            self._shared_line_fields(
                linestyle=linestyle,
                linewidth=linewidth,
                marker=marker,
                markersize=markersize,
                markeredgewidth=markeredgewidth,
            )
        )
        sources, final_cycle, commit_cycle, transitions = self._prepare_data_batch(
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
                PreparedChartSeries(
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
                linestyle=line_style,
                linewidth=line_width,
                marker=line_marker,
                markersize=line_ms,
                markeredgewidth=line_mew,
            ),
            final_cycle=final_cycle,
            commit_cycle=commit_cycle,
            color_transitions=transitions,
        )

    # Add text
    @staticmethod
    def _resolve_text_usetex(usetex: bool | None) -> bool:
        if usetex is None:
            return tex_config.is_tex_enabled()
        return bool(usetex) and tex_config.is_tex_enabled()

    def _free_text_artist_kwargs(
        self,
        fontfamily: str,
        fontsize: float,
        *,
        color=None,
        fontweight=None,
        fontstyle=None,
    ) -> dict[str, Any]:
        if self._restoring_component_tree_now:
            kwargs: dict[str, Any] = {
                "family": fontfamily,
                "fontsize": fontsize,
                "usetex": False,
            }
            if color is not None:
                kwargs["color"] = color
            if fontweight is not None:
                kwargs["fontweight"] = fontweight
            if fontstyle is not None:
                kwargs["fontstyle"] = fontstyle
            return kwargs
        resolved = self._resolve_text_creation(
            settings=self._read_component_defaults(),
            fontfamily=fontfamily,
            fontsize=fontsize,
            color=color,
            fontweight=fontweight,
            fontstyle=fontstyle,
        )
        kwargs: dict[str, Any] = {
            "family": resolved.fontfamily,
            "fontsize": resolved.fontsize,
            "usetex": False,
        }
        if resolved.color is not None:
            kwargs["color"] = resolved.color
        if resolved.fontweight is not None:
            kwargs["fontweight"] = resolved.fontweight
        if resolved.fontstyle is not None:
            kwargs["fontstyle"] = resolved.fontstyle
        return kwargs

    @_history_command("Create Text")
    def add_text(
        self,
        x: float,
        y: float,
        text: str,
        fontfamily: str,
        fontsize: float,
        usetex: bool | None = None,
        object_id: str | None = None,
        color=None,
        fontweight=None,
        fontstyle=None,
    ):
        """Add text."""

        desired_usetex = self._resolve_text_usetex(usetex)
        text_kwargs = self._free_text_artist_kwargs(
            fontfamily,
            fontsize,
            color=color,
            fontweight=fontweight,
            fontstyle=fontstyle,
        )
        with matplotlib_style_context(self.component_style):
            text_artist = self.current_axes.text(
                x,
                y,
                text,
                transform=self.current_axes.transAxes,
                **text_kwargs,
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
        if not self._restoring_component_tree_now and (not result.ok or result.notices):
            self.message_presenter.present(result)
        self._finish_created_component(controller)
        return text_artist

    @_history_command("Create Text")
    def add_global_text(
        self,
        x: float,
        y: float,
        text: str,
        fontfamily: str,
        fontsize: float,
        usetex: bool | None = None,
        object_id: str | None = None,
        color=None,
        fontweight=None,
        fontstyle=None,
    ):
        """Add global text."""

        desired_usetex = self._resolve_text_usetex(usetex)
        text_kwargs = self._free_text_artist_kwargs(
            fontfamily,
            fontsize,
            color=color,
            fontweight=fontweight,
            fontstyle=fontstyle,
        )
        with matplotlib_style_context(self.component_style):
            text_artist = self.fig.text(
                x,
                y,
                text,
                **text_kwargs,
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
        if not self._restoring_component_tree_now and (not result.ok or result.notices):
            self.message_presenter.present(result)
        self._finish_created_component(controller)
        return text_artist

    @_history_command("Create Annotation")
    def add_annotation(
        self,
        properties: dict[str, Any] | None = None,
        *,
        axes_id: str | None = None,
        object_id: str | None = None,
        component_order: int | None = None,
        announce: bool = True,
    ):
        """Create and publish one Annotation atomically on a normal Axes."""

        owner_axes_id = (
            axes_id if axes_id is not None else self.current_axes_component_id
        )
        if owner_axes_id is None:
            raise ValueError("Select an Axes before creating an Annotation.")
        parent = self.component_registry.get(owner_axes_id)
        if parent.state.kind is not ComponentKind.AXES:
            raise ValueError("Annotations must be owned by a normal Axes.")
        axes = parent.resolve_target()

        merged = AnnotationController.default_properties()
        merged.update(properties or {})
        component_id = object_id or new_id()
        artist_kwargs = annotation_artist_kwargs(merged)

        with self.component_registry.registration_transaction() as transaction:
            with matplotlib_style_context(self.component_style):
                annotation = axes.annotate(merged["text"], **artist_kwargs)
            transaction.on_rollback(
                lambda: self._remove_created_artist(annotation)
            )
            state = ComponentState(
                id=component_id,
                kind=ComponentKind.ANNOTATION,
                role=ComponentRole.ANNOTATION,
                parent_id=owner_axes_id,
                order=(
                    self._next_child_order(
                        owner_axes_id,
                        kind=ComponentKind.ANNOTATION,
                    )
                    if component_order is None
                    else int(component_order)
                ),
                selector={"object_id": component_id},
                properties=merged,
                data={},
            )
            controller = AnnotationController(state, target=annotation)
            initialized = controller.apply_state(controller.state)
            if not initialized.ok:
                raise ValueError(
                    initialized.message or "Could not initialize the Annotation."
                )
            controller.sync_from_target(strict=True)
            self.component_registry.register(controller, target=annotation)
            annotation.set_gid(component_id)
            if not self._restoring_component_tree_now:
                result = self.text_render_service.apply(
                    controller,
                    {"usetex": bool(merged.get("usetex", False))},
                )
                if not result.ok:
                    raise ValueError(
                        result.message or "Annotation render validation failed."
                    )
            self._prepare_created_component(controller, transaction)
            self.component_registry.request_update(
                axes,
                UpdateImpact.REDRAW,
            )

        self._finish_created_component(controller)
        if announce and not self._restoring_component_tree_now:
            status_messages.show_success("Annotation created.")
        return annotation

    def add_annotation_from_input(
        self,
        properties: dict[str, Any] | None = None,
        *,
        axes_id: str | None = None,
    ):
        """Create one Annotation from UI input with a frozen style snapshot.

        Only interactive creation reads the active Figure style here; restore,
        history replay, and template application go through ``add_annotation``
        with their persisted state only.
        """

        defaults = self.component_creation_defaults()
        text_style = defaults.text
        line_style = defaults.line
        style = {
            "fontfamily": text_style.fontfamily,
            "fontsize": text_style.fontsize,
            "fontweight": text_style.fontweight,
            "fontstyle": text_style.fontstyle,
            "color": text_style.color,
            "arrow_color": text_style.color,
            "arrow_linewidth": line_style.linewidth,
        }
        merged = dict(style)
        merged.update(properties or {})
        return self.add_annotation(merged, axes_id=axes_id)

    @_history_command("Duplicate Annotation")
    def duplicate_annotation(self, component_id: str):
        """Duplicate one Annotation with a new stable id and full state."""

        controller = self.annotation_service.annotation_controller(component_id)
        state = controller.read_state(strict=True)
        new_id_value = new_id()
        self.add_annotation(
            state.properties,
            axes_id=state.parent_id,
            object_id=new_id_value,
            announce=False,
        )
        if not self._restoring_component_tree_now:
            status_messages.show_success("Annotation duplicated.")
        return new_id_value

    def duplicate_component(self, component_id: str):
        """Duplicate one duplicable component by id."""

        controller = self.component_registry.get(component_id)
        if controller.state.kind is ComponentKind.ANNOTATION:
            return self.duplicate_annotation(component_id)
        raise ValueError(f"Component {component_id} cannot be duplicated.")

    @_history_command("Create In-Axes Element")
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
            with matplotlib_style_context(self.component_style):
                runtime = self.in_axes_service.create_runtime(
                    parent_axes,
                    tuple(properties["bounds"]),
                    zorder=float(properties["zorder"]),
                )
            transaction.on_rollback(
                lambda target=runtime: self.in_axes_service.destroy_runtime(target)
            )
            controller = controller_type(state, target=runtime)
            # Controller construction fills every current-schema default. Apply
            # that complete state so creation inputs may stay focused on the
            # values a user can reasonably choose up front.
            initial = controller.apply_state(controller.state)
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

    def _add_field_2d(
        self,
        role: ComponentRole,
        display_name: str,
        x_ref: ColumnRef | dict[str, Any],
        y_ref: ColumnRef | dict[str, Any],
        z_ref: ColumnRef | dict[str, Any],
        properties: dict[str, Any] | None,
        *,
        object_id: str | None,
        color_order: int | None,
        announce: bool,
    ):
        owner_axes_id = self.current_axes_component_id
        owner_axes = self.current_axes
        if owner_axes_id is None or owner_axes is None:
            raise ValueError(f"Select an Axes before creating a {display_name}.")
        x_ref = ColumnRef.from_dict(x_ref) if not isinstance(x_ref, ColumnRef) else x_ref
        y_ref = ColumnRef.from_dict(y_ref) if not isinstance(y_ref, ColumnRef) else y_ref
        z_ref = ColumnRef.from_dict(z_ref) if not isinstance(z_ref, ColumnRef) else z_ref
        controller_type = {
            ComponentRole.PSEUDOCOLOR: PseudocolorController,
            ComponentRole.HEATMAP: HeatmapController,
            ComponentRole.CONTOUR: ContourController,
        }[role]
        component_id = object_id or new_id()
        if self._restoring_component_tree_now:
            requested = dict(properties or {})
        else:
            requested = default_field_2d_properties(role, self.component_style)
            requested.update(properties or {})
        controller = None
        runtime = None
        grid = None
        with self.component_registry.registration_transaction() as transaction:
            transaction.watch_existing(owner_axes_id)
            with matplotlib_style_context(self.component_style):
                grid = self.field_2d_service.resolve_grid(
                    x_ref, y_ref, z_ref, role
                )
                runtime = self.field_2d_service.create_runtime(
                    owner_axes,
                    role,
                    grid,
                    requested,
                    style=self.component_style,
                    gid=component_id,
                )
            transaction.on_rollback(
                lambda target=runtime: self.field_2d_service.destroy_runtime(target)
            )
            state = ComponentState(
                id=component_id,
                kind=ComponentKind.FIELD_2D,
                role=role,
                parent_id=owner_axes_id,
                order=self._claim_color_order(color_order),
                selector={"object_id": component_id},
                properties=dict(requested),
                data={
                    "x_ref": x_ref.to_dict(),
                    "y_ref": y_ref.to_dict(),
                    "z_ref": z_ref.to_dict(),
                },
            )
            controller = controller_type(state, target=runtime)
            actual = controller.sync_from_target(strict=True)
            desired = deepcopy(actual.properties)
            for key in requested:
                desired[key] = deepcopy(requested[key])
            applied = controller.apply_state(actual.clone(properties=desired))
            if not applied.ok:
                raise ValueError(applied.message or f"Could not initialize {display_name}.")
            controller.sync_from_target(strict=True)
            self.component_registry.register(controller, target=runtime)
            runtime.set_gid(component_id)
            self.component_registry.request_update(
                owner_axes,
                UpdateImpact.AUTOSCALE,
            )
            self._prepare_created_component(controller, transaction)
            self.component_registry.request_update(self.fig, UpdateImpact.REDRAW)
            if self.fig.canvas is not None:
                self.fig.canvas.draw()

        self._finish_created_component(controller)
        if announce and not self._restoring_component_tree_now:
            if grid is not None and grid.skipped_xy_count:
                status_messages.show_warning(
                    f"{display_name} created; skipped "
                    f"{grid.skipped_xy_count} row(s) with missing or "
                    "non-finite X or Y coordinates."
                )
            elif runtime is not None and runtime.empty:
                status_messages.show_warning(
                    f"{display_name} created with no drawable data yet."
                )
            else:
                status_messages.show_success(f"{display_name} created.")
        return runtime

    @_history_command("Create Pseudocolor")
    def add_pseudocolor(
        self,
        x_ref,
        y_ref,
        z_ref,
        properties: dict[str, Any] | None = None,
        *,
        object_id: str | None = None,
        color_order: int | None = None,
        announce: bool = True,
    ):
        """Create and publish one Pseudocolor chart atomically."""

        return self._add_field_2d(
            ComponentRole.PSEUDOCOLOR,
            "Pseudocolor",
            x_ref,
            y_ref,
            z_ref,
            properties,
            object_id=object_id,
            color_order=color_order,
            announce=announce,
        )

    @_history_command("Create Heatmap")
    def add_heatmap(
        self,
        x_ref,
        y_ref,
        z_ref,
        properties: dict[str, Any] | None = None,
        *,
        object_id: str | None = None,
        color_order: int | None = None,
        announce: bool = True,
    ):
        """Create and publish one Heatmap chart atomically."""

        return self._add_field_2d(
            ComponentRole.HEATMAP,
            "Heatmap",
            x_ref,
            y_ref,
            z_ref,
            properties,
            object_id=object_id,
            color_order=color_order,
            announce=announce,
        )

    @_history_command("Create Contour")
    def add_contour(
        self,
        x_ref,
        y_ref,
        z_ref,
        properties: dict[str, Any] | None = None,
        *,
        object_id: str | None = None,
        color_order: int | None = None,
        announce: bool = True,
    ):
        """Create and publish one Contour chart atomically."""

        return self._add_field_2d(
            ComponentRole.CONTOUR,
            "Contour",
            x_ref,
            y_ref,
            z_ref,
            properties,
            object_id=object_id,
            color_order=color_order,
            announce=announce,
        )

    def eligible_colorbar_sources(self) -> tuple[tuple[str, str], ...]:
        """Return valid scalar-mapped sources under the selected owner Axes."""

        axes_id = self.current_axes_component_id
        if axes_id is None:
            return ()
        return tuple(
            (
                source.source_controller.component_id,
                self.colorbar_service.source_preview(source),
            )
            for source in self.colorbar_service.eligible_sources(axes_id)
        )

    @_history_command("Create Colorbar")
    def add_colorbar(
        self,
        source_component_id: str,
        properties: dict[str, Any] | None = None,
        *,
        object_id: str | None = None,
        component_order: int | None = None,
        announce: bool = True,
    ):
        """Create and publish one first-class Colorbar Component atomically."""

        owner_axes_id = self.current_axes_component_id
        owner_axes = self.current_axes
        if owner_axes_id is None or owner_axes is None:
            raise ValueError("Select an Axes before creating a Colorbar.")
        if source_component_id not in self.component_registry:
            raise ValueError("The selected Colorbar source is unavailable.")
        self.colorbar_service.validate_source(
            owner_axes_id,
            source_component_id,
        )
        component_id = object_id or new_id()
        requested = dict(properties or {})
        controller = None
        runtime = None
        with self.component_registry.registration_transaction() as transaction:
            with matplotlib_style_context(self.component_style):
                runtime, normalized = self.colorbar_service.create_runtime(
                    owner_axes_id,
                    source_component_id,
                    requested,
                    component_id=component_id,
                )
            transaction.on_rollback(
                lambda target=runtime: self.colorbar_service.destroy_runtime(target)
            )
            transaction.on_rollback(
                lambda component_id=component_id: (
                    self.axes_geometry_service.restore_colorbar_follower(
                        component_id,
                        None,
                    )
                )
            )
            state = ComponentState(
                id=component_id,
                kind=ComponentKind.COLORBAR,
                role=ComponentRole.COLORBAR,
                parent_id=owner_axes_id,
                order=(
                    self._next_child_order(owner_axes_id)
                    if component_order is None
                    else int(component_order)
                ),
                selector={"object_id": component_id},
                properties=normalized,
                data={"source_component_id": str(source_component_id)},
            )
            controller = ColorbarController(state, target=runtime)
            actual = controller.sync_from_target(strict=True)
            desired = deepcopy(actual.properties)
            for key in requested:
                desired[key] = deepcopy(normalized[key])
            applied = controller.apply_state(actual.clone(properties=desired))
            if not applied.ok:
                raise ValueError(applied.message or "Could not initialize Colorbar.")
            controller.sync_from_target(strict=True)
            self.component_registry.register(controller, target=runtime)
            self._prepare_created_component(controller, transaction)
            self.component_registry.request_update(self.fig, UpdateImpact.REDRAW)
            if self.fig.canvas is not None:
                self.fig.canvas.draw()

        self._finish_created_component(controller)
        if announce and not self._restoring_component_tree_now:
            status_messages.show_success("Colorbar created.")
        return runtime

    @_history_command("Create Secondary Axis")
    def add_secondary_axis(
        self,
        spec: SecondaryAxisCreateSpec,
        *,
        axes_id: str | None = None,
        object_id: str | None = None,
        component_order: int | None = None,
        announce: bool = True,
        allow_invalid_domain: bool = False,
    ):
        """Create one reversible parent-bound Secondary Axis atomically."""

        if not isinstance(spec, SecondaryAxisCreateSpec):
            raise TypeError("add_secondary_axis requires SecondaryAxisCreateSpec.")
        owner_axes_id = str(axes_id or self.current_axes_component_id or "")
        owner_axes = self.component_registry.resolve_target(owner_axes_id)
        if not isinstance(owner_axes, Axes):
            raise ValueError("Select an Axes before creating a Secondary Axis.")
        component_id = object_id or new_id()
        controller = None
        runtime = None
        with self.component_registry.registration_transaction() as transaction:
            with matplotlib_style_context(self.component_style):
                runtime, normalized = self.secondary_axis_service.create_runtime(
                    owner_axes_id,
                    spec,
                    allow_invalid_domain=allow_invalid_domain,
                )
            transaction.on_rollback(
                lambda target=runtime: self.secondary_axis_service.destroy_runtime(target)
            )
            role = (
                ComponentRole.SECONDARY_X_AXIS
                if spec.orientation == "x"
                else ComponentRole.SECONDARY_Y_AXIS
            )
            state = ComponentState(
                id=component_id,
                kind=ComponentKind.SECONDARY_AXIS,
                role=role,
                parent_id=owner_axes_id,
                order=(
                    self._next_child_order(owner_axes_id)
                    if component_order is None
                    else int(component_order)
                ),
                selector={"object_id": component_id},
                properties=normalized,
                data={},
            )
            controller = SecondaryAxisController(state, target=runtime)
            controller.sync_from_target(strict=True)
            self.component_registry.register(controller, target=runtime)
            self._prepare_created_component(controller, transaction)
            self.component_registry.request_update(owner_axes, UpdateImpact.REDRAW)
            if self.fig.canvas is not None:
                self.fig.canvas.draw()

        self._finish_created_component(controller)
        if announce and not self._restoring_component_tree_now:
            status_messages.show_success("Secondary Axis created.")
        return runtime

    @_history_command("Create Reflection Positions")
    def add_reference_marks(
        self,
        positions,
        properties: dict[str, Any] | None = None,
        *,
        object_id: str | None = None,
        component_order: int | None = None,
        announce: bool = True,
        position_ref=None,
        placement=None,
    ):
        """Create and publish one Reflection Positions component atomically."""

        owner_axes_id = self.current_axes_component_id
        owner_axes = self.current_axes
        if owner_axes_id is None or owner_axes is None:
            raise ValueError(
                "Select an Axes before creating Reflection Positions."
            )
        component_id = object_id or new_id()
        controller = None
        runtime = None
        with self.component_registry.registration_transaction() as transaction:
            (
                runtime,
                normalized_positions,
                normalized_ref,
                normalized,
                normalized_placement,
            ) = (
                self.reference_marks_service.create_runtime(
                    owner_axes_id,
                    positions,
                    properties,
                    position_ref,
                    placement,
                )
            )
            transaction.on_rollback(
                lambda target=runtime: (
                    self.reference_marks_service.destroy_runtime(target)
                )
            )
            state = ComponentState(
                id=component_id,
                kind=ComponentKind.REFERENCE_MARKS,
                role=ComponentRole.REFLECTION_POSITIONS,
                parent_id=owner_axes_id,
                order=(
                    self._next_child_order(owner_axes_id)
                    if component_order is None
                    else int(component_order)
                ),
                selector={"object_id": component_id},
                properties=normalized,
                data={
                    "positions": normalized_positions,
                    "position_ref": normalized_ref,
                    "placement": normalized_placement,
                },
            )
            controller = ReferenceMarksController(state, target=runtime)
            controller.bind_table(self.repository, self.project_id)
            initialized = controller.apply_state(controller.state)
            if not initialized.ok:
                raise ValueError(
                    initialized.message
                    or "Could not initialize Reflection Positions."
                )
            controller.sync_from_target(strict=True)
            self.component_registry.register(controller, target=runtime)
            runtime.set_gid(component_id)
            self._prepare_created_component(controller, transaction)
            self.component_registry.request_update(
                owner_axes,
                UpdateImpact.REDRAW,
            )
            if self.fig.canvas is not None:
                self.fig.canvas.draw()

        self._finish_created_component(controller)
        if announce and not self._restoring_component_tree_now:
            status_messages.show_success("Reflection Positions created.")
        return runtime

    @_history_command("Create Reference Line")
    def add_reference_line(
        self,
        properties: dict[str, Any] | None = None,
        *,
        object_id: str | None = None,
        component_order: int | None = None,
        announce: bool = True,
    ):
        """Create and publish one constant Reference Line atomically."""

        return self._add_reference_guide(
            ComponentRole.REFERENCE_LINE,
            properties,
            object_id=object_id,
            component_order=component_order,
            announce=announce,
        )

    @_history_command("Create Reference Band")
    def add_reference_band(
        self,
        properties: dict[str, Any] | None = None,
        *,
        object_id: str | None = None,
        component_order: int | None = None,
        announce: bool = True,
    ):
        """Create and publish one constant Reference Band atomically."""

        return self._add_reference_guide(
            ComponentRole.REFERENCE_BAND,
            properties,
            object_id=object_id,
            component_order=component_order,
            announce=announce,
        )

    def _add_reference_guide(
        self,
        role: ComponentRole,
        properties: dict[str, Any] | None,
        *,
        object_id: str | None,
        component_order: int | None,
        announce: bool,
    ):
        """Stage one guide and publish it through one registration boundary."""

        owner_axes_id = self.current_axes_component_id
        owner_axes = self.current_axes
        if owner_axes_id is None or owner_axes is None:
            raise ValueError("Select an Axes before creating a Reference Guide.")
        style_defaults = self.component_creation_defaults().reference_marks
        if role is ComponentRole.REFERENCE_LINE:
            controller_type = ReferenceLineController
            create_runtime = self.reference_guide_service.create_line_runtime
            label = "Reference Line"
            requested = {
                "color": style_defaults.color,
                "linewidth": style_defaults.linewidth,
            }
        elif role is ComponentRole.REFERENCE_BAND:
            controller_type = ReferenceBandController
            create_runtime = self.reference_guide_service.create_band_runtime
            label = "Reference Band"
            requested = {
                "facecolor": style_defaults.color,
                "edgecolor": style_defaults.color,
                "linewidth": style_defaults.linewidth,
            }
        else:
            raise ValueError("Unsupported Reference Guide role.")
        requested.update(properties or {})

        component_id = object_id or new_id()
        controller = None
        runtime = None
        with self.component_registry.registration_transaction() as transaction:
            runtime, normalized = create_runtime(owner_axes_id, requested)
            transaction.on_rollback(
                lambda target=runtime: (
                    self.reference_guide_service.destroy_runtime(target)
                )
            )
            state = ComponentState(
                id=component_id,
                kind=ComponentKind.REFERENCE_GUIDE,
                role=role,
                parent_id=owner_axes_id,
                order=(
                    self._next_child_order(owner_axes_id)
                    if component_order is None
                    else int(component_order)
                ),
                selector={"object_id": component_id},
                properties=normalized,
                data={},
            )
            controller = controller_type(state, target=runtime)
            initialized = controller.apply_state(controller.state)
            if not initialized.ok:
                raise ValueError(
                    initialized.message or f"Could not initialize {label}."
                )
            controller.sync_from_target(strict=True)
            self.component_registry.register(controller, target=runtime)
            runtime.set_gid(component_id)
            self._prepare_created_component(controller, transaction)
            self.reference_guide_service.verify_render(controller)
            self.component_registry.request_update(
                owner_axes,
                UpdateImpact.REDRAW,
            )

        self._finish_created_component(controller)
        if announce and not self._restoring_component_tree_now:
            status_messages.show_success(f"{label} created.")
        return runtime

    def _on_mpl_button_press(self, event) -> None:
        """Handle Matplotlib button_press_event for right-click Annotation creation."""

        if self._disposed or self._restoring_component_tree_now:
            return
        if getattr(event, "button", None) != 3:
            return
        toolbar_mode = str(getattr(self.navigation_toolbar, "mode", "")).strip()
        if toolbar_mode != "":
            return
        target_axes = getattr(event, "inaxes", None)
        if target_axes is None:
            return
        axes_id = None
        for controller in self.component_registry.query(kind=ComponentKind.AXES):
            if controller.resolve_target() is target_axes:
                if controller.state.role is ComponentRole.AXES:
                    axes_id = controller.component_id
                break
        if axes_id is None:
            return
        x_data = getattr(event, "xdata", None)
        y_data = getattr(event, "ydata", None)
        if (
            x_data is None
            or y_data is None
            or not (math.isfinite(x_data) and math.isfinite(y_data))
        ):
            return

        menu = QMenu(self)
        action = menu.addAction("Add Annotation Here")
        gui_event = getattr(event, "guiEvent", None)
        global_position = None
        if gui_event is not None:
            getter = getattr(gui_event, "globalPosition", None)
            if callable(getter):
                global_position = getter().toPoint()
        if menu.exec(global_position or QCursor.pos()) is not action:
            return
        properties = {
            "text": "New Annotation",
            "xy": [float(x_data), float(y_data)],
            "xycoords": "data",
            "xytext": [20.0, 20.0],
            "textcoords": "offset_points",
            "arrow_enabled": True,
        }
        try:
            annotation_artist = self.add_annotation_from_input(
                properties,
                axes_id=axes_id,
            )
            new_id = getattr(annotation_artist, "get_gid", lambda: None)()
            if new_id:
                self.select_component(new_id)
                self._focus_annotation_editor(new_id)
        except Exception as exc:
            status_messages.show_error(str(exc))

    def _focus_annotation_editor(self, component_id: str) -> None:
        """Focus the text content input of a newly created Annotation."""

        if self.figure_inspector is None:
            return
        inspector = self.component_editor_manager.editor(component_id)
        if inspector is None:
            return
        try:
            content_section = inspector.section("content")
            if hasattr(content_section, "text_content"):
                content_section.text_content.setFocus()
        except Exception:
            pass

    def export_context(self) -> FigureExportContext:
        """Return the export summary. Callers must not read canvas.fig."""

        size_inches = self.fig.get_size_inches()
        return FigureExportContext(
            project_name=self.project_name,
            document_dpi=float(self.document_dpi),
            width_inches=float(size_inches[0]),
            height_inches=float(size_inches[1]),
        )

    def export_figure(self, request: FigureExportRequest) -> None:
        """Write one validated Figure.savefig request through an atomic publish."""

        if not isinstance(request, FigureExportRequest):
            raise TypeError("export_figure requires a FigureExportRequest.")
        kwargs = request.savefig_kwargs()

        def write(temporary_path) -> None:
            with matplotlib_style_context(self.component_style):
                self.fig.savefig(temporary_path, **kwargs)

        try:
            publish_export_file(request.path, write)
        finally:
            # print_figure may leave display-space Text positions from the
            # export DPI; restore the on-screen Figure without changing state.
            self.redraw()

    def save(self, filename, dpi=None):
        """Save the current figure through the selected destination."""

        save_dpi = self.document_dpi if dpi is None else dpi
        self.export_figure(
            compatible_export_request(filename, dpi=float(save_dpi))
        )

    def dependent_records(self, refs: set[ColumnRef]) -> ComponentDependencySnapshot:
        """Return Controller snapshots for table-deletion undo."""

        return self.dependency_service.capture(
            refs,
            selected_component_id=self.current_component_id,
        )

    def _register_component_materializers(self, expected_phases) -> None:
        register_canvas_materializers(self, expected_phases)

    def _materialize_zoom_in_axes(self, state, _transaction) -> None:
        materialize_zoom_in_axes(self, state, _transaction)

    def _materialize_image_in_axes(self, state, _transaction) -> None:
        materialize_image_in_axes(self, state, _transaction)

    def _materialize_function_curve(self, state, _transaction) -> None:
        materialize_function_curve(self, state, _transaction)

    def _materialize_line(self, state, _transaction) -> None:
        materialize_line(self, state, _transaction)

    def _materializer_pair(self, state, *, preserve_gaps: bool):
        return materializer_pair(self, state, preserve_gaps=preserve_gaps)

    def _materialize_data_plot(self, state, _transaction) -> None:
        materialize_data_plot(self, state, _transaction)

    def _materialize_scatter(self, state, _transaction) -> None:
        materialize_scatter(self, state, _transaction)

    def _materialize_errorbar(self, state, _transaction) -> None:
        materialize_errorbar(self, state, _transaction)

    def _materialize_field_2d(self, state, _transaction) -> None:
        materialize_field_2d(self, state, _transaction)

    def _materialize_colorbar(self, state, _transaction) -> None:
        materialize_colorbar(self, state, _transaction)

    def _materialize_secondary_axis(self, state, _transaction) -> None:
        materialize_secondary_axis(self, state, _transaction)

    def _materialize_reference_marks(self, state, _transaction) -> None:
        materialize_reference_marks(self, state, _transaction)

    def _materialize_reference_line(self, state, _transaction) -> None:
        materialize_reference_line(self, state, _transaction)

    def _materialize_reference_band(self, state, _transaction) -> None:
        materialize_reference_band(self, state, _transaction)

    def _materialize_interpolation(self, state, _transaction) -> None:
        materialize_interpolation(self, state, _transaction)

    def _materialize_fit(self, state, _transaction) -> None:
        materialize_fit(self, state, _transaction)

    def _materialize_text(self, state, _transaction) -> None:
        materialize_text(self, state, _transaction)

    def _materialize_annotation(self, state, _transaction) -> None:
        materialize_annotation(self, state, _transaction)

    @contextmanager
    def _history_component_id_overrides(
        self,
        states: tuple[ComponentState, ...],
    ):
        """Temporarily make saved Axes semantic IDs reusable by materializers."""

        figure = next(
            (
                state
                for state in states
                if state.kind is ComponentKind.FIGURE
            ),
            None,
        )
        if figure is None:
            raise ValueError("Figure history target has no Figure root.")
        tree = {
            "root_component_id": figure.id,
            "components": [state.to_dict() for state in states],
        }
        overrides = self._component_paths_from_tree(tree)
        previous_overrides = dict(self._component_id_overrides)
        previous_allocated = set(self._allocated_component_ids)
        self._component_id_overrides.update(overrides)
        self._allocated_component_ids.difference_update(overrides.values())
        try:
            yield
        finally:
            self._component_id_overrides = previous_overrides
            self._allocated_component_ids = previous_allocated

    def materialize_history_states(
        self,
        target_states: tuple[ComponentState, ...],
        added_ids: set[str],
    ) -> None:
        """Restore structural history through Axes/materializer architecture."""

        state_by_id = {state.id: state for state in target_states}
        missing = set(added_ids) - set(state_by_id)
        if missing:
            raise ValueError(
                "Figure history is missing target states: "
                + ", ".join(sorted(missing))
            )
        axes_states = tuple(
            sorted(
                (
                    state_by_id[component_id]
                    for component_id in added_ids
                    if state_by_id[component_id].kind is ComponentKind.AXES
                ),
                key=lambda state: int(state.selector["index"]),
            )
        )
        dynamic_states = tuple(
            state_by_id[component_id]
            for component_id in added_ids
            if (state_by_id[component_id].kind, state_by_id[component_id].role)
            in self.component_materializers.keys
        )
        restorable_ids = {
            state.id for state in axes_states
        } | {state.id for state in dynamic_states}
        fixed_ids = set(added_ids) - restorable_ids
        for component_id in fixed_ids:
            state = state_by_id[component_id]
            cursor = state.parent_id
            while cursor is not None and cursor not in restorable_ids:
                parent = state_by_id.get(cursor)
                cursor = parent.parent_id if parent is not None else None
            if cursor is None:
                raise ValueError(
                    f"No materializer owns added component {component_id!r}."
                )

        previous_restoring = self._restoring_component_tree_now
        self._restoring_component_tree_now = True
        try:
            with (
                self._history_component_id_overrides(target_states),
                self.component_registry.registration_transaction(),
            ):
                if axes_states:
                    self.axes_layout_service.materialize(axes_states)
                for phase in self.component_materializers.phases:
                    for state in self.component_materializers.states_for_phase(
                        dynamic_states,
                        phase,
                    ):
                        self._restore_component_state(state)
        finally:
            self._restoring_component_tree_now = previous_restoring
        unresolved = sorted(
            component_id
            for component_id in added_ids
            if component_id not in self.component_registry
        )
        if unresolved:
            raise ValueError(
                "Figure history materialization did not restore: "
                + ", ".join(unresolved)
            )

    def _restore_component_state(self, state: ComponentState):
        """Materialize one dynamic component within registration scope."""

        if state.id in self.component_registry:
            return self.component_registry.get(state.id)
        previous_axes_id = self.current_axes_component_id
        previous_restoring = self._restoring_component_tree_now
        if state.parent_id != self.root_component_id:
            parent = self.component_registry.get(state.parent_id)
            if not isinstance(parent, AxesController):
                raise ValueError(
                    f"Dynamic component {state.id!r} requires an Axes parent."
                )
            self.current_axes_component_id = parent.component_id
        self._restoring_component_tree_now = True
        try:
            with self.component_registry.registration_transaction() as transaction:
                self.component_materializers.materialize(state, transaction)
                controller = self.component_registry.get(state.id)
                change = controller.apply_state(state)
                if not change.ok:
                    raise ValueError(change.message)
            return controller
        finally:
            self.current_axes_component_id = previous_axes_id
            self._restoring_component_tree_now = previous_restoring

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
        with self.figure_history.suspend_recording():
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
            with self.figure_history.suspend_recording():
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
        """Materialize and apply a validated schema-v17 component tree."""

        self._restoring_component_tree_now = True
        try:
            with (
                self.figure_history.suspend_recording(),
                self.component_registry.batch_events(),
                self.in_axes_service.suspend_refresh(),
            ):
                self._restore_component_tree_impl(component_tree)
        finally:
            self._restoring_component_tree_now = False
            # Component changes during materialization belong to the single
            # project-open action.  Do not let their deferred fallback message
            # overwrite the final Project opened/error result.
            self.message_presenter.discard_pending()
        target = (
            self.current_axes_component_id
            if self.current_axes_component_id in self.component_registry
            else self.root_component_id
        )
        if self.figure_inspector is not None and target in self.component_registry:
            self.select_component(target)

    def _restore_component_tree_impl(
        self,
        component_tree: dict[str, Any] | None = None,
    ) -> None:
        """Perform the materialization while creation selection is paused."""

        source = component_tree or self._restore_component_tree
        if not isinstance(source, dict):
            return
        source = normalize_v23_figure(source)
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
        axes_ids = self.axes_layout_service.materialize(axes_states)
        if axes_ids and self.current_axes_component_id is None:
            # Restoration suppresses the per-component selection side effects.
            # Publish one deterministic final Axes selection after the full
            # component tree has been applied successfully.
            self.current_axes_component_id = axes_ids[0]

        for phase in self.component_materializers.phases:
            for state in self.component_materializers.states_for_phase(
                states,
                phase,
            ):
                self._restore_component_state(state)

        self.apply_component_tree(source)

    def apply_component_tree(
        self, component_tree: dict[str, Any] | None
    ) -> None:
        """Apply all schema-v14 states after their Matplotlib targets exist."""

        self._snapshot_applier.apply_component_tree(component_tree)

    @staticmethod
    def _json_component_value(value):
        return json_component_value(value)

    def component_snapshot(self) -> dict[str, Any]:
        """Return the canonical schema-v23 component tree used by persistence."""

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
        return normalize_v23_figure(snapshot)

    def validate_component_snapshot(self) -> dict[str, Any]:
        """Validate and return the current complete schema-v23 Figure tree."""

        snapshot = self.component_snapshot()
        project = self.repository.project(self.project_id)
        available_refs = {
            ColumnRef(project.id, sheet.id, column.id): column.type
            for sheet in project.sheets.values()
            for column in sheet.columns
        }
        validate_v23_figure(
            snapshot,
            available_refs,
            self.project_id,
            self.project_name,
        )
        return snapshot
