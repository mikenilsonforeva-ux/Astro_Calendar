import pytest
import requests

from api.geocoding_api import parse_results, search_places
from api.http_client import ApiError, HttpClient


class FakeResponse:
    def __init__(self, status=200, payload=None, content=b""):
        self.status_code, self._payload, self.content = status, payload, content
        self.headers = {"Content-Length": str(len(content))}
        self.text = ""

    def json(self):
        if self._payload is None:
            raise ValueError("not json")
        return self._payload

    def iter_content(self, chunk_size):
        yield self.content


class FakeSession:
    def __init__(self, responses):
        self.responses, self.calls = list(responses), 0
        self.headers = {}

    def get(self, url, **kwargs):
        self.calls += 1
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def client(responses, retries=3):
    s = FakeSession(responses)
    return HttpClient(retries=retries, backoff=0, session=s), s


def test_retry_on_connection_error_then_success():
    c, s = client([requests.ConnectionError("down"), FakeResponse(payload={"ok": 1})])
    assert c.get_json("http://x") == {"ok": 1}
    assert s.calls == 2


def test_gives_up_after_retries_with_friendly_message():
    c, s = client([requests.Timeout("t")] * 3)
    with pytest.raises(ApiError, match="Проверьте подключение к интернету"):
        c.get_json("http://x")
    assert s.calls == 3


def test_client_error_not_retried():
    c, s = client([FakeResponse(status=404)])
    with pytest.raises(ApiError):
        c.get_json("http://x")
    assert s.calls == 1


def test_server_error_retried():
    c, s = client([FakeResponse(status=503), FakeResponse(payload=[1])])
    assert c.get_json("http://x") == [1]


def test_invalid_json():
    c, _ = client([FakeResponse(payload=None)])
    with pytest.raises(ApiError, match="не JSON"):
        c.get_json("http://x")


def test_download_checks_size(tmp_path):
    c, _ = client([FakeResponse(content=b"abc")])
    with pytest.raises(ApiError):
        c.download("http://x", tmp_path / "f.bin", min_size=10)
    assert not (tmp_path / "f.bin").exists()
    assert not (tmp_path / "f.bin.part").exists()
    c, _ = client([FakeResponse(content=b"abcdef")])
    assert c.download("http://x", tmp_path / "f.bin", min_size=3).read_bytes() == b"abcdef"


def test_geocoding_parse_skips_bad_records():
    payload = {"results": [
        {"name": "Москва", "country": "Россия", "admin1": "Москва", "latitude": 55.75,
         "longitude": 37.62, "elevation": 144, "timezone": "Europe/Moscow"},
        {"name": "Bad", "latitude": 999, "longitude": 0},
        {"name": "NoCoords"},
    ]}
    result = parse_results(payload)
    assert len(result) == 1 and result[0].timezone == "Europe/Moscow"
    assert parse_results({}) == []


def test_geocoding_short_query_rejected():
    with pytest.raises(ApiError):
        search_places("a")


def test_geocoding_offline_error():
    c, _ = client([requests.ConnectionError("down")] * 3)
    with pytest.raises(ApiError):
        search_places("Москва", client=c)
