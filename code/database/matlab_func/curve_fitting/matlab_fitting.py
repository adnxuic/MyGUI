import code.database.matlab_func.curve_fitting as curve_fitting
import matlab
print('matlab')

def matlab_fitting(x, y, fit_type, isdefault,
                   up_limit=None, low_limit=None, start_point=None):
    """
    Performs curve fitting on provided `x` and `y` data points using a specified fitting method.

    This function interfaces with a MATLAB engine to apply the curve fitting algorithm, handling the initialization,
    execution, and termination of the MATLAB session internally. It supports custom upper and lower limits for the fit,
    as well as a starting point for the optimization process.

    Parameters:
    - x (list or array-like): The independent variable data points for the fit.
    - y (list or array-like): The dependent variable data points for the fit.
    - fit_type (str): The type of fitting model to use. This should be a string compatible with the underlying fitting package.
    - isdefault (bool): A flag indicating whether default settings should be used for the fit.
    - up_limit (optional, list or None): Upper limit constraints for the fitted parameters. Defaults to None.
    - low_limit (optional, list or None): Lower limit constraints for the fitted parameters. Defaults to None.
    - start_point (optional, list or None): Initial guess for the fitted parameters. Defaults to None.

    Returns:
    A tuple containing:
    - value_exp (str): The fitted equation with actual numerical values substituted for variables, formatted for Python evaluation.
    - show_exp (str): A formatted version of the fitted equation with coefficients rounded to two decimal places, suitable for display purposes.

    Raises:
    - SystemExit: If there's an error initializing the fitting package or during the execution of the fitting process.

    Note:
    Ensure that the MATLAB engine is properly set up and accessible in the system environment where this function is used.
    """
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
        print(exp)
        print(coeff_name)
        print(coeff_value[0])
        print(gof)

        # 将公式中的变量名替换为实际的数值
        for name, value in zip(coeff_name, coeff_value[0]):
            value_exp = value_exp.replace(name, str(value))

        # # 将coeff_value[0]的值保留两位小数
        # for i in range(len(coeff_value[0])):
        #     coeff_value[0][i] = round(coeff_value[0][i], 2)
        #
        # # 展示用的公式只保留前2位小数
        for name, value in zip(coeff_name, coeff_value[0]):
            show_exp = show_exp.replace(name, str(value))

        # 将^替换为**
        value_exp = value_exp.replace('^', '**')
        show_exp = show_exp.replace('^', '**')

    except Exception as e:
        print('Error occurred during program execution\n:{}'.format(e))

    fitting.terminate()
    return value_exp, show_exp
