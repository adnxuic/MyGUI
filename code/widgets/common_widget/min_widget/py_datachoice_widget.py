from Qt_core import *
import weakref


from code.database.py_database import PyDatabase

class PyDataChoiceWidget(QFrame):
    instances = weakref.WeakSet()

    def __new__(cls, *args, **kwargs):
        instance = super().__new__(cls, *args, **kwargs)
        cls.instances.add(instance)
        return instance
    def __init__(self):
        super().__init__()

        self.layout = QVBoxLayout()
        self.x_layout = QHBoxLayout()
        self.y_layout = QHBoxLayout()

        self.x_data_input = QComboBox(self)
        self.y_data_input = QComboBox(self)
        
        self.x_layout.addWidget(QLabel('X Data:'))
        self.x_layout.addWidget(self.x_data_input)
        self.y_layout.addWidget(QLabel('Y Data:'))
        self.y_layout.addWidget(self.y_data_input)

        self.layout.addLayout(self.x_layout)
        self.layout.addLayout(self.y_layout)

        self.setLayout(self.layout)

        self.update_data()

    def update_data(self):
        # 记录当前的数据
        current_x_data = self.x_data_input.currentText()
        current_y_data = self.y_data_input.currentText()

        # 暂时阻塞信号
        self.x_data_input.blockSignals(True)
        self.y_data_input.blockSignals(True)

        data_names = list(PyDatabase.iter_data_names())
        self.x_data_input.clear()
        self.y_data_input.clear()
        self.x_data_input.addItems(data_names)
        self.y_data_input.addItems(data_names)

        # 恢复信号
        self.x_data_input.blockSignals(False)
        self.y_data_input.blockSignals(False)

        # 恢复到当前数据
        if current_x_data in data_names:
            self.x_data_input.setCurrentText(current_x_data)
        elif data_names:
            self.x_data_input.setCurrentIndex(0)

        if current_y_data in data_names:
            self.y_data_input.setCurrentText(current_y_data)
        elif data_names:
            self.y_data_input.setCurrentIndex(0)

    @classmethod
    def update_all_instances(cls):
        for instance in list(cls.instances):
            try:
                instance.update_data()
            except RuntimeError:
                cls.instances.discard(instance)

    def get_x_data(self):
        return self.x_data_input.currentText()

    def get_y_data(self):
        return self.y_data_input.currentText()

    def set_x_data(self, data_name: str):
        self.x_data_input.setCurrentText(data_name)

    def set_y_data(self, data_name: str):
        self.y_data_input.setCurrentText(data_name)

    def text_connect(self, x_func, y_func):
        self.x_data_input.currentTextChanged.connect(x_func)
        self.y_data_input.currentTextChanged.connect(y_func)

    
