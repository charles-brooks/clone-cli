"""High-level orchestration for running the clone similarity audit."""
from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from time import perf_counter

import requests

from .config import ComparisonConfig, CrawlConfig, ExtractionConfig
from .adapters import HostingProvider, WhoisProvider
from .core import (
    ComparisonResult,
    Comparer,
    CrawlResult,
    Crawler,
    Extractor,
    HostingRecord,
    SiteArtifacts,
    WhoisRecord,
)
from .whois_client import WhoisClient
from .hosting_client import HostingClient

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AnalysisTimings:
    crawl: dict[str, float] = field(default_factory=dict)
    extract: dict[str, float] = field(default_factory=dict)
    whois: dict[str, float] = field(default_factory=dict)
    hosting: dict[str, float] = field(default_factory=dict)
    compare: float = 0.0

    @property
    def total(self) -> float:
        return (
            sum(self.crawl.values())
            + sum(self.extract.values())
            + sum(self.whois.values())
            + sum(self.hosting.values())
            + self.compare
        )


@dataclass(frozen=True)
class AnalysisResult:
    base: SiteArtifacts
    clone: SiteArtifacts
    comparison: ComparisonResult
    base_whois: WhoisRecord
    clone_whois: WhoisRecord
    base_hosting: HostingRecord
    clone_hosting: HostingRecord
    timings: AnalysisTimings


class SiteAnalyzer:
    """Coordinates crawl, extraction, comparison, and WHOIS lookups."""

    def __init__(
        self,
        crawl_config: CrawlConfig,
        extraction_config: ExtractionConfig,
        comparison_config: ComparisonConfig,
        *,
        whois_provider: WhoisProvider | None = None,
        hosting_provider: HostingProvider | None = None,
    ) -> None:
        self.crawl_config = crawl_config
        self.extraction_config = extraction_config
        self.comparison_config = comparison_config
        self._comparison = Comparer(comparison_config)
        self._whois: WhoisProvider = whois_provider or WhoisClient()
        self._hosting: HostingProvider = hosting_provider or HostingClient()

    def run(self, base_url: str, clone_url: str) -> AnalysisResult:
        logger.info("Starting crawl: base=%s clone=%s", base_url, clone_url)
        crawl_timings: dict[str, float] = {}
        extract_timings: dict[str, float] = {}
        whois_timings: dict[str, float] = {}

        with ThreadPoolExecutor(max_workers=2) as executor:
            base_future = executor.submit(self._timed_crawl, base_url)
            clone_future = executor.submit(self._timed_crawl, clone_url)
            base_crawl, base_crawl_time = base_future.result()
            clone_crawl, clone_crawl_time = clone_future.result()
        crawl_timings["base"] = base_crawl_time
        crawl_timings["clone"] = clone_crawl_time

        start = perf_counter()
        base_artifacts = self._extract(base_crawl)
        extract_timings["base"] = perf_counter() - start

        start = perf_counter()
        clone_artifacts = self._extract(clone_crawl)
        extract_timings["clone"] = perf_counter() - start

        start = perf_counter()
        comparison = self._comparison.compare(base_artifacts, clone_artifacts)
        compare_time = perf_counter() - start

        with ThreadPoolExecutor(max_workers=2) as executor:
            base_future = executor.submit(self._timed_lookup, base_url)
            clone_future = executor.submit(self._timed_lookup, clone_url)
            base_whois, base_whois_time = base_future.result()
            clone_whois, clone_whois_time = clone_future.result()
        whois_timings["base"] = base_whois_time
        whois_timings["clone"] = clone_whois_time

        hosting_timings: dict[str, float] = {}
        with ThreadPoolExecutor(max_workers=2) as executor:
            base_future = executor.submit(self._timed_host_lookup, base_url)
            clone_future = executor.submit(self._timed_host_lookup, clone_url)
            base_hosting, base_host_time = base_future.result()
            clone_hosting, clone_host_time = clone_future.result()
        hosting_timings["base"] = base_host_time
        hosting_timings["clone"] = clone_host_time

        timings = AnalysisTimings(
            crawl=crawl_timings,
            extract=extract_timings,
            whois=whois_timings,
            hosting=hosting_timings,
            compare=compare_time,
        )
        logger.info(
            "Analysis timings (s): crawl=%s extract=%s whois=%s compare=%.2f total=%.2f",
            crawl_timings,
            extract_timings,
            whois_timings,
            compare_time,
            timings.total,
        )

        return AnalysisResult(
            base=base_artifacts,
            clone=clone_artifacts,
            comparison=comparison,
            base_whois=base_whois,
            clone_whois=clone_whois,
            base_hosting=base_hosting,
            clone_hosting=clone_hosting,
            timings=timings,
        )

    def _timed_crawl(self, url: str) -> tuple[CrawlResult, float]:
        start = perf_counter()
        crawl = self._crawl_site(url)
        return crawl, perf_counter() - start

    def _timed_lookup(self, url: str) -> tuple[WhoisRecord, float]:
        start = perf_counter()
        record = self._lookup_whois(url)
        return record, perf_counter() - start

    def _timed_host_lookup(self, url: str) -> tuple[HostingRecord, float]:
        start = perf_counter()
        record = self._lookup_hosting(url)
        return record, perf_counter() - start

    def _crawl_site(self, url: str) -> CrawlResult:
        session = requests.Session()
        try:
            return self._crawl(url, session)
        finally:
            session.close()

    def _crawl(self, url: str, session: requests.Session) -> CrawlResult:
        config = CrawlConfig(
            base_url=url,
            max_pages=self.crawl_config.max_pages,
            max_depth=self.crawl_config.max_depth,
            delay_seconds=self.crawl_config.delay_seconds,
            timeout=self.crawl_config.timeout,
            same_domain_only=self.crawl_config.same_domain_only,
            user_agent=self.crawl_config.user_agent,
            page_concurrency=self.crawl_config.page_concurrency,
        )
        crawler = Crawler(config=config, session=session)
        return crawler.crawl()

    def _extract(self, crawl_result: CrawlResult) -> SiteArtifacts:
        extractor = Extractor(config=self.extraction_config)
        return extractor.extract(crawl_result)

    def _lookup_whois(self, target: str) -> WhoisRecord:
        return self._whois.lookup(target)

    def _lookup_hosting(self, target: str) -> HostingRecord:
        return self._hosting.lookup(target)


__all__ = ["SiteAnalyzer", "AnalysisResult", "AnalysisTimings"]
