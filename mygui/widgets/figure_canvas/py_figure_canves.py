"""Host Matplotlib figures and register their editable components."""

from contextlib import contextmanager
from copy import deepcopy
from dataclasses import dataclass
from functools import partial, wraps
from typing import Any, Optional
from PySide6.QtCore import QTimer, Qt, Signal
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QDialogButtonBox,
    QLabel,
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
    AxesCommandService,
    ChartDataService,
    ColorbarService,
    ColorConsumptionLedger,
    ComponentDeletionService,
    ComponentDependencySnapshot,
    ComponentDependencyService,
    DeleteReason,
    DeletionRequest,
    FitService,
    FunctionCurveService,
    InterpolationService,
    ReferenceGuideService,
    ReferenceMarksService,
    TextRenderService,
)
from mygui.figuremodify.history import FigureHistoryService
from mygui.widgets.figure_canvas.deletion_coordinator import DeletionCoordinator
from mygui.widgets.figure_canvas.project_metadata import ProjectMetadataPort
from mygui.widgets.figure_canvas.component_materializers import (
    ComponentMaterializer,
    ComponentMaterializerRegistry,
)
from mygui.figuremodify.components import (
    AxesController,
    ComponentEvent,
    ComponentEventKind,
    ComponentKind,
    ComponentRegistry,
    ComponentRole,
    ComponentState,
    ColorbarController,
    DataPlotController,
    FigureController,
    FitCurveController,
    FitEngine,
    FunctionCurveController,
    InterpolationController,
    ImageInAxesController,
    LineController,
    ObserverFailure,
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
from mygui.figuremodify.components.serialization import (
    deterministic_component_id,
    normalize_v15_figure,
    validate_v15_figure,
)
from mygui.figuremodify.components.property_values import marker_value
from mygui.figuremodify.axes_layout import AxesLayoutSpec
from mygui.figuremodify.axes_layout_service import AxesLayoutService
from mygui.figuremodify.in_axes import (
    ImageInAxesCreateSpec,
    InAxesCreateSpec,
    InAxesService,
    ZoomInAxesCreateSpec,
)

from mygui import tex_config
from mygui import status_messages
from mygui.database import (
    ColumnRef,
    ColumnType,
    DataPreprocessSpec,
    TableChangeSet,
    TableRepository,
    resolve_preprocessed_pair,
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
from mygui.figuremodify.matplotlib_adapter import matplotlib_style_context

from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.backends.backend_qtagg import (
    NavigationToolbar2QT as NavigationToolbar,
)
from matplotlib.figure import Figure
from matplotlib.axes import Axes

import numpy as np


def _history_command(text: str, *, scan_all: bool = False):
    """Record one public Canvas operation as a single user intent."""

    def decorate(method):
        @wraps(method)
        def wrapped(self, *args, **kwargs):
            history = getattr(self, "figure_history", None)
            if history is None:
                return method(self, *args, **kwargs)
            return history.perform(
                text,
                lambda: method(self, *args, **kwargs),
                scan_all=scan_all,
            )

        return wrapped

    return decorate


class _ProjectNavigationToolbar(NavigationToolbar):
    """Add project history boundaries to persisted canvas view actions."""

    def __init__(self, canvas, parent, history) -> None:
        self._project_history = history
        super().__init__(canvas, parent)

    def home(self, *args):
        return self._project_history.perform(
            "Reset Figure View",
            lambda: super(_ProjectNavigationToolbar, self).home(*args),
            scan_all=True,
        )

    def back(self, *args):
        return self._project_history.perform(
            "Back Figure View",
            lambda: super(_ProjectNavigationToolbar, self).back(*args),
            scan_all=True,
        )

    def forward(self, *args):
        return self._project_history.perform(
            "Forward Figure View",
            lambda: super(_ProjectNavigationToolbar, self).forward(*args),
            scan_all=True,
        )

    def edit_parameters(self):
        result = super().edit_parameters()
        dialog = getattr(self, "_fedit_dialog", None)
        if dialog is None or bool(
            dialog.property("mygui_history_connected")
        ):
            return result
        dialog.setProperty("mygui_history_connected", True)
        apply_button = dialog.bbox.button(
            QDialogButtonBox.StandardButton.Apply
        )
        ok_button = dialog.bbox.button(
            QDialogButtonBox.StandardButton.Ok
        )
        if apply_button is not None:
            apply_button.pressed.connect(
                lambda: self._project_history.begin_interaction(
                    "Customize Figure"
                )
            )
            apply_button.clicked.connect(
                self._project_history.end_interaction
            )
        if ok_button is not None:
            ok_button.pressed.connect(
                lambda: self._project_history.begin_interaction(
                    "Customize Figure"
                )
            )
            dialog.accepted.connect(self._project_history.end_interaction)
        dialog.rejected.connect(self._project_history.cancel_interaction)
        return result

    def press_pan(self, event):
        started = self._project_history.begin_interaction("Pan Figure View")
        try:
            result = super().press_pan(event)
        except Exception:
            if started:
                self._project_history.cancel_interaction()
            raise
        if started and self._pan_info is None:
            self._project_history.cancel_interaction()
        return result

    def release_pan(self, event):
        active = self._pan_info is not None
        try:
            result = super().release_pan(event)
        except Exception:
            if active:
                self._project_history.cancel_interaction()
            raise
        if active:
            self._project_history.end_interaction()
        return result

    def press_zoom(self, event):
        started = self._project_history.begin_interaction("Zoom Figure View")
        try:
            result = super().press_zoom(event)
        except Exception:
            if started:
                self._project_history.cancel_interaction()
            raise
        if started and self._zoom_info is None:
            self._project_history.cancel_interaction()
        return result

    def release_zoom(self, event):
        active = self._zoom_info is not None
        try:
            result = super().release_zoom(event)
        except Exception:
            if active:
                self._project_history.cancel_interaction()
            raise
        if active:
            self._project_history.end_interaction()
        return result


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


class _CanvasPopoutWindow(QDialog):
    """Temporarily host one Canvas scroll area in a top-level window."""

    def __init__(self, owner: "PyFigureCanvas") -> None:
        # Keep this native window parentless.  A QDialog whose QObject parent
        # is the Canvas can become only a transient/owned window on Windows;
        # with MyGUI's custom main window that leaves the dialog behind the
        # owner even after raise_()/activateWindow().  PyFigureCanvas retains
        # and closes this object explicitly, so QObject parenting is not
        # needed for lifetime management.
        super().__init__(None, Qt.Window)
        self._owner = owner
        self._content: QWidget | None = None
        self._canvas_returned = False
        self.setObjectName("figure_popout_window")
        self.setWindowModality(Qt.NonModal)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        # Esc must close the window even while the Canvas holds the keyboard
        # focus, and the Matplotlib canvas consumes key events without
        # propagating them.  A window shortcut is resolved before the focus
        # widget sees the key, unlike QDialog's own Esc handling.
        self._close_shortcut = QShortcut(QKeySequence(Qt.Key_Escape), self)
        self._close_shortcut.setContext(Qt.WindowShortcut)
        self._close_shortcut.activated.connect(self.close)

    def attach_content(self, content: QWidget) -> None:
        """Attach the unique live Canvas content widget."""

        if self._content is not None:
            raise RuntimeError("The Canvas popout already owns content.")
        self._content = content
        self.layout().addWidget(content)
        # The project tab hid this widget explicitly when its QStackedWidget
        # switched to the placeholder.  Reparenting preserves that flag, so
        # without an explicit show the window stays empty and reports a
        # 0 x 0 size hint.
        content.setVisible(True)
        self.layout().activate()

    @property
    def canvas_returned(self) -> bool:
        """Return whether this window already handed its Canvas back."""

        return self._canvas_returned

    def release_content(self) -> QWidget | None:
        """Detach and return the hosted content exactly once."""

        content = self._content
        self._canvas_returned = True
        if content is None:
            return None
        self.layout().removeWidget(content)
        self._content = None
        return content

    def closeEvent(self, event) -> None:
        """Return the Canvas content before the top-level window closes."""

        self._owner._restore_canvas_from_popout(self)
        super().closeEvent(event)

    def done(self, result: int) -> None:
        """Return the Canvas on every QDialog result path.

        ``QDialog.reject()`` hides the window without sending a close event,
        which would otherwise leave the live Canvas inside an invisible window
        while the project tab keeps showing its placeholder.
        """

        self._owner._restore_canvas_from_popout(self)
        super().done(result)


class PyFigureCanvas(QWidget):
    """Provide the py figure canvas Qt widget."""

    componentSelectionChanged = Signal(str)

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
        self.function_curve_service = FunctionCurveService(
            self.component_registry
        )
        self.chart_data_service = ChartDataService(
            self.repository,
            self.component_registry,
        )
        self.colorbar_service = ColorbarService(self.component_registry)
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
            axes_layout=self.axes_layout_service,
            function_curves=self.function_curve_service,
            chart_data=self.chart_data_service,
            interpolation=self.interpolation_service,
            fitting=self.fit_service,
            text_rendering=self.text_render_service,
            colorbars=self.colorbar_service,
            reference_marks=self.reference_marks_service,
            reference_guides=self.reference_guide_service,
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
                        tick_path = f"{axes_path}/axis/{axis_name}/tick/{level}"
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
                        paths[f"{axes_path}/axis/{axis_name}/grid/{level}"] = (
                            component_id
                        )
        return paths

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
        try:
            self.repository.transaction_committed.disconnect(self._table_changed)
        except (RuntimeError, TypeError):
            pass
        if self._selection_unsubscribe is not None:
            self._selection_unsubscribe()
            self._selection_unsubscribe = None
        self.figure_history.dispose()
        self.message_presenter.close()
        self.component_registry.set_observer_failure_handler(None)
        self.component_editor_manager.close()
        self.axes_layout_service.dispose()
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
    ) -> tuple[
        tuple[str, ...],
        dict[str, Any] | None,
        bool,
        tuple[tuple[dict[str, Any] | None, dict[str, Any]], ...],
    ]:
        if not isinstance(selection, ColorSelection):
            raise TypeError("Batch chart color must be a ColorSelection.")
        if selection.palette is None:
            return (
                tuple(selection.color for _index in range(count)),
                None,
                False,
                (),
            )
        axes_id = self.current_axes_component_id
        if axes_id is None:
            raise ValueError("Select an axes before adding charts.")
        cycle = self.axes_commands.cycle_state(axes_id)
        colors: list[str] = []
        transitions = []
        next_selection = selection
        for index in range(count):
            if index:
                next_selection = cycle.peek()
            colors.append(next_selection.color)
            before = cycle.to_dict()
            cycle.commit(next_selection)
            transitions.append((before, cycle.to_dict()))
        return tuple(colors), cycle.to_dict(), True, tuple(transitions)

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
        tuple[_PreparedChartSeries, ...],
        dict[str, Any] | None,
        bool,
        tuple[tuple[dict[str, Any] | None, dict[str, Any]], ...],
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
                        "X Data and Y Data have no valid row pairs after preprocessing."
                    )
            except Exception as exc:
                raise ValueError(f"{label}: {exc}") from exc
            resolved.append((y_ref, label, pair))
        if consume_palette:
            colors, final_cycle, commit_cycle, transitions = (
                self._batch_color_plan(
                    color_selection,
                    len(resolved),
                )
            )
        else:
            if not isinstance(color_selection, ColorSelection):
                raise TypeError("Batch chart color must be a ColorSelection.")
            colors = tuple(color_selection.color for _item in resolved)
            final_cycle = None
            commit_cycle = False
            transitions = ()
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
        return prepared, final_cycle, commit_cycle, transitions

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
        with matplotlib_style_context(self.component_style):
            (line,) = self.current_axes.plot(series.x, series.y, **plot_kwargs)
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
        color_ref: ColumnRef | None = None,
        size_ref: ColumnRef | None = None,
        color_mapping: dict[str, Any] | None = None,
        size_mapping: dict[str, Any] | None = None,
        object_id: str | None = None,
        color_order: int | None = None,
    ):
        object_id = object_id or new_id()
        with matplotlib_style_context(self.component_style):
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
        properties = {
            "color": series.color,
            "edgecolor": series.color,
            "size": float(size),
            "marker": marker,
            "label": series.label,
        }
        if color_mapping is not None:
            properties["color_mapping"] = deepcopy(color_mapping)
        if size_mapping is not None:
            properties["size_mapping"] = deepcopy(size_mapping)
        controller = self._register_chart_controller(
            ScatterController,
            object_id,
            ComponentRole.SCATTER,
            scatter,
            component_order,
            properties,
            {
                "x_ref": series.x_ref.to_dict(),
                "y_ref": series.y_ref.to_dict(),
                "color_ref": (
                    None if color_ref is None else color_ref.to_dict()
                ),
                "size_ref": (
                    None if size_ref is None else size_ref.to_dict()
                ),
                "preprocess": preprocess.to_dict(),
            },
        )
        if color_mapping is not None or size_mapping is not None:
            state = controller.state
            change = self.chart_data_service.configure_scatter_mapping(
                controller,
                color_ref=color_ref,
                size_ref=size_ref,
                color_mapping=state.properties["color_mapping"],
                size_mapping=state.properties["size_mapping"],
            )
            if not change.ok:
                raise ValueError(
                    change.message or "Could not configure Scatter mapping."
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
        with matplotlib_style_context(self.component_style):
            (line,) = self.current_axes.plot(
                series.x,
                series.y,
                color=series.color,
                label=series.label,
            )
        transaction.on_rollback(lambda line=line: self._remove_created_artist(line))
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
        color_transitions: tuple[tuple[dict[str, Any] | None, dict[str, Any]], ...],
        record_recent: bool = True,
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
        for controller, (before, after) in zip(
            controllers,
            color_transitions,
        ):
            self.color_consumption_ledger.record(
                axes_id,
                controller.component_id,
                before,
                after,
            )
        self._select_created_component(controllers[-1])
        self.redraw()
        colors = tuple(series.color for series in prepared)
        if record_recent:
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
    def create_axes_layout(self, spec: AxesLayoutSpec) -> tuple[str, ...]:
        """Create a validated Axes layout through the domain service."""

        return self.axes_layout_service.create(spec)

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
    ):
        """Add curve."""

        color = normalize_color(color)
        object_id = object_id or new_id()
        x = np.linspace(x_start, x_stop, 1000)
        y = evaluate_curve_expression(func_text, x)
        with self.component_registry.registration_transaction() as transaction:
            with matplotlib_style_context(self.component_style):
                (line,) = self.current_axes.plot(
                    x, y, ls=style, color=color, label=label
                )
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
            color_transition = self._commit_single_creation_color(
                transaction,
                color_selection,
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
            self.color_library.record_recent(color)
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
        self._finish_created_component(controller)
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
    ) -> ChartBatchCreationResult:
        """Atomically create one Plot component for every selected Y column."""

        spec = DataPreprocessSpec.from_dict(preprocess)
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
                style=style,
                size=size,
                linewidth=linewidth,
                preprocess=spec,
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
                color_ref=color_ref,
                size_ref=size_ref,
                color_mapping=color_mapping,
                size_mapping=size_mapping,
                object_id=object_id,
                color_order=color_order,
            )
        self._finish_created_component(controller)
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
                size=size,
                marker=marker,
                preprocess=spec,
                color_ref=color_ref,
                size_ref=size_ref,
                color_mapping=color_spec,
                size_mapping=size_spec,
            ),
            final_cycle=final_cycle,
            commit_cycle=commit_cycle,
            color_transitions=transitions,
            record_recent=record_recent,
        )

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
        *,
        color_selection: ColorSelection | None = None,
        preview_cycle: ColorCycleState | None = None,
    ):
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
        try:
            engine = FitEngine(engine)
        except ValueError as exc:
            raise ValueError(
                f"Unsupported fitting engine: {engine}"
            ) from exc

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
                line_y = evaluate_curve_expression(
                    expression,
                    line_x,
                    limits=GENERATED_FIT_EXPRESSION_LIMITS,
                )
            except ValueError:
                status_messages.show_error("Saved fit expression could not be restored; showing source data.")
                expression = ""

        plot_kwargs = {"color": color, "label": label}
        if style is not None:
            plot_kwargs["linestyle"] = style
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
                {
                    "linestyle": line.get_linestyle(),
                    "color": color,
                    "label": label,
                },
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
                },
            )
            self._prepare_created_component(controller, transaction)
            color_transition = self._commit_single_creation_color(
                transaction,
                color_selection,
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
            self.color_library.record_recent(color)
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
        self._finish_created_component(controller)
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
    ) -> ChartBatchCreationResult:
        """Atomically create one interpolation component for every Y."""

        spec = DataPreprocessSpec.from_dict(preprocess)
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
            color_transitions=transitions,
        )

    # Add text
    @staticmethod
    def _resolve_text_usetex(usetex: bool | None) -> bool:
        if usetex is None:
            return tex_config.is_tex_enabled()
        return bool(usetex) and tex_config.is_tex_enabled()

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
    ):
        """Add text."""

        desired_usetex = self._resolve_text_usetex(usetex)
        with matplotlib_style_context(self.component_style):
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
    ):
        """Add global text."""

        desired_usetex = self._resolve_text_usetex(usetex)
        with matplotlib_style_context(self.component_style):
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
        if not self._restoring_component_tree_now and (not result.ok or result.notices):
            self.message_presenter.present(result)
        self._finish_created_component(controller)
        return text_artist

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
                )
            transaction.on_rollback(
                lambda target=runtime: self.colorbar_service.destroy_runtime(target)
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
            runtime, normalized_positions, normalized_ref, normalized = (
                self.reference_marks_service.create_runtime(
                    owner_axes_id,
                    positions,
                    properties,
                    position_ref,
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

    def save(self, filename, dpi=None):
        """Save the current figure through the selected destination."""

        if dpi is None:
            save_dpi = self.document_dpi
        else:
            save_dpi = dpi
        with matplotlib_style_context(self.component_style):
            self.fig.savefig(filename, dpi=save_dpi)

    def dependent_records(self, refs: set[ColumnRef]) -> ComponentDependencySnapshot:
        """Return Controller snapshots for table-deletion undo."""

        return self.dependency_service.capture(
            refs,
            selected_component_id=self.current_component_id,
        )

    def _register_component_materializers(self, expected_phases) -> None:
        declarations = (
            ComponentMaterializer(
                (ComponentKind.IN_AXES, ComponentRole.IN_AXES_ZOOM),
                self._materialize_zoom_in_axes,
                expected_phases[
                    (ComponentKind.IN_AXES, ComponentRole.IN_AXES_ZOOM)
                ],
            ),
            ComponentMaterializer(
                (ComponentKind.IN_AXES, ComponentRole.IN_AXES_IMAGE),
                self._materialize_image_in_axes,
                expected_phases[
                    (ComponentKind.IN_AXES, ComponentRole.IN_AXES_IMAGE)
                ],
            ),
            ComponentMaterializer(
                (ComponentKind.LINE, ComponentRole.FUNCTION_CURVE),
                self._materialize_function_curve,
                expected_phases[
                    (ComponentKind.LINE, ComponentRole.FUNCTION_CURVE)
                ],
            ),
            ComponentMaterializer(
                (ComponentKind.LINE, ComponentRole.LINE),
                self._materialize_line,
                expected_phases[(ComponentKind.LINE, ComponentRole.LINE)],
            ),
            ComponentMaterializer(
                (ComponentKind.LINE, ComponentRole.DATA_PLOT),
                self._materialize_data_plot,
                expected_phases[
                    (ComponentKind.LINE, ComponentRole.DATA_PLOT)
                ],
            ),
            ComponentMaterializer(
                (ComponentKind.SCATTER, ComponentRole.SCATTER),
                self._materialize_scatter,
                expected_phases[
                    (ComponentKind.SCATTER, ComponentRole.SCATTER)
                ],
            ),
            ComponentMaterializer(
                (ComponentKind.COLORBAR, ComponentRole.COLORBAR),
                self._materialize_colorbar,
                expected_phases[
                    (ComponentKind.COLORBAR, ComponentRole.COLORBAR)
                ],
            ),
            ComponentMaterializer(
                (
                    ComponentKind.REFERENCE_MARKS,
                    ComponentRole.REFLECTION_POSITIONS,
                ),
                self._materialize_reference_marks,
                expected_phases[
                    (
                        ComponentKind.REFERENCE_MARKS,
                        ComponentRole.REFLECTION_POSITIONS,
                    )
                ],
            ),
            ComponentMaterializer(
                (
                    ComponentKind.REFERENCE_GUIDE,
                    ComponentRole.REFERENCE_LINE,
                ),
                self._materialize_reference_line,
                expected_phases[
                    (
                        ComponentKind.REFERENCE_GUIDE,
                        ComponentRole.REFERENCE_LINE,
                    )
                ],
            ),
            ComponentMaterializer(
                (
                    ComponentKind.REFERENCE_GUIDE,
                    ComponentRole.REFERENCE_BAND,
                ),
                self._materialize_reference_band,
                expected_phases[
                    (
                        ComponentKind.REFERENCE_GUIDE,
                        ComponentRole.REFERENCE_BAND,
                    )
                ],
            ),
            ComponentMaterializer(
                (ComponentKind.LINE, ComponentRole.INTERPOLATION),
                self._materialize_interpolation,
                expected_phases[
                    (ComponentKind.LINE, ComponentRole.INTERPOLATION)
                ],
            ),
            ComponentMaterializer(
                (ComponentKind.LINE, ComponentRole.FIT_CURVE),
                self._materialize_fit,
                expected_phases[
                    (ComponentKind.LINE, ComponentRole.FIT_CURVE)
                ],
            ),
            ComponentMaterializer(
                (ComponentKind.TEXT, ComponentRole.TEXT),
                self._materialize_text,
                expected_phases[(ComponentKind.TEXT, ComponentRole.TEXT)],
            ),
        )
        for declaration in declarations:
            self.component_materializers.register(declaration)
        self.component_materializers.validate_complete(expected_phases)

    def _materialize_zoom_in_axes(self, state, _transaction) -> None:
        if state.role is not ComponentRole.IN_AXES_ZOOM:
            raise ValueError("Zoom materializer requires an in-axes Zoom state.")
        properties = state.properties
        spec = ZoomInAxesCreateSpec(
            bounds=tuple(properties["bounds"]),
            xlim=tuple(properties["xlim"]),
            ylim=tuple(properties["ylim"]),
            facecolor=properties["facecolor"],
            edgecolor=properties["edgecolor"],
            linewidth=properties["linewidth"],
            indicator_color=properties["region_color"],
            indicator_linestyle=(
                properties["region_linestyle"].get("value", "-")
                if isinstance(properties["region_linestyle"], dict)
                else properties["region_linestyle"]
            ),
            indicator_linewidth=properties["region_linewidth"],
            indicator_alpha=properties["region_alpha"],
            visible=properties["visible"],
            zorder=properties["zorder"],
            frameon=properties["frameon"],
            ticks_visible=properties["ticks_visible"],
            region_visible=properties["region_visible"],
            connectors_visible=any(item["visible"] for item in properties["connectors"]),
        )
        self.add_in_axes(spec, object_id=state.id)

    def _materialize_image_in_axes(self, state, _transaction) -> None:
        if state.role is not ComponentRole.IN_AXES_IMAGE:
            raise ValueError("Image materializer requires an in-axes Image state.")
        properties = state.properties
        data = state.data
        spec = ImageInAxesCreateSpec(
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
            origin=properties["origin"],
            extent=properties["extent"],
            resample=properties["resample"],
            filternorm=properties["filternorm"],
            filterrad=properties["filterrad"],
            interpolation_stage=properties["interpolation_stage"],
            image_visible=properties["image_visible"],
            image_zorder=properties["image_zorder"],
            image_clip_on=properties["image_clip_on"],
            image_rasterized=properties["image_rasterized"],
            image_in_layout=properties["image_in_layout"],
            image_snap=properties["image_snap"],
            image_gid=properties["image_gid"],
            image_url=properties["image_url"],
            visible=properties["visible"],
            zorder=properties["zorder"],
            frameon=properties["frameon"],
        )
        self.add_in_axes(spec, object_id=state.id)

    def _materialize_function_curve(self, state, _transaction) -> None:
        pattern = state.properties.get("linestyle", {"kind": "preset", "value": "-"})
        style = pattern.get("value", "-") if pattern.get("kind") == "preset" else (pattern["offset"], pattern["dashes"])
        self.add_curve(
            state.data["expression"],
            state.data["x_start"],
            state.data["x_stop"],
            style,
            state.properties.get("color", "black"),
            state.properties.get("label", ""),
            object_id=state.id,
            color_order=state.order,
        )

    def _materialize_line(self, state, _transaction) -> None:
        pattern = state.properties.get("linestyle", {"kind": "preset", "value": "-"})
        style = pattern.get("value", "-") if pattern.get("kind") == "preset" else (pattern["offset"], pattern["dashes"])
        self.add_component_line(
            state.data.get("x", []),
            state.data.get("y", []),
            style,
            state.properties.get("color", "black"),
            state.properties.get("label", ""),
            object_id=state.id,
            color_order=state.order,
        )

    def _materializer_pair(self, state, *, preserve_gaps: bool):
        x_ref = ColumnRef.from_dict(state.data["x_ref"])
        y_ref = ColumnRef.from_dict(state.data["y_ref"])
        preprocess = DataPreprocessSpec.from_dict(state.data["preprocess"])
        pair = resolve_preprocessed_pair(
            self.repository,
            x_ref,
            y_ref,
            preprocess,
            preserve_gaps=preserve_gaps,
        )
        return x_ref, y_ref, preprocess, pair

    def _materialize_data_plot(self, state, _transaction) -> None:
        x_ref, y_ref, preprocess, pair = self._materializer_pair(
            state,
            preserve_gaps=True,
        )
        pattern = state.properties.get("linestyle", {"kind": "preset", "value": "-"})
        style = pattern.get("value", "-") if pattern.get("kind") == "preset" else (pattern["offset"], pattern["dashes"])
        self.add_plot(
            pair.x,
            pair.y,
            style,
            state.properties.get("markersize", 2.0),
            state.properties.get("color", "black"),
            state.properties.get("label", ""),
            x_ref,
            y_ref,
            object_id=state.id,
            color_order=state.order,
            preprocess=preprocess,
        )

    def _materialize_scatter(self, state, _transaction) -> None:
        x_ref, y_ref, preprocess, pair = self._materializer_pair(
            state,
            preserve_gaps=False,
        )
        self.add_scatter(
            pair.x,
            pair.y,
            state.properties.get("size", 20.0),
            state.properties.get("color", "black"),
            marker_value(state.properties.get("marker", {"kind": "symbol", "value": "o"})),
            state.properties.get("label", ""),
            x_ref,
            y_ref,
            object_id=state.id,
            color_order=state.order,
            preprocess=preprocess,
            color_ref=(
                None
                if state.data.get("color_ref") is None
                else ColumnRef.from_dict(state.data["color_ref"])
            ),
            size_ref=(
                None
                if state.data.get("size_ref") is None
                else ColumnRef.from_dict(state.data["size_ref"])
            ),
            color_mapping=state.properties["color_mapping"],
            size_mapping=state.properties["size_mapping"],
        )

    def _materialize_colorbar(self, state, _transaction) -> None:
        if (
            state.kind is not ComponentKind.COLORBAR
            or state.role is not ComponentRole.COLORBAR
        ):
            raise ValueError("Colorbar materializer requires a Colorbar state.")
        source_id = state.data.get("source_component_id")
        if not isinstance(source_id, str) or source_id not in self.component_registry:
            raise ValueError("Colorbar source component is unavailable.")
        self.add_colorbar(
            source_id,
            state.properties,
            object_id=state.id,
            component_order=state.order,
            announce=False,
        )

    def _materialize_reference_marks(self, state, _transaction) -> None:
        if (
            state.kind is not ComponentKind.REFERENCE_MARKS
            or state.role is not ComponentRole.REFLECTION_POSITIONS
        ):
            raise ValueError(
                "Reference Marks materializer requires Reflection Positions."
            )
        self.add_reference_marks(
            state.data["positions"],
            state.properties,
            object_id=state.id,
            component_order=state.order,
            announce=False,
            position_ref=state.data.get("position_ref"),
        )

    def _materialize_reference_line(self, state, _transaction) -> None:
        if (
            state.kind is not ComponentKind.REFERENCE_GUIDE
            or state.role is not ComponentRole.REFERENCE_LINE
        ):
            raise ValueError(
                "Reference Line materializer requires a Reference Line state."
            )
        self.add_reference_line(
            state.properties,
            object_id=state.id,
            component_order=state.order,
            announce=False,
        )

    def _materialize_reference_band(self, state, _transaction) -> None:
        if (
            state.kind is not ComponentKind.REFERENCE_GUIDE
            or state.role is not ComponentRole.REFERENCE_BAND
        ):
            raise ValueError(
                "Reference Band materializer requires a Reference Band state."
            )
        self.add_reference_band(
            state.properties,
            object_id=state.id,
            component_order=state.order,
            announce=False,
        )

    def _materialize_interpolation(self, state, _transaction) -> None:
        x_ref, y_ref, preprocess, pair = self._materializer_pair(
            state,
            preserve_gaps=False,
        )
        self.add_interpolate_curve(
            pair.x,
            pair.y,
            x_ref,
            y_ref,
            state.data["method"],
            k=state.data.get("k", 3),
            label=state.properties.get("label", "interpolate"),
            color=state.properties.get("color", "black"),
            samples=state.data.get("samples", DEFAULT_INTERPOLATION_SAMPLES),
            lam=state.data.get("lam"),
            lam_auto=state.data.get("lam_auto", True),
            object_id=state.id,
            color_order=state.order,
            allow_empty=True,
            preprocess=preprocess,
            announce=False,
        )

    def _materialize_fit(self, state, _transaction) -> None:
        x_ref, y_ref, preprocess, pair = self._materializer_pair(
            state,
            preserve_gaps=False,
        )
        pattern = state.properties.get("linestyle", {"kind": "preset", "value": "-"})
        style = pattern.get("value", "-") if pattern.get("kind") == "preset" else (pattern["offset"], pattern["dashes"])
        self.add_fit_curve(
            pair.x,
            pair.y,
            state.properties.get("color", "black"),
            state.properties.get("label", "fitting"),
            x_ref,
            y_ref,
            engine=state.data.get("engine", FitEngine.PYTHON.value),
            fit_type=state.data.get("fit_type"),
            fit_options=state.data.get("fit_options"),
            fit_result=state.data.get("fit_result"),
            expression=state.data.get("expression", ""),
            x_start=state.data.get("x_start"),
            x_stop=state.data.get("x_stop"),
            style=style,
            object_id=state.id,
            color_order=state.order,
            preprocess=preprocess,
        )

    def _materialize_text(self, state, _transaction) -> None:
        properties = state.properties
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
        """Materialize and apply a validated schema-v15 component tree."""

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
        source = normalize_v15_figure(source)
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

        if not isinstance(component_tree, dict):
            return
        states = [
            ComponentState.from_dict(raw_state)
            for raw_state in component_tree.get("components", [])
        ]
        states = list(
            self.axes_layout_service.repair_legacy_minor_locator_states(states)
        )
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
            state for state in states if state.kind is ComponentKind.FIGURE
        ]
        axes_states = [state for state in states if state.kind is ComponentKind.AXES]
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
                    use_effective_fallback = (
                        source_state.kind is ComponentKind.TEXT
                        and source_state.properties.get("usetex")
                        and not tex_config.is_tex_enabled()
                    )
                    change = controller.apply_state(source_state)
                    if not change.ok:
                        raise ValueError(
                            f"Could not restore component {source_state.id}: {change.message}"
                        )
                    if use_effective_fallback:
                        fallback = (
                            self.text_render_service.apply_tex_availability(
                                False,
                                force=True,
                            )
                        )
                        if not fallback.committed:
                            raise ValueError(fallback.message)
                        tex_fallback = True

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
                if bool(legend_state.properties.get("visible", True)):
                    self.axes_commands.ensure_legend(
                        legend_state.parent_id
                    )
            result = self.axes_commands.apply_legend_properties(
                controller,
                legend_state.properties,
            )
            if not result.ok:
                raise ValueError(
                    f"Could not restore component {legend_state.id}: {result.message}"
                )
        self.axes_layout_service.restore_runtime_relationships(refresh=True)
        self.component_registry.validate_tree()
        self.component_registry.validate_axes_targets()
        if tex_fallback:
            status_messages.show_warning(
                "TeX text is displayed with Matplotlib text rendering until "
                "TeX is enabled; its saved TeX preference was preserved."
            )

        self.redraw()

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
        """Return the canonical schema-v15 component tree used by persistence."""

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
        return normalize_v15_figure(snapshot)

    def validate_component_snapshot(self) -> dict[str, Any]:
        """Validate and return the current complete schema-v15 Figure tree."""

        snapshot = self.component_snapshot()
        project = self.repository.project(self.project_id)
        available_refs = {
            ColumnRef(project.id, sheet.id, column.id): column.type
            for sheet in project.sheets.values()
            for column in sheet.columns
        }
        validate_v15_figure(
            snapshot,
            available_refs,
            self.project_id,
            self.project_name,
        )
        return snapshot
