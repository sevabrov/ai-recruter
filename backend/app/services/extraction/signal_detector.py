"""
Signal detection (spec §36).

The question is never "is this a good candidate?" — that would hand judgement,
and the score, to a model. Each signal is asked about separately and answered
with `detected` + `confidence` + the quote that justifies it. Turning those into
a number is the scoring service's job, not this one's.

Geographic match is the one signal that cannot be read off a page in isolation:
it only means something relative to the criteria, so it is re-derived per search.
"""

import re
from typing import Protocol

from app.core.errors import ProviderError
from app.models.common import SignalType
from app.models.lead import LeadSignal
from app.models.profile import ExtractedProfile
from app.models.search import SearchCriteria
from app.services.extraction.vocabulary import quote


class SignalDetector(Protocol):
    name: str
    #: Whether judging one profile costs money. The cost model reads this instead of
    #: assuming that every detector is an LLM: pricing the keyword stand-in put a
    #: quarter of a euro on a search that spent nothing.
    paid: bool

    async def detect(
        self, profile: ExtractedProfile, criteria: SearchCriteria
    ) -> list[LeadSignal]: ...


class FixtureSignalDetector(SignalDetector):
    """
    Phase 2 detector: trusts the observations the extractor returned and only
    re-judges what is criteria-relative. Phase 6 replaces it with the LLM
    detector — the pipeline call site is identical.

    Two things are criteria-relative, not two ways of saying one thing:

    * **geography**, which only means anything against the country that was asked
      for, and is therefore re-derived per search;
    * **the client's own words.** The vocabulary in `extraction/vocabulary.py` is a
      general one — "network marketing", "distribuidora", "сетевой маркетинг" — and
      it does not contain `Jerelia`, `Farmasi` or `MIHI`. So a search for Jerelia
      distributors found them and then refused them for missing the MLM signal,
      because their profiles say "Jerelia" and nothing the word list knows. A brand
      the client is hunting *is* the signal, and it is quoted like any other.
    """

    name = "fixture"
    paid = False

    async def detect(self, profile: ExtractedProfile, criteria: SearchCriteria) -> list[LeadSignal]:
        target = (criteria.location.country or "").strip().lower()
        profile_country = (profile.location.country or "").strip().lower()

        signals: list[LeadSignal] = []
        for observation in _with_client_terms(profile, criteria):
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


#: The shortest a client's term may be before it is worth searching for. Two-letter
#: terms match inside other words often enough to be worse than nothing.
MIN_TERM = 3

#: What a term found in the profile's own text is worth. Below a page's own claim
#: (0.9) and at a search snippet's ceiling: it is one word, quoted, nothing more.
CLIENT_TERM_CONFIDENCE = 0.55


def _with_client_terms(profile: ExtractedProfile, criteria: SearchCriteria) -> list[LeadSignal]:
    """
    The observations, plus any signal the client's own search terms support.

    Only fills gaps: an observation the extractor already detected is never
    overwritten, because the page's own words outrank a keyword match. Every
    addition carries the sentence it was found in, like any other signal — a
    detection without a quote is not a detection (spec §16, §36).
    """
    wanted = {
        SignalType.MLM: [*criteria.keywords, *criteria.business_types],
        SignalType.BEAUTY: list(criteria.industry),
    }
    detected = {observation.type for observation in profile.observations if observation.detected}
    text = " ".join(
        part for part in (profile.name, profile.headline, profile.company, profile.summary) if part
    )
    if not text.strip():
        return list(profile.observations)

    found: dict[SignalType, str] = {}
    for signal, terms in wanted.items():
        if signal in detected:
            continue
        for term in terms:
            cleaned = term.strip()
            if len(cleaned) < MIN_TERM:
                continue
            if re.search(rf"(?<!\w){re.escape(cleaned)}(?!\w)", text, re.IGNORECASE):
                found[signal] = quote(text, cleaned)
                break

    if not found:
        return list(profile.observations)

    upgraded = [
        observation.model_copy(
            update={
                "detected": True,
                "confidence": CLIENT_TERM_CONFIDENCE,
                "evidence": found[observation.type],
            }
        )
        if observation.type in found
        else observation.model_copy()
        for observation in profile.observations
    ]
    # An extractor is not obliged to report every signal; a term found for one it
    # never mentioned still has to arrive as a sighting of its own.
    seen = {observation.type for observation in profile.observations}
    source = profile.sources[0] if profile.sources else None
    upgraded.extend(
        LeadSignal(
            type=signal,
            detected=True,
            confidence=CLIENT_TERM_CONFIDENCE,
            evidence=evidence,
            source_url=source.url if source else profile.url,
            source_platform=profile.platform,
        )
        for signal, evidence in found.items()
        if signal not in seen
    )
    return upgraded


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
    paid = True

    def __init__(self, api_key: str, model: str = "gpt-4o-mini") -> None:
        self.api_key = api_key
        self.model = model

    async def detect(self, profile: ExtractedProfile, criteria: SearchCriteria) -> list[LeadSignal]:
        raise ProviderError(
            "LLM signal detection is wired up in Phase 6. Set OPENAI_API_KEY and "
            "implement LlmSignalDetector.detect.",
            provider=self.name,
        )
