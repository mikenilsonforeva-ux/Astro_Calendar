"""Дымовой тест: главное окно создаётся и страницы открываются без исключений."""
import os

import pytest

pytest.importorskip("PySide6")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def test_main_window_opens_all_pages(tmp_path):
    from PySide6.QtWidgets import QApplication
    from database.db_manager import DatabaseManager
    from ui.app_state import AppState
    from ui.main_window import MainWindow
    from ui.theme import apply_theme

    app = QApplication.instance() or QApplication([])
    state = AppState(DatabaseManager(tmp_path / "ui.db"))
    for theme in ("dark", "light"):
        apply_theme(app, theme)
    window = MainWindow(state)
    window.show()
    for row in range(window.nav.count()):
        window.nav.setCurrentRow(row)
        app.processEvents()
    from PySide6.QtCore import QThreadPool
    QThreadPool.globalInstance().waitForDone(20000)
    app.processEvents()
    assert window.nav.count() == 16
    assert window.pages[5].title == "Звёздное небо"
    assert state.location.name == "Москва"
