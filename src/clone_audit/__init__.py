"""Website clone similarity auditing toolkit."""
from __future__ import annotations

from importlib import import_module
from typing import Any

from . import utils
from .config import ComparisonConfig, CrawlConfig, ExtractionConfig, ReportConfig

__all__ = [
    "ComparisonConfig",
    "CrawlConfig",
    "ExtractionConfig",
    "ReportConfig",
    "ReportBuilder",
    "SiteAnalyzer",
    "AnalysisResult",
    "utils",
]


def __getattr__(name: str) -> Any:  # pragma: no cover - import side effect
    if name in {"SiteAnalyzer", "AnalysisResult"}:
        module = import_module(".analyzer", __name__)
        return getattr(module, name)
    if name == "ReportBuilder":
        module = import_module(".report", __name__)
        return getattr(module, name)
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")
