import pytest

from api import catalog_api as ca
from api.http_client import ApiError
from database.db_manager import MIGRATIONS, DatabaseManager
from services.catalog_service import CatalogService, display_designation, object_links

HEADER = ("Name;Type;RA;Dec;Const;MajAx;MinAx;PosAng;B-Mag;V-Mag;J-Mag;H-Mag;K-Mag;SurfBr;Hubble;Pax;"
          "Pm-RA;Pm-Dec;RadVel;Redshift;Cstar U-Mag;Cstar B-Mag;Cstar V-Mag;M;NGC;IC;Cstar Names;"
          "Identifiers;Common names;NED notes;OpenNGC notes;Sources")


def row(name, typ, ra, dec, const, maj="", mn="", b="", v="", m="", common=""):
    cols = [""] * 32
    cols[0], cols[1], cols[2], cols[3], cols[4] = name, typ, ra, dec, const
    cols[5], cols[6], cols[8], cols[9], cols[23], cols[28] = maj, mn, b, v, m, common
    return ";".join(cols)


NGC_CSV = "\n".join([
    HEADER,
    row("NGC0224", "G", "00:42:44.33", "+41:16:07.5", "And", "177.83", "69.66", "4.36", "3.44", "031", "Andromeda Galaxy"),
    row("NGC1976", "HII", "05:35:16.46", "-05:23:22.8", "Ori", "90", "60", "", "4.0", "042", "Orion Nebula"),
    row("NGC0001", "G", "00:07:15.84", "+27:42:29.1", "Peg", "1.8", "1.1", "13.69", "", "", ""),
    row("NGC0002", "Dup", "00:07:16.00", "+27:42:00.0", "Peg"),
    row("NGC0003", "NonEx", "00:07:17.00", "+08:18:00", "Psc"),
    row("IC0010", "G", "", "", "Cas"),                                     # без координат — пропускается
    row("NGC7000", "HII", "20:58:47.0", "+44:19:48", "Cyg", "120", "100", "", "4.0", "", "North America Nebula"),
    row("NGC6205", "GCl", "16:41:41.24", "+36:27:35.5", "Her", "23.2", "", "", "5.78", "013", "Great Hercules Cluster"),
])
ADDENDUM_CSV = "\n".join([
    HEADER,
    row("Mel022", "OCl", "03:47:00.0", "+24:07:00", "Tau", "120", "", "", "1.6", "045", "Pleiades"),
    row("NGC0224", "G", "00:00:00", "+00:00:00", "And"),                  # дубликат обозначения
])


def test_coordinate_parsing():
    assert ca.parse_ra("00:42:44.33") == pytest.approx(10.68471, abs=1e-4)
    assert ca.parse_ra("12:00:00") == pytest.approx(180.0)
    assert ca.parse_dec("+41:16:07.5") == pytest.approx(41.26875, abs=1e-5)
    assert ca.parse_dec("-05:23:22.8") == pytest.approx(-5.38967, abs=1e-5)
    for bad in ("", "x", "25:00:00", "00:61:00"):
        assert ca.parse_ra(bad) is None
    assert ca.parse_dec("+95:00:00") is None and ca.parse_dec("") is None


def test_name_normalisation():
    assert ca.normalize_name("NGC0224") == ("NGC 224", "NGC")
    assert ca.normalize_name("IC1396A") == ("IC 1396A", "IC")
    assert ca.normalize_name("Mel022")[0] == "Mel022"


def test_parse_skips_dup_nonex_and_missing_coords():
    objs = ca.parse_openngc(NGC_CSV)
    ids = [o["catalog_id"] for o in objs]
    assert ids == ["NGC 224", "NGC 1976", "NGC 1", "NGC 7000", "NGC 6205"]
    m31 = objs[0]
    assert m31["messier"] == 31 and m31["magnitude"] == 3.44 and m31["name"] == "Andromeda Galaxy"
    assert m31["object_type"] == "galaxy" and m31["size_arcmin"] == 177.83 and m31["size_minor_arcmin"] == 69.66
    assert objs[2]["magnitude"] == 13.69          # нет V — берётся B
    assert objs[1]["dec_deg"] < 0


