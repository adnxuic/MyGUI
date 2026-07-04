from code.database import matlab_adapter

def matlab_fitting(x, y, fit_type, fit_options=None):
    """
    Performs curve fitting on provided `x` and `y` data points using a specified fitting method.

    This function interfaces with the packaged MATLAB fitting runtime through the project adapter.
    Advanced settings are passed as a single fit_options dictionary and serialized to options_json
    for the MATLAB package.

    Parameters:
    - x (list or array-like): The independent variable data points for the fit.
    - y (list or array-like): The dependent variable data points for the fit.
    - fit_type (str): The type of fitting model to use. This should be a string compatible with the underlying fitting package.
    - fit_options (optional, dict or None): MATLAB fitoptions values such as Lower, Upper, StartPoint, and tolerances.

    Returns:
    A dictionary containing the fitted expression, coefficient details, confidence bounds, and goodness-of-fit values.

    Raises:
    - RuntimeError: If MATLAB or the packaged fitting runtime cannot be initialized or executed.

    Note:
    Ensure that the MATLAB engine is properly set up and accessible in the system environment where this function is used.
    """
    return matlab_adapter.fit_curve(x, y, fit_type, fit_options)
