"""
Judging a candidate against a search's requirements (spec §36).

The question is never "is this a good candidate?" — that would hand judgement,
and the score, to a model. Each requirement is asked about separately and answered
with `detected` + `confidence` + the quote that justifies it. Turning those into
a number is the scoring service's job, not this one's.

Requirements are written per search: the product recruits for any role, so "Python",
"Django" and "middle or senior" are as much a requirement as the built-in
network-marketing signals. Two judges answer them:

* `FixtureSignalDetector` — no model. Built-in signals come from what the page
  reader observed; a search's own requirements are matched by their words.
* `LlmSignalDetector` — one structured call per candidate. Every "met" must come
  with a quote that is checked, character for character, against the profile text;
  a quote that is not there is a requirement not met. When the model fails, the
  candidate is judged by the words instead — a search never fails for want of one.

Geographic match is the one requirement that cannot be read off a page in
isolation: it only means something relative to the criteria, so it is derived
here from the profile's country, by code, for both judges.
"""

import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol

import httpx

from app.core.errors import ProviderAuthError, ProviderError, ProviderUnavailableError
from app.core.logging import get_logger
from app.models.common import SignalType
from app.models.lead import LeadSignal
from app.models.profile import ExtractedProfile
from app.models.search import Requirement, SearchCriteria
from app.models.source import LeadSourceKind
from app.services.extraction.vocabulary import DATED_ACTIVITY_CONFIDENCE, find_place, quote

log = get_logger(__name__)


@dataclass
class Judgement:
    """A candidate judged: one sighting per requirement, and whether it is a person."""

    signals: list[LeadSignal]
    #: False when the judge read a company, shop, school or community page rather
    #: than one person's own; None when nobody could tell (the keyword judge).
    is_person: bool | None = None
    reason: str = ""
    #: What the page is instead of a person, as one of `NOT_PERSON_KINDS` — the
    #: reason in a form the interface can put in the client's language.
    not_person_kind: str = ""
    #: Where the judge read that the person is, when the text says so in a form
    #: code cannot read ("Мордовия", "Мартук", a flag) — with the quote that says it.
    country: str | None = None
    country_evidence: str = ""


class SignalDetector(Protocol):
    name: str
    #: Whether judging one profile costs money. The cost model reads this instead of
    #: assuming that every detector is an LLM: pricing the keyword stand-in put a
    #: quarter of a euro on a search that spent nothing.
    paid: bool

    async def detect(
        self, profile: ExtractedProfile, criteria: SearchCriteria
    ) -> list[LeadSignal]: ...


#: The shortest a client's term may be before it is worth searching for. Two-letter
#: terms match inside other words often enough to be worse than nothing.
MIN_TERM = 3

#: What a term found in the profile's own text is worth. Below a page's own claim
#: (0.9) and at a search snippet's ceiling: it is one word, quoted, nothing more.
CLIENT_TERM_CONFIDENCE = 0.55

#: A model read the text and quoted it; still not a certainty (as for the page reader).
MAX_JUDGED_CONFIDENCE = 0.9

#: How a confirmed country is worth, when the profile itself places the person.
LOCATION_CONFIDENCE = 0.75


# ----------------------------------------------------------------- without a model


class FixtureSignalDetector(SignalDetector):
    """
    Judges without a model: the page reader's observations for the built-in
    signals, the requirement's own words for everything else, the country by code.

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
        return keyword_signals(profile, criteria)

    async def assess(self, profile: ExtractedProfile, criteria: SearchCriteria) -> Judgement:
        return Judgement(keyword_signals(profile, criteria))


async def assess(
    detector: SignalDetector, profile: ExtractedProfile, criteria: SearchCriteria
) -> Judgement:
    """A detector's full judgement, for detectors that only answer `detect` too."""
    if hasattr(detector, "assess"):
        return await detector.assess(profile, criteria)
    return Judgement(await detector.detect(profile, criteria))


async def assess_many(
    detector: SignalDetector, profiles: list[ExtractedProfile], criteria: SearchCriteria
) -> list[Judgement]:
    """Judgements for a batch, from detectors that judge one at a time too."""
    if hasattr(detector, "assess_many"):
        return await detector.assess_many(profiles, criteria)
    return [await assess(detector, profile, criteria) for profile in profiles]


