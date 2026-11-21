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

from collections.abc import Mapping

from app.models.common import HIGH_QUALITY_THRESHOLD, SCORED_SIGNALS
from app.models.lead import LeadSignal, ScoreComponent
from app.models.search import Requirement


class ScoringService:
    def score(
        self,
        signals: list[LeadSignal],
        requirements: list[Requirement] | Mapping[str, int],
    ) -> tuple[int, list[ScoreComponent]]:
        """
        Points per requirement, summed: `round(weight × confidence)` for each one
        the candidate visibly meets.

        Takes the search's requirements. A bare `{signal: points}` mapping — how a
        search was scored before requirements existed — is read as the built-in
        signals with those points, so the arithmetic for recorded searches and
        their tests is exactly what it was.
        """
        # The legacy mapping lists every built-in signal, a zero-point one included;
        # a search's own requirements list only what carries points.
        legacy = isinstance(requirements, Mapping)
        if isinstance(requirements, Mapping):
            requirements = [
                Requirement(id=str(signal), weight=requirements.get(signal, 0))
                for signal in SCORED_SIGNALS
            ]
        by_type = {str(signal.type): signal for signal in signals}
        breakdown = [
            ScoreComponent(
                type=requirement.id,
                label=requirement.label or None,
                awarded=self._points(by_type.get(requirement.id), requirement.weight),
                max=requirement.weight,
            )
            for requirement in requirements
            if legacy or requirement.weight > 0
        ]
        return sum(component.awarded for component in breakdown), breakdown

    @staticmethod
    def _points(signal: LeadSignal | None, weight: int) -> int:
        if signal is None or not signal.detected:
            return 0
        return round(weight * signal.confidence)

    @staticmethod
    def total_weight(requirements: list[Requirement] | Mapping[str, int]) -> int:
        """The effective maximum — 100 unless the points were redistributed."""
        if isinstance(requirements, Mapping):
            return sum(requirements.get(signal, 0) for signal in SCORED_SIGNALS)
        return sum(requirement.weight for requirement in requirements)

    @staticmethod
    def is_high_quality(score: int) -> bool:
        return score >= HIGH_QUALITY_THRESHOLD
