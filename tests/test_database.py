import sqlite3

import pytest

from database.db_manager import MIGRATIONS, DatabaseManager
from database.models import Location


@pytest.fixture
def db(tmp_path):
    return DatabaseManager(tmp_path / "t.db")


def loc(name="Москва", lat=55.75, lon=37.62, tz="Europe/Moscow", **kw):
    return Location(name=name, latitude=lat, longitude=lon, elevation_m=150, timezone=tz, **kw)


def test_schema_created_with_required_tables(db):
    with db.connect() as conn:
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"locations", "celestial_objects", "astronomical_events", "weather_data",
            "satellite_data", "ephemeris_cache", "settings", "update_history"} <= tables
    assert db.schema_version() == len(MIGRATIONS)


def test_migration_is_idempotent(tmp_path):
    DatabaseManager(tmp_path / "a.db")
    again = DatabaseManager(tmp_path / "a.db")
    assert again.schema_version() == len(MIGRATIONS)


def test_database_from_newer_version_refused(tmp_path):
    path = tmp_path / "n.db"
    DatabaseManager(path)
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA user_version = 999")
    conn.commit()
    conn.close()
    with pytest.raises(RuntimeError):
        DatabaseManager(path)


def test_first_location_becomes_default_and_default_switches(db):
    a = db.add_location(loc("A"))
    b = db.add_location(loc("B"))
    assert db.get_default_location().id == a
    db.set_default_location(b)
    assert db.get_default_location().id == b
    assert [l.is_default for l in db.list_locations() if l.id == a] == [False]


def test_invalid_location_rejected(db):
    with pytest.raises(ValueError):
        db.add_location(loc(lat=123))
    with pytest.raises(ValueError):
        db.add_location(loc(tz="Nowhere/Land"))
    with pytest.raises(ValueError):
        db.add_location(loc(name="  "))


def test_delete_default_promotes_another_and_keeps_last(db):
    a = db.add_location(loc("A"))
    b = db.add_location(loc("B"))
    db.delete_location(a)
    assert db.get_default_location().id == b
    with pytest.raises(ValueError):
        db.delete_location(b)


def test_settings_roundtrip(db):
    assert db.get_setting("theme", "dark") == "dark"
    db.set_setting("theme", "light")
    db.set_setting("nested", {"a": [1, 2], "ключ": "значение"})
    assert db.get_setting("theme") == "light"
    assert db.get_setting("nested") == {"a": [1, 2], "ключ": "значение"}


def test_events_replace_and_query(db):
    ev = lambda t, cat="moon_phase": {"category": cat, "body": "moon", "title": "x",
                                      "utc_time": t, "params": {"k": 1}}
    db.replace_events("2024-01-01T00:00:00", "2025-01-01T00:00:00",
                      [ev("2024-03-01T10:00:00"), ev("2024-02-01T10:00:00", "season")])
    all_ = db.query_events("2024-01-01T00:00:00", "2025-01-01T00:00:00")
    assert [e["utc_time"] for e in all_] == ["2024-02-01T10:00:00", "2024-03-01T10:00:00"]
    assert db.query_events("2024-01-01T00:00:00", "2025-01-01T00:00:00", ["season"])[0]["params"] == {"k": 1}
    assert db.query_events("2024-01-01T00:00:00", "2025-01-01T00:00:00", []) == []
    db.replace_events("2024-01-01T00:00:00", "2025-01-01T00:00:00", [ev("2024-05-01T00:00:00")])
    assert len(db.query_events("2024-01-01T00:00:00", "2025-01-01T00:00:00")) == 1


def test_cache_and_update_history(db):
    from datetime import timedelta
    from services.cache_manager import CacheManager
    cache = CacheManager(db)
    assert cache.get("k") is None
    cache.set("k", {"v": 1})
    assert cache.get("k") == {"v": 1}
    assert cache.get("k", max_age=timedelta(seconds=-1)) is None   # устарел
    db.log_update("ephemeris", "ok", "готово", "2024-01-01T00:00:00")
    db.log_update("ephemeris", "error", "нет сети", "2024-01-02T00:00:00")
    assert db.last_successful_update("ephemeris") is not None
    assert db.list_updates()[0]["status"] == "error"
