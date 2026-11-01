"""Настройки: места наблюдения и тема оформления."""
from __future__ import annotations

import html

from PySide6.QtWidgets import (QComboBox, QDoubleSpinBox, QFormLayout, QGroupBox, QHBoxLayout,
                               QLineEdit, QListWidget, QListWidgetItem, QMessageBox, QPushButton,
                               QVBoxLayout)

from api.geocoding_api import GeoResult, search_places
from api.http_client import ApiError
from astronomy.time_utils import list_timezones
from database.models import Location
from ui.app_state import AppState
from ui.base_page import BasePage, heading, hint_label, message_page_layout
from ui.theme import THEMES
from ui.workers import run_async


class SettingsPage(BasePage):
    title = "Настройки"

    def __init__(self, state: AppState):
        super().__init__(state)
        self._current_id: int | None = None
        self._geo_results: list[GeoResult] = []
        layout = message_page_layout(self)
        layout.addWidget(heading("Настройки"))

        theme_row = QHBoxLayout()
        theme_row.addWidget(hint_label("Тема оформления:"))
        self.theme_combo = QComboBox()
        for key, name in THEMES.items():
            self.theme_combo.addItem(name, key)
        self.theme_combo.currentIndexChanged.connect(self._theme_changed)
        theme_row.addWidget(self.theme_combo)
        theme_row.addStretch(1)
        layout.addLayout(theme_row)

        box = QGroupBox("Места наблюдения")
        outer = QHBoxLayout(box)
        self.list = QListWidget()
        self.list.currentItemChanged.connect(self._select)
        outer.addWidget(self.list, 1)

        form_box = QVBoxLayout()
        form = QFormLayout()
        self.name = QLineEdit()
        self.name.setPlaceholderText("Название населённого пункта")
        search_row = QHBoxLayout()
        search_row.addWidget(self.name, 1)
        self.find_btn = QPushButton("Найти координаты (интернет)")
        self.find_btn.setToolTip("Поиск через Open-Meteo Geocoding API. Нужно подключение к интернету.")
        self.find_btn.clicked.connect(self._search)
        search_row.addWidget(self.find_btn)
        form.addRow("Название:", search_row)
        self.found = QComboBox()
        self.found.currentIndexChanged.connect(self._apply_found)
        self.found.setVisible(False)
        form.addRow("Найдено:", self.found)
        self.lat = QDoubleSpinBox(); self.lat.setRange(-90, 90); self.lat.setDecimals(5)
        self.lon = QDoubleSpinBox(); self.lon.setRange(-180, 180); self.lon.setDecimals(5)
        self.elev = QDoubleSpinBox(); self.elev.setRange(-500, 9000); self.elev.setDecimals(0)
        self.elev.setSuffix(" м")
        form.addRow("Широта (+ северная):", self.lat)
        form.addRow("Долгота (+ восточная):", self.lon)
        form.addRow("Высота над уровнем моря:", self.elev)
        self.tz = QComboBox()
        self.tz.setEditable(True)
        self.tz.addItems(list_timezones())
        form.addRow("Часовой пояс:", self.tz)
        form_box.addLayout(form)
        buttons = QHBoxLayout()
        for text, slot in (("Новое место", self._new), ("Сохранить", self._save),
                           ("Сделать основным", self._make_default), ("Удалить", self._delete)):
            b = QPushButton(text)
            b.clicked.connect(slot)
            buttons.addWidget(b)
        form_box.addLayout(buttons)
        self.status = hint_label()
        form_box.addWidget(self.status)
        form_box.addStretch(1)
        outer.addLayout(form_box, 2)
        layout.addWidget(box, 1)

    # ---- обновление ----------------------------------------------------------
    def refresh(self) -> None:
        self.theme_combo.blockSignals(True)
        self.theme_combo.setCurrentIndex(max(0, self.theme_combo.findData(self.state.theme)))
        self.theme_combo.blockSignals(False)
        self._reload_list()

    def _reload_list(self, select_id: int | None = None) -> None:
        self.list.blockSignals(True)
        self.list.clear()
        target = select_id if select_id is not None else self.state.location.id
        for loc in self.state.db.list_locations():
            item = QListWidgetItem(loc.name + ("  ★ основное" if loc.is_default else ""))
            item.setData(256, loc)   # Qt.UserRole
            self.list.addItem(item)
            if loc.id == target:
                self.list.setCurrentItem(item)
        self.list.blockSignals(False)
        if self.list.currentItem():
            self._select(self.list.currentItem(), None)

    def _select(self, item: QListWidgetItem | None, _prev) -> None:
        if item is None:
            return
        loc: Location = item.data(256)
        self._current_id = loc.id
        self.name.setText(loc.name)
        self.lat.setValue(loc.latitude)
        self.lon.setValue(loc.longitude)
        self.elev.setValue(loc.elevation_m)
        self.tz.setCurrentText(loc.timezone)

    def _read_form(self) -> Location:
        return Location(name=self.name.text().strip(), latitude=self.lat.value(),
                        longitude=self.lon.value(), elevation_m=self.elev.value(),
                        timezone=self.tz.currentText().strip(), id=self._current_id)

    def _info(self, text: str, error: bool = False) -> None:
        color = "#d9534f" if error else "#5cb85c"
        self.status.setText(f"<span style='color:{color}'>{html.escape(text)}</span>")

    # ---- действия -------------------------------------------------------------
    def _theme_changed(self) -> None:
        key = self.theme_combo.currentData()
        self.state.db.set_setting("theme", key)
        self.state.theme_changed.emit(key)

    def _new(self) -> None:
        self._current_id = None
        self.name.clear()
        self.list.clearSelection()
        self._info("Введите данные нового места и нажмите «Сохранить».")

    def _save(self) -> None:
        loc = self._read_form()
        try:
            if loc.id is None:
                new_id = self.state.db.add_location(loc)
            else:
                self.state.db.update_location(loc)
                new_id = loc.id
        except ValueError as exc:
            self._info(str(exc), error=True)
            return
        self._current_id = new_id
        self._reload_list(new_id)
        self.state.notify_location_changed()
        self._info("Место сохранено.")

    def _make_default(self) -> None:
        if self._current_id is None:
            self._info("Сначала сохраните или выберите место.", error=True)
            return
        self.state.db.set_default_location(self._current_id)
        self._reload_list(self._current_id)
        self.state.notify_location_changed()
        self._info("Основное место изменено. Все расчёты используют его.")

    def _delete(self) -> None:
        if self._current_id is None:
            return
        if QMessageBox.question(self, "Удаление", "Удалить выбранное место?") != QMessageBox.Yes:
            return
        try:
            self.state.db.delete_location(self._current_id)
        except ValueError as exc:
            self._info(str(exc), error=True)
            return
        self._current_id = None
        self._reload_list()
        self.state.notify_location_changed()

    def _search(self) -> None:
        name = self.name.text()
        self._info("Поиск…")
        self.find_btn.setEnabled(False)
        run_async(lambda: search_places(name), self._found, self._search_failed)

    def _search_failed(self, message: str) -> None:
        self.find_btn.setEnabled(True)
        self._info(message, error=True)

    def _found(self, results: list[GeoResult]) -> None:
        self.find_btn.setEnabled(True)
        self._geo_results = results
        self.found.blockSignals(True)
        self.found.clear()
        for r in results:
            self.found.addItem(r.label)
        self.found.blockSignals(False)
        self.found.setVisible(bool(results))
        if not results:
            self._info("Ничего не найдено. Введите координаты вручную.", error=True)
            return
        self._info(f"Найдено вариантов: {len(results)}. Выберите нужный и нажмите «Сохранить».")
        self._apply_found(0)

    def _apply_found(self, index: int) -> None:
        if not 0 <= index < len(self._geo_results):
            return
        r = self._geo_results[index]
        self.name.setText(r.name)
        self.lat.setValue(r.latitude)
        self.lon.setValue(r.longitude)
        self.elev.setValue(r.elevation_m)
        self.tz.setCurrentText(r.timezone)
