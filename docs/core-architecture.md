# Core Module Overview

This project now exposes its crawl/extract/compare building blocks via `clone_audit.core`.  The goal is to keep the logic small and deterministic so other services (cert monitoring, proactive crawl, reporting) can reuse the same APIs without carrying CLI-specific baggage.

- `clone_audit.core.crawler` — breadth-first crawler that returns `PageSnapshot` objects.
- `clone_audit.core.extractor` — converts crawl output into text, image, and structural artefacts.
- `clone_audit.core.comparer` — performs similarity scoring using `ScoreAggregator` from `core.scoring`.
- `clone_audit.core.models` — dataclasses shared by all components.
- `clone_audit.core.scoring` — weight-aware scoring helper used by the comparer.

Legacy imports like `clone_audit.crawler.Crawler` and `clone_audit.models.PageSnapshot` still work through thin compatibility shims.  New code should prefer importing from `clone_audit.core` directly.  This keeps future service runners free to inject alternate adapters while preserving today’s CLI ergonomics.

Adapter protocols live in `clone_audit.adapters` so tests and services can provide custom WHOIS or hosting clients to `SiteAnalyzer` without modifying core modules.
