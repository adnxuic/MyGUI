from typing import Any, Callable, Dict, Iterable, List, Union

import numpy as np
from numpy import ndarray

databases: Dict[str, Dict[str, Any]] = {}


class PyDatabase:
    """
    一张表的数据
    每一列数据跟着一个字典，用于存储使用该列数据画图的线的属性
    """

    def __init__(self):
        self.data: Dict[str, List[Union[ndarray, Dict]]] = {}

    @staticmethod
    def notify_data_choices():
        try:
            from code.widgets.common_widget.min_widget.py_datachoice_widget import PyDataChoiceWidget
        except ImportError:
            return
        PyDataChoiceWidget.update_all_instances()

    @staticmethod
    def clear():
        databases.clear()
        PyDatabase.notify_data_choices()

    @staticmethod
    def register_table(table_name: str):
        databases.setdefault(table_name, {})
        PyDatabase.notify_data_choices()

    @staticmethod
    def unregister_table(table_name: str):
        databases.pop(table_name, None)
        PyDatabase.notify_data_choices()

    @staticmethod
    def register_sheet(table_name: str, sheet_name: str, database: "PyDatabase"):
        PyDatabase.register_table(table_name)
        databases[table_name][sheet_name] = database
        PyDatabase.notify_data_choices()

    @staticmethod
    def unregister_sheet(table_name: str, sheet_name: str):
        sheets = databases.get(table_name)
        if sheets is None:
            return
        sheets.pop(sheet_name, None)
        PyDatabase.notify_data_choices()

    @staticmethod
    def next_table_name(prefix: str = "Table") -> str:
        index = 1
        while f"{prefix}{index}" in databases:
            index += 1
        return f"{prefix}{index}"

    @staticmethod
    def next_sheet_name(table_name: str, prefix: str = "Sheet") -> str:
        index = 1
        sheets = databases.get(table_name, {})
        while f"{prefix}{index}" in sheets:
            index += 1
        return f"{prefix}{index}"

    @staticmethod
    def split_data_name(data_name: str) -> tuple[str, str, str]:
        try:
            table_name, sheet_name, column_name = data_name.split("/")
        except ValueError as exc:
            raise KeyError(f"Invalid data name: {data_name}") from exc
        return table_name, sheet_name, column_name

    @staticmethod
    def has_data(data_name: str) -> bool:
        try:
            table_name, sheet_name, column_name = PyDatabase.split_data_name(data_name)
            return column_name in databases[table_name][sheet_name].data
        except (KeyError, TypeError):
            return False

    @staticmethod
    def iter_data_names() -> Iterable[str]:
        for table_name, sheets in databases.items():
            for sheet_name, database in sheets.items():
                for column_name in database.data.keys():
                    yield f"{table_name}/{sheet_name}/{column_name}"

    def update_data(self, index: int, data: ndarray):
        # 如果该列数据不存在，则创建,且更新所有数据选择框
        if self.data.get(str(index)) is None:
            self.data[str(index)] = [data, {}]  # Dict[id: int, func: Any]
            PyDatabase.notify_data_choices()
        else:
            self.data[str(index)][0] = data
            # 更新数据后，需要更新所有使用该数据的图像
            for id_num, callback_map in list(self.data[str(index)][1].items()):
                for xy, func in list(callback_map.items()):
                    func(data)

        # print(self.data[index][0])

    # 提取数据
    @staticmethod
    def get_data(data_name: str) -> ndarray:
        """
        data_name: 数据名
        形式为：Table/Sheet/Column
        提取出表名，片名，列名
        """
        table_name, sheet_name, column_name = PyDatabase.split_data_name(data_name)
        return databases[table_name][sheet_name].data[column_name][0]

    # 数据连接到对应的映射
    @staticmethod
    def data_connect(data_name: str, id_num: int, xy: str, connection_func: Callable[[ndarray], Any]):
        table_name, sheet_name, column_name = PyDatabase.split_data_name(data_name)

        if databases[table_name][sheet_name].data[column_name][1].get(id_num) is None:
            databases[table_name][sheet_name].data[column_name][1][id_num] = {}

        databases[table_name][sheet_name].data[column_name][1][id_num][xy] = connection_func

    @staticmethod
    def remove_data_connection(data_name: str, id_num: int, xy: str | None = None):
        if not PyDatabase.has_data(data_name):
            return

        table_name, sheet_name, column_name = PyDatabase.split_data_name(data_name)
        callback_map = databases[table_name][sheet_name].data[column_name][1]
        if id_num not in callback_map:
            return

        if xy is None:
            callback_map.pop(id_num, None)
            return

        callback_map[id_num].pop(xy, None)
        if not callback_map[id_num]:
            callback_map.pop(id_num, None)

    # 改变数据连接的映射
    @staticmethod
    def change_data_connection(before_data_name: str, after_data_name: str, id_num: int, xy: str) -> bool:
        """

        """
        # 移除原来的连接
        if before_data_name == after_data_name:
            return PyDatabase.has_data(after_data_name)

        if not PyDatabase.has_data(before_data_name) or not PyDatabase.has_data(after_data_name):
            return False

        table_name, sheet_name, column_name = PyDatabase.split_data_name(before_data_name)
        old_callbacks = databases[table_name][sheet_name].data[column_name][1]
        if id_num not in old_callbacks or xy not in old_callbacks[id_num]:
            return False

        func = old_callbacks[id_num].pop(xy)
        if not old_callbacks[id_num]:
            old_callbacks.pop(id_num, None)

        # 添加新的连接
        table_name, sheet_name, column_name = PyDatabase.split_data_name(after_data_name)
        if databases[table_name][sheet_name].data[column_name][1].get(id_num) is None:
            databases[table_name][sheet_name].data[column_name][1][id_num] = {}

        databases[table_name][sheet_name].data[column_name][1][id_num][xy] = func
        return True

