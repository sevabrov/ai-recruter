"""
Scoring (spec §37–38).

The rule this file exists to enforce: **the model detects signals, the backend
computes the score.** No LLM ever returns a number that reaches the user — it
returns `detected` plus a confidence, and the arithmetic happens here, where it
is deterministic, testable and explainable.

    points(signal) = round(weight(signal) × confidence)

The same function runs in Phase 1's frontend mock (`lib/scoring.ts`); keeping the
two in step is what lets the UI switch data sources without changing a pixel.
"""

from app.models.common import HIGH_QUALITY_THRESHOLD, SCORED_SIGNALS, SignalType
from app.models.lead import LeadSignal, ScoreComponent


class ScoringService:
    def score(
        self,
        signals: list[LeadSignal],
        weights: dict[SignalType, int],
    ) -> tuple[int, list[ScoreComponent]]:
        by_type = {signal.type: signal for signal in signals}
        breakdown = [
            ScoreComponent(
                type=signal_type,
                awarded=self._points(by_type.get(signal_type), weights.get(signal_type, 0)),
                max=weights.get(signal_type, 0),
            )
            for signal_type in SCORED_SIGNALS
        ]
        return sum(component.awarded for component in breakdown), breakdown

    @staticmethod
    def _points(signal: LeadSignal | None, weight: int) -> int:
        if signal is None or not signal.detected:
            return 0
        return round(weight * signal.confidence)

    @staticmethod
    def total_weight(weights: dict[SignalType, int]) -> int:
        """The effective maximum — 100 unless the user redistributed the points."""
        return sum(weights.get(signal_type, 0) for signal_type in SCORED_SIGNALS)

    @staticmethod
    def is_high_quality(score: int) -> bool:
        return score >= HIGH_QUALITY_THRESHOLD
