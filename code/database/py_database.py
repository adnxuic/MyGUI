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
        self.data: Dict[int, List[Union[ndarray, Dict]]] = {}

    def update_data(self, index, data: ndarray):
        # 如果该列数据不存在，则创建
        if self.data.get(index) is None:
            self.data[index] = [data, {}]
        else:
            self.data[index][0] = data


