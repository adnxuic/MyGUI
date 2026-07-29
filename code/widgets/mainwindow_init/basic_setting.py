"""Apply basic startup settings to the Qt application."""

from code.widgets import json_func, qss_func
import sys
import os
# 本文件的绝对路径的根目录
current_path = os.path.dirname(os.path.abspath(__file__))
json_path = os.path.join(current_path, "setting.json")

# 从json文件中反序列化数据
mainwindow_init_item = json_func.deserialize(json_path)

qss_path = os.path.join(current_path, "style.qss")

# 定义样式
mainwindow_qss = qss_func.qss_loader(qss_path)
