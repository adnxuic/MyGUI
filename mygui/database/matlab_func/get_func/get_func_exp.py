from mygui.database import matlab_adapter


def get_func_exp(func_name: str):
    return matlab_adapter.get_func_exp(func_name)
