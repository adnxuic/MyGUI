"""Deletion Coordinator, Batch Deletion & Undo/Redo Replay desktop smoke. Group id: deletion_history."""

from __future__ import annotations

from typing import Any, Callable

from mygui.figuremodify.axes_layout import AxesLayoutSpec
from mygui.figuremodify.components import ComponentKind, ComponentRole
from mygui.widgets.component_tree.dialogs import (
    ComponentBatchDeleteDialog,
    DeleteCandidate,
)

from desktop_smoke.harness import SmokeError, SmokeHarness


def run_deletion_history_scenarios(harness: SmokeHarness) -> list[dict[str, Any]]:
    """Walk through Deletion Coordinator, Batch Deletion, and Undo/Redo replay."""
    results: list[dict[str, Any]] = []

    results.append(
        _run_case(
            harness,
            "deletion_history.single_delete",
            lambda: _scenario_single_delete(harness),
        )
    )
    results.append(
        _run_case(
            harness,
            "deletion_history.batch_delete",
            lambda: _scenario_batch_delete(harness),
        )
    )
    results.append(
        _run_case(
            harness,
            "deletion_history.axes_cascade",
            lambda: _scenario_axes_cascade(harness),
        )
    )
    results.append(
        _run_case(
            harness,
            "deletion_history.undo_redo",
            lambda: _scenario_undo_redo(harness),
        )
    )
    return results


def _run_case(
    harness: SmokeHarness,
    scenario_id: str,
    body: Callable[[], None],
) -> dict[str, Any]:
    before = len(harness.screenshots)
    try:
        body()
        return {
            "id": scenario_id,
            "status": "passed",
            "screenshotCount": len(harness.screenshots) - before,
        }
    except Exception as exc:  # noqa: BLE001
        try:
            harness.dismiss_all_dialogs()
            harness.grab_main(f"{scenario_id.replace('.', '-')}-failure")
        except Exception:
            pass
        return {
            "id": scenario_id,
            "status": "failed",
            "error": f"{type(exc).__name__}: {exc}",
            "screenshotCount": len(harness.screenshots) - before,
        }


def _scenario_single_delete(harness: SmokeHarness) -> None:
    canvas = harness.create_project("Smoke_Single_Delete")
    canvas.create_axes_layout(AxesLayoutSpec.grid(1, 1))
    harness.pump(50)

    canvas.add_curve("sin(x)", 0, 5, "-", "#1f77b4", "Curve1")
    canvas.add_curve("cos(x)", 0, 5, "-", "#ff7f0e", "Curve2")
    harness.pump(50)

    curves_before = canvas.component_registry.query(
        kind=ComponentKind.LINE, role=ComponentRole.FUNCTION_CURVE
    )
    if len(curves_before) != 2:
        raise SmokeError(
            f"Expected 2 curves before delete, got {len(curves_before)}."
        )

    # Request deletion of line1
    canvas.delete_components([curves_before[0].component_id])
    harness.pump(60)
    canvas.redraw()
    harness.pump(40)

    curves_after = canvas.component_registry.query(
        kind=ComponentKind.LINE, role=ComponentRole.FUNCTION_CURVE
    )
    if len(curves_after) != 1:
        raise SmokeError(
            f"Expected 1 curve after delete, got {len(curves_after)}."
        )

    harness.grab_canvas("delete-01-single-delete-canvas")


def _scenario_batch_delete(harness: SmokeHarness) -> None:
    canvas = harness.create_project("Smoke_Batch_Delete")
    canvas.create_axes_layout(AxesLayoutSpec.grid(1, 1))
    harness.pump(50)

    canvas.add_curve("x", 0, 5, "-", "#1f77b4", "C1")
    canvas.add_curve("2*x", 0, 5, "-", "#ff7f0e", "C2")
    canvas.add_curve("3*x", 0, 5, "-", "#2ca02c", "C3")
    harness.pump(50)

    curves = canvas.component_registry.query(
        kind=ComponentKind.LINE, role=ComponentRole.FUNCTION_CURVE
    )
    candidates = [
        DeleteCandidate(
            component_id=c.component_id,
            instance_label=f"Curve {idx}",
            parent_label="Axes 1",
            cohort_key=(None, "line", "function_curve", "remove"),
        )
        for idx, c in enumerate(curves, 1)
    ]

    dialog = ComponentBatchDeleteDialog(
        candidates, role_label="Function Curve", parent=harness.window
    )
    dialog.setModal(False)
    dialog.show()
    harness.pump(50)
    harness.grab(dialog, "delete-02-batch-delete-dialog")

    # Select only the first 2
    selected_ids = [candidates[0].component_id, candidates[1].component_id]
    canvas.delete_components(selected_ids)
    dialog.accept()
    harness.pump(60)
    canvas.redraw()
    harness.pump(40)

    surviving = canvas.component_registry.query(
        kind=ComponentKind.LINE, role=ComponentRole.FUNCTION_CURVE
    )
    if len(surviving) != 1:
        raise SmokeError(
            f"Expected 1 surviving curve after batch delete, got {len(surviving)}."
        )

    harness.grab_canvas("delete-03-batch-delete-canvas")


