"""Страница «Звёздное небо»: интерактивная карта, управление временем и слоями."""
from __future__ import annotations

import html
from datetime import datetime, timedelta, timezone

from PySide6.QtCore import QDateTime
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDateTimeEdit, QGroupBox, QHBoxLayout, QLabel,
                               QPushButton, QTextBrowser, QVBoxLayout, QWidget)

from astronomy.sky_snapshot import build_snapshot
from astronomy.time_utils import get_timezone
from services.star_service import ATTRIBUTION, StarService
from ui.app_state import AppState
from ui.base_page import BasePage, heading, hint_label, message_page_layout
from ui.sky_widget import MODES, SkyMapWidget, describe_object
from ui.workers import run_async

LAYERS = [("star_names", "Названия звёзд"), ("asterisms", "Фигуры созвездий"),
          ("constellation_names", "Названия созвездий"), ("bodies", "Солнце, Луна, планеты"),
          ("milky_way", "Млечный Путь (схема)"), ("ecliptic", "Эклиптика"),
          ("grid", "Координатная сетка"), ("deep_sky", "Объекты каталога (до 9ᵐ)"),
          ("below_horizon", "Показывать под горизонтом")]
DEEP_SKY_MAGNITUDE = 9.0


class SkyPage(BasePage):
    title = "Звёздное небо"

    def __init__(self, state: AppState):
        super().__init__(state)
        self.stars = StarService(state.db)
        self._request = 0
        layout = message_page_layout(self)
        layout.addWidget(heading("Звёздное небо"))
        self.status = hint_label()
        layout.addWidget(self.status)

        row = QHBoxLayout()
        row.addWidget(QLabel("Момент (местное время):"))
        self.dt_edit = QDateTimeEdit(self._now_local())
        self.dt_edit.setCalendarPopup(True)
        self.dt_edit.setDisplayFormat("dd.MM.yyyy HH:mm")
        self.dt_edit.dateTimeChanged.connect(lambda _: self.rebuild())
        row.addWidget(self.dt_edit)
        for text, delta in (("−1 сут", -1440), ("−1 ч", -60), ("+1 ч", 60), ("+1 сут", 1440)):
            btn = QPushButton(text)
            btn.clicked.connect(lambda _=False, d=delta: self._shift(d))
            row.addWidget(btn)
        now = QPushButton("Сейчас")
        now.clicked.connect(lambda: self.dt_edit.setDateTime(self._now_local()))
        row.addWidget(now)
        row.addSpacing(12)
        self.mode = QComboBox()
        self.mode.addItem("Горизонтальная система (азимут/высота)", "horizontal")
        self.mode.addItem("Экваториальная система (α/δ)", "equatorial")
        self.mode.currentIndexChanged.connect(self._mode_changed)
        row.addWidget(self.mode)
        row.addStretch(1)
        layout.addLayout(row)

        body = QHBoxLayout()
        self.map = SkyMapWidget()
        self.map.object_selected.connect(self._object_selected)
        body.addWidget(self.map, 1)

        side = QVBoxLayout()
        view_box = QGroupBox("Направление")
        grid = QHBoxLayout(view_box)
        for label, az in (("С", 0.0), ("В", 90.0), ("Ю", 180.0), ("З", 270.0)):
            btn = QPushButton(label)
            btn.setFixedWidth(36)
            btn.clicked.connect(lambda _=False, a=az: self.map.look_at_direction(a))
            grid.addWidget(btn)
        zenith = QPushButton("Зенит")
        zenith.clicked.connect(self.map.reset_view)
        grid.addWidget(zenith)
        side.addWidget(view_box)

        zoom_box = QHBoxLayout()
        zin, zout = QPushButton("Приблизить"), QPushButton("Отдалить")
        zin.clicked.connect(lambda: self.map.zoom(0.7))
        zout.clicked.connect(lambda: self.map.zoom(1 / 0.7))
        zoom_box.addWidget(zin)
        zoom_box.addWidget(zout)
        side.addLayout(zoom_box)

        layers_box = QGroupBox("Слои")
        lv = QVBoxLayout(layers_box)
        for key, text in LAYERS:
            cb = QCheckBox(text)
            cb.setChecked(self.map.layers[key])
            cb.toggled.connect(lambda checked, k=key: self.map.set_layer(k, checked))
            lv.addWidget(cb)
        side.addWidget(layers_box)

        self.download_btn = QPushButton("Скачать каталог звёзд (интернет)")
        self.download_btn.clicked.connect(self._download)
        side.addWidget(self.download_btn)
        self.info = QTextBrowser()
        self.info.setMinimumHeight(180)
        self.info.setHtml("<p>Щёлкните по объекту на карте. Колесо мыши — масштаб, "
                          "перетаскивание — смена направления.</p>")
        side.addWidget(self.info, 1)
        panel = QWidget()
        panel.setLayout(side)
        panel.setFixedWidth(290)
        body.addWidget(panel)
        layout.addLayout(body, 1)
        layout.addWidget(hint_label(ATTRIBUTION + " Высота и азимут геометрические, без учёта рефракции."))

    # ---- время -----------------------------------------------------------------------
    def _tz(self):
        return get_timezone(self.state.location.timezone)

    def _now_local(self) -> QDateTime:
        now = datetime.now(self._tz())
        return QDateTime(now.year, now.month, now.day, now.hour, now.minute)

    def _shift(self, minutes: int) -> None:
        self.dt_edit.setDateTime(self.dt_edit.dateTime().addSecs(minutes * 60))

    def _mode_changed(self) -> None:
        self.map.set_mode(self.mode.currentData())

    # ---- построение снимка --------------------------------------------------------------
    def refresh(self) -> None:
        self.dt_edit.blockSignals(True)
        self.dt_edit.setDateTime(self._now_local())
        self.dt_edit.blockSignals(False)
        self.rebuild()

    def rebuild(self) -> None:
        if not self.stars.is_available():
            self.status.setText("Звёздный каталог не загружен. Нажмите «Скачать каталог звёзд» "
                                "(≈ 50 МБ из Hipparcos, один раз; после обработки хранится ≈ 1 МБ).")
            self.download_btn.setVisible(True)
            return
        self.download_btn.setVisible(False)
        self._request += 1
        request = self._request
        self.status.setText("Расчёт положений…")
        run_async(self._work, lambda snap: self._built(request, snap), self._failed,
                  self.dt_edit.dateTime().toPython())

    def _work(self, local_naive: datetime):
        ctx = self.state.context()
        when = local_naive.replace(tzinfo=ctx.tz).astimezone(timezone.utc)
        cat = self.stars.load()
        centers = self.stars.constellation_centers(ctx)
        deep = self.state.db.list_objects(max_magnitude=DEEP_SKY_MAGNITUDE)
        deep = [o for o in deep if o.get("ra_deg") is not None and o.get("dec_deg") is not None]
        return ctx, build_snapshot(ctx, when, cat, centers, deep)

    def _built(self, request: int, result) -> None:
        if request != self._request:
            return      # уже запрошен более новый момент
        ctx, snap = result
        self.map.set_snapshot(snap)
        sun_alt = snap.sun_alt
        sky = ("день" if sun_alt > -0.8 else "гражданские сумерки" if sun_alt > -6 else
               "навигационные сумерки" if sun_alt > -12 else "астрономические сумерки" if sun_alt > -18
               else "ночь")
        self.status.setText(f"{html.escape(ctx.place_name)}: {ctx.local(snap.when_utc):%d.%m.%Y %H:%M} "
                            f"({ctx.tz.key}); Солнце на высоте {sun_alt:+.1f}° — {sky}. "
                            f"Звёзд на карте: {len(snap.star_mag)}.")

    def _failed(self, message: str) -> None:
        self.status.setText(f"<span style='color:#d9534f'>{html.escape(message)}</span>")

    def _object_selected(self, info: dict) -> None:
        self.info.setHtml(describe_object({**info, "name": html.escape(str(info["name"])),
                                           "detail": html.escape(str(info.get("detail", "")))}))

    # ---- загрузка каталога --------------------------------------------------------------
    def _download(self) -> None:
        self.download_btn.setEnabled(False)
        self.status.setText("Загрузка каталога Hipparcos (≈ 50 МБ)… это может занять несколько минут.")
        run_async(self.stars.download, self._downloaded, self._download_failed)

    def _downloaded(self, count: int) -> None:
        self.download_btn.setEnabled(True)
        self.rebuild()

    def _download_failed(self, message: str) -> None:
        self.download_btn.setEnabled(True)
        self.status.setText(f"<span style='color:#d9534f'>{html.escape(message)}</span>")
