"""Element creation staging without Canvas-owned state."""

from __future__ import annotations

import math
from copy import deepcopy
from typing import Any, Protocol

from matplotlib.axes import Axes
from PySide6.QtGui import QCursor
from PySide6.QtWidgets import QMenu

from mygui import status_messages
from mygui.database import ColumnRef
from mygui.database.table_document import new_id
from mygui.figuremodify.component_services import (
    SecondaryAxisCreateSpec,
    default_field_2d_properties,
)
from mygui.figuremodify.components import (
    AnnotationController,
    ColorbarController,
    ComponentKind,
    ComponentRole,
    ComponentState,
    ContourController,
    HeatmapController,
    ImageInAxesController,
    PseudocolorController,
    ReferenceBandController,
    ReferenceLineController,
    ReferenceMarksController,
    SecondaryAxisController,
    UpdateImpact,
    ZoomInAxesController,
    decode_in_axes_image,
)
from mygui.figuremodify.in_axes import (
    ImageInAxesCreateSpec,
    ZoomInAxesCreateSpec,
)
from mygui.figuremodify.matplotlib_adapter import matplotlib_style_context
from mygui.figuremodify.services.annotation import annotation_artist_kwargs
from mygui.widgets.figure_canvas.creation_requests import (
    AnnotationCreateRequest,
    ColorbarCreateRequest,
    Field2DCreateRequest,
    InAxesElementCreateRequest,
    ReferenceGuideCreateRequest,
    ReferenceMarksCreateRequest,
    SecondaryAxisElementRequest,
    TextCreateRequest,
)
from mygui.widgets.figure_canvas.canvas_host import (
    CanvasRegistrationHost,
    CanvasSelectionHost,
)


class ElementCreationHost(CanvasRegistrationHost, CanvasSelectionHost, Protocol):
    """Element staging extras on top of the narrow Canvas helper slices."""

    component_style: str
    current_axes: Any
    current_axes_component_id: str | None
    fig: Any
    in_axes_service: Any
    field_2d_service: Any
    colorbar_service: Any
    axes_geometry_service: Any
    secondary_axis_service: Any
    reference_marks_service: Any
    reference_guide_service: Any
    text_render_service: Any
    message_presenter: Any
    navigation_toolbar: Any
    figure_inspector: Any
    component_editor_manager: Any
    _disposed: bool
    _restoring_component_tree_now: bool
    root_component_id: str
    repository: Any
    project_id: str

    def _resolve_text_usetex(self, usetex: bool | None) -> bool:
        ...

    def _resolve_text_creation(self, **kwargs: Any) -> Any:
        ...

    def _read_component_defaults(self) -> Any:
        ...

    def component_creation_defaults(self) -> Any:
        ...

    def add_annotation_from_input(self, *args: Any, **kwargs: Any) -> Any:
        ...

    def _focus_annotation_editor(self, component_id: str) -> None:
        ...


