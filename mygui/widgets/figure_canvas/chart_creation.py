"""Chart-batch creation records and staging without Canvas-owned state."""

from __future__ import annotations

from collections.abc import Callable
from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Protocol

from mygui import status_messages
from mygui.database import (
    ColumnRef,
    ColumnType,
    DataPreprocessSpec,
    FitInputRangeSpec,
    resolve_preprocessed_pair,
    select_fit_input_pair,
)
from mygui.database.interpolate_func import interpolate_curve
from mygui.database.safe_expression import (
    GENERATED_FIT_EXPRESSION_LIMITS,
    evaluate_curve_expression,
)
from mygui.database.table_document import new_id
from mygui.figuremodify.component_services import resolve_errorbar_data
from mygui.figuremodify.components import (
    ComponentRole,
    DataPlotController,
    ErrorBarData,
    ErrorBarController,
    FitCurveController,
    FitEngine,
    FunctionCurveController,
    InterpolationController,
    LineController,
    ScatterController,
)
from mygui.figuremodify.matplotlib_adapter import matplotlib_style_context
from mygui.figuremodify.style_base.color_models import (
    ColorSelection,
    normalize_color,
)
from mygui.figuremodify.style_base.creation_preferences import (
    ResolvedErrorBarAppearance,
)
from mygui.widgets.figure_canvas.creation_requests import (
    CurveCreateRequest,
    ErrorBarCreateRequest,
    FitCurveCreateRequest,
    InterpolationBatchCreateRequest,
    InterpolationCreateRequest,
    LineCreateRequest,
    PlotBatchCreateRequest,
    PlotCreateRequest,
    ScatterBatchCreateRequest,
    ScatterCreateRequest,
)

import numpy as np


@dataclass(frozen=True, slots=True)
class ChartBatchCreationResult:
    """Transient result returned after one atomic chart creation batch."""

    component_ids: tuple[str, ...]
    artists: tuple[Any, ...]
    colors: tuple[str, ...]
    excluded_counts: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class PreparedChartSeries:
    x_ref: ColumnRef
    y_ref: ColumnRef
    x: Any
    y: Any
    label: str
    color: str
    excluded_count: int


@dataclass(frozen=True, slots=True)
class PreparedErrorBarSeries:
    """Already-resolved Error Bar data plus specs for one creation."""

    x_ref: ColumnRef
    y_ref: ColumnRef
    x: Any
    y: Any
    xerr: Any
    yerr: Any
    label: str
    xerr_spec: dict[str, Any]
    yerr_spec: dict[str, Any]
    preprocess: DataPreprocessSpec
    excluded_count: int


class ChartCreationHost(Protocol):
    """Canvas surface used by the stager; the host remains state authority."""

    project_id: str
    repository: Any
    current_axes_component_id: str | None
    current_axes: Any
    current_axes_controller: Any
    component_registry: Any
    axes_commands: Any
    chart_data_service: Any
    color_consumption_ledger: Any
    color_library: Any
    component_style: str

    def _remove_created_artist(self, artist: Any) -> None:
        ...

    def _claim_color_order(self, preferred: int | None = None) -> int:
        ...

    def _register_chart_controller(
        self,
        controller_type: Any,
        component_id: str,
        role: ComponentRole,
        artist: Any,
        order: int,
        properties: dict[str, Any],
        data: dict[str, Any],
    ) -> Any:
        ...

    def _prepare_created_component(self, controller: Any, transaction: Any) -> None:
        ...

    def _select_created_component(self, controller: Any) -> None:
        ...

    def redraw(self) -> None:
        ...