def placed_by_judge(
    profile: ExtractedProfile, criteria: SearchCriteria, judgement: Judgement
) -> tuple[ExtractedProfile, list[LeadSignal]]:
    """
    The profile with the country the judge read, when code could not read one.

    A bio says "Пермь", "Мордовия" or "из Алматы" far more often than it names a
    country, and no word list knows every town: twelve SMM "leads" for a Kyiv
    search came from Latvia, Turkey and Russia with their country unknown. The
    judge knows the towns; its quote is checked like every other one. The
    location requirement is then re-judged by code against the places asked for.
    """
    if not judgement.country or (profile.location.country or "").strip():
        return profile, judgement.signals
    found = find_place(judgement.country)
    country = found[0] if found else judgement.country
    located = profile.model_copy(
        update={"location": profile.location.model_copy(update={"country": country})}
    )
    fresh = {
        str(signal.type): signal
        for signal in keyword_signals(located, criteria)
        if signal.type == SignalType.LOCATION
    }
    signals = [
        fresh.get(str(signal.type), signal) if signal.type == SignalType.LOCATION else signal
        for signal in judgement.signals
    ]
    return located, signals


def keyword_signals(profile: ExtractedProfile, criteria: SearchCriteria) -> list[LeadSignal]:
    """
    One sighting per requirement, judged by words and by code.

    A search recorded before requirements existed gets exactly what it got then:
    every observation, the location one re-derived against the target country.
    """
    observed = _located(_with_client_terms(profile, criteria), profile, criteria)
    if criteria.requirements is None:
        return observed

    by_type = {str(signal.type): signal for signal in observed}
    text = profile_text(profile)
    signals: list[LeadSignal] = []
    for requirement in criteria.requirements:
        if requirement.id == SignalType.LOCATION:
            signals.append(_labelled(_location(profile, criteria, by_type), requirement))
        elif requirement.is_preset:
            sighting = by_type.get(requirement.id) or _not_seen(requirement.id, profile)
            signals.append(_labelled(sighting, requirement))
        else:
            signals.append(_by_terms(requirement, text, profile))
    return signals


def _located(
    observations: list[LeadSignal], profile: ExtractedProfile, criteria: SearchCriteria
) -> list[LeadSignal]:
    """The observations, with the location one judged against the places asked for."""
    asked = bool(criteria.allowed_countries())
    inside = criteria.in_allowed_place(profile.location.country)

    signals: list[LeadSignal] = []
    for observation in observations:
        if observation.type != SignalType.LOCATION or not asked or inside:
            signals.append(observation.model_copy())
            continue
        signals.append(
            observation.model_copy(
                update={
                    "detected": False,
                    "confidence": 0.15,
                    "evidence": (
                        f"Profile location {profile.location.country or 'unknown'} "
                        f"does not match target {criteria.place_label()}."
                    ),
                }
            )
        )
    return signals


def _location(
    profile: ExtractedProfile, criteria: SearchCriteria, by_type: dict[str, LeadSignal]
) -> LeadSignal:
    """
    In the place the search asks for — said by the profile, not guessed.

    A matching country is a sighting even when the extractor reported no
    location observation of its own: the profile's country is the evidence.
    """
    seen = by_type.get(SignalType.LOCATION)
    found = (profile.location.country or "").strip()
    if criteria.in_allowed_place(found) is False:
        return _not_seen(SignalType.LOCATION, profile)
    if criteria.in_allowed_place(found):
        if seen and seen.detected:
            return seen
        where = ", ".join(part for part in (profile.location.city, found) if part)
        return _sighting(
            SignalType.LOCATION,
            profile,
            LOCATION_CONFIDENCE,
            f"The profile places them in {where}.",
        )
    return seen or _not_seen(SignalType.LOCATION, profile)


def _by_terms(requirement: Requirement, text: str, profile: ExtractedProfile) -> LeadSignal:
    """A requirement of the search's own, met when one of its words is on the profile."""
    terms = requirement.terms or [requirement.label]
    for term in terms:
        cleaned = " ".join(term.split())
        if len(cleaned) < MIN_TERM:
            continue
        if re.search(rf"(?<!\w){re.escape(cleaned)}(?!\w)", text, re.IGNORECASE):
            return _labelled(
                _sighting(requirement.id, profile, CLIENT_TERM_CONFIDENCE, quote(text, cleaned)),
                requirement,
            )
    return _labelled(_not_seen(requirement.id, profile), requirement)