def test_parse_rejects_unknown_format():
    with pytest.raises(ApiError, match="не распознан"):
        ca.parse_openngc("a,b,c\n1,2,3")
    with pytest.raises(ApiError):
        ca.parse_openngc(HEADER + "\n")


def test_merge_prefers_first_file():
    merged = ca.merge_files([NGC_CSV, ADDENDUM_CSV])
    by_id = {o["catalog_id"]: o for o in merged}
    assert by_id["NGC 224"]["ra_deg"] > 10 and "Mel022" in by_id


@pytest.fixture
def service(tmp_path):
    db = DatabaseManager(tmp_path / "c.db")
    svc = CatalogService(db, tmp_path / "catalogs")
    assert svc.import_texts([NGC_CSV, ADDENDUM_CSV]) == 6
    return svc


def test_migration_adds_catalog_columns(tmp_path):
    db = DatabaseManager(tmp_path / "m.db")
    assert db.schema_version() == len(MIGRATIONS) >= 2
    with db.connect() as conn:
        cols = {r[1] for r in conn.execute("PRAGMA table_info(celestial_objects)")}
    assert {"messier", "name_ru", "catalog", "size_minor_arcmin"} <= cols


def test_search_by_designation_name_and_russian(service):
    assert [o["catalog_id"] for o in service.search("M31")] == ["NGC 224"]
    assert [o["catalog_id"] for o in service.search("m 31")] == ["NGC 224"]
    assert [o["catalog_id"] for o in service.search("ngc7000")] == ["NGC 7000"]
    assert [o["catalog_id"] for o in service.search("orion")] == ["NGC 1976"]
    assert [o["catalog_id"] for o in service.search("андромеды")] == ["NGC 224"]       # русское название
    assert [o["catalog_id"] for o in service.search("ПЛЕЯДЫ")] == ["Mel022"]           # без учёта регистра
    assert service.search("нет такого") == []


def test_filters_and_sorting(service):
    assert {o["messier"] for o in service.search(messier_only=True)} == {31, 42, 13, 45}
    assert [o["catalog_id"] for o in service.search(types=["galaxy"], sort="designation")] == ["NGC 1", "NGC 224"]
    assert {o["catalog_id"] for o in service.search(constellation="Cyg")} == {"NGC 7000"}
    bright = service.search(max_magnitude=4.0)
    assert all(o["magnitude"] <= 4.0 for o in bright) and len(bright) == 4
    by_mag = service.search()
    assert by_mag[0]["catalog_id"] == "Mel022"                       # самый яркий (1.6)
    assert by_mag[-1]["magnitude"] == 13.69
    assert service.search(sort="size")[0]["catalog_id"] == "NGC 224"
    assert len(service.search(limit=2)) == 2


def test_reimport_replaces_instead_of_duplicating(service):
    service.import_texts([NGC_CSV])
    assert service.status().count == 5


def test_status_and_helpers(service):
    assert service.status().count == 6
    ab = [a for a, _ in service.constellations()]
    assert {"And", "Ori", "Cyg"} <= set(ab)
    m31 = service.search("M31")[0]
    assert display_designation(m31) == "M 31 / NGC 224"
    links = object_links(m31)
    assert links[0][1].startswith("https://simbad.cds.unistra.fr/simbad/sim-id?Ident=M%2031")
    assert service.search("M31")[0]["name_ru"] == "Галактика Андромеды"


def test_import_local_files(tmp_path):
    db = DatabaseManager(tmp_path / "l.db")
    svc = CatalogService(db, tmp_path / "cat")
    assert svc.import_local_if_present() == 0
    (tmp_path / "cat").mkdir()
    (tmp_path / "cat" / "NGC.csv").write_text(NGC_CSV, encoding="utf-8")
    assert svc.import_local_if_present() == 5
