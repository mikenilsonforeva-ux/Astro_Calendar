"""Карта Земли: геометрия, береговая линия, сервис, «космическая история»."""
import json

import numpy as np
import pytest

from api.http_client import ApiError
from astronomy import earthmap
from database.db_manager import DatabaseManager
from services import space_history
from services.geodata_service import GeoDataService

GEOJSON = json.dumps({"type": "FeatureCollection", "features": [
    {"type": "Feature", "geometry": {"type": "LineString", "coordinates": [[0, 0], [10, 5], [20, 0]]}},
    {"type": "Feature", "geometry": {"type": "MultiLineString",
                                      "coordinates": [[[30, 30], [40, 35]], [[50, 50], [60, 55]]]}},
    {"type": "Feature", "geometry": {"type": "Polygon", "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 0]]]}},
    {"type": "Feature", "geometry": {"type": "Point", "coordinates": [1, 1]}}]})


def test_normalize_lon():
    assert earthmap.normalize_lon(190.0) == pytest.approx(-170.0)
    assert earthmap.normalize_lon(-180.0) == pytest.approx(-180.0)
    assert earthmap.normalize_lon(540.0) == pytest.approx(-180.0)


def test_terminator_equinox_is_meridian_pair():
    lons = np.array([-90.0, 0.0, 90.0])
    lats = earthmap.terminator_latitudes(lons, 0.0, 0.0)
    assert abs(lats[1]) > 80                    # на подсолнечном меридиане терминатор у полюса
    assert abs(lats[0]) < 1e-3 or abs(lats[0]) < 1.0   # на 90° от Солнца терминатор у экватора


def test_terminator_summer_sun_night_at_south():
    # Солнце над 23.4° с.ш.: в подсолнечной долготе граница лежит на 66.6° ю.ш. (полярный день на севере)
    lat = earthmap.terminator_latitudes([0.0], 23.44, 0.0)[0]
    assert lat == pytest.approx(-(90.0 - 23.44), abs=0.01)
    lon, lat_poly = earthmap.night_polygon(23.44, 0.0)
    assert lat_poly[-1] == -90.0 and lon[0] == -180.0 and lon[-3] == 180.0


def test_footprint_radius_matches_iss():
    # МКС на высоте 420 км: горизонт ≈ 2300 км по поверхности
    assert earthmap.footprint_radius_km(420.0) == pytest.approx(2290.0, rel=0.03)
    lon, lat = earthmap.footprint(0.0, 0.0, 420.0, n=8)
    dist = np.degrees(np.arccos(np.cos(np.radians(lat)) * np.cos(np.radians(lon))))
    expected = np.degrees(earthmap.footprint_radius_km(420.0) / earthmap.EARTH_RADIUS_KM)
    assert np.allclose(dist, expected, atol=1e-6)


def test_footprint_wraps_over_dateline():
    lon, lat = earthmap.footprint(10.0, 179.0, 800.0)
    assert lon.min() < -150 and lon.max() > 150         # окружность пересекает линию перемены дат
    parts = earthmap.split_dateline(lon, lat)
    assert len(parts) >= 2
    for a, _ in parts:
        assert np.abs(np.diff(a)).max() < 180.0


def test_split_dateline_track():
    lons = [170, 175, 179, -179, -175, -170]
    parts = earthmap.split_dateline(lons, [0, 1, 2, 3, 4, 5])
    assert [len(a) for a, _ in parts] == [3, 3]
    assert earthmap.split_dateline([1.0], [1.0]) == []


def test_parse_geojson_lines():
    lines = earthmap.parse_geojson_lines(GEOJSON)
    assert len(lines) == 4 and all(l.shape[1] == 2 for l in lines)
    with pytest.raises(ValueError):
        earthmap.parse_geojson_lines("не json")
    with pytest.raises(ValueError):
        earthmap.parse_geojson_lines(json.dumps({"type": "FeatureCollection", "features": []}))


class FakeClient:
    def __init__(self, texts):
        self.texts, self.calls = list(texts), 0

    def get_text(self, url, params=None):
        self.calls += 1
        item = self.texts.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def test_geodata_download_fallback_and_cache(tmp_path):
    db = DatabaseManager(tmp_path / "g.db")
    service = GeoDataService(db, tmp_path / "geo")
    assert not service.is_available()
    with pytest.raises(FileNotFoundError):
        service.load()
    client = FakeClient([ApiError("нет связи"), GEOJSON])       # первый адрес недоступен — берётся второй
    assert service.download(client) == 4 and client.calls == 2
    assert service.is_available() and len(GeoDataService(db, tmp_path / "geo").load()) == 4
    with pytest.raises(ApiError):
        GeoDataService(db, tmp_path / "other").download(FakeClient([ApiError("a"), "мусор"]))


def test_space_history_integrity():
    events = space_history.EVENTS
    assert len(events) > 150
    assert all(e.category in space_history.CATEGORIES for e in events)
    assert len({(e.month, e.day, e.year, e.text) for e in events}) == len(events)
    assert all(1 <= e.month <= 12 and 1 <= e.day <= 31 and 1400 <= e.year <= 2026 for e in events)
    assert events == sorted(events, key=lambda e: (e.month, e.day, e.year))


def test_space_history_lookup():
    day = space_history.events_for(4, 12)
    assert {e.year for e in day} >= {1961, 1981}
    assert space_history.events_for(4, 12, "disaster") == []
    near = space_history.nearest(1, 1, 3)
    assert near and all(abs(s) <= 3 for s, _ in near)
    assert abs(near[0][0]) <= abs(near[-1][0])
    wrap = space_history.nearest(12, 31, 3)                    # переход через границу года
    assert any(e.month == 1 for _, e in wrap) or any(e.month == 12 for _, e in wrap)


def test_history_page_text():
    pytest.importorskip("PySide6")
    from ui.history_page import render_day, years_text
    text = render_day(4, 12, 2026, None)
    assert "Гагарин" in text and "65 лет назад" in text
    assert "Ближайшие даты" in render_day(1, 9, 2026, "disaster") or "нет" in render_day(1, 9, 2026, "disaster")
    assert years_text(1) == "1 год назад" and years_text(2) == "2 года назад" and years_text(11) == "11 лет назад"
    assert years_text(21) == "21 год назад" and years_text(112) == "112 лет назад"
