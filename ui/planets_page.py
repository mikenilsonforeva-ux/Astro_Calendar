"""Страница «Планеты»."""
from __future__ import annotations

import html
from datetime import datetime, timezone

from PySide6.QtCore import QDate, QDateTime
from PySide6.QtWidgets import QDateTimeEdit, QHBoxLayout, QLabel, QPushButton

from astronomy import planets
from astronomy.coordinates import compass_point, format_dms, format_hms
from astronomy.time_utils import format_time
from ui.app_state import AppState
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
        self.note = hint_label(
            "Блеск — приближённая оценка по формулам Astronomical Almanac (точность порядка 0.1–0.3ᵐ; "
            "для Сатурна без учёта колец ошибка может быть больше). Фаза — угол Солнце–планета–Земля; "
            "освещённость показана для Меркурия, Венеры и Марса. Графики движения планет и ретроградные "
            "периоды — этап 6.")
        layout.addWidget(self.note)

    def refresh(self) -> None:
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
