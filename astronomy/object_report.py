"""Подробная характеристика объекта карты неба: звезда, Солнце, Луна, планета, объект каталога.

Динамические величины (положение, восход/заход, расстояние) считаются для выбранного места и момента;
физические характеристики Солнца, Луны и планет — справочные константы. Если данных нет
в используемом каталоге (например, спектральный класс звезды), это указывается прямо.
"""
from __future__ import annotations

import html
import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta

import numpy as np

from astronomy import skymap
from astronomy.constellations_ru import constellation_ru
from astronomy.context import AstroContext
from astronomy.coordinates import compass_point, format_dms, format_hms
from astronomy.time_utils import format_duration, format_time

PC_TO_LY = 3.26156
AU_KM = 149_597_870.7
LIGHT_SECONDS_PER_AU = 499.0048
SUN_ABS_MAG_V = 4.83
MIN_RELIABLE_PARALLAX_MAS = 3.0

# Справочные данные планет: масса (кг), большая полуось (а. е.), сидерический период обращения, период вращения.
PLANET_FACTS = {
    "mercury": (3.301e23, 0.387, "87,97 сут", "58,65 сут"),
    "venus": (4.867e24, 0.723, "224,70 сут", "243,02 сут (обратное вращение)"),
    "mars": (6.417e23, 1.524, "686,98 сут (1,88 года)", "24 ч 37 мин"),
    "jupiter": (1.898e27, 5.203, "11,86 года", "9 ч 56 мин"),
    "saturn": (5.683e26, 9.537, "29,46 года", "10 ч 33 мин"),
    "uranus": (8.681e25, 19.19, "84,02 года", "17 ч 14 мин (обратное вращение)"),
    "neptune": (1.024e26, 30.07, "164,8 года", "16 ч 06 мин"),
}


@dataclass
class ObjectReport:
    title: str
    subtitle: str
    sections: list[tuple[str, list[tuple[str, str]]]] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    links: list[tuple[str, str]] = field(default_factory=list)


def _mag(value: float | None) -> str:
    return "—" if value is None else f"{value:+.2f}ᵐ"


def _sci(value: float, unit: str) -> str:
    mantissa, exp = f"{value:.3e}".split("e")
    return f"{mantissa.replace('.', ',')} × 10^{int(exp)} {unit}"


def _distance_text(d_pc: float) -> str:
    ly = d_pc * PC_TO_LY
    ly_text = f"{ly:.1f}" if ly < 100 else f"{ly:,.0f}".replace(",", " ")
    return f"{ly_text} св. лет ({d_pc:,.1f} пк)".replace(",", " ")


def _coordinates_rows(ra_deg: float, dec_deg: float) -> list[tuple[str, str]]:
    l, b = skymap.icrs_to_galactic(ra_deg, dec_deg)
    return [("Прямое восхождение (J2000)", format_hms(ra_deg / 15.0)), ("Склонение (J2000)", format_dms(dec_deg)),
            ("Галактические координаты", f"l = {float(l):.2f}°, b = {float(b):+.2f}°")]


def constellation_of(ctx: AstroContext, ra_deg: float, dec_deg: float) -> str:
    from skyfield.positionlib import position_of_radec
    return constellation_ru(ctx.constellation_at(position_of_radec(ra_deg / 15.0, dec_deg)))


def _sun_alt(ctx: AstroContext, when_utc: datetime) -> float:
    from astronomy.visibility import altitude_azimuth
    return altitude_azimuth(ctx, ctx.eph["sun"], when_utc)[0]


def _fixed_rows(ctx: AstroContext, ra_deg: float, dec_deg: float, when_utc: datetime) -> list[tuple[str, str]]:
    from astronomy import visibility
    info = visibility.fixed_object_info(ctx, ra_deg, dec_deg, when_utc)
    rows = [("Высота / азимут", f"{info.altitude:+.1f}° / {info.azimuth:.0f}° ({compass_point(info.azimuth)})"),
            ("Сейчас", visibility.sky_state(_sun_alt(ctx, when_utc), info.altitude)),
            ("Максимальная высота", f"{info.max_altitude:.0f}° (в верхней кульминации)")]
    if info.never_rises:
        rows.append(("Восход и заход", "объект никогда не восходит на вашей широте"))
    elif info.circumpolar:
        rows.append(("Восход и заход", "незаходящий объект (над горизонтом круглые сутки)"))
    else:
        rows.append(("Восход", format_time(info.rise)))
        rows.append(("Заход", format_time(info.set)))
    rows.append(("Верхняя кульминация", format_time(info.transit)))
    return rows


