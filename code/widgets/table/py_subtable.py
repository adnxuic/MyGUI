'''
完成批量复制粘贴和删除 以及右键菜单添加数字
'''

import sys
from Qt_core import *


class MyTableWidget(QTableWidget):
    textChanged = Signal(str)  # 定义一个信号，用于发送字符串类型的数据

    def __init__(self, rows, columns, parent=None):
        super().__init__(rows, columns, parent)

        self.setMouseTracking(True)

        self.initializeShortcuts()  # 初始化快捷键
        self.initializeColumnHeaders(columns)  # 初始化列标题

        # self.textChanged = Signal(str)  # 定义一个信号，用于发送字符串类型的数据

        # 设置所有列的宽度和所有行的高度
        min_width, min_height = 100, 30
        for col in range(self.columnCount()):
            self.setColumnWidth(col, min_width)
        for row in range(self.rowCount()):
            self.setRowHeight(row, min_height)

        self.horizontalHeader().setContextMenuPolicy(Qt.CustomContextMenu)  # 设置自定义上下文菜单策略
        self.horizontalHeader().customContextMenuRequested.connect(self.headerContextMenu)  # 连接自定义上下文菜单信号

        self.setHorizontalScrollMode(QAbstractItemView.ScrollPerPixel)  # 水平滚动
        self.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)  # 垂直滚动
        self.setSelectionBehavior(QTableWidget.SelectItems)  # 选择单个单元格

        self.currentCellChanged.connect(self.check_need_more_cells)  # 连接当前单元格改变信号

    def check_need_more_cells(self, currentRow, currentColumn, previousRow, previousColumn):
        if currentRow == self.rowCount() - 1:
            self.insertRow(self.rowCount())
            self.setRowHeight(self.rowCount() - 1, 30)
        if currentColumn == self.columnCount() - 1:
            new_column_index = self.columnCount()
            self.insertColumn(new_column_index)
            self.setColumnWidth(new_column_index, 100)
            self.setHorizontalHeaderItem(new_column_index, QTableWidgetItem(f"x{new_column_index + 1}"))

    def headerContextMenu(self, pos):
        menu = QMenu()
        column = self.horizontalHeader().logicalIndexAt(pos)
        if column != -1:
            sort_asc_action = menu.addAction("Sort Ascending")
            sort_desc_action = menu.addAction("Sort Descending")
            add_numbers_action = menu.addAction("添加数字")

            action = menu.exec(self.horizontalHeader().mapToGlobal(pos))
            if action == sort_asc_action:
                self.sortItems(column, Qt.AscendingOrder)
            elif action == sort_desc_action:
                self.sortItems(column, Qt.DescendingOrder)
            elif action == add_numbers_action:
                self.addNumbersToColumn(column)

    def addNumbersToColumn(self, column):
        startNum, ok = QInputDialog.getInt(self, "输入起始数字", "起始数字:")
        if not ok:
            return
        step, ok = QInputDialog.getInt(self, "输入间隔", "间隔:")
        if not ok:
            return
        count, ok = QInputDialog.getInt(self, "输入个数", "个数:")
        if not ok:
            return

        for i in range(count):
            if self.rowCount() <= i:
                self.insertRow(self.rowCount())
            self.setItem(i, column, QTableWidgetItem(str(startNum + step * i)))

    def keyPressEvent(self, event):
        current_item = self.currentItem()
        if not current_item:
            self.setItem(self.currentRow(), self.currentColumn(), QTableWidgetItem(""))
            current_item = self.currentItem()
        if event.key() in (Qt.Key_Return, Qt.Key_Enter):
            self.editItem(current_item)
        elif event.key() == Qt.Key_Delete:
            self.deleteItems()
        else:
            super().keyPressEvent(event)

        if self.currentItem() and self.state() == QAbstractItemView.EditingState:
            editor = self.findChild(QLineEdit)
            if editor and not hasattr(editor, 'is_connected'):
                editor.textChanged.connect(self.handleTextChange)
                setattr(editor, 'is_connected', True)  # 设置属性，避免重复连接

    def handleTextChange(self, text):
        self.textChanged.emit(text)  # 当编辑器的文本变化时，发射信号

    def mouseDoubleClickEvent(self, event):
        pos = event.position().toPoint()
        index = self.indexAt(pos)
        if index.isValid():
            self.edit(index)
        super().mouseDoubleClickEvent(event)

    # 添加快捷键
    def initializeShortcuts(self):
        copyShortcut = QShortcut(QKeySequence.Copy, self)
        copyShortcut.activated.connect(self.copyItems)
        pasteShortcut = QShortcut(QKeySequence.Paste, self)
        pasteShortcut.activated.connect(self.pasteItems)
        deleteShortcut = QShortcut(QKeySequence.Delete, self)
        deleteShortcut.activated.connect(self.deleteItems)

    def initializeColumnHeaders(self, columns):
        headers = [f"x{i + 1}" for i in range(columns)]
        self.setHorizontalHeaderLabels(headers)

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
                    item = self.item(rows[0] + r, cols[0] + c)
                    if item:
                        table_contents += item.text()
            QApplication.clipboard().setText(table_contents)

    def pasteItems(self):
        clipboard = QApplication.clipboard().text()
        if clipboard:
            startPosition = self.currentRow(), self.currentColumn()
            rows = clipboard.split('\n')
            for i, row in enumerate(rows):
                columns = row.split('\t')
                for j, column in enumerate(columns):
                    rowPosition = startPosition[0] + i
                    colPosition = startPosition[1] + j
                    if rowPosition < self.rowCount() and colPosition < self.columnCount():
                        self.setItem(rowPosition, colPosition, QTableWidgetItem(column))
                    else:
                        if rowPosition >= self.rowCount():
                            self.insertRow(self.rowCount())
                        if colPosition >= self.columnCount():
                            self.insertColumn(self.columnCount())
                        self.setItem(rowPosition, colPosition, QTableWidgetItem(column))

    def deleteItems(self):
        selection = self.selectedIndexes()
        for index in selection:
            self.setItem(index.row(), index.column(), QTableWidgetItem(""))

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
        delete_action = menu.addAction("Delete")
        action = menu.exec(position)  # 显示菜单

        if action == delete_action:
            if self.count() > 1 and tab_index != self.count() - 1:  # 确保至少有一个标签页，且不是"+"标签
                response = QMessageBox.question(self, "Confirm Delete",
                                                "Are you sure you want to delete this sheet?",
                                                QMessageBox.Yes | QMessageBox.No)
                if response == QMessageBox.Yes:
                    self.removeTab(tab_index)

