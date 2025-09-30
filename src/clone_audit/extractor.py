"""Compatibility shim exposing the extractor via the legacy module path."""
from __future__ import annotations

from .core.extractor import Extractor

__all__ = ["Extractor"]
