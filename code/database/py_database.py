import numpy as np

databases = {}


class PyDatabase:
    def __init__(self):
        self.num_data = {}
        self.str_data = {}

    def add_num_data(self, name, data):
        self.num_data[name] = data

    def add_str_data(self, name, data):
        self.str_data[name] = data

    @staticmethod
    def add_database(name, subname, database):
        databases[name][subname] = database