class PySubTable(QFrame):
    def __init__(self):
        super().__init__()

        self.setMouseTracking(True)

        # 使用自定义的QTabWidget
        self.tabWidget = SheetTabWidget()
        self.tabWidget.setTabPosition(QTabWidget.South)
        self.tabWidget.addTab(MyTableWidget(20, 5), "Sheet1")

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
        # 连接当前单元格改变信号
        self.currentSheet.textChanged.connect(self.updateFullContentDisplayManual)
        self.currentSheet.currentItemChanged.connect(self.updateFullContentDisplay)

        self.fullContentDisplay = QLineEdit()
        self.fullContentDisplay.setReadOnly(True)
        # # 连接当前单元格改变信号
        # self.tableWidget.currentItemChanged.connect(self.updateFullContentDisplay)
        # self.tableWidget.textChanged.connect(self.updateFullContentDisplayManual)

        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.fullContentDisplay)
        layout.addWidget(self.tabWidget)
        self.setLayout(layout)

    def updateCurrentSheet(self):
        # 更新当前标签页引用
        self.currentSheet = self.tabWidget.currentWidget()
        # 连接信号
        self.currentSheet.textChanged.connect(self.updateFullContentDisplayManual)
        self.currentSheet.currentItemChanged.connect(self.updateFullContentDisplay)

    # 更新全文显示
    def updateFullContentDisplay(self, current):
        # 如果当前单元格不为空，则显示当前单元格的文本
        if current and current.text().strip() != "":
            self.fullContentDisplay.setText(current.text())
        else:
            self.fullContentDisplay.clear()

    # 更新全文显示
    def updateFullContentDisplayManual(self, text):
        self.fullContentDisplay.setText(text)

    def add_new_sheet(self):
        # 添加新标签页
        index = self.tabWidget.count() - 1
        new_sheet_name = f"Sheet{index + 1}"
        self.tabWidget.insertTab(index, MyTableWidget(20, 5), new_sheet_name)
        self.tabWidget.setCurrentIndex(index)