def _with_client_terms(profile: ExtractedProfile, criteria: SearchCriteria) -> list[LeadSignal]:
    """
    The observations, plus any built-in signal the client's own search terms support.

    Only fills gaps: an observation the extractor already detected is never
    overwritten, because the page's own words outrank a keyword match. Every
    addition carries the sentence it was found in, like any other signal — a
    detection without a quote is not a detection (spec §16, §36).
    """
    wanted = {
        # A distributor names the brand they sell; that is the MLM signal, in
        # whatever language the rest of the profile is written.
        SignalType.MLM: [*criteria.brands, *criteria.keywords, *criteria.business_types],
        SignalType.BEAUTY: list(criteria.industry),
    }
    detected = {
        str(observation.type) for observation in profile.observations if observation.detected
    }
    text = " ".join(
        part for part in (profile.name, profile.headline, profile.company, profile.summary) if part
    )
    if not text.strip():
        return list(profile.observations)

    found: dict[str, str] = {}
    for signal, terms in wanted.items():
        if signal in detected:
            continue
        for term in terms:
            cleaned = term.strip()
            if len(cleaned) < MIN_TERM:
                continue
            if re.search(rf"(?<!\w){re.escape(cleaned)}(?!\w)", text, re.IGNORECASE):
                found[signal.value] = quote(text, cleaned)
                break

    if not found:
        return list(profile.observations)

    upgraded = [
        observation.model_copy(
            update={
                "detected": True,
                "confidence": CLIENT_TERM_CONFIDENCE,
                "evidence": found[str(observation.type)],
            }
        )
        if str(observation.type) in found
        else observation.model_copy()
        for observation in profile.observations
    ]
    # An extractor is not obliged to report every signal; a term found for one it
    # never mentioned still has to arrive as a sighting of its own.
    seen = {str(observation.type) for observation in profile.observations}
    upgraded.extend(
        _sighting(signal, profile, CLIENT_TERM_CONFIDENCE, evidence)
        for signal, evidence in found.items()
        if signal not in seen
    )
    return upgraded


def _sighting(kind: str, profile: ExtractedProfile, confidence: float, evidence: str) -> LeadSignal:
    source = profile.sources[0] if profile.sources else None
    return LeadSignal(
        type=str(kind),
        detected=True,
        confidence=confidence,
        evidence=evidence,
        source_url=source.url if source else profile.url,
        source_platform=profile.platform,
    )


def _not_seen(kind: str, profile: ExtractedProfile) -> LeadSignal:
    return LeadSignal(
        type=str(kind), detected=False, confidence=0, source_platform=profile.platform
    )


def _labelled(signal: LeadSignal, requirement: Requirement) -> LeadSignal:
    return signal.model_copy(update={"type": requirement.id, "label": requirement.label or None})


def profile_text(profile: ExtractedProfile, *, snippets: int = 3) -> str:
    """
    Everything known about the candidate, as one text to judge and to quote from.

    Labelled lines, so a quote can be traced to where it came from; the search
    results the person was found through are included because, for a profile that
    would not open, they are all there is.
    """
    lines = [
        ("Address", profile.url),
        ("Name", profile.name),
        ("Headline", profile.headline),
        ("Company", profile.company),
        (
            "Location",
            ", ".join(part for part in (profile.location.city, profile.location.country) if part),
        ),
        ("Languages", ", ".join(profile.languages)),
        ("About", profile.summary),
    ]
    pages = [source for source in profile.sources if source.kind is not LeadSourceKind.POST]
    posts = [source for source in profile.sources if source.kind is LeadSourceKind.POST]
    for source in pages[:snippets]:
        lines.append(("Search result", " — ".join(p for p in (source.title, source.snippet) if p)))
    # The person's own posts get a label of their own: their words are the person
    # speaking, which a search result about a page is not.
    for source in posts[:snippets]:
        published = source.published_at
        when = f" (published {published.date().isoformat()})" if published else ""
        lines.append(
            (f"Their own post{when}", " — ".join(p for p in (source.title, source.snippet) if p))
        )
    return "\n".join(f"{label}: {value}" for label, value in lines if value and value.strip())


