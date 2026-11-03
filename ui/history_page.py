"""Страница «Космическая история»: события космической тематики в выбранный день года."""
from __future__ import annotations

import html
from datetime import datetime

from PySide6.QtCore import QDate
from PySide6.QtWidgets import (QComboBox, QDateEdit, QHBoxLayout, QLabel, QPushButton, QTextBrowser)

from astronomy.time_utils import get_timezone
from services import space_history
from ui.app_state import AppState
from ui.base_page import BasePage, heading, hint_label, message_page_layout

MONTHS = ["января", "февраля", "марта", "апреля", "мая", "июня", "июля", "августа", "сентября", "октября",
          "ноября", "декабря"]
NEAR_WINDOW_DAYS = 7


def years_text(n: int) -> str:
    if n <= 0:
        return ""
    last2, last = n % 100, n % 10
    word = "лет" if 11 <= last2 <= 14 else "год" if last == 1 else "года" if 2 <= last <= 4 else "лет"
    return f"{n} {word} назад"


def render_day(month: int, day: int, current_year: int, category: str | None) -> str:
    """HTML-текст событий дня (вынесен из виджета, чтобы проверять без Qt)."""
    title = f"{day} {MONTHS[month - 1]}"
    events = space_history.events_for(month, day, category)
    parts = [f"<h2>{title}</h2>"]
    if events:
        parts.append(f"<p>Событий в подборке: {len(events)}.</p><ul>")
        for e in events:
            ago = years_text(current_year - e.year)
            parts.append(f"<li><p><b>{e.year}</b>"
                         f"{' (' + ago + ')' if ago else ''} · <i>{html.escape(e.category_name)}</i><br>"
                         f"{html.escape(e.text)}</p></li>")
        parts.append("</ul>")
    else:
        parts.append("<p>На этот день в подборке событий нет.</p>")
        near = space_history.nearest(month, day, NEAR_WINDOW_DAYS, category)[:8]
        if near:
            parts.append(f"<p>Ближайшие даты (±{NEAR_WINDOW_DAYS} дней):</p><ul>")
            for shift, e in near:
                when = f"{e.day} {MONTHS[e.month - 1]}"
                parts.append(f"<li><b>{when} {e.year}</b> ({'+' if shift > 0 else ''}{shift} дн.): "
                             f"{html.escape(e.text)}</li>")
            parts.append("</ul>")
    return "".join(parts)


class HistoryPage(BasePage):
    title = "Космическая история"

    def __init__(self, state: AppState):
        super().__init__(state)
        layout = message_page_layout(self)
        layout.addWidget(heading("Этот день в истории космоса"))

        row = QHBoxLayout()
        row.addWidget(QLabel("Дата:"))
        self.date = QDateEdit(self._today())
        self.date.setCalendarPopup(True)
        self.date.setDisplayFormat("dd.MM.yyyy")
        self.date.dateChanged.connect(lambda _: self._render())
        row.addWidget(self.date)
        for text, delta in (("‹ день", -1), ("день ›", 1)):
            btn = QPushButton(text)
            btn.clicked.connect(lambda _=False, d=delta: self.date.setDate(self.date.date().addDays(d)))
            row.addWidget(btn)
        today = QPushButton("Сегодня")
        today.clicked.connect(lambda: self.date.setDate(self._today()))
        row.addWidget(today)
        self.category = QComboBox()
        self.category.addItem("все темы", None)
        for key, name in space_history.CATEGORIES.items():
            self.category.addItem(name, key)
        self.category.currentIndexChanged.connect(lambda _: self._render())
        row.addWidget(self.category)
        row.addStretch(1)
        layout.addLayout(row)

        self.view = QTextBrowser()
        layout.addWidget(self.view, 1)
        layout.addWidget(hint_label(
            f"В подборке {len(space_history.EVENTS)} событий. Она составлена вручную по общеизвестным данным "
            "и не претендует на полноту; даты — по общепринятым источникам (чаще по UTC), у ночных запусков "
            "в разных источниках они могут отличаться на сутки."))

    def _today(self) -> QDate:
        now = datetime.now(get_timezone(self.state.location.timezone))
        return QDate(now.year, now.month, now.day)

    def refresh(self) -> None:
        self._render()

    def _render(self) -> None:
        d = self.date.date()
        self.view.setHtml(render_day(d.month(), d.day(), d.year(), self.category.currentData()))
