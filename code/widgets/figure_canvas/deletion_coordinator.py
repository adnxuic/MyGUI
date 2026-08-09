"""Coordinate atomic Component deletion across Registry, artists, and Qt UI."""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING

from code.figuremodify.component_services import (
    DeletionOutcome,
    DeletionRequest,
)
from code.figuremodify.components import ComponentKind, DeletionPolicy
from code.figuremodify.components.serialization import normalize_v8_figure
from code.widgets.component_tree.model import ComponentTreeModel
from code.widgets.component_tree.presentation import TreePresentationResolver

if TYPE_CHECKING:
    from .py_figure_canves import PyFigureCanvas


class DeletionCoordinator:
    """Provide the sole Canvas-level production path for physical deletion."""

    def __init__(self, canvas: "PyFigureCanvas") -> None:
        self.canvas = canvas
        self.presentation = TreePresentationResolver(canvas.editor_registry)

    def _fallback_id(self, request: DeletionRequest, removed_ids: set[str]) -> str:
        canvas = self.canvas
        registry = canvas.component_registry
        current_id = canvas.current_component_id
        if current_id is not None and current_id not in removed_ids:
            return current_id

        anchor_id = (
            current_id
            if current_id is not None and current_id in registry
            else request.anchor_id
        )
        if anchor_id is None or anchor_id not in registry:
            anchor_id = request.component_ids[0]
        anchor = registry.get(anchor_id)
        state = anchor.state
        cohort = sorted(
            (
                controller
                for controller in registry.children(state.parent_id)
                if controller.state.kind is state.kind
                and controller.state.role is state.role
                and controller.DELETION_POLICY is DeletionPolicy.REMOVE
            ),
            key=lambda controller: self.presentation.sort_key(controller.state),
        )
        cohort_ids = [controller.component_id for controller in cohort]
        if anchor_id in cohort_ids:
            position = cohort_ids.index(anchor_id)
            for component_id in cohort_ids[position + 1 :]:
                if component_id not in removed_ids:
                    return component_id
            for component_id in reversed(cohort_ids[:position]):
                if component_id not in removed_ids:
                    return component_id

        parent_id = state.parent_id
        visited: set[str] = set()
        while parent_id is not None and parent_id not in visited:
            visited.add(parent_id)
            if parent_id not in removed_ids and parent_id in registry:
                return parent_id
            parent = registry.get(parent_id) if parent_id in registry else None
            parent_id = parent.state.parent_id if parent is not None else None
        return canvas.root_component_id

    def _candidate_axes_map(self) -> dict[object, str]:
        canvas = self.canvas
        registry = canvas.component_registry
        surviving = sorted(
            registry.query(kind=ComponentKind.AXES),
            key=lambda controller: int(controller.state.selector["index"]),
        )
        result = {
            controller.resolve_target(): controller.component_id
            for controller in surviving
        }
        if len(result) != len(surviving):
            raise ValueError("Two surviving Axes resolve to the same artist.")
        if any(axes not in canvas.fig.axes for axes in result):
            raise ValueError("A surviving Axes is detached from its Figure.")
        return result

    def delete(
        self,
        request: DeletionRequest,
        *,
        role_label: str = "component",
        present_success: bool = True,
    ) -> bool:
        """Prepare, verify, commit, and publish one deletion result."""

        canvas = self.canvas
        presenter = canvas.message_presenter
        try:
            prepared = canvas.deletion_service.prepare(request)
            fallback_id = self._fallback_id(
                request,
                set(prepared.plan.removed_ids),
            )
            prepared.set_fallback(fallback_id)
        except Exception as exc:
            presenter.discard_pending()
            return presenter.present(
                DeletionOutcome(False, True, message=str(exc)).as_batch_change()
            )

        previous_component_id = canvas.current_component_id
        previous_axes_id = canvas.current_axes_component_id
        panel = canvas.figure_inspector
        axes_handles = []
        fallback_inspector_existed = bool(
            panel is None or panel.inspector(fallback_id) is not None
        )

        def rollback_ui() -> list[str]:
            errors = []
            for handle in reversed(axes_handles):
                try:
                    panel.restore_axes_inspector(handle)
                except Exception as exc:
                    errors.append(str(exc))
            if (
                panel is not None
                and not fallback_inspector_existed
                and fallback_id in canvas.component_registry
            ):
                try:
                    panel.remove_component_inspector(fallback_id)
                except Exception as exc:
                    errors.append(str(exc))
            if (
                panel is not None
                and previous_component_id is not None
                and previous_component_id in canvas.component_registry
            ):
                try:
                    if not panel.show_component(previous_component_id):
                        raise RuntimeError(
                            "The previous Inspector could not be restored."
                        )
                except Exception as exc:
                    errors.append(str(exc))
            return errors

        try:
            if panel is not None:
                panel.ensure_component(fallback_id)
                if not panel.show_component(fallback_id):
                    raise RuntimeError(
                        f"Fallback Inspector for {fallback_id!r} is unavailable."
                    )
                for component_id in prepared.plan.root_ids:
                    controller = canvas.component_registry.get(component_id)
                    if controller.state.kind is not ComponentKind.AXES:
                        continue
                    handle = panel.take_axes_inspector(component_id)
                    if handle is not None:
                        axes_handles.append(handle)
        except Exception as exc:
            ui_rollback_errors = rollback_ui()
            presenter.discard_pending()
            message = str(exc)
            if ui_rollback_errors:
                message = (
                    f"{message} UI rollback was incomplete: "
                    + "; ".join(ui_rollback_errors)
                ).strip()
            return presenter.present(
                DeletionOutcome(
                    False,
                    not ui_rollback_errors,
                    message=message,
                ).as_batch_change()
            )

        candidate_axes_map: dict[object, str] = {}

        def verify_candidate() -> None:
            nonlocal candidate_axes_map
            canvas.component_registry.validate_tree()
            ComponentTreeModel.validate_registry_projection(
                canvas.component_registry,
                canvas.editor_registry,
            )
            normalize_v8_figure(canvas.component_snapshot())
            candidate_axes_map = self._candidate_axes_map()

        try:
            outcome = prepared.execute(verifier=verify_candidate)
        except Exception as exc:
            outcome = DeletionOutcome(
                False,
                False,
                message=f"Deletion transaction failed unexpectedly: {exc}",
            )
        if not outcome.committed:
            ui_rollback_errors = rollback_ui()
            canvas.current_component_id = previous_component_id
            canvas.current_axes_component_id = previous_axes_id
            if ui_rollback_errors:
                outcome = replace(
                    outcome,
                    rollback_complete=False,
                    message=(
                        f"{outcome.message} UI rollback was incomplete: "
                        + "; ".join(ui_rollback_errors)
                    ).strip(),
                )
            presenter.discard_pending()
            return presenter.present(outcome.as_batch_change())

        cleanup_notices = list(outcome.notices)
        for handle in axes_handles:
            try:
                panel.finalize_axes_inspector_removal(handle)
            except Exception as exc:
                from code.figuremodify.components import ComponentNotice, MessageLevel

                cleanup_notices.append(
                    ComponentNotice(
                        MessageLevel.WARNING,
                        f"Components were deleted, but Inspector cleanup reported: {exc}",
                    )
                )
        canvas._axes_component_ids = candidate_axes_map
        fallback_axes_id = canvas._axes_ancestor_id(fallback_id)
        canvas.current_axes_component_id = (
            fallback_axes_id
            if fallback_axes_id is not None
            else previous_axes_id
            if previous_axes_id in canvas.component_registry
            else None
        )
        canvas.current_component_id = fallback_id
        if fallback_id != previous_component_id:
            canvas.componentSelectionChanged.emit(fallback_id)
        outcome = replace(
            outcome,
            selected_component_id=fallback_id,
            notices=tuple(cleanup_notices),
        )
        presenter.discard_pending()
        if not present_success:
            return True
        count = len(request.component_ids)
        success = (
            "Axes deleted."
            if role_label.casefold() == "axes" and count == 1
            else (
                f"{count} {role_label} component"
                f"{'' if count == 1 else 's'} deleted."
            )
        )
        return presenter.present(outcome.as_batch_change(), success=success)