def _scenario_axes_cascade(harness: SmokeHarness) -> None:
    canvas = harness.create_project("Smoke_Axes_Cascade")
    axes_ids = canvas.create_axes_layout(AxesLayoutSpec.grid(2, 2))
    if len(axes_ids) != 4:
        raise SmokeError(f"Expected 4 axes in 2x2 layout, got {len(axes_ids)}.")
    harness.pump(50)

    # Delete middle Axes (axes_ids[1])
    target_id = str(axes_ids[1])
    canvas.delete_components([target_id])
    harness.pump(60)
    canvas.redraw()
    harness.pump(40)

    remaining = canvas.component_registry.query(kind=ComponentKind.AXES)
    if len(remaining) != 3:
        raise SmokeError(
            f"Expected 3 surviving axes after cascade delete, got {len(remaining)}."
        )

    harness.grab_canvas("delete-04-axes-cascade-canvas")


def _scenario_undo_redo(harness: SmokeHarness) -> None:
    canvas = harness.create_project("Smoke_Undo_Redo")
    canvas.create_axes_layout(AxesLayoutSpec.grid(1, 1))
    harness.pump(50)

    # Add curve
    canvas.add_curve("sin(x)", 0, 5, "-", "#1f77b4", "CurveUndo")
    harness.pump(50)
    canvas.redraw()
    harness.grab_canvas("history-01-curve-added")

    stack = canvas.repository.undo_stack(canvas.project_id)

    # Undo
    stack.undo()
    harness.pump(60)
    canvas.redraw()
    harness.pump(40)

    curves = canvas.component_registry.query(
        kind=ComponentKind.LINE, role=ComponentRole.FUNCTION_CURVE
    )
    if curves:
        raise SmokeError("Curve still exists after undo.")
    harness.grab_canvas("history-02-after-undo")

    # Redo
    stack.redo()
    harness.pump(60)
    canvas.redraw()
    harness.pump(40)

    curves_redo = canvas.component_registry.query(
        kind=ComponentKind.LINE, role=ComponentRole.FUNCTION_CURVE
    )
    if not curves_redo:
        raise SmokeError("Curve missing after redo.")
    harness.grab_canvas("history-03-after-redo")

    # Add Annotation and test Undo/Redo
    canvas.add_annotation(
        {
            "text": "Undo/Redo Annotation",
            "xy": [2.0, 0.0],
            "xycoords": "data",
            "xytext": [20.0, 20.0],
            "textcoords": "offset_points",
            "arrow_enabled": True,
        }
    )
    harness.pump(60)
    canvas.redraw()
    harness.pump(40)
    annos = canvas.component_registry.query(kind=ComponentKind.ANNOTATION)
    if not annos:
        raise SmokeError("Annotation was not created in undo/redo scenario.")
    harness.grab_canvas("history-04-annotation-added")

    stack.undo()
    harness.pump(60)
    canvas.redraw()
    harness.pump(40)
    annos_undo = canvas.component_registry.query(kind=ComponentKind.ANNOTATION)
    if annos_undo:
        raise SmokeError("Annotation still exists after undo.")
    harness.grab_canvas("history-05-annotation-undo")

    stack.redo()
    harness.pump(60)
    canvas.redraw()
    harness.pump(40)
    annos_redo = canvas.component_registry.query(kind=ComponentKind.ANNOTATION)
    if not annos_redo:
        raise SmokeError("Annotation missing after redo.")
    harness.grab_canvas("history-06-annotation-redo")
