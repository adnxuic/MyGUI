from code.widgets import json_func
import sys
import os
# 本文件的绝对路径的根目录
current_path = os.path.dirname(os.path.abspath(__file__))
json_path = os.path.join(current_path, "setting.json")

# 从json文件中反序列化数据
mainwindow_init_item = json_func.deserialize(json_path)

