"""
Domain vocabulary.

These are the same string literals the frontend's `services/types.ts` declares —
they are the wire format, so the values must not drift. `tests/test_contract.py`
guards that.
"""

from enum import StrEnum

from pydantic import BaseModel


class SearchStatus(StrEnum):
    DRAFT = "draft"
    QUEUED = "queued"
    SEARCHING = "searching"
    EXTRACTING = "extracting"
    SCORING = "scoring"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class SearchStage(StrEnum):
    QUEUED = "queued"
    GENERATING_QUERIES = "generating_queries"
    WEB_SEARCH = "web_search"
    DISCOVERING_PROFILES = "discovering_profiles"
    EXTRACTING = "extracting"
    SCORING = "scoring"
    DEDUPLICATING = "deduplicating"
    DONE = "done"


class SourceKind(StrEnum):
    PUBLIC_WEB = "public_web"
    INSTAGRAM_PUBLIC = "instagram_public"
    LINKEDIN_PUBLIC = "linkedin_public"
    FACEBOOK_PUBLIC = "facebook_public"
    THREADS_PUBLIC = "threads_public"
    COMPANY_WEBSITES = "company_websites"
    BLOGS = "blogs"


class SignalType(StrEnum):
    MLM = "mlm"
    BEAUTY = "beauty"
    RECRUITING = "recruiting"
    LEADERSHIP = "leadership"
    LOCATION = "location"
    PERSONAL_BRAND = "personalBrand"
    ACTIVITY = "activity"


#: Signals that carry points. `activity` is detected and shown, never scored,
#: so the weights always sum over exactly these six (spec §37).
SCORED_SIGNALS: tuple[SignalType, ...] = (
    SignalType.MLM,
    SignalType.BEAUTY,
    SignalType.RECRUITING,
    SignalType.LEADERSHIP,
    SignalType.LOCATION,
    SignalType.PERSONAL_BRAND,
)

#: Spec §37's default distribution.
DEFAULT_SIGNAL_WEIGHTS: dict[SignalType, int] = {
    SignalType.MLM: 30,
    SignalType.BEAUTY: 20,
    SignalType.RECRUITING: 20,
    SignalType.LEADERSHIP: 15,
    SignalType.LOCATION: 10,
    SignalType.PERSONAL_BRAND: 5,
}

#: A lead at or above this score is "high quality" everywhere in the product.
HIGH_QUALITY_THRESHOLD = 85


class Platform(StrEnum):
    INSTAGRAM = "instagram"
    LINKEDIN = "linkedin"
    FACEBOOK = "facebook"
    THREADS = "threads"
    WEBSITE = "website"
    BLOG = "blog"


SOCIAL_PLATFORMS = (Platform.INSTAGRAM, Platform.LINKEDIN, Platform.FACEBOOK, Platform.THREADS)


class LeadStatus(StrEnum):
    NEW = "new"
    REVIEWED = "reviewed"
    QUALIFIED = "qualified"
    CONTACT_LATER = "contact_later"
    CONTACTED = "contacted"
    REJECTED = "rejected"


class LeadSort(StrEnum):
    SCORE_DESC = "score_desc"
    NEWEST = "newest"
    NAME_ASC = "name_asc"


class OutreachChannel(StrEnum):
    INSTAGRAM_DM = "instagram_dm"
    LINKEDIN_DM = "linkedin_dm"
    EMAIL = "email"


class OutreachTone(StrEnum):
    WARM = "warm"
    DIRECT = "direct"
    FORMAL = "formal"


class GeoLocation(BaseModel):
    country: str | None = None
    region: str | None = None
    city: str | None = None
