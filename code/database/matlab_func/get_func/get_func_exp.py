import importlib


def get_func_exp(func_name: str):
    my_get_func = None
    try:
        get_func = importlib.import_module('code.database.matlab_func.get_func')
        my_get_func = get_func.initialize()
    except Exception as exc:
        raise RuntimeError(f"Error initializing get_func package: {exc}") from exc

    try:
        func_exp, func_coefs = my_get_func.get_func(func_name, nargout=2)
    except Exception as exc:
        raise RuntimeError(f"Error occurred during program execution: {exc}") from exc
    finally:
        if my_get_func is not None:
            my_get_func.terminate()

    return func_exp, func_coefs
