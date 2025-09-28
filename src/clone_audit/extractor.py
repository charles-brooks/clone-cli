"""HTML artefact extraction helpers."""
from __future__ import annotations

import io
import logging
from time import perf_counter
from typing import Dict, Iterable, Optional

import numpy as np
import requests
from PIL import Image, UnidentifiedImageError
from bs4 import BeautifulSoup, Tag

from .config import ExtractionConfig
from .models import CrawlResult, ImageArtifact, SiteArtifacts, StructureSignature, TextArtifact
from .utils import (
    clean_text,
    iter_block_candidates,
    normalize_url,
    resolve_url,
    tokenize_text,
)

_HASH_SIZE = 8
_MAX_STRUCTURE_TAGS = 600

logger = logging.getLogger(__name__)


class Extractor:
    """Extracts text, image, and structural signals from crawled pages."""

    def __init__(self, config: ExtractionConfig, session: Optional[requests.Session] = None) -> None:
        self.config = config
        self.session = session or requests.Session()
        self._image_cache: Dict[str, tuple[Optional[str], Optional[int], Optional[str], Optional[bytes]]] = {}

    def extract(self, crawl_result: CrawlResult) -> SiteArtifacts:
        start = perf_counter()
        artifacts = SiteArtifacts(crawl=crawl_result)
        for snapshot in crawl_result.snapshots:
            if not snapshot.html:
                continue
            soup = BeautifulSoup(snapshot.html, "html.parser")

            if self.config.collect_text:
                artifacts.texts.extend(self._extract_text(snapshot.url, soup))

            if self.config.collect_images:
                artifacts.images.extend(self._extract_images(snapshot.url, soup))

            if self.config.collect_structure:
                signature = self._extract_structure(snapshot.url, snapshot.depth, soup)
                if signature:
                    artifacts.structures.append(signature)
        duration = perf_counter() - start
        logger.info(
            "Extracted artefacts from %s pages in %.2fs (text=%s, images=%s, structure=%s)",
            len(crawl_result.snapshots),
            duration,
            len(artifacts.texts),
            len(artifacts.images),
            len(artifacts.structures),
        )
        return artifacts

    def _extract_text(self, page_url: str, soup: BeautifulSoup) -> Iterable[TextArtifact]:
        entries: list[TextArtifact] = []
        for tag in iter_block_candidates(soup):
            if not isinstance(tag, Tag):
                continue
            text = clean_text(tag.get_text(separator=" "))
            if len(text) < self.config.min_text_length:
                continue
            if len(text) > self.config.max_text_length:
                text = text[: self.config.max_text_length]
            locator = self._dom_path(tag)
            tokens = tokenize_text(text)
            if not tokens:
                continue
            entries.append(
                TextArtifact(
                    page_url=page_url,
                    locator=locator,
                    text=text,
                    token_count=len(tokens),
                    tokens=tuple(tokens),
                )
            )
        return entries

    def _extract_images(self, page_url: str, soup: BeautifulSoup) -> Iterable[ImageArtifact]:
        images: list[ImageArtifact] = []
        for img in soup.find_all("img"):
            if not isinstance(img, Tag):
                continue
            src = img.get("src")
            full_url = resolve_url(page_url, src)
            if not full_url or full_url.startswith("data:"):
                continue
            normalized = normalize_url(full_url)
            hash_bits, size_bytes, content_type, preview_bytes = self._fetch_image_metadata(normalized)
            images.append(
                ImageArtifact(
                    page_url=page_url,
                    url=normalized,
                    hash_bits=hash_bits,
                    bytes_size=size_bytes,
                    content_type=content_type,
                    preview_bytes=preview_bytes,
                )
            )
        return images

    def _extract_structure(self, page_url: str, depth: int, soup: BeautifulSoup) -> Optional[StructureSignature]:
        tags: list[str] = []
        for element in soup.find_all(True, limit=_MAX_STRUCTURE_TAGS):
            if isinstance(element, Tag):
                tags.append(element.name)
        if not tags:
            return None
        return StructureSignature(page_url=page_url, depth=depth, tag_sequence=tuple(tags))

    def _fetch_image_metadata(
        self, url: str
    ) -> tuple[Optional[str], Optional[int], Optional[str], Optional[bytes]]:
        if url in self._image_cache:
            return self._image_cache[url]
        try:
            response = self.session.get(url, timeout=10)
            response.raise_for_status()
            content_type = response.headers.get("Content-Type")
            content = response.content
            size_bytes = len(content)
            hash_bits = None
            preview_bytes = None
            if content_type and "image" in content_type and content:
                hash_bits = self._average_hash(content)
                preview_bytes = self._create_preview(content)
        except (requests.RequestException, UnidentifiedImageError, OSError):  # pragma: no cover - network edge
            self._image_cache[url] = (None, None, None, None)
            return (None, None, None, None)
        result = (hash_bits, size_bytes, content_type, preview_bytes)
        self._image_cache[url] = result
        return result

    def _average_hash(self, content: bytes) -> Optional[str]:
        with Image.open(io.BytesIO(content)) as img:
            image = img.convert("L").resize((_HASH_SIZE, _HASH_SIZE), Image.LANCZOS)
        pixels = np.asarray(image, dtype=float)
        avg = pixels.mean()
        bits = pixels > avg
        bit_string = "".join("1" if bit else "0" for bit in bits.flatten())
        value = int(bit_string, 2)
        return f"{value:0{_HASH_SIZE * _HASH_SIZE // 4}x}"

    def _create_preview(self, content: bytes) -> Optional[bytes]:
        with Image.open(io.BytesIO(content)) as img:
            preview = img.convert("RGB")
            preview.thumbnail((320, 320))
            buffer = io.BytesIO()
            preview.save(buffer, format="PNG")
            return buffer.getvalue()

    def _dom_path(self, tag: Tag) -> str:
        parts: list[str] = []
        current: Optional[Tag] = tag
        while current and isinstance(current, Tag):
            index = self._sibling_index(current)
            part = current.name
            if index > 1:
                part = f"{part}[{index}]"
            parts.append(part)
            current = current.parent  # type: ignore[assignment]
        return "/".join(reversed(parts))

    @staticmethod
    def _sibling_index(tag: Tag) -> int:
        count = 1
        sibling = tag.previous_sibling
        while sibling:
            if isinstance(sibling, Tag) and sibling.name == tag.name:
                count += 1
            sibling = sibling.previous_sibling
        return count


__all__ = ["Extractor"]
