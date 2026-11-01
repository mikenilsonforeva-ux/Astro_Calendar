"""Сверка с независимыми справочными значениями (USNO / JPL / астрономические календари).

Допуски выбраны с запасом: событие должно совпасть по минутам-часам, а не «по порядку величины».
Тесты пропускаются, если нет Skyfield или файла эфемерид.
"""
from datetime import date, datetime, timedelta, timezone

import pytest

pytest.importorskip("skyfield")


def utc(*args):
    return datetime(*args, tzinfo=timezone.utc)


def close(a, b, minutes):
    return abs((a - b).total_seconds()) <= minutes * 60


def test_equinoxes_and_solstices_2024(ctx):
    from astronomy import sun
    events = sun.season_events(ctx, ctx.ts.utc(2024, 1, 1), ctx.ts.utc(2025, 1, 1))
    expected = [utc(2024, 3, 20, 3, 6), utc(2024, 6, 20, 20, 51),
                utc(2024, 9, 22, 12, 44), utc(2024, 12, 21, 9, 21)]
    assert len(events) == 4
    for event, ref in zip(events, expected):
        assert close(event.utc_time, ref, 3), (event.title, event.utc_time, ref)


def test_moon_phases_january_2024(ctx):
    from astronomy import moon
    events = moon.phase_events(ctx, ctx.ts.utc(2024, 1, 1), ctx.ts.utc(2024, 2, 1))
    by_kind = {e.params["kind"]: e.utc_time for e in events}
    assert close(by_kind[0], utc(2024, 1, 11, 11, 57), 3)   # новолуние
    assert close(by_kind[2], utc(2024, 1, 25, 17, 54), 3)   # полнолуние


def test_moon_illumination_at_full_and_new(ctx):
    from astronomy import moon
    assert moon.illumination_at(ctx, utc(2024, 1, 25, 17, 54)) > 0.995
    assert moon.illumination_at(ctx, utc(2024, 1, 11, 11, 57)) < 0.005
    assert 14.0 < moon.age_days(ctx, utc(2024, 1, 25, 17, 54)) < 15.5


def test_moon_distance_and_angular_size_plausible(ctx):
    from astronomy import moon
    info = moon.info(ctx, utc(2024, 1, 25, 12, 0), with_rise_set=False)
    assert 356_000 < info.distance_km < 407_000
    assert 29.0 < info.angular_diameter_arcmin < 34.5


def test_sun_distance_and_equation_of_time(ctx):
    from astronomy import sun
    jan = sun.position(ctx, utc(2024, 1, 4, 12, 0))      # около перигелия
    jul = sun.position(ctx, utc(2024, 7, 4, 12, 0))      # около афелия
    assert 0.9830 < jan.distance_au < 0.9840
    assert 1.0160 < jul.distance_au < 1.0171
    nov = sun.position(ctx, utc(2024, 11, 3, 12, 0))     # максимум ≈ +16.4 мин
    feb = sun.position(ctx, utc(2024, 2, 11, 12, 0))     # минимум ≈ −14.2 мин
    assert 16.0 < nov.equation_of_time_min < 16.8
    assert -14.6 < feb.equation_of_time_min < -13.8


def test_sunrise_sunset_moscow_solstice_is_plausible(ctx):
    from astronomy import sun
    info = sun.day_info(ctx, date(2024, 6, 21))
    assert info.sunrise.tzinfo is not None and info.sunrise.utcoffset() == timedelta(hours=3)
    assert 3 <= info.sunrise.hour <= 4 and 21 <= info.sunset.hour <= 21
    assert timedelta(hours=17, minutes=0) < info.day_length < timedelta(hours=17, minutes=40)
    assert info.sunrise < info.solar_noon < info.sunset
    assert info.astronomical_dawn is None   # в Москве в июне астрономической ночи нет


def test_polar_day_and_night(ctx):
    from astronomy.context import AstroContext
    from astronomy import sun
    import config
    tromso = AstroContext.create(69.65, 18.96, 10, "Europe/Oslo", config.find_ephemeris_file(), "Тромсё")
    assert sun.day_info(tromso, date(2024, 6, 21)).polar_state == "polar_day"
    assert sun.day_info(tromso, date(2024, 12, 21)).polar_state == "polar_night"


