"""
完成批量复制粘贴和删除 以及右键菜单添加数字
"""

import sys
from typing import cast

from Qt_core import *
import numpy as np

from code.database.py_database import databases
from code.database.py_database import PyDatabase


class TableModel(QAbstractTableModel):
    def __init__(self, database: PyDatabase):
        super().__init__()

        self.database = database

        data = [["" for _ in range(5)] for _ in range(20)]
        self._data = np.array(data, dtype=object)

    def data(self, index, role=Qt.DisplayRole):
        if role == Qt.DisplayRole:
            value = self._data[index.row(), index.column()]
            return str(value) if value is not None else ""

    def rowCount(self, index=QModelIndex()):
        return self._data.shape[0]

    def columnCount(self, index=QModelIndex()):
        return self._data.shape[1]

    def flags(self, index):
        return super().flags(index) | Qt.ItemIsEditable

    def setData(self, index, value, role=Qt.EditRole):
        if role == Qt.EditRole:
            self._data[index.row(), index.column()] = value
            self.dataChanged.emit(index, index)
            # print('setData:', value)
            # print(self._data)
            return True
        return False

    def addRow(self):
        self.beginInsertRows(QModelIndex(), self.rowCount(), self.rowCount())
        new_row = np.array([[""] * self._data.shape[1]], dtype=object)
        self._data = np.vstack([self._data, new_row])
        self.endInsertRows()

    def addColumn(self):
        self.beginInsertColumns(QModelIndex(), self.columnCount(), self.columnCount())
        new_col = np.array([[""] * self._data.shape[0]], dtype=object).T
        self._data = np.hstack([self._data, new_col])
        self.endInsertColumns()

    def clearData(self, indexes):
        for index in indexes:
            if index.isValid():
                self.setData(index, "", Qt.EditRole)

    def Individual_sort(self, column, order):
        self.layoutAboutToBeChanged.emit()
        # 提取列数据
        col_data = self._data[:, column]
        # 分离出非空值和空值
        non_null_data = col_data[col_data != '']
        null_data = col_data[col_data == '']

        try:
            non_null_data = non_null_data.astype(float)
            non_null_data = np.sort(non_null_data, kind='mergesort')
        except ValueError:
            non_null_data = np.sort(non_null_data, kind='mergesort')

        if order == Qt.DescendingOrder:
            non_null_data = non_null_data[::-1]

        # 重建整列数据，将非空数据排序后与空数据结合
        sorted_data = np.concatenate((non_null_data, null_data))
        self._data[:, column] = sorted_data
        self.layoutChanged.emit()

    def sort(self, column, order=Qt.AscendingOrder):
        self.layoutAboutToBeChanged.emit()
        # 提取列数据
        col_data = self._data[:, column]
        # 分离出非空值和对应的索引
        valid_indices = np.where(col_data != '')[0]
        valid_data = col_data[valid_indices]

        null_data_indices = np.where(col_data == '')[0]

        try:
            valid_data = valid_data.astype(float)
            sorted_indices = np.argsort(valid_data, kind='mergesort')
        except ValueError:
            sorted_indices = np.argsort(valid_data, kind='mergesort')

        if order == Qt.DescendingOrder:
            sorted_indices = sorted_indices[::-1]

        # 合并索引数组获取最终排序的完整行索引
        final_indices = np.concatenate((valid_indices[sorted_indices], null_data_indices))

        # 重排整个数组
        self._data = self._data[final_indices]
        self.layoutChanged.emit()

    # 有关database的操作
    def save_data_to_database(self):
        print(self._data)
        # 提取每一列的数据
        for i in range(self.columnCount()):
            col_data = self._data[:, i]
            # 检查是否有数据
            if col_data.any():
                # 分离出非空值和空值
                non_null_data = col_data[col_data != '']
                # 转换
                try:
                    non_null_data = non_null_data.astype(float)
                except ValueError:
                    non_null_data = non_null_data.astype(str)
                # 保存到数据库
                self.database.update_data(i + 1, non_null_data)


