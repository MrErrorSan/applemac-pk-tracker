import pytest
from scraper.fetch import Fetcher, FetchError


class FakeResponse:
    def __init__(self, text="<html></html>", status_code=200):
        self.text = text
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        return {"ok": True}


class FakeSession:
    """Records calls and replays a queued list of responses or exceptions."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []
        self.headers = {}

    def get(self, url, timeout=None):
        self.calls.append(url)
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def test_fetch_category_builds_correct_url():
    session = FakeSession([FakeResponse("<html>ok</html>")])
    fetcher = Fetcher(session=session, delay=0)
    html = fetcher.fetch_category("macbook-pro-14")
    assert html == "<html>ok</html>"
    assert session.calls == ["https://applemac.pk/category/macbook-pro-14"]


def test_fetch_retries_then_succeeds(monkeypatch):
    sleeps = []
    monkeypatch.setattr("scraper.fetch.time.sleep", lambda s: sleeps.append(s))
    session = FakeSession([RuntimeError("boom"), FakeResponse("<html>ok</html>")])
    fetcher = Fetcher(session=session, delay=0)
    assert fetcher.fetch_category("iphone-17") == "<html>ok</html>"
    assert len(session.calls) == 2
    assert sleeps == [1], f"Expected backoff of [1], got {sleeps}"


def test_fetch_raises_after_max_retries(monkeypatch):
    sleeps = []
    monkeypatch.setattr("scraper.fetch.time.sleep", lambda s: sleeps.append(s))
    session = FakeSession([RuntimeError("boom")] * 5)
    fetcher = Fetcher(session=session, delay=0)
    with pytest.raises(FetchError) as exc:
        fetcher.fetch_category("iphone-17")
    assert "iphone-17" in str(exc.value)
    assert sleeps == [1, 2, 4], f"Expected backoff sequence [1, 2, 4], got {sleeps}"


def test_caches_html_when_cache_dir_given(tmp_path):
    session = FakeSession([FakeResponse("<html>cached</html>")])
    fetcher = Fetcher(session=session, delay=0, cache_dir=tmp_path)
    fetcher.fetch_category("macbook-pro-14")
    assert (tmp_path / "macbook-pro-14.html").read_text(encoding="utf-8") ==         "<html>cached</html>"


def test_fetch_sitemap_uses_correct_url():
    session = FakeSession([FakeResponse("<urlset/>")])
    Fetcher(session=session, delay=0).fetch_sitemap()
    assert session.calls == ["https://applemac.pk/sitemap.xml"]


def test_user_agent_is_set():
    session = FakeSession([FakeResponse()])
    Fetcher(session=session, delay=0)
    assert "applemac-price-tracker" in session.headers["User-Agent"]


def test_rate_limit_waits_between_requests(monkeypatch):
    sleeps = []
    monkeypatch.setattr("scraper.fetch.time.sleep", lambda s: sleeps.append(s))
    monkeypatch.setattr("scraper.fetch.time.monotonic", lambda: 0.0)
    session = FakeSession([FakeResponse(), FakeResponse()])
    fetcher = Fetcher(session=session, delay=1.5)
    fetcher.fetch_category("a")
    fetcher.fetch_category("b")
    assert any(s > 0 for s in sleeps), "second request should have waited"


@pytest.mark.live
def test_live_category_still_parses():
    """Detects upstream markup changes. Run with: pytest -m live"""
    fetcher = Fetcher()
    html = fetcher.fetch_category("macbook-pro-14")
    assert 'data-price="' in html, "card markup changed upstream"
