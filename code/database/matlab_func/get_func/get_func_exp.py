import code.database.matlab_func.get_func as get_func


def get_func_exp(func_name: str):
    try:
        my_get_func = get_func.initialize()
    except Exception as e:
        print('Error initializing get_func package\n:{}'.format(e))
        exit(1)
    func_exp = ''
    func_coefs = []
    try:
        func_exp, func_coefs = my_get_func.get_func(func_name, nargout=2)
    except Exception as e:
        print('Error occurred during program execution\n:{}'.format(e))
    my_get_func.terminate()

    return func_exp, func_coefs
