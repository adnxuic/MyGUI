from Qt_core import *

from code.widgets.qss_func import qss_loader
from code.widgets.fig_control_window.all_mod_widgets.py_chart_mod_widgets import PyFitMatlabModWidget
from code.widgets.common_widget.min_widget.py_datachoice_widget import PyDataChoiceWidget

from code.database.py_database import PyDatabase
from code.database import matlab_adapter


import numpy as np

import itertools
import time
from typing import Optional
import weakref
import os

current_path = os.path.dirname(os.path.abspath(__file__))
qss_path = os.path.join(current_path, "style.qss")
_matlab_task_counter = itertools.count(1)
_active_matlab_tasks = {}


class MatlabTaskWorker(QObject):
    finished = Signal(object)
    failed = Signal(str)

    def __init__(self, task_id, task_name, func, *args, **kwargs):
        super().__init__()
        self.task_id = task_id
        self.task_name = task_name
        self.func = func
        self.args = args
        self.kwargs = kwargs

    @Slot()
    def run(self):
        logger = matlab_adapter.matlab_logger()
        logger.debug("MATLAB GUI task worker started task_id=%s task=%s", self.task_id, self.task_name)
        try:
            result = self.func(*self.args, **self.kwargs)
        except Exception as exc:
            logger.debug(
                "MATLAB GUI task worker failed task_id=%s task=%s error=%s",
                self.task_id,
                self.task_name,
                exc,
            )
            self.failed.emit(str(exc))
        else:
            logger.debug("MATLAB GUI task worker succeeded task_id=%s task=%s", self.task_id, self.task_name)
            self.finished.emit(result)


def start_matlab_task(owner, func, on_finished, on_failed, *args, **kwargs):
    task_id = next(_matlab_task_counter)
    task_name = getattr(func, "__name__", func.__class__.__name__)
    logger = matlab_adapter.matlab_logger()
    logger.debug(
        "MATLAB GUI task queued task_id=%s task=%s owner=%s",
        task_id,
        task_name,
        owner.__class__.__name__,
    )
    thread = QThread()
    worker = MatlabTaskWorker(task_id, task_name, func, *args, **kwargs)
    worker.moveToThread(thread)
    owner_ref = weakref.ref(owner)
    owner_alive = {"value": True}
    started_at = time.monotonic()

    def mark_owner_destroyed(*_args):
        owner_alive["value"] = False
        logger.debug("MATLAB GUI task owner destroyed task_id=%s task=%s", task_id, task_name)

    owner.destroyed.connect(mark_owner_destroyed)

    task_record = (task_id, thread, worker)
    _active_matlab_tasks[task_id] = task_record

    def should_deliver(result_type):
        if not owner_alive["value"] or owner_ref() is None:
            logger.debug(
                "MATLAB GUI task %s ignored after owner destruction task_id=%s task=%s",
                result_type,
                task_id,
                task_name,
            )
            return False
        return True

    def deliver_finished(result):
        elapsed = time.monotonic() - started_at
        logger.debug(
            "MATLAB GUI task finished task_id=%s task=%s elapsed=%.3fs",
            task_id,
            task_name,
            elapsed,
        )
        if should_deliver("success"):
            try:
                on_finished(result)
            except Exception:
                logger.exception(
                    "MATLAB GUI task success callback failed task_id=%s task=%s",
                    task_id,
                    task_name,
                )

    def deliver_failed(message):
        elapsed = time.monotonic() - started_at
        logger.debug(
            "MATLAB GUI task failed task_id=%s task=%s elapsed=%.3fs message=%s",
            task_id,
            task_name,
            elapsed,
            message,
        )
        if should_deliver("failure"):
            try:
                on_failed(message)
            except Exception:
                logger.exception(
                    "MATLAB GUI task failure callback failed task_id=%s task=%s",
                    task_id,
                    task_name,
                )

    def cleanup():
        _active_matlab_tasks.pop(task_id, None)
        logger.debug("MATLAB GUI task cleaned up task_id=%s task=%s", task_id, task_name)
        worker.deleteLater()
        thread.deleteLater()

    thread.started.connect(worker.run)
    worker.finished.connect(deliver_finished)
    worker.failed.connect(deliver_failed)
    worker.finished.connect(thread.quit)
    worker.failed.connect(thread.quit)
    thread.finished.connect(cleanup)
    thread.start()
    return thread, worker


