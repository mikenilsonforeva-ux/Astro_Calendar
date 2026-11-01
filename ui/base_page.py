"""Базовый класс страницы и общие виджеты."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QAbstractItemView, QFrame, QHeaderView, QLabel, QTableWidget,
                               QTableWidgetItem, QVBoxLayout, QWidget)

from ui.app_state import AppState


class BasePage(QWidget):
    """Страница рабочей области. Метод refresh() вызывается при показе страницы."""

    title = ""

    def __init__(self, state: AppState):
        super().__init__()
        self.state = state
        self._stale = True
        state.location_changed.connect(self.mark_stale)
        state.data_updated.connect(self.mark_stale)

    def mark_stale(self) -> None:
        self._stale = True
        if self.isVisible():
            self.on_show()

    def on_show(self) -> None:
        if self._stale:
            self._stale = False
            self.refresh()

    def refresh(self) -> None:  # переопределяется в страницах
        pass


def heading(text: str) -> QLabel:
    label = QLabel(text)
    font = label.font()
    font.setPointSize(font.pointSize() + 5)
    font.setBold(True)
    label.setFont(font)
    return label


def hint_label(text: str = "") -> QLabel:
    label = QLabel(text)
    label.setWordWrap(True)
    label.setTextInteractionFlags(Qt.TextSelectableByMouse)
    return label


def make_table(headers: list[str], stretch_last: bool = True) -> QTableWidget:
    table = QTableWidget(0, len(headers))
    table.setHorizontalHeaderLabels(headers)
    table.setEditTriggers(QAbstractItemView.NoEditTriggers)
    table.setSelectionBehavior(QAbstractItemView.SelectRows)
    table.setAlternatingRowColors(True)
    table.verticalHeader().setVisible(False)
    table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
    if stretch_last:
        table.horizontalHeader().setStretchLastSection(True)
    return table


def fill_table(table: QTableWidget, rows: list[list[str]]) -> None:
    table.setSortingEnabled(False)
    table.setRowCount(len(rows))
    for r, row in enumerate(rows):
        for c, value in enumerate(row):
            table.setItem(r, c, QTableWidgetItem(str(value)))
    table.resizeColumnsToContents()


def separator() -> QFrame:
    line = QFrame()
    line.setFrameShape(QFrame.HLine)
    line.setFrameShadow(QFrame.Sunken)
    return line


def message_page_layout(page: QWidget) -> QVBoxLayout:
    layout = QVBoxLayout(page)
    layout.setContentsMargins(18, 14, 18, 14)
    return layout