# ---------------------------------------------------------------------------
def star_report(ctx: AstroContext, info: dict, when_utc: datetime) -> ObjectReport:
    ra, dec, mag = info["ra"], info["dec"], info["mag"]
    hip = info.get("hip")
    name = info["name"]
    report = ObjectReport(name, f"Звезда · созвездие {constellation_of(ctx, ra, dec)}")
    general = [("Название", name if not name.startswith("HIP") else "собственного имени в справочнике нет"),
               ("Обозначение", f"HIP {hip}" if hip else "—"),
               ("Созвездие", constellation_of(ctx, ra, dec)),
               ("Видимая звёздная величина (V)", _mag(mag))]
    plx = info.get("plx")
    if plx is not None and plx >= MIN_RELIABLE_PARALLAX_MAS:
        d_pc = 1000.0 / plx
        abs_mag = mag + 5.0 - 5.0 * math.log10(d_pc)
        lum = 10 ** ((SUN_ABS_MAG_V - abs_mag) / 2.5)
        general += [("Параллакс", f"{plx:.2f} мс дуги"),
                    ("Расстояние", _distance_text(d_pc)),
                    ("Абсолютная звёздная величина", _mag(abs_mag)),
                    ("Светимость (приближённо)", f"{lum:,.0f} L☉".replace(",", " ") if lum >= 10 else f"{lum:.2f} L☉")]
        report.notes.append("Светимость вычислена по визуальной величине без болометрической поправки и без "
                            "учёта межзвёздного поглощения — это оценка порядка величины.")
    else:
        general.append(("Расстояние", "параллакс в каталоге слишком мал или не определён — "
                                       "расстояние надёжно не вычисляется"))
    general.append(("Спектральный класс", "нет в используемом каталоге (в приложении только положения и блеск)"))
    report.sections.append(("Общие сведения", general))

    sky = _coordinates_rows(ra, dec)
    pm_ra, pm_dec = info.get("pm_ra"), info.get("pm_dec")
    if pm_ra is not None and pm_dec is not None:
        sky.append(("Собственное движение", f"μα* = {pm_ra:+.1f}, μδ = {pm_dec:+.1f} мс дуги/год "
                                            f"(всего {math.hypot(pm_ra, pm_dec):.1f})"))
    report.sections.append(("Координаты", sky))
    report.sections.append((f"Условия наблюдения из «{ctx.place_name}»", _fixed_rows(ctx, ra, dec, when_utc)))
    if hip:
        from urllib.parse import quote
        report.links.append(("SIMBAD", "https://simbad.cds.unistra.fr/simbad/sim-id?Ident=" + quote(f"HIP {hip}")))
    return report


def sun_report(ctx: AstroContext, when_utc: datetime) -> ObjectReport:
    from astronomy import sun
    pos = sun.position(ctx, when_utc)
    day = sun.day_info(ctx, ctx.local(when_utc).date())
    diameter_arcmin = 2.0 * math.degrees(math.asin(695_700.0 / pos.distance_km)) * 60.0
    report = ObjectReport("Солнце", "Звезда · центр Солнечной системы")
    report.sections.append(("Положение сейчас", [
        ("Высота / азимут", f"{pos.altitude:+.1f}° / {pos.azimuth:.0f}° ({compass_point(pos.azimuth)})"),
        ("α / δ (эпоха даты)", f"{format_hms(pos.ra_hours)} / {format_dms(pos.dec_deg)}"),
        ("Расстояние", f"{pos.distance_au:.4f} а. е. ({pos.distance_km / 1e6:.2f} млн км)"),
        ("Свету идти до нас", f"{pos.distance_au * LIGHT_SECONDS_PER_AU / 60:.2f} мин"),
        ("Угловой диаметр", f"{diameter_arcmin:.2f}′"),
        ("Уравнение времени", f"{pos.equation_of_time_min:+.1f} мин")]))
    report.sections.append((f"Сегодня в «{ctx.place_name}»", [
        ("Восход", format_time(day.sunrise)), ("Солнечный полдень", format_time(day.solar_noon)),
        ("Заход", format_time(day.sunset)), ("Длина дня", format_duration(day.day_length)),
        ("Начало астрономической ночи", format_time(day.astronomical_dusk))]))
    report.sections.append(("Физические характеристики", [
        ("Спектральный класс", "G2V (жёлтый карлик)"), ("Диаметр", "1 392 700 км (≈ 109 диаметров Земли)"),
        ("Масса", _sci(1.989e30, "кг") + " (≈ 333 000 масс Земли)"),
        ("Температура поверхности", "≈ 5 772 К"), ("Возраст", "≈ 4,6 млрд лет"),
        ("Период вращения", "≈ 25 сут на экваторе (вращение неравномерное)")]))
    report.notes.append("Никогда не смотрите на Солнце без специального солнечного светофильтра.")
    return report


