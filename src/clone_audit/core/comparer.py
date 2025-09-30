"""Comparison logic for extracted artefacts."""
from __future__ import annotations

import difflib
import logging
from collections import defaultdict
from time import perf_counter
from typing import Iterable, Optional

from ..config import ComparisonConfig
from .models import (
    ComparisonResult,
    ImageArtifact,
    ImageMatch,
    SimilarityBreakdown,
    SiteArtifacts,
    StructureMatch,
    TextArtifact,
    TextMatch,
)
from .scoring import ScoreAggregator
from ..utils import canonical_path, hamming_distance, tokenize_text

_HASH_BITS = 64

logger = logging.getLogger(__name__)


class Comparer:
    """Computes similarity scores between two sites."""

    def __init__(self, config: ComparisonConfig) -> None:
        self.config = config
        self._scorer = ScoreAggregator(config)

    def compare(self, base: SiteArtifacts, clone: SiteArtifacts) -> ComparisonResult:
        start = perf_counter()
        text_score, text_matches = self._compare_text(base.texts, clone.texts)
        image_score, image_matches = self._compare_images(base.images, clone.images)
        structure_score, structure_matches = self._compare_structure(
            base.structures, clone.structures
        )
        overall = self._scorer.overall(text_score, image_score, structure_score)
        breakdown = SimilarityBreakdown(
            text_score=text_score,
            image_score=image_score,
            structure_score=structure_score,
            overall_score=overall,
        )
        duration = perf_counter() - start
        logger.info(
            "Compared artefacts in %.2fs (text=%s, images=%s, structure=%s)",
            duration,
            len(base.texts),
            len(base.images),
            len(base.structures),
        )
        return ComparisonResult(
            base=base,
            clone=clone,
            text_matches=text_matches,
            image_matches=image_matches,
            structure_matches=structure_matches,
            breakdown=breakdown,
        )

    def _compare_text(
        self, base_texts: Iterable[TextArtifact], clone_texts: Iterable[TextArtifact]
    ) -> tuple[float, list[TextMatch]]:
        prepared_base = self._prepare_text_entries(base_texts)
        prepared_clone = self._prepare_text_entries(clone_texts)
        if not prepared_base or not prepared_clone:
            return 0.0, []

        clone_exact: dict[str, list[tuple[TextArtifact, tuple[str, ...], set[str]]]] = defaultdict(list)
        clone_by_len: dict[int, list[tuple[TextArtifact, tuple[str, ...], set[str]]]] = defaultdict(list)
        for clone_artifact, clone_tokens, clone_set in prepared_clone:
            clone_exact[clone_artifact.text].append((clone_artifact, clone_tokens, clone_set))
            clone_by_len[len(clone_tokens)].append((clone_artifact, clone_tokens, clone_set))

        matches: list[TextMatch] = []
        seen_pairs: set[tuple[str, str]] = set()
        total = 0.0

        for base_artifact, base_tokens, base_set in prepared_base:
            best_clone: Optional[TextArtifact] = None
            best_score = 0.0

            exact_candidates = clone_exact.get(base_artifact.text)
            if exact_candidates:
                best_clone = exact_candidates[0][0]
                best_score = 1.0
            else:
                length = len(base_tokens)
                length_window = max(3, int(length * 0.25))
                min_len = max(1, length - length_window)
                max_len = length + length_window
                for candidate_len in range(min_len, max_len + 1):
                    candidates = clone_by_len.get(candidate_len)
                    if not candidates:
                        continue
                    for clone_artifact, clone_tokens, clone_set in candidates:
                        shared = len(base_set & clone_set)
                        if not shared:
                            continue
                        overlap = shared / max(len(base_set), len(clone_set))
                        if overlap < 0.3:
                            continue
                        matcher = difflib.SequenceMatcher(None, base_artifact.text, clone_artifact.text)
                        if matcher.quick_ratio() < self.config.text_threshold * 0.8:
                            continue
                        score = matcher.ratio()
                        if score > best_score:
                            best_score = score
                            best_clone = clone_artifact
                    if best_score >= 0.999:
                        break
            total += best_score
            if best_clone and best_score >= self.config.text_threshold:
                pair_key = (
                    base_artifact.snippet(160),
                    best_clone.snippet(160),
                )
                if pair_key in seen_pairs:
                    continue
                seen_pairs.add(pair_key)
                matches.append(
                    TextMatch(
                        base=base_artifact,
                        clone=best_clone,
                        similarity=best_score,
                        high_confidence=best_score >= self.config.high_confidence_threshold,
                    )
                )
        matches.sort(
            key=lambda match: (
                match.similarity,
                min(match.base.token_count, match.clone.token_count),
            ),
            reverse=True,
        )
        curated: list[TextMatch] = []
        overflow: list[TextMatch] = []
        seen_pages: set[str] = set()
        for match in matches:
            if match.base.page_url not in seen_pages:
                curated.append(match)
                seen_pages.add(match.base.page_url)
            else:
                overflow.append(match)
        curated.extend(overflow)
        limited_matches = curated[: self.config.top_match_limit]
        average = total / len(prepared_base)
        return average, limited_matches

    def _prepare_text_entries(
        self, entries: Iterable[TextArtifact]
    ) -> list[tuple[TextArtifact, tuple[str, ...], set[str]]]:
        prepared: list[tuple[TextArtifact, tuple[str, ...], set[str]]] = []
        for entry in entries:
            tokens = entry.tokens if entry.tokens else tuple(tokenize_text(entry.text))
            if not tokens:
                continue
            token_set = set(tokens)
            prepared.append((entry, tokens, token_set))
        return prepared

    def _compare_images(
        self, base_images: Iterable[ImageArtifact], clone_images: Iterable[ImageArtifact]
    ) -> tuple[float, list[ImageMatch]]:
        base_list = [img for img in base_images if img.hash_bits]
        clone_list = [img for img in clone_images if img.hash_bits]
        if not base_list or not clone_list:
            return 0.0, []
        matches: list[ImageMatch] = []
        seen_pairs: set[tuple[str, str]] = set()
        total = 0.0
        for base_image in base_list:
            best: Optional[ImageArtifact] = None
            best_distance = _HASH_BITS
            for clone_image in clone_list:
                try:
                    distance = hamming_distance(base_image.hash_bits, clone_image.hash_bits)
                except ValueError:
                    continue
                if (
                    distance < best_distance
                    or (
                        distance == best_distance
                        and (clone_image.bytes_size or 0) > (best.bytes_size or 0 if best else -1)
                    )
                ):
                    best_distance = distance
                    best = clone_image
            if best is None:
                continue
            similarity = 1.0 - (best_distance / _HASH_BITS)
            total += similarity
            if best_distance <= self.config.image_hash_threshold:
                base_key = base_image.hash_bits or base_image.url
                clone_key = best.hash_bits or best.url
                pair_key = (base_key, clone_key)
                if pair_key in seen_pairs:
                    continue
                seen_pairs.add(pair_key)
                matches.append(
                    ImageMatch(
                        base=base_image,
                        clone=best,
                        hamming_distance=best_distance,
                        similarity=similarity,
                    )
                )
        def _image_match_weight(match: ImageMatch) -> tuple[float, int]:
            return (
                match.similarity,
                max(match.base.bytes_size or 0, match.clone.bytes_size or 0),
            )

        matches.sort(key=_image_match_weight, reverse=True)
        limited_matches = matches[: self.config.top_match_limit]
        average = total / len(base_list)
        return average, limited_matches

    def _compare_structure(
        self,
        base_structures,
        clone_structures,
    ) -> tuple[float, list[StructureMatch]]:
        base_map = {canonical_path(sig.page_url): sig for sig in base_structures}
        clone_map = {canonical_path(sig.page_url): sig for sig in clone_structures}
        matches: list[StructureMatch] = []
        scores: list[float] = []
        for path, base_sig in base_map.items():
            clone_sig = clone_map.get(path)
            if not clone_sig:
                continue
            similarity = self._jaccard_similarity(base_sig.tag_sequence, clone_sig.tag_sequence)
            scores.append(similarity)
            if similarity >= self.config.structure_threshold:
                matches.append(
                    StructureMatch(
                        base=base_sig,
                        clone=clone_sig,
                        similarity=similarity,
                    )
                )
        matches.sort(key=lambda match: match.similarity, reverse=True)
        limited_matches = matches[: self.config.top_match_limit]
        average = sum(scores) / len(scores) if scores else 0.0
        return average, limited_matches

    @staticmethod
    def _jaccard_similarity(seq_a, seq_b) -> float:
        set_a = set(seq_a)
        set_b = set(seq_b)
        if not set_a or not set_b:
            return 0.0
        intersection = len(set_a & set_b)
        union = len(set_a | set_b)
        return intersection / union if union else 0.0


__all__ = ["Comparer"]
