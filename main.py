"""Точка входа приложения «Астрономический календарь»."""
from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler

import config


def setup_logging() -> None:
    config.ensure_dirs()
    handler = RotatingFileHandler(config.LOG_DIR / "app.log", maxBytes=1_000_000, backupCount=3,
                                  encoding="utf-8")
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=[handler, logging.StreamHandler()],
    )


def _log_uncaught(exc_type, exc, tb) -> None:
    """Необработанные ошибки (в том числе из обработчиков Qt) — в лог, а не только в консоль."""
    logging.getLogger("uncaught").error("Необработанная ошибка", exc_info=(exc_type, exc, tb))
    sys.__excepthook__(exc_type, exc, tb)


def main() -> int:
    setup_logging()
    sys.excepthook = _log_uncaught
    logging.getLogger("matplotlib").setLevel(logging.WARNING)      # убрать служебные INFO-сообщения
    log = logging.getLogger("main")
    log.info("Запуск %s %s", config.APP_TITLE, config.APP_VERSION)

    from PySide6.QtWidgets import QApplication, QMessageBox

    app = QApplication(sys.argv)
    app.setApplicationName(config.APP_NAME)

    try:
        from database.db_manager import DatabaseManager
        from ui.app_state import AppState
        from ui.main_window import MainWindow
        from ui.theme import apply_theme

        state = AppState(DatabaseManager(config.DB_PATH))
        apply_theme(app, state.theme)
        state.theme_changed.connect(lambda name: apply_theme(app, name))
        window = MainWindow(state)
    except Exception as exc:
        log.exception("Не удалось запустить приложение")
        QMessageBox.critical(None, config.APP_TITLE, f"Не удалось запустить приложение:\n{exc}")
        return 1

    window.show()
    code = app.exec()
    from PySide6.QtCore import QThreadPool
    QThreadPool.globalInstance().waitForDone(5000)   # дождаться фоновых задач перед выходом
    return code


if __name__ == "__main__":
    sys.exit(main())
