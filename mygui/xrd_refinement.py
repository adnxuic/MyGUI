"""Application-level FullProf PRF import orchestration.

The service coordinates existing Table, Axes-layout, component, legend, and
history boundaries.  It does not own a second state store and does not persist
the source PRF path or parser objects.
"""

from __future__ import annotations

from dataclasses import dataclass
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
    normalize_reference_positions,
)
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
class XrdRefinementImportRequest:
    """Controller-free, non-persisted request for one validated PRF result."""

    result: FullProfPrfResult
    legend: XrdRefinementLegendSelection = XrdRefinementLegendSelection()

    def __post_init__(self) -> None:
        if not isinstance(self.result, FullProfPrfResult):
            raise TypeError("XRD refinement import requires a parsed PRF result.")
        if not isinstance(self.legend, XrdRefinementLegendSelection):
            raise TypeError("XRD refinement import requires typed legend selections.")


@dataclass(frozen=True, slots=True)
class XrdTableImportPlan:
    """Complete sheets and stable references planned before publication."""

    profile_sheet: SheetDocument
    reflection_sheet: SheetDocument
    two_theta_ref: ColumnRef
    yobs_ref: ColumnRef
    ycal_ref: ColumnRef
    residual_ref: ColumnRef

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
    residual_axes_id: str
    observed_id: str
    calculated_id: str
    reflection_positions_id: str
    residual_id: str


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
    return XrdTableImportPlan(
        profile_sheet=profile_sheet,
        reflection_sheet=reflection_sheet,
        two_theta_ref=refs["2Theta"],
        yobs_ref=refs["Yobs"],
        ycal_ref=refs["Ycal"],
        residual_ref=refs["Residual"],
    )


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

    def _resolve_new_axes(
        self,
        before_layout_ids: set[str],
    ) -> tuple[str, str, str]:
        after = {str(item["id"]) for item in self.canvas.axes_layout_service.layout_definitions()}
        added = after - before_layout_ids
        if len(added) != 1:
            raise RuntimeError("XRD workflow could not identify its new Axes layout.")
        layout_id = added.pop()
        by_semantic = {}
        for controller in self.canvas.axes_layout_service.axes_for_layout(layout_id):
            subplot = controller.state.data["subplot"]
            key = (
                int(subplot["row"]),
                int(subplot["column"]),
                str(subplot["layer"]),
            )
            by_semantic[key] = controller.component_id
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

    def _create_figure(
        self,
        layout_spec: AxesLayoutSpec,
        request: XrdRefinementImportRequest,
        plan: XrdTableImportPlan,
    ) -> XrdRefinementImportOutcome:
        canvas = self.canvas
        before_layout_ids = {
            str(item["id"]) for item in canvas.axes_layout_service.layout_definitions()
        }
        before_component = canvas.current_component_id
        before_axes = canvas.current_axes_component_id
        before_ledger = canvas.color_consumption_ledger.history_snapshot()
        defaults = canvas.component_creation_defaults()
        preprocess = DataPreprocessSpec()
        reflection_positions = normalize_reference_positions(
            [item.position for item in request.result.reflections]
        )

        try:
            with canvas.component_registry.registration_transaction():
                canvas.create_axes_layout(layout_spec)
                layout_id, main_id, residual_id = self._resolve_new_axes(before_layout_ids)

                canvas.update_current_axes(main_id)
                observed = canvas.add_scatters(
                    plan.two_theta_ref,
                    (plan.yobs_ref,),
                    size=defaults.scatter.size,
                    marker=defaults.scatter.marker,
                    preprocess=preprocess,
                    color_selection=canvas.creation_color_cycle().peek(),
                    record_recent=False,
                )
                calculated = canvas.add_plots(
                    plan.two_theta_ref,
                    (plan.ycal_ref,),
                    style="-",
                    size=defaults.line.markersize,
                    linewidth=defaults.line.linewidth,
                    preprocess=preprocess,
                    color_selection=canvas.creation_color_cycle().peek(),
                    record_recent=False,
                )
                reflection_id = new_id()
                canvas.add_reference_marks(
                    reflection_positions,
                    {
                        "label": (
                            "Reflection positions" if request.legend.reflection_positions else ""
                        ),
                        "color": defaults.reference_marks.color,
                        "linewidth": defaults.reference_marks.linewidth,
                    },
                    object_id=reflection_id,
                    announce=False,
                )

                canvas.update_current_axes(residual_id)
                residual = canvas.add_plots(
                    plan.two_theta_ref,
                    (plan.residual_ref,),
                    style="-",
                    size=defaults.line.markersize,
                    linewidth=defaults.line.linewidth,
                    preprocess=preprocess,
                    color_selection=canvas.creation_color_cycle().peek(),
                    record_recent=False,
                )

                label_result = canvas.component_registry.apply_transaction(
                    (
                        ComponentMutation(
                            observed.component_ids[0],
                            properties={"label": "Observed" if request.legend.observed else ""},
                        ),
                        ComponentMutation(
                            calculated.component_ids[0],
                            properties={
                                "label": ("Calculated" if request.legend.calculated else "")
                            },
                        ),
                        ComponentMutation(
                            residual.component_ids[0],
                            properties={"label": "Residual" if request.legend.residual else ""},
                        ),
                    )
                )
                self._require_change(label_result, "Could not configure XRD labels.")
                self._set_axes_labels(main_id, residual_id)
                self._configure_legends(
                    main_id,
                    residual_id,
                    request.legend,
                )
                canvas.validate_component_snapshot()

            return XrdRefinementImportOutcome(
                table=plan,
                layout_id=layout_id,
                main_axes_id=main_id,
                residual_axes_id=residual_id,
                observed_id=observed.component_ids[0],
                calculated_id=calculated.component_ids[0],
                reflection_positions_id=reflection_id,
                residual_id=residual.component_ids[0],
            )
        except Exception:
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
            raise

    def execute(
        self,
        layout_spec: AxesLayoutSpec,
        request: XrdRefinementImportRequest,
    ) -> XrdRefinementImportOutcome:
        """Run the validated Table command followed by one Figure intent."""

        if not isinstance(layout_spec, AxesLayoutSpec):
            raise TypeError("XRD refinement import requires an AxesLayoutSpec.")
        if not isinstance(request, XrdRefinementImportRequest):
            raise TypeError("XRD refinement import requires a typed request.")
        cells = {(cell.row, cell.column, cell.right_y is not None) for cell in layout_spec.cells}
        if (
            layout_spec.nrows != 2
            or layout_spec.ncols != 1
            or tuple(layout_spec.height_ratios or ()) != (3.0, 1.0)
            or layout_spec.share_x is not ShareMode.ALL
            or layout_spec.share_y is not ShareMode.NONE
            or not layout_spec.outer_x_labels
            or cells != {(0, 0, False), (1, 0, False)}
        ):
            raise ValueError("XRD refinement import requires Main Plot + Residual.")

        plan = plan_xrd_table_import(
            self.repository,
            self.project_id,
            request.result,
        )
        self.import_table(plan)
        try:
            return self.canvas.figure_history.perform(
                FIGURE_COMMAND_TEXT,
                lambda: self._create_figure(layout_spec, request, plan),
                scan_all=True,
            )
        except Exception as exc:
            raise XrdPlotCreationError(f"Data imported, plot creation failed: {exc}") from exc


__all__ = [
    "FIGURE_COMMAND_TEXT",
    "TABLE_COMMAND_TEXT",
    "XrdPlotCreationError",
    "XrdRefinementImportOutcome",
    "XrdRefinementImportRequest",
    "XrdRefinementImportService",
    "XrdRefinementLegendSelection",
    "XrdTableImportPlan",
    "plan_xrd_table_import",
]
