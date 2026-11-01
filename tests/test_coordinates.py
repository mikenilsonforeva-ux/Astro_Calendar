import pytest

from astronomy import coordinates as c


@pytest.mark.parametrize("az,expected", [(0, "С"), (359.9, "С"), (45, "СВ"), (90, "В"),
                                         (180, "Ю"), (270, "З"), (22.5, "ССВ"), (337.4, "ССЗ")])
def test_compass(az, expected):
    assert c.compass_point(az) == expected


def test_format_hms_rounding_carry():
    assert c.format_hms(5.5) == "05ч 30м 00.0с"
    assert c.format_hms(23.999999) == "00ч 00м 00.0с"


def test_format_dms():
    assert c.format_dms(-12.5) == "-12° 30′ 00″"
    assert c.format_dms(0.9999999) == "+1° 00′ 00″"
    assert c.format_dms(10.0, signed=False) == "10° 00′ 00″"


def test_format_lat_lon():
    assert c.format_lat_lon(55.7558, 37.6173) == "55.7558° с. ш., 37.6173° в. д."
    assert c.format_lat_lon(-33.9, -70.7) == "33.9000° ю. ш., 70.7000° з. д."
