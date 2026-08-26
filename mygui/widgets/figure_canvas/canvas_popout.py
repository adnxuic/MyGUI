"""Top-level Canvas popout window that returns its content on close."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import QDialog, QVBoxLayout, QWidget

if TYPE_CHECKING:
    from .py_figure_canves import PyFigureCanvas


class CanvasPopoutWindow(QDialog):
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
        # Theme subscription only. This window must not cache ComponentState,
        # selection IDs, or color-cycle cursors.
        from mygui.application_theme import subscribe_theme_window

        subscribe_theme_window(self)

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
