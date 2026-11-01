"""Главное окно: боковая панель навигации и рабочая область."""
from __future__ import annotations

from PySide6.QtWidgets import QHBoxLayout, QListWidget, QMainWindow, QStackedWidget, QWidget

import config
from ui.app_state import AppState
from ui.base_page import BasePage
from ui.calendar_page import CalendarPage
from ui.event_list_page import make_eclipse_page, make_meteor_page
from ui.home_page import HomePage
from ui.moon_page import MoonPage
from ui.placeholder_page import PlaceholderPage
from ui.planets_page import PlanetsPage
from ui.settings_page import SettingsPage
from ui.sun_page import SunPage
from ui.update_page import UpdatePage


class MainWindow(QMainWindow):
    def __init__(self, state: AppState):
        super().__init__()
        self.state = state
        self.setWindowTitle(f"{config.APP_TITLE} {config.APP_VERSION}")
        self.resize(1280, 800)
        self.setMinimumSize(900, 600)

        pages: list[BasePage] = [
            HomePage(state),
            CalendarPage(state),
            SunPage(state),
            MoonPage(state),
            PlanetsPage(state),
            PlaceholderPage(state, "Звёздное небо", "этап 6",
                            "Интерактивная карта неба: звёзды, созвездия, планеты, Солнце, Луна, "
                            "горизонт, масштабирование и смена даты."),
            PlaceholderPage(state, "Каталог небесных объектов", "этап 5",
                            "Каталоги Мессье и NGC, поиск и фильтрация, данные SIMBAD/VizieR."),
            make_meteor_page(state),
            make_eclipse_page(state),
            PlaceholderPage(state, "Астрономическая погода", "этап 4",
                            "Прогноз Open-Meteo и индекс пригодности ночи (0–100) для наблюдений."),
            PlaceholderPage(state, "Солнечная активность", "этап 4/7",
                            "Данные NOAA SWPC: вспышки, КВМ, индекс Kp, прогноз магнитных бурь."),
            PlaceholderPage(state, "Искусственные спутники", "этап 7",
                            "TLE из CelesTrak, МКС, расчёт пролётов над местом наблюдения."),
            SettingsPage(state),
            UpdatePage(state),
        ]
        self.pages = pages
        self.nav = QListWidget()
        self.nav.setFixedWidth(230)
        self.stack = QStackedWidget()
        for page in pages:
            self.nav.addItem(page.title)
            self.stack.addWidget(page)
        self.nav.currentRowChanged.connect(self._switch)

        central = QWidget()
        layout = QHBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.nav)
        layout.addWidget(self.stack, 1)
        self.setCentralWidget(central)

        state.location_changed.connect(self._update_status)
        state.data_updated.connect(self._update_status)
        self._update_status()
        self.nav.setCurrentRow(0)

    def _switch(self, row: int) -> None:
        if row < 0:
            return
        self.stack.setCurrentIndex(row)
        self.pages[row].on_show()

    def _update_status(self) -> None:
        loc = self.state.location
        eph = config.find_ephemeris_file()
        eph_text = f"эфемериды: {eph.name}" if eph else "эфемериды не загружены"
        self.statusBar().showMessage(
            f"Место: {loc.name} ({loc.latitude:.3f}, {loc.longitude:.3f}) · {loc.timezone} · {eph_text}")
