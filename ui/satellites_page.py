"""Страница «Искусственные спутники»: пролёты МКС и ярких спутников над местом наблюдения."""
from __future__ import annotations

import html
from datetime import datetime, timezone

from PySide6.QtWidgets import (QCheckBox, QComboBox, QHBoxLayout, QLabel, QPushButton, QSpinBox)

from api.celestrak_api import ATTRIBUTION, GROUPS
from astronomy import satellites
from services.satellite_service import SatelliteService
from ui.app_state import AppState
from ui.base_page import BasePage, fill_table, heading, hint_label, make_table, message_page_layout
from ui.workers import run_async

HEADERS = ["Спутник", "Восход", "Азимут восхода", "Кульминация", "Макс. высота", "Азимут max",
           "Заход", "Азимут захода", "Длительность", "Видимость"]


class SatellitesPage(BasePage):
    title = "Искусственные спутники"

    def __init__(self, state: AppState):
        super().__init__(state)
        self.service = SatelliteService(state.db)
        self._names: list[str] = []
        self._request = 0
        layout = message_page_layout(self)
        layout.addWidget(heading("Искусственные спутники"))
        self.status = hint_label()
        layout.addWidget(self.status)

        row = QHBoxLayout()
        self.group = QComboBox()
        for key, name in GROUPS.items():
            self.group.addItem(name, key)
        row.addWidget(self.group)
        self.sat = QComboBox()
        self.sat.setMinimumWidth(220)
        row.addWidget(self.sat)
        row.addWidget(QLabel("дней:"))
        self.days = QSpinBox()
        self.days.setRange(1, 10)
        self.days.setValue(5)
        row.addWidget(self.days)
        row.addWidget(QLabel("мин. высота, °:"))
        self.min_alt = QSpinBox()
        self.min_alt.setRange(0, 60)
        self.min_alt.setValue(int(satellites.MIN_ALTITUDE))
        row.addWidget(self.min_alt)
        self.only_visible = QCheckBox("только видимые глазом")
        row.addWidget(self.only_visible)
        self.calc_btn = QPushButton("Рассчитать пролёты")
        self.calc_btn.clicked.connect(self._calculate)
        row.addWidget(self.calc_btn)
        self.update_btn = QPushButton("Обновить TLE (интернет)")
        self.update_btn.clicked.connect(lambda: self._load_tles(force=True))
        row.addWidget(self.update_btn)
        row.addStretch(1)
        layout.addLayout(row)

        self.position = hint_label()
        layout.addWidget(self.position)
        self.table = make_table(HEADERS)
        layout.addWidget(self.table, 1)
        layout.addWidget(hint_label(
            ATTRIBUTION + " «Виден» — спутник освещён Солнцем, а у вас Солнце ниже −6°. Яркость не оценивается. "
            "Точность падает, если орбитальные элементы старше недели; время — местное."))
        self.group.currentIndexChanged.connect(lambda _: self._load_tles())
        self.sat.currentIndexChanged.connect(lambda _: self._calculate())
        self._ready = False

    # ---- загрузка TLE -----------------------------------------------------------------------
    def refresh(self) -> None:
        self._load_tles()

    def _load_tles(self, force: bool = False) -> None:
        self._ready = False
        self.status.setText("Получение орбитальных элементов (CelesTrak)…")
        self.update_btn.setEnabled(False)
        run_async(self.service.load, self._tles_loaded, self._failed, self.group.currentData(), force)

    def _tles_loaded(self, tle_set) -> None:
        self.update_btn.setEnabled(True)
        self._tle_set = tle_set
        self._names = [t.name for t in tle_set.tles]
        self.sat.blockSignals(True)
        self.sat.clear()
        for name in self._names:
            self.sat.addItem(name)
        iss = next((i for i, n in enumerate(self._names) if n.startswith("ISS")), 0)
        self.sat.setCurrentIndex(iss)
        self.sat.blockSignals(False)
        source = "из сохранённого кэша" if tle_set.from_cache else "загружены только что"
        warn = "".join(f"<br><span style='color:#d9534f'>{html.escape(w)}</span>" for w in tle_set.warnings)
        self.status.setText(f"Спутников в группе: {len(self._names)}; элементы {source} "
                            f"(получены {tle_set.updated_at or '—'} UTC).{warn}")
        self._ready = True
        self._calculate()

    def _failed(self, message: str) -> None:
        self.update_btn.setEnabled(True)
        self.calc_btn.setEnabled(True)
        self.status.setText(f"<span style='color:#d9534f'>{html.escape(message)}</span>")

    # ---- расчёт ---------------------------------------------------------------------------------
    def _calculate(self) -> None:
        if not self._ready or self.sat.currentIndex() < 0:
            return
        self._request += 1
        request = self._request
        tle = self._tle_set.tles[self.sat.currentIndex()]
        self.calc_btn.setEnabled(False)
        self.position.setText("Расчёт пролётов…")
        run_async(self._work, lambda r: self._done(request, r), self._failed,
                  tle, self.days.value(), float(self.min_alt.value()))

    def _work(self, tle, days: int, min_alt: float):
        ctx = self.state.context()
        sat = satellites.make_satellite(ctx, tle.name, tle.line1, tle.line2)
        now = datetime.now(timezone.utc)
        return (ctx, satellites.compute_passes(ctx, sat, now, days, min_alt),
                satellites.current_position(ctx, sat, now), satellites.tle_age_days(sat, now))

    def _done(self, request: int, result) -> None:
        if request != self._request:
            return
        ctx, passes, pos, age = result
        self.calc_btn.setEnabled(True)
        shown = [p for p in passes if p.visible] if self.only_visible.isChecked() else passes
        fill_table(self.table, [satellites.describe_pass(p, ctx.tz) for p in shown])
        lat_s = f"{abs(pos['latitude']):.2f}°{'с' if pos['latitude'] >= 0 else 'ю'}.ш."
        lon_s = f"{abs(pos['longitude']):.2f}°{'в' if pos['longitude'] >= 0 else 'з'}.д."
        above = (f"над горизонтом (высота {pos['alt']:.0f}°, азимут {pos['az']:.0f}°)" if pos["alt"] > 0
                 else "под горизонтом")
        stale = (f" <span style='color:#d9534f'>Элементы старше {satellites.TLE_STALE_DAYS} суток — "
                 "обновите TLE.</span>" if age > satellites.TLE_STALE_DAYS else "")
        self.position.setText(
            f"Сейчас: над точкой {lat_s} {lon_s}, высота орбиты {pos['height_km']:.0f} км, {above}; "
            f"{'освещён Солнцем' if pos['sunlit'] else 'в тени Земли'}. "
            f"Пролётов за {self.days.value()} сут.: {len(passes)}, показано {len(shown)}. "
            f"Возраст TLE: {age:.1f} сут.{stale}")
