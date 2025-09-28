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

## Planned Architecture
- `crawler.py`: BFS crawler constrained to same-host URLs, producing `PageSnapshot` objects with HTML payloads and metadata.
- `extractor.py`: Pulls text blocks (visible content), downloads images to hash (aHash), and derives structural tag n-grams.
- `comparer.py`: Matches text/image/structure artefacts between sites using simple heuristics (cosine similarity for text shingles, Hamming distance for hashes, Jaccard for structure).
- `scorer.py`: Aggregates per-signal similarities into an overall score with configurable weights.
- `whois_client.py`: Retrieves registrar details via `python-whois` (fall back to socket whois).
- `report.py`: Renders Markdown + optional JSON showing top matches, divergence notes, and WHOIS summary.
- `cli.py` (entry point): Argument parsing, dependency checks, orchestration, error handling.

All components will be kept modular so future contributors can swap out heuristics with richer models or add persistence.

## Usage (planned)
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export PATH="$PATH:/home/workstation/CAR/clone-cli/src"; PYTHONPATH=src python -m clone_audit.cli \
  --base https://legit.example --clone https://www.example.com \
  --max-pages 50 \
  --max-depth 2 \
  --output report.md \
  --pdf-output report.pdf \
  --homepage-threshold 0.7
```

CLI flags (to be implemented; defaults may change):
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

## Testing Approach (next iteration)
- Unit tests for URL normalization, extraction helpers, and similarity scoring.
- Tiny local fixtures (sample HTML + images) for deterministic comparisons.
- CLI smoke test to ensure end-to-end run produces a report.

### Running Tests Today
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
