"""Project-history-aware Matplotlib navigation toolbar for one Canvas."""

from __future__ import annotations

from functools import wraps

from PySide6.QtWidgets import QDialogButtonBox

from mygui.widgets.english_buttons import apply_english_dialog_buttons
from matplotlib.backends.backend_qtagg import (
    NavigationToolbar2QT as NavigationToolbar,
)


def history_command(text: str, *, scan_all: bool = False):
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


class ProjectNavigationToolbar(NavigationToolbar):
    """Add project history boundaries to persisted canvas view actions."""

    def __init__(self, canvas, parent, history) -> None:
        self._project_history = history
        super().__init__(canvas, parent)

    def home(self, *args):
        return self._project_history.perform(
            "Reset Figure View",
            lambda: super(ProjectNavigationToolbar, self).home(*args),
            scan_all=True,
        )

    def back(self, *args):
        return self._project_history.perform(
            "Back Figure View",
            lambda: super(ProjectNavigationToolbar, self).back(*args),
            scan_all=True,
        )

    def forward(self, *args):
        return self._project_history.perform(
            "Forward Figure View",
            lambda: super(ProjectNavigationToolbar, self).forward(*args),
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
        apply_english_dialog_buttons(dialog.bbox)
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

    def apply_theme_icons(self, snapshot, provider) -> None:
        """Rebuild Matplotlib tool icons from the current toolbar palette."""

        del snapshot, provider
        actions = getattr(self, "_actions", None)
        if not actions:
            return
        for text, _tooltip, image_file, callback in self.toolitems:
            if not text or not image_file:
                continue
            action = actions.get(callback)
            if action is None:
                continue
            action.setIcon(self._icon(f"{image_file}.png"))

    def save_figure(self, *args):
        figure_canvas = self.parent()
        figure_canvas.exportRequested.emit(figure_canvas)

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