class ElementCreationStager:
    """Stage in-Axes and annotation-like elements through the Canvas host."""

    def __init__(self, host: ElementCreationHost) -> None:
        self._host = host

    def free_text_artist_kwargs(
        self,
        fontfamily,
        fontsize,
        *,
        color=None,
        fontweight=None,
        fontstyle=None,
    ) -> dict[str, Any]:
        host = self._host
        if host._restoring_component_tree_now:
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
        resolved = host._resolve_text_creation(
            settings=host._read_component_defaults(),
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

    def create_text(self, request: TextCreateRequest):
        host = self._host
        desired_usetex = host._resolve_text_usetex(request.usetex)
        text_kwargs = self.free_text_artist_kwargs(
            request.fontfamily,
            request.fontsize,
            color=request.color,
            fontweight=request.fontweight,
            fontstyle=request.fontstyle,
        )
        if request.scope == "figure":
            with matplotlib_style_context(host.component_style):
                text_artist = host.fig.text(
                    request.x,
                    request.y,
                    request.text,
                    **text_kwargs,
                )
            object_id = request.object_id or new_id()
            parent_id = host.root_component_id
            kind_scope = "figure"
        else:
            with matplotlib_style_context(host.component_style):
                text_artist = host.current_axes.text(
                    request.x,
                    request.y,
                    request.text,
                    transform=host.current_axes.transAxes,
                    **text_kwargs,
                )
            object_id = request.object_id or new_id()
            parent_id = host.current_axes_component_id
            kind_scope = "axes"
        with host.component_registry.registration_transaction() as transaction:
            transaction.on_rollback(
                lambda: host._remove_created_artist(text_artist)
            )
            controller = host._register_text_controller(
                object_id,
                text_artist,
                parent_id=parent_id,
                order=host._next_child_order(
                    parent_id,
                    kind=ComponentKind.TEXT,
                ),
                scope=kind_scope,
            )
            result = host.text_render_service.apply(
                controller,
                {"usetex": desired_usetex},
            )
            host._prepare_created_component(controller, transaction)
        if not host._restoring_component_tree_now and (not result.ok or result.notices):
            host.message_presenter.present(result)
        host._finish_created_component(controller)
        return text_artist

    def create_annotation(self, request: AnnotationCreateRequest):
        host = self._host
        owner_axes_id = (
            request.axes_id
            if request.axes_id is not None
            else host.current_axes_component_id
        )
        if owner_axes_id is None:
            raise ValueError("Select an Axes before creating an Annotation.")
        parent = host.component_registry.get(owner_axes_id)
        if parent.state.kind is not ComponentKind.AXES:
            raise ValueError("Annotations must be owned by a normal Axes.")
        axes = parent.resolve_target()

        merged = AnnotationController.default_properties()
        merged.update(request.properties or {})
        component_id = request.object_id or new_id()
        artist_kwargs = annotation_artist_kwargs(merged)

        with host.component_registry.registration_transaction() as transaction:
            with matplotlib_style_context(host.component_style):
                annotation = axes.annotate(merged["text"], **artist_kwargs)
            transaction.on_rollback(
                lambda: host._remove_created_artist(annotation)
            )
            state = ComponentState(
                id=component_id,
                kind=ComponentKind.ANNOTATION,
                role=ComponentRole.ANNOTATION,
                parent_id=owner_axes_id,
                order=(
                    host._next_child_order(
                        owner_axes_id,
                        kind=ComponentKind.ANNOTATION,
                    )
                    if request.component_order is None
                    else int(request.component_order)
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
            host.component_registry.register(controller, target=annotation)
            annotation.set_gid(component_id)
            if not host._restoring_component_tree_now:
                result = host.text_render_service.apply(
                    controller,
                    {"usetex": bool(merged.get("usetex", False))},
                )
                if not result.ok:
                    raise ValueError(
                        result.message or "Annotation render validation failed."
                    )
            host._prepare_created_component(controller, transaction)
            host.component_registry.request_update(
                axes,
                UpdateImpact.REDRAW,
            )

        host._finish_created_component(controller)
        if request.announce and not host._restoring_component_tree_now:
            status_messages.show_success("Annotation created.")
        return annotation

    def create_in_axes(self, request: InAxesElementCreateRequest) -> Axes:
        host = self._host
        spec = request.spec
        parent_axes = host.current_axes
        parent_id = host.current_axes_component_id
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

        component_id = request.object_id or new_id()
        state = ComponentState(
            id=component_id,
            kind=ComponentKind.IN_AXES,
            role=role,
            parent_id=parent_id,
            order=host._next_child_order(
                parent_id,
                kind=ComponentKind.IN_AXES,
            ),
            selector={"object_id": component_id},
            properties=properties,
            data=data,
        )
        controller = None
        mirrored = None
        with host.component_registry.registration_transaction() as transaction:
            with matplotlib_style_context(host.component_style):
                runtime = host.in_axes_service.create_runtime(
                    parent_axes,
                    tuple(properties["bounds"]),
                    zorder=float(properties["zorder"]),
                )
            transaction.on_rollback(
                lambda target=runtime: host.in_axes_service.destroy_runtime(target)
            )
            controller = controller_type(state, target=runtime)
            initial = controller.apply_state(controller.state)
            if not initial.ok:
                raise ValueError(initial.message)
            if isinstance(controller, ZoomInAxesController):
                host.in_axes_service.add_zoom_indicator(runtime, properties)
            controller.sync_from_target(strict=True)
            host.component_registry.register(controller, target=runtime)
            host.in_axes_service.register_runtime(component_id, runtime)
            transaction.on_rollback(
                lambda target=component_id: host.in_axes_service.unregister_runtime(target)
            )
            if isinstance(controller, ZoomInAxesController):
                mirrored = host.in_axes_service.refresh_zoom(controller)
            host._prepare_created_component(controller, transaction)

        host._select_created_component(controller)
        if not host._restoring_component_tree_now:
            host.redraw()
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

    def create_field_2d(self, request: Field2DCreateRequest):
        host = self._host
        owner_axes_id = host.current_axes_component_id
        owner_axes = host.current_axes
        if owner_axes_id is None or owner_axes is None:
            raise ValueError(
                f"Select an Axes before creating a {request.display_name}."
            )
        x_ref = (
            ColumnRef.from_dict(request.x_ref)
            if not isinstance(request.x_ref, ColumnRef)
            else request.x_ref
        )
        y_ref = (
            ColumnRef.from_dict(request.y_ref)
            if not isinstance(request.y_ref, ColumnRef)
            else request.y_ref
        )
        z_ref = (
            ColumnRef.from_dict(request.z_ref)
            if not isinstance(request.z_ref, ColumnRef)
            else request.z_ref
        )
        controller_type = {
            ComponentRole.PSEUDOCOLOR: PseudocolorController,
            ComponentRole.HEATMAP: HeatmapController,
            ComponentRole.CONTOUR: ContourController,
        }[request.role]
        component_id = request.object_id or new_id()
        if host._restoring_component_tree_now:
            requested = dict(request.properties or {})
        else:
            requested = default_field_2d_properties(request.role, host.component_style)
            requested.update(request.properties or {})
        controller = None
        runtime = None
        grid = None
        with host.component_registry.registration_transaction() as transaction:
            transaction.watch_existing(owner_axes_id)
            with matplotlib_style_context(host.component_style):
                grid = host.field_2d_service.resolve_grid(
                    x_ref, y_ref, z_ref, request.role
                )
                runtime = host.field_2d_service.create_runtime(
                    owner_axes,
                    request.role,
                    grid,
                    requested,
                    style=host.component_style,
                    gid=component_id,
                )
            transaction.on_rollback(
                lambda target=runtime: host.field_2d_service.destroy_runtime(target)
            )
            state = ComponentState(
                id=component_id,
                kind=ComponentKind.FIELD_2D,
                role=request.role,
                parent_id=owner_axes_id,
                order=host._claim_color_order(request.color_order),
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
                raise ValueError(
                    applied.message or f"Could not initialize {request.display_name}."
                )
            controller.sync_from_target(strict=True)
            host.component_registry.register(controller, target=runtime)
            runtime.set_gid(component_id)
            host.component_registry.request_update(
                owner_axes,
                UpdateImpact.AUTOSCALE,
            )
            host._prepare_created_component(controller, transaction)
            host.component_registry.request_update(host.fig, UpdateImpact.REDRAW)
            if host.fig.canvas is not None:
                host.fig.canvas.draw()

        host._finish_created_component(controller)
        if request.announce and not host._restoring_component_tree_now:
            if grid is not None and grid.skipped_xy_count:
                status_messages.show_warning(
                    f"{request.display_name} created; skipped "
                    f"{grid.skipped_xy_count} row(s) with missing or "
                    "non-finite X or Y coordinates."
                )
            elif runtime is not None and runtime.empty:
                status_messages.show_warning(
                    f"{request.display_name} created with no drawable data yet."
                )
            else:
                status_messages.show_success(f"{request.display_name} created.")
        return runtime

    def create_colorbar(self, request: ColorbarCreateRequest):
        host = self._host
        owner_axes_id = host.current_axes_component_id
        owner_axes = host.current_axes
        if owner_axes_id is None or owner_axes is None:
            raise ValueError("Select an Axes before creating a Colorbar.")
        if request.source_component_id not in host.component_registry:
            raise ValueError("The selected Colorbar source is unavailable.")
        host.colorbar_service.validate_source(
            owner_axes_id,
            request.source_component_id,
        )
        component_id = request.object_id or new_id()
        requested = dict(request.properties or {})
        controller = None
        runtime = None
        with host.component_registry.registration_transaction() as transaction:
            with matplotlib_style_context(host.component_style):
                runtime, normalized = host.colorbar_service.create_runtime(
                    owner_axes_id,
                    request.source_component_id,
                    requested,
                    component_id=component_id,
                )
            transaction.on_rollback(
                lambda target=runtime: host.colorbar_service.destroy_runtime(target)
            )
            transaction.on_rollback(
                lambda component_id=component_id: (
                    host.axes_geometry_service.restore_colorbar_follower(
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
                    host._next_child_order(owner_axes_id)
                    if request.component_order is None
                    else int(request.component_order)
                ),
                selector={"object_id": component_id},
                properties=normalized,
                data={"source_component_id": str(request.source_component_id)},
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
            host.component_registry.register(controller, target=runtime)
            host._prepare_created_component(controller, transaction)
            host.component_registry.request_update(host.fig, UpdateImpact.REDRAW)
            if host.fig.canvas is not None:
                host.fig.canvas.draw()

        host._finish_created_component(controller)
        if request.announce and not host._restoring_component_tree_now:
            status_messages.show_success("Colorbar created.")
        return runtime

    def create_secondary_axis(self, request: SecondaryAxisElementRequest):
        host = self._host
        spec = request.spec
        if not isinstance(spec, SecondaryAxisCreateSpec):
            raise TypeError("add_secondary_axis requires SecondaryAxisCreateSpec.")
        owner_axes_id = str(request.axes_id or host.current_axes_component_id or "")
        owner_axes = host.component_registry.resolve_target(owner_axes_id)
        if not isinstance(owner_axes, Axes):
            raise ValueError("Select an Axes before creating a Secondary Axis.")
        component_id = request.object_id or new_id()
        controller = None
        runtime = None
        with host.component_registry.registration_transaction() as transaction:
            with matplotlib_style_context(host.component_style):
                runtime, normalized = host.secondary_axis_service.create_runtime(
                    owner_axes_id,
                    spec,
                    allow_invalid_domain=request.allow_invalid_domain,
                )
            transaction.on_rollback(
                lambda target=runtime: host.secondary_axis_service.destroy_runtime(target)
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
                    host._next_child_order(owner_axes_id)
                    if request.component_order is None
                    else int(request.component_order)
                ),
                selector={"object_id": component_id},
                properties=normalized,
                data={},
            )
            controller = SecondaryAxisController(state, target=runtime)
            controller.sync_from_target(strict=True)
            host.component_registry.register(controller, target=runtime)
            host._prepare_created_component(controller, transaction)
            host.component_registry.request_update(owner_axes, UpdateImpact.REDRAW)
            if host.fig.canvas is not None:
                host.fig.canvas.draw()

        host._finish_created_component(controller)
        if request.announce and not host._restoring_component_tree_now:
            status_messages.show_success("Secondary Axis created.")
        return runtime

    def create_reference_marks(self, request: ReferenceMarksCreateRequest):
        host = self._host
        owner_axes_id = host.current_axes_component_id
        owner_axes = host.current_axes
        if owner_axes_id is None or owner_axes is None:
            raise ValueError(
                "Select an Axes before creating Reflection Positions."
            )
        component_id = request.object_id or new_id()
        controller = None
        runtime = None
        with host.component_registry.registration_transaction() as transaction:
            (
                runtime,
                normalized_positions,
                normalized_ref,
                normalized,
                normalized_placement,
            ) = (
                host.reference_marks_service.create_runtime(
                    owner_axes_id,
                    request.positions,
                    request.properties,
                    request.position_ref,
                    request.placement,
                )
            )
            transaction.on_rollback(
                lambda target=runtime: (
                    host.reference_marks_service.destroy_runtime(target)
                )
            )
            state = ComponentState(
                id=component_id,
                kind=ComponentKind.REFERENCE_MARKS,
                role=ComponentRole.REFLECTION_POSITIONS,
                parent_id=owner_axes_id,
                order=(
                    host._next_child_order(owner_axes_id)
                    if request.component_order is None
                    else int(request.component_order)
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
            controller.bind_table(host.repository, host.project_id)
            initialized = controller.apply_state(controller.state)
            if not initialized.ok:
                raise ValueError(
                    initialized.message
                    or "Could not initialize Reflection Positions."
                )
            controller.sync_from_target(strict=True)
            host.component_registry.register(controller, target=runtime)
            runtime.set_gid(component_id)
            host._prepare_created_component(controller, transaction)
            host.component_registry.request_update(
                owner_axes,
                UpdateImpact.REDRAW,
            )
            if host.fig.canvas is not None:
                host.fig.canvas.draw()

        host._finish_created_component(controller)
        if request.announce and not host._restoring_component_tree_now:
            status_messages.show_success("Reflection Positions created.")
        return runtime

    def create_reference_guide(self, request: ReferenceGuideCreateRequest):
        host = self._host
        role = request.role
        owner_axes_id = host.current_axes_component_id
        owner_axes = host.current_axes
        if owner_axes_id is None or owner_axes is None:
            raise ValueError("Select an Axes before creating a Reference Guide.")
        style_defaults = host.component_creation_defaults().reference_marks
        if role is ComponentRole.REFERENCE_LINE:
            controller_type = ReferenceLineController
            create_runtime = host.reference_guide_service.create_line_runtime
            label = "Reference Line"
            requested = {
                "color": style_defaults.color,
                "linewidth": style_defaults.linewidth,
            }
        elif role is ComponentRole.REFERENCE_BAND:
            controller_type = ReferenceBandController
            create_runtime = host.reference_guide_service.create_band_runtime
            label = "Reference Band"
            requested = {
                "facecolor": style_defaults.color,
                "edgecolor": style_defaults.color,
                "linewidth": style_defaults.linewidth,
            }
        else:
            raise ValueError("Unsupported Reference Guide role.")
        requested.update(request.properties or {})

        component_id = request.object_id or new_id()
        controller = None
        runtime = None
        with host.component_registry.registration_transaction() as transaction:
            runtime, normalized = create_runtime(owner_axes_id, requested)
            transaction.on_rollback(
                lambda target=runtime: (
                    host.reference_guide_service.destroy_runtime(target)
                )
            )
            state = ComponentState(
                id=component_id,
                kind=ComponentKind.REFERENCE_GUIDE,
                role=role,
                parent_id=owner_axes_id,
                order=(
                    host._next_child_order(owner_axes_id)
                    if request.component_order is None
                    else int(request.component_order)
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
            host.component_registry.register(controller, target=runtime)
            runtime.set_gid(component_id)
            host._prepare_created_component(controller, transaction)
            host.reference_guide_service.verify_render(controller)
            host.component_registry.request_update(
                owner_axes,
                UpdateImpact.REDRAW,
            )

        host._finish_created_component(controller)
        if request.announce and not host._restoring_component_tree_now:
            status_messages.show_success(f"{label} created.")
        return runtime

    def handle_mpl_button_press(self, event) -> None:
        host = self._host
        if host._disposed or host._restoring_component_tree_now:
            return
        if getattr(event, "button", None) != 3:
            return
        toolbar_mode = str(getattr(host.navigation_toolbar, "mode", "")).strip()
        if toolbar_mode != "":
            return
        target_axes = getattr(event, "inaxes", None)
        if target_axes is None:
            return
        axes_id = None
        for controller in host.component_registry.query(kind=ComponentKind.AXES):
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

        menu = QMenu(host)
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
            annotation_artist = host.add_annotation_from_input(
                properties,
                axes_id=axes_id,
            )
            new_component_id = getattr(annotation_artist, "get_gid", lambda: None)()
            if new_component_id:
                host.select_component(new_component_id)
                host._focus_annotation_editor(new_component_id)
        except Exception as exc:
            status_messages.show_error(str(exc))