class PyMatlabWindow(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)

        self.setMouseTracking(True)
        self.setObjectName("matlab_window")

        qss_path = os.path.join(current_path, "style.qss")
        self.setStyleSheet(qss_loader(qss_path))

        self.connect_widget: Optional[PyFitMatlabModWidget] = None
        self._connect_request_id = 0
        self._fit_request_id = 0

        self.layout = QVBoxLayout()
        self.layout.setSpacing(0)
        self.layout.setContentsMargins(0, 0, 0, 0)

        # 检测是否能连接matlab
        self.matlab_isconnect = QPushButton("Connect Matlab")
        self.matlab_isconnect.setFixedWidth(150)
        self.matlab_isconnect.setFixedHeight(30)
        self.matlab_isconnect.clicked.connect(self.matlab_connect_click)
        self.layout.addWidget(self.matlab_isconnect)

        self.setLayout(self.layout)

    def matlab_connect_click(self):
        self._connect_request_id += 1
        request_id = self._connect_request_id
        started_at = time.monotonic()
        matlab_adapter.matlab_logger().info("MATLAB connect request started request_id=%s", request_id)
        self.matlab_isconnect.setEnabled(False)
        self.matlab_isconnect.setText("Connecting...")
        start_matlab_task(
            self,
            matlab_adapter.ensure_matlab_available_isolated,
            lambda status, rid=request_id, started=started_at: self._matlab_connect_succeeded(rid, started, status),
            lambda message, rid=request_id, started=started_at: self._matlab_connect_failed(rid, started, message),
        )

    def _matlab_connect_succeeded(self, request_id, started_at, _status):
        if request_id != self._connect_request_id:
            matlab_adapter.matlab_logger().debug(
                "MATLAB stale connect success ignored request_id=%s current_request_id=%s",
                request_id,
                self._connect_request_id,
            )
            return
        elapsed = time.monotonic() - started_at
        matlab_adapter.matlab_logger().info(
            "MATLAB connect request succeeded request_id=%s elapsed=%.3fs",
            request_id,
            elapsed,
        )
        matlab_adapter.set_matlab_enabled(True)
        self.init()

    def _matlab_connect_failed(self, request_id, started_at, message):
        if request_id != self._connect_request_id:
            matlab_adapter.matlab_logger().debug(
                "MATLAB stale connect failure ignored request_id=%s current_request_id=%s",
                request_id,
                self._connect_request_id,
            )
            return
        elapsed = time.monotonic() - started_at
        matlab_adapter.matlab_logger().warning(
            "MATLAB connect request failed request_id=%s elapsed=%.3fs message=%s",
            request_id,
            elapsed,
            message,
        )
        self.reset_to_connect_button()
        QMessageBox.warning(self, "Connect Matlab", message)

    def reset_to_connect_button(self):
        matlab_adapter.set_matlab_enabled(False)
        while self.layout.count():
            item = self.layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()

        self.connect_widget = None
        self.matlab_isconnect = QPushButton("Connect Matlab")
        self.matlab_isconnect.setFixedWidth(150)
        self.matlab_isconnect.setFixedHeight(30)
        self.matlab_isconnect.clicked.connect(self.matlab_connect_click)
        self.layout.addWidget(self.matlab_isconnect)

    def init(self):
        # 删掉原来的按钮
        self.layout.itemAt(self.layout.count() - 1).widget().setParent(None)

        # 数据选择
        self.data_choice_widget = PyDataChoiceWidget()
        self.layout.addWidget(self.data_choice_widget)

        # 拟合类型
        self.fit_type = QGroupBox("Fit Type")
        self.fit_type_layout = QVBoxLayout()
        self.fit_type.setLayout(self.fit_type_layout)

        # 选择拟合类型
        self.fit_type_input = QComboBox()
        self.fit_type_input.setFixedWidth(150)
        self.fit_type_input.addItems(matlab_adapter.FIT_TYPES.keys())

        # 连接不同的布局
        self.fit_type_input.currentTextChanged.connect(self.fit_type_change)
        self.fit_type_layout.addWidget(self.fit_type_input)
        self.layout.addWidget(self.fit_type)

        # 默认布局为poly
        self.fit_type_window = PyFitWindow()
        self.layout.addWidget(self.fit_type_window)

        # 启动拟合按钮
        self.fit_button = QPushButton("Fit")
        self.fit_button.setFixedWidth(150)
        self.fit_button.setFixedHeight(30)
        self.fit_button.clicked.connect(self.fit_curve)
        self.layout.addWidget(self.fit_button)

    def set_connect_widget(self, connect_widget: PyFitMatlabModWidget):
        self.connect_widget = connect_widget

    def fit_type_change(self, text):
        matlab_adapter.matlab_logger().debug("MATLAB fit type changed fit_type=%s", text)
        try:
            new_fit_type_window = PyFitWindow(fit_type_name=text)
        except Exception as exc:
            matlab_adapter.matlab_logger().warning(
                "MATLAB fit option initialization failed fit_type=%s error=%s",
                text,
                exc,
            )
            QMessageBox.warning(self, "Matlab Fit", str(exc))
            return
        # 删除旧的 fit_type_window
        self.layout.removeWidget(self.fit_type_window)
        self.fit_type_window.deleteLater()  # 确保旧的窗口被正确删除

        # 更新为新的 fit_type_window
        self.fit_type_window = new_fit_type_window
        self.layout.insertWidget(self.layout.count() - 1, self.fit_type_window)  # 插入到倒数第二个位置

    def fit_curve(self):
        if self.connect_widget is None:
            matlab_adapter.matlab_logger().warning("MATLAB fit requested without a selected fitting curve")
            QMessageBox.warning(self, "Matlab Fit", "Please select a Matlab fit curve first.")
            return

        try:
            x_name = self.data_choice_widget.get_x_data()
            y_name = self.data_choice_widget.get_y_data()
            x_data = PyDatabase.get_data(x_name)
            y_data = PyDatabase.get_data(y_name)
        except KeyError as exc:
            matlab_adapter.matlab_logger().warning("MATLAB fit data lookup failed error=%s", exc)
            QMessageBox.warning(self, "Matlab Fit", str(exc))
            return

        if len(x_data) == 0 or len(y_data) == 0:
            matlab_adapter.matlab_logger().warning(
                "MATLAB fit data validation failed x_len=%s y_len=%s reason=empty",
                len(x_data),
                len(y_data),
            )
            QMessageBox.warning(self, "Matlab Fit", "X Data and Y Data must not be empty.")
            return

        if len(x_data) != len(y_data):
            matlab_adapter.matlab_logger().warning(
                "MATLAB fit data validation failed x_len=%s y_len=%s reason=length mismatch",
                len(x_data),
                len(y_data),
            )
            QMessageBox.warning(self, "Matlab Fit", "X Data and Y Data must have the same length.")
            return

        x_max = max(x_data)
        x_min = min(x_data)

        try:
            fit_type_order, isdefault, up_limit, down_limit, start_point = self.fit_type_window.fit_parameters()
        except ValueError as exc:
            matlab_adapter.matlab_logger().warning("MATLAB fit parameter validation failed error=%s", exc)
            QMessageBox.warning(self, "Matlab Fit", str(exc))
            return

        self._fit_request_id += 1
        request_id = self._fit_request_id
        started_at = time.monotonic()
        matlab_adapter.matlab_logger().info(
            "MATLAB fit request started request_id=%s fit_type=%s x_data=%s y_data=%s x_len=%s y_len=%s",
            request_id,
            fit_type_order,
            x_name,
            y_name,
            len(x_data),
            len(y_data),
        )
        self.fit_button.setEnabled(False)
        self.fit_button.setText("Fitting...")
        x_values = [float(value) for value in x_data]
        y_values = [float(value) for value in y_data]
        start_matlab_task(
            self,
            matlab_adapter.fit_curve_isolated,
            lambda result, rid=request_id, started=started_at, xmin=x_min, xmax=x_max: self._fit_succeeded(
                rid,
                started,
                result,
                xmin,
                xmax,
            ),
            lambda message, rid=request_id, started=started_at: self._fit_failed(rid, started, message),
            x_values,
            y_values,
            fit_type_order,
            isdefault,
            up_limit,
            down_limit,
            start_point,
        )

    def _restore_fit_button(self):
        if hasattr(self, "fit_button"):
            self.fit_button.setEnabled(True)
            self.fit_button.setText("Fit")

    def _fit_succeeded(self, request_id, started_at, result, x_min, x_max):
        if request_id != self._fit_request_id:
            matlab_adapter.matlab_logger().debug(
                "MATLAB stale fit success ignored request_id=%s current_request_id=%s",
                request_id,
                self._fit_request_id,
            )
            return
        self._restore_fit_button()
        value_exp, show_exp = result
        elapsed = time.monotonic() - started_at
        matlab_adapter.matlab_logger().info(
            "MATLAB fit request succeeded request_id=%s elapsed=%.3fs",
            request_id,
            elapsed,
        )
        if self.connect_widget is not None:
            self.connect_widget.update_curve(value_exp, show_exp, x_min, x_max)

    def _fit_failed(self, request_id, started_at, message):
        if request_id != self._fit_request_id:
            matlab_adapter.matlab_logger().debug(
                "MATLAB stale fit failure ignored request_id=%s current_request_id=%s",
                request_id,
                self._fit_request_id,
            )
            return
        self._restore_fit_button()
        elapsed = time.monotonic() - started_at
        matlab_adapter.matlab_logger().warning(
            "MATLAB fit request failed request_id=%s elapsed=%.3fs message=%s",
            request_id,
            elapsed,
            message,
        )
        QMessageBox.warning(self, "Matlab Fit", message)


