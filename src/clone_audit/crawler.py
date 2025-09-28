"""Website crawler for collecting page snapshots."""
from __future__ import annotations

import logging
from collections import deque
from datetime import datetime
from queue import Empty, Queue
from threading import Event, Lock, Thread
from time import monotonic, perf_counter
from typing import Deque

import requests
from bs4 import BeautifulSoup

from .config import CrawlConfig
from .models import CrawlResult, PageSnapshot
from .utils import is_html_content, is_same_domain, normalize_url, resolve_url, sleep

logger = logging.getLogger(__name__)


class Crawler:
    """Breadth-first crawler constrained to a single site."""

    def __init__(self, config: CrawlConfig, session: requests.Session | None = None) -> None:
        self.config = config
        if session is None:
            session = requests.Session()
        self.session = session
        # Always enforce the configured user-agent so ModSecurity/WAF rules don't
        # see the default python-requests fingerprint.
        self.session.headers["User-Agent"] = self.config.user_agent

    def crawl(self) -> CrawlResult:
        start = perf_counter()
        if self.config.page_concurrency <= 1:
            result = self._crawl_serial()
        else:
            result = self._crawl_parallel()
        duration = perf_counter() - start
        logger.info(
            "Crawled %s pages (errors=%s, depth<=%s) in %.2fs",
            len(result.snapshots),
            len(result.errors),
            self.config.max_depth,
            duration,
        )
        return result

    def _crawl_serial(self) -> CrawlResult:
        queue: Deque[tuple[str, int]] = deque([(self.config.base_url, 0)])
        visited: set[str] = set()
        snapshots: list[PageSnapshot] = []
        errors: list[str] = []

        while queue and len(snapshots) < self.config.max_pages:
            url, depth = queue.popleft()
            normalized = normalize_url(url)
            if normalized in visited:
                continue
            visited.add(normalized)
            if depth > self.config.max_depth:
                continue

            try:
                response = self.session.get(
                    normalized,
                    timeout=self.config.timeout,
                    allow_redirects=True,
                )
                status_code = response.status_code
                content_type = response.headers.get("Content-Type")
                html = response.text if is_html_content(content_type) else ""
            except requests.RequestException as exc:  # pragma: no cover - network edge
                errors.append(f"{normalized}: {exc}")
                continue

            discovered: list[str] = []
            if html:
                soup = BeautifulSoup(html, "html.parser")
                for tag in soup.find_all("a", href=True):
                    link_url = resolve_url(normalized, tag.get("href"))
                    if not link_url:
                        continue
                    link_normalized = normalize_url(link_url)
                    if self.config.same_domain_only and not is_same_domain(
                        link_normalized, self.config.base_url
                    ):
                        continue
                    if link_normalized not in visited:
                        discovered.append(link_normalized)
                        queue.append((link_normalized, depth + 1))

            snapshot = PageSnapshot(
                url=normalized,
                depth=depth,
                status_code=status_code,
                html=html,
                content_type=content_type,
                fetched_at=datetime.utcnow(),
                discovered_urls=discovered,
            )
            snapshots.append(snapshot)

            if self.config.delay_seconds > 0:
                sleep(self.config.delay_seconds)

        return CrawlResult(root_url=self.config.base_url, snapshots=snapshots, errors=errors)

    def _crawl_parallel(self) -> CrawlResult:
        work_queue: Queue[tuple[str, int] | None] = Queue()
        work_queue.put((self.config.base_url, 0))
        visited: set[str] = set()
        visited_lock = Lock()
        snapshots: list[PageSnapshot] = []
        snapshots_lock = Lock()
        errors: list[str] = []
        errors_lock = Lock()
        completion_event = Event()
        request_lock = Lock()
        last_request = [monotonic() - self.config.delay_seconds]

        def create_session() -> requests.Session:
            session = requests.Session()
            session.headers.update(self.session.headers)
            session.headers["User-Agent"] = self.config.user_agent
            return session

        def acquire_request_slot() -> None:
            with request_lock:
                if self.config.delay_seconds <= 0:
                    last_request[0] = monotonic()
                    return
                now = monotonic()
                wait = self.config.delay_seconds - (now - last_request[0])
                if wait > 0:
                    sleep(wait)
                last_request[0] = monotonic()

        def worker() -> None:
            session = create_session()
            try:
                while True:
                    try:
                        item = work_queue.get(timeout=0.1)
                    except Empty:
                        if completion_event.is_set():
                            break
                        continue
                    if item is None:
                        work_queue.task_done()
                        break
                    url, depth = item
                    if completion_event.is_set():
                        work_queue.task_done()
                        continue

                    normalized = normalize_url(url)
                    with visited_lock:
                        if normalized in visited:
                            work_queue.task_done()
                            continue
                        visited.add(normalized)

                    if depth > self.config.max_depth:
                        work_queue.task_done()
                        continue

                    acquire_request_slot()
                    try:
                        response = session.get(
                            normalized,
                            timeout=self.config.timeout,
                            allow_redirects=True,
                        )
                        status_code = response.status_code
                        content_type = response.headers.get("Content-Type")
                        html = response.text if is_html_content(content_type) else ""
                    except requests.RequestException as exc:  # pragma: no cover - network edge
                        with errors_lock:
                            errors.append(f"{normalized}: {exc}")
                        work_queue.task_done()
                        continue

                    discovered: list[str] = []
                    if html:
                        soup = BeautifulSoup(html, "html.parser")
                        for tag in soup.find_all("a", href=True):
                            link_url = resolve_url(normalized, tag.get("href"))
                            if not link_url:
                                continue
                            link_normalized = normalize_url(link_url)
                            if self.config.same_domain_only and not is_same_domain(
                                link_normalized, self.config.base_url
                            ):
                                continue
                            discovered.append(link_normalized)
                            if not completion_event.is_set():
                                work_queue.put((link_normalized, depth + 1))

                    snapshot = PageSnapshot(
                        url=normalized,
                        depth=depth,
                        status_code=status_code,
                        html=html,
                        content_type=content_type,
                        fetched_at=datetime.utcnow(),
                        discovered_urls=discovered,
                    )
                    reached_limit = False
                    with snapshots_lock:
                        if len(snapshots) < self.config.max_pages:
                            snapshots.append(snapshot)
                            reached_limit = len(snapshots) >= self.config.max_pages
                        else:
                            reached_limit = True
                    if reached_limit:
                        completion_event.set()
                    work_queue.task_done()
            finally:
                session.close()

        threads = [Thread(target=worker, name=f"crawler-worker-{i}") for i in range(self.config.page_concurrency)]
        for thread in threads:
            thread.daemon = True
            thread.start()

        work_queue.join()
        completion_event.set()
        for _ in threads:
            work_queue.put(None)
        for thread in threads:
            thread.join()

        return CrawlResult(root_url=self.config.base_url, snapshots=snapshots, errors=errors)


__all__ = ["Crawler"]
