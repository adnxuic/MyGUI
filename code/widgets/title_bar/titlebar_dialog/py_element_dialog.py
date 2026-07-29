"""Collect inputs for creating Figure text elements."""

from Qt_core import *

from matplotlib import font_manager

from code.widgets.figure_canvas.py_figure_window import PyFigureWindow

from code.widgets import qss_func
import os

current_path = os.path.dirname(os.path.abspath(__file__))
qss_path = os.path.join(current_path, "dialog_style.qss")


class PyTextDialog(QDialog):
    """Provide the py text dialog Qt widget."""

    def __init__(self, dialog_name=None, figure_window=None, parent=None):
        super().__init__(parent)
        self.setObjectName("text_dialog")
        qss_file = qss_func.qss_loader(qss_path)
        self.setStyleSheet(qss_file)

        self.setWindowTitle(dialog_name)
        self.setWindowIcon(QIcon("pictures/icons/element_images/Text.svg"))

        self.figure_window: PyFigureWindow = figure_window

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
        font_paths = font_manager.findSystemFonts()
        fonts = [font_manager.FontProperties(fname=path).get_name() for path in font_paths]
        font_list = sorted(set(fonts))

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

        self.font_input.setCurrentText('Times New Roman')
        self.layout.addWidget(self.font_input)

        # 选择输入文本的字体大小
        self.font_size_input = QSpinBox(self)
        self.font_size_input.setMinimum(1)
        self.font_size_input.setMaximum(100)
        self.font_size_input.setValue(20)
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
            if self.figure_window.current_canva.current_axes is None:
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


element_dialog_dict = {
    'Text': PyTextDialog,
}
