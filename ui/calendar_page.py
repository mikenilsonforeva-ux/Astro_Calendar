"""Астрономический календарь: день / неделя / месяц / год, фильтр по категориям."""
from __future__ import annotations

import html
from datetime import date, timedelta

from PySide6.QtCore import QDate
from PySide6.QtWidgets import (QCalendarWidget, QCheckBox, QComboBox, QHBoxLayout, QLabel,
                               QSplitter, QTextBrowser, QVBoxLayout, QWidget)

from astronomy.event_types import CATEGORY_NAMES, AstroEvent
from astronomy.time_utils import get_timezone, local_range_bounds_utc
from ui.app_state import AppState
from ui.base_page import BasePage, fill_table, heading, hint_label, make_table, message_page_layout
from ui.workers import run_async

MODES = ["День", "Неделя", "Месяц", "Год"]


def period_bounds(mode: str, selected: date) -> tuple[date, date]:
    """Первая и последняя местные даты периода."""
    if mode == "День":
        return selected, selected
    if mode == "Неделя":
        monday = selected - timedelta(days=selected.weekday())
        return monday, monday + timedelta(days=6)
    if mode == "Месяц":
        first = selected.replace(day=1)
        nxt = date(selected.year + (selected.month == 12), selected.month % 12 + 1, 1)
        return first, nxt - timedelta(days=1)
    return date(selected.year, 1, 1), date(selected.year, 12, 31)


def event_local_label(event: AstroEvent, tz) -> tuple[str, str]:
    """(дата, время) события в часовом поясе места наблюдения."""
    if event.all_day:
        day = date.fromisoformat(event.params["peak_date"])
        return day.strftime("%d.%m.%Y"), "весь день"
    local = event.utc_time.astimezone(tz)
    return local.strftime("%d.%m.%Y"), local.strftime("%H:%M")


class CalendarPage(BasePage):
    title = "Астрономический календарь"

    def __init__(self, state: AppState):
        super().__init__(state)
        self._events: list[AstroEvent] = []
        self._shown: list[AstroEvent] = []
        layout = message_page_layout(self)
        layout.addWidget(heading("Астрономический календарь"))

        top = QHBoxLayout()
        top.addWidget(QLabel("Период:"))
        self.mode = QComboBox()
        self.mode.addItems(MODES)
        self.mode.setCurrentText("Месяц")
        top.addWidget(self.mode)
        top.addSpacing(20)
        self.checks: dict[str, QCheckBox] = {}
        for key, name in CATEGORY_NAMES.items():
            box = QCheckBox(name)
            box.setChecked(True)
            box.toggled.connect(self._apply_filter)
            self.checks[key] = box
            top.addWidget(box)
        top.addStretch(1)
        layout.addLayout(top)

        split = QSplitter()
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        self.calendar = QCalendarWidget()
        self.calendar.setGridVisible(True)
        left_layout.addWidget(self.calendar)
        self.status = hint_label()
        left_layout.addWidget(self.status)
        left_layout.addStretch(1)
        split.addWidget(left)

        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        self.table = make_table(["Дата", "Время", "Категория", "Событие"])
        self.table.itemSelectionChanged.connect(self._show_details)
        right_layout.addWidget(self.table, 3)
        self.details = QTextBrowser()
        self.details.setOpenExternalLinks(True)
        right_layout.addWidget(self.details, 2)
        split.addWidget(right)
        split.setStretchFactor(1, 1)
        layout.addWidget(split, 1)

        self.mode.currentTextChanged.connect(lambda _: self.refresh())
        self.calendar.selectionChanged.connect(self.refresh)
        self.calendar.currentPageChanged.connect(self._page_changed)

    def _page_changed(self, year: int, month: int) -> None:
        if self.mode.currentText() in ("Месяц", "Год"):
            self.calendar.setSelectedDate(QDate(year, month, min(self.calendar.selectedDate().day(), 28)))

    def refresh(self) -> None:
        selected: date = self.calendar.selectedDate().toPython()
        first, last = period_bounds(self.mode.currentText(), selected)
        tz = get_timezone(self.state.location.timezone)
        start_utc, end_utc = local_range_bounds_utc(first, last, tz)
        self.status.setText(f"Период: {first:%d.%m.%Y} — {last:%d.%m.%Y}. Расчёт…")
        run_async(self._work, self._done, self._failed, start_utc, end_utc)

    def _work(self, start_utc, end_utc):
        try:
            ctx = self.state.context()
        except Exception:
            ctx = None   # автономный режим: покажем уже сохранённые события
        return self.state.events.get_events(ctx, start_utc, end_utc), ctx is not None

    def _failed(self, message: str) -> None:
        self.status.setText(f"<span style='color:#d9534f'>{html.escape(message)}</span>")

    def _done(self, result) -> None:
        self._events, with_ctx = result
        note = "" if with_ctx else (" Нет файла эфемерид: показаны только ранее сохранённые события "
                                    "(раздел «Обновление данных»).")
        self.status.setText(f"Событий в периоде: {len(self._events)}.{note}")
        self._apply_filter()

    def _visible_events(self) -> list[AstroEvent]:
        active = {k for k, box in self.checks.items() if box.isChecked()}
        return [e for e in self._events if e.category in active]

    def _apply_filter(self) -> None:
        tz = get_timezone(self.state.location.timezone)
        self._shown = self._visible_events()
        rows = []
        for e in self._shown:
            day, time_ = event_local_label(e, tz)
            rows.append([day, time_, CATEGORY_NAMES.get(e.category, e.category), e.title])
        fill_table(self.table, rows)
        self.details.clear()

    def _show_details(self) -> None:
        rows = self.table.selectionModel().selectedRows()
        if not rows or rows[0].row() >= len(self._shown):
            return
        e = self._shown[rows[0].row()]
        tz = get_timezone(self.state.location.timezone)
        day, time_ = event_local_label(e, tz)
        kind = "Глобальное событие" if e.is_global else "Зависит от места наблюдения"
        params = "".join(f"<li>{html.escape(str(k))}: {html.escape(str(v))}</li>"
                         for k, v in e.params.items() if k not in ("all_day", "kind", "peak_date"))
        self.details.setHtml(
            f"<h3>{html.escape(e.title)}</h3>"
            f"<p><b>Дата:</b> {day} <b>Время:</b> {time_} ({self.state.location.timezone})</p>"
            f"<p>{html.escape(e.description)}</p>"
            f"<p><b>Видимость из «{html.escape(self.state.location.name)}»:</b> {html.escape(e.visibility)}</p>"
            f"<p><i>{kind}.</i></p>"
            + (f"<ul>{params}</ul>" if params else "")
            + f"<p><small>Источник: {html.escape(e.source)}</small></p>")
