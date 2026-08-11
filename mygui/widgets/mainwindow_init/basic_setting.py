"""Load the main-window stylesheet without unrelated import-time state."""

from mygui.resources import load_qss_resource


mainwindow_qss = load_qss_resource("mygui/widgets/mainwindow_init/style.qss")
