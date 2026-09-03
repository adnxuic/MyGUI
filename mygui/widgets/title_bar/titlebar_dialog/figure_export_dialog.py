"""Modal Figure export window shared by the File menu and canvas Save."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from pathlib import Path

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
)

from mygui import status_messages
from mygui.application_settings import (
    ExportSettings,
    commit_succeeded,
)
from mygui.application_settings.ports import (
    ExportPreferencesPort,
    MemoryExportPreferences,
)
from mygui.figure_export import (
    ExportFormat,
    FigureExportContext,
    FigureExportRequest,
    extension_error,
    with_format_extension,
)
from mygui.application_theme import bind_widget_qss
from mygui.widgets.ui_components import (
    UiRole,
    UiVariant,
    annotate_form_fields,
    annotate_sections,
    apply_ui_style,
    ask_confirmation,
    style_accept_cancel,
)
from mygui.resources import icon_path
from mygui.widgets.common_widget.min_widget.color_library import ColorLibrary
from mygui.widgets.title_bar.titlebar_dialog.figure_export_options_panel import (
    FigureExportOptionsPanel,
)

_PREFERENCE_WARNING = (
    "Figure exported, but export preferences could not be saved."
)


class FigureExportDialog(QDialog):
    """Collect one-shot export options without changing the live Figure."""

    def __init__(
        self,
        *,
        context: FigureExportContext,
        color_library: ColorLibrary,
        export_preferences: ExportPreferencesPort | None = None,
        export_callable: Callable[[FigureExportRequest], None],
        parent=None,
    ):
        super().__init__(parent)
        if color_library is None:
            raise ValueError("FigureExportDialog requires the shared ColorLibrary.")
        if export_callable is None:
            raise ValueError("FigureExportDialog requires an export callable.")
        self._context = context
        self._color_library = color_library
        self._export_preferences = (
            export_preferences
            if export_preferences is not None
            else MemoryExportPreferences()
        )
        self._export_callable = export_callable
        self._generated_path = True
        self.setObjectName("figure_export_dialog")
        self.setModal(True)
        self.setWindowTitle("Export Current Figure")
        self.setWindowIcon(QIcon(icon_path("save.svg")))
        bind_widget_qss(
            self,
            "mygui/widgets/title_bar/titlebar_dialog/dialog_style.qss",
        )
        self.resize(640, 620)

        preferences = self._export_preferences.current()
        self.options_panel = FigureExportOptionsPanel(
            color_library,
            document_dpi=context.document_dpi,
            width_inches=context.width_inches,
            height_inches=context.height_inches,
            include_format_row=False,
            parent=self,
        )
        self.options_panel.set_export_settings(preferences)
        self._bind_panel_widgets()
        self._last_directory = preferences.last_directory

        root = QVBoxLayout(self)
        destination = QHBoxLayout()
        self.path_edit = QLineEdit(self)
        self.path_edit.setObjectName("export_path_edit")
        self.path_edit.setAccessibleName("Export path")
        self.browse_button = QPushButton("Browse…", self)
        self.browse_button.setObjectName("export_browse_button")
        destination.addWidget(self.path_edit, 1)
        destination.addWidget(self.format_combo)
        destination.addWidget(self.browse_button)
        root.addLayout(destination)

        self.error_label = QLabel(self)
        self.error_label.setObjectName("export_error_label")
        self.error_label.setWordWrap(True)
        root.addWidget(self.error_label)

        self.tabs = self.options_panel.tabs
        root.addWidget(self.options_panel, 1)

        self.summary_label = QLabel(self)
        self.summary_label.setObjectName("export_summary_label")
        self.summary_label.setWordWrap(True)
        root.addWidget(self.summary_label)

        buttons = QHBoxLayout()
        self.restore_button = QPushButton("Restore defaults", self)
        self.restore_button.setObjectName("export_restore_button")
        self.export_button = QPushButton("Export", self)
        self.export_button.setObjectName("export_button")
        self.export_button.setDefault(True)
        self.cancel_button = QPushButton("Cancel", self)
        self.cancel_button.setObjectName("export_cancel_button")
        apply_ui_style(
            self.restore_button,
            role=UiRole.BUTTON,
            variant=UiVariant.GHOST,
        )
        apply_ui_style(
            self.browse_button,
            role=UiRole.BUTTON,
            variant=UiVariant.OUTLINE,
        )
        style_accept_cancel(self.export_button, self.cancel_button)
        annotate_form_fields(self)
        annotate_sections(self)
        buttons.addWidget(self.restore_button)
        buttons.addStretch(1)
        buttons.addWidget(self.export_button)
        buttons.addWidget(self.cancel_button)
        root.addLayout(buttons)

        self.path_edit.textChanged.connect(self._path_edited)
        self.format_combo.currentIndexChanged.connect(self._format_changed)
        self.options_panel.valuesChanged.connect(self._refresh_state)
        self.browse_button.clicked.connect(self._browse)
        self.restore_button.clicked.connect(self._restore_defaults)
        self.export_button.clicked.connect(self._export)
        self.cancel_button.clicked.connect(self.reject)
        self._generated_path = True
        self.path_edit.setText(
            str(self._context.default_path(self.current_format(), self._last_directory))
        )
        self._refresh_state()

    def current_format(self) -> ExportFormat:
        """Return the format combo as the authoritative export format."""

        return self.options_panel.current_format()

    def _bind_panel_widgets(self) -> None:
        for name, widget in self.options_panel.widget_aliases().items():
            setattr(self, name, widget)

    def _restore_defaults(self) -> None:
        self.options_panel.set_export_settings(ExportSettings())
        self._last_directory = ""
        self._generated_path = True
        blocked = self.path_edit.blockSignals(True)
        self.path_edit.setText(
            str(self._context.default_path(self.current_format(), ""))
        )
        self.path_edit.blockSignals(blocked)
        self._refresh_state()

    def _path_edited(self, _text: str) -> None:
        if self.path_edit.hasFocus():
            self._generated_path = False
        self._refresh_state()

    def _format_changed(self) -> None:
        fmt = self.current_format()
        current = Path(self.path_edit.text().strip() or ".")
        if self._generated_path:
            updated = self._context.default_path(fmt, self._last_directory)
        else:
            updated = with_format_extension(current, fmt)
        blocked = self.path_edit.blockSignals(True)
        self.path_edit.setText(str(updated))
        self.path_edit.blockSignals(blocked)
        self._refresh_state()

    def _browse(self) -> None:
        fmt = self.current_format()
        start = self.path_edit.text().strip() or str(
            self._context.default_path(fmt, self._last_directory)
        )
        patterns = " ".join(f"*{ext}" for ext in fmt.extensions)
        selected, _filter = QFileDialog.getSaveFileName(
            self,
            "Export Current Figure",
            start,
            f"{fmt.display_name} ({patterns})",
            options=QFileDialog.Option.DontConfirmOverwrite,
        )
        if not selected:
            return
        self._generated_path = False
        self._last_directory = str(Path(selected).parent)
        self.options_panel.set_last_directory(self._last_directory)
        self.path_edit.setText(str(with_format_extension(selected, fmt)))
        self._refresh_state()

    def _build_request(self) -> FigureExportRequest:
        return FigureExportRequest(
            path=Path(self.path_edit.text().strip()),
            format=self.current_format(),
            options=self.options_panel.figure_export_options(),
        )

    def _validation_message(self) -> str | None:
        fmt = self.current_format()
        path_error = extension_error(self.path_edit.text().strip(), fmt)
        if path_error:
            return path_error
        try:
            self._build_request()
        except ValueError as exc:
            return str(exc)
        return None

    def _refresh_state(self) -> None:
        self.options_panel.refresh_enabled_state()
        fmt = self.current_format()
        dpi = self.options_panel.effective_dpi()
        tight = self.bbox_tight.isChecked()
        error = self._validation_message()
        self.error_label.setText(error or "")
        self.export_button.setEnabled(error is None)
        self.summary_label.setText(self._summary_text(fmt, dpi, tight))

    def _summary_text(self, fmt: ExportFormat, dpi: float, tight: bool) -> str:
        parts = [
            f"{fmt.display_name} at {dpi:g} DPI",
            "transparent" if self.transparent.isChecked() else "opaque",
            "tight crop" if tight else "figure bounds",
        ]
        if fmt is ExportFormat.PNG:
            if self.png_optimize.isChecked():
                parts.append("PNG optimize")
            else:
                parts.append(f"PNG compression {self.png_compress.value()}")
        elif fmt is ExportFormat.JPEG:
            parts.append(f"JPEG quality {self.jpeg_quality.value()}")
        elif fmt is ExportFormat.TIFF:
            parts.append(f"TIFF {self.tiff_compression.currentText()}")
        elif fmt is ExportFormat.WEBP:
            mode = "lossless" if self.webp_mode.currentData() else "lossy"
            parts.append(f"WebP {mode}")
        return " · ".join(parts)

    def _commit_preferences(self, request: FigureExportRequest) -> bool:
        directory = str(request.path.parent.resolve())
        self._last_directory = directory
        settings = replace(
            self.options_panel.export_settings(),
            last_directory=directory,
        )
        self.options_panel.set_last_directory(directory)
        try:
            result = self._export_preferences.commit(settings)
        except Exception as exc:
            status_messages.show_warning(f"{_PREFERENCE_WARNING} {exc}")
            return False
        if commit_succeeded(result):
            return True
        detail = getattr(result, "error", None) or getattr(result, "warning", None)
        message = _PREFERENCE_WARNING if not detail else f"{_PREFERENCE_WARNING} {detail}"
        status_messages.show_warning(message)
        return False

    def _export(self) -> None:
        error = self._validation_message()
        if error:
            self.error_label.setText(error)
            self.export_button.setEnabled(False)
            return
        request = self._build_request()
        if request.path.exists():
            if not ask_confirmation(
                self,
                "Export Current Figure",
                f"Overwrite existing file?\n{request.path}",
                destructive=True,
            ):
                return
        try:
            self._export_callable(request)
        except Exception as exc:
            status_messages.show_error(str(exc))
            return
        if self._commit_preferences(request):
            status_messages.show_success(f"Figure exported: {request.path.name}")
        self.accept()
