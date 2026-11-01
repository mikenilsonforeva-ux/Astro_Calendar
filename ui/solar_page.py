"""Солнечная активность: Kp (история и прогноз), вспышки, оценка полярных сияний."""
from __future__ import annotations

import html
from datetime import datetime, timedelta, timezone

from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure
from PySide6.QtWidgets import QApplication, QHBoxLayout, QPushButton, QTextBrowser

from astronomy.space_weather import aurora_assessment, storm_scale
from services.solar_service import SolarData, SolarService
from ui.app_state import AppState
from ui.base_page import BasePage, fill_table, heading, hint_label, make_table, message_page_layout
from ui.theme import is_dark
from ui.workers import run_async


class SolarPage(BasePage):
    title = "Солнечная активность"

    def __init__(self, state: AppState):
        super().__init__(state)
        self.service = SolarService(state.db)
        layout = message_page_layout(self)
        layout.addWidget(heading("Солнечная активность"))
        row = QHBoxLayout()
        self.update_btn = QPushButton("Обновить данные")
        self.update_btn.setToolTip("Загрузить данные NOAA SWPC (нужен интернет).")
        self.update_btn.clicked.connect(lambda: self._reload(True))
        row.addWidget(self.update_btn)
        row.addStretch(1)
        layout.addLayout(row)
        self.status = hint_label()
        layout.addWidget(self.status)
        self.summary = QTextBrowser()
        self.summary.setMaximumHeight(150)
        layout.addWidget(self.summary)
        self.figure = Figure(figsize=(6, 2.8))
        self.canvas = FigureCanvasQTAgg(self.figure)
        layout.addWidget(self.canvas, 1)
        layout.addWidget(hint_label("<b>Вспышки на Солнце за 7 суток (класс по рентгену, GOES)</b>"))
        self.flares = make_table(["Максимум (местное время)", "Класс"])
        self.flares.setMaximumHeight(170)
        layout.addWidget(self.flares)
        layout.addWidget(hint_label(
            "Корональные выбросы массы (NASA DONKI) пока не подключены: для них нужен ключ API, "
            "который нельзя хранить в исходном коде."))

    def refresh(self) -> None:
        self._reload(False)

    def _reload(self, force: bool) -> None:
        self.update_btn.setEnabled(False)
        self.status.setText("Загрузка данных NOAA SWPC…")
        run_async(self.service.get, self._done, self._failed, force)

    def _failed(self, message: str) -> None:
        self.update_btn.setEnabled(True)
        self.status.setText(f"<span style='color:#d9534f'>{html.escape(message)}</span>")

    def _done(self, data: SolarData) -> None:
        self.update_btn.setEnabled(True)
        loc = self.state.location
        text = f"Источник: NOAA SWPC. Обновлено: {data.updated_at or '—'} (UTC)" \
               f"{' (из сохранённых данных)' if data.from_cache else ''}."
        if data.warnings:
            text += " <span style='color:#d9534f'>" + html.escape(" | ".join(data.warnings)) + "</span>"
        self.status.setText(text)

        observed = [p for p in data.kp_history if p.observed]
        current = observed[-1] if observed else None
        now = datetime.now(timezone.utc)
        upcoming = [p for p in data.kp_forecast if p.time_utc >= now]
        peak = max(upcoming, key=lambda p: p.kp) if upcoming else None
        lines = []
        if current:
            verdict, why = aurora_assessment(loc.latitude, loc.longitude, current.kp)
            lines.append(f"<b>Текущий Kp: {current.kp:.1f}</b> ({storm_scale(current.kp)}), "
                         f"измерение {current.time_utc:%d.%m %H:%M} UTC.")
            lines.append(f"Полярное сияние сейчас в «{html.escape(loc.name)}»: "
                         f"<b>вероятность {verdict}</b> — {html.escape(why)}")
        if peak:
            verdict, _ = aurora_assessment(loc.latitude, loc.longitude, peak.kp)
            lines.append(f"Максимум Kp в прогнозе: <b>{peak.kp:.1f}</b> ({storm_scale(peak.kp)}), "
                         f"{peak.time_utc:%d.%m %H:%M} UTC; вероятность сияния у вас тогда: {verdict}.")
        self.summary.setHtml("<br>".join(lines) or "Нет данных Kp.")
        self._plot(data)

        from astronomy.time_utils import get_timezone
        tz = get_timezone(loc.timezone)
        recent = [f for f in data.flares if f.max_utc][-30:]
        fill_table(self.flares, [[f.max_utc.astimezone(tz).strftime("%d.%m.%Y %H:%M"), f.max_class]
                                 for f in reversed(recent)])

    def _plot(self, data: SolarData) -> None:
        dark = is_dark(QApplication.instance())
        fg, bg = ("#e4e6eb", "#202228") if dark else ("#222222", "#ffffff")
        self.figure.clear()
        self.figure.patch.set_facecolor(bg)
        ax = self.figure.add_subplot(111)
        ax.set_facecolor(bg)
        start = datetime.now(timezone.utc) - timedelta(days=4)

        def colour(kp):
            return "#5cb85c" if kp < 4 else "#f0ad4e" if kp < 5 else "#d9534f"

        hist = [p for p in data.kp_history if p.time_utc >= start]
        width = 3 / 24 * 0.9
        ax.bar([p.time_utc for p in hist], [p.kp for p in hist], width=width,
               color=[colour(p.kp) for p in hist], label="измерено")
        fc = [p for p in data.kp_forecast if not p.observed and p.time_utc >= start]
        ax.bar([p.time_utc for p in fc], [p.kp for p in fc], width=width, fill=False,
               edgecolor=fg, hatch="//", label="прогноз")
        ax.axhline(5, color="#d9534f", linewidth=0.8, linestyle="--")
        ax.text(0.01, 5.15, "G1 (Kp ≥ 5)", transform=ax.get_yaxis_transform(), color=fg, fontsize=7)
        ax.set_ylim(0, 9)
        ax.set_ylabel("Kp", color=fg)
        ax.set_title("Геомагнитный индекс Kp (UTC)", color=fg, fontsize=9)
        ax.tick_params(colors=fg, labelsize=8)
        self.figure.autofmt_xdate()
        for spine in ax.spines.values():
            spine.set_color(fg)
        if hist or fc:
            ax.legend(facecolor=bg, labelcolor=fg, fontsize=7)
        self.figure.tight_layout()
        self.canvas.draw_idle()
