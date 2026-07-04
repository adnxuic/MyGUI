from Qt_core import *
from code.widgets import qss_func

import os
current_path = os.path.dirname(os.path.abspath(__file__))
qss_path = os.path.join(current_path, "style.qss")

class PyBottomBar(QFrame):
    def __init__(self):
        super().__init__()

        self.setObjectName("bottom_bar")
        qss_file = qss_func.qss_loader(qss_path)
        self.setStyleSheet(qss_file)

        self.layout = QHBoxLayout(self)
        self.layout.setContentsMargins(10, 0, 10, 0)
        self.layout.setSpacing(0)

        self.message_label = QLabel("")
        self.message_label.setObjectName("bottom_bar_message")
        self.message_label.setTextFormat(Qt.PlainText)
        self.message_label.setAlignment(Qt.AlignVCenter | Qt.AlignLeft)
        self.message_label.setWordWrap(False)
        self.message_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.layout.addWidget(self.message_label)

    def show_message(self, message, level="info"):
        self.message_label.setText(message)
        self.message_label.setToolTip(message)
        if level == "error":
            self.message_label.setStyleSheet("color: #ff4d4f;")
        elif level == "success":
            self.message_label.setStyleSheet("color: #22c55e;")
        else:
            self.message_label.setStyleSheet("color: #f2f2f2;")

    def show_error(self, message):
        self.show_message(message, "error")

    def show_success(self, message):
        self.show_message(message, "success")

    def clear_message(self):
        self.show_message("", "info")
