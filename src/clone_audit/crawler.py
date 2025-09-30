"""Backward-compatible alias to `clone_audit.core.crawler`."""
from __future__ import annotations

import sys
from importlib import import_module
from types import ModuleType
from typing import Any

_core_crawler = import_module("clone_audit.core.crawler")


class _CrawlerProxy(ModuleType):
    """Module proxy that forwards attribute access to the core crawler module."""

    def __getattr__(self, name: str) -> Any:
        return getattr(_core_crawler, name)

    def __setattr__(self, name: str, value: Any) -> None:
        setattr(_core_crawler, name, value)

    def __dir__(self) -> list[str]:  # pragma: no cover - introspection helper
        return sorted(set(dir(_core_crawler)))


_proxy = _CrawlerProxy(__name__)
_proxy.__dict__["__file__"] = __file__
_proxy.__dict__["__package__"] = __package__
_proxy.__dict__["__doc__"] = __doc__

sys.modules[__name__] = _proxy
