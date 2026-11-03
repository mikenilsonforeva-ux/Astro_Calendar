"""Страница «Карта Земли»: положение и траектории выбранных спутников в реальном времени."""
from __future__ import annotations

import html
from datetime import datetime, timezone

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (QCheckBox, QComboBox, QHBoxLayout, QListWidget, QListWidgetItem, QPushButton,
                               QVBoxLayout, QWidget)

from api.celestrak_api import ATTRIBUTION as TLE_ATTRIBUTION, GROUPS
from astronomy import satellites
from services.geodata_service import ATTRIBUTION as GEO_ATTRIBUTION, GeoDataService
from services.satellite_service import SatelliteService
from ui.app_state import AppState
from ui.base_page import BasePage, fill_table, heading, hint_label, make_table, message_page_layout
from ui.earth_widget import COLORS, EarthMapWidget, SatDisplay
from ui.workers import run_async

HEADERS = ["Спутник", "Широта", "Долгота", "Высота, км", "Скорость, км/с", "Над вашим горизонтом", "Освещён Солнцем"]
TICK_MS = 2000
TRACK_EVERY = 10        # трассы пересчитываются каждые 10 тиков (≈ 20 с)
MAX_SELECTED = 8


class EarthPage(BasePage):
    title = "Карта Земли: спутники"

    def __init__(self, state: AppState):
        super().__init__(state)
        self.service = SatelliteService(state.db)
        self.geo = GeoDataService(state.db)
        self._tle_set = None
        self._busy = False
        self._tick_no = 0
        self._tracks: dict[str, dict] = {}
        self._need_tracks = True
        self._request = 0

        layout = message_page_layout(self)
        layout.addWidget(heading("Карта Земли: спутники в реальном времени"))
        self.status = hint_label()
        layout.addWidget(self.status)

        body = QHBoxLayout()
        side = QVBoxLayout()
        self.group = QComboBox()
        for key, name in GROUPS.items():
            self.group.addItem(name, key)
        self.group.currentIndexChanged.connect(lambda _: self._load_tles())
        side.addWidget(self.group)
        self.list = QListWidget()
        self.list.itemChanged.connect(self._selection_changed)
        side.addWidget(self.list, 1)
        self.footprint_cb = QCheckBox("Зона радиовидимости")
        self.footprint_cb.setChecked(True)
        self.footprint_cb.toggled.connect(self._view_options)
        self.night_cb = QCheckBox("Ночная сторона Земли")
        self.night_cb.setChecked(True)
        self.night_cb.toggled.connect(self._view_options)
        side.addWidget(self.footprint_cb)
        side.addWidget(self.night_cb)
        self.update_btn = QPushButton("Обновить TLE (интернет)")
        self.update_btn.clicked.connect(lambda: self._load_tles(force=True))
        side.addWidget(self.update_btn)
        self.geo_btn = QPushButton("Скачать контуры материков")
        self.geo_btn.clicked.connect(self._download_geo)
        side.addWidget(self.geo_btn)
        panel = QWidget()
        panel.setLayout(side)
        panel.setFixedWidth(270)
        body.addWidget(panel)

        right = QVBoxLayout()
        self.map = EarthMapWidget()
        right.addWidget(self.map, 1)
        self.table = make_table(HEADERS)
        self.table.setMaximumHeight(190)
        right.addWidget(self.table)
        body.addLayout(right, 1)
        layout.addLayout(body, 1)
        layout.addWidget(hint_label(
            "Сплошная линия — трасса на ближайшие 2 часа 15 минут, пунктир — пройденный путь за 45 минут; "
            "кружок вокруг спутника — область, откуда он выше горизонта; ⊕ — ваше место. "
            f"{TLE_ATTRIBUTION} {GEO_ATTRIBUTION}"))

        self.timer = QTimer(self)
        self.timer.setInterval(TICK_MS)
        self.timer.timeout.connect(self._tick)

    # ---- жизненный цикл ------------------------------------------------------------------------
    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        self.timer.start()

    def hideEvent(self, event) -> None:  # noqa: N802
        self.timer.stop()
        super().hideEvent(event)

    def refresh(self) -> None:
        self._load_geo()
        self._load_tles()

    # ---- контуры материков -----------------------------------------------------------------------------
    def _load_geo(self) -> None:
        if self.geo.is_available():
            try:
                self.map.set_coast(self.geo.load())
                self.map.notice = ""
                self.geo_btn.setVisible(False)
                return
            except (ValueError, OSError) as exc:
                self.status.setText(f"<span style='color:#d9534f'>{html.escape(str(exc))}</span>")
        self.geo_btn.setVisible(True)
        self.map.notice = ("Контуры материков не загружены — нажмите «Скачать контуры материков» "
                           "(≈ 0,1 МБ, один раз). Спутники и ночная сторона работают и без них.")
        self.map.update()

    def _download_geo(self) -> None:
        self.geo_btn.setEnabled(False)
        run_async(self.geo.download, self._geo_done, self._geo_failed)

    def _geo_done(self, _count) -> None:
        self.geo_btn.setEnabled(True)
        self._load_geo()

    def _geo_failed(self, message: str) -> None:
        self.geo_btn.setEnabled(True)
        self.status.setText(f"<span style='color:#d9534f'>{html.escape(message)}</span>")

    # ---- орбитальные элементы --------------------------------------------------------------------------
    def _load_tles(self, force: bool = False) -> None:
        self.status.setText("Получение орбитальных элементов (CelesTrak)…")
        self.update_btn.setEnabled(False)
        run_async(self.service.load, self._tles_loaded, self._tles_failed, self.group.currentData(), force)

    def _tles_loaded(self, tle_set) -> None:
        self.update_btn.setEnabled(True)
        previous = self._checked_names()
        self._tle_set = tle_set
        self.list.blockSignals(True)
        self.list.clear()
        default = previous or {t.name for t in tle_set.tles if t.name.startswith("ISS")}
        for t in tle_set.tles:
            item = QListWidgetItem(t.name)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Checked if t.name in default else Qt.Unchecked)
            self.list.addItem(item)
        self.list.blockSignals(False)
        warn = "".join(f"<br><span style='color:#d9534f'>{html.escape(w)}</span>" for w in tle_set.warnings)
        self.status.setText(f"Спутников в группе: {len(tle_set.tles)} (выбрано не более {MAX_SELECTED}); "
                            f"элементы получены {tle_set.updated_at or '—'} UTC.{warn}")
        self._need_tracks = True
        self._tick()

    def _tles_failed(self, message: str) -> None:
        self.update_btn.setEnabled(True)
        self.status.setText(f"<span style='color:#d9534f'>{html.escape(message)}</span>")

    def _checked_names(self) -> set[str]:
        return {self.list.item(i).text() for i in range(self.list.count())
                if self.list.item(i).checkState() == Qt.Checked}

    def _selection_changed(self, item: QListWidgetItem) -> None:
        if item.checkState() == Qt.Checked and len(self._checked_names()) > MAX_SELECTED:
            self.list.blockSignals(True)
            item.setCheckState(Qt.Unchecked)
            self.list.blockSignals(False)
            self.status.setText(f"Можно выбрать не более {MAX_SELECTED} спутников.")
            return
        self._need_tracks = True
        self._tick()

    def _view_options(self) -> None:
        self.map.show_footprint = self.footprint_cb.isChecked()
        self.map.show_night = self.night_cb.isChecked()
        self.map.update()

    # ---- обновление в реальном времени -------------------------------------------------------------------
    def _tick(self) -> None:
        if self._tle_set is None or self._busy:
            return
        names = self._checked_names()
        chosen = [t for t in self._tle_set.tles if t.name in names]
        self._tick_no += 1
        with_tracks = self._need_tracks or self._tick_no % TRACK_EVERY == 0
        self._need_tracks = False
        self._busy = True
        self._request += 1
        request = self._request
        run_async(self._work, lambda r: self._done(request, r), self._failed, chosen, with_tracks)

    def _work(self, chosen, with_tracks: bool):
        ctx = self.state.context()
        now = datetime.now(timezone.utc)
        sun = satellites.subsolar_point(ctx, now)
        rows, tracks = [], {}
        for tle in chosen:
            sat = satellites.make_satellite(ctx, tle.name, tle.line1, tle.line2)
            rows.append((tle.name, satellites.current_position(ctx, sat, now)))
            if with_tracks:
                tracks[tle.name] = satellites.ground_track(ctx, sat, now)
        return ctx, sun, rows, tracks

    def _failed(self, message: str) -> None:
        self._busy = False
        self.status.setText(f"<span style='color:#d9534f'>{html.escape(message)}</span>")

    def _done(self, request: int, result) -> None:
        self._busy = False
        if request != self._request:
            return
        ctx, sun, rows, tracks = result
        self._tracks.update(tracks)
        displays, table = [], []
        for i, (name, pos) in enumerate(rows):
            track = self._tracks.get(name)
            display = SatDisplay(name, COLORS[i % len(COLORS)], pos["latitude"], pos["longitude"], pos["height_km"])
            if track:
                display.past = (track["past_lon"], track["past_lat"])
                display.future = (track["future_lon"], track["future_lat"])
            displays.append(display)
            above = f"{pos['alt']:+.0f}°, азимут {pos['az']:.0f}°" if pos["alt"] > 0 else "ниже горизонта"
            table.append([name, f"{pos['latitude']:+.2f}°", f"{pos['longitude']:+.2f}°", f"{pos['height_km']:.0f}",
                          f"{pos['speed_kms']:.2f}", above, "да" if pos["sunlit"] else "в тени"])
        self.map.set_state(displays, sun, (ctx.latitude, ctx.longitude, ctx.place_name))
        fill_table(self.table, table)
