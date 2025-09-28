import sys
import threading
from types import ModuleType, SimpleNamespace

try:  # pragma: no cover - dependency shim for test environment
    import bs4  # type: ignore
except ModuleNotFoundError:  # pragma: no cover - dependency shim for test environment
    bs4_stub = ModuleType("bs4")
    bs4_stub.BeautifulSoup = object  # type: ignore[attr-defined]
    bs4_stub.Tag = object  # type: ignore[attr-defined]
    sys.modules["bs4"] = bs4_stub

import pytest

from clone_audit.analyzer import SiteAnalyzer
from clone_audit.config import ComparisonConfig, CrawlConfig, ExtractionConfig
from clone_audit.models import (
    ComparisonResult,
    CrawlResult,
    HostingRecord,
    SimilarityBreakdown,
    SiteArtifacts,
    WhoisRecord,
)


def _make_site(url: str) -> SiteArtifacts:
    return SiteArtifacts(crawl=CrawlResult(root_url=url, snapshots=[]))


def _make_analyzer() -> SiteAnalyzer:
    crawl_config = CrawlConfig(base_url="https://placeholder.test")
    extraction_config = ExtractionConfig()
    comparison_config = ComparisonConfig()
    return SiteAnalyzer(
        crawl_config=crawl_config,
        extraction_config=extraction_config,
        comparison_config=comparison_config,
    )


def _fake_compare(base: SiteArtifacts, clone: SiteArtifacts) -> ComparisonResult:
    return ComparisonResult(
        base=base,
        clone=clone,
        text_matches=[],
        image_matches=[],
        structure_matches=[],
        breakdown=SimilarityBreakdown(0.0, 0.0, 0.0, 0.0),
    )


def test_run_crawls_sites_in_parallel(monkeypatch: pytest.MonkeyPatch) -> None:
    analyzer = _make_analyzer()
    analyzer._comparison = SimpleNamespace(compare=_fake_compare)

    base_url = "https://base.test"
    clone_url = "https://clone.test"
    artefacts = {
        base_url: _make_site(base_url),
        clone_url: _make_site(clone_url),
    }
    monkeypatch.setattr(SiteAnalyzer, "_extract", lambda self, crawl: artefacts[crawl.root_url])

    barrier = threading.Barrier(2)

    def fake_crawl_site(self: SiteAnalyzer, url: str) -> CrawlResult:
        try:
            barrier.wait(timeout=1.0)
        except threading.BrokenBarrierError as exc:  # pragma: no cover - defensive
            pytest.fail(f"site crawls were not executed in parallel: {exc}")
        return CrawlResult(root_url=url, snapshots=[])

    monkeypatch.setattr(SiteAnalyzer, "_crawl_site", fake_crawl_site)

    def fake_lookup(self: SiteAnalyzer, target: str) -> WhoisRecord:
        return WhoisRecord(
            domain=target,
            registrar=None,
            creation_date=None,
            updated_date=None,
            expiration_date=None,
            raw_text=None,
            error=None,
        )

    monkeypatch.setattr(SiteAnalyzer, "_lookup_whois", fake_lookup)

    def fake_hosting(self: SiteAnalyzer, target: str) -> HostingRecord:
        return HostingRecord(
            domain=target,
            ip="203.0.113.10",
            network_name="ExampleNet",
            organization="Example Hosting",
            country="US",
            source="https://rdap.example/ip/203.0.113.10",
            raw=None,
            error=None,
        )

    monkeypatch.setattr(SiteAnalyzer, "_lookup_hosting", fake_hosting)

    result = analyzer.run(base_url, clone_url)

    assert result.base is artefacts[base_url]
    assert result.clone is artefacts[clone_url]
    assert not barrier.broken
    assert set(result.timings.crawl.keys()) == {"base", "clone"}
    assert set(result.timings.extract.keys()) == {"base", "clone"}
    assert result.timings.compare >= 0.0


def test_run_performs_whois_in_parallel(monkeypatch: pytest.MonkeyPatch) -> None:
    analyzer = _make_analyzer()
    analyzer._comparison = SimpleNamespace(compare=_fake_compare)

    base_url = "https://base.test"
    clone_url = "https://clone.test"
    artefacts = {
        base_url: _make_site(base_url),
        clone_url: _make_site(clone_url),
    }

    monkeypatch.setattr(SiteAnalyzer, "_crawl_site", lambda self, url: CrawlResult(root_url=url, snapshots=[]))
    monkeypatch.setattr(SiteAnalyzer, "_extract", lambda self, crawl: artefacts[crawl.root_url])

    whois_barrier = threading.Barrier(2)

    def fake_lookup(self: SiteAnalyzer, target: str) -> WhoisRecord:
        try:
            whois_barrier.wait(timeout=1.0)
        except threading.BrokenBarrierError as exc:  # pragma: no cover - defensive
            pytest.fail(f"WHOIS lookups were not executed in parallel: {exc}")
        return WhoisRecord(
            domain=target,
            registrar=None,
            creation_date=None,
            updated_date=None,
            expiration_date=None,
            raw_text=None,
            error=None,
        )

    monkeypatch.setattr(SiteAnalyzer, "_lookup_whois", fake_lookup)

    hosting_barrier = threading.Barrier(2)

    def fake_hosting(self: SiteAnalyzer, target: str) -> HostingRecord:
        try:
            hosting_barrier.wait(timeout=1.0)
        except threading.BrokenBarrierError as exc:  # pragma: no cover - defensive
            pytest.fail(f"Hosting lookups were not executed in parallel: {exc}")
        return HostingRecord(
            domain=target,
            ip="198.51.100.5",
            network_name="Net-{target}".format(target=target),
            organization="Example Hosting",
            country="US",
            source=None,
            raw=None,
            error=None,
        )

    monkeypatch.setattr(SiteAnalyzer, "_lookup_hosting", fake_hosting)

    result = analyzer.run(base_url, clone_url)

    assert result.base is artefacts[base_url]
    assert result.clone is artefacts[clone_url]
    assert not whois_barrier.broken
    assert not hosting_barrier.broken
    assert set(result.timings.whois.keys()) == {"base", "clone"}
    assert set(result.timings.hosting.keys()) == {"base", "clone"}
    assert result.timings.total >= result.timings.compare
