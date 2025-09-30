"""Adapter protocol definitions for injectable dependencies."""
from __future__ import annotations

from typing import Protocol, runtime_checkable

from ..core import HostingRecord, WhoisRecord


@runtime_checkable
class WhoisProvider(Protocol):
    """Minimal interface for performing WHOIS lookups."""

    def lookup(self, target: str) -> WhoisRecord:
        ...


@runtime_checkable
class HostingProvider(Protocol):
    """Minimal interface for resolving hosting/network metadata."""

    def lookup(self, target: str) -> HostingRecord:
        ...


__all__ = ["WhoisProvider", "HostingProvider"]
