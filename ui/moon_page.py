"""Страница «Луна»: текущие параметры, рисунок фазы, календарь фаз и апсид."""
from __future__ import annotations

import html
import math
from datetime import datetime, timedelta, timezone

from PySide6.QtCore import QDate, QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath
from PySide6.QtWidgets import (QDateEdit, QHBoxLayout, QLabel, QPushButton, QTextBrowser,
                               QVBoxLayout, QWidget)

from astronomy import moon
from astronomy.coordinates import compass_point, format_dms, format_hms
from astronomy.time_utils import format_time
from ui.app_state import AppState
from ui.base_page import BasePage, fill_table, heading, hint_label, make_table, message_page_layout
from ui.workers import run_async


class MoonPhaseWidget(QWidget):
    """Рисует диск Луны с освещённой частью по фазовому углу (0° — новолуние)."""

    def __init__(self) -> None:
        super().__init__()
        self.phase_angle = 0.0
        self.southern = False
        self.setMinimumSize(180, 180)

    def set_phase(self, phase_angle: float, southern: bool = False) -> None:
        self.phase_angle, self.southern = phase_angle % 360.0, southern
        self.update()

    def paintEvent(self, _event) -> None:  # noqa: N802 (имя задано Qt)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        side = min(self.width(), self.height()) - 16
        cx, cy, r = self.width() / 2, self.height() / 2, side / 2
        if self.southern:   # в южном полушарии картина зеркальна
            painter.translate(self.width(), 0)
            painter.scale(-1, 1)
        disc = QPainterPath()
        disc.addEllipse(QPointF(cx, cy), r, r)
        painter.fillPath(disc, QColor(45, 48, 60))
        phase = math.radians(self.phase_angle)
        c = math.cos(phase)
        half = QPainterPath()
        if self.phase_angle < 180.0:   # растущая — освещён правый край
            half.addRect(QRectF(cx, cy - r, r, 2 * r))
        else:
            half.addRect(QRectF(cx - r, cy - r, r, 2 * r))
        lit = disc.intersected(half)
        ellipse = QPainterPath()
        ellipse.addEllipse(QPointF(cx, cy), abs(c) * r, r)
        lit = lit.subtracted(ellipse) if c > 0 else lit.united(ellipse)
        painter.fillPath(lit.intersected(disc), QColor(238, 232, 205))
        painter.setPen(QColor(120, 125, 140))
        painter.drawEllipse(QPointF(cx, cy), r, r)


class MoonPage(BasePage):
    title = "Луна"

    def __init__(self, state: AppState):
        super().__init__(state)
        layout = message_page_layout(self)
        layout.addWidget(heading("Луна"))
        row = QHBoxLayout()
        row.addWidget(QLabel("Дата (на 12:00 местного, для сегодняшней даты — сейчас):"))
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

        body = QHBoxLayout()
        self.phase_widget = MoonPhaseWidget()
        body.addWidget(self.phase_widget)
        self.text = QTextBrowser()
        body.addWidget(self.text, 1)
        layout.addLayout(body, 1)
        layout.addWidget(QLabel("<b>Фазы Луны, перигей и апогей: ближайшие два месяца</b>"))
        self.table = make_table(["Дата и время (местное)", "Событие", "Примечание"])
        layout.addWidget(self.table, 1)

    def refresh(self) -> None:
        day = self.date_edit.date().toPython()
        self.status.setText("Расчёт…")
        run_async(self._work, self._done, self._failed, day)

    def _work(self, day):
        ctx = self.state.context()
        now = datetime.now(timezone.utc)
        if day == ctx.local(now).date():
            moment = now
        else:
            moment = datetime(day.year, day.month, day.day, 12, tzinfo=ctx.tz).astimezone(timezone.utc)
        data = moon.info(ctx, moment)
        t0 = ctx.t(moment)
        t1 = ctx.t(moment + timedelta(days=62))
        events = moon.phase_events(ctx, t0, t1) + moon.apsis_events(ctx, t0, t1)
        events.sort(key=lambda e: e.utc_time)
        return ctx, data, events

    def _failed(self, message: str) -> None:
        self.status.setText(f"<span style='color:#d9534f'>{html.escape(message)}</span>")

    def _done(self, result) -> None:
        ctx, d, events = result
        self.status.setText(f"Часовой пояс: {ctx.tz.key}. Источник: Skyfield + {ctx.ephemeris_name}.")
        self.phase_widget.set_phase(d.phase_angle, southern=ctx.latitude < 0)
        rows = [
            ("Момент расчёта", ctx.local(d.when_utc).strftime("%d.%m.%Y %H:%M")),
            ("Фаза", d.phase_name),
            ("Освещённость диска", f"{d.illumination * 100:.1f}%"),
            ("Возраст Луны", f"{d.age_days:.1f} сут"),
            ("Восход / заход (местные сутки)", f"{format_time(d.rise)} / {format_time(d.set)}"),
            ("Азимут / высота", f"{d.azimuth:.1f}° ({compass_point(d.azimuth)}) / {d.altitude:+.1f}°"),
            ("Прямое восхождение (эпоха даты)", format_hms(d.ra_hours)),
            ("Склонение (эпоха даты)", format_dms(d.dec_deg)),
            ("Расстояние до Земли", f"{d.distance_km:,.0f} км".replace(",", " ")),
            ("Угловой диаметр", f"{d.angular_diameter_arcmin:.1f}′"),
        ]
        body = "".join(f"<tr><td>{a}</td><td><b>{b}</b></td></tr>" for a, b in rows)
        self.text.setHtml(f"<table cellspacing='4'>{body}</table>"
                          "<p><i>Лунные затмения — в разделе «Затмения».</i></p>")
        fill_table(self.table, [
            [ctx.local(e.utc_time).strftime("%d.%m.%Y %H:%M"), e.title,
             e.description if e.params.get("distance_km") else ""] for e in events])
