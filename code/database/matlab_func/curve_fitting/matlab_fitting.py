import code.database.matlab_func.curve_fitting as curve_fitting
import matlab


def matlab_fitting(x, y, fit_type, isdefault,
                   up_limit=None, low_limit=None, start_point=None):
    exp = ''
    try:
        fitting = curve_fitting.initialize()
    except Exception as e:
        print('Error initializing fittest package\n:{}'.format(e))
        exit(1)
    try:
        x_data = matlab.double(x, size=(len(x), 1))
        y_data = matlab.double(y, size=(len(y), 1))
        exp, coeff_name, coeff_value, gof = fitting.curve_fitting(x_data, y_data, fit_type, isdefault, nargout=4)

        # 将公式中的变量名替换为实际的数值
        for name, value in zip(coeff_name, coeff_value[0]):
            exp = exp.replace(name, str(value))

        # 将^替换为**
        exp = exp.replace('^', '**')

    except Exception as e:
        print('Error occurred during program execution\n:{}'.format(e))

    fitting.terminate()
    return exp
