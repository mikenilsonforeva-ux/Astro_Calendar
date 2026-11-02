"""CelesTrak (разбор TLE), сервис с кэшем и расчёт пролётов."""
from datetime import datetime, timezone

import pytest

from api import celestrak_api
from api.http_client import ApiError
from database.db_manager import DatabaseManager
from services.satellite_service import SatelliteService

L1 = "1 25544U 98067A   08264.51782528 -.00002182  00000-0 -11606-4 0  2927"
L2 = "2 25544  51.6416 247.4627 0006703 130.5360 325.0288 15.72125391563537"
TEXT = f"ISS (ZARYA)\n{L1}\n{L2}\n"


class FakeClient:
    def __init__(self, text=TEXT, fail=False):
        self.text, self.fail, self.calls = text, fail, 0

    def get_text(self, url, params=None):
        self.calls += 1
        if self.fail:
            raise ApiError("нет сети")
        return self.text


def test_checksum_and_parse():
    assert celestrak_api.checksum_ok(L1) and celestrak_api.checksum_ok(L2)
    tles = celestrak_api.parse_tle(TEXT)
    assert len(tles) == 1 and tles[0].name == "ISS (ZARYA)" and tles[0].catnr == 25544


def test_parse_skips_broken_records():
    broken = L1[:-1] + "0"                       # неверная контрольная сумма
    text = f"BAD\n{broken}\n{L2}\n{TEXT}"
    tles = celestrak_api.parse_tle(text)
    assert [t.name for t in tles] == ["ISS (ZARYA)"]
    assert celestrak_api.parse_tle("мусор\nещё мусор") == []


def test_fetch_group_error_on_empty():
    with pytest.raises(ApiError):
        celestrak_api.fetch_group("stations", FakeClient("<html>blocked</html>"))


def test_service_cache_and_offline_fallback(tmp_path):
    db = DatabaseManager(tmp_path / "s.db")
    client = FakeClient()
    service = SatelliteService(db, client)
    first = service.load("stations")
    assert not first.from_cache and client.calls == 1
    second = service.load("stations")
    assert second.from_cache and client.calls == 1            # свежий кэш, сеть не нужна
    client.fail = True
    forced = service.load("stations", force=True)             # сети нет — старые данные с предупреждением
    assert forced.from_cache and forced.warnings and forced.tles[0].name == "ISS (ZARYA)"
    with pytest.raises(ApiError):
        SatelliteService(DatabaseManager(tmp_path / "t.db"), FakeClient(fail=True)).load("stations")


def test_passes_with_ephemeris():
    pytest.importorskip("skyfield")
    import config
    from astronomy import satellites
    from astronomy.context import AstroContext
    path = config.find_ephemeris_file()
    if path is None:
        pytest.skip("нет файла эфемерид")
    ctx = AstroContext.create(55.75, 37.62, 150.0, "Europe/Moscow", path, place_name="Москва")
    sat = satellites.make_satellite(ctx, "ISS (ZARYA)", L1, L2)
    # TLE 2008 года: берём время рядом с эпохой — модель SGP4 корректна только там
    start = datetime(2008, 9, 21, 12, 0, tzinfo=timezone.utc)
    passes = satellites.compute_passes(ctx, sat, start, days=3, min_altitude=10.0)
    assert passes, "за 3 суток МКС (наклонение 51.6°) должна пролететь над Москвой"
    for p in passes:
        assert p.rise < p.culminate < p.set
        assert p.max_alt >= 10.0 - 1e-6
        assert 0 <= p.rise_az < 360 and p.duration_s < 20 * 60
    pos = satellites.current_position(ctx, sat, start)
    assert abs(pos["latitude"]) <= 52.0 and 300 < pos["height_km"] < 450
    assert satellites.tle_age_days(sat, start) == pytest.approx(3.0, abs=1.0)