def moon_report(ctx: AstroContext, when_utc: datetime) -> ObjectReport:
    from astronomy import moon
    m = moon.info(ctx, when_utc)
    report = ObjectReport("Луна", "Естественный спутник Земли")
    report.sections.append(("Положение и фаза сейчас", [
        ("Фаза", f"{m.phase_name}, освещено {m.illumination * 100:.0f}%"),
        ("Возраст", f"{m.age_days:.1f} сут"),
        ("Высота / азимут", f"{m.altitude:+.1f}° / {m.azimuth:.0f}° ({compass_point(m.azimuth)})"),
        ("α / δ (эпоха даты)", f"{format_hms(m.ra_hours)} / {format_dms(m.dec_deg)}"),
        ("Расстояние", f"{m.distance_km:,.0f} км".replace(",", " ")),
        ("Угловой диаметр", f"{m.angular_diameter_arcmin:.1f}′")]))
    report.sections.append((f"Сегодня в «{ctx.place_name}»", [("Восход", format_time(m.rise)), ("Заход", format_time(m.set))]))
    report.sections.append(("Физические характеристики", [
        ("Диаметр", "3 474,8 км (≈ 0,27 земного)"), ("Масса", _sci(7.342e22, "кг") + " (≈ 1/81 массы Земли)"),
        ("Среднее расстояние до Земли", "384 400 км"),
        ("Сидерический период обращения", "27,32 сут"), ("Синодический период (смена фаз)", "29,53 сут"),
        ("Ускорение свободного падения", "1,62 м/с² (≈ 1/6 земного)")]))
    return report


def planet_report(ctx: AstroContext, key: str, when_utc: datetime) -> ObjectReport:
    from astronomy import planets
    p = planets.info(ctx, key, when_utc)
    _, name, _, radius_km, _ = planets.PLANET_BY_KEY[key]
    before = planets.info(ctx, key, when_utc - timedelta(days=1), with_rise_set=False).ecl_lon
    after = planets.info(ctx, key, when_utc + timedelta(days=1), with_rise_set=False).ecl_lon
    delta = (after - before + 180.0) % 360.0 - 180.0
    motion = "прямое" if delta >= 0 else "попятное (ретроградное)"
    report = ObjectReport(name, f"Планета · созвездие {p.constellation}")
    now = [("Созвездие", p.constellation),
           ("Видимая звёздная величина", _mag(p.magnitude)),
           ("Высота / азимут", f"{p.altitude:+.1f}° / {p.azimuth:.0f}° ({compass_point(p.azimuth)})"),
           ("Сейчас", p.state),
           ("Расстояние от Земли", f"{p.distance_au:.3f} а. е. ({p.distance_au * AU_KM / 1e6:,.1f} млн км)".replace(",", " ")),
           ("Свету идти до нас", f"{p.distance_au * LIGHT_SECONDS_PER_AU / 60:.1f} мин"),
           ("Расстояние от Солнца", f"{p.sun_distance_au:.3f} а. е."),
           ("Угловой диаметр", f"{p.angular_diameter_arcsec:.1f}″"),
           ("Элонгация от Солнца", f"{p.elongation:.1f}° ({p.elongation_side})"),
           ("Фазовый угол", f"{p.phase_angle:.0f}°")]
    if p.illumination is not None:
        now.append(("Освещённая часть диска", f"{p.illumination * 100:.0f}%"))
    now += [("Эклиптические координаты", f"λ = {p.ecl_lon:.2f}°, β = {p.ecl_lat:+.2f}°"),
            ("α / δ (эпоха даты)", f"{format_hms(p.ra_hours)} / {format_dms(p.dec_deg)}"),
            ("Видимое движение по эклиптике", f"{motion} ({delta:+.2f}°/сут)"),
            ("Восход", format_time(p.rise)), ("Заход", format_time(p.set))]
    report.sections.append(("Положение сейчас", now))
    mass, axis, period, rotation = PLANET_FACTS[key]
    report.sections.append(("Физические и орбитальные характеристики", [
        ("Экваториальный диаметр", f"{2 * radius_km:,.0f} км (≈ {2 * radius_km / 12_756.3:.2f} земного)".replace(",", " ")),
        ("Масса", _sci(mass, "кг") + f" (≈ {mass / 5.972e24:.3g} масс Земли)"),
        ("Большая полуось орбиты", f"{axis} а. е."), ("Период обращения вокруг Солнца", period),
        ("Период вращения", rotation)]))
    report.notes.append("Блеск — расчётная оценка по формулам Astronomical Almanac (точность порядка 0,1–0,3ᵐ).")
    return report


