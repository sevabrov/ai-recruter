"""
Signal detection (spec §36).

The question is never "is this a good candidate?" — that would hand judgement,
and the score, to a model. Each signal is asked about separately and answered
with `detected` + `confidence` + the quote that justifies it. Turning those into
a number is the scoring service's job, not this one's.

Geographic match is the one signal that cannot be read off a page in isolation:
it only means something relative to the criteria, so it is re-derived per search.
"""

from typing import Protocol

from app.core.errors import ProviderError
from app.models.common import SignalType
from app.models.lead import LeadSignal
from app.models.profile import ExtractedProfile
from app.models.search import SearchCriteria


class SignalDetector(Protocol):
    name: str

    async def detect(
        self, profile: ExtractedProfile, criteria: SearchCriteria
    ) -> list[LeadSignal]: ...


class FixtureSignalDetector(SignalDetector):
    """
    Phase 2 detector: trusts the observations the extractor returned and only
    re-judges what is criteria-relative. Phase 6 replaces it with the LLM
    detector — the pipeline call site is identical.
    """

    name = "fixture"

    async def detect(self, profile: ExtractedProfile, criteria: SearchCriteria) -> list[LeadSignal]:
        target = (criteria.location.country or "").strip().lower()
        profile_country = (profile.location.country or "").strip().lower()

        signals: list[LeadSignal] = []
        for observation in profile.observations:
            if observation.type is not SignalType.LOCATION or not target:
                signals.append(observation.model_copy())
                continue

            if profile_country == target:
                signals.append(observation.model_copy())
            else:
                signals.append(
                    observation.model_copy(
                        update={
                            "detected": False,
                            "confidence": 0.15,
                            "evidence": (
                                f"Profile location {profile.location.country or 'unknown'} "
                                f"does not match target {criteria.location.country}."
                            ),
                        }
                    )
                )
        return signals


class LlmSignalDetector(SignalDetector):
    """
    Phase 6. One structured call per profile that returns, for every signal in
    `criteria.must_have + criteria.nice_to_have`: detected, confidence 0–1, the
    verbatim evidence and which source URL it came from (spec §16, §36).

    Rules for that phase: the model never sees or returns a score; it may answer
    "not found"; calls are bounded by LLM_CONCURRENCY and counted into
    `SearchUsage.llm_calls` (§52, §54).
    """

    name = "llm"

    def __init__(self, api_key: str, model: str = "gpt-4o-mini") -> None:
        self.api_key = api_key
        self.model = model

    async def detect(self, profile: ExtractedProfile, criteria: SearchCriteria) -> list[LeadSignal]:
        raise ProviderError(
            "LLM signal detection is wired up in Phase 6. Set OPENAI_API_KEY and "
            "implement LlmSignalDetector.detect.",
            provider=self.name,
        )
