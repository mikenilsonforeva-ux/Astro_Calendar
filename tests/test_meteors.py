from datetime import date

from astronomy import meteors


def test_quadrantids_period_spans_new_year():
    q = next(s for s in meteors.SHOWERS if s.code == "QUA")
    start, end = meteors.activity_period(q, 2025)
    assert start == date(2024, 12, 28) and end == date(2025, 1, 12)


def test_all_showers_have_valid_data():
    for s in meteors.SHOWERS:
        assert 0 <= s.ra_hours < 24 and -90 <= s.dec_deg <= 90 and s.zhr > 0
        start, end = meteors.activity_period(s, 2026)
        assert start <= meteors.peak_date(s, 2026) <= end


def test_events_for_year():
    events = meteors.shower_events(2026)
    assert len(events) == len(meteors.SHOWERS)
    assert all(e.all_day and e.utc_time.year == 2026 for e in events)
    geminids = next(e for e in events if e.params["code"] == "GEM")
    assert geminids.params["peak_date"] == "2026-12-14"


def test_moon_influence():
    assert "почти не мешает" in meteors.moon_influence(0.1)
    assert "сильно" in meteors.moon_influence(0.9)
