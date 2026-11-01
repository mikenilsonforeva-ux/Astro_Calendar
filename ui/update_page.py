"""Страница «Обновление данных»: эфемериды, кэш событий, история."""
from __future__ import annotations

import html

from PySide6.QtWidgets import QHBoxLayout, QLabel, QProgressBar, QPushButton

from ui.app_state import AppState
from ui.base_page import BasePage, fill_table, heading, hint_label, make_table, message_page_layout
from ui.workers import run_async


class UpdatePage(BasePage):
    title = "Обновление данных"

    def __init__(self, state: AppState):
        super().__init__(state)
        layout = message_page_layout(self)
        layout.addWidget(heading("Обновление данных"))
        layout.addWidget(hint_label(
            "Для расчётов нужен файл эфемерид JPL (скачивается один раз). После этого программа "
            "работает полностью автономно; интернет требуется только для обновлений, поиска "
            "координат по названию и (в следующих версиях) погоды и космической погоды."))
        self.status = hint_label()
        layout.addWidget(self.status)
        row = QHBoxLayout()
        self.download_btn = QPushButton("Скачать / обновить эфемериды")
        self.download_btn.clicked.connect(self._download)
        self.reset_btn = QPushButton("Пересчитать события")
        self.reset_btn.setToolTip("Сбросить кэш астрономических событий; они пересчитаются заново.")
        self.reset_btn.clicked.connect(self._reset)
        row.addWidget(self.download_btn)
        row.addWidget(self.reset_btn)
        row.addStretch(1)
        layout.addLayout(row)
        self.progress = QProgressBar()
        self.progress.setVisible(False)
        layout.addWidget(self.progress)
        self.message = hint_label()
        layout.addWidget(self.message)
        layout.addWidget(QLabel("<b>История обновлений</b>"))
        self.table = make_table(["Завершено (UTC)", "Источник", "Статус", "Сообщение"])
        layout.addWidget(self.table, 1)

    def refresh(self) -> None:
        st = self.state.updates.ephemeris_status()
        if st["available"]:
            text = (f"Эфемериды: <b>{html.escape(st['name'])}</b> найдены ({html.escape(st['years'])}). "
                    f"Последняя загрузка: {st['last_update'] or 'неизвестно'}.")
        else:
            text = (f"Эфемериды <b>{html.escape(st['name'])}</b> не найдены. Нажмите «Скачать» "
                    f"(≈ {st['size_mb']} МБ, нужен интернет).")
        self.status.setText(text)
        fill_table(self.table, [[u["finished_at"], u["source"], u["status"], u["message"] or ""]
                                for u in self.state.db.list_updates()])

    # ---- действия -------------------------------------------------------------
    def _download(self) -> None:
        self.download_btn.setEnabled(False)
        self.progress.setVisible(True)
        self.progress.setRange(0, 0)
        self.message.setText("Загрузка…")
        run_async(self._download_work, self._download_done, self._download_failed)

    def _download_work(self):
        # Прогресс из рабочего потока не передаём в интерфейс напрямую: индикатор «занят».
        return self.state.updates.download_ephemeris()

    def _download_done(self, path) -> None:
        self.download_btn.setEnabled(True)
        self.progress.setVisible(False)
        self.message.setText(f"Готово: {path}")
        self.state.notify_data_updated()
        self.refresh()

    def _download_failed(self, message: str) -> None:
        self.download_btn.setEnabled(True)
        self.progress.setVisible(False)
        self.message.setText(f"<span style='color:#d9534f'>{html.escape(message)}</span>")
        self.refresh()

    def _reset(self) -> None:
        self.state.updates.clear_event_cache()
        self.message.setText("Кэш событий сброшен.")
        self.state.notify_data_updated()
        self.refresh()
