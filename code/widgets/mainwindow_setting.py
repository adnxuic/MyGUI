import sys

from code.widgets.mainwindow_init import mainwindow_init_item

from Qt_core import *

class MainWindow_Setting(object):
    def setup_ui(self, parent):

        if not parent.objectName():
            parent.setObjectName("MainWindow")

        parent.resize(mainwindow_init_item["start_size"][0], mainwindow_init_item["start_size"][1])
        parent.setMinimumSize(QSize(mainwindow_init_item["min_size"][0], mainwindow_init_item["min_size"][1]))


