from Qt_core import *

from code.widgets.figure_canvas.py_figure_window import PyFigureWindow

from code.widgets import qss_func
import os

current_path = os.path.dirname(os.path.abspath(__file__))
qss_path = os.path.join(current_path, "dialog_style.qss")


class PyStyleDialog(QDialog):
    def __init__(self, parent=None, dialog_name=None, figure_window=None, fig_control_window=None):
        super().__init__()
        self.style = dialog_name

        self.setObjectName("style_dialog")
        qss_file = qss_func.qss_loader(qss_path)
        self.setStyleSheet(qss_file)

        self.setWindowTitle(dialog_name)
        self.setWindowIcon(QIcon("pictures/icons/style.svg"))

        self.layout = QVBoxLayout()

        self.figure_control_window = fig_control_window
        self.figure_window = figure_window

        # 传入Figure创建函数的数据
        self.wight_label = QLabel("宽度")
        self.height_label = QLabel("高度")
        self.dpi_label = QLabel("DPI")
        self.canva_name_label = QLabel("图表名称")

        self.width_line = QLineEdit()
        self.height_line = QLineEdit()
        self.dpi_line = QLineEdit()
        self.canva_name_line = QLineEdit()

        # 设置默认值
        self.width_line.setText("6.4")
        self.height_line.setText("4.8")
        self.dpi_line.setText("100")
        self.canva_name_line.setText(dialog_name)

        self.layout.addWidget(self.wight_label)
        self.layout.addWidget(self.width_line)
        self.layout.addWidget(self.height_label)
        self.layout.addWidget(self.height_line)
        self.layout.addWidget(self.dpi_label)
        self.layout.addWidget(self.dpi_line)
        self.layout.addWidget(self.canva_name_label)
        self.layout.addWidget(self.canva_name_line)

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
        width = float(self.width_line.text())
        height = float(self.height_line.text())
        dpi = int(self.dpi_line.text())
        canva_name = self.canva_name_line.text()

        self.figure_window.add_figure(width=width, height=height, dpi=dpi,
                                      style=self.style, canva_name=canva_name)

        super().accept()

    def reject(self):
        super().reject()


class PyLayoutDialog(QDialog):
    def __init__(self, parent=None, dialog_name=None, figure_window=None, fig_control_window=None, layout=None):
        super().__init__()
        self.setObjectName("layout_dialog")
        qss_file = qss_func.qss_loader(qss_path)
        self.setStyleSheet(qss_file)

        self.setWindowTitle(dialog_name)
        self.setWindowIcon(QIcon("pictures/icons/layout.svg"))

        self.figure_window: PyFigureWindow = figure_window
        self.fig_control_window = fig_control_window

        self.layout_value = layout

        self.layout = QVBoxLayout()

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
        self.figure_window.current_canva.add_axes(nrows=self.layout_value[0], ncols=self.layout_value[1])
        super().accept()

    def reject(self):
        super().reject()


class PyChartDialog(QDialog):
    def __init__(self, parent=None, dialog_name=None):
        super().__init__()
        self.setObjectName("chart_dialog")
        qss_file = qss_func.qss_loader(qss_path)
        self.setStyleSheet(qss_file)

        self.setWindowTitle(dialog_name)
        self.setWindowIcon(QIcon("pictures/icons/chart.svg"))
