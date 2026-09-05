"""Native dialog-open and lightweight component-creation frame probes."""

from __future__ import annotations

from collections import Counter
from contextlib import ExitStack
from typing import Any, Callable
from unittest.mock import patch

from PySide6.QtWidgets import QWidget

from desktop_smoke.frame_probe import (
    FrameSample,
    measure_frame,
    median_ms,
    p95_ms,
    wait_settle,
)
from desktop_smoke.gates import (
    SAMPLE_FRAMES,
    WARMUP_FRAMES,
    assert_creation_gates,
)
from desktop_smoke.harness import SmokeError, SmokeHarness


_COUNTER_KEYS = (
    "style_default_resolution",
    "stylesheet_write",
    "inspector_construction",
    "selection_publication",
    "canvas_draw",
    "canvas_draw_idle",
)


class _CreationInstrumentation:
    """Count expensive work only while a measured action is dispatching."""

    def __init__(self, canvas) -> None:
        self.canvas = canvas
        self.active = False
        self.counts: Counter[str] = Counter()
        self._stack = ExitStack()
        self._original_draw = canvas.canva.draw
        self._original_draw_idle = canvas.canva.draw_idle

    def __enter__(self):
        from mygui.figuremodify.style_base.creation_defaults import (
            resolve_component_creation_defaults,
        )
        from mygui.widgets.fig_control_window.component_editors.inspector import (
            ComponentInspector,
        )

        original_inspector_init = ComponentInspector.__init__
        original_set_stylesheet = QWidget.setStyleSheet

        def resolve_defaults(style):
            self._count("style_default_resolution")
            return resolve_component_creation_defaults(style)

        def inspector_init(widget, *args, **kwargs):
            self._count("inspector_construction")
            return original_inspector_init(widget, *args, **kwargs)

        def set_stylesheet(widget, stylesheet):
            self._count("stylesheet_write")
            return original_set_stylesheet(widget, stylesheet)

        self._stack.enter_context(
            patch(
                "mygui.widgets.figure_canvas.py_figure_canves."
                "resolve_component_creation_defaults",
                side_effect=resolve_defaults,
            )
        )
        self._stack.enter_context(
            patch.object(ComponentInspector, "__init__", inspector_init)
        )
        self._stack.enter_context(
            patch.object(QWidget, "setStyleSheet", set_stylesheet)
        )
        self.canvas.canva.draw = self._draw
        self.canvas.canva.draw_idle = self._draw_idle
        self.canvas.componentSelectionChanged.connect(self._selection_changed)
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        try:
            self.canvas.componentSelectionChanged.disconnect(
                self._selection_changed
            )
        except (RuntimeError, TypeError):
            pass
        self.canvas.canva.draw = self._original_draw
        self.canvas.canva.draw_idle = self._original_draw_idle
        self._stack.close()

    def _count(self, key: str) -> None:
        if self.active:
            self.counts[key] += 1

    def _draw(self, *args, **kwargs):
        self._count("canvas_draw")
        return self._original_draw(*args, **kwargs)

    def _draw_idle(self, *args, **kwargs):
        self._count("canvas_draw_idle")
        return self._original_draw_idle(*args, **kwargs)

    def _selection_changed(self, _component_id: str) -> None:
        self._count("selection_publication")

    def measure(
        self,
        target: QWidget,
        action: Callable[[], Any],
    ) -> tuple[FrameSample, dict[str, int]]:
        before = Counter(self.counts)

        def dispatch():
            self.active = True
            try:
                return action()
            finally:
                self.active = False

        sample = measure_frame(target, dispatch)
        return sample, {
            key: int(self.counts[key] - before[key]) for key in _COUNTER_KEYS
        }


def _timing(samples: list[FrameSample]) -> dict[str, Any]:
    dispatch = [item.dispatch_ms for item in samples]
    first_paint = [item.first_paint_ms for item in samples]
    settle = [item.settle_ms for item in samples]
    return {
        "paintRegion": samples[0].paint_region,
        "dispatch_ms": {
            "samples": dispatch,
            "median": median_ms(dispatch),
            "p95": p95_ms(dispatch),
        },
        "first_paint_ms": {
            "samples": first_paint,
            "median": median_ms(first_paint),
            "p95": p95_ms(first_paint),
        },
        "settle_ms": {
            "samples": settle,
            "median": median_ms(settle),
            "p95": p95_ms(settle),
        },
    }


