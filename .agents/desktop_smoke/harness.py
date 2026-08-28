"""Temporary settings backend, MainWindow, clicks, grabs, and modal helpers."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import tempfile
from typing import Any, Callable

from PySide6.QtCore import QCoreApplication, QEventLoop, Qt, QTimer
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QInputDialog,
    QMessageBox,
    QPushButton,
    QWidget,
)

from mygui.application_settings import ApplicationSettingsService
from mygui.application_settings.storage import create_settings_backend
from mygui.application_theme import (
    apply_committed_appearance,
    compose_theme_runtime_applier,
    compose_theme_service,
)
from mygui.widgets.settings_center.window import SettingsCenterWindow

ORGANIZATION_NAME = "MyGUI-DesktopSmoke"
APPLICATION_NAME = "MyGUI-DesktopSmoke"
OVERRIDE_LINEWIDTH = 4.25
OVERRIDE_FACECOLOR = "#FFCC00"


class SmokeError(RuntimeError):
    """Structural failure in the desktop smoke walk."""


@dataclass
class ScreenshotRecord:
    name: str
    path: str
    width: int
    height: int


@dataclass
class ProjectSeed:
    canvas: Any
    old_axes_id: str
    old_line: Any
    old_linewidth: float
    old_facecolor: str
    x_ref: Any
    y_ref: Any
    new_canvas: Any = None
    new_axes_id: str | None = None
    new_line: Any = None


@dataclass
class SmokeHarness:
    output_dir: Path
    screenshots: list[ScreenshotRecord] = field(default_factory=list)
    app: QApplication | None = None
    window: Any = None
    seed: ProjectSeed | None = None
    _theme: Any = None
    _tempdir: tempfile.TemporaryDirectory[str] | None = None
    settings_path: Path | None = None
    _backend: Any = None
    timings: dict[str, float] = field(default_factory=dict)

    def start(self) -> None:
        """Create an isolated settings file, ThemeService, and visible MainWindow."""

        self.output_dir.mkdir(parents=True, exist_ok=True)
        existing = QApplication.instance()
        if existing is None:
            self.app = QApplication([])
        else:
            self.app = existing
        QCoreApplication.setOrganizationName(ORGANIZATION_NAME)
        QCoreApplication.setApplicationName(APPLICATION_NAME)
        self.app.setQuitOnLastWindowClosed(False)

        self._tempdir = tempfile.TemporaryDirectory(prefix="mygui-desktop-smoke-")
        self.settings_path = Path(self._tempdir.name) / "settings.ini"
        self._backend = create_settings_backend(file_path=self.settings_path)
        self._theme = compose_theme_service(self.app)
        service = ApplicationSettingsService(
            document=self._backend.application_settings_port(),
            runtime_applier=compose_theme_runtime_applier(self._theme),
        )
        apply_committed_appearance(self._theme, service.snapshot())

        from main import MainWindow

        self.window = MainWindow(
            settings_backend=self._backend,
            settings_service=service,
            theme_service=self._theme,
        )
        self.window._skip_close_confirmation = True
        self._isolate_template_library()
        self.window.showMaximized()
        self.pump(200)
        if not self.window.isVisible():
            raise SmokeError("MainWindow did not become visible.")

    def _isolate_template_library(self) -> None:
        """Redirect the shared TemplateLibrary away from the repository template/."""

        if self.window is None or self._tempdir is None:
            raise SmokeError("Cannot isolate the template library before start.")
        root = Path(self._tempdir.name) / "templates"
        root.mkdir(parents=True, exist_ok=True)
        library = self.window.template_workflow.library
        library.root = root

    def shutdown(self) -> None:
        """Close windows and drop the temporary settings file."""

        dialog = self.settings_dialog()
        if dialog is not None:
            try:
                dialog.reject()
            except RuntimeError:
                pass
            try:
                dialog.close()
                dialog.deleteLater()
            except RuntimeError:
                pass
        if self.window is not None:
            try:
                self.window._skip_close_confirmation = True
                self.window.close()
                self.window.deleteLater()
            except RuntimeError:
                pass
            self.window = None
        if self._theme is not None:
            try:
                self._theme.shutdown()
            except Exception:
                pass
            self._theme = None
        self.pump(50)
        if self._tempdir is not None:
            self._tempdir.cleanup()
            self._tempdir = None
        self._backend = None

    def pump(self, milliseconds: int = 50) -> None:
        """Process Qt events, including a short wait for paints and timers."""

        app = self.app or QApplication.instance()
        if app is None:
            return
        if milliseconds > 0:
            timer = QTimer()
            timer.setSingleShot(True)
            loop = QEventLoop()
            timer.timeout.connect(loop.quit)
            timer.start(max(1, int(milliseconds)))
            loop.exec()
        app.processEvents()

    def grab(self, widget: QWidget | None, name: str) -> Path:
        """Capture ``widget`` with ``QWidget.grab()`` and write a PNG."""

        if widget is None:
            raise SmokeError(f"Cannot screenshot {name!r}: widget is missing.")
        try:
            if not widget.isVisible():
                widget.show()
                self.pump(30)
            pixmap: QPixmap = widget.grab()
        except RuntimeError as exc:
            raise SmokeError(f"Cannot screenshot {name!r}: {exc}") from exc
        if pixmap.isNull() or pixmap.width() < 1 or pixmap.height() < 1:
            raise SmokeError(f"Screenshot {name!r} produced an empty pixmap.")
        path = self.output_dir / f"{name}.png"
        if not pixmap.save(str(path), "PNG"):
            raise SmokeError(f"Could not write screenshot {path}.")
        record = ScreenshotRecord(
            name=name,
            path=str(path),
            width=int(pixmap.width()),
            height=int(pixmap.height()),
        )
        self.screenshots.append(record)
        return path

    def grab_main(self, name: str) -> Path:
        return self.grab(self.window, name)

    def settings_dialog(self) -> SettingsCenterWindow | None:
        host = getattr(self.window, "settings_center", None)
        cached = getattr(host, "window", None) if host is not None else None
        if cached is not None:
            try:
                cached.objectName()
            except RuntimeError:
                cached = None
            else:
                return cached
        app = self.app or QApplication.instance()
        if app is None:
            return None
        for widget in app.topLevelWidgets():
            if widget.objectName() == "setting_dialog":
                return widget  # type: ignore[return-value]
        return None

    def require_settings(self) -> SettingsCenterWindow:
        dialog = self.settings_dialog()
        if dialog is None:
            raise SmokeError("Settings window objectName setting_dialog was not found.")
        return dialog

    def open_settings_via_gear(self, while_open: Callable[[], None]) -> None:
        """Click the rail gear. Run ``while_open`` inside the modal ``exec`` loop."""

        if self.window is None:
            raise SmokeError("MainWindow is not started.")
        button = self.window.left_column.setting_button
        error: list[BaseException] = []

        def _work() -> None:
            try:
                while_open()
            except BaseException as exc:  # noqa: BLE001 — surface after exec returns
                error.append(exc)
                dialog = self.settings_dialog()
                if dialog is not None:
                    try:
                        dialog.reject()
                    except RuntimeError:
                        pass

        QTimer.singleShot(0, _work)
        button.click()
        self.pump(50)
        if error:
            raise error[0]

    def present_settings(
        self,
        page_id: str | None = None,
        *,
        wait_ms: int = 80,
    ) -> SettingsCenterWindow:
        """Reopen the cached Settings window without blocking."""

        host = getattr(self.window, "settings_center", None)
        if host is None:
            raise SmokeError("Settings Center host is not installed.")
        dialog = host.present(page_id)
        if wait_ms > 0:
            self.pump(wait_ms)
        else:
            app = self.app or QApplication.instance()
            if app is not None:
                app.processEvents()
        if dialog.objectName() != "setting_dialog":
            raise SmokeError(
                f"Cached settings window objectName is {dialog.objectName()!r}."
            )
        return dialog

    def close_settings(self, *, cancel: bool = True, wait_ms: int = 50) -> None:
        dialog = self.settings_dialog()
        if dialog is None:
            return
        if cancel:
            dialog.reject()
        else:
            dialog.accept()
        if wait_ms > 0:
            self.pump(wait_ms)
        else:
            app = self.app or QApplication.instance()
            if app is not None:
                app.processEvents()

    def click(self, widget: QWidget | None, *, wait_ms: int = 40) -> None:
        if widget is None:
            raise SmokeError("Cannot click a missing widget.")
        if not widget.isEnabled():
            raise SmokeError(f"Widget {widget.objectName()!r} is disabled.")
        widget.click()
        self.pump(wait_ms)

    def click_and_dismiss_confirm(self, button: QPushButton) -> None:
        """Click a command that opens Yes/No or Cancel confirmation; always dismiss."""

        QTimer.singleShot(0, self.dismiss_confirmation)
        button.click()
        self.pump(80)
        self.dismiss_confirmation()

    def click_and_accept_confirm(self, button: QPushButton) -> None:
        """Click a command that opens a Yes/No box and accept with Yes."""

        QTimer.singleShot(0, self.accept_confirmation)
        button.click()
        self.pump(80)
        self.accept_confirmation()

    def accept_confirmation(self) -> None:
        app = self.app or QApplication.instance()
        if app is None:
            return
        for widget in list(app.topLevelWidgets()):
            if not isinstance(widget, QMessageBox):
                continue
            try:
                visible = widget.isVisible()
            except RuntimeError:
                continue
            if not visible:
                continue
            yes_button = widget.button(QMessageBox.StandardButton.Yes)
            if yes_button is not None:
                yes_button.click()
            else:
                widget.accept()
        self.pump(20)

    def accept_input_dialog(self) -> None:
        """Accept a visible QInputDialog without waiting for keyboard focus."""

        app = self.app or QApplication.instance()
        if app is None:
            return
        for widget in list(app.topLevelWidgets()):
            if not isinstance(widget, QInputDialog):
                continue
            try:
                visible = widget.isVisible()
            except RuntimeError:
                continue
            if visible:
                widget.accept()
                break
        self.pump(20)

    def dismiss_confirmation(self) -> None:
        app = self.app or QApplication.instance()
        if app is None:
            return
        for widget in list(app.topLevelWidgets()):
            if not isinstance(widget, QMessageBox):
                continue
            try:
                visible = widget.isVisible()
            except RuntimeError:
                continue
            if not visible:
                continue
            no_button = widget.button(QMessageBox.StandardButton.No)
            cancel_button = widget.button(QMessageBox.StandardButton.Cancel)
            target = no_button or cancel_button
            if target is not None:
                target.click()
            else:
                widget.reject()
        self.pump(20)

    def select_page(self, page_id: str) -> None:
        dialog = self.require_settings()
        nav = dialog.nav_list
        for index in range(nav.count()):
            item = nav.item(index)
            if item is not None and str(item.data(Qt.UserRole)) == page_id:
                nav.setCurrentItem(item)
                self.pump(60)
                return
        raise SmokeError(f"Settings nav has no page {page_id!r}.")

    def page_title(self) -> str:
        dialog = self.require_settings()
        label = dialog.findChild(QWidget, "settings_page_title")
        if label is None:
            raise SmokeError("settings_page_title is missing.")
        return str(label.text())

    def seed_default_project(self) -> ProjectSeed:
        """Create one project, one Axes, and one Curve as the pre-Apply baseline."""

        from mygui.database import ColumnRef
        from mygui.figuremodify.axes_layout import AxesLayoutSpec
        from mygui.figuremodify.style_base.color_models import normalize_color

        if self.window is None:
            raise SmokeError("MainWindow is not started.")
        figure_window = self.window.figure_window
        figure_window.add_figure(
            width=6.4,
            height=4.8,
            dpi=100,
            style="default",
            canva_name="DesktopSmoke",
        )
        canvas = figure_window.current_canva
        if canvas is None:
            raise SmokeError("Figure canvas was not created.")
        cell_view = canvas.axes_layout_service.creation_view_defaults()
        axes_ids = canvas.create_axes_layout(
            AxesLayoutSpec.grid(
                1,
                1,
                cell_view=cell_view,
            )
        )
        if not axes_ids:
            raise SmokeError("Axes layout did not return an Axes id.")
        old_axes_id = str(axes_ids[0])
        old_line = canvas.add_curve("x", 0, 1, "-", "#222222", "keep")
        target = canvas.component_registry.resolve_target(old_axes_id)
        sheet = self.window.table.current_subtable().get_table(0).table_model.sheet
        sheet.set_block(0, 0, [[0.0, 1.0], [1.0, 2.0], [2.0, 3.0]])
        x_ref = ColumnRef(canvas.project_id, sheet.id, sheet.columns[0].id)
        y_ref = ColumnRef(canvas.project_id, sheet.id, sheet.columns[1].id)
        self.seed = ProjectSeed(
            canvas=canvas,
            old_axes_id=old_axes_id,
            old_line=old_line,
            old_linewidth=float(old_line.get_linewidth()),
            old_facecolor=normalize_color(target.get_facecolor()),
            x_ref=x_ref,
            y_ref=y_ref,
        )
        self.pump(80)
        try:
            canvas.draw()
        except Exception:
            pass
        self.pump(40)
        return self.seed

    def create_project(
        self,
        name: str = "TestProject",
        style: str = "default",
        width: float = 6.4,
        height: float = 4.8,
        dpi: int = 100,
    ) -> Any:
        """Create a new Figure canvas in the figure workspace."""
        if self.window is None:
            raise SmokeError("MainWindow is not started.")
        figure_window = self.window.figure_window
        figure_window.add_figure(
            width=width,
            height=height,
            dpi=dpi,
            style=style,
            canva_name=name,
        )
        self.pump(80)
        canvas = figure_window.current_canva
        if canvas is None:
            raise SmokeError(f"Failed to create project {name!r}.")
        return canvas

    def seed_field_2d_table(
        self,
        canvas: Any = None,
        n_x: int = 5,
        n_y: int = 5,
    ) -> tuple[Any, Any, Any]:
        """Populate a 2D regular grid (X, Y, Z) in the current table."""
        from mygui.database import ColumnRef

        if canvas is None:
            canvas = self.window.figure_window.current_canva
        subtable = self.window.table.current_subtable()
        sheet = subtable.get_table(0).table_model.sheet
        rows = []
        for i in range(n_x):
            for j in range(n_y):
                x = float(i)
                y = float(j)
                z = float((i - n_x / 2.0) ** 2 + (j - n_y / 2.0) ** 2)
                rows.append([x, y, z])
        sheet.set_block(0, 0, rows)
        x_ref = ColumnRef(canvas.project_id, sheet.id, sheet.columns[0].id)
        y_ref = ColumnRef(canvas.project_id, sheet.id, sheet.columns[1].id)
        z_ref = ColumnRef(canvas.project_id, sheet.id, sheet.columns[2].id)
        self.pump(40)
        return x_ref, y_ref, z_ref

    def seed_multi_column_table(
        self,
        canvas: Any = None,
    ) -> tuple[Any, tuple[Any, ...]]:
        """Populate a table sheet with X, Y1, Y2, Y3 columns."""
        from mygui.database import ColumnRef

        if canvas is None:
            canvas = self.window.figure_window.current_canva
        subtable = self.window.table.current_subtable()
        sheet = subtable.get_table(0).table_model.sheet
        rows = [
            [1.0, 2.0, 5.0, 10.0],
            [2.0, 4.0, 8.0, 14.0],
            [3.0, 6.0, 11.0, 18.0],
            [4.0, 8.0, 14.0, 22.0],
            [5.0, 10.0, 17.0, 26.0],
        ]
        sheet.set_block(0, 0, rows)
        x_ref = ColumnRef(canvas.project_id, sheet.id, sheet.columns[0].id)
        y1_ref = ColumnRef(canvas.project_id, sheet.id, sheet.columns[1].id)
        y2_ref = ColumnRef(canvas.project_id, sheet.id, sheet.columns[2].id)
        y3_ref = ColumnRef(canvas.project_id, sheet.id, sheet.columns[3].id)
        self.pump(40)
        return x_ref, (y1_ref, y2_ref, y3_ref)

    def select_component(self, component_id: str) -> None:
        """Select a component on the active canvas and pump the UI."""
        canvas = self.window.figure_window.current_canva
        if canvas is not None:
            canvas.select_component(component_id)
            self.pump(60)

    def grab_inspector(self, name: str) -> Path:
        """Capture screenshot of the active Inspector host."""
        host = self.window.fig_control_window.figure_inspector_host
        return self.grab(host, name)

    def grab_canvas(self, name: str) -> Path:
        """Capture screenshot of the active Figure canvas."""
        canvas = self.window.figure_window.current_canva
        return self.grab(canvas, name)

    def zoom_in_axes_spec(self, canvas: Any, bounds=(0.6, 0.55, 0.35, 0.35)):
        """Build a Zoom inset spec from the current Figure creation defaults."""

        from mygui.figuremodify.in_axes import ZoomInAxesCreateSpec

        defaults = canvas.component_creation_defaults().in_axes
        return ZoomInAxesCreateSpec(
            bounds=bounds,
            xlim=(0.0, 5.0),
            ylim=(0.0, 25.0),
            facecolor=defaults.facecolor,
            edgecolor=defaults.edgecolor,
            linewidth=defaults.linewidth,
            indicator_color=defaults.indicator_color,
            indicator_linestyle=defaults.indicator_linestyle,
            indicator_linewidth=defaults.indicator_linewidth,
        )

    def image_in_axes_spec(self, canvas: Any, bounds=(0.05, 0.55, 0.3, 0.3)):
        """Build an Image inset spec with an in-memory PNG payload."""

        import base64
        from io import BytesIO

        from PIL import Image

        from mygui.figuremodify.in_axes import ImageInAxesCreateSpec

        defaults = canvas.component_creation_defaults().in_axes
        buffer = BytesIO()
        Image.new("RGBA", (4, 3), (20, 40, 80, 255)).save(buffer, format="PNG")
        return ImageInAxesCreateSpec(
            bounds=bounds,
            filename="smoke.png",
            mime_type="image/png",
            payload_base64=base64.b64encode(buffer.getvalue()).decode("ascii"),
            facecolor=defaults.facecolor,
            edgecolor=defaults.edgecolor,
            linewidth=defaults.linewidth,
            interpolation=defaults.image_interpolation,
        )

    def dismiss_all_dialogs(self) -> None:
        """Close any remaining open modal or modeless dialogs."""
        from PySide6.QtWidgets import QDialog

        app = self.app or QApplication.instance()
        if app is None:
            return
        for widget in list(app.topLevelWidgets()):
            if isinstance(widget, QDialog) and widget.isVisible():
                try:
                    widget.reject()
                except Exception:
                    try:
                        widget.close()
                    except Exception:
                        pass
        self.pump(30)
