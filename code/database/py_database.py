import numpy as np

from numpy import ndarray

databases = {}


class PyDatabase:
    def __init__(self):
        self.data = {}

    def add_data(self, index, data: ndarray):
        self.data[index] = data

