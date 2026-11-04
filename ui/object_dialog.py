"""Окно с подробной характеристикой объекта, выбранного на карте неба."""
from __future__ import annotations

import html

from PySide6.QtWidgets import QDialog, QHBoxLayout, QPushButton, QTextBrowser, QVBoxLayout


class ObjectDialog(QDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Характеристика объекта")
        self.resize(560, 680)
        layout = QVBoxLayout(self)
        self.view = QTextBrowser()
        self.view.setOpenExternalLinks(True)
        layout.addWidget(self.view, 1)
        row = QHBoxLayout()
        row.addStretch(1)
        close = QPushButton("Закрыть")
        close.clicked.connect(self.close)
        row.addWidget(close)
        layout.addLayout(row)

    def show_loading(self, name: str) -> None:
        self.setWindowTitle(name)
        self.view.setHtml(f"<h2>{html.escape(name)}</h2><p>Расчёт характеристик…</p>")
        self._present()

    def show_html(self, title: str, body: str) -> None:
        self.setWindowTitle(title)
        self.view.setHtml(body)
        self._present()

    def show_error(self, name: str, message: str) -> None:
        self.view.setHtml(f"<h2>{html.escape(name)}</h2>"
                          f"<p style='color:#d9534f'>{html.escape(message)}</p>")
        self._present()

    def _present(self) -> None:
        if not self.isVisible():
            self.show()
        self.raise_()
        self.activateWindow()
