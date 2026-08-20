"""Collect Controller-free inputs for creating Figure Elements."""

from dataclasses import dataclass

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QIcon
from PySide6.QtWidgets import (
    QComboBox,
    QCompleter,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QStyledItemDelegate,
    QVBoxLayout,
)
from mygui.resources import icon_path

from mygui.widgets.figure_canvas.py_figure_window import PyFigureWindow
from mygui.figuremodify.matplotlib_adapter import available_font_families
from mygui.figuremodify.style_base.creation_defaults import (
    resolve_component_creation_defaults,
)
from mygui import status_messages
from mygui.widgets.fig_control_window.component_editors import (
    ColorbarInput,
    InAxesInput,
)

from mygui.resources import load_qss_resource


class PyTextDialog(QDialog):
    """Provide the py text dialog Qt widget."""

    def __init__(self, dialog_name=None, figure_window=None, parent=None):
        super().__init__(parent)
        self.setObjectName("text_dialog")
        qss_file = load_qss_resource(
            "mygui/widgets/title_bar/titlebar_dialog/dialog_style.qss"
        )
        self.setStyleSheet(qss_file)

        self.setWindowTitle(dialog_name)
        self.setWindowIcon(QIcon(icon_path("element_images/Text.svg")))

        self.figure_window: PyFigureWindow = figure_window
        canvas = getattr(figure_window, "current_canva", None)
        self.creation_defaults = (
            canvas.component_creation_defaults()
            if canvas is not None
            else resolve_component_creation_defaults("default")
        )

        self.layout = QVBoxLayout()

        # 选择是全局还是局部选择框
        self.global_local_layout = QHBoxLayout()
        self.global_button = QRadioButton('全局')
        self.local_button = QRadioButton('局部')
        self.local_button.setChecked(True)
        self.global_local_layout.addWidget(self.global_button)
        self.global_local_layout.addWidget(self.local_button)
        self.layout.addLayout(self.global_local_layout)

        # 输入文本
        self.text_label = QLabel("Text:")
        self.text_edit = QLineEdit()
        self.layout.addWidget(self.text_label)
        self.layout.addWidget(self.text_edit)

        # 输入文本的位置, x,y为相对坐标，0-1之间
        self.position_input_layout = QHBoxLayout()
        self.x_input = QDoubleSpinBox()
        self.x_input.setMinimumWidth(100)
        self.x_input.setRange(-1, 2)
        self.x_input.setSingleStep(0.01)
        self.x_input.setValue(0.5)

        self.y_input = QDoubleSpinBox()
        self.y_input.setMinimumWidth(100)
        self.y_input.setRange(-1, 2)
        self.y_input.setSingleStep(0.01)
        self.y_input.setValue(0.5)

        self.position_input_layout.addWidget(QLabel('x:'))
        self.position_input_layout.addWidget(self.x_input)
        self.position_input_layout.addWidget(QLabel('y:'))
        self.position_input_layout.addWidget(self.y_input)
        self.layout.addLayout(self.position_input_layout)

        # 选择输入文本的字体
        self.layout.addWidget(QLabel('Choose a Font:'))

        # 获取所有系统字体及 Matplotlib 字体
        font_list = available_font_families()

        # 代理类，使得下拉菜单中的字体显示为对应字体
        class FontDelegate(QStyledItemDelegate):
            def paint(self, painter, option, index):
                option.font = QFont(index.data())
                super().paint(painter, option, index)

        # 下拉菜单和手动输入框
        self.font_input = QComboBox()
        self.font_input.setEditable(True)
        self.font_input.setItemDelegate(FontDelegate(self.font_input))

        # 设置自动补全
        completer = QCompleter(font_list)
        completer.setCaseSensitivity(Qt.CaseInsensitive)
        self.font_input.setCompleter(completer)

        for font in font_list:
            self.font_input.addItem(font)

        self.font_input.setCurrentText(
            self.creation_defaults.text.fontfamily
        )
        self.layout.addWidget(self.font_input)

        # 选择输入文本的字体大小
        self.font_size_input = QDoubleSpinBox(self)
        self.font_size_input.setRange(1.0, 1000.0)
        self.font_size_input.setDecimals(2)
        self.font_size_input.setSingleStep(0.5)
        self.font_size_input.setValue(
            self.creation_defaults.text.fontsize
        )
        self.layout.addWidget(QLabel('Font Size:'))
        self.layout.addWidget(self.font_size_input)

        # 确定和取消按钮
        self.ok_button = QPushButton("确定")
        self.cancel_button = QPushButton("取消")
        self.ok_button.clicked.connect(self.accept)
        self.cancel_button.clicked.connect(self.reject)
        self.button_layout = QHBoxLayout()
        self.button_layout.addStretch(1)
        self.button_layout.addWidget(self.ok_button)
        self.button_layout.addWidget(self.cancel_button)
        self.layout.addLayout(self.button_layout)

        self.setLayout(self.layout)

    def accept(self):
        # 如果current_canva为空，弹出警告
        """Validate the inputs and accept the dialog when they are usable."""

        if self.figure_window.current_canva is None:
            QMessageBox.warning(self, 'Warning', 'Please add an axes first!')
            return

        # 如果current_axes为空，弹出警告
        if self.local_button.isChecked():
            if not self.figure_window.current_canva.has_current_axes:
                QMessageBox.warning(self, 'Warning', 'Please select an axes first!')
                return
            self.figure_window.current_canva.add_text(text=self.text_edit.text(),
                                                      x=self.x_input.value(),
                                                      y=self.y_input.value(),
                                                      fontfamily=self.font_input.currentText(),
                                                      fontsize=self.font_size_input.value())
        else:
            self.figure_window.current_canva.add_global_text(text=self.text_edit.text(),
                                                             x=self.x_input.value(),
                                                             y=self.y_input.value(),
                                                             fontfamily=self.font_input.currentText(),
                                                             fontsize=self.font_size_input.value())
        super().accept()

    def reject(self):
        """Reject the dialog without applying its pending inputs."""

        super().reject()


