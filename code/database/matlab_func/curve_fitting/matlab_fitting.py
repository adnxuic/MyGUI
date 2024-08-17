import code.database.matlab_func.curve_fitting as curve_fitting
import matlab


def matlab_fitting(x, y, fit_type, isdefault,
                   up_limit=None, low_limit=None, start_point=None):
    exp = ''
    value_exp = ''
    show_exp = ''
    try:
        fitting = curve_fitting.initialize()
    except Exception as e:
        print('Error initializing fittest package\n:{}'.format(e))
        exit(1)
    try:
        x_data = matlab.double(x, size=(len(x), 1))
        y_data = matlab.double(y, size=(len(y), 1))
        exp, coeff_name, coeff_value, gof = fitting.curve_fitting(x_data, y_data, fit_type, isdefault, nargout=4)

        value_exp = exp
        show_exp = exp

        # 将公式中的变量名替换为实际的数值
        for name, value in zip(coeff_name, coeff_value[0]):
            value_exp = value_exp.replace(name, str(value))

        # 将coeff_value[0]的值保留两位小数
        for i in range(len(coeff_value[0])):
            coeff_value[0][i] = round(coeff_value[0][i], 2)

        # 展示用的公式只保留前2位小数
        for name, value in zip(coeff_name, coeff_value[0]):
            show_exp = show_exp.replace(name, str(value))

        # 将^替换为**
        value_exp = value_exp.replace('^', '**')
        show_exp = show_exp.replace('^', '**')

    except Exception as e:
        print('Error occurred during program execution\n:{}'.format(e))

    fitting.terminate()
    return value_exp, show_exp
