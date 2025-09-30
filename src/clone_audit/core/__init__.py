"""Shared, side-effect-light building blocks for clone auditing."""
from __future__ import annotations

from importlib import import_module
from typing import Any

__all__ = [
    "Crawler",
    "Extractor",
    "Comparer",
    "PageSnapshot",
    "CrawlResult",
    "SiteArtifacts",
    "TextArtifact",
    "ImageArtifact",
    "StructureSignature",
    "TextMatch",
    "ImageMatch",
    "StructureMatch",
    "SimilarityBreakdown",
    "ComparisonResult",
    "HostingRecord",
    "WhoisRecord",
]


def __getattr__(name: str) -> Any:  # pragma: no cover - import side effects
    if name == "Crawler":
        module = import_module(".crawler", __name__)
        return module.Crawler
    if name == "Extractor":
        module = import_module(".extractor", __name__)
        return module.Extractor
    if name == "Comparer":
        module = import_module(".comparer", __name__)
        return module.Comparer
    if name in {
        "PageSnapshot",
        "CrawlResult",
        "SiteArtifacts",
        "TextArtifact",
        "ImageArtifact",
        "StructureSignature",
        "TextMatch",
        "ImageMatch",
        "StructureMatch",
        "SimilarityBreakdown",
        "ComparisonResult",
        "HostingRecord",
        "WhoisRecord",
    }:
        module = import_module(".models", __name__)
        return getattr(module, name)
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")
