import gzip

import numpy as np
import pytest

from astronomy import skymap as sm
from astronomy import stars as st


def test_center_projects_to_origin_and_roundtrip():
    sx, sy, ok = sm.stereo_project(120.0, 30.0, 120.0, 30.0)
    assert float(sx) == pytest.approx(0, abs=1e-12) and float(sy) == pytest.approx(0, abs=1e-12) and bool(ok)
    for lon, lat, l0, p0 in [(120, 30, 100, 40), (10, -20, 350, 10), (200, 85, 0, 90), (5, 0, 180, -60)]:
        x, y, _ = sm.stereo_project(lon, lat, l0, p0)
        got = sm.stereo_unproject(float(x), float(y), l0, p0)
        assert got[0] == pytest.approx(lon % 360, abs=1e-6) and got[1] == pytest.approx(lat, abs=1e-6)


def test_east_is_left_and_north_is_up():
    sx, sy, _ = sm.stereo_project(10.0, 0.0, 0.0, 0.0)         # восточнее центра
    assert float(sx) < 0
    sx, sy, _ = sm.stereo_project(0.0, 10.0, 0.0, 0.0)         # севернее центра
    assert float(sy) > 0 and float(sx) == pytest.approx(0, abs=1e-12)


def test_stereographic_radius_formula_and_antipode_invalid():
    x, y, ok = sm.stereo_project(60.0, 0.0, 0.0, 0.0)
    assert np.hypot(x, y) == pytest.approx(2 * np.tan(np.radians(30)))        # r = 2·tan(θ/2)
    assert not sm.stereo_project(180.0, 0.0, 0.0, 0.0)[2]


def test_unproject_center():
    assert sm.stereo_unproject(0, 0, 33.0, 12.0) == (33.0, 12.0)


def test_zenith_centered_orientation():
    # центр — зенит, север (az=0, alt=45) внизу, восток (az=90) слева
    _, sy_n, _ = sm.stereo_project(0.0, 45.0, 0.0, 90.0)
    sx_e, sy_e, _ = sm.stereo_project(90.0, 45.0, 0.0, 90.0)
    assert float(sy_n) < 0 and float(sx_e) < 0 and float(sy_e) == pytest.approx(0, abs=1e-9)


def test_galactic_and_ecliptic_reference_points():
    ra, dec = sm.galactic_to_icrs(0.0, 0.0)                     # центр Галактики
    assert float(ra) == pytest.approx(266.405, abs=0.01) and float(dec) == pytest.approx(-28.936, abs=0.01)
    ra, dec = sm.galactic_to_icrs(0.0, 90.0)                    # северный полюс Галактики
    assert float(ra) == pytest.approx(192.859, abs=0.01) and float(dec) == pytest.approx(27.128, abs=0.01)
    ra, dec = sm.ecliptic_to_icrs(90.0, 0.0)
    assert float(ra) == pytest.approx(90.0) and float(dec) == pytest.approx(23.4393, abs=1e-3)
    ra, dec = sm.ecliptic_to_icrs(0.0, 0.0)
    assert float(ra) == pytest.approx(0.0, abs=1e-9) and float(dec) == pytest.approx(0.0, abs=1e-9)
    ras, decs = sm.galactic_plane_points(37)
    assert len(ras) == 37 and np.all(np.abs(decs) <= 62.9)


def test_angular_distance():
    assert float(sm.angular_distance(0, 0, 90, 0)) == pytest.approx(90.0)
    assert float(sm.angular_distance(10, 89, 190, 89)) == pytest.approx(2.0, abs=1e-6)
    assert float(sm.angular_distance(5, 5, 5, 5)) == 0.0


def test_split_runs_breaks_on_invalid_and_jumps():
    sx = np.array([0, 1, 2, 3, 100, 101, 102, 103.0])
    sy = np.zeros(8)
    valid = np.array([1, 1, 1, 0, 1, 1, 1, 1], bool)
    runs = sm.split_runs(valid, sx, sy, max_jump=5)
    assert runs == [slice(0, 3), slice(4, 8)]
    runs2 = sm.split_runs(np.ones(8, bool), sx, sy, max_jump=5)      # прыжок 3 -> 100
    assert runs2 == [slice(0, 4), slice(4, 8)]


