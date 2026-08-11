"""Host table and figure views in the right column."""

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QFrame, QPushButton, QVBoxLayout
from mygui.resources import icon_path, load_qss_resource


class PyRightColumn(QFrame):
    """Provide the py right column Qt widget."""

    def __init__(self, fig_control_layout = None):
        super().__init__()

        self.fig_control_layout = fig_control_layout

        self.setObjectName("right_column")
        qss_file = load_qss_resource("mygui/widgets/right_column/style.qss")
        self.setStyleSheet(qss_file)


        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(0)

        self.tex_button = QPushButton(QIcon(icon_path("tex.svg")), "")
        self.tex_button.setObjectName("tex_button")
        self.tex_button.setToolTip("Show or hide the TeX panel")
        self.tex_button.setAccessibleName("Toggle TeX panel")
        self.tex_button.setCheckable(True)
        self.tex_button.setChecked(False)
        self.tex_button.toggled.connect(self.tex_show)
        self.layout.addWidget(self.tex_button)

        self.matlab_button = QPushButton(QIcon(icon_path("matlab.svg")), "")
        self.matlab_button.setObjectName("matlab_button")
        self.matlab_button.setToolTip("Show or hide the MATLAB panel")
        self.matlab_button.setAccessibleName("Toggle MATLAB panel")
        self.matlab_button.setCheckable(True)
        self.matlab_button.setChecked(False)
        self.matlab_button.toggled.connect(self.matlab_show)
        self.layout.addWidget(self.matlab_button)

    def tex_show(self, checked):
        """Open the optional TeX integration settings."""

        if checked:
            if self.matlab_button.isChecked():
                self.matlab_button.setChecked(False)
            self.fig_control_layout.setCurrentIndex(1)
        else:
            self.fig_control_layout.setCurrentIndex(0)

    def matlab_show(self, checked):
        """Open the optional MATLAB integration settings."""

        if checked:
            if self.tex_button.isChecked():
                self.tex_button.setChecked(False)
            self.fig_control_layout.setCurrentIndex(2)
        else:
            self.fig_control_layout.setCurrentIndex(0)
