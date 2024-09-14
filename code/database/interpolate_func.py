from scipy.interpolate import CubicSpline, make_interp_spline, splrep, splev, lagrange
import numpy as np

def CubicSpline_interpolate(x: np.ndarray, y: np.ndarray):

    cspl = CubicSpline(x, y)

    x_min = x.min()
    x_max = x.max()
    x_new = np.linspace(x_min, x_max, 1000)
    y_new = cspl(x_new)

    return x_new, y_new

def b_spline_interpolate(x: np.ndarray, y: np.ndarray, k=3):

    bspl = make_interp_spline(x, y, k=k)

    x_min = x.min()
    x_max = x.max()
    x_new = np.linspace(x_min, x_max, 1000)
    y_new = bspl(x_new)

    return x_new, y_new

def b_spline_splrep_interpolate(x: np.ndarray, y: np.ndarray, k=3):

    tck = splrep(x, y, k=k)

    x_min = x.min()
    x_max = x.max()
    x_new = np.linspace(x_min, x_max, 1000)
    y_new = splev(x_new, tck)

    return x_new, y_new

interpolate_dict = {
    "三次样条插值": CubicSpline_interpolate,
    "B样条插值": b_spline_splrep_interpolate
}
