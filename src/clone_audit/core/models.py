"""Core dataclasses representing crawl and comparison artefacts."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Iterable, Optional


@dataclass(slots=True)
class PageSnapshot:
    url: str
    depth: int
    status_code: Optional[int]
    html: str
    content_type: Optional[str]
    fetched_at: datetime
    discovered_urls: list[str] = field(default_factory=list)
    error: Optional[str] = None


@dataclass(slots=True)
class TextArtifact:
    page_url: str
    locator: str
    text: str
    token_count: int
    tokens: tuple[str, ...] = tuple()

    def snippet(self, length: int = 200) -> str:
        return self.text[:length].strip()


@dataclass(slots=True)
class ImageArtifact:
    page_url: str
    url: str
    hash_bits: Optional[str]
    bytes_size: Optional[int]
    content_type: Optional[str]
    preview_bytes: Optional[bytes] = None


@dataclass(slots=True)
class StructureSignature:
    page_url: str
    depth: int
    tag_sequence: tuple[str, ...]


@dataclass(slots=True)
class CrawlResult:
    root_url: str
    snapshots: list[PageSnapshot]
    errors: list[str] = field(default_factory=list)

    def __iter__(self) -> Iterable[PageSnapshot]:
        return iter(self.snapshots)


@dataclass(slots=True)
class SiteArtifacts:
    crawl: CrawlResult
    texts: list[TextArtifact] = field(default_factory=list)
    images: list[ImageArtifact] = field(default_factory=list)
    structures: list[StructureSignature] = field(default_factory=list)


@dataclass(slots=True)
class TextMatch:
    base: TextArtifact
    clone: TextArtifact
    similarity: float
    high_confidence: bool


@dataclass(slots=True)
class ImageMatch:
    base: ImageArtifact
    clone: ImageArtifact
    hamming_distance: int
    similarity: float


@dataclass(slots=True)
class StructureMatch:
    base: StructureSignature
    clone: StructureSignature
    similarity: float


@dataclass(slots=True)
class SimilarityBreakdown:
    text_score: float
    image_score: float
    structure_score: float
    overall_score: float


@dataclass(slots=True)
class ComparisonResult:
    base: SiteArtifacts
    clone: SiteArtifacts
    text_matches: list[TextMatch]
    image_matches: list[ImageMatch]
    structure_matches: list[StructureMatch]
    breakdown: SimilarityBreakdown


@dataclass(slots=True)
class HostingRecord:
    domain: str
    ip: Optional[str]
    network_name: Optional[str]
    organization: Optional[str]
    country: Optional[str]
    source: Optional[str] = None
    raw: Optional[dict[str, Any]] = None
    error: Optional[str] = None


@dataclass(slots=True)
class WhoisRecord:
    domain: str
    registrar: Optional[str]
    creation_date: Optional[datetime]
    updated_date: Optional[datetime]
    expiration_date: Optional[datetime]
    name_servers: tuple[str, ...] = tuple()
    raw_text: Optional[str] = None
    error: Optional[str] = None
