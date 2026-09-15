"""The only module that performs network I/O."""
import time

import requests

from . import config


class FetchError(Exception):
    """A URL could not be retrieved after all retries."""


class Fetcher:
    def __init__(self, session=None, delay=None, cache_dir=None):
        self.session = session if session is not None else requests.Session()
        self.session.headers["User-Agent"] = config.USER_AGENT
        self.delay = config.REQUEST_DELAY if delay is None else delay
        self.cache_dir = cache_dir
        self._last_request_at = None

    def _wait(self):
        if self.delay <= 0 or self._last_request_at is None:
            return
        elapsed = time.monotonic() - self._last_request_at
        remaining = self.delay - elapsed
        if remaining > 0:
            time.sleep(remaining)

    def _get(self, url):
        last_error = None
        for attempt in range(config.MAX_RETRIES):
            self._wait()
            try:
                response = self.session.get(url, timeout=config.REQUEST_TIMEOUT)
                response.raise_for_status()
                self._last_request_at = time.monotonic()
                return response
            except Exception as error:  # noqa: BLE001 - retry any transport error
                last_error = error
                self._last_request_at = time.monotonic()
                time.sleep(2 ** attempt)
        raise FetchError(f"{url} failed after {config.MAX_RETRIES} attempts: {last_error}")

    def fetch_category(self, slug):
        html = self._get(f"{config.BASE_URL}/category/{slug}").text
        if self.cache_dir is not None:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            (self.cache_dir / f"{slug}.html").write_text(html, encoding="utf-8")
        return html

    def fetch_sitemap(self):
        return self._get(f"{config.BASE_URL}/sitemap.xml").text

    def fetch_fx(self, url):
        return self._get(url).json()
