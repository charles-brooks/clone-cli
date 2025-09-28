import sys
import threading
import time
from types import ModuleType

try:  # pragma: no cover - dependency shim for test environment
    import bs4  # type: ignore
except ModuleNotFoundError:  # pragma: no cover - dependency shim for test environment
    bs4_stub = ModuleType("bs4")

    class _StubSoup:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

        def find_all(self, *_args, **_kwargs):
            return []

    bs4_stub.BeautifulSoup = _StubSoup  # type: ignore[attr-defined]
    sys.modules["bs4"] = bs4_stub

import pytest

from clone_audit.config import CrawlConfig
from clone_audit.crawler import Crawler


class FakeResponse:
    def __init__(self, html: str) -> None:
        self.status_code = 200
        self.headers = {"Content-Type": "text/html"}
        self.text = html


class SessionFactory:
    def __init__(self, html_map: dict[str, str], delay: float = 0.01) -> None:
        self.html_map = html_map
        self.delay = delay
        self.lock = threading.Lock()
        self.active = 0
        self.max_active = 0

    def __call__(self):
        factory = self

        class _Session:
            def __init__(self) -> None:
                self.headers: dict[str, str] = {}

            def get(self, url: str, timeout: float, allow_redirects: bool):
                html = factory.html_map.get(url)
                if html is None:
                    raise AssertionError(f"Unexpected URL requested: {url}")
                with factory.lock:
                    factory.active += 1
                    factory.max_active = max(factory.max_active, factory.active)
                time.sleep(factory.delay)
                with factory.lock:
                    factory.active -= 1
                return FakeResponse(html)

            def close(self) -> None:  # pragma: no cover - compatibility
                pass

        return _Session()


@pytest.mark.parametrize("concurrency", [1, 3])
def test_crawler_parallel_fetches(monkeypatch: pytest.MonkeyPatch, concurrency: int) -> None:
    base_url = "https://example.test"
    html_map = {
        "https://example.test/": "<a href='/a'>A</a><a href='/b'>B</a>",
        "https://example.test/a": "<p>A</p>",
        "https://example.test/b": "<p>B</p>",
    }
    link_map = {
        "<a href='/a'>A</a><a href='/b'>B</a>": ["/a", "/b"],
        "<p>A</p>": [],
        "<p>B</p>": [],
    }

    class FakeTag:
        def __init__(self, href: str) -> None:
            self._href = href

        def get(self, key: str, default=None):
            if key == "href":
                return self._href
            return default

    class FakeSoup:
        def __init__(self, html: str, parser: str) -> None:
            self._links = link_map.get(html, [])

        def find_all(self, selector, href=False):
            if selector == "a":
                return [FakeTag(link) for link in self._links]
            return []

    factory = SessionFactory(html_map)
    monkeypatch.setattr("clone_audit.crawler.requests.Session", factory)
    monkeypatch.setattr("clone_audit.crawler.BeautifulSoup", FakeSoup)

    config = CrawlConfig(
        base_url=base_url,
        max_pages=3,
        max_depth=1,
        delay_seconds=0.0,
        page_concurrency=concurrency,
    )
    crawler = Crawler(config=config)
    result = crawler.crawl()

    assert len(result.snapshots) == 3
    if concurrency > 1:
        assert factory.max_active >= 2
    else:
        assert factory.max_active == 1