def test_limit_magnitude_and_radius_monotonic():
    assert sm.star_limit_magnitude(170) < sm.star_limit_magnitude(60) < sm.star_limit_magnitude(15)
    r = sm.star_radius_px(np.array([-1.0, 2.0, 6.0]))
    assert r[0] > r[1] > r[2] >= 0.7


# ---------- каталог Hipparcos ----------
def hip_line(hip, ra, dec, vmag, plx=10.0, pmra=1.0, pmde=-2.0):
    f = ["H", f"{hip:>11}", " ", "00 00 00.00", "+00 00 00.0", f"{vmag:>5}", " ", "H", f"{ra:.8f}",
         f"{dec:.8f}", " ", f"{plx:.2f}", f"{pmra:.2f}", f"{pmde:.2f}", "1.0", "1.0"]
    return "|".join(f)


def make_catalog_lines(extra=()):
    rng = np.random.default_rng(1)
    lines = [hip_line(1000 + i, rng.uniform(0, 360), rng.uniform(-80, 80), rng.uniform(4, 6.9)) for i in range(5200)]
    lines.append(hip_line(32349, 101.28715533, -16.71611586, -1.44))            # Сириус
    lines.append(hip_line(91262, 279.23473479, 38.78368896, 0.03))              # Вега
    lines.append(hip_line(2, 10.0, 10.0, 9.5))                                  # слабая — отсеивается
    lines.append(hip_line(3, 10.0, 10.0, "") if False else "H|     4| | | | | | |||")   # мусор
    lines += list(extra)
    return lines


def test_parse_hip_main_filters_and_validates():
    cat = st.parse_hip_main(make_catalog_lines())
    assert len(cat) == 5202 and cat.mag.min() == pytest.approx(-1.44)
    assert 2 not in cat.hip and 4 not in cat.hip
    i = list(cat.hip).index(32349)
    assert cat.ra[i] == pytest.approx(101.28715533) and cat.parallax[i] == 10.0 and cat.pm_dec[i] == -2.0


def test_parse_rejects_wrong_format():
    with pytest.raises(ValueError, match="слишком мало"):
        st.parse_hip_main(["x|y|z"] * 100)
    dim = [hip_line(5000 + i, i % 360, 0.0, 5.0) for i in range(5200)]
    with pytest.raises(ValueError, match="Сириус"):
        st.parse_hip_main(dim)


def test_catalog_save_load_and_gz_file(tmp_path):
    cat = st.parse_hip_main(make_catalog_lines())
    st.save_catalog(cat, tmp_path / "s.npz")
    back = st.load_catalog(tmp_path / "s.npz")
    assert len(back) == len(cat) and np.allclose(back.ra, cat.ra)
    gz = tmp_path / "hip.dat.gz"
    with gzip.open(gz, "wt", encoding="ascii") as fh:
        fh.write("\n".join(make_catalog_lines()))
    assert len(st.parse_hip_main_file(gz)) == len(cat)


def test_named_star_matching_is_conservative():
    cat = st.parse_hip_main(make_catalog_lines())
    names = st.match_named_stars(cat)
    assert cat.hip[names["Сириус"]] == 32349 and cat.hip[names["Вега"]] == 91262
    # звезда рядом по координатам, но с неподходящим блеском — не подписывается
    wrong = st.parse_hip_main(make_catalog_lines([hip_line(77, 6.752 * 15, -16.716, 5.0)]))
    assert "Сириус" in st.match_named_stars(wrong)          # настоящий Сириус остаётся
    only_dim = st.parse_hip_main([l for l in make_catalog_lines() if "32349" not in l] +
                                 [hip_line(78, 200.0, 40.0, -1.2), hip_line(77, 6.752 * 15, -16.716, 5.0)])
    assert "Сириус" not in st.match_named_stars(only_dim)


def test_asterism_segments_use_only_found_stars():
    cat = st.parse_hip_main(make_catalog_lines())
    names = st.match_named_stars(cat)
    assert st.asterism_segments(names) == []                 # Дубхе и др. не найдены — линий нет
    fake = {"Вега": 1, "Денеб": 2, "Альтаир": 3}
    segs = st.asterism_segments(fake)
    assert {(a, b) for _, a, b in segs} == {(1, 2), (2, 3), (3, 1)}
    assert all(label == "Летний треугольник" for label, _, _ in segs)


