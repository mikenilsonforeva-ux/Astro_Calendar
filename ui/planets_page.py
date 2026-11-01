"""Страница «Планеты»."""
from __future__ import annotations

import html
from datetime import datetime, timezone

from PySide6.QtCore import QDate, QDateTime
from PySide6.QtWidgets import QComboBox, QDateTimeEdit, QHBoxLayout, QLabel, QPushButton

from astronomy import planets
from astronomy.coordinates import compass_point, format_dms, format_hms
from astronomy.time_utils import format_time
from ui.app_state import AppState
from ui.motion_chart import MotionChart
from ui.base_page import BasePage, fill_table, heading, hint_label, make_table, message_page_layout
from ui.workers import run_async

HEADERS = ["Планета", "Созвездие", "α (эпоха даты)", "δ (эпоха даты)", "λ эклипт.", "β эклипт.",
           "Азимут", "Высота", "Восход", "Заход", "Расстояние, а. е.", "Блеск",
           "Диаметр, ″", "Фаза/освещ.", "Элонгация", "Видимость"]


class PlanetsPage(BasePage):
    title = "Планеты"

    def __init__(self, state: AppState):
        super().__init__(state)
        layout = message_page_layout(self)
        layout.addWidget(heading("Планеты"))
        row = QHBoxLayout()
        row.addWidget(QLabel("Момент (местное время):"))
        self.dt_edit = QDateTimeEdit(QDateTime.currentDateTime())
        self.dt_edit.setCalendarPopup(True)
        self.dt_edit.setDisplayFormat("dd.MM.yyyy HH:mm")
        self.dt_edit.dateTimeChanged.connect(lambda _: self.refresh())
        row.addWidget(self.dt_edit)
        now = QPushButton("Сейчас")
        now.clicked.connect(lambda: self.dt_edit.setDateTime(QDateTime.currentDateTime()))
        row.addWidget(now)
        row.addStretch(1)
        layout.addLayout(row)
        self.status = hint_label()
        layout.addWidget(self.status)
        self.table = make_table(HEADERS, stretch_last=True)
        layout.addWidget(self.table, 1)

        chart_row = QHBoxLayout()
        chart_row.addWidget(QLabel("График движения:"))
        self.planet_combo = QComboBox()
        for key, name, *_ in planets.PLANETS:
            self.planet_combo.addItem(name, key)
        self.planet_combo.setCurrentIndex(3)
        self.period_combo = QComboBox()
        for label, days in (("1 год", 366), ("2 года", 731), ("5 лет", 1827), ("12 лет", 4383)):
            self.period_combo.addItem(label, days)
        chart_row.addWidget(self.planet_combo)
        chart_row.addWidget(self.period_combo)
        chart_row.addStretch(1)
        layout.addLayout(chart_row)
        self.chart = MotionChart()
        layout.addWidget(self.chart, 1)
        self.planet_combo.currentIndexChanged.connect(lambda _: self._load_chart())
        self.period_combo.currentIndexChanged.connect(lambda _: self._load_chart())
        self.note = hint_label(
            "Блеск — приближённая оценка по формулам Astronomical Almanac (точность порядка 0.1–0.3ᵐ; "
            "для Сатурна без учёта колец ошибка может быть больше). Фаза — угол Солнце–планета–Земля; "
            "освещённость показана для Меркурия, Венеры и Марса. На графике попятное движение выделено "
            "красным; даты ретроградных периодов есть в календаре событий.")
        layout.addWidget(self.note)

    def _load_chart(self) -> None:
        self._chart_request = getattr(self, "_chart_request", 0) + 1
        request = self._chart_request
        key, days = self.planet_combo.currentData(), self.period_combo.currentData()
        local_naive = self.dt_edit.dateTime().toPython()

        def work():
            ctx = self.state.context()
            start = local_naive.replace(tzinfo=ctx.tz).astimezone(timezone.utc)
            step = 2.0 if days <= 731 else 5.0
            return ctx, planets.motion_series(ctx, key, start, days, step)

        def done(result):
            if request == self._chart_request:
                self.chart.set_series(result[1], result[0].tz)

        run_async(work, done, lambda m: self.chart.set_message(m))

    def refresh(self) -> None:
        self._load_chart()
        local_naive = self.dt_edit.dateTime().toPython()
        self.status.setText("Расчёт…")
        run_async(self._work, self._done, self._failed, local_naive)

    def _work(self, local_naive: datetime):
        ctx = self.state.context()
        when = local_naive.replace(tzinfo=ctx.tz).astimezone(timezone.utc)
        return ctx, planets.all_info(ctx, when)

    def _failed(self, message: str) -> None:
        self.status.setText(f"<span style='color:#d9534f'>{html.escape(message)}</span>")

    def _done(self, result) -> None:
        ctx, infos = result
        self.status.setText(f"Часовой пояс: {ctx.tz.key}. Источник: Skyfield + {ctx.ephemeris_name}. "
                            "Восход/заход — для местных суток выбранной даты.")
        rows = []
        for p in infos:
            phase = "—" if p.illumination is None else f"{p.phase_angle:.0f}° / {p.illumination * 100:.0f}%"
            rows.append([
                p.name, p.constellation, format_hms(p.ra_hours), format_dms(p.dec_deg),
                f"{p.ecl_lon:.2f}°", f"{p.ecl_lat:+.2f}°",
                f"{p.azimuth:.0f}° {compass_point(p.azimuth)}", f"{p.altitude:+.1f}°",
                format_time(p.rise), format_time(p.set), f"{p.distance_au:.3f}",
                f"{p.magnitude:+.1f}ᵐ", f"{p.angular_diameter_arcsec:.1f}", phase,
                f"{p.elongation:.1f}° {p.elongation_side}", p.state])
        fill_table(self.table, rows)
