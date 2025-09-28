"""Configuration dataclasses for the clone auditor."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


DEFAULT_CRAWLER_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


@dataclass(slots=True)
class CrawlConfig:
    base_url: str
    max_pages: int = 50
    max_depth: int = 2
    delay_seconds: float = 0.5
    timeout: float = 10.0
    same_domain_only: bool = True
    user_agent: str = DEFAULT_CRAWLER_USER_AGENT
    page_concurrency: int = 1


@dataclass(slots=True)
class ExtractionConfig:
    collect_images: bool = True
    collect_text: bool = True
    collect_structure: bool = True
    min_text_length: int = 40
    max_text_length: int = 2000


@dataclass(slots=True)
class ComparisonConfig:
    text_threshold: float = 0.75
    high_confidence_threshold: float = 0.95
    image_hash_threshold: int = 10  # max Hamming distance (out of 64 bits)
    structure_threshold: float = 0.6
    weight_text: float = 0.4
    weight_images: float = 0.4
    weight_structure: float = 0.2
    top_match_limit: int = 10

    def normalised_weights(self) -> tuple[float, float, float]:
        total = self.weight_text + self.weight_images + self.weight_structure
        if total == 0:
            return (0.0, 0.0, 0.0)
        return (
            self.weight_text / total,
            self.weight_images / total,
            self.weight_structure / total,
        )


@dataclass(slots=True)
class ReportConfig:
    output_path: Optional[str] = None
    json_output_path: Optional[str] = None
    pdf_output_path: Optional[str] = None
    include_raw_data: bool = False
    include_errors: bool = True
    include_homepage: bool = True
    homepage_similarity_threshold: float = 0.7
    homepage_capture_timeout: float = 20.0
    homepage_render_delay: float = 2.0
    homepage_width: int = 1280
    homepage_height: int = 720
    homepage_capture_tool: str = "auto"  # auto|chrome|wkhtml
    homepage_user_agent: str = DEFAULT_CRAWLER_USER_AGENT
