"""Каталог небесных объектов: поиск, фильтры, карточка объекта с условиями видимости."""
from __future__ import annotations

import html
from datetime import datetime, timezone

from PySide6.QtWidgets import (QCheckBox, QComboBox, QDoubleSpinBox, QHBoxLayout, QLabel, QLineEdit,
                               QPushButton, QSplitter, QTextBrowser, QVBoxLayout, QWidget)

from api.catalog_api import ATTRIBUTION, TYPE_NAMES_RU
from astronomy import visibility
from astronomy.constellations_ru import constellation_ru
from astronomy.coordinates import compass_point, format_dms, format_hms
from astronomy.time_utils import format_time
from services.catalog_service import SORTS, CatalogService, display_designation, object_links
from ui.app_state import AppState
from ui.base_page import BasePage, fill_table, heading, hint_label, make_table, message_page_layout
from ui.workers import run_async


class CatalogPage(BasePage):
    title = "Каталог небесных объектов"

    def __init__(self, state: AppState):
        super().__init__(state)
        self.service = CatalogService(state.db)
        self._rows: list[dict] = []
        layout = message_page_layout(self)
        layout.addWidget(heading("Каталог небесных объектов"))
        self.status = hint_label()
        layout.addWidget(self.status)

        top = QHBoxLayout()
        self.download_btn = QPushButton("Скачать / обновить каталог (интернет)")
        self.download_btn.clicked.connect(self._download)
        top.addWidget(self.download_btn)
        top.addStretch(1)
        layout.addLayout(top)

        filters = QHBoxLayout()
        self.query = QLineEdit()
        self.query.setPlaceholderText("Поиск: M31, NGC 7000, Андромеды, Orion…")
        self.query.setClearButtonEnabled(True)
        self.query.returnPressed.connect(self._search)
        filters.addWidget(self.query, 2)
        self.type_combo = QComboBox()
        self.type_combo.currentIndexChanged.connect(self._search)
        filters.addWidget(self.type_combo)
        self.const_combo = QComboBox()
        self.const_combo.currentIndexChanged.connect(self._search)
        filters.addWidget(self.const_combo)
        filters.addWidget(QLabel("блеск до"))
        self.mag = QDoubleSpinBox()
        self.mag.setRange(0, 30)
        self.mag.setValue(30)
        self.mag.setSingleStep(0.5)
        self.mag.setToolTip("30 — без ограничения")
        self.mag.valueChanged.connect(self._search)
        filters.addWidget(self.mag)
        self.messier = QCheckBox("только Мессье")
        self.messier.toggled.connect(self._search)
        filters.addWidget(self.messier)
        self.sort = QComboBox()
        for key, name in SORTS.items():
            self.sort.addItem("сортировка " + name, key)
        self.sort.currentIndexChanged.connect(self._search)
        filters.addWidget(self.sort)
        layout.addLayout(filters)

        split = QSplitter()
        self.table = make_table(["Обозначение", "Название", "Тип", "Созвездие", "Блеск", "Размер, ′"])
        self.table.itemSelectionChanged.connect(self._show_details)
        split.addWidget(self.table)
        self.details = QTextBrowser()
        self.details.setOpenExternalLinks(True)
        split.addWidget(self.details)
        split.setStretchFactor(0, 3)
        split.setStretchFactor(1, 2)
        layout.addWidget(split, 1)
        layout.addWidget(hint_label(ATTRIBUTION))
        self._filters_ready = False

    # ---- состояние каталога ---------------------------------------------------------
    def refresh(self) -> None:
        st = self.service.status()
        if st.count == 0:
            restored = 0
            try:
                restored = self.service.import_local_if_present()
            except Exception as exc:    # повреждённый локальный файл
                self.status.setText(f"<span style='color:#d9534f'>{html.escape(str(exc))}</span>")
            st = self.service.status() if restored else st
        if st.count == 0:
            self.status.setText("Каталог не загружен. Нажмите «Скачать / обновить каталог» "
                                "(≈ 4 МБ, нужен интернет; после этого каталог работает автономно).")
            self.table.setRowCount(0)
            return
        self.status.setText(f"Объектов в каталоге: {st.count}. Последняя загрузка: {st.last_update or '—'} (UTC).")
        self._fill_filters()
        self._search()

    def _fill_filters(self) -> None:
        self._filters_ready = False
        self.type_combo.blockSignals(True)
        self.const_combo.blockSignals(True)
        self.type_combo.clear()
        self.type_combo.addItem("все типы", None)
        for key in self.state.db.object_types():
            self.type_combo.addItem(TYPE_NAMES_RU.get(key, key), key)
        self.const_combo.clear()
        self.const_combo.addItem("все созвездия", None)
        for abbr, ru in self.service.constellations():
            self.const_combo.addItem(ru, abbr)
        self.type_combo.blockSignals(False)
        self.const_combo.blockSignals(False)
        self._filters_ready = True

    def _download(self) -> None:
        self.download_btn.setEnabled(False)
        self.status.setText("Загрузка каталога OpenNGC…")
        run_async(self.service.download, self._downloaded, self._download_failed)

    def _downloaded(self, count: int) -> None:
        self.download_btn.setEnabled(True)
        self.refresh()

    def _download_failed(self, message: str) -> None:
        self.download_btn.setEnabled(True)
        self.status.setText(f"<span style='color:#d9534f'>{html.escape(message)}</span>")

    # ---- поиск ------------------------------------------------------------------------
    def _search(self, *_args) -> None:
        if not self._filters_ready:
            return
        type_key = self.type_combo.currentData()
        mag = self.mag.value()
        self._rows = self.service.search(
            self.query.text(), [type_key] if type_key else None, self.const_combo.currentData(),
            self.messier.isChecked(), None if mag >= 30 else mag, self.sort.currentData())
        fill_table(self.table, [[
            display_designation(o), o["name_ru"] or o["name"] or "", TYPE_NAMES_RU.get(o["object_type"], ""),
            constellation_ru(o["constellation"]) if o["constellation"] else "",
            "—" if o["magnitude"] is None else f"{o['magnitude']:.1f}",
            "—" if o["size_arcmin"] is None else f"{o['size_arcmin']:.1f}"] for o in self._rows])
        self.details.clear()

    def _show_details(self) -> None:
        sel = self.table.selectionModel().selectedRows()
        if not sel or sel[0].row() >= len(self._rows):
            return
        obj = self._rows[sel[0].row()]
        self._current = obj
        self.details.setHtml("Расчёт условий видимости…")
        run_async(self._visibility, lambda info: self._render(obj, info), lambda m: self._render(obj, m), obj)

    def _visibility(self, obj: dict):
        ctx = self.state.context()
        return ctx, visibility.fixed_object_info(ctx, obj["ra_deg"], obj["dec_deg"], datetime.now(timezone.utc))

    def _render(self, obj: dict, result) -> None:
        if obj is not getattr(self, "_current", None):
            return      # пользователь уже выбрал другой объект
        rows = [
            ("Обозначение", display_designation(obj)),
            ("Название", html.escape(obj["name_ru"] or obj["name"] or "—")),
            ("Тип", TYPE_NAMES_RU.get(obj["object_type"], "—")),
            ("Созвездие", constellation_ru(obj["constellation"]) if obj["constellation"] else "—"),
            ("Прямое восхождение (J2000)", format_hms(obj["ra_deg"] / 15.0)),
            ("Склонение (J2000)", format_dms(obj["dec_deg"])),
            ("Звёздная величина", "—" if obj["magnitude"] is None else f"{obj['magnitude']:.1f}ᵐ"),
            ("Угловые размеры", self._size_text(obj)),
            ("Расстояние", "нет в каталоге"),
        ]
        body = "".join(f"<tr><td>{a}</td><td><b>{b}</b></td></tr>" for a, b in rows)
        local = ""
        if isinstance(result, str):
            local = f"<p style='color:#d9534f'>{html.escape(result)}</p>"
        else:
            ctx, info = result
            if info.never_rises:
                state = "в вашей широте <b>никогда не восходит</b>"
            elif info.circumpolar:
                state = "<b>незаходящий</b> объект (виден в течение всех суток)"
            else:
                state = f"восход {format_time(info.rise)}, заход {format_time(info.set)}"
            local = (f"<h4>Из «{html.escape(ctx.place_name)}» сейчас</h4>"
                     f"<p>Высота {info.altitude:+.1f}°, азимут {info.azimuth:.0f}° ({compass_point(info.azimuth)}).<br>"
                     f"Верхняя кульминация {format_time(info.transit)}, максимальная высота {info.max_altitude:.0f}°; "
                     f"{state}.</p>"
                     "<p><i>Видимость геометрическая; для слабых объектов нужны тёмное небо без Луны и подходящий инструмент.</i></p>")
        links = "".join(f"<li><a href='{u}'>{html.escape(n)}</a></li>" for n, u in object_links(obj))
        self.details.setHtml(f"<h3>{html.escape(display_designation(obj))}</h3><table cellspacing='4'>{body}</table>"
                             f"{local}<p>Ссылки:</p><ul>{links}</ul>")

    @staticmethod
    def _size_text(obj: dict) -> str:
        if obj["size_arcmin"] is None:
            return "—"
        if obj["size_minor_arcmin"]:
            return f"{obj['size_arcmin']:.1f}′ × {obj['size_minor_arcmin']:.1f}′"
        return f"{obj['size_arcmin']:.1f}′"