# ---------------------------------------------------------------------- the model

#: What each built-in signal means, for a judge that has only the id.
PRESET_DESCRIPTIONS: dict[str, str] = {
    SignalType.MLM: "Is personally an independent consultant, distributor or partner "
    "of a network-marketing (MLM / direct selling) brand — Farmasi, Oriflame, Avon, "
    "Jerelia, Amway, Faberlic and the like — or says they build a team in one. A "
    "person who publishes their own posts promoting network marketing as a business, "
    "explaining why they do it or inviting others into it, shows this too. A "
    "company that distributes or wholesales products is NOT network marketing, and "
    "a news outlet or journalist writing about MLM is not a participant in it.",
    SignalType.BEAUTY: "Works with beauty, cosmetics, skincare or perfume products.",
    SignalType.RECRUITING: "Actively invites people to join their team or business.",
    SignalType.LEADERSHIP: "Leads, mentors or manages a team or other people.",
    SignalType.PERSONAL_BRAND: "Publishes as themselves with an audience: a blog, a "
    "course, their own site, a sizeable following.",
    SignalType.ACTIVITY: "Visibly active recently: a post or update dated within the last 30 days.",
}

#: What a page that is not one person's can be, for `not_person_kind`. Kept short
#: and stable: the interface has a sentence for each, in every language it speaks.
NOT_PERSON_KINDS = (
    "company",
    "shop",
    "brand",
    "media",
    "community",
    "school",
    "job_posting",
    "other",
)


def _kind(value: Any) -> str:
    kind = str(value or "")
    return kind if kind in NOT_PERSON_KINDS else ""


JUDGE_PROMPT = """\
You check one candidate's public profile text against a recruiter's requirements.

For EVERY requirement return:
- met: true only if the profile text itself shows it. Absence of evidence is false.
- confidence: 0 to 1, how clearly the text shows it.
- evidence: when met, a short quote copied EXACTLY, character for character, from \
the profile text (max 200 characters, no paraphrase, no translation, no "…"). \
Quote what the person or page says — never the labels of this text ("Address:", \
"Name:", "Location:", "Languages:", "Search result:", "Their own post:") or the \
address: that the profile is on Instagram shows nothing. When not met, "".
- A "Their own post" line is a post this person published on their own account: \
its words are the person speaking and count as the profile showing them, exactly \
like their bio. Its publication date, when given, is evidence of recent activity.
- A level or seniority is met only by that level: "middle" is not met by "Senior", \
"Lead" or "Head of"; "junior" is not met by "Senior". Years of experience count \
only when the text states them.

Also decide is_person: true only if this is one individual human's own profile; \
false for a company, brand, shop, school, clinic, agency, community, group or any \
organisation's page (give the reason in not_person_reason, in English, else "", and \
the kind of page in not_person_kind: company, shop, brand, media, community, school, \
job_posting or other — "other" when it is a person). An \
account run by one person under a business-like name is still a person when it \
speaks as them or names them ("Робота_МЛМ_Світлана", "Наставник сетевиков", "Anna | \
beauty coach"); judge by who is speaking, not by how the account is titled. A \
person's first or last name in the handle or address (marianna.konovalova, \
svitlana_kostyuchok_mlm) means a person. An independent consultant or leader of a \
network-marketing brand selling from their own account is one person, even when the \
account is titled with the brand and their role and talks about orders, discounts \
and catalogues ("Konsultantka AVON - Świebodzice", "Avon Lider Luboń", "Farmasi \
Beauty Consultant") — taking orders is what such an account is for. It is NOT a \
person only when it is the brand's own official or national account ("Avon Polska", \
"Amway Polska"), a physical shop or salon, or a group of many consultants. Mark false \
only when the page clearly speaks for an organisation ("we", a company name, a shop, \
a school, a law firm). A job \
posting is not a candidate: a page or post where someone is hiring ("шукаємо", \
"шукає SMM-менеджера", "вакансія", "we are hiring") is is_person false.

Also decide country: the country this person lives or works in, as its English name, \
ONLY when the text says where they are — a city, a region, a country, a flag next \
to a place ("Kyiv", "Пермь", "Мордовия", "из Алматы", "🇵🇱 Warszawa"). A language \
alone, a name or a brand is not a place: then "". country_evidence: the exact quote \
that places them, copied character for character; "" when country is "".

You may use general knowledge to interpret what the text says — that a brand is a \
network-marketing company, that "Senior Software Engineer" means a senior level — \
but the quote itself must be in the text. Never judge by the person's name, \
photo, gender or age."""


