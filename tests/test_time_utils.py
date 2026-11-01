from datetime import date, datetime, timezone

import pytest

from astronomy import time_utils as tu


def test_unknown_timezone_gives_friendly_error():
    with pytest.raises(ValueError, match="Неизвестный часовой пояс"):
        tu.get_timezone("Mars/Olympus")


@pytest.mark.parametrize("lat,lon,elev", [(91, 0, 0), (-91, 0, 0), (0, 181, 0), (0, -181, 0),
                                          (0, 0, 10000), (float("nan"), 0, 0)])
def test_invalid_coordinates_rejected(lat, lon, elev):
    with pytest.raises(ValueError):
        tu.validate_coordinates(lat, lon, elev)


def test_valid_coordinates_accepted():
    tu.validate_coordinates(55.75, 37.62, 150)
    tu.validate_coordinates(-90, 180, -100)


def test_naive_datetime_rejected():
    with pytest.raises(ValueError):
        tu.ensure_utc(datetime(2024, 1, 1))


def test_moscow_day_bounds():
    tz = tu.get_timezone("Europe/Moscow")  # UTC+3 без перехода на летнее время
    start, end = tu.local_day_bounds_utc(date(2024, 6, 21), tz)
    assert start == datetime(2024, 6, 20, 21, 0, tzinfo=timezone.utc)
    assert end == datetime(2024, 6, 21, 21, 0, tzinfo=timezone.utc)


def test_dst_days_have_23_and_25_hours():
    tz = tu.get_timezone("Europe/Berlin")
    s, e = tu.local_day_bounds_utc(date(2024, 3, 31), tz)   # переход на летнее время
    assert (e - s).total_seconds() == 23 * 3600
    s, e = tu.local_day_bounds_utc(date(2024, 10, 27), tz)  # возврат на зимнее время
    assert (e - s).total_seconds() == 25 * 3600


def test_range_bounds():
    tz = tu.get_timezone("UTC")
    s, e = tu.local_range_bounds_utc(date(2024, 1, 1), date(2024, 1, 31), tz)
    assert (e - s).days == 31


def test_format_duration():
    from datetime import timedelta
    assert tu.format_duration(timedelta(hours=17, minutes=30)) == "17 ч 30 мин"
    assert tu.format_duration(None) == "—"