def test_named_star_table_is_sane():
    assert len({n for n, *_ in st.NAMED_STARS}) == len(st.NAMED_STARS)
    for name, ra_h, dec, v in st.NAMED_STARS:
        assert 0 <= ra_h < 24 and -90 <= dec <= 90 and -2 < v < 4
    known = {n for n, *_ in st.NAMED_STARS}
    for chains in st.ASTERISMS.values():
        for chain in chains:
            assert set(chain) <= known


# ---------- прецессия ----------
def test_precession_magnitude_and_roundtrip():
    from astronomy import precession as p
    ra, dec = p.j2000_to_date(0.0, 0.0, 0.27)                    # 2027 год
    assert float(ra) == pytest.approx(0.346, abs=0.005) and float(dec) == pytest.approx(0.150, abs=0.005)
    back = p.date_to_j2000(ra, dec, 0.27)
    assert (float(back[0]) + 1e-9) % 360 == pytest.approx(0.0, abs=1e-6) or float(back[0]) == pytest.approx(360.0)
    assert float(back[1]) == pytest.approx(0.0, abs=1e-9)
    same = p.j2000_to_date(123.0, 45.0, 0.0)                     # в эпоху J2000 ничего не меняется
    assert float(same[0]) == pytest.approx(123.0) and float(same[1]) == pytest.approx(45.0)


def test_horizon_to_equatorial_cardinal_points():
    from astronomy import precession as p
    lst, lat = 100.0, 55.0
    ra, dec = p.horizon_to_equatorial_of_date(90, 0, lat, lst)    # зенит
    assert float(ra) == pytest.approx(lst) and float(dec) == pytest.approx(lat)
    ra, dec = p.horizon_to_equatorial_of_date(0, 180, lat, lst)   # юг: на меридиане
    assert float(ra) == pytest.approx(lst) and float(dec) == pytest.approx(lat - 90)
    ra, dec = p.horizon_to_equatorial_of_date(0, 0, lat, lst)     # север: нижняя кульминация
    assert float(ra) == pytest.approx((lst + 180) % 360) and float(dec) == pytest.approx(90 - lat)
    ra, dec = p.horizon_to_equatorial_of_date(0, 90, lat, lst)    # восток: на экваторе, восточнее меридиана
    assert float(dec) == pytest.approx(0.0, abs=1e-9) and float(ra) == pytest.approx(lst + 90)


# ---------- сервис звёзд ----------
def test_star_service_download_parse_and_cache(tmp_path, monkeypatch):
    from api.http_client import ApiError
    from database.db_manager import DatabaseManager
    from services import star_service

    lines = make_catalog_lines()
    payload = gzip.compress("\n".join(lines).encode("ascii"))

    class FakeClient:
        def __init__(self):
            self.urls = []

        def download(self, url, dest, progress=None, min_size=1):
            self.urls.append(url)
            if len(self.urls) == 1:
                raise ApiError("недоступен")          # первый адрес не работает — берётся запасной
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(payload)
            return dest

    db = DatabaseManager(tmp_path / "s.db")
    svc = star_service.StarService(db, tmp_path / "stars")
    assert not svc.is_available()
    with pytest.raises(FileNotFoundError):
        svc.load()
    client = FakeClient()
    assert svc.download(client=client) == 5202
    assert len(client.urls) == 2 and svc.is_available()
    assert not (tmp_path / "stars" / "hip_main.dat.gz").exists()          # исходный файл удалён
    again = star_service.StarService(db, tmp_path / "stars")
    assert len(again.load()) == 5202
    assert db.last_successful_update("stars")


def test_star_service_reports_bad_format_and_network_errors(tmp_path):
    from api.http_client import ApiError
    from database.db_manager import DatabaseManager
    from services import star_service

    class BadFormat:
        def download(self, url, dest, progress=None, min_size=1):
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(gzip.compress(b"abc|def\n" * 10))
            return dest

    class Offline:
        def download(self, url, dest, progress=None, min_size=1):
            raise ApiError("нет сети")

        def get_text(self, url, params=None):
            raise ApiError("нет сети")

    db = DatabaseManager(tmp_path / "e.db")
    svc = star_service.StarService(db, tmp_path / "stars")
    with pytest.raises(ApiError, match="слишком мало"):
        svc.download(client=BadFormat())
    with pytest.raises(ApiError, match="Не удалось скачать"):
        svc.download(client=Offline())
    assert not svc.is_available()
    assert [u["status"] for u in db.list_updates()] == ["error", "error"]