class LlmSignalDetector(SignalDetector):
    """
    One structured call per candidate (Phase 6). The model never sees or returns a
    score; it may answer "not met"; calls are bounded by LLM_CONCURRENCY and counted
    into `SearchUsage.llm_calls` (§52, §54).

    The location requirement is not asked: it is a comparison of two countries,
    and code does that without being wrong.
    """

    name = "llm"
    paid = True

    def __init__(
        self,
        api_key: str,
        model: str = "gpt-4.1-mini",
        *,
        endpoint: str = "https://api.openai.com/v1/chat/completions",
        timeout_seconds: float = 30.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.api_key = api_key
        self.model = model
        self._endpoint = endpoint
        self._timeout = timeout_seconds
        self._client = client

    async def detect(self, profile: ExtractedProfile, criteria: SearchCriteria) -> list[LeadSignal]:
        return (await self.assess(profile, criteria)).signals

    async def assess(self, profile: ExtractedProfile, criteria: SearchCriteria) -> Judgement:
        return (await self.assess_many([profile], criteria))[0]

    async def assess_many(
        self, profiles: list[ExtractedProfile], criteria: SearchCriteria
    ) -> list[Judgement]:
        """
        Several candidates in one call. The instructions and the requirements are
        most of a call's tokens, so sending them once per batch rather than once per
        person is what makes judging every candidate affordable. Each candidate is
        still answered — and its quotes checked — on its own text only.
        """
        bases = [keyword_signals(profile, criteria) for profile in profiles]
        asked = [
            requirement
            for requirement in criteria.effective_requirements()
            if requirement.id != SignalType.LOCATION
        ]
        texts = [profile_text(profile) for profile in profiles]
        judgements = [Judgement(base) for base in bases]
        todo = [index for index, text in enumerate(texts) if text]
        if not asked or not todo:
            return judgements

        try:
            replies = await self._ask([texts[index] for index in todo], asked)
        except ProviderError as error:
            # Judged by words instead: one failed call must not lose the candidates.
            log.warning("judge_fell_back", extra={"candidates": len(todo), "error": str(error)})
            return judgements

        for position, index in enumerate(todo):
            reply = replies.get(position)
            if reply is None:
                continue  # the model skipped this one: its words judge it instead
            answers, person = reply
            judgements[index] = self._judged(
                profiles[index], bases[index], asked, answers, person, texts[index]
            )
        return judgements

    def _judged(
        self,
        profile: ExtractedProfile,
        base: list[LeadSignal],
        asked: list[Requirement],
        answers: dict[str, dict[str, Any]],
        person: tuple[bool | None, str, str, str, str],
        text: str,
    ) -> Judgement:
        by_id = {requirement.id: requirement for requirement in asked}
        judged: list[LeadSignal] = []
        for signal in base:
            requirement = by_id.get(str(signal.type))
            answer = answers.get(str(signal.type))
            if requirement is None or answer is None:
                judged.append(signal)
                continue
            judged.append(self._verdict(signal, requirement, answer, text, profile))
        # A requirement the keyword pass never mentioned still gets its answer.
        present = {str(signal.type) for signal in base}
        for requirement in asked:
            if requirement.id not in present and requirement.id in answers:
                empty = _labelled(_not_seen(requirement.id, profile), requirement)
                judged.append(
                    self._verdict(empty, requirement, answers[requirement.id], text, profile)
                )
        is_person, reason, kind, country, said = person
        # A place counts only with the words that say it, checked like any quote.
        placed = bool(country) and quoted(said, text)
        return Judgement(
            judged,
            is_person=is_person,
            reason=reason,
            not_person_kind=kind,
            country=country if placed else None,
            country_evidence=said if placed else "",
        )

    @staticmethod
    def _verdict(
        signal: LeadSignal,
        requirement: Requirement,
        answer: dict[str, Any],
        text: str,
        profile: ExtractedProfile,
    ) -> LeadSignal:
        evidence = " ".join(str(answer.get("evidence") or "").split())
        met = bool(answer.get("met")) and quoted(evidence, text)
        if not met and _dated_activity(signal):
            # Read by code from a date the judge never sees as such — a post's
            # publication date, the index's page age. A text reader saying "no
            # date in the text" does not make the date go away.
            return signal.model_copy(update={"label": requirement.label or None})
        if not met:
            return signal.model_copy(update={"detected": False, "confidence": 0, "evidence": None})
        try:
            confidence = float(answer.get("confidence") or 0)
        except (TypeError, ValueError):
            confidence = 0.0
        source = profile.sources[0] if profile.sources else None
        return signal.model_copy(
            update={
                "detected": True,
                "confidence": max(0.3, min(MAX_JUDGED_CONFIDENCE, confidence)),
                "evidence": evidence,
                "source_url": signal.source_url or (source.url if source else profile.url),
                "label": requirement.label or None,
            }
        )

    async def _ask(
        self, texts: list[str], requirements: list[Requirement]
    ) -> dict[int, tuple[dict[str, dict[str, Any]], tuple[bool | None, str, str, str, str]]]:
        """One call for a batch; the answers keyed by the candidate's position."""
        listing = "\n".join(
            f"- id={requirement.id}: {requirement.label or requirement.id}"
            + (
                f" — {requirement.description or PRESET_DESCRIPTIONS.get(requirement.id, '')}"
                if requirement.description or requirement.id in PRESET_DESCRIPTIONS
                else ""
            )
            for requirement in requirements
        )
        ids = [requirement.id for requirement in requirements]
        numbers = list(range(1, len(texts) + 1))
        result = {
            "type": "object",
            "properties": {
                "id": {"type": "string", "enum": ids},
                "met": {"type": "boolean"},
                "confidence": {"type": "number"},
                "evidence": {"type": "string"},
            },
            "required": ["id", "met", "confidence", "evidence"],
            "additionalProperties": False,
        }
        schema = {
            "type": "object",
            "properties": {
                "candidates": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "candidate": {"type": "integer", "enum": numbers},
                            "is_person": {"type": "boolean"},
                            "not_person_reason": {"type": "string"},
                            "not_person_kind": {"type": "string", "enum": list(NOT_PERSON_KINDS)},
                            "country": {"type": "string"},
                            "country_evidence": {"type": "string"},
                            "results": {"type": "array", "items": result},
                        },
                        "required": [
                            "candidate",
                            "is_person",
                            "not_person_reason",
                            "not_person_kind",
                            "country",
                            "country_evidence",
                            "results",
                        ],
                        "additionalProperties": False,
                    },
                }
            },
            "required": ["candidates"],
            "additionalProperties": False,
        }
        profiles = "\n\n".join(
            f"=== Candidate {number} ===\n{text}"
            for number, text in zip(numbers, texts, strict=True)
        )
        payload = {
            "model": self.model,
            "temperature": 0,
            "messages": [
                {"role": "system", "content": JUDGE_PROMPT},
                {
                    "role": "user",
                    "content": (
                        # A post's date means nothing to a reader who does not know
                        # what day it is.
                        f"Today is {datetime.now(UTC).date().isoformat()}.\n\n"
                        f"Requirements:\n{listing}\n\nJudge every candidate below on its "
                        f"own text only; quotes must come from that candidate's text.\n\n"
                        f"{profiles}"
                    ),
                },
            ],
            "response_format": {
                "type": "json_schema",
                "json_schema": {"name": "requirements_check", "strict": True, "schema": schema},
            },
        }
        raw = await self._post(payload)
        candidates = raw.get("candidates") if isinstance(raw, dict) else None
        if not isinstance(candidates, list):
            raise ProviderError("The judge returned no candidates", provider=self.name)

        replies: dict[
            int, tuple[dict[str, dict[str, Any]], tuple[bool | None, str, str, str, str]]
        ] = {}
        for entry in candidates:
            if not isinstance(entry, dict) or entry.get("candidate") not in numbers:
                continue
            results = entry.get("results") if isinstance(entry.get("results"), list) else []
            answers = {
                str(item.get("id")): item
                for item in results
                if isinstance(item, dict) and item.get("id") in ids
            }
            person = entry.get("is_person")
            replies[int(entry["candidate"]) - 1] = (
                answers,
                (
                    person if isinstance(person, bool) else None,
                    " ".join(str(entry.get("not_person_reason") or "").split())[:200],
                    _kind(entry.get("not_person_kind")),
                    " ".join(str(entry.get("country") or "").split())[:60],
                    " ".join(str(entry.get("country_evidence") or "").split())[:200],
                ),
            )
        return replies

    async def _post(self, payload: dict[str, Any]) -> dict[str, Any]:
        client = self._client or httpx.AsyncClient(timeout=httpx.Timeout(self._timeout))
        try:
            response = await client.post(
                self._endpoint, json=payload, headers={"Authorization": f"Bearer {self.api_key}"}
            )
        except httpx.HTTPError as error:
            raise ProviderUnavailableError(
                f"OpenAI request failed: {error}", provider=self.name
            ) from error
        finally:
            if self._client is None:
                await client.aclose()

        if response.status_code in (401, 403):
            raise ProviderAuthError("OpenAI rejected the API key", provider=self.name)
        if response.status_code >= 400:
            raise ProviderError(
                f"OpenAI answered {response.status_code}: {response.text[:300]}",
                provider=self.name,
            )
        try:
            message = response.json()["choices"][0]["message"]
            if message.get("refusal"):
                raise ProviderError("The judge refused", provider=self.name)
            return json.loads(message["content"])
        except (KeyError, IndexError, TypeError, ValueError) as error:
            raise ProviderError(
                "OpenAI returned an unreadable answer", provider=self.name
            ) from error


