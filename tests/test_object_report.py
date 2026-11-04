"""Подробная характеристика объектов карты неба."""
from datetime import datetime, timezone

import pytest

from astronomy import object_report as orp
from astronomy import skymap


def test_icrs_to_galactic_roundtrip_and_known_points():
    l, b = skymap.icrs_to_galactic(266.405, -28.936)             # центр Галактики
    assert float(l) % 360 == pytest.approx(0.0, abs=0.01) or float(l) == pytest.approx(360.0, abs=0.01)
    assert float(b) == pytest.approx(0.0, abs=0.01)
    l, b = skymap.icrs_to_galactic(101.287, -16.716)             # Сириус: l≈227.2°, b≈−8.9°
    assert float(l) == pytest.approx(227.23, abs=0.05) and float(b) == pytest.approx(-8.89, abs=0.05)
    ra, dec = skymap.galactic_to_icrs(*skymap.icrs_to_galactic(10.6847, 41.2687))
    assert float(ra) == pytest.approx(10.6847, abs=1e-6) and float(dec) == pytest.approx(41.2687, abs=1e-6)


def test_report_html_escapes_and_contains_parts():
    report = orp.ObjectReport("<b>Звезда</b>", "тип & созвездие",
                              sections=[("Раздел", [("Параметр", "значение <script>")])],
                              notes=["примечание"], links=[("SIMBAD", "https://example.org/?a=1&b=2")])
    text = orp.report_to_html(report, "01.11.2026 20:00")
    assert "<script>" not in text and "&lt;script&gt;" in text and "&lt;b&gt;Звезда" in text
    assert "01.11.2026 20:00" in text and "примечание" in text and "SIMBAD" in text and "&amp;b=2" in text


def test_build_report_rejects_unknown_type():
    with pytest.raises(ValueError):
        orp.build_report(None, {"type": "что-то"}, datetime.now(timezone.utc))


def test_distance_text():
    assert orp._distance_text(2.637).startswith("8.6 св. лет")
    assert orp._distance_text(100.0).startswith("326 св. лет")
    assert orp._distance_text(1000.0).startswith("3 262 св. лет")


def test_scientific_notation_formatting():
    assert orp._sci(1.989e30, "кг") == "1,989 × 10^30 кг"
    assert orp._sci(7.342e22, "кг") == "7,342 × 10^22 кг"


@pytest.fixture(scope="module")
def ctx():
    pytest.importorskip("skyfield")
    import config
    from astronomy.context import AstroContext
    path = config.find_ephemeris_file()
    if path is None:
        pytest.skip("нет файла эфемерид")
    return AstroContext.create(55.75, 37.62, 150.0, "Europe/Moscow", path, place_name="Москва")


WHEN = datetime(2026, 1, 15, 21, 0, tzinfo=timezone.utc)


def rows(report):
    return {k: v for _, section in report.sections for k, v in section}


def test_star_report_sirius(ctx):
    info = {"type": "star", "name": "Сириус", "hip": 32349, "mag": -1.46, "ra": 101.287, "dec": -16.716,
            "plx": 379.21, "pm_ra": -546.01, "pm_dec": -1223.07, "alt": 0.0, "az": 0.0}
    report = orp.build_report(ctx, info, WHEN)
    r = rows(report)
    assert "Большой Пёс" in report.subtitle
    assert r["Расстояние"].startswith("8.6 св. лет")
    assert float(r["Абсолютная звёздная величина"].rstrip("ᵐ").replace("+", "")) == pytest.approx(1.42, abs=0.05)
    assert "L☉" in r["Светимость (приближённо)"] and "Восход" in r and "Верхняя кульминация" in r
    far = orp.build_report(ctx, {**info, "plx": 0.5, "name": "HIP 1"}, WHEN)
    assert "надёжно не вычисляется" in rows(far)["Расстояние"]


def test_sun_moon_planet_reports(ctx):
    sun = rows(orp.build_report(ctx, {"type": "sun"}, WHEN))
    assert sun["Расстояние"].startswith("0.98") or sun["Расстояние"].startswith("0,98")
    assert "G2V" in sun["Спектральный класс"]
    moon = rows(orp.build_report(ctx, {"type": "moon"}, WHEN))
    assert "км" in moon["Расстояние"] and "освещено" in moon["Фаза"]
    jup = orp.build_report(ctx, {"type": "planet", "key": "jupiter"}, WHEN)
    j = rows(jup)
    assert "Юпитер" == jup.title and "142 984" in j["Экваториальный диаметр"].replace(" ", " ")
    assert "11,86" in j["Период обращения вокруг Солнца"] and "движение" in " ".join(j)
    for key in ("mercury", "venus", "mars", "saturn", "uranus", "neptune"):
        assert orp.build_report(ctx, {"type": "planet", "key": key}, WHEN).sections


def test_catalog_report_m31(ctx):
    obj = {"catalog_id": "NGC 224", "messier": 31, "name": "Andromeda Galaxy", "name_ru": "Туманность Андромеды",
           "object_type": "Galaxy", "ra_deg": 10.6847, "dec_deg": 41.2687, "magnitude": 3.44,
           "size_arcmin": 177.8, "size_minor_arcmin": 69.7, "constellation": "And", "distance_ly": None,
           "description": None}
    report = orp.build_report(ctx, {"type": "deepsky", "object": obj}, WHEN)
    r = rows(report)
    assert report.title == "Туманность Андромеды" and "177.8′ × 69.7′" in r["Угловые размеры"]
    assert "l = 121.17" in r["Галактические координаты"] and report.links
