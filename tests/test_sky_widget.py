"""Тесты виджета карты неба на синтетическом снимке (эфемериды не нужны)."""
import os
from datetime import datetime, timezone

import numpy as np
import pytest

pytest.importorskip("PySide6")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from astronomy import skymap  # noqa: E402
from astronomy.sky_snapshot import Curve, SkyBody, SkySnapshot  # noqa: E402


def _curve(n=19):
    ra = np.linspace(0, 360, n)
    dec = np.zeros(n)
    return Curve(ra, dec, dec.copy(), ra.copy())


def make_snapshot(sun_alt=-30.0) -> SkySnapshot:
    rng = np.random.default_rng(1)
    n = 300
    ra, dec = rng.uniform(0, 360, n), np.degrees(np.arcsin(rng.uniform(-1, 1, n)))
    alt, az = rng.uniform(-60, 90, n), rng.uniform(0, 360, n)
    mag = rng.uniform(-1, 6.5, n)
    az_line = np.linspace(0, 360, 37)
    return SkySnapshot(
        when_utc=datetime(2026, 1, 1, tzinfo=timezone.utc), latitude=55.0, longitude=37.0, sun_alt=sun_alt,
        zenith_ra=10.0, zenith_dec=55.0, star_ra=ra, star_dec=dec, star_mag=mag, star_alt=alt, star_az=az,
        star_hip=np.arange(n) + 1, star_names={"Сириус": 0, "Вега": 1}, segments=[("Тест", 0, 1)],
        const_labels=[("Орион", 85.0, 0.0, 30.0, 180.0)], milky_way=_curve(), ecliptic=_curve(),
        horizon_ra=az_line, horizon_dec=np.zeros_like(az_line), cardinals=[("С", 0.0, 0.0), ("В", 90.0, 0.0)],
        bodies=[SkyBody("sun", "Солнце", "sun", 280.0, -23.0, sun_alt, 10.0, -26.7),
                SkyBody("moon", "Луна", "moon", 100.0, 20.0, 35.0, 200.0, None, "тест", phase_angle=100.0),
                SkyBody("mars", "Марс", "planet", 50.0, 15.0, 40.0, 150.0, 0.5, "тест")],
        deep_sky=[{"catalog_id": "NGC224", "messier": 31, "name": "Andromeda", "name_ru": "Андромеда",
                   "ra_deg": 10.7, "dec_deg": 41.3, "magnitude": 3.4, "alt": 50.0, "az": 20.0}])


@pytest.fixture(scope="module")
def app():
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


@pytest.mark.parametrize("mode", ["horizontal", "equatorial"])
@pytest.mark.parametrize("sun_alt", [-30.0, -9.0, 20.0])
def test_widget_paints_without_errors(app, mode, sun_alt):
    from ui.sky_widget import SkyMapWidget
    widget = SkyMapWidget()
    widget.resize(600, 600)
    widget.set_snapshot(make_snapshot(sun_alt))
    widget.set_mode(mode)
    for fov in (170.0, 60.0, 10.0):
        widget.fov = fov
        image = widget.grab().toImage()
        assert not image.isNull()
    widget.set_layer("below_horizon", True)
    widget.grab()


def test_widget_without_snapshot_paints(app):
    from ui.sky_widget import SkyMapWidget
    widget = SkyMapWidget()
    widget.resize(300, 300)
    assert not widget.grab().toImage().isNull()


def test_zoom_limits_and_directions(app):
    from ui.sky_widget import MAX_FOV, MIN_FOV, SkyMapWidget
    widget = SkyMapWidget()
    widget.set_snapshot(make_snapshot())
    for _ in range(40):
        widget.zoom(0.5)
    assert widget.fov == MIN_FOV
    for _ in range(40):
        widget.zoom(2.0)
    assert widget.fov == MAX_FOV
    widget.look_at_direction(90.0)
    assert (widget.lon0, widget.lat0) == (90.0, 35.0)


def test_click_selects_planet(app):
    from PySide6.QtCore import QPointF
    from ui.sky_widget import SkyMapWidget
    widget = SkyMapWidget()
    widget.resize(600, 600)
    widget.set_snapshot(make_snapshot())
    widget.grab()
    got = []
    widget.object_selected.connect(got.append)
    x, y, info = next(h for h in widget._hits if h[2]["key"] == "mars")
    widget._pick(QPointF(x + 2, y + 1))
    assert got and got[0]["name"] == "Марс"
    assert widget.selected_key == "mars"


def test_sky_color_gradient_and_describe(app):
    from ui.sky_widget import describe_object, sky_color
    assert sky_color(-30).blue() < sky_color(20).blue()
    text = describe_object({"name": "Марс", "kind": "Планета", "mag": 0.5, "alt": 40.0, "az": 150.0,
                            "ra": 50.0, "dec": 15.0, "detail": "тест"})
    assert "Марс" in text and "Над горизонтом" in text


def test_project_roundtrip_of_view_center():
    sx, sy, valid = skymap.stereo_project(120.0, 30.0, 120.0, 30.0)
    assert valid and abs(float(sx)) < 1e-9 and abs(float(sy)) < 1e-9
