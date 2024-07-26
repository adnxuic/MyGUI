from Qt_core import *
from code.figuremodify.py_text_modify import PyTextModify

class PyTextModWidget(QFrame):
    def __init__(self, text_modify: PyTextModify):
        super().__init__()

        self.text_modify = text_modify

        self.layout = QVBoxLayout()

        self.setLayout(self.layout)