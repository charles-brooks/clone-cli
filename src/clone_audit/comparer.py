"""Compatibility shim exposing comparison utilities via the legacy module path."""
from __future__ import annotations

from .core.comparer import Comparer

__all__ = ["Comparer"]
