"""Астрономическая погода: прогноз Open-Meteo и индекс пригодности ночи."""
from __future__ import annotations

import html

from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure
from PySide6.QtWidgets import (QApplication, QComboBox, QHBoxLayout, QLabel, QPushButton,
                               QSplitter, QVBoxLayout, QWidget)

from astronomy.observing_index import DISCLAIMER
from astronomy.planets import PLANETS
from services.weather_service import ForecastResult, NightReport, WeatherService
from ui.app_state import AppState
from ui.base_page import BasePage, fill_table, heading, hint_label, make_table, message_page_layout
from ui.theme import is_dark
from ui.workers import run_async


class WeatherPage(BasePage):
    title = "Астрономическая погода"

    def __init__(self, state: AppState):
        super().__init__(state)
        self.service = WeatherService(state.db)
        self._nights: list[NightReport] = []
        layout = message_page_layout(self)
        layout.addWidget(heading("Астрономическая погода"))
        row = QHBoxLayout()
        row.addWidget(QLabel("Объект наблюдения (для учёта высоты):"))
        self.target = QComboBox()
        self.target.addItem("не выбран (небо в целом)", None)
        for key, name, *_ in PLANETS:
            self.target.addItem(name, key)
        self.target.currentIndexChanged.connect(lambda _: self._reload(False))
        row.addWidget(self.target)
        self.update_btn = QPushButton("Обновить прогноз")
        self.update_btn.setToolTip("Загрузить свежий прогноз из Open-Meteo (нужен интернет).")
        self.update_btn.clicked.connect(lambda: self._reload(True))
        row.addWidget(self.update_btn)
        row.addStretch(1)
        layout.addLayout(row)
        self.status = hint_label()
        layout.addWidget(self.status)
        layout.addWidget(hint_label(DISCLAIMER))

        split = QSplitter()
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.addWidget(QLabel("<b>Ночи</b>"))
        self.nights_table = make_table(["Вечер", "Индекс (средний)", "Лучший час", "Оценка"])
        self.nights_table.itemSelectionChanged.connect(self._show_night)
        left_layout.addWidget(self.nights_table)
        self.figure = Figure(figsize=(4, 2.5))
        self.canvas = FigureCanvasQTAgg(self.figure)
        left_layout.addWidget(self.canvas, 1)
        split.addWidget(left)
        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.addWidget(QLabel("<b>Почасовой прогноз выбранной ночи</b>"))
        self.hours_table = make_table(["Время", "Индекс", "Облачн., %", "T, °C", "Влажн., %",
                                       "Ветер, км/ч", "Осадки, мм", "Видим., км", "P, гПа",
                                       "Луна: выс./осв.", "Примечание"])
        right_layout.addWidget(self.hours_table, 1)
        split.addWidget(right)
        split.setStretchFactor(1, 2)
        layout.addWidget(split, 1)

    def refresh(self) -> None:
        self._reload(False)

    def _reload(self, force: bool) -> None:
        self.update_btn.setEnabled(False)
        self.status.setText("Загрузка прогноза…")
        run_async(self._work, self._done, self._failed, force, self.target.currentData())

    def _work(self, force: bool, target_key):
        loc = self.state.location
        forecast = self.service.get_forecast(loc, force)
        ctx = self.state.context()
        return forecast, ctx, WeatherService.build_report(ctx, forecast.hours, target_key)

    def _failed(self, message: str) -> None:
        self.update_btn.setEnabled(True)
        self.status.setText(f"<span style='color:#d9534f'>{html.escape(message)}</span>")

    def _done(self, result) -> None:
        self.update_btn.setEnabled(True)
        forecast: ForecastResult
        forecast, ctx, self._nights = result
        text = (f"Источник: Open-Meteo. Данные загружены: {forecast.fetched_at or '—'} (UTC)"
                f"{' (из сохранённых)' if forecast.from_cache else ''}. Время — {ctx.tz.key}.")
        if forecast.warning:
            text += f" <span style='color:#d9534f'>{html.escape(forecast.warning)}</span>"
        self.status.setText(text)
        rows = []
        for n in self._nights:
            best = n.best
            rows.append([n.evening_date.strftime("%d.%m.%Y"),
                         "—" if n.average is None else str(n.average),
                         best.time_local.strftime("%d.%m %H:%M") if best else "—",
                         best.score.label if best else "нет тёмных часов"])
        fill_table(self.nights_table, rows)
        self._plot()
        if self._nights:
            self.nights_table.selectRow(0)

    def _show_night(self) -> None:
        sel = self.nights_table.selectionModel().selectedRows()
        if not sel or sel[0].row() >= len(self._nights):
            return

        def num(value, fmt="{:.0f}"):
            return "—" if value is None else fmt.format(value)

        rows = []
        for h in self._nights[sel[0].row()].hours:
            w = h.weather
            rows.append([
                h.time_local.strftime("%d.%m %H:%M"),
                "—" if h.score.score is None else f"{h.score.score} ({h.score.label})",
                num(w.cloud_cover_pct), num(w.temperature_c, "{:.1f}"), num(w.humidity_pct),
                num(w.wind_kmh), num(w.precipitation_mm, "{:.1f}"),
                num(None if w.visibility_m is None else w.visibility_m / 1000.0, "{:.1f}"),
                num(w.pressure_hpa), f"{h.moon_altitude:+.0f}° / {h.moon_illumination * 100:.0f}%",
                h.score.note])
        fill_table(self.hours_table, rows)

    def _plot(self) -> None:
        dark = is_dark(QApplication.instance())
        fg, bg = ("#e4e6eb", "#202228") if dark else ("#222222", "#ffffff")
        self.figure.clear()
        self.figure.patch.set_facecolor(bg)
        ax = self.figure.add_subplot(111)
        ax.set_facecolor(bg)
        labels = [n.evening_date.strftime("%d.%m") for n in self._nights if n.average is not None]
        values = [n.average for n in self._nights if n.average is not None]
        colors = ["#5cb85c" if v >= 60 else "#f0ad4e" if v >= 40 else "#d9534f" for v in values]
        ax.bar(labels, values, color=colors)
        ax.set_ylim(0, 100)
        ax.set_title("Средний индекс по ночам (оценка приложения)", color=fg, fontsize=9)
        ax.tick_params(colors=fg, labelsize=8)
        for spine in ax.spines.values():
            spine.set_color(fg)
        self.figure.tight_layout()
        self.canvas.draw_idle()
