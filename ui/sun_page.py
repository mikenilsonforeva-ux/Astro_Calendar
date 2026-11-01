"""Страница «Солнце»."""
from __future__ import annotations

import html
from datetime import date, datetime, timezone

from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure
from PySide6.QtCore import QDate
from PySide6.QtWidgets import QDateEdit, QHBoxLayout, QLabel, QPushButton, QTextBrowser

from astronomy import sun
from astronomy.coordinates import compass_point, format_dms, format_hms
from astronomy.time_utils import format_duration, format_time
from ui.app_state import AppState
from ui.base_page import BasePage, fill_table, heading, hint_label, make_table, message_page_layout
from ui.theme import is_dark
from ui.workers import run_async


class SunPage(BasePage):
    title = "Солнце"

    def __init__(self, state: AppState):
        super().__init__(state)
        layout = message_page_layout(self)
        layout.addWidget(heading("Солнце"))
        row = QHBoxLayout()
        row.addWidget(QLabel("Дата:"))
        self.date_edit = QDateEdit(QDate.currentDate())
        self.date_edit.setCalendarPopup(True)
        self.date_edit.setDisplayFormat("dd.MM.yyyy")
        self.date_edit.dateChanged.connect(lambda _: self.refresh())
        row.addWidget(self.date_edit)
        today = QPushButton("Сегодня")
        today.clicked.connect(lambda: self.date_edit.setDate(QDate.currentDate()))
        row.addWidget(today)
        row.addStretch(1)
        layout.addLayout(row)
        self.status = hint_label()
        layout.addWidget(self.status)
        self.text = QTextBrowser()
        self.text.setMaximumHeight(300)
        layout.addWidget(self.text)
        self.figure = Figure(figsize=(6, 3))
        self.canvas = FigureCanvasQTAgg(self.figure)
        layout.addWidget(self.canvas, 1)
        layout.addWidget(QLabel("<b>Равноденствия и солнцестояния</b>"))
        self.seasons = make_table(["Событие", "Дата и время (местное)"])
        self.seasons.setMaximumHeight(150)
        layout.addWidget(self.seasons)

    def refresh(self) -> None:
        day: date = self.date_edit.date().toPython()
        self.status.setText("Расчёт…")
        run_async(self._work, self._done, self._failed, day)

    def _work(self, day: date):
        ctx = self.state.context()
        moment = datetime.now(timezone.utc) if day == ctx.local(datetime.now(timezone.utc)).date() \
            else ctx.local(datetime(day.year, day.month, day.day, 12, tzinfo=ctx.tz)).astimezone(timezone.utc)
        info = sun.day_info(ctx, day)
        pos = sun.position(ctx, moment)
        times, alts = sun.altitude_series(ctx, day)
        t0, t1 = ctx.ts.utc(day.year, 1, 1), ctx.ts.utc(day.year + 1, 1, 1)
        seasons = [(e.title, ctx.local(e.utc_time)) for e in sun.season_events(ctx, t0, t1)]
        return ctx, info, pos, times, alts, seasons

    def _failed(self, message: str) -> None:
        self.status.setText(f"<span style='color:#d9534f'>{html.escape(message)}</span>")

    def _done(self, result) -> None:
        ctx, info, pos, times, alts, seasons = result
        self.status.setText(f"Часовой пояс: {ctx.tz.key}. Источник: Skyfield + {ctx.ephemeris_name}. "
                            "Высота с учётом стандартной рефракции; восход/заход по горизонту −0.833°.")
        moment = ctx.local(pos.when_utc)
        rows = [
            ("Момент расчёта положения", moment.strftime("%d.%m.%Y %H:%M")),
            ("Восход", format_time(info.sunrise)), ("Солнечный полдень", format_time(info.solar_noon)),
            ("Заход", format_time(info.sunset)),
            ("Продолжительность дня", format_duration(info.day_length)),
            ("Продолжительность ночи", format_duration(info.night_length)),
            ("Гражданские сумерки", f"{format_time(info.civil_dawn)} — {format_time(info.civil_dusk)}"),
            ("Навигационные сумерки", f"{format_time(info.nautical_dawn)} — {format_time(info.nautical_dusk)}"),
            ("Астрономические сумерки", f"{format_time(info.astronomical_dawn)} — {format_time(info.astronomical_dusk)}"),
            ("Азимут / высота", f"{pos.azimuth:.1f}° ({compass_point(pos.azimuth)}) / {pos.altitude:+.1f}°"),
            ("Прямое восхождение (эпоха даты)", format_hms(pos.ra_hours)),
            ("Склонение (эпоха даты)", format_dms(pos.dec_deg)),
            ("Расстояние", f"{pos.distance_au:.5f} а. е. ({pos.distance_km / 1e6:.3f} млн км)"),
            ("Уравнение времени", f"{pos.equation_of_time_min:+.1f} мин"),
        ]
        body = "".join(f"<tr><td>{a}</td><td><b>{b}</b></td></tr>" for a, b in rows)
        notes = "".join(f"<p><i>{html.escape(n)}</i></p>" for n in info.notes)
        self.text.setHtml(f"<table cellspacing='4'>{body}</table>{notes}")
        self._plot(times, alts, info)
        fill_table(self.seasons, [[title, local.strftime("%d.%m.%Y %H:%M")] for title, local in seasons])

    def _plot(self, times, alts, info) -> None:
        from PySide6.QtWidgets import QApplication
        dark = is_dark(QApplication.instance())
        fg, bg = ("#e4e6eb", "#202228") if dark else ("#222222", "#ffffff")
        self.figure.clear()
        self.figure.patch.set_facecolor(bg)
        ax = self.figure.add_subplot(111)
        ax.set_facecolor(bg)
        hours = [t.hour + t.minute / 60 for t in times]
        # Если сутки не 24 ч (переход на летнее время), ось всё равно строится по часам стены.
        ax.plot(hours, alts, color="#f0a030", linewidth=2)
        ax.axhline(0, color=fg, linewidth=0.8)
        for level, label in ((-6, "гражд."), (-12, "навиг."), (-18, "астр.")):
            ax.axhline(level, color=fg, linewidth=0.5, linestyle=":")
            ax.text(0.1, level + 0.8, label, color=fg, fontsize=7)
        ax.set_xlim(0, 24)
        ax.set_xticks(range(0, 25, 3))
        ax.set_xlabel("Местное время, ч", color=fg)
        ax.set_ylabel("Высота Солнца, °", color=fg)
        ax.set_title("Высота Солнца в течение суток", color=fg)
        ax.tick_params(colors=fg)
        for spine in ax.spines.values():
            spine.set_color(fg)
        ax.grid(alpha=0.25)
        self.figure.tight_layout()
        self.canvas.draw_idle()
