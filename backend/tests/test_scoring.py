"""Scoring is the one place a number is produced, so it is tested directly (spec §37–38)."""

import pytest

from app.models.common import DEFAULT_SIGNAL_WEIGHTS, SignalType
from app.models.lead import LeadSignal
from app.services.scoring.scoring_service import ScoringService


def signal(kind: SignalType, detected: bool = True, confidence: float = 1.0) -> LeadSignal:
    return LeadSignal(type=kind, detected=detected, confidence=confidence)


@pytest.fixture
def scoring() -> ScoringService:
    return ScoringService()


def test_full_confidence_awards_the_full_weight(scoring):
    signals = [signal(kind) for kind in DEFAULT_SIGNAL_WEIGHTS]

    score, breakdown = scoring.score(signals, DEFAULT_SIGNAL_WEIGHTS)

    assert score == 100
    assert all(row.awarded == row.max for row in breakdown)


def test_points_are_weight_times_confidence(scoring):
    """The spec's worked example: 18/20 recruiting, 12/15 leadership."""
    signals = [
        signal(SignalType.MLM),
        signal(SignalType.BEAUTY),
        signal(SignalType.RECRUITING, confidence=0.9),
        signal(SignalType.LEADERSHIP, confidence=0.8),
        signal(SignalType.LOCATION),
        signal(SignalType.PERSONAL_BRAND, confidence=0.8),
    ]

    score, breakdown = scoring.score(signals, DEFAULT_SIGNAL_WEIGHTS)
    awarded = {row.type: row.awarded for row in breakdown}

    assert awarded[SignalType.RECRUITING] == 18
    assert awarded[SignalType.LEADERSHIP] == 12
    assert awarded[SignalType.PERSONAL_BRAND] == 4
    assert score == 94


def test_undetected_signals_award_nothing_however_confident(scoring):
    signals = [signal(SignalType.MLM, detected=False, confidence=0.99)]

    score, breakdown = scoring.score(signals, DEFAULT_SIGNAL_WEIGHTS)

    assert score == 0
    assert next(row for row in breakdown if row.type is SignalType.MLM).awarded == 0


def test_missing_signals_are_reported_with_their_maximum(scoring):
    score, breakdown = scoring.score([], DEFAULT_SIGNAL_WEIGHTS)

    assert score == 0
    assert len(breakdown) == len(DEFAULT_SIGNAL_WEIGHTS)
    assert sum(row.max for row in breakdown) == 100


def test_activity_never_scores_even_if_weighted(scoring):
    """`activity` is a signal, not points — a stray weight must not change the score."""
    weights = {**DEFAULT_SIGNAL_WEIGHTS, SignalType.ACTIVITY: 50}

    score, breakdown = scoring.score([signal(SignalType.ACTIVITY)], weights)

    assert score == 0
    assert SignalType.ACTIVITY not in {row.type for row in breakdown}


def test_user_weights_change_the_ranking(scoring):
    """Redistributing points is the whole reason weights are per-search."""
    signals = [signal(SignalType.MLM), signal(SignalType.LEADERSHIP, confidence=0.5)]
    leadership_heavy = {**DEFAULT_SIGNAL_WEIGHTS, SignalType.MLM: 5, SignalType.LEADERSHIP: 40}

    default_score, _ = scoring.score(signals, DEFAULT_SIGNAL_WEIGHTS)
    reweighted, _ = scoring.score(signals, leadership_heavy)

    assert default_score == 30 + 8
    assert reweighted == 5 + 20


def test_high_quality_threshold(scoring):
    assert scoring.is_high_quality(85)
    assert not scoring.is_high_quality(84)
    assert scoring.total_weight(DEFAULT_SIGNAL_WEIGHTS) == 100
