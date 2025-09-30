# Website Clone Similarity Auditor

Lightweight Python tooling that crawls a legitimate site and a suspected clone, extracts comparable artefacts (text, images, DOM structure), and generates a similarity report enriched with WHOIS registrar data. Designed for quick triage of phishing lookalikes without a heavy infrastructure investment.

## Why This Exists
Security responders often need a fast confidence check when a clone is reported. Manual diffing is tedious, and fully fledged takedown platforms are overkill. This project aims to provide a scriptable middle ground that can grow as the team gains traction.

## Current Scope (MVP)
- Crawl each target domain with configurable depth, breadth, and delays.
- Record per-page text snippets, image hashes, and lightweight structural fingerprints.
- Cross-compare collected artefacts to compute similarity scores and highlight 1:1 matches.
- Perform WHOIS lookups for each domain and surface registrar/creation metadata.
- Produce a human-readable report (Markdown) and optional JSON dump for automation.

## Architecture Overview
Core crawl/extract/compare logic now lives under `clone_audit/core` so both the CLI and future long-lived services share deterministic building blocks. See `docs/core-architecture.md` for a deeper dive.

- `clone_audit/core/crawler.py`: breadth-first crawler returning `PageSnapshot` objects with HTML payloads and metadata.
- `clone_audit/core/extractor.py`: converts snapshots into text, image, and structural artefacts.
- `clone_audit/core/comparer.py`: scores artefacts via lightweight heuristics with `ScoreAggregator` in `core/scoring`.
- `clone_audit/core/models.py`: dataclasses passed between modules (snapshots, artefacts, matches, breakdowns).
- `clone_audit/adapters/__init__.py`: minimal protocols for WHOIS and hosting lookups so callers can inject alternatives.
- `whois_client.py` / `hosting_client.py`: default adapter implementations used by the CLI.
- `report.py`: renders Markdown, JSON, and PDF outputs.
- `cli.py`: argument parsing and orchestration built on the shared library.

Legacy module paths (`clone_audit.crawler`, `clone_audit.models`, etc.) re-export the core modules so existing imports and tests continue to work while new code can depend on the shared package.

## Usage (planned)
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export PATH="$PATH:/home/workstation/CAR/clone-cli/src"; PYTHONPATH=src python -m clone_audit.cli \
  --base https://cryptoassetrecovery.com --clone https://www.example.com \
  --pdf-output report.pdf \
  --homepage-tool chrome \
  --homepage-delay 4 \
  --homepage-timeout 60 \
```

CLI flags (defaults may change):
- `--base`, `--clone` (required): root URLs.
- `--max-pages`, `--max-depth`: crawl limits.
- `--delay`: seconds between requests per host.
- `--collect-images/--no-collect-images`, `--collect-text`, `--collect-structure`: feature toggles.
- `--output`: path for Markdown report; `--json-output` optional raw data dump.
- `--pdf-output`: optional PDF summary with embedded image previews of top matches.
- `--no-homepage`: skip automatic homepage screenshot capture (defaults to on when wkhtmltoimage is available).
- `--homepage-threshold`: tweak the similarity required before attempting homepage screenshots.
- `--homepage-timeout`: limit how long `wkhtmltoimage` is allowed to run per capture.
- `--homepage-delay`: add a JavaScript render delay before capturing screenshots.
- `--homepage-width`: change the screenshot width (default 1280px).
- `--homepage-height`: change the screenshot height (default 720px).
- `--homepage-tool`: choose `auto`, `chrome`, or `wkhtml` for screenshot capture.
- `--homepage-user-agent`: override the browser User-Agent used for captures (defaults to modern Chrome).
- `--weights`: optional JSON/YAML for signal weighting.

## Dependencies
- Python 3.10+
- `requests`, `beautifulsoup4`
- `Pillow` (for image hashing)
- `numpy` (assist with hashing math)
- `python-whois` (optional, degrades gracefully)
- `fpdf2` (generates PDF reports with image previews)
- `wkhtmltoimage` binary available on PATH (enables homepage screenshots in PDFs)
- Headless Chrome/Chromium (`google-chrome --headless` or `chromium --headless`) recommended for full-fidelity homepage captures

Dependency management will start with a simple `requirements.txt`. Packaging (Poetry, pipx) can be revisited later.

## Testing
Unit tests cover URL utilities, crawl/extract behaviour, comparison heuristics, reporting, and analyzer orchestration. Add fixtures or regression captures alongside tests to keep runs deterministic.

```bash
PYTHONPATH=src python -m pytest
```

## Roadmap Highlights
1. Implement crawler + extractor skeleton with logging and polite defaults.
2. Layer in comparison primitives and overall similarity scoring.
3. Add Markdown report generator with WHOIS data embedding.
4. Expand tests and add sample datasets.
5. Explore richer text similarity (TF-IDF or embeddings) once baseline is validated.

## Contributing & Collaboration
- Keep changes small and well-documented; note new assumptions in PR descriptions.
- Avoid bundling optional heavy dependencies without discussion.
- Share real-world phishing artefacts privately; do not commit sensitive data.

## License
TBD — defaulting to internal usage until ownership decides otherwise.
