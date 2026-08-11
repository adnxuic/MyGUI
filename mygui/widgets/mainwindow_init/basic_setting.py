"""Load the main-window stylesheet without unrelated import-time state."""

from pathlib import Path

from mygui.widgets import qss_func


qss_path = Path(__file__).with_name("style.qss")
mainwindow_qss = qss_func.qss_loader(str(qss_path))