class PyFitWindow(QFrame):
    def __init__(self, parent=None, fit_type_name='poly'):
        super().__init__(parent)
        self.setMouseTracking(True)
        # self.setObjectName("poly_fit_window")
        #
        # qss_path = os.path.join(current_path, "style.qss")
        # self.setStyleSheet(qss_loader(qss_path))

        self.connect_widget: Optional[PyFitMatlabModWidget] = None

        self.layout = QVBoxLayout()

        self.fit_type = fit_type_name
        self._expression_request_id = 0

        # 拟合选项
        self.fit_option = QGroupBox("Fit Option")

        self.fit_option_layout = QVBoxLayout()
        self.fit_option_layout.setSpacing(0)
        self.fit_option_layout.setContentsMargins(0, 0, 0, 0)
        self.fit_option.setLayout(self.fit_option_layout)

        # 阶数
        self.order_layout = QHBoxLayout()
        self.order_input = QComboBox()
        items_list = matlab_adapter.FIT_TYPES[fit_type_name]
        self.order_input.addItems(items_list)
        self.order_layout.addWidget(QLabel("Order:"))
        self.order_layout.addWidget(self.order_input)

        # 获取函数表达式和系数
        self.func_exp = ""
        self.func_coefs = []
        # 函数表达式
        self.expression_input = QPlainTextEdit()
        # 设置默认值和不可编辑
        self.expression_input.setPlainText("Loading MATLAB expression...")
        self.expression_input.setReadOnly(True)

        # 连接不同的表达式
        self.order_input.currentTextChanged.connect(self.expression_change)

        self.fit_option_layout.addLayout(self.order_layout)
        self.fit_option_layout.addWidget(QLabel("Expression:"))
        self.fit_option_layout.addWidget(self.expression_input)

        # 高级选项
        self.advanced_option = QGroupBox("Advanced Option")
        self.advanced_option_layout = QVBoxLayout()
        self.advanced_option.setLayout(self.advanced_option_layout)
        # 设置是否显示高级选项，默认不显示
        self.advanced_option.setCheckable(True)
        self.advanced_option.setChecked(False)

        # 系数的上下限
        self.coeff_up_limit = []
        self.coeff_down_limit = []

        self.coefficient_table = QTableWidget()

        if fit_type_name == 'poly' or fit_type_name == 'log':
            self.coefficient_table.setColumnCount(3)
            self.coefficient_table.setHorizontalHeaderLabels(['系数', '上限', '下限'])
        else:
            self.start_point = []
            self.coefficient_table.setColumnCount(4)
            self.coefficient_table.setHorizontalHeaderLabels(['系数', '上限', '下限', '起点'])

        # 设置系数名称，且不可编辑
        self.coefficient_table.setRowCount(len(self.func_coefs))
        for i, coef in enumerate(self.func_coefs):
            self.coefficient_table.setItem(i, 0, QTableWidgetItem(coef))
            self.coefficient_table.item(i, 0).setFlags(Qt.ItemIsEnabled)

        # 上下限设置为正负无穷, 起点设置为[0,1]随机数
        for i in range(len(self.func_coefs)):
            self.coefficient_table.setItem(i, 1, QTableWidgetItem('inf'))
            self.coefficient_table.setItem(i, 2, QTableWidgetItem('-inf'))

            if fit_type_name != 'poly' and fit_type_name != 'log':
                num = np.random.rand(1)
                # 展示前4位
                self.coefficient_table.setItem(i, 3, QTableWidgetItem(str(num[0])[:4]))

        self.advanced_option_layout.addWidget(self.coefficient_table)

        self.layout.addWidget(self.fit_option)
        self.layout.addWidget(self.advanced_option)
        self.setLayout(self.layout)
        self.load_expression(self.order_input.currentText())


    def load_expression(self, text):
        self._expression_request_id += 1
        request_id = self._expression_request_id
        started_at = time.monotonic()
        matlab_adapter.matlab_logger().info(
            "MATLAB expression request started request_id=%s func_name=%s",
            request_id,
            text,
        )
        self.order_input.setEnabled(False)
        self.expression_input.setPlainText("Loading MATLAB expression...")
        self.coefficient_table.setRowCount(0)
        start_matlab_task(
            self,
            matlab_adapter.get_func_exp_isolated,
            lambda result, rid=request_id, started=started_at: self._expression_loaded(rid, started, result),
            lambda message, rid=request_id, started=started_at: self._expression_failed(rid, started, message),
            text,
        )

    def _expression_loaded(self, request_id, started_at, result):
        if request_id != self._expression_request_id:
            matlab_adapter.matlab_logger().debug(
                "MATLAB stale expression success ignored request_id=%s current_request_id=%s",
                request_id,
                self._expression_request_id,
            )
            return
        self.order_input.setEnabled(True)
        self.func_exp, self.func_coefs = result
        self.expression_input.setPlainText(self.func_exp)
        self._set_coefficients(self.func_coefs)
        elapsed = time.monotonic() - started_at
        matlab_adapter.matlab_logger().info(
            "MATLAB expression request succeeded request_id=%s elapsed=%.3fs coefficient_count=%s",
            request_id,
            elapsed,
            len(self.func_coefs),
        )

    def _expression_failed(self, request_id, started_at, message):
        if request_id != self._expression_request_id:
            matlab_adapter.matlab_logger().debug(
                "MATLAB stale expression failure ignored request_id=%s current_request_id=%s",
                request_id,
                self._expression_request_id,
            )
            return
        self.order_input.setEnabled(True)
        if not self.func_exp:
            self.expression_input.setPlainText("MATLAB expression unavailable")
            self.coefficient_table.setRowCount(0)
        else:
            self.expression_input.setPlainText(self.func_exp)
            self._set_coefficients(self.func_coefs)
        elapsed = time.monotonic() - started_at
        matlab_adapter.matlab_logger().warning(
            "MATLAB expression request failed request_id=%s elapsed=%.3fs message=%s",
            request_id,
            elapsed,
            message,
        )
        QMessageBox.warning(self, "Matlab Fit", message)

    def _set_coefficients(self, coefficients):
        self.coefficient_table.setRowCount(len(coefficients))
        for i, coef in enumerate(coefficients):
            self.coefficient_table.setItem(i, 0, QTableWidgetItem(coef))
            self.coefficient_table.item(i, 0).setFlags(Qt.ItemIsEnabled)
        for i in range(len(coefficients)):
            self.coefficient_table.setItem(i, 1, QTableWidgetItem('inf'))
            self.coefficient_table.setItem(i, 2, QTableWidgetItem('-inf'))

            if self.fit_type != 'poly' and self.fit_type != 'log':
                num = np.random.rand(1)
                self.coefficient_table.setItem(i, 3, QTableWidgetItem(str(num[0])[:4]))

    def expression_change(self, text):
        self.load_expression(text)

    # 获得上下限
    def get_coef_limit(self):
        # 清空上下限
        self.coeff_up_limit.clear()
        self.coeff_down_limit.clear()
        if hasattr(self, "start_point"):
            self.start_point.clear()

        for i in range(self.coefficient_table.rowCount()):
            up = self.coefficient_table.item(i, 1).text()
            down = self.coefficient_table.item(i, 2).text()
            self.coeff_up_limit.append(float(up))
            self.coeff_down_limit.append(float(down))

        if self.fit_type != 'poly' and self.fit_type != 'log':
            for i in range(self.coefficient_table.rowCount()):
                start = self.coefficient_table.item(i, 3).text()
                self.start_point.append(float(start))

    def fit_parameters(self):
        fit_type_order = self.order_input.currentText()
        if not fit_type_order:
            raise ValueError("Please select a Matlab fit type first.")

        if not self.advanced_option.isChecked():
            return fit_type_order, True, None, None, None

        self.get_coef_limit()
        start_point = list(getattr(self, "start_point", [])) or None
        return fit_type_order, False, list(self.coeff_up_limit), list(self.coeff_down_limit), start_point

    def fit_curve(self, x, y):
        '''
        拟合曲线
        :param x:
        :param y:
        :return: exp的matlab表达式
        '''

        if self.advanced_option.isChecked():
            isdefault = False
            self.get_coef_limit()
        else:
            isdefault = True

        # if self.fit_type != 'poly' and self.fit_type != 'log':
        #     print(self.start_point)

        fit_type_order = self.order_input.currentText()

        value_exp, show_exp = matlab_adapter.fit_curve_isolated(
            x,
            y,
            fit_type_order,
            isdefault,
            self.coeff_up_limit if not isdefault else None,
            self.coeff_down_limit if not isdefault else None,
            self.start_point if not isdefault and hasattr(self, "start_point") else None,
        )

        return value_exp, show_exp







