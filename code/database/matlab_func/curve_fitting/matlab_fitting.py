from code.database import matlab_adapter

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
    - RuntimeError: If MATLAB or the packaged fitting runtime cannot be initialized or executed.

    Note:
    Ensure that the MATLAB engine is properly set up and accessible in the system environment where this function is used.
    """
    return matlab_adapter.fit_curve(x, y, fit_type, isdefault, up_limit, low_limit, start_point)
