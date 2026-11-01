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


def main() -> int:
    setup_logging()
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
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