def _diagnostics(samples: list[dict[str, int]]) -> dict[str, Any]:
    return {
        key: {
            "samples": [sample[key] for sample in samples],
            "total": sum(sample[key] for sample in samples),
            "max": max(sample[key] for sample in samples),
        }
        for key in _COUNTER_KEYS
    }


def _sample_actions(
    instrumentation: _CreationInstrumentation,
    target: QWidget,
    action: Callable[[int], Any],
    cleanup: Callable[[int], None],
) -> tuple[dict[str, Any], dict[str, Any]]:
    measured: list[FrameSample] = []
    diagnostics: list[dict[str, int]] = []
    total = WARMUP_FRAMES + SAMPLE_FRAMES
    for index in range(total):
        sample, counts = instrumentation.measure(
            target,
            lambda current=index: action(current),
        )
        cleanup(index)
        wait_settle(target)
        if index >= WARMUP_FRAMES:
            measured.append(sample)
            diagnostics.append(counts)
    return _timing(measured), _diagnostics(diagnostics)


def measure_creation_performance(harness: SmokeHarness) -> None:
    """Measure recreated dialogs and lightweight component publication."""

    from mygui.figuremodify.axes_layout import AxesLayoutSpec
    from mygui.widgets.title_bar.titlebar_dialog.py_chart_dialog import (
        PyPlotDialog,
    )
    from mygui.widgets.title_bar.titlebar_dialog.py_element_dialog import (
        PyTextDialog,
    )

    canvas = harness.create_project("Smoke_Creation_Performance")
    canvas.create_axes_layout(AxesLayoutSpec.grid(1, 1))
    wait_settle(harness.window)
    figure_window = harness.window.figure_window
    open_dialogs: dict[int, QWidget] = {}

    def dialog_action(dialog_type, title: str, index: int):
        dialog = dialog_type(
            dialog_name=title,
            figure_window=figure_window,
            parent=harness.window,
        )
        dialog.setModal(False)
        dialog.show()
        open_dialogs[index] = dialog
        return dialog

    def close_dialog(index: int) -> None:
        dialog = open_dialogs.pop(index)
        dialog.reject()
        dialog.deleteLater()

    payload: dict[str, Any] = {}
    diagnostics: dict[str, Any] = {}
    with _CreationInstrumentation(canvas) as instrumentation:
        canvas._creation_defaults_cache = None
        canvas._creation_defaults_cache_key = None
        payload["plot_dialog"], diagnostics["plot_dialog"] = _sample_actions(
            instrumentation,
            harness.window,
            lambda index: dialog_action(PyPlotDialog, "Plot", index),
            close_dialog,
        )
        payload["text_dialog"], diagnostics["text_dialog"] = _sample_actions(
            instrumentation,
            harness.window,
            lambda index: dialog_action(PyTextDialog, "Text", index),
            close_dialog,
        )

        created_ids: dict[int, str] = {}

        def create_curve(index: int):
            component_id = f"perf-curve-{index}"
            created_ids[index] = component_id
            canvas.add_curve(
                "x",
                0.0,
                1.0,
                "-",
                "#1f77b4",
                "performance",
                object_id=component_id,
            )
            return canvas.figure_inspector.inspector(component_id)

        def create_text(index: int):
            component_id = f"perf-text-{index}"
            created_ids[index] = component_id
            canvas.add_text(
                0.25,
                0.75,
                "performance",
                "DejaVu Sans",
                10.0,
                object_id=component_id,
            )
            return canvas.figure_inspector.inspector(component_id)

        def delete_created(index: int) -> None:
            component_id = created_ids.pop(index)
            if not canvas.delete_component_group(
                (component_id,),
                role_label="performance component",
            ):
                raise SmokeError(
                    f"Could not delete measured component {component_id!r}."
                )

        payload["curve_create"], diagnostics["curve_create"] = _sample_actions(
            instrumentation,
            harness.window.fig_control_window.figure_inspector_host,
            create_curve,
            delete_created,
        )
        payload["text_create"], diagnostics["text_create"] = _sample_actions(
            instrumentation,
            harness.window.fig_control_window.figure_inspector_host,
            create_text,
            delete_created,
        )

    payload["diagnostics"] = diagnostics
    harness.timings["creation_performance"] = payload
    assert_creation_gates(harness.timings)