def test_outer_planet_oppositions(ctx):
    from astronomy import planets
    events = planets.planet_events(ctx, ctx.ts.utc(2024, 1, 1), ctx.ts.utc(2025, 3, 1))
    opp = {e.body: e.utc_time for e in events if e.params.get("kind") == "opposition"}
    assert close(opp["saturn"], utc(2024, 9, 8, 12), 36 * 60)
    assert close(opp["jupiter"], utc(2024, 12, 7, 12), 36 * 60)
    assert close(opp["mars"], utc(2025, 1, 16, 12), 36 * 60)


def test_inner_planet_elongations_are_in_physical_range(ctx):
    from astronomy import planets
    events = planets.planet_events(ctx, ctx.ts.utc(2024, 1, 1), ctx.ts.utc(2026, 1, 1))
    for e in events:
        if e.params.get("kind") == "greatest_elongation":
            limit = (28.5, 17.5) if e.body == "mercury" else (47.5, 44.5)
            assert limit[1] < e.params["elongation_deg"] < limit[0]
    assert any(e.body == "venus" and e.params.get("kind") == "greatest_elongation" for e in events)


def test_planet_info_sanity(ctx):
    from astronomy import planets
    for p in planets.all_info(ctx, utc(2024, 12, 7, 0, 0), with_rise_set=False):
        assert 0 <= p.ra_hours < 24 and -90 <= p.dec_deg <= 90
        assert 0 <= p.elongation <= 180
        assert p.constellation
    jupiter = planets.info(ctx, "jupiter", utc(2024, 12, 7, 0, 0), with_rise_set=False)
    assert jupiter.elongation > 170                       # противостояние
    assert -3.0 < jupiter.magnitude < -2.3                # около −2.8ᵐ
    assert jupiter.constellation == "Телец"


def test_lunar_eclipses_2025(ctx):
    from astronomy import eclipses
    events = eclipses.lunar_eclipse_events(ctx, ctx.ts.utc(2025, 1, 1), ctx.ts.utc(2026, 1, 1))
    assert len(events) == 2                      # 14.03.2025 и 07.09.2025, оба полные
    assert close(events[0].utc_time, utc(2025, 3, 14, 6, 59), 20)
    assert close(events[1].utc_time, utc(2025, 9, 7, 18, 12), 20)
    assert all(e.params["kind"] == "total" for e in events)


def test_moon_apsides_alternate(ctx):
    from astronomy import moon
    events = moon.apsis_events(ctx, ctx.ts.utc(2024, 1, 1), ctx.ts.utc(2025, 1, 1))
    events.sort(key=lambda e: e.utc_time)
    kinds = [e.params["kind"] for e in events]
    assert 24 <= len(events) <= 28
    assert all(a != b for a, b in zip(kinds, kinds[1:]))
    for e in events:
        assert 356_000 < e.params["distance_km"] < 407_000


def test_event_manager_caches_in_db_and_annotates(ctx, tmp_path):
    from database.db_manager import DatabaseManager
    from services.event_manager import EventManager
    manager = EventManager(DatabaseManager(tmp_path / "e.db"))
    events = manager.get_events(ctx, utc(2024, 1, 1), utc(2024, 2, 1))
    assert manager.is_year_cached(2024)
    assert {"moon_phase", "apsides"} <= {e.category for e in events}
    assert all(e.visibility for e in events)
    offline = manager.get_events(None, utc(2024, 1, 1), utc(2024, 2, 1))   # без эфемерид — из БД
    assert [e.title for e in offline] == [e.title for e in events]
    assert all("нет файла эфемерид" in e.visibility for e in offline)


def test_meteor_visibility_text(ctx):
    from astronomy import meteors
    e = next(x for x in meteors.shower_events(2024) if x.params["code"] == "PER")
    text = meteors.local_visibility_text(ctx, e)
    assert "радиант" in text and "Луны" in text


def test_weather_report_groups_nights_and_scores_dark_hours(ctx):
    from api.weather_api import HourlyWeather
    from services.weather_service import WeatherService
    start = utc(2026, 12, 10, 12, 0)    # зимой в Москве ночь длинная
    hours = [HourlyWeather(start + timedelta(hours=i), -5, 60, 0, 5, 0, 25000, 1015) for i in range(48)]
    nights = WeatherService.build_report(ctx, hours)
    assert len(nights) >= 2
    first = nights[0]
    assert first.average is not None and 0 <= first.average <= 100
    assert any(h.score.score is None for h in first.hours)        # днём индекса нет
    with_target = WeatherService.build_report(ctx, hours, "jupiter")
    assert with_target[0].hours[0].target_altitude is not None
