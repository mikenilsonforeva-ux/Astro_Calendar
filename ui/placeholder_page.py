"""Раздел, который будет реализован на следующих этапах разработки."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel

from ui.app_state import AppState
from ui.base_page import BasePage, heading, message_page_layout


class PlaceholderPage(BasePage):
    def __init__(self, state: AppState, title: str, stage: str, description: str):
        super().__init__(state)
        self.title = title
        layout = message_page_layout(self)
        layout.addWidget(heading(title))
        info = QLabel(f"Раздел в разработке — {stage}.\n\n{description}")
        info.setWordWrap(True)
        info.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        layout.addWidget(info, 1)
