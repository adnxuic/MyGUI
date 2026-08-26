"""Application-level FullProf PRF import orchestration.

The service coordinates existing Table, Axes-layout, component, legend, and
history boundaries.  It does not own a second state store and does not persist
the source PRF path or parser objects.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any

from mygui.database import (
    ColumnRef,
    ColumnType,
    DataPreprocessSpec,
    SheetDocument,
    TableChangeSet,
    TableMutationCommand,
    TableRepository,
)
from mygui.database.table_document import DEFAULT_ROWS, new_id
from mygui.figuremodify.axes_layout import AxesLayoutSpec, ShareMode
from mygui.figuremodify.components import (
    ComponentKind,
    ComponentMutation,
    ComponentRole,
)
from mygui.figuremodify.style_base.color_models import ColorSelection
from mygui.fullprof_prf import FullProfPrfResult


TABLE_COMMAND_TEXT = "Import XRD Refinement Data"
FIGURE_COMMAND_TEXT = "Create XRD Refinement Plot"


@dataclass(frozen=True, slots=True)
class XrdRefinementLegendSelection:
    """Legend membership requested independently for each target Axes."""

    observed: bool = True
    calculated: bool = True
    reflection_positions: bool = False
    residual: bool = False

    def __post_init__(self) -> None:
        for name in (
            "observed",
            "calculated",
            "reflection_positions",
            "residual",
        ):
            if type(getattr(self, name)) is not bool:
                raise TypeError(f"Legend selection {name} must be Boolean.")


@dataclass(frozen=True, slots=True)
class XrdScatterAppearance:
    """Observed scatter style chosen before XRD figure publication."""

    color: str = "#D62728"
    edgecolor: str = "#D62728"
    marker: str = "o"
    size: float = 1.0
    linewidth: float = 1.0


@dataclass(frozen=True, slots=True)
class XrdPlotAppearance:
    """Calculated or residual plot style chosen before publication."""

    color: str
    linewidth: float
    linestyle: str = "-"


@dataclass(frozen=True, slots=True)
class XrdReflectionAppearance:
    """Reflection Positions style chosen before XRD figure publication."""

    label: str = ""
    baseline: float = 0.0375
    height: float = 0.025
    color: str | None = None
    linewidth: float | None = None


@dataclass(frozen=True, slots=True)
class XrdAppearanceConfig:
    """Non-persisted four-component appearance for one XRD import."""

    observed: XrdScatterAppearance = XrdScatterAppearance()
    calculated: XrdPlotAppearance = XrdPlotAppearance("#000000", 0.5)
    residual: XrdPlotAppearance = XrdPlotAppearance("#0000FF", 0.2)
    reflection: XrdReflectionAppearance = XrdReflectionAppearance()


@dataclass(frozen=True, slots=True)
class XrdRefinementImportRequest:
    """Controller-free, non-persisted request for one validated PRF result."""

    result: FullProfPrfResult
    legend: XrdRefinementLegendSelection = XrdRefinementLegendSelection()
    appearance: XrdAppearanceConfig = XrdAppearanceConfig()
    draw_single_residual: bool = True

    def __post_init__(self) -> None:
        if not isinstance(self.result, FullProfPrfResult):
            raise TypeError("XRD refinement import requires a parsed PRF result.")
        if not isinstance(self.legend, XrdRefinementLegendSelection):
            raise TypeError("XRD refinement import requires typed legend selections.")
        if not isinstance(self.appearance, XrdAppearanceConfig):
            raise TypeError("XRD refinement import requires typed appearance config.")
        if type(self.draw_single_residual) is not bool:
            raise TypeError("draw_single_residual must be Boolean.")


@dataclass(frozen=True, slots=True)
class XrdTableImportPlan:
    """Complete sheets and stable references planned before publication."""

    profile_sheet: SheetDocument
    reflection_sheet: SheetDocument
    two_theta_ref: ColumnRef
    yobs_ref: ColumnRef
    ycal_ref: ColumnRef
    residual_ref: ColumnRef
    prf_difference_ref: ColumnRef
    reflection_position_ref: ColumnRef

    @property
    def sheet_ids(self) -> tuple[str, str]:
        return self.profile_sheet.id, self.reflection_sheet.id

    @property
    def refs(self) -> frozenset[ColumnRef]:
        return frozenset(
            ColumnRef(self.two_theta_ref.project_id, sheet.id, column.id)
            for sheet in (self.profile_sheet, self.reflection_sheet)
            for column in sheet.columns
        )


@dataclass(frozen=True, slots=True)
class XrdRefinementImportOutcome:
    """Stable IDs produced by a successful Table and Figure workflow."""

    table: XrdTableImportPlan
    layout_id: str
    main_axes_id: str
    residual_axes_id: str | None
    observed_id: str
    calculated_id: str
    reflection_positions_id: str
    residual_id: str | None
    chi2_text_id: str | None = None


class XrdPlotCreationError(RuntimeError):
    """Report the intentional partial-success boundary after Table import."""

    data_imported = True


def _number_sheet(
    name: str,
    columns: tuple[tuple[str, tuple[float | int, ...]], ...],
) -> SheetDocument:
    row_count = max(DEFAULT_ROWS, *(len(values) for _name, values in columns))
    sheet = SheetDocument(id=new_id(), name=name, row_count=row_count)
    for column_name, values in columns:
        sheet.add_column(column_name, ColumnType.NUMBER, values=values)
    return sheet


def plan_xrd_table_import(
    repository: TableRepository,
    project_id: str,
    result: FullProfPrfResult,
) -> XrdTableImportPlan:
    """Build both complete sheets and stable refs without publishing them."""

    if not isinstance(repository, TableRepository):
        raise TypeError("XRD Table import requires the shared TableRepository.")
    if not isinstance(result, FullProfPrfResult):
        raise TypeError("XRD Table import requires a parsed PRF result.")
    project = repository.project(str(project_id))
    profile_name = project.unique_sheet_name(f"{result.source_name} Profile")
    used = {sheet.name.casefold() for sheet in project.sheets.values()}
    used.add(profile_name.casefold())
    reflection_base = f"{result.source_name} Reflections"
    reflection_name = reflection_base
    suffix = 2
    while reflection_name.casefold() in used:
        reflection_name = f"{reflection_base} {suffix}"
        suffix += 1

    profile = result.profile
    profile_sheet = _number_sheet(
        profile_name,
        (
            ("2Theta", profile.two_theta),
            ("Yobs", profile.yobs),
            ("Ycal", profile.ycal),
            ("Yobs-Ycal (PRF)", profile.prf_difference),
            ("Residual", profile.residual),
            ("Backg", profile.background),
        ),
    )
    reflections = result.reflections
    reflection_sheet = _number_sheet(
        reflection_name,
        (
            ("2Theta", tuple(item.position for item in reflections)),
            ("h", tuple(item.h for item in reflections)),
            ("k", tuple(item.k for item in reflections)),
            ("l", tuple(item.l for item in reflections)),
        ),
    )
    refs = {
        column.name: ColumnRef(project.id, profile_sheet.id, column.id)
        for column in profile_sheet.columns
    }
    reflection_refs = {
        column.name: ColumnRef(project.id, reflection_sheet.id, column.id)
        for column in reflection_sheet.columns
    }
    return XrdTableImportPlan(
        profile_sheet=profile_sheet,
        reflection_sheet=reflection_sheet,
        two_theta_ref=refs["2Theta"],
        yobs_ref=refs["Yobs"],
        ycal_ref=refs["Ycal"],
        residual_ref=refs["Residual"],
        prf_difference_ref=refs["Yobs-Ycal (PRF)"],
        reflection_position_ref=reflection_refs["2Theta"],
    )


def classify_xrd_layout(spec: AxesLayoutSpec) -> str:
    """Return 'single' or 'main_residual' for a strictly accepted XRD layout."""

    cells = {(cell.row, cell.column, cell.right_y is not None) for cell in spec.cells}
    if (
        spec.nrows == 1
        and spec.ncols == 1
        and spec.share_x is ShareMode.NONE
        and spec.share_y is ShareMode.NONE
        and cells == {(0, 0, False)}
    ):
        return "single"
    if (
        spec.nrows == 2
        and spec.ncols == 1
        and tuple(spec.height_ratios or ()) == (3.0, 1.0)
        and spec.share_x is ShareMode.ALL
        and spec.share_y is ShareMode.NONE
        and spec.outer_x_labels
        and cells == {(0, 0, False), (1, 0, False)}
    ):
        return "main_residual"
    raise ValueError(
        "XRD refinement import requires a single 1×1 Axes or Main Plot + Residual."
    )


def validate_prf_residual_display_gap(result: FullProfPrfResult) -> None:
    """Reject Single residual overlay when PRF difference overlaps main data."""

    profile = result.profile
    lower = [float(value) for value in profile.prf_difference if math.isfinite(value)]
    upper = [
        float(value)
        for value in (*profile.yobs, *profile.ycal)
        if math.isfinite(value)
    ]
    if not lower or not upper:
        raise ValueError(
            "The FullProf difference does not leave a display gap below the "
            "observed and calculated intensities. Turn off Draw residual or "
            "use Main Plot + Residual."
        )
    if max(lower) >= min(upper):
        raise ValueError(
            "The FullProf difference does not leave a display gap below the "
            "observed and calculated intensities. Turn off Draw residual or "
            "use Main Plot + Residual."
        )


def format_chi2_text(chi2: float | None) -> str:
    """Return the Chi² annotation, using an em dash when the value is missing."""

    if chi2 is None or not math.isfinite(float(chi2)):
        return "χ²: —"
    return f"χ²: {float(chi2):g}"


class XrdRefinementImportService:
    """Coordinate validated PRF data into existing Table/Figure state paths."""

    def __init__(self, *, canvas, table_view: object | None = None) -> None:
        self.canvas = canvas
        self.repository = canvas.repository
        self.project_id = str(canvas.project_id)
        self.table_view = table_view

    def _sync_table_view(self) -> None:
        if self.table_view is None:
            return
        sync = getattr(self.table_view, "sync_project_sheets", None)
        if not callable(sync):
            raise RuntimeError("Table workspace cannot synchronize imported sheets.")
        sync(self.project_id)

    def import_table(self, plan: XrdTableImportPlan) -> None:
        """Publish both planned sheets as one atomic Table command."""

        if not isinstance(plan, XrdTableImportPlan):
            raise TypeError("XRD Table import requires a typed import plan.")
        project = self.repository.project(self.project_id)
        imported = (plan.profile_sheet, plan.reflection_sheet)
        failures: list[BaseException] = []

        def redo() -> bool:
            try:
                for sheet in imported:
                    project.add_sheet(sheet=sheet)
                self._sync_table_view()
            except BaseException as exc:
                failures.append(exc)
                return False
            return True

        def undo() -> None:
            for sheet in imported:
                project.sheets.pop(sheet.id, None)
            self._sync_table_view()

        changes = TableChangeSet(
            self.project_id,
            set(plan.refs),
            metadata_changed=True,
            structure_changed=True,
            reason="xrd-refinement-import",
        )
        command = TableMutationCommand(
            TABLE_COMMAND_TEXT,
            self.repository,
            self.project_id,
            redo,
            undo,
            changes,
            rollback_on_error=True,
        )
        if not self.repository.push(self.project_id, command):
            cause = failures[-1] if failures else None
            error = RuntimeError("XRD refinement Table import was rejected.")
            if cause is None:
                raise error
            raise error from cause

    @staticmethod
    def _require_change(result: Any, fallback: str) -> None:
        if bool(getattr(result, "ok", False)):
            return
        raise ValueError(str(getattr(result, "message", "")) or fallback)

    def _layout_axes_by_semantic(self, layout_id: str) -> dict[tuple[int, int, str], str]:
        by_semantic = {}
        for controller in self.canvas.axes_layout_service.axes_for_layout(layout_id):
            subplot = controller.state.data["subplot"]
            key = (
                int(subplot["row"]),
                int(subplot["column"]),
                str(subplot["layer"]),
            )
            by_semantic[key] = controller.component_id
        return by_semantic

    def _resolve_added_layout(self, before_layout_ids: set[str]) -> str:
        after = {
            str(item["id"])
            for item in self.canvas.axes_layout_service.layout_definitions()
        }
        added = after - before_layout_ids
        if len(added) != 1:
            raise RuntimeError("XRD workflow could not identify its new Axes layout.")
        return added.pop()

    def _resolve_new_axes(
        self,
        before_layout_ids: set[str],
    ) -> tuple[str, str, str]:
        layout_id = self._resolve_added_layout(before_layout_ids)
        by_semantic = self._layout_axes_by_semantic(layout_id)
        try:
            main_id = by_semantic[(0, 0, "primary")]
            residual_id = by_semantic[(1, 0, "primary")]
        except KeyError as exc:
            raise RuntimeError(
                "Main + Residual layout did not publish the required semantic Axes."
            ) from exc
        if set(by_semantic) != {(0, 0, "primary"), (1, 0, "primary")}:
            raise RuntimeError("Main + Residual layout published unexpected Axes.")
        return layout_id, main_id, residual_id

    def _resolve_single_axes(
        self,
        before_layout_ids: set[str],
    ) -> tuple[str, str]:
        layout_id = self._resolve_added_layout(before_layout_ids)
        by_semantic = self._layout_axes_by_semantic(layout_id)
        try:
            axes_id = by_semantic[(0, 0, "primary")]
        except KeyError as exc:
            raise RuntimeError(
                "Single Axes layout did not publish the required semantic Axes."
            ) from exc
        if set(by_semantic) != {(0, 0, "primary")}:
            raise RuntimeError("Single Axes layout published unexpected Axes.")
        return layout_id, axes_id

    def _set_axes_labels(self, main_id: str, residual_id: str) -> None:
        patches = (
            (
                self.canvas.axes_commands.semantic(
                    main_id,
                    kind=ComponentKind.TEXT,
                    role=ComponentRole.Y_LABEL,
                ),
                {"text": "Intensity (a.u.)"},
            ),
            (
                self.canvas.axes_commands.semantic(
                    residual_id,
                    kind=ComponentKind.TEXT,
                    role=ComponentRole.X_LABEL,
                ),
                {"text": "2θ (°)"},
            ),
            (
                self.canvas.axes_commands.semantic(
                    residual_id,
                    kind=ComponentKind.TEXT,
                    role=ComponentRole.Y_LABEL,
                ),
                {"text": "Residual"},
            ),
        )
        self._require_change(
            self.canvas.text_render_service.apply_many(patches),
            "Could not configure XRD Axes labels.",
        )

    def _configure_legends(
        self,
        main_id: str,
        residual_id: str,
        selection: XrdRefinementLegendSelection,
    ) -> None:
        for axes_id, visible in (
            (
                main_id,
                selection.observed or selection.calculated or selection.reflection_positions,
            ),
            (residual_id, selection.residual),
        ):
            legend = self.canvas.axes_commands.semantic(
                axes_id,
                kind=ComponentKind.LEGEND,
                role=ComponentRole.LEGEND,
                recursive=False,
            )
            self._require_change(
                self.canvas.axes_commands.apply_legend_properties(
                    legend,
                    {"visible": bool(visible)},
                ),
                "Could not configure the XRD legend.",
            )

    def _configure_single_legend(
        self,
        axes_id: str,
        selection: XrdRefinementLegendSelection,
        *,
        draw_residual: bool,
    ) -> None:
        visible = (
            selection.observed
            or selection.calculated
            or selection.reflection_positions
            or (draw_residual and selection.residual)
        )
        legend = self.canvas.axes_commands.semantic(
            axes_id,
            kind=ComponentKind.LEGEND,
            role=ComponentRole.LEGEND,
            recursive=False,
        )
        self._require_change(
            self.canvas.axes_commands.apply_legend_properties(
                legend,
                {"visible": bool(visible)},
            ),
            "Could not configure the XRD legend.",
        )

    def _set_single_axes_labels(self, axes_id: str) -> None:
        patches = (
            (
                self.canvas.axes_commands.semantic(
                    axes_id,
                    kind=ComponentKind.TEXT,
                    role=ComponentRole.X_LABEL,
                ),
                {"text": "2θ (°)"},
            ),
            (
                self.canvas.axes_commands.semantic(
                    axes_id,
                    kind=ComponentKind.TEXT,
                    role=ComponentRole.Y_LABEL,
                ),
                {"text": "Intensity (a.u.)"},
            ),
        )
        self._require_change(
            self.canvas.text_render_service.apply_many(patches),
            "Could not configure XRD Axes labels.",
        )

    def _reflection_style(self, request: XrdRefinementImportRequest) -> tuple[str, str, float]:
        defaults = self.canvas.component_creation_defaults()
        reflection_style = request.appearance.reflection
        reflection_label = reflection_style.label
        if request.legend.reflection_positions:
            reflection_label = reflection_label or "Reflection positions"
        else:
            reflection_label = ""
        reflection_color = reflection_style.color or defaults.reference_marks.color
        reflection_width = (
            defaults.reference_marks.linewidth
            if reflection_style.linewidth is None
            else reflection_style.linewidth
        )
        return reflection_label, reflection_color, reflection_width

    def _observed_style_mutation(self, component_id: str, request: XrdRefinementImportRequest):
        observed_style = request.appearance.observed
        return ComponentMutation(
            component_id,
            properties={
                "label": "Observed" if request.legend.observed else "",
                "color": observed_style.color,
                "edgecolor": observed_style.edgecolor,
                "size": observed_style.size,
                "linewidth": observed_style.linewidth,
                "marker": {
                    "kind": "symbol",
                    "value": observed_style.marker,
                },
                "linestyle": {"kind": "preset", "value": "None"},
            },
        )

    def _plot_style_mutation(
        self,
        component_id: str,
        style,
        *,
        label: str,
    ):
        return ComponentMutation(
            component_id,
            properties={
                "label": label,
                "color": style.color,
                "linewidth": style.linewidth,
                "linestyle": {
                    "kind": "preset",
                    "value": style.linestyle,
                },
                "marker": {"kind": "symbol", "value": "None"},
                "drawstyle": "default",
                "gapcolor": None,
            },
        )

    def _add_chi2_text(self, axes_id: str, result: FullProfPrfResult) -> str:
        canvas = self.canvas
        canvas.update_current_axes(axes_id)
        defaults = canvas.component_creation_defaults().text
        text_id = new_id()
        canvas.add_text(
            0.04,
            0.96,
            format_chi2_text(result.metadata.chi2),
            defaults.fontfamily,
            defaults.fontsize,
            object_id=text_id,
        )
        self._require_change(
            canvas.component_registry.apply_transaction(
                (
                    ComponentMutation(
                        text_id,
                        properties={
                            "coordinate_system": "axes",
                            "position": (0.04, 0.96),
                            "horizontalalignment": "left",
                            "verticalalignment": "top",
                            "color": "#000000",
                        },
                    ),
                )
            ),
            "Could not configure the XRD χ² text.",
        )
        return text_id

    def _create_observed_calculated(
        self,
        axes_id: str,
        plan: XrdTableImportPlan,
        request: XrdRefinementImportRequest,
    ):
        canvas = self.canvas
        defaults = canvas.component_creation_defaults()
        preprocess = DataPreprocessSpec()
        observed_style = request.appearance.observed
        calculated_style = request.appearance.calculated
        canvas.update_current_axes(axes_id)
        observed = canvas.add_scatters(
            plan.two_theta_ref,
            (plan.yobs_ref,),
            size=observed_style.size,
            marker=observed_style.marker,
            linewidth=observed_style.linewidth,
            preprocess=preprocess,
            color_selection=ColorSelection(observed_style.color),
            record_recent=False,
        )
        calculated = canvas.add_plots(
            plan.two_theta_ref,
            (plan.ycal_ref,),
            style=calculated_style.linestyle,
            size=defaults.line.markersize,
            linewidth=calculated_style.linewidth,
            preprocess=preprocess,
            color_selection=ColorSelection(calculated_style.color),
            record_recent=False,
        )
        return observed, calculated

    def _add_residual_plot(
        self,
        axes_id: str,
        two_theta_ref: ColumnRef,
        y_ref: ColumnRef,
        request: XrdRefinementImportRequest,
    ):
        canvas = self.canvas
        defaults = canvas.component_creation_defaults()
        residual_style = request.appearance.residual
        canvas.update_current_axes(axes_id)
        return canvas.add_plots(
            two_theta_ref,
            (y_ref,),
            style=residual_style.linestyle,
            size=defaults.line.markersize,
            linewidth=residual_style.linewidth,
            preprocess=DataPreprocessSpec(),
            color_selection=ColorSelection(residual_style.color),
            record_recent=False,
        )

    def _add_reflection_positions(
        self,
        axes_id: str,
        request: XrdRefinementImportRequest,
        plan: XrdTableImportPlan,
        *,
        placement: dict[str, Any],
        baseline: float,
        height: float,
    ) -> str:
        canvas = self.canvas
        canvas.update_current_axes(axes_id)
        reflection_label, reflection_color, reflection_width = self._reflection_style(
            request
        )
        reflection_id = new_id()
        canvas.add_reference_marks(
            [],
            {
                "label": reflection_label,
                "baseline": baseline,
                "height": height,
                "color": reflection_color,
                "linewidth": reflection_width,
            },
            object_id=reflection_id,
            announce=False,
            position_ref=plan.reflection_position_ref.to_dict(),
            placement=placement,
        )
        return reflection_id

    def _rollback_figure(
        self,
        *,
        before_ledger,
        before_axes,
        before_component,
    ) -> None:
        canvas = self.canvas
        canvas.color_consumption_ledger.restore_history_snapshot(before_ledger)
        canvas.message_presenter.discard_pending()
        try:
            canvas.axes_layout_service.restore_persisted_geometry()
            canvas.axes_layout_service.restore_runtime_relationships(refresh=True)
        finally:
            canvas.current_axes_component_id = (
                before_axes
                if before_axes is not None and before_axes in canvas.component_registry
                else None
            )
            if before_component is not None and before_component in canvas.component_registry:
                canvas.select_component(before_component)
            elif canvas.root_component_id in canvas.component_registry:
                canvas.select_component(canvas.root_component_id)

    def _create_main_residual_figure(
        self,
        layout_spec: AxesLayoutSpec,
        request: XrdRefinementImportRequest,
        plan: XrdTableImportPlan,
        before_layout_ids: set[str],
        appearance=None,
    ) -> XrdRefinementImportOutcome:
        canvas = self.canvas
        observed, calculated = None, None
        canvas.create_axes_layout(layout_spec, appearance=appearance)
        layout_id, main_id, residual_axes_id = self._resolve_new_axes(before_layout_ids)
        observed, calculated = self._create_observed_calculated(
            main_id, plan, request
        )
        reflection_id = self._add_reflection_positions(
            main_id,
            request,
            plan,
            placement={"kind": "fixed"},
            baseline=request.appearance.reflection.baseline,
            height=request.appearance.reflection.height,
        )
        residual = self._add_residual_plot(
            residual_axes_id,
            plan.two_theta_ref,
            plan.residual_ref,
            request,
        )
        style_result = canvas.component_registry.apply_transaction(
            (
                ComponentMutation(
                    main_id,
                    properties={
                        "y_lower_reserve": 0.1,
                        "xmargin": 0.0,
                        "autoscalex_on": True,
                    },
                ),
                ComponentMutation(
                    residual_axes_id,
                    properties={
                        "xmargin": 0.0,
                        "autoscalex_on": True,
                    },
                ),
                self._observed_style_mutation(observed.component_ids[0], request),
                self._plot_style_mutation(
                    calculated.component_ids[0],
                    request.appearance.calculated,
                    label="Calculated" if request.legend.calculated else "",
                ),
                self._plot_style_mutation(
                    residual.component_ids[0],
                    request.appearance.residual,
                    label="Residual" if request.legend.residual else "",
                ),
            )
        )
        self._require_change(style_result, "Could not configure XRD styles.")
        self._set_axes_labels(main_id, residual_axes_id)
        self._configure_legends(main_id, residual_axes_id, request.legend)
        canvas.select_component(main_id)
        canvas.validate_component_snapshot()
        return XrdRefinementImportOutcome(
            table=plan,
            layout_id=layout_id,
            main_axes_id=main_id,
            residual_axes_id=residual_axes_id,
            observed_id=observed.component_ids[0],
            calculated_id=calculated.component_ids[0],
            reflection_positions_id=reflection_id,
            residual_id=residual.component_ids[0],
            chi2_text_id=None,
        )

    def _create_single_figure(
        self,
        layout_spec: AxesLayoutSpec,
        request: XrdRefinementImportRequest,
        plan: XrdTableImportPlan,
        before_layout_ids: set[str],
        appearance=None,
    ) -> XrdRefinementImportOutcome:
        canvas = self.canvas
        draw_residual = bool(request.draw_single_residual)
        if draw_residual:
            validate_prf_residual_display_gap(request.result)
        canvas.create_axes_layout(layout_spec, appearance=appearance)
        layout_id, axes_id = self._resolve_single_axes(before_layout_ids)
        observed, calculated = self._create_observed_calculated(
            axes_id, plan, request
        )
        residual = None
        if draw_residual:
            residual = self._add_residual_plot(
                axes_id,
                plan.two_theta_ref,
                plan.prf_difference_ref,
                request,
            )
        mutations = [
            ComponentMutation(
                axes_id,
                properties={
                    "y_lower_reserve": 0.0 if draw_residual else 0.1,
                    "xmargin": 0.0,
                    "autoscalex_on": True,
                },
            ),
            self._observed_style_mutation(observed.component_ids[0], request),
            self._plot_style_mutation(
                calculated.component_ids[0],
                request.appearance.calculated,
                label="Calculated" if request.legend.calculated else "",
            ),
        ]
        if residual is not None:
            mutations.append(
                self._plot_style_mutation(
                    residual.component_ids[0],
                    request.appearance.residual,
                    label="Residual" if request.legend.residual else "",
                )
            )
        style_result = canvas.component_registry.apply_transaction(tuple(mutations))
        self._require_change(style_result, "Could not configure XRD styles.")
        if draw_residual:
            placement = {
                "kind": "between_table_ranges",
                "lower_ref": plan.prf_difference_ref.to_dict(),
                "upper_refs": [
                    plan.yobs_ref.to_dict(),
                    plan.ycal_ref.to_dict(),
                ],
            }
            baseline = request.appearance.reflection.baseline
        else:
            placement = {"kind": "fixed"}
            baseline = request.appearance.reflection.baseline
        reflection_id = self._add_reflection_positions(
            axes_id,
            request,
            plan,
            placement=placement,
            baseline=baseline,
            height=request.appearance.reflection.height,
        )
        chi2_text_id = self._add_chi2_text(axes_id, request.result)
        self._set_single_axes_labels(axes_id)
        self._configure_single_legend(
            axes_id,
            request.legend,
            draw_residual=draw_residual,
        )
        canvas.select_component(axes_id)
        canvas.validate_component_snapshot()
        return XrdRefinementImportOutcome(
            table=plan,
            layout_id=layout_id,
            main_axes_id=axes_id,
            residual_axes_id=None,
            observed_id=observed.component_ids[0],
            calculated_id=calculated.component_ids[0],
            reflection_positions_id=reflection_id,
            residual_id=None if residual is None else residual.component_ids[0],
            chi2_text_id=chi2_text_id,
        )

    def _create_figure(
        self,
        layout_spec: AxesLayoutSpec,
        request: XrdRefinementImportRequest,
        plan: XrdTableImportPlan,
        *,
        appearance=None,
    ) -> XrdRefinementImportOutcome:
        canvas = self.canvas
        before_layout_ids = {
            str(item["id"]) for item in canvas.axes_layout_service.layout_definitions()
        }
        before_component = canvas.current_component_id
        before_axes = canvas.current_axes_component_id
        before_ledger = canvas.color_consumption_ledger.history_snapshot()
        kind = classify_xrd_layout(layout_spec)
        try:
            with canvas.component_registry.registration_transaction():
                if kind == "single":
                    return self._create_single_figure(
                        layout_spec,
                        request,
                        plan,
                        before_layout_ids,
                        appearance,
                    )
                return self._create_main_residual_figure(
                    layout_spec,
                    request,
                    plan,
                    before_layout_ids,
                    appearance,
                )
        except Exception:
            self._rollback_figure(
                before_ledger=before_ledger,
                before_axes=before_axes,
                before_component=before_component,
            )
            raise

    def execute(
        self,
        layout_spec: AxesLayoutSpec,
        request: XrdRefinementImportRequest,
        *,
        appearance=None,
    ) -> XrdRefinementImportOutcome:
        """Run the validated Table command followed by one Figure intent."""

        if not isinstance(layout_spec, AxesLayoutSpec):
            raise TypeError("XRD refinement import requires an AxesLayoutSpec.")
        if not isinstance(request, XrdRefinementImportRequest):
            raise TypeError("XRD refinement import requires a typed request.")
        kind = classify_xrd_layout(layout_spec)
        if kind == "single" and request.draw_single_residual:
            validate_prf_residual_display_gap(request.result)

        plan = plan_xrd_table_import(
            self.repository,
            self.project_id,
            request.result,
        )
        self.import_table(plan)
        try:
            return self.canvas.figure_history.perform(
                FIGURE_COMMAND_TEXT,
                lambda: self._create_figure(
                    layout_spec, request, plan, appearance=appearance
                ),
                scan_all=True,
            )
        except Exception as exc:
            raise XrdPlotCreationError(f"Data imported, plot creation failed: {exc}") from exc


__all__ = [
    "FIGURE_COMMAND_TEXT",
    "TABLE_COMMAND_TEXT",
    "XrdAppearanceConfig",
    "XrdPlotAppearance",
    "XrdPlotCreationError",
    "XrdReflectionAppearance",
    "XrdRefinementImportOutcome",
    "XrdRefinementImportRequest",
    "XrdRefinementImportService",
    "XrdRefinementLegendSelection",
    "XrdScatterAppearance",
    "XrdTableImportPlan",
    "classify_xrd_layout",
    "format_chi2_text",
    "plan_xrd_table_import",
    "validate_prf_residual_display_gap",
]
