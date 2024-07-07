from Qt_core import *
from code.widgets.title_bar.py_title_button import SelectButton

class PySelectorBar(QWidget):
    def __init__(self):
        super().__init__()
        self.expanded = False  # 用于追踪组件是否已扩展
        self.initUI()

    def initUI(self):
        self.gridLayout = QGridLayout(self)

        # 初始化前5个按钮，最后一个为下拉按钮
        for i in range(4):
            button = QPushButton(f"Button {i + 1}", self)
            self.gridLayout.addWidget(button, 0, i)

        # 下拉/收缩按钮
        self.toggleBtn = QPushButton("Dropdown", self)
        self.toggleBtn.clicked.connect(self.toggleWidget)
        self.gridLayout.addWidget(self.toggleBtn, 0, 4)

        self.setLayout(self.gridLayout)

    def toggleWidget(self):
        if not self.expanded:
            # 扩展为5x5
            for i in range(1, 5):  # 新增四行
                for j in range(5):  # 每行五个按钮
                    button = QPushButton(f"Button {i * 5 + j + 1}", self)
                    self.gridLayout.addWidget(button, i, j)
            self.toggleBtn.setText("Collapse")
            self.expanded = True

        else:
            # 收缩回1x5
            for i in range(1, 5):  # 移除四行
                for j in range(5):
                    item = self.gridLayout.itemAtPosition(i, j)
                    if item:
                        widget = item.widget()
                        self.gridLayout.removeWidget(widget)
                        widget.deleteLater()
            self.toggleBtn.setText("Dropdown")
            self.expanded = False
        self.adjustSize()  # 调整窗口大小以适应新的布局
