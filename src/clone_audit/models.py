"""Compatibility shim exporting core data models at the legacy module path."""
from __future__ import annotations

from .core.models import (
    ComparisonResult,
    CrawlResult,
    HostingRecord,
    ImageArtifact,
    ImageMatch,
    PageSnapshot,
    SiteArtifacts,
    SimilarityBreakdown,
    StructureMatch,
    StructureSignature,
    TextArtifact,
    TextMatch,
    WhoisRecord,
)

__all__ = [
    "ComparisonResult",
    "CrawlResult",
    "HostingRecord",
    "ImageArtifact",
    "ImageMatch",
    "PageSnapshot",
    "SiteArtifacts",
    "SimilarityBreakdown",
    "StructureMatch",
    "StructureSignature",
    "TextArtifact",
    "TextMatch",
    "WhoisRecord",
]