class TableView(QTableView):
    def __init__(self, database: PyDatabase):
        super().__init__()

        model = TableModel(database)
        self.setModel(model)
        self.model = cast(TableModel, self.model())

        self.setSelectionBehavior(QAbstractItemView.SelectItems)
        self.selectionModel().currentChanged.connect(self.check_need_more_cells)
        self.initActions()

        # 添加表头右键菜单
        self.horizontalHeader().setContextMenuPolicy(Qt.CustomContextMenu)
        self.horizontalHeader().customContextMenuRequested.connect(self.headerContextMenu)

    def check_need_more_cells(self, current, previous):
        if current.row() == self.model.rowCount() - 1:
            self.model.addRow()
        if current.column() == self.model.columnCount() - 1:
            self.model.addColumn()

    def initActions(self):
        copyAction = QAction("Copy", self)
        copyAction.setShortcut("Ctrl+C")
        copyAction.triggered.connect(self.copyItems)

        pasteAction = QAction("Paste", self)
        pasteAction.setShortcut("Ctrl+V")
        pasteAction.triggered.connect(self.pasteItems)

        deleteAction = QAction("Delete", self)
        deleteAction.setShortcut("Delete")
        deleteAction.triggered.connect(self.deleteItems)

        saveAction = QAction("Save", self)
        saveAction.setShortcut("Ctrl+S")
        saveAction.triggered.connect(self.model.save_data_to_database)

        self.addAction(copyAction)
        self.addAction(pasteAction)
        self.addAction(deleteAction)
        self.addAction(saveAction)

    def copyItems(self):
        selection = self.selectedIndexes()
        if selection:
            rows = sorted(index.row() for index in selection)
            cols = sorted(index.column() for index in selection)
            rowcount = rows[-1] - rows[0] + 1
            colcount = cols[-1] - cols[0] + 1
            table_contents = ''
            for r in range(rowcount):
                if r > 0:
                    table_contents += '\n'
                for c in range(colcount):
                    if c > 0:
                        table_contents += '\t'
                    index = self.model.index(rows[0] + r, cols[0] + c)
                    item = self.model.data(index, Qt.DisplayRole)
                    if item:
                        table_contents += item
            QGuiApplication.clipboard().setText(table_contents)

    def pasteItems(self):
        clipboard = QGuiApplication.clipboard().text()
        if clipboard:
            startPosition = self.currentIndex()
            rows = clipboard.split('\n')
            for i, row in enumerate(rows):
                columns = row.split('\t')
                for j, column in enumerate(columns):
                    rowPosition = startPosition.row() + i
                    colPosition = startPosition.column() + j
                    if rowPosition >= self.model.rowCount():
                        self.model.addRow()
                    if colPosition >= self.model.columnCount():
                        self.model.addColumn()
                    index = self.model.index(rowPosition, colPosition)
                    self.model.setData(index, column, Qt.EditRole)

    def deleteItems(self):
        selection = self.selectedIndexes()
        self.model.clearData(selection)

    def headerContextMenu(self, pos):
        menu = QMenu()

        Individual_sortAscAction = menu.addAction("单独升序")
        Individual_sortDescAction = menu.addAction("单独逆序")
        sortAscAction = menu.addAction("升序")
        sortDescAction = menu.addAction("逆序")

        action = menu.exec(self.horizontalHeader().mapToGlobal(pos))
        column = self.horizontalHeader().logicalIndexAt(pos)
        if action == Individual_sortAscAction:
            self.model.Individual_sort(column, Qt.AscendingOrder)
        elif action == Individual_sortDescAction:
            self.model.Individual_sort(column, Qt.DescendingOrder)
        elif action == sortAscAction:
            self.model.sort(column, Qt.AscendingOrder)
        elif action == sortDescAction:
            self.model.sort(column, Qt.DescendingOrder)


# 自定义的QTabWidget
class SheetTabWidget(QTabWidget):
    def __init__(self, parent=None):
        super().__init__(parent)

        self.setMouseTracking(True)

    def mousePressEvent(self, event):
        if event.button() == Qt.RightButton:
            pos = event.position().toPoint()
            pos.setY(pos.y() - self.tabBar().y())
            clicked_tab_index = self.tabBar().tabAt(pos)
            if clicked_tab_index != -1:
                self.show_context_menu(event.globalPosition().toPoint(), clicked_tab_index)
        super().mousePressEvent(event)

    def show_context_menu(self, position, tab_index):
        menu = QMenu()

        save_to_database_action = menu.addAction("Save to Database")
        delete_action = menu.addAction("Delete")
        action = menu.exec(position)  # 显示菜单

        if action == delete_action:
            if self.count() > 1 and tab_index != self.count() - 1:  # 确保至少有一个标签页，且不是"+"标签
                response = QMessageBox.question(self, "Confirm Delete",
                                                "Are you sure you want to delete this sheet?",
                                                QMessageBox.Yes | QMessageBox.No)
                if response == QMessageBox.Yes:
                    self.removeTab(tab_index)

        elif action == save_to_database_action:
            # 提取前如果当前单元格有未保存的数据，先保存
            current_widget = cast(TableView, self.currentWidget())
            model = cast(TableModel, current_widget.model)
            #
            # editor = current_widget.focusWidget()
            # current_index = current_widget.currentIndex()  # 获取当前编辑的索引
            # value = editor.text()  # 从 QLineEdit 获取文本
            # model.setData(current_index, value, Qt.EditRole)  # 提交到模型
            # current_widget.update(current_index)  # 更新视图
            # current_index = current_widget.currentIndex()
            # # 退出编辑状态
            # current_widget.closePersistentEditor(current_index)
            #
            #
            # next_index = model.index(current_index.row(), current_index.column() + 1)
            # current_widget.setCurrentIndex(next_index)
            # current_widget.edit(next_index)

            model.save_data_to_database()


class PySubTable(QFrame):
    def __init__(self, table_name: str, pydatabase: PyDatabase):
        super().__init__()

        self.table_name = table_name

        self.setMouseTracking(True)

        databases[self.table_name]['Sheet1'] = pydatabase

        # 使用自定义的QTabWidget
        self.tabWidget = SheetTabWidget()
        self.tabWidget.setTabPosition(QTabWidget.South)
        self.tabWidget.addTab(TableView(databases[table_name]['Sheet1']), "Sheet1")

        # 创建"+"按钮，并添加为一个标签页，但设为不可选择
        self.plusButton = QPushButton("+")
        self.plusButton.clicked.connect(self.add_new_sheet)
        self.tabWidget.addTab(QWidget(), "")
        self.tabWidget.setTabEnabled(self.tabWidget.count() - 1, False)  # 设为不可选择
        self.tabWidget.tabBar().setTabButton(self.tabWidget.count() - 1, QTabBar.ButtonPosition.RightSide,
                                             self.plusButton)

        # 连接标签页切换信号
        self.currentSheet = self.tabWidget.currentWidget()
        self.tabWidget.currentChanged.connect(self.updateCurrentSheet)

        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.tabWidget)
        self.setLayout(layout)

    def updateCurrentSheet(self):
        pass

    def add_new_sheet(self):
        # 添加新标签页
        index = self.tabWidget.count() - 1
        new_sheet_name = f"Sheet{index + 1}"
        databases[self.table_name][new_sheet_name] = PyDatabase()
        self.tabWidget.insertTab(index, TableView(databases[self.table_name][new_sheet_name]), new_sheet_name)
        self.tabWidget.setCurrentIndex(index)
