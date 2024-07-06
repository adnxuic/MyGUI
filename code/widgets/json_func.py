import json

def deserialize(path):
    # 读取json文件
    items = {}
    with open(path, "r", encoding='utf-8') as reader:
        settings = json.loads(reader.read())
        items = settings

    return items