def catalog_report(ctx: AstroContext, obj: dict, when_utc: datetime) -> ObjectReport:
    from api.catalog_api import TYPE_NAMES_RU
    from services.catalog_service import display_designation, object_links
    designation = display_designation(obj)
    title = obj.get("name_ru") or obj.get("name") or designation
    kind = TYPE_NAMES_RU.get(obj.get("object_type"), "объект глубокого космоса")
    constellation = constellation_ru(obj["constellation"]) if obj.get("constellation") else \
        constellation_of(ctx, obj["ra_deg"], obj["dec_deg"])
    report = ObjectReport(title, f"{kind} · созвездие {constellation}")
    size = "—"
    if obj.get("size_arcmin"):
        size = (f"{obj['size_arcmin']:.1f}′ × {obj['size_minor_arcmin']:.1f}′" if obj.get("size_minor_arcmin")
                else f"{obj['size_arcmin']:.1f}′")
    general = [("Обозначение", designation), ("Название", obj.get("name_ru") or obj.get("name") or "—"),
               ("Тип", kind), ("Созвездие", constellation),
               ("Звёздная величина", _mag(obj.get("magnitude")) if obj.get("magnitude") is not None else "—"),
               ("Угловые размеры", size),
               ("Расстояние", f"{obj['distance_ly']:,.0f} св. лет".replace(",", " ") if obj.get("distance_ly") else "нет в каталоге")]
    if obj.get("description"):
        general.append(("Примечание каталога", obj["description"]))
    report.sections.append(("Общие сведения", general))
    report.sections.append(("Координаты", _coordinates_rows(obj["ra_deg"], obj["dec_deg"])))
    report.sections.append((f"Условия наблюдения из «{ctx.place_name}»",
                            _fixed_rows(ctx, obj["ra_deg"], obj["dec_deg"], when_utc)))
    report.notes.append("Видимость геометрическая; слабые объекты требуют тёмного неба без Луны и телескопа.")
    report.links = object_links(obj)
    return report


def build_report(ctx: AstroContext, info: dict, when_utc: datetime) -> ObjectReport:
    """Подробный отчёт по объекту, выбранному на карте (info из SkyMapWidget.object_selected)."""
    kind = info.get("type")
    if kind == "sun":
        return sun_report(ctx, when_utc)
    if kind == "moon":
        return moon_report(ctx, when_utc)
    if kind == "planet":
        return planet_report(ctx, info["key"], when_utc)
    if kind == "deepsky":
        return catalog_report(ctx, info["object"], when_utc)
    if kind == "star":
        return star_report(ctx, info, when_utc)
    raise ValueError(f"Неизвестный тип объекта: {kind!r}")


def report_to_html(report: ObjectReport, when_text: str = "") -> str:
    """HTML-представление отчёта (все значения экранируются)."""
    e = html.escape
    parts = [f"<h2>{e(report.title)}</h2><p><i>{e(report.subtitle)}</i>"
             f"{'<br>Момент: ' + e(when_text) if when_text else ''}</p>"]
    for title, rows in report.sections:
        parts.append(f"<h3>{e(title)}</h3><table cellspacing='4' cellpadding='2'>")
        parts += [f"<tr><td>{e(a)}</td><td><b>{e(b)}</b></td></tr>" for a, b in rows]
        parts.append("</table>")
    if report.notes:
        parts.append("<p>" + "<br>".join(f"<i>{e(n)}</i>" for n in report.notes) + "</p>")
    if report.links:
        parts.append("<p>Подробнее: " + " · ".join(f"<a href='{e(u)}'>{e(n)}</a>" for n, u in report.links) + "</p>")
    return "".join(parts)
