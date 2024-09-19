from typing import Dict, List, Union, Any

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

    def update_data(self, index: int, data: ndarray):
        # 如果该列数据不存在，则创建,且更新所有数据选择框
        if self.data.get(str(index)) is None:
            self.data[str(index)] = [data, {}]  # Dict[id: int, func: Any]
            from code.widgets.common_widget.min_widget.py_datachoice_widget import PyDataChoiceWidget
            PyDataChoiceWidget.update_all_instances()
        else:
            self.data[str(index)][0] = data
            # 更新数据后，需要更新所有使用该数据的图像
            for id_num, dict in self.data[str(index)][1].items():
                for xy, func in dict.items():
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
        table_name, sheet_name, column_name = data_name.split('/')
        return databases[table_name][sheet_name].data[column_name][0]

    # 数据连接到对应的映射
    @staticmethod
    def data_connect(data_name: str, id_num: int, xy: str, connection_func: Any):
        table_name, sheet_name, column_name = data_name.split('/')

        if databases[table_name][sheet_name].data[column_name][1].get(id_num) is None:
            databases[table_name][sheet_name].data[column_name][1][id_num] = {}

        databases[table_name][sheet_name].data[column_name][1][id_num][xy] = connection_func

    # 改变数据连接的映射
    @staticmethod
    def change_data_connection(before_data_name: str, after_data_name: str, id_num: int, xy: str):
        """

        """
        # 移除原来的连接
        table_name, sheet_name, column_name = before_data_name.split('/')
        func = databases[table_name][sheet_name].data[column_name][1][id_num].pop(xy)

        # 添加新的连接
        table_name, sheet_name, column_name = after_data_name.split('/')
        if databases[table_name][sheet_name].data[column_name][1].get(id_num) is None:
            databases[table_name][sheet_name].data[column_name][1][id_num] = {}

        databases[table_name][sheet_name].data[column_name][1][id_num][xy] = func

