from datetime import datetime, timezone

import pytest

from api.http_client import ApiError
from api.weather_api import HourlyWeather, parse_forecast
from astronomy import observing_index as oi

PAYLOAD = {"hourly": {
    "time": ["2026-11-02T00:00", "2026-11-02T01:00", "bad", "2026-11-02T03:00"],
    "temperature_2m": [1.5, 1.0, 0, None],
    "relative_humidity_2m": [60, 95, 0, 80],
    "cloud_cover": [0, 100, 0, None],
    "wind_speed_10m": [5, 30, 0, 12],
    "precipitation": [0, 0.5, 0, 0],
    "visibility": [24000, 3000, 0, None],
    "pressure_msl": [1015, 1012, 0, 1010],
}}


def hour(**kw):
    base = dict(time_utc=datetime(2026, 11, 2, tzinfo=timezone.utc), temperature_c=0, humidity_pct=60,
                cloud_cover_pct=0, wind_kmh=5, precipitation_mm=0, visibility_m=25000, pressure_hpa=1015)
    base.update(kw)
    return HourlyWeather(**base)


def test_parse_forecast_skips_bad_time_and_keeps_none():
    hours = parse_forecast(PAYLOAD)
    assert len(hours) == 3
    assert hours[0].cloud_cover_pct == 0 and hours[2].cloud_cover_pct is None
    assert hours[2].temperature_c is None
    assert hours[0].time_utc == datetime(2026, 11, 2, 0, 0, tzinfo=timezone.utc)


@pytest.mark.parametrize("payload", [{}, {"hourly": {}}, {"hourly": {"time": []}},
                                     {"error": True, "reason": "x", "hourly": {"time": ["2026-11-02T00:00"]}}])
def test_parse_forecast_rejects_bad_payload(payload):
    with pytest.raises(ApiError):
        parse_forecast(payload)


def test_weather_roundtrip_dict():
    w = hour()
    assert HourlyWeather.from_dict(w.time_utc, w.to_dict()) == w


def test_perfect_night_scores_100_and_clouds_kill_it():
    perfect = oi.night_score(hour(), sun_altitude=-30, moon_altitude=-20, moon_illumination=1.0)
    assert perfect.score == 100 and perfect.label == "отлично"
    cloudy = oi.night_score(hour(cloud_cover_pct=100), -30, -20, 0.0)
    assert cloudy.score <= 55 and cloudy.score < perfect.score


def test_bright_moon_up_lowers_score():
    dark = oi.night_score(hour(), -30, 40, 0.0).score
    bright = oi.night_score(hour(), -30, 40, 1.0).score
    assert dark - bright == 15


def test_precipitation_caps_score():
    assert oi.night_score(hour(precipitation_mm=1.0), -30, -20, 0.0).score <= 15


def test_daytime_has_no_index():
    r = oi.night_score(hour(), sun_altitude=-5, moon_altitude=0, moon_illumination=0)
    assert r.score is None and r.label == "не ночь"


def test_target_altitude_factor():
    assert oi.altitude_factor(0) == 0 and oi.altitude_factor(-10) == 0
    assert oi.altitude_factor(40) == pytest.approx(1.0) and oi.altitude_factor(90) == 1.0
    assert 0 < oi.altitude_factor(20) < 1
    assert oi.night_score(hour(), -30, -20, 0, target_altitude=-5).score == 0
    low = oi.night_score(hour(), -30, -20, 0, target_altitude=15).score
    assert 0 < low < 100


def test_missing_data_is_renormalised_and_flagged():
    r = oi.night_score(hour(cloud_cover_pct=None, visibility_m=None), -30, -20, 0.0)
    assert r.score is not None and "облачности" in r.note
    r2 = oi.night_score(hour(humidity_pct=None, wind_kmh=None, visibility_m=None), -30, -20, 0.0)
    assert r2.score == 100


def test_score_always_in_range():
    for cloud in (0, 50, 100):
        for wind in (0, 25, 80):
            s = oi.night_score(hour(cloud_cover_pct=cloud, wind_kmh=wind), -30, 50, 0.7).score
            assert 0 <= s <= 100


def test_weather_db_storage(tmp_path):
    from database.db_manager import DatabaseManager
    from database.models import Location
    db = DatabaseManager(tmp_path / "w.db")
    lid = db.add_location(Location("A", 50, 30, 100, "Europe/Kyiv"))
    rows = [("2026-11-02T00:00:00", hour().to_dict()), ("2026-11-02T01:00:00", hour(cloud_cover_pct=40).to_dict())]
    db.save_weather(lid, rows, "Open-Meteo")
    db.save_weather(lid, rows[:1], "Open-Meteo")          # повторная запись не дублирует
    loaded, fetched = db.load_weather(lid, "2026-11-02T00:00:00")
    assert len(loaded) == 2 and fetched
    assert db.load_weather(lid, "2026-11-02T01:00:00")[0][0][0] == "2026-11-02T01:00:00"
    assert db.load_weather(lid + 1, "2000-01-01T00:00:00") == ([], None)
