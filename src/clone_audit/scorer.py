"""Scoring helpers for similarity aggregation."""
from __future__ import annotations

from .config import ComparisonConfig


class ScoreAggregator:
    def __init__(self, config: ComparisonConfig) -> None:
        self.config = config

    def overall(self, text_score: float, image_score: float, structure_score: float) -> float:
        weight_text, weight_images, weight_structure = self.config.normalised_weights()
        return (
            (text_score * weight_text)
            + (image_score * weight_images)
            + (structure_score * weight_structure)
        )


__all__ = ["ScoreAggregator"]