class PyInAxesDialog(QDialog):
    """Create a Zoom or embedded-image child Axes Element."""

    ICON_PATH = icon_path("element_images/in_axes.svg")

    def __init__(self, dialog_name=None, figure_window=None, parent=None):
        super().__init__(parent)
        self.setObjectName("in_axes_dialog")
        self.setWindowTitle(dialog_name or "in_axes")
        self.setWindowIcon(QIcon(self.ICON_PATH))
        self.figure_window: PyFigureWindow = figure_window
        canvas = getattr(figure_window, "current_canva", None)
        defaults = (
            canvas.component_creation_defaults()
            if canvas is not None
            else resolve_component_creation_defaults("default")
        )
        color_library = getattr(figure_window, "color_library", None)
        if color_library is None:
            raise ValueError("The application ColorLibrary is unavailable.")

        layout = QVBoxLayout(self)
        self.input = InAxesInput(
            color_library=color_library,
            defaults=defaults.in_axes,
            parent=self,
        )
        layout.addWidget(self.input)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel,
            parent=self,
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def accept(self):
        """Validate and create one inset without closing on failure."""

        canvas = getattr(self.figure_window, "current_canva", None)
        if canvas is None or not canvas.has_current_axes:
            QMessageBox.warning(
                self,
                "No Axes selected",
                "Select an Axes before creating an in_axes Element.",
            )
            return
        try:
            canvas.add_in_axes(self.input.spec())
        except Exception as exc:
            QMessageBox.warning(self, "Could not create in_axes", str(exc))
            return
        super().accept()


class PyColorbarDialog(QDialog):
    """Collect Controller-free source and placement values for a Colorbar."""

    ICON_PATH = icon_path("element_images/colorbar.svg")

    def __init__(self, dialog_name=None, figure_window=None, parent=None):
        super().__init__(parent)
        self.setObjectName("colorbar_dialog")
        self.setWindowTitle(dialog_name or "Colorbar")
        self.setWindowIcon(QIcon(self.ICON_PATH))
        self.figure_window: PyFigureWindow = figure_window
        canvas = getattr(figure_window, "current_canva", None)
        sources = canvas.eligible_colorbar_sources() if canvas is not None else ()
        layout = QVBoxLayout(self)
        self.input = ColorbarInput(sources, parent=self)
        layout.addWidget(self.input)
        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel,
            parent=self,
        )
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)
        if not self.input.has_source():
            self.buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(False)
            status_messages.show_warning(
                "No scalar-mapped Scatter without a Colorbar is available "
                "under the selected Axes."
            )

    def accept(self):
        """Create the Colorbar without closing when validation fails."""

        canvas = getattr(self.figure_window, "current_canva", None)
        source_id = self.input.source_component_id()
        if canvas is None or not canvas.has_current_axes:
            status_messages.show_warning(
                "Select an Axes before creating a Colorbar."
            )
            return
        if source_id is None:
            status_messages.show_warning(
                "No eligible scalar-mapped Scatter source is available."
            )
            return
        try:
            canvas.add_colorbar(source_id, self.input.properties())
        except Exception as exc:
            status_messages.show_error(str(exc))
            return
        super().accept()


@dataclass(frozen=True, slots=True)
class ElementActionSpec:
    """Declare one Elements action and its resolved icon."""

    dialog_type: type[QDialog]
    icon_path: str


element_action_specs = {
    "Text": ElementActionSpec(
        PyTextDialog,
        icon_path("element_images/Text.svg"),
    ),
    "in_axes": ElementActionSpec(
        PyInAxesDialog,
        PyInAxesDialog.ICON_PATH,
    ),
    "Colorbar": ElementActionSpec(
        PyColorbarDialog,
        PyColorbarDialog.ICON_PATH,
    ),
}
