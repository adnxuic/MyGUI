"""Chart-batch creation records and staging without Canvas-owned state."""

from __future__ import annotations

from collections.abc import Callable
from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Protocol

from mygui.database import (
    ColumnRef,
    ColumnType,
    DataPreprocessSpec,
    resolve_preprocessed_pair,
)
from mygui.database.table_document import new_id
from mygui.figuremodify.components import (
    ComponentRole,
    DataPlotController,
    InterpolationController,
    ScatterController,
)
from mygui.figuremodify.matplotlib_adapter import matplotlib_style_context
from mygui.figuremodify.style_base.color_models import ColorSelection


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
        for ref, name in zip(y_refs, names):
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
        for y_ref, label in zip(normalized_y, labels):
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
            for (y_ref, label, pair), color in zip(resolved, colors)
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
        for controller, (before, after) in zip(
            controllers,
            color_transitions,
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
