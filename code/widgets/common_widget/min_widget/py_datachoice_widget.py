from Qt_core import *


from code.database.py_database import databases

class PyDataChoiceWidget(QFrame):
    instances = []

    def __new__(cls, *args, **kwargs):
        instance = super().__new__(cls, *args, **kwargs)
        cls.instances.append(instance)
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

        self.x_data_input.clear()
        self.y_data_input.clear()
        for key1, value1 in databases.items():
            for key2, value2 in value1.items():
                for key3 in value2.data.keys():
                    item = f"{key1}/{key2}/{key3}"
                    self.x_data_input.addItem(item)
                    self.y_data_input.addItem(item)

        # 恢复信号
        self.x_data_input.blockSignals(False)
        self.y_data_input.blockSignals(False)

        # 恢复到当前数据
        self.x_data_input.setCurrentText(current_x_data)
        self.y_data_input.setCurrentText(current_y_data)

    @classmethod
    def update_all_instances(cls):
        for instance in cls.instances:
            instance.update_data()

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

    
