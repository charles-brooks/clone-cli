"""Command-line interface for the clone similarity auditor."""
from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

if __package__ is None or __package__ == "":  # pragma: no cover - script execution path
    import sys

    PACKAGE_ROOT = Path(__file__).resolve().parents[1]
    if str(PACKAGE_ROOT) not in sys.path:
        sys.path.insert(0, str(PACKAGE_ROOT))

    from clone_audit.analyzer import SiteAnalyzer
    from clone_audit.config import (
        ComparisonConfig,
        CrawlConfig,
        ExtractionConfig,
        ReportConfig,
        DEFAULT_CRAWLER_USER_AGENT,
    )
    from clone_audit.report import ReportBuilder
else:  # pragma: no cover - package execution path
    from .analyzer import SiteAnalyzer
    from .config import (
        ComparisonConfig,
        CrawlConfig,
        ExtractionConfig,
        ReportConfig,
        DEFAULT_CRAWLER_USER_AGENT,
    )
    from .report import ReportBuilder

logger = logging.getLogger(__name__)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Website clone similarity auditor")
    parser.add_argument("--base", required=True, help="URL of the legitimate site")
    parser.add_argument("--clone", required=True, help="URL of the suspected clone")
    parser.add_argument("--max-pages", type=int, default=50, help="Maximum pages to crawl per site")
    parser.add_argument("--max-depth", type=int, default=2, help="Maximum crawl depth")
    parser.add_argument("--delay", type=float, default=0.5, help="Delay between requests (seconds)")
    parser.add_argument("--timeout", type=float, default=10.0, help="Request timeout (seconds)")
    parser.add_argument(
        "--crawl-concurrency",
        type=int,
        default=1,
        help="Number of parallel fetchers per site (1 disables parallel crawl)",
    )
    parser.add_argument(
        "--user-agent",
        default=DEFAULT_CRAWLER_USER_AGENT,
        help="User-Agent header to send with crawler requests",
    )
    parser.add_argument("--allow-offsite", action="store_true", help="Allow crawler to leave the starting domain")
    parser.add_argument("--no-images", action="store_true", help="Skip image collection and comparison")
    parser.add_argument("--no-text", action="store_true", help="Skip text collection and comparison")
    parser.add_argument("--no-structure", action="store_true", help="Skip DOM structure comparison")
    parser.add_argument("--text-threshold", type=float, default=0.75, help="Minimum similarity ratio for text matches")
    parser.add_argument("--high-confidence", type=float, default=0.95, help="Similarity ratio considered a high-confidence text match")
    parser.add_argument("--image-distance", type=int, default=10, help="Maximum Hamming distance for image matches (0-64)")
    parser.add_argument("--structure-threshold", type=float, default=0.6, help="Minimum structural similarity for reporting")
    parser.add_argument("--weight-text", type=float, default=0.4, help="Weight assigned to text similarity")
    parser.add_argument("--weight-images", type=float, default=0.4, help="Weight assigned to image similarity")
    parser.add_argument("--weight-structure", type=float, default=0.2, help="Weight assigned to structure similarity")
    parser.add_argument("--top-matches", type=int, default=10, help="Maximum matches to display per category")
    parser.add_argument("--output", type=Path, help="Path to save Markdown report; prints to stdout if omitted")
    parser.add_argument("--json-output", type=Path, help="Optional path for JSON report payload")
    parser.add_argument("--pdf-output", type=Path, help="Optional path for PDF report with image previews")
    parser.add_argument("--include-raw", action="store_true", help="Include raw text and WHOIS payloads in reports")
    parser.add_argument("--no-homepage", action="store_true", help="Skip homepage screenshot comparison in PDF output")
    parser.add_argument("--homepage-threshold", type=float, default=0.7, help="Minimum overall/structural similarity required before capturing homepage screenshots")
    parser.add_argument("--homepage-timeout", type=float, default=20.0, help="Timeout (seconds) for homepage screenshot capture via wkhtmltoimage")
    parser.add_argument("--homepage-delay", type=float, default=2.0, help="JavaScript render delay (seconds) before capturing homepage screenshots")
    parser.add_argument("--homepage-width", type=int, default=1280, help="Pixel width for homepage captures")
    parser.add_argument("--homepage-height", type=int, default=720, help="Pixel height for homepage captures")
    parser.add_argument("--homepage-tool", choices=["auto", "chrome", "wkhtml"], default="auto", help="Screenshot engine preference")
    parser.add_argument("--homepage-user-agent", default="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36", help="Override User-Agent for homepage captures")
    parser.add_argument("--log-level", default="INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR"], help="Logging verbosity")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    configure_logging(args.log_level)

    crawl_config = CrawlConfig(
        base_url=args.base,
        max_pages=args.max_pages,
        max_depth=args.max_depth,
        delay_seconds=args.delay,
        timeout=args.timeout,
        same_domain_only=not args.allow_offsite,
        user_agent=args.user_agent,
        page_concurrency=max(1, args.crawl_concurrency),
    )
    extraction_config = ExtractionConfig(
        collect_images=not args.no_images,
        collect_text=not args.no_text,
        collect_structure=not args.no_structure,
    )
    comparison_config = ComparisonConfig(
        text_threshold=args.text_threshold,
        high_confidence_threshold=args.high_confidence,
        image_hash_threshold=args.image_distance,
        structure_threshold=args.structure_threshold,
        weight_text=args.weight_text,
        weight_images=args.weight_images,
        weight_structure=args.weight_structure,
        top_match_limit=args.top_matches,
    )
    report_config = ReportConfig(
        output_path=str(args.output) if args.output else None,
        json_output_path=str(args.json_output) if args.json_output else None,
        pdf_output_path=str(args.pdf_output) if args.pdf_output else None,
        include_raw_data=args.include_raw,
        include_homepage=not args.no_homepage,
        homepage_similarity_threshold=args.homepage_threshold,
        homepage_capture_timeout=args.homepage_timeout,
        homepage_render_delay=args.homepage_delay,
        homepage_width=args.homepage_width,
        homepage_height=args.homepage_height,
        homepage_capture_tool=args.homepage_tool,
        homepage_user_agent=args.homepage_user_agent,
    )

    analyzer = SiteAnalyzer(
        crawl_config=crawl_config,
        extraction_config=extraction_config,
        comparison_config=comparison_config,
    )

    logger.info("Running analysis")
    analysis = analyzer.run(args.base, args.clone)

    builder = ReportBuilder(report_config)
    markdown = builder.build_markdown(analysis)
    if args.output:
        _ensure_parent(args.output)
        args.output.write_text(markdown, encoding="utf-8")
        logger.info("Markdown report written to %s", args.output)
    else:
        print(markdown)

    if args.json_output:
        _ensure_parent(args.json_output)
        payload = builder.build_json(analysis)
        args.json_output.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        logger.info("JSON report written to %s", args.json_output)

    if args.pdf_output:
        _ensure_parent(args.pdf_output)
        try:
            builder.build_pdf(analysis, str(args.pdf_output))
        except RuntimeError as exc:
            logger.error("Failed to generate PDF report: %s", exc)
        else:
            logger.info("PDF report written to %s", args.pdf_output)

    return 0


def configure_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


def _ensure_parent(path: Path) -> None:
    if path.parent and not path.parent.exists():
        path.parent.mkdir(parents=True, exist_ok=True)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
