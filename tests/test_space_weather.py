from datetime import timedelta

import pytest

from api import noaa_api
from api.http_client import ApiError
from astronomy import space_weather as sw

KP_OBJECTS = [
    {"time_tag": "2026-11-01T00:00:00", "Kp": 1.33, "a_running": 5, "station_count": 8},
    {"time_tag": "2026-11-01T03:00:00", "Kp": 5.67, "a_running": 50, "station_count": 8},
    {"time_tag": "bad", "Kp": 3},
    {"time_tag": "2026-11-01T06:00:00", "Kp": 99},
]
KP_ARRAYS = [["time_tag", "Kp", "a_running", "station_count"],
             ["2026-11-01 00:00:00.000", "2.00", "7", "8"],
             ["2026-11-01 03:00:00.000", "3.33", "12", "8"]]
FORECAST_ARRAYS = [["time_tag", "kp", "observed", "noaa_scale"],
                   ["2026-11-01 09:00:00", "4.33", "predicted", None],
                   ["2026-11-01 12:00:00", "5.00", "predicted", "G1"]]


def test_kp_parse_both_formats_and_filters_garbage():
    pts = noaa_api.parse_kp(KP_OBJECTS)
    assert [p.kp for p in pts] == [1.33, 5.67]
    arr = noaa_api.parse_kp(KP_ARRAYS)
    assert [p.kp for p in arr] == [2.0, 3.33] and arr[0].observed
    fc = noaa_api.parse_kp(FORECAST_ARRAYS)
    assert not fc[0].observed and fc[1].noaa_scale == "G1"


@pytest.mark.parametrize("payload", [{}, "x", [], [{"time_tag": "bad", "Kp": 1}]])
def test_kp_parse_bad_payload(payload):
    with pytest.raises(ApiError):
        noaa_api.parse_kp(payload)


def test_flares_parse_sorted_and_skips_empty():
    payload = [{"begin_time": "2026-11-01T05:00:00Z", "max_time": "2026-11-01T05:10:00Z", "max_class": "M1.2"},
               {"begin_time": "2026-10-30T05:00:00Z", "max_time": "2026-10-30T05:10:00Z", "max_class": "C3.0"},
               {"max_time": "2026-10-31T00:00:00Z", "max_class": ""}]
    flares = noaa_api.parse_flares(payload)
    assert [f.max_class for f in flares] == ["C3.0", "M1.2"]
    assert flares[1].max_utc - flares[1].begin_utc == timedelta(minutes=10)


def test_storm_scale():
    assert storm_ok(4.9, "возмущённо") and storm_ok(2, "бури нет")
    assert sw.storm_scale(5.0).startswith("G1") and sw.storm_scale(7.67).startswith("G3")
    assert sw.storm_scale(9).startswith("G5")


def storm_ok(kp, text):
    return text in sw.storm_scale(kp)


def test_geomagnetic_latitude_known_cities():
    assert sw.geomagnetic_latitude(55.75, 37.62) == pytest.approx(51.6, abs=1.0)   # Москва ≈ 51.5°
    assert sw.geomagnetic_latitude(69.65, 18.96) == pytest.approx(67.0, abs=1.5)   # Тромсё ≈ 67°
    assert sw.geomagnetic_latitude(80.65, -72.68) == pytest.approx(90.0, abs=0.01)


def test_aurora_assessment_by_latitude_and_kp():
    assert sw.aurora_assessment(69.65, 18.96, 3)[0] == "высокая"
    assert sw.aurora_assessment(55.75, 37.62, 2)[0] == "очень низкая"
    assert sw.aurora_assessment(55.75, 37.62, 8)[0] in ("средняя", "высокая")
    assert "не прогноз NOAA" in sw.aurora_assessment(55.75, 37.62, 5)[1]


def test_solar_service_offline_fallback(tmp_path, monkeypatch):
    from database.db_manager import DatabaseManager
    from services import solar_service

    db = DatabaseManager(tmp_path / "s.db")
    svc = solar_service.SolarService(db)
    kp = noaa_api.parse_kp(KP_OBJECTS)
    monkeypatch.setattr(noaa_api, "fetch_kp_history", lambda: kp)
    monkeypatch.setattr(noaa_api, "fetch_kp_forecast", lambda: noaa_api.parse_kp(FORECAST_ARRAYS))
    monkeypatch.setattr(noaa_api, "fetch_flares", lambda: [])
    first = svc.get(force=True)
    assert not first.from_cache and len(first.kp_history) == 2

    def offline():
        raise ApiError("нет сети")
    for name in ("fetch_kp_history", "fetch_kp_forecast", "fetch_flares"):
        monkeypatch.setattr(noaa_api, name, offline)
    second = svc.get(force=True)                       # сеть недоступна — берём сохранённое
    assert second.from_cache and len(second.kp_history) == 2 and second.warnings
    empty = solar_service.SolarService(DatabaseManager(tmp_path / "e.db")).get(force=True)
    assert empty.kp_history == [] and empty.warnings
