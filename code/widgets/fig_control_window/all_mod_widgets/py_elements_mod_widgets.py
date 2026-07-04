from Qt_core import *

from code.widgets import qss_func
from code import status_messages
from code.figuremodify.py_text_modify import PyTextModify, TextRenderError

from matplotlib import font_manager

import os

current_path = os.path.dirname(os.path.abspath(__file__))
qss_path = os.path.join(current_path, "element_mod_style.qss")


class PyTextModWidget(QFrame):
    def __init__(self, text_modify: PyTextModify):
        super().__init__()

        self.text_modify = text_modify

        self.setObjectName("text_mod_widget")
        qss_file = qss_func.qss_loader(qss_path)
        self.setStyleSheet(qss_file)

        self.layout = QVBoxLayout()
        self.layout.setSpacing(10)
        self.layout.setContentsMargins(0, 0, 0, 0)

        # 字体选择
        self.font_layout = QHBoxLayout()
        self.font_layout.setSpacing(0)
        self.font_layout.addWidget(QLabel('Font:'))

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
        self.font_input.setFixedWidth(160)
        self.font_input.setEditable(True)
        self.font_input.setItemDelegate(FontDelegate(self.font_input))

        # 设置自动补全
        completer = QCompleter(font_list)
        completer.setCaseSensitivity(Qt.CaseInsensitive)
        self.font_input.setCompleter(completer)

        for font in font_list:
            self.font_input.addItem(font)

        current_font_family = self.text_modify.text.get_fontfamily()
        if isinstance(current_font_family, (list, tuple)):
            current_font_family = current_font_family[0] if current_font_family else 'Times New Roman'
        self.font_input.setCurrentText(current_font_family or 'Times New Roman')
        self.font_input.currentTextChanged.connect(self.text_modify.set_text_font)
        self.font_layout.addWidget(self.font_input)
        self.layout.addLayout(self.font_layout)

        # 文本的字体大小
        self.font_size_layout = QHBoxLayout()
        self.font_size_layout.setSpacing(0)
        self.font_size_input = QSpinBox(self)
        self.font_size_input.setFixedWidth(80)
        self.font_size_input.setMinimum(1)
        self.font_size_input.setMaximum(100)
        self.font_size_input.setValue(int(round(self.text_modify.text.get_fontsize())))
        self.font_size_input.valueChanged.connect(self.text_modify.set_text_fontsize)
        font_size_label = QLabel("Size:")
        self.font_size_layout.addWidget(font_size_label)
        self.font_size_layout.addWidget(self.font_size_input)
        self.layout.addLayout(self.font_size_layout)

        # 文本内容
        self.text_content = QPlainTextEdit()
        self.text_content.setPlaceholderText("Text content")
        self.text_content.setPlainText(self.text_modify.text.get_text())
        self.text_content.textChanged.connect(self.set_text_content)
        self.layout.addWidget(self.text_content)

        # 选择文本位置
        self.text_xy_layout = QHBoxLayout()

        self.text_x_pos = QDoubleSpinBox()
        self.text_x_pos.setRange(-1, 1)
        self.text_x_pos.setSingleStep(0.01)
        self.text_x_pos.setValue(self.text_modify.text.get_position()[0])

        self.text_y_pos = QDoubleSpinBox()
        self.text_y_pos.setRange(-1, 1)
        self.text_y_pos.setSingleStep(0.01)
        self.text_y_pos.setValue(self.text_modify.text.get_position()[1])

        self.text_x_pos.textChanged.connect(self.set_xy_position)
        self.text_y_pos.textChanged.connect(self.set_xy_position)

        x_label = QLabel("X:")
        y_label = QLabel("Y:")
        x_label.setFixedWidth(20)
        y_label.setFixedWidth(20)
        self.text_xy_layout.addWidget(x_label)
        self.text_xy_layout.addWidget(self.text_x_pos)
        self.text_xy_layout.addWidget(y_label)
        self.text_xy_layout.addWidget(self.text_y_pos)

        self.layout.addLayout(self.text_xy_layout)

        # 添加弹性空间
        self.layout.addStretch()

        self.setLayout(self.layout)

    def delete_object(self):
        self.text_modify.delete_object()

    def set_text_content(self):
        content = self.text_content.toPlainText()
        try:
            self.text_modify.set_text_content(content)
        except TextRenderError as exc:
            status_messages.show_error(str(exc))
        else:
            if getattr(self.text_modify, "last_render_warning", None) is None:
                status_messages.clear_message()

    def set_xy_position(self):
        x = self.text_x_pos.value()
        y = self.text_y_pos.value()

        self.text_modify.set_xy_position(x, y)
