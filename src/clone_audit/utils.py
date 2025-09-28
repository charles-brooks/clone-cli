"""Utility helpers for crawling and comparison."""
from __future__ import annotations

import re
import time
from collections.abc import Iterable
from typing import Iterable as IterableType, Iterator, Sequence
from urllib.parse import urljoin, urlparse, urlunparse

_WHITESPACE_RE = re.compile(r"\s+")
_BLOCK_TAGS = {
    "p",
    "div",
    "article",
    "section",
    "header",
    "footer",
    "main",
    "li",
    "td",
    "th",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "pre",
    "blockquote",
}



def normalize_url(url: str, remove_fragment: bool = True) -> str:
    """Normalise URL for deduplication."""
    parsed = urlparse(url)
    scheme = parsed.scheme.lower() or "http"
    netloc = parsed.netloc.lower()
    path = parsed.path or "/"
    if remove_fragment:
        fragment = ""
    else:
        fragment = parsed.fragment
    normalized = parsed._replace(
        scheme=scheme,
        netloc=netloc,
        path=path,
        params="",
        query=parsed.query,
        fragment=fragment,
    )
    return urlunparse(normalized)


def canonical_path(url: str) -> str:
    """Return a path-based identifier for page comparison."""
    parsed = urlparse(url)
    path = parsed.path or "/"
    if parsed.query:
        path = f"{path}?{parsed.query}"
    return path


def is_same_domain(url: str, root: str) -> bool:
    root_host = urlparse(root).netloc.lower()
    url_host = urlparse(url).netloc.lower()
    return url_host == root_host


def is_html_content(content_type: str | None) -> bool:
    if not content_type:
        return True
    return content_type.split(";")[0].strip().lower() in {
        "text/html",
        "application/xhtml+xml",
    }


def clean_text(value: str) -> str:
    return _WHITESPACE_RE.sub(" ", value).strip()




def tokenize_text(value: str) -> list[str]:
    return [token.lower() for token in re.findall(r"[\w']+", value)]

def iter_block_candidates(soup) -> Iterator:
    """Yield candidate nodes for text extraction."""
    for tag in soup.find_all(_BLOCK_TAGS):
        yield tag


def sleep(seconds: float) -> None:
    time.sleep(seconds)


def resolve_url(base_url: str, link: str | None) -> str | None:
    if not link:
        return None
    return urljoin(base_url, link)


def hamming_distance(hash_a: str, hash_b: str) -> int:
    """Compute Hamming distance between two hex-encoded hashes."""
    if len(hash_a) != len(hash_b):
        raise ValueError("Hash lengths must match")
    a_int = int(hash_a, 16)
    b_int = int(hash_b, 16)
    xor = a_int ^ b_int
    return xor.bit_count()


def chunked(iterable: IterableType, size: int) -> Iterator[list]:
    chunk: list = []
    for item in iterable:
        chunk.append(item)
        if len(chunk) >= size:
            yield chunk
            chunk = []
    if chunk:
        yield chunk