class BudgetedSignalDetector(SignalDetector):
    """
    A paid judge with a limit: the first `limit` candidates are judged by it, the
    rest by their words. One per search, so `paid_calls` is that search's count.
    """

    def __init__(self, primary: SignalDetector, limit: int) -> None:
        self._primary = primary
        self.limit = max(0, limit)
        self.name = primary.name
        self.paid = primary.paid
        self.paid_calls = 0

    async def detect(self, profile: ExtractedProfile, criteria: SearchCriteria) -> list[LeadSignal]:
        return (await self.assess(profile, criteria)).signals

    async def assess(self, profile: ExtractedProfile, criteria: SearchCriteria) -> Judgement:
        return (await self.assess_many([profile], criteria))[0]

    async def assess_many(
        self, profiles: list[ExtractedProfile], criteria: SearchCriteria
    ) -> list[Judgement]:
        room = max(0, self.limit - self.paid_calls)
        paid, free = profiles[:room], profiles[room:]
        self.paid_calls += len(paid)
        judged = await assess_many(self._primary, paid, criteria) if paid else []
        return [*judged, *(Judgement(keyword_signals(p, criteria)) for p in free)]


#: The labels `profile_text` writes in front of each field. Never evidence.
def _dated_activity(signal: LeadSignal) -> bool:
    """An activity sighting the code read off a date (see `DATED_ACTIVITY_CONFIDENCE`)."""
    return (
        str(signal.type) == SignalType.ACTIVITY
        and signal.detected
        and signal.confidence >= DATED_ACTIVITY_CONFIDENCE
    )


PROFILE_LABELS = re.compile(
    r"(?:^|\n|\s)(?:Address|Name|Headline|Company|Location|Languages|About|Search result"
    r"|Their own post(?: \(published [\d-]+\))?):",
)


def quoted(evidence: str, text: str) -> bool:
    """
    Whether a model's quote is really on the profile — the one check that keeps a
    judge from inventing the evidence it is scored by.

    Whitespace and case are forgiven; anything else is not. A quote cut with an
    ellipsis is checked piece by piece, every piece having to be there.
    """
    if not evidence or PROFILE_LABELS.search(evidence):
        # "Address: https://www.instagram.com/… Name: …" is on the text, and it
        # proves nothing: it was quoted as evidence of "runs Instagram and reels".
        return False
    haystack = " ".join(text.split()).casefold()
    pieces = [
        " ".join(piece.split()).casefold().strip(" \"'«»“”")
        for piece in re.split(r"…|\.\.\.", evidence)
    ]
    pieces = [piece for piece in pieces if len(piece) >= MIN_TERM]
    return bool(pieces) and all(piece in haystack for piece in pieces)