class ChartCreationStager:
    """Stage and commit chart batches through the Canvas host Protocol."""

    def __init__(self, host: ChartCreationHost) -> None:
        self._host = host

    def stage_errorbar(
        self,
        transaction,
        series: PreparedErrorBarSeries,
        *,
        appearance: ResolvedErrorBarAppearance,
        object_id: str | None = None,
        color_order: int | None = None,
    ):
        """Create one Error Bar runtime and register its Controller."""

        from mygui.figuremodify.component_services import (
            ErrorBarRuntime,
            create_errorbar_container,
            errorbar_properties_from_appearance,
        )

        host = self._host
        object_id = object_id or new_id()
        properties = errorbar_properties_from_appearance(
            appearance,
            label=series.label,
        )
        drawable = ErrorBarData(
            series.x,
            series.y,
            series.xerr,
            series.yerr,
        )
        axes = host.current_axes
        if axes is None:
            raise ValueError("Select an axes before adding a chart.")
        with matplotlib_style_context(host.component_style):
            container = create_errorbar_container(axes, drawable, properties)
        runtime = ErrorBarRuntime(
            axes,
            container,
            data=drawable,
            properties=properties,
        )
        transaction.on_rollback(
            lambda target=runtime: host.errorbar_service.destroy_runtime(target)
        )
        component_order = host._claim_color_order(color_order)
        controller = host._register_chart_controller(
            ErrorBarController,
            object_id,
            ComponentRole.ERROR_BAR,
            runtime,
            component_order,
            properties,
            {
                "x_ref": series.x_ref.to_dict(),
                "y_ref": series.y_ref.to_dict(),
                "xerr": deepcopy(series.xerr_spec),
                "yerr": deepcopy(series.yerr_spec),
                "preprocess": series.preprocess.to_dict(),
            },
        )
        host._prepare_created_component(controller, transaction)
        return runtime, controller

    def normalize_batch_refs(
        self,
        x_ref: ColumnRef,
        y_refs,
    ) -> tuple[ColumnRef, tuple[ColumnRef, ...]]:
        host = self._host
        if not isinstance(x_ref, ColumnRef):
            raise ValueError("Please select X Data.")
        normalized_y = tuple(y_refs)
        if not normalized_y:
            raise ValueError("Please select at least one Y Data column.")
        if any(not isinstance(ref, ColumnRef) for ref in normalized_y):
            raise ValueError("Every Y Data selection must be a column reference.")
        if len(set(normalized_y)) != len(normalized_y):
            raise ValueError("Duplicate Y Data selections are not allowed.")
        if x_ref.project_id != host.project_id:
            raise ValueError("X Data must belong to the current project.")
        if not host.repository.has_ref(x_ref):
            raise ValueError("X Data column was removed.")
        x_column = host.repository.sheet(
            x_ref.project_id, x_ref.sheet_id
        ).column(x_ref.column_id)
        if x_column.type not in {ColumnType.NUMBER, ColumnType.DATETIME}:
            raise ValueError("X Data must be numeric or date/time.")
        for index, ref in enumerate(normalized_y, start=1):
            if ref.project_id != host.project_id:
                raise ValueError(
                    f"Y Data selection {index} must belong to the current project."
                )
            if not host.repository.has_ref(ref):
                raise ValueError(f"Y Data selection {index} was removed.")
            column = host.repository.sheet(
                ref.project_id, ref.sheet_id
            ).column(ref.column_id)
            if column.type is not ColumnType.NUMBER:
                raise ValueError(
                    f"Y Data selection {index} must be numeric."
                )
        return x_ref, normalized_y

    def batch_series_labels(
        self,
        y_refs: tuple[ColumnRef, ...],
    ) -> tuple[str, ...]:
        repository = self._host.repository
        names = tuple(
            str(
                repository.sheet(ref.project_id, ref.sheet_id)
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
        for ref, name in zip(y_refs, names, strict=True):
            if counts[name.casefold()] == 1:
                labels.append(name)
                continue
            sheet = repository.sheet(ref.project_id, ref.sheet_id)
            labels.append(f"{sheet.name}/{name}")
        return tuple(labels)

    def batch_color_plan(
        self,
        selection: ColorSelection,
        count: int,
    ) -> tuple[
        tuple[str, ...],
        dict[str, Any] | None,
        bool,
        tuple[tuple[dict[str, Any] | None, dict[str, Any]], ...],
    ]:
        host = self._host
        if not isinstance(selection, ColorSelection):
            raise TypeError("Batch chart color must be a ColorSelection.")
        if selection.palette is None:
            return (
                tuple(selection.color for _index in range(count)),
                None,
                False,
                (),
            )
        axes_id = host.current_axes_component_id
        if axes_id is None:
            raise ValueError("Select an axes before adding charts.")
        cycle = host.axes_commands.cycle_state(axes_id)
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

    def prepare_data_batch(
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
        host = self._host
        x_ref, normalized_y = self.normalize_batch_refs(x_ref, y_refs)
        spec = DataPreprocessSpec.from_dict(preprocess)
        labels = self.batch_series_labels(normalized_y)
        resolved = []
        for y_ref, label in zip(normalized_y, labels, strict=True):
            try:
                pair = resolve_preprocessed_pair(
                    host.repository,
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
            colors, final_cycle, commit_cycle, transitions = self.batch_color_plan(
                color_selection,
                len(resolved),
            )
        else:
            if not isinstance(color_selection, ColorSelection):
                raise TypeError("Batch chart color must be a ColorSelection.")
            colors = tuple(color_selection.color for _item in resolved)
            final_cycle = None
            commit_cycle = False
            transitions = ()
        prepared = tuple(
            PreparedChartSeries(
                x_ref=x_ref,
                y_ref=y_ref,
                x=pair.x,
                y=pair.y,
                label=label,
                color=color,
                excluded_count=pair.excluded_count,
            )
            for (y_ref, label, pair), color in zip(resolved, colors, strict=True)
        )
        return prepared, final_cycle, commit_cycle, transitions

    def stage_plot(
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
        host = self._host
        object_id = object_id or new_id()
        plot_kwargs = {
            "linestyle": style,
            "markersize": size,
            "color": series.color,
            "label": series.label,
        }
        if linewidth is not None:
            plot_kwargs["linewidth"] = float(linewidth)
        if marker is not None:
            plot_kwargs["marker"] = marker
        if markeredgewidth is not None:
            plot_kwargs["markeredgewidth"] = float(markeredgewidth)
        with matplotlib_style_context(host.component_style):
            (line,) = host.current_axes.plot(series.x, series.y, **plot_kwargs)
        transaction.on_rollback(
            lambda line=line: host._remove_created_artist(line)
        )
        component_order = host._claim_color_order(color_order)
        controller = host._register_chart_controller(
            DataPlotController,
            object_id,
            ComponentRole.DATA_PLOT,
            line,
            component_order,
            host._line_sync_properties(
                line, color=series.color, label=series.label
            ),
            {
                "x_ref": series.x_ref.to_dict(),
                "y_ref": series.y_ref.to_dict(),
                "preprocess": preprocess.to_dict(),
            },
        )
        host._prepare_created_component(controller, transaction)
        return line, controller

    def stage_scatter(
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
        host = self._host
        object_id = object_id or new_id()
        scatter_kwargs = {
            "s": size,
            "c": series.color,
            "marker": marker,
            "label": series.label,
        }
        if linewidth is not None:
            scatter_kwargs["linewidths"] = float(linewidth)
            scatter_kwargs["edgecolors"] = series.color
        with matplotlib_style_context(host.component_style):
            scatter = host.current_axes.scatter(
                series.x,
                series.y,
                **scatter_kwargs,
            )
        transaction.on_rollback(
            lambda scatter=scatter: host._remove_created_artist(scatter)
        )
        component_order = host._claim_color_order(color_order)
        properties = {
            "color": series.color,
            "edgecolor": series.color,
            "size": float(size),
            "marker": marker,
            "label": series.label,
        }
        if linewidth is not None:
            properties["linewidth"] = float(linewidth)
        if color_mapping is not None:
            properties["color_mapping"] = deepcopy(color_mapping)
        if size_mapping is not None:
            properties["size_mapping"] = deepcopy(size_mapping)
        controller = host._register_chart_controller(
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
            change = host.chart_data_service.configure_scatter_mapping(
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
        host._prepare_created_component(controller, transaction)
        return scatter, controller

    def stage_interpolation(
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
        host = self._host
        object_id = object_id or new_id()
        plot_kwargs = {
            "color": series.color,
            "label": series.label,
        }
        if linestyle is not None:
            plot_kwargs["linestyle"] = linestyle
        if linewidth is not None:
            plot_kwargs["linewidth"] = float(linewidth)
        if marker is not None:
            plot_kwargs["marker"] = marker
        if markersize is not None:
            plot_kwargs["markersize"] = float(markersize)
        if markeredgewidth is not None:
            plot_kwargs["markeredgewidth"] = float(markeredgewidth)
        with matplotlib_style_context(host.component_style):
            (line,) = host.current_axes.plot(
                series.x,
                series.y,
                **plot_kwargs,
            )
        transaction.on_rollback(
            lambda line=line: host._remove_created_artist(line)
        )
        component_order = host._claim_color_order(color_order)
        controller = host._register_chart_controller(
            InterpolationController,
            object_id,
            ComponentRole.INTERPOLATION,
            line,
            component_order,
            host._line_sync_properties(
                line, color=series.color, label=series.label
            ),
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
        host._prepare_created_component(controller, transaction)
        return line, controller

    def commit_chart_batch(
        self,
        prepared: tuple[PreparedChartSeries, ...],
        stage: Callable[..., Any],
        *,
        final_cycle: dict[str, Any] | None,
        commit_cycle: bool,
        color_transitions: tuple[tuple[dict[str, Any] | None, dict[str, Any]], ...],
        record_recent: bool = True,
    ) -> ChartBatchCreationResult:
        host = self._host
        axes_id = host.current_axes_component_id
        axes_controller = host.current_axes_controller
        if axes_id is None or axes_controller is None or host.current_axes is None:
            raise ValueError("Select an axes before adding charts.")
        artists = []
        controllers = []
        with host.component_registry.registration_transaction() as transaction:
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
        if color_transitions:
            for controller, (before, after) in zip(
                controllers,
                color_transitions,
                strict=True,
            ):
                host.color_consumption_ledger.record(
                    axes_id,
                    controller.component_id,
                    before,
                    after,
                )
        host._select_created_component(controllers[-1])
        host.redraw()
        colors = tuple(series.color for series in prepared)
        if record_recent:
            host.color_library.record_recent_many(colors)
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

    def publish_single(
        self,
        stage: Callable,
        *,
        commit_selection: ColorSelection | None,
        preview_cycle,
        resolved_color: str | None,
        record_recent: bool = True,
    ):
        """Register one chart, then commit palette and select it."""

        host = self._host
        axes_id = host.current_axes_component_id
        if axes_id is None:
            raise ValueError("Select an axes before adding a chart.")
        with host.component_registry.registration_transaction() as transaction:
            transaction.watch_existing(axes_id)
            artist, controller = stage(transaction)
            color_transition = host._commit_single_creation_color(
                transaction,
                commit_selection,
                preview_cycle,
            )
        host._finish_created_component(controller)
        if color_transition is not None:
            host.color_consumption_ledger.record(
                axes_id,
                controller.component_id,
                *color_transition,
            )
            if record_recent and resolved_color is not None:
                host.color_library.record_recent(resolved_color)
        return artist, controller

    def line_plot_plan(
        self,
        *,
        label: str,
        color=None,
        color_selection: ColorSelection | None = None,
        preview_cycle=None,
        linestyle=None,
        linewidth=None,
        marker=None,
        markersize=None,
        markeredgewidth=None,
    ):
        host = self._host
        if host._restoring_component_tree_now:
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
            return (
                kwargs,
                str(kwargs.get("color", "#000000")),
                color_selection,
                preview_cycle,
            )
        resolved = host._resolve_line_creation(
            settings=host._read_component_defaults(),
            color=color,
            color_selection=color_selection,
            linestyle=linestyle,
            linewidth=linewidth,
            marker=marker,
            markersize=markersize,
            markeredgewidth=markeredgewidth,
        )
        commit_selection, cycle = host._commit_resolved_line_color(
            resolved, color_selection, preview_cycle
        )
        return resolved.plot_kwargs(label=label), resolved.color, commit_selection, cycle

    def create_plot(self, request: PlotCreateRequest):
        host = self._host
        preprocess = DataPreprocessSpec.from_dict(request.preprocess)
        pair = resolve_preprocessed_pair(
            host.repository,
            request.x_ref,
            request.y_ref,
            preprocess,
            preserve_gaps=True,
        )
        preview_cycle = request.preview_cycle
        if host._restoring_component_tree_now:
            resolved_color = normalize_color(request.color)
            resolved_style = request.style
            resolved_size = request.size
            resolved_lw = request.linewidth
            resolved_marker = request.marker
            resolved_mew = request.markeredgewidth
            commit_selection = request.color_selection
        else:
            resolved = host._resolve_line_creation(
                settings=host._read_component_defaults(),
                color=request.color,
                color_selection=request.color_selection,
                linestyle=request.style,
                linewidth=request.linewidth,
                marker=request.marker,
                markersize=request.size,
                markeredgewidth=request.markeredgewidth,
            )
            resolved_color = resolved.color
            resolved_style = resolved.linestyle
            resolved_size = resolved.markersize
            resolved_lw = resolved.linewidth
            resolved_marker = resolved.marker
            resolved_mew = resolved.markeredgewidth
            commit_selection, preview_cycle = host._commit_resolved_line_color(
                resolved, request.color_selection, preview_cycle
            )
        series = PreparedChartSeries(
            x_ref=request.x_ref,
            y_ref=request.y_ref,
            x=pair.x,
            y=pair.y,
            label=str(request.label),
            color=resolved_color,
            excluded_count=pair.excluded_count,
        )
        line, _controller = self.publish_single(
            lambda transaction: self.stage_plot(
                transaction,
                series,
                style=resolved_style,
                size=resolved_size,
                linewidth=resolved_lw,
                preprocess=preprocess,
                object_id=request.object_id,
                color_order=request.color_order,
                marker=resolved_marker,
                markeredgewidth=resolved_mew,
            ),
            commit_selection=commit_selection,
            preview_cycle=preview_cycle,
            resolved_color=resolved_color,
        )
        return line

    def create_plots(self, request: PlotBatchCreateRequest) -> ChartBatchCreationResult:
        host = self._host
        spec = DataPreprocessSpec.from_dict(request.preprocess)
        line_style, line_width, line_marker, line_size, line_mew = (
            host._shared_line_fields(
                linestyle=request.style,
                linewidth=request.linewidth,
                marker=request.marker,
                markersize=request.size,
                markeredgewidth=request.markeredgewidth,
            )
        )
        prepared, final_cycle, commit_cycle, transitions = self.prepare_data_batch(
            request.x_ref,
            request.y_refs,
            spec,
            request.color_selection,
            preserve_gaps=True,
        )
        return self.commit_chart_batch(
            prepared,
            lambda transaction, series: self.stage_plot(
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
            record_recent=request.record_recent,
        )

    def create_scatter(self, request: ScatterCreateRequest):
        host = self._host
        preprocess = DataPreprocessSpec.from_dict(request.preprocess)
        pair = resolve_preprocessed_pair(
            host.repository,
            request.x_ref,
            request.y_ref,
            preprocess,
            preserve_gaps=False,
        )
        mapping_enabled = False
        if isinstance(request.color_mapping, dict):
            mapping_enabled = bool(request.color_mapping.get("enabled"))
        preview_cycle = request.preview_cycle
        if host._restoring_component_tree_now:
            resolved_color = normalize_color(request.color)
            resolved_marker = request.marker
            resolved_size = request.size
            resolved_lw = request.linewidth
            commit_selection = None if mapping_enabled else request.color_selection
        else:
            resolved = host._resolve_scatter_creation(
                settings=host._read_component_defaults(),
                color=request.color,
                color_selection=None if mapping_enabled else request.color_selection,
                marker=request.marker,
                size=request.size,
                linewidth=request.linewidth,
            )
            resolved_color = resolved.color
            resolved_marker = resolved.marker
            resolved_size = resolved.size
            resolved_lw = resolved.linewidth
            if mapping_enabled:
                commit_selection = None
            else:
                commit_selection, preview_cycle = host._commit_resolved_line_color(
                    resolved, request.color_selection, preview_cycle
                )
        series = PreparedChartSeries(
            x_ref=request.x_ref,
            y_ref=request.y_ref,
            x=pair.x,
            y=pair.y,
            label=str(request.label),
            color=resolved_color,
            excluded_count=pair.excluded_count,
        )
        scatter, _controller = self.publish_single(
            lambda transaction: self.stage_scatter(
                transaction,
                series,
                size=resolved_size,
                marker=resolved_marker,
                preprocess=preprocess,
                color_ref=request.color_ref,
                size_ref=request.size_ref,
                color_mapping=request.color_mapping,
                size_mapping=request.size_mapping,
                object_id=request.object_id,
                color_order=request.color_order,
                linewidth=resolved_lw,
            ),
            commit_selection=commit_selection,
            preview_cycle=preview_cycle,
            resolved_color=resolved_color,
        )
        return scatter

    def create_scatters(
        self,
        request: ScatterBatchCreateRequest,
    ) -> ChartBatchCreationResult:
        host = self._host
        spec = DataPreprocessSpec.from_dict(request.preprocess)
        color_spec = (
            ScatterController.property_specs()["color_mapping"].normalize(
                request.color_mapping
                if request.color_mapping is not None
                else ScatterController.default_properties()["color_mapping"]
            )
        )
        size_spec = (
            ScatterController.property_specs()["size_mapping"].normalize(
                request.size_mapping
                if request.size_mapping is not None
                else ScatterController.default_properties()["size_mapping"]
            )
        )
        if host._restoring_component_tree_now:
            resolved_marker = request.marker
            resolved_size = request.size
            resolved_lw = request.linewidth
        else:
            resolved = host._resolve_scatter_creation(
                settings=host._read_component_defaults(),
                color=request.color_selection.color,
                color_selection=request.color_selection,
                marker=request.marker,
                size=request.size,
                linewidth=request.linewidth,
            )
            resolved_marker = resolved.marker
            resolved_size = resolved.size
            resolved_lw = resolved.linewidth
        prepared, final_cycle, commit_cycle, transitions = self.prepare_data_batch(
            request.x_ref,
            request.y_refs,
            spec,
            request.color_selection,
            preserve_gaps=False,
            consume_palette=not color_spec["enabled"],
        )
        return self.commit_chart_batch(
            prepared,
            lambda transaction, series: self.stage_scatter(
                transaction,
                series,
                size=resolved_size,
                marker=resolved_marker,
                preprocess=spec,
                color_ref=request.color_ref,
                size_ref=request.size_ref,
                color_mapping=color_spec,
                size_mapping=size_spec,
                linewidth=resolved_lw,
            ),
            final_cycle=final_cycle,
            commit_cycle=commit_cycle,
            color_transitions=transitions,
            record_recent=request.record_recent,
        )

    def create_curve(self, request: CurveCreateRequest):
        host = self._host
        object_id = request.object_id or new_id()
        x = np.linspace(request.x_start, request.x_stop, 1000)
        y = evaluate_curve_expression(request.func_text, x)
        plot_kwargs, resolved_color, commit_selection, preview_cycle = (
            self.line_plot_plan(
                label=request.label,
                color=request.color,
                color_selection=request.color_selection,
                preview_cycle=request.preview_cycle,
                linestyle=request.style,
                linewidth=request.linewidth,
                marker=request.marker,
                markersize=request.markersize,
                markeredgewidth=request.markeredgewidth,
            )
        )

        def stage(transaction):
            with matplotlib_style_context(host.component_style):
                (line,) = host.current_axes.plot(x, y, **plot_kwargs)
            transaction.on_rollback(
                lambda: host._remove_created_artist(line)
            )
            component_order = host._claim_color_order(request.color_order)
            controller = host._register_chart_controller(
                FunctionCurveController,
                object_id,
                ComponentRole.FUNCTION_CURVE,
                line,
                component_order,
                host._line_sync_properties(
                    line, color=resolved_color, label=request.label
                ),
                {
                    "expression": request.func_text,
                    "x_start": float(request.x_start),
                    "x_stop": float(request.x_stop),
                },
            )
            host._prepare_created_component(controller, transaction)
            return line, controller

        line, _controller = self.publish_single(
            stage,
            commit_selection=commit_selection,
            preview_cycle=preview_cycle,
            resolved_color=resolved_color,
        )
        return line

    def create_line(self, request: LineCreateRequest):
        host = self._host
        color = normalize_color(request.color)
        object_id = request.object_id or new_id()
        axes_id = host.current_axes_component_id
        if axes_id is None:
            raise ValueError("Select an axes before adding a chart.")
        with host.component_registry.registration_transaction() as transaction:
            with matplotlib_style_context(host.component_style):
                (line,) = host.current_axes.plot(
                    np.asarray(request.x),
                    np.asarray(request.y),
                    linestyle=request.style,
                    color=color,
                    label=request.label,
                )
            transaction.on_rollback(lambda: host._remove_created_artist(line))
            component_order = host._claim_color_order(request.color_order)
            controller = host._register_chart_controller(
                LineController,
                object_id,
                ComponentRole.LINE,
                line,
                component_order,
                {
                    "linestyle": line.get_linestyle(),
                    "color": color,
                    "label": request.label,
                },
                {
                    "x": np.asarray(request.x).tolist(),
                    "y": np.asarray(request.y).tolist(),
                },
            )
            host._prepare_created_component(controller, transaction)
        host._finish_created_component(controller)
        return line

    def create_errorbar(self, request: ErrorBarCreateRequest):
        from mygui.figuremodify.components.property_values import (
            DEFAULT_ERROR_SPEC,
            normalize_error_spec,
        )

        host = self._host
        preprocess_spec = DataPreprocessSpec.from_dict(request.preprocess)
        xerr_spec = normalize_error_spec(
            request.xerr if request.xerr is not None else deepcopy(DEFAULT_ERROR_SPEC)
        )
        yerr_spec = normalize_error_spec(
            request.yerr if request.yerr is not None else deepcopy(DEFAULT_ERROR_SPEC)
        )
        drawable = resolve_errorbar_data(
            host.repository,
            request.x_ref,
            request.y_ref,
            xerr_spec,
            yerr_spec,
            preprocess_spec,
        )
        preview_cycle = request.preview_cycle
        if host._restoring_component_tree_now:
            resolved = ResolvedErrorBarAppearance(
                color=normalize_color(request.color),
                linestyle=(
                    deepcopy(request.linestyle)
                    if request.linestyle is not None
                    else {"kind": "preset", "value": "-"}
                ),
                linewidth=(
                    float(request.linewidth) if request.linewidth is not None else 1.5
                ),
                marker=(
                    deepcopy(request.marker)
                    if request.marker is not None
                    else {"kind": "symbol", "value": "None"}
                ),
                markersize=(
                    float(request.markersize) if request.markersize is not None else 6.0
                ),
                markeredgewidth=(
                    float(request.markeredgewidth)
                    if request.markeredgewidth is not None
                    else 1.0
                ),
                markerfacecoloralt=(
                    str(request.markerfacecoloralt)
                    if request.markerfacecoloralt is not None
                    else "none"
                ),
                fillstyle=(
                    str(request.fillstyle) if request.fillstyle is not None else "full"
                ),
                drawstyle=(
                    str(request.drawstyle) if request.drawstyle is not None else "default"
                ),
                antialiased=(
                    bool(request.antialiased)
                    if request.antialiased is not None
                    else True
                ),
                ecolor=(
                    normalize_color(request.ecolor)
                    if request.ecolor is not None
                    else normalize_color(request.color)
                ),
                elinewidth=(
                    float(request.elinewidth) if request.elinewidth is not None else 1.5
                ),
                capsize=float(request.capsize) if request.capsize is not None else 0.0,
                capthick=(
                    float(request.capthick) if request.capthick is not None else 1.0
                ),
                error_linestyle=(
                    deepcopy(request.error_linestyle)
                    if request.error_linestyle is not None
                    else {"kind": "preset", "value": "-"}
                ),
                error_capstyle=(
                    None if request.error_capstyle is None else str(request.error_capstyle)
                ),
                error_antialiased=(
                    bool(request.error_antialiased)
                    if request.error_antialiased is not None
                    else True
                ),
                errorevery=(
                    deepcopy(request.errorevery)
                    if request.errorevery is not None
                    else {"kind": "all"}
                ),
                lolims=bool(request.lolims) if request.lolims is not None else False,
                uplims=bool(request.uplims) if request.uplims is not None else False,
                xlolims=bool(request.xlolims) if request.xlolims is not None else False,
                xuplims=bool(request.xuplims) if request.xuplims is not None else False,
                barsabove=(
                    bool(request.barsabove) if request.barsabove is not None else False
                ),
                color_selection=(
                    request.color_selection
                    if request.color_selection is not None
                    else ColorSelection(normalize_color(request.color))
                ),
            )
            commit_selection = request.color_selection
        else:
            resolved = host._resolve_errorbar_creation(
                settings=host._read_component_defaults(),
                color=request.color,
                color_selection=request.color_selection,
                linestyle=request.linestyle,
                linewidth=request.linewidth,
                marker=request.marker,
                markersize=request.markersize,
                markeredgewidth=request.markeredgewidth,
                markerfacecoloralt=request.markerfacecoloralt,
                fillstyle=request.fillstyle,
                drawstyle=request.drawstyle,
                antialiased=request.antialiased,
                ecolor=request.ecolor,
                elinewidth=request.elinewidth,
                capsize=request.capsize,
                capthick=request.capthick,
                error_linestyle=request.error_linestyle,
                error_capstyle=request.error_capstyle,
                error_antialiased=request.error_antialiased,
                errorevery=request.errorevery,
                lolims=request.lolims,
                uplims=request.uplims,
                xlolims=request.xlolims,
                xuplims=request.xuplims,
                barsabove=request.barsabove,
            )
            commit_selection, preview_cycle = host._commit_resolved_line_color(
                resolved, request.color_selection, preview_cycle
            )
        series = PreparedErrorBarSeries(
            x_ref=request.x_ref,
            y_ref=request.y_ref,
            x=drawable.x,
            y=drawable.y,
            xerr=drawable.xerr,
            yerr=drawable.yerr,
            label=str(request.label),
            xerr_spec=xerr_spec,
            yerr_spec=yerr_spec,
            preprocess=preprocess_spec,
            excluded_count=0,
        )
        runtime, _controller = self.publish_single(
            lambda transaction: self.stage_errorbar(
                transaction,
                series,
                appearance=resolved,
                object_id=request.object_id,
                color_order=request.color_order,
            ),
            commit_selection=commit_selection,
            preview_cycle=preview_cycle,
            resolved_color=resolved.color,
        )
        return runtime

    def create_fit_curve(self, request: FitCurveCreateRequest):
        host = self._host
        preprocess = DataPreprocessSpec.from_dict(request.preprocess)
        input_range = FitInputRangeSpec.from_dict(request.fit_input_range)
        pair = resolve_preprocessed_pair(
            host.repository,
            request.x_ref,
            request.y_ref,
            preprocess,
            preserve_gaps=False,
        )
        selected = select_fit_input_pair(pair, input_range, require_data=False)
        x, y = selected.x, selected.y
        try:
            engine = FitEngine(request.engine)
        except ValueError as exc:
            raise ValueError(
                f"Unsupported fitting engine: {request.engine}"
            ) from exc
        object_id = request.object_id or new_id()
        x_array = np.asarray(x, dtype=float)
        y_array = np.asarray(y, dtype=float)
        x_start = (
            selected.x_start if request.x_start is None else float(request.x_start)
        )
        x_stop = selected.x_stop if request.x_stop is None else float(request.x_stop)
        expression = request.expression
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
                status_messages.show_error(
                    "Saved fit expression could not be restored; showing source data."
                )
                expression = ""
                line_x = x_array
                line_y = y_array
        plot_kwargs, resolved_color, commit_selection, preview_cycle = (
            self.line_plot_plan(
                label=request.label,
                color=request.color,
                color_selection=request.color_selection,
                preview_cycle=request.preview_cycle,
                linestyle=request.style,
                linewidth=request.linewidth,
                marker=request.marker,
                markersize=request.markersize,
                markeredgewidth=request.markeredgewidth,
            )
        )

        def stage(transaction):
            with matplotlib_style_context(host.component_style):
                (line,) = host.current_axes.plot(
                    line_x,
                    line_y,
                    **plot_kwargs,
                )
            transaction.on_rollback(
                lambda: host._remove_created_artist(line)
            )
            component_order = host._claim_color_order(request.color_order)
            controller = host._register_chart_controller(
                FitCurveController,
                object_id,
                ComponentRole.FIT_CURVE,
                line,
                component_order,
                host._line_sync_properties(
                    line, color=resolved_color, label=request.label
                ),
                {
                    "x_ref": request.x_ref.to_dict(),
                    "y_ref": request.y_ref.to_dict(),
                    "preprocess": preprocess.to_dict(),
                    "engine": engine.value,
                    "fit_type": deepcopy(request.fit_type),
                    "fit_options": deepcopy(request.fit_options),
                    "fit_result": deepcopy(request.fit_result),
                    "expression": expression or "",
                    "x_start": float(x_start),
                    "x_stop": float(x_stop),
                    "fit_input_range": input_range.to_dict(),
                },
            )
            host._prepare_created_component(controller, transaction)
            return line, controller

        line, _controller = self.publish_single(
            stage,
            commit_selection=commit_selection,
            preview_cycle=preview_cycle,
            resolved_color=resolved_color,
        )
        return line

    def create_interpolate_curve(self, request: InterpolationCreateRequest):
        host = self._host
        preprocess = DataPreprocessSpec.from_dict(request.preprocess)
        pair = resolve_preprocessed_pair(
            host.repository,
            request.x_ref,
            request.y_ref,
            preprocess,
            preserve_gaps=False,
        )
        x_values = np.asarray(pair.x)
        y_values = np.asarray(pair.y)
        if request.allow_empty and (x_values.size == 0 or y_values.size == 0):
            x_new = np.asarray([], dtype=float)
            y_new = np.asarray([], dtype=float)
        else:
            try:
                x_new, y_new = interpolate_curve(
                    x_values,
                    y_values,
                    request.method,
                    k=request.k,
                    samples=request.samples,
                    lam=request.lam,
                    lam_auto=request.lam_auto,
                )
            except ValueError as exc:
                if not request.allow_empty:
                    status_messages.show_error(str(exc))
                    return None
                x_new = np.asarray([], dtype=float)
                y_new = np.asarray([], dtype=float)
                status_messages.show_warning(
                    "Interpolation could not be recomputed from the "
                    f"current source data ({exc}); an empty component "
                    "was restored."
                )
        preview_cycle = request.preview_cycle
        if host._restoring_component_tree_now:
            resolved_color = normalize_color(request.color)
            line_style = request.linestyle
            line_width = request.linewidth
            line_marker = request.marker
            line_ms = request.markersize
            line_mew = request.markeredgewidth
            commit_selection = request.color_selection
        else:
            resolved = host._resolve_line_creation(
                settings=host._read_component_defaults(),
                color=request.color,
                color_selection=request.color_selection,
                linestyle=request.linestyle,
                linewidth=request.linewidth,
                marker=request.marker,
                markersize=request.markersize,
                markeredgewidth=request.markeredgewidth,
            )
            resolved_color = resolved.color
            line_style = resolved.linestyle
            line_width = resolved.linewidth
            line_marker = resolved.marker
            line_ms = resolved.markersize
            line_mew = resolved.markeredgewidth
            commit_selection, preview_cycle = host._commit_resolved_line_color(
                resolved, request.color_selection, preview_cycle
            )
        series = PreparedChartSeries(
            x_ref=request.x_ref,
            y_ref=request.y_ref,
            x=x_new,
            y=y_new,
            label=str(request.label),
            color=resolved_color,
            excluded_count=pair.excluded_count,
        )
        line, _controller = self.publish_single(
            lambda transaction: self.stage_interpolation(
                transaction,
                series,
                method=request.method,
                k=request.k,
                samples=request.samples,
                lam=request.lam,
                lam_auto=request.lam_auto,
                preprocess=preprocess,
                object_id=request.object_id,
                color_order=request.color_order,
                linestyle=line_style,
                linewidth=line_width,
                marker=line_marker,
                markersize=line_ms,
                markeredgewidth=line_mew,
            ),
            commit_selection=commit_selection,
            preview_cycle=preview_cycle,
            resolved_color=resolved_color,
        )
        if request.announce and not host._restoring_component_tree_now:
            if x_new.size:
                status_messages.show_success("Interpolation curve created.")
            else:
                status_messages.show_warning(
                    "Interpolation curve has no valid data yet; "
                    "its editor and style were kept."
                )
        return line

    def create_interpolate_curves(
        self,
        request: InterpolationBatchCreateRequest,
    ) -> ChartBatchCreationResult:
        host = self._host
        spec = DataPreprocessSpec.from_dict(request.preprocess)
        line_style, line_width, line_marker, line_ms, line_mew = (
            host._shared_line_fields(
                linestyle=request.linestyle,
                linewidth=request.linewidth,
                marker=request.marker,
                markersize=request.markersize,
                markeredgewidth=request.markeredgewidth,
            )
        )
        sources, final_cycle, commit_cycle, transitions = self.prepare_data_batch(
            request.x_ref,
            request.y_refs,
            spec,
            request.color_selection,
            preserve_gaps=False,
        )
        prepared = []
        for series in sources:
            try:
                x_new, y_new = interpolate_curve(
                    np.asarray(series.x),
                    np.asarray(series.y),
                    request.method,
                    k=request.k,
                    samples=request.samples,
                    lam=request.lam,
                    lam_auto=request.lam_auto,
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
        return self.commit_chart_batch(
            tuple(prepared),
            lambda transaction, series: self.stage_interpolation(
                transaction,
                series,
                method=request.method,
                k=request.k,
                samples=request.samples,
                lam=request.lam,
                lam_auto=request.lam_auto,
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
