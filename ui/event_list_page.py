"""Универсальная страница списка событий одной категории (метеорные потоки, затмения)."""
from __future__ import annotations

import html
from datetime import date

from PySide6.QtWidgets import QHBoxLayout, QLabel, QSpinBox, QTextBrowser

from astronomy.eclipses import NOT_IMPLEMENTED_NOTE
from astronomy.event_types import CAT_ECLIPSE, CAT_METEOR
from astronomy.time_utils import get_timezone, local_range_bounds_utc
from ui.app_state import AppState
from ui.base_page import BasePage, fill_table, heading, hint_label, make_table, message_page_layout
from ui.calendar_page import event_local_label
from ui.workers import run_async


class EventListPage(BasePage):
    def __init__(self, state: AppState, category: str, title: str, note: str = ""):
        super().__init__(state)
        self.category = category
        self.title = title
        self._events = []
        layout = message_page_layout(self)
        layout.addWidget(heading(title))
        row = QHBoxLayout()
        row.addWidget(QLabel("Год:"))
        self.year = QSpinBox()
        self.year.setRange(1850, 2149)
        self.year.setValue(date.today().year)
        self.year.valueChanged.connect(lambda _: self.refresh())
        row.addWidget(self.year)
        row.addStretch(1)
        layout.addLayout(row)
        if note:
            layout.addWidget(hint_label(note))
        self.status = hint_label()
        layout.addWidget(self.status)
        self.table = make_table(["Дата", "Время", "Событие"])
        self.table.itemSelectionChanged.connect(self._show_details)
        layout.addWidget(self.table, 2)
        self.details = QTextBrowser()
        layout.addWidget(self.details, 1)

    def refresh(self) -> None:
        year = self.year.value()
        tz = get_timezone(self.state.location.timezone)
        start, end = local_range_bounds_utc(date(year, 1, 1), date(year, 12, 31), tz)
        self.status.setText("Расчёт…")
        run_async(self._work, self._done, self._failed, start, end)

    def _work(self, start, end):
        try:
            ctx = self.state.context()
        except Exception:
            ctx = None
        return self.state.events.get_events(ctx, start, end, [self.category])

    def _failed(self, message: str) -> None:
        self.status.setText(f"<span style='color:#d9534f'>{html.escape(message)}</span>")

    def _done(self, events) -> None:
        self._events = events
        self.status.setText(f"Событий за год: {len(events)}.")
        tz = get_timezone(self.state.location.timezone)
        fill_table(self.table, [[*event_local_label(e, tz), e.title] for e in events])
        self.details.clear()

    def _show_details(self) -> None:
        rows = self.table.selectionModel().selectedRows()
        if not rows or rows[0].row() >= len(self._events):
            return
        e = self._events[rows[0].row()]
        self.details.setHtml(
            f"<h3>{html.escape(e.title)}</h3><p>{html.escape(e.description)}</p>"
            f"<p><b>Видимость из выбранного места:</b> {html.escape(e.visibility)}</p>"
            f"<p><small>Источник: {html.escape(e.source)}</small></p>")


def make_meteor_page(state: AppState) -> EventListPage:
    return EventListPage(state, CAT_METEOR, "Метеорные потоки",
                         "Основные ежегодные потоки по календарю IMO. Даты максимума и ZHR ориентировочные; "
                         "условия наблюдения (радиант, Луна) рассчитываются для выбранного места.")


def make_eclipse_page(state: AppState) -> EventListPage:
    return EventListPage(state, CAT_ECLIPSE, "Затмения", NOT_IMPLEMENTED_NOTE)