# ---------- запасной источник VizieR и ручной импорт ----------
def make_vizier_tsv(n=5300, columns=("HIP", "RAhms", "Vmag", "RAdeg", "DEdeg", "Plx", "pmRA", "pmDE")):
    rows = ["#\n#   VizieR Astronomical Server", "\t".join(columns), "\t".join(["", "h:m:s", "mag", "deg", "deg", "mas", "mas/yr", "mas/yr"]),
            "\t".join(["---"] * len(columns))]
    for i in range(n):
        mag = -1.46 if i == 0 else 3.0 + (i % 40) / 10.0
        values = {"HIP": str(32349 + i), "RAhms": "06 45 08", "Vmag": f"{mag:.2f}", "RAdeg": f"{(i * 0.069) % 360:.5f}",
                  "DEdeg": f"{-89 + (i % 178):.4f}", "Plx": "379.21", "pmRA": "-546.01", "pmDE": "-1223.07"}
        values["RAICRS"], values["DEICRS"] = values["RAdeg"], values["DEdeg"]
        rows.append("\t".join(values.get(c, "") for c in columns))
    return "\n".join(rows)


def test_parse_vizier_tsv_and_aliases():
    from astronomy import stars
    cat = stars.parse_vizier_tsv(make_vizier_tsv())
    assert len(cat) == 5300 and cat.mag.min() == pytest.approx(-1.46) and cat.pm_dec[0] == pytest.approx(-1223.07)
    alt = stars.parse_vizier_tsv(make_vizier_tsv(columns=("HIP", "RAhms", "Vmag", "RAICRS", "DEICRS", "Plx", "pmRA", "pmDE")))
    assert len(alt) == 5300
    with pytest.raises(ValueError, match="нет столбца"):
        stars.parse_vizier_tsv(make_vizier_tsv(columns=("HIP", "Vmag", "X", "Y")))
    with pytest.raises(ValueError):
        stars.parse_vizier_tsv("#только комментарий")
    with pytest.raises(ValueError, match="слишком мало"):
        stars.parse_vizier_tsv(make_vizier_tsv(n=50))


def test_star_service_vizier_fallback_and_import(tmp_path):
    from api.http_client import ApiError
    from database.db_manager import DatabaseManager
    from services import star_service

    class ArchiveDown:
        def __init__(self):
            self.queried = []

        def download(self, url, dest, progress=None, min_size=1):
            raise ApiError("CDS недоступен")

        def get_text(self, url, params=None):
            self.queried.append((url, params))
            if len(self.queried) == 1:
                raise ApiError("зеркало 1 недоступно")
            return make_vizier_tsv()

    db = DatabaseManager(tmp_path / "v.db")
    svc = star_service.StarService(db, tmp_path / "stars")
    client = ArchiveDown()
    assert svc.download(client=client) == 5300 and svc.is_available()
    assert len(client.queried) == 2 and client.queried[1][1]["-source"] == "I/239/hip_main"

    manual = tmp_path / "manual" / "hip_main.dat.gz"
    manual.parent.mkdir()
    manual.write_bytes(gzip.compress("\n".join(make_catalog_lines()).encode("ascii")))
    other = star_service.StarService(DatabaseManager(tmp_path / "m.db"), tmp_path / "stars2")
    assert other.import_file(manual) == 5202
    with pytest.raises(ApiError, match="импортировать"):
        other.import_file(tmp_path / "нет_файла.dat")


def test_star_service_uses_file_placed_manually(tmp_path):
    from database.db_manager import DatabaseManager
    from services import star_service

    class NoNetwork:
        def download(self, *a, **k):
            raise AssertionError("сеть не должна использоваться")

        get_text = download

    folder = tmp_path / "stars"
    folder.mkdir()
    (folder / "hip_main.dat.gz").write_bytes(gzip.compress("\n".join(make_catalog_lines()).encode("ascii")))
    svc = star_service.StarService(DatabaseManager(tmp_path / "f.db"), folder)
    assert svc.download(client=NoNetwork()) == 5202
