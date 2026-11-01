"""Главная страница: дата и время, место, Луна, Солнце, планеты, ближайшие события."""
from __future__ import annotations

from datetime import datetime, timezone

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QGridLayout, QGroupBox, QLabel, QVBoxLayout

from astronomy.coordinates import format_lat_lon
from astronomy.event_types import CATEGORY_NAMES
from astronomy.time_utils import format_duration, format_time
from services.dashboard_service import Dashboard, build_dashboard
from ui.app_state import AppState
from ui.base_page import BasePage, fill_table, heading, hint_label, make_table, message_page_layout
from ui.workers import run_async


def _card(title: str) -> tuple[QGroupBox, QLabel]:
    box = QGroupBox(title)
    label = QLabel("…")
    label.setWordWrap(True)
    label.setTextFormat(Qt.RichText)
    layout = QVBoxLayout(box)
    layout.addWidget(label)
    return box, label


class HomePage(BasePage):
    title = "Главная"

    def __init__(self, state: AppState):
        super().__init__(state)
        layout = message_page_layout(self)
        layout.addWidget(heading("Главная"))
        self.clock = QLabel()
        font = self.clock.font()
        font.setPointSize(font.pointSize() + 8)
        self.clock.setFont(font)
        layout.addWidget(self.clock)
        self.place = hint_label()
        layout.addWidget(self.place)
        self.status = hint_label()
        layout.addWidget(self.status)

        grid = QGridLayout()
        self.moon_box, self.moon_label = _card("Луна")
        self.sun_box, self.sun_label = _card("Солнце")
        self.weather_box, self.weather_label = _card("Астрономическая погода")
        self.weather_label.setText("Откройте раздел «Астрономическая погода».")
        grid.addWidget(self.moon_box, 0, 0)
        grid.addWidget(self.sun_box, 0, 1)
        grid.addWidget(self.weather_box, 0, 2)
        layout.addLayout(grid)

        layout.addWidget(QLabel("<b>Видимость планет сейчас</b>"))
        self.planet_table = make_table(["Планета", "Созвездие", "Высота", "Блеск", "Видимость"])
        self.planet_table.setMaximumHeight(240)
        layout.addWidget(self.planet_table)
        layout.addWidget(QLabel("<b>Ближайшие события</b>"))
        self.event_table = make_table(["Дата и время", "Категория", "Событие"])
        layout.addWidget(self.event_table, 1)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.timer.start(1000)
        self._tick()

    def _tick(self) -> None:
        loc = self.state.location
        from astronomy.time_utils import get_timezone
        now = datetime.now(get_timezone(loc.timezone))
        self.clock.setText(now.strftime("%d.%m.%Y  %H:%M:%S") + f"   ({loc.timezone})")

    def refresh(self) -> None:
        loc = self.state.location
        self.place.setText(f"Место наблюдения: <b>{loc.name}</b> — "
                           f"{format_lat_lon(loc.latitude, loc.longitude)}, {loc.elevation_m:.0f} м")
        self.status.setText("Расчёт…")
        run_async(self._work, self._done, self._failed)

    def _work(self) -> Dashboard:
        ctx = self.state.context()
        return build_dashboard(ctx, self.state.events)

    def _failed(self, message: str) -> None:
        self.status.setText(f"<span style='color:#d9534f'>{message}</span>")
        for label in (self.moon_label, self.sun_label):
            label.setText("—")

    def _done(self, d: Dashboard) -> None:
        loc = self.state.location
        self.status.setText(f"Расчёт выполнен по локальным эфемеридам ({self.state.context().ephemeris_name}).")
        m = d.moon
        self.moon_label.setText(
            f"<b>{m.phase_name}</b><br>Освещённость: {m.illumination * 100:.0f}%<br>"
            f"Возраст: {m.age_days:.1f} сут<br>Восход: {format_time(m.rise)}, заход: {format_time(m.set)}")
        s = d.sun_day
        note = f"<br><i>{s.notes[0]}</i>" if s.notes else ""
        self.sun_label.setText(
            f"Восход: <b>{format_time(s.sunrise)}</b><br>Заход: <b>{format_time(s.sunset)}</b><br>"
            f"Долгота дня: {format_duration(s.day_length)}{note}")
        rows = [[p.name, p.constellation, f"{p.altitude:+.0f}°", f"{p.magnitude:+.1f}ᵐ", p.state]
                for p in d.planets]
        fill_table(self.planet_table, rows)
        fill_table(self.event_table, [
            [self._local(e.utc_time, e.all_day), CATEGORY_NAMES.get(e.category, e.category), e.title]
            for e in d.events])

    def _local(self, utc_time: datetime, all_day: bool) -> str:
        from astronomy.time_utils import get_timezone
        tz = get_timezone(self.state.location.timezone)
        if all_day:
            return utc_time.astimezone(timezone.utc).strftime("%d.%m.%Y") + " (весь день)"
        return utc_time.astimezone(tz).strftime("%d.%m.%Y %H:%M")
