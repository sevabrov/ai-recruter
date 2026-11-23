/**
 * Domain vocabulary: orderings, tones and small derivations shared by every
 * screen.
 *
 * The *words* live in `messages/<locale>.json` under the `domain` namespace and
 * are keyed by the ids below - a component reads them with
 * `t('domain.signal.mlm')` and friends, so wording stays consistent without
 * being pinned to one language. Anything here that is still a string is either
 * an id or an operator, never display copy.
 */

import type {
  LeadStatus,
  Platform,
  RejectionReason,
  Requirement,
  RequirementImportance,
  ScoredSignalType,
  SearchCriteria,
  SearchStage,
  SearchStatus,
  SignalType,
  SourceKind,
} from "@/services/types";

export const SIGNAL_TYPES: SignalType[] = [
  "mlm",
  "beauty",
  "recruiting",
  "leadership",
  "activity",
  "personalBrand",
  "location",
];

export const SCORED_SIGNALS: ScoredSignalType[] = [
  "mlm",
  "beauty",
  "recruiting",
  "leadership",
  "location",
  "personalBrand",
];

export const DEFAULT_SIGNAL_WEIGHTS: Record<ScoredSignalType, number> = {
  mlm: 30,
  beauty: 20,
  recruiting: 20,
  leadership: 15,
  location: 10,
  personalBrand: 5,
};

export const PLATFORMS: Platform[] = [
  "instagram",
  "linkedin",
  "facebook",
  "threads",
  "website",
  "blog",
];

/**
 * Sources in the order the wizard offers them. The label and the hint are
 * `domain.source.<id>.label` / `.hint`; a note about why a source behaves the
 * way it does belongs with the translation, not here - Threads, for instance,
 * came back empty in every measured run while still costing a search call.
 */
export const SOURCE_KINDS: { id: SourceKind; platform?: Platform }[] = [
  { id: "public_web" },
  { id: "instagram_public", platform: "instagram" },
  { id: "linkedin_public", platform: "linkedin" },
  { id: "facebook_public", platform: "facebook" },
  { id: "threads_public", platform: "threads" },
  { id: "company_websites", platform: "website" },
  { id: "blogs", platform: "blog" },
];

/**
 * The `site:` operator that keeps a query on one platform, per source.
 *
 * One map, used by the query preview and by the wizard's own-query builder, so
 * what the client is offered and what the backend generates cannot drift apart.
 */
export const SITE_BY_SOURCE: Partial<Record<SourceKind, string>> = {
  instagram_public: "site:instagram.com",
  linkedin_public: "site:linkedin.com/in",
  facebook_public: "site:facebook.com",
  threads_public: "site:threads.net",
};

/** Sources that mean "anywhere on the indexed web", where a bare query belongs. */
export const WEB_SOURCES: SourceKind[] = ["public_web", "company_websites", "blogs"];

/**
 * Closed vocabularies, as `{ id, token }`.
 *
 * The *token* is what the criteria store and the backend keys on - the country
 * name the markets map knows, the English industry word the phrasebook
 * translates into each query language. The *id* names its translation:
 * `domain.country.<id>`, `domain.language.<id>`, `domain.industry.<id>`,
 * `domain.businessType.<id>`. The client never sees a token: the old wizard
 * showed them raw, which is how "Cosmetics / Beauty" ended up on a Ukrainian
 * screen. Mirrors `backend/app/services/brief/vocabulary.py`.
 */
export type VocabularyEntry = { id: string; token: string };

export const COUNTRIES: VocabularyEntry[] = [
  { id: "UA", token: "Ukraine" },
  { id: "ES", token: "Spain" },
  { id: "PL", token: "Poland" },
  { id: "DE", token: "Germany" },
  { id: "IT", token: "Italy" },
  { id: "PT", token: "Portugal" },
  { id: "FR", token: "France" },
  { id: "NL", token: "Netherlands" },
  { id: "CZ", token: "Czechia" },
  { id: "AT", token: "Austria" },
  { id: "CH", token: "Switzerland" },
  { id: "GB", token: "United Kingdom" },
  { id: "RO", token: "Romania" },
  { id: "BE", token: "Belgium" },
  { id: "US", token: "United States" },
];

export const LANGUAGES: VocabularyEntry[] = [
  { id: "uk", token: "Ukrainian" },
  { id: "ru", token: "Russian" },
  { id: "en", token: "English" },
  { id: "es", token: "Spanish" },
  { id: "pl", token: "Polish" },
  { id: "de", token: "German" },
  { id: "it", token: "Italian" },
  { id: "pt", token: "Portuguese" },
  { id: "fr", token: "French" },
  { id: "ro", token: "Romanian" },
  { id: "cs", token: "Czech" },
  { id: "nl", token: "Dutch" },
];

export const INDUSTRIES: VocabularyEntry[] = [
  { id: "beauty", token: "Beauty" },
  { id: "cosmetics", token: "Cosmetics" },
  { id: "skincare", token: "Skincare" },
  { id: "perfume", token: "Perfume" },
  { id: "wellness", token: "Wellness" },
  { id: "supplements", token: "Supplements" },
  { id: "hair", token: "Hair" },
  { id: "nails", token: "Nails" },
  { id: "household", token: "Household" },
];

export const BUSINESS_TYPES: VocabularyEntry[] = [
  { id: "mlm", token: "MLM" },
  { id: "networkMarketing", token: "Network marketing" },
  { id: "directSales", token: "Direct sales" },
  { id: "affiliate", token: "Affiliate" },
  { id: "franchise", token: "Franchise" },
];

/** The entry a stored token belongs to, case-insensitively; undefined if none. */
export function vocabularyEntry(list: VocabularyEntry[], token?: string | null) {
  const key = (token ?? "").trim().toLowerCase();
  return key ? list.find((entry) => entry.token.toLowerCase() === key) : undefined;
}

/**
 * Where a new search looks when the brief names no platform: the three that
 * return people. The open web is left out - with no `site:` it spent a third of
 * a run's calls on directories and articles.
 */
export const DEFAULT_SOURCES: SourceKind[] = [
  "instagram_public",
  "facebook_public",
  "linkedin_public",
];

export const LEAD_STATUSES: { id: LeadStatus; tone: Tone }[] = [
  { id: "new", tone: "neutral" },
  { id: "reviewed", tone: "info" },
  { id: "qualified", tone: "good" },
  { id: "contact_later", tone: "warn" },
  { id: "contacted", tone: "accent" },
  { id: "rejected", tone: "bad" },
];

export type Tone = "neutral" | "accent" | "good" | "warn" | "bad" | "info";

/**
 * How the refused half of a result is presented.
 *
 * `group` is the part that answers the question the list exists for - *are we
 * losing leads in there?* A candidate whose page was opened was judged on what
 * they published; one refused at an address nobody opened was judged on a
 * two-line search result, and that is where a lead can hide. The third group is
 * the sources the client themselves excluded, which is a setting, not a loss.
 */
export type RejectionGroup = "unseen" | "excluded" | "judged";

export const REJECTION_REASONS: {
  id: RejectionReason;
  tone: Tone;
  group: RejectionGroup;
}[] = [
  { id: "unreadable", tone: "warn", group: "unseen" },
  { id: "not_examined", tone: "warn", group: "unseen" },
  { id: "not_a_profile", tone: "neutral", group: "unseen" },
  { id: "off_source", tone: "info", group: "excluded" },
  { id: "not_a_person", tone: "neutral", group: "judged" },
  { id: "wrong_country", tone: "neutral", group: "judged" },
  { id: "wrong_language", tone: "neutral", group: "judged" },
  { id: "missing_signals", tone: "neutral", group: "judged" },
];

/** True for a reason this build knows how to name; unknown ones render raw. */
export function isKnownRejectionReason(reason: string) {
  return REJECTION_REASONS.some((entry) => entry.id === reason);
}

export function rejectionMeta(reason: RejectionReason) {
  return (
    REJECTION_REASONS.find((entry) => entry.id === reason) ?? {
      id: reason,
      tone: "neutral" as Tone,
      group: "judged" as RejectionGroup,
    }
  );
}

export const REJECTION_GROUPS: RejectionGroup[] = ["unseen", "excluded", "judged"];

export function leadStatusMeta(status: LeadStatus) {
  return LEAD_STATUSES.find((entry) => entry.id === status)!;
}

export const SEARCH_STATUSES: SearchStatus[] = [
  "draft",
  "queued",
  "searching",
  "extracting",
  "scoring",
  "completed",
  "failed",
  "cancelled",
];

export function searchStatusTone(status: SearchStatus): Tone {
  if (status === "completed") return "good";
  if (status === "failed") return "bad";
  if (status === "cancelled" || status === "draft") return "neutral";
  return "accent";
}

export function isSearchRunning(status: SearchStatus) {
  return (
    status === "queued" ||
    status === "searching" ||
    status === "extracting" ||
    status === "scoring"
  );
}

/** The pipeline the progress screen narrates, in order. */
export const PIPELINE_STAGES: SearchStage[] = [
  "generating_queries",
  "web_search",
  "discovering_profiles",
  "extracting",
  "scoring",
  "deduplicating",
];

export type ScoreTier = "high" | "medium" | "low";

export function scoreTier(score: number): ScoreTier {
  if (score >= 85) return "high";
  if (score >= 70) return "medium";
  return "low";
}

export function scoreTierTone(score: number): Tone {
  const tier = scoreTier(score);
  if (tier === "high") return "good";
  if (tier === "medium") return "warn";
  return "neutral";
}

export const HIGH_QUALITY_THRESHOLD = 85;

export type WeightLevel = "HIGH" | "MEDIUM" | "LOW";

export function weightLevel(points: number): WeightLevel {
  if (points >= 25) return "HIGH";
  if (points >= 12) return "MEDIUM";
  return "LOW";
}

/**
 * The short summary line next to a search name. It is built from the client's
 * own words, so it is not translated; only the empty case has to say something,
 * and that is left to the caller.
 */
export function criteriaTarget(criteria: SearchCriteria) {
  const parts = [
    criteria.businessTypes.join(" / "),
    criteria.industry.join(" / "),
  ].filter(Boolean);
  return parts.join(" · ");
}

/** Relative share of the 100 points per importance (mirrors the backend). */
const IMPORTANCE_SHARE: Record<RequirementImportance, number> = {
  required: 3,
  high: 2,
  normal: 1,
};

export const REQUIREMENT_IMPORTANCE: RequirementImportance[] = ["required", "high", "normal"];

/** At most this many requirements; past it each one is worth too little to matter. */
export const MAX_REQUIREMENTS = 8;

/** Whether a requirement id names a built-in signal (translated by the interface). */
export function isPresetSignal(id: string): id is SignalType {
  return (SIGNAL_TYPES as string[]).includes(id);
}

/**
 * The same requirements with points shared out by importance, summing to 100.
 * Mirrors `balanced` in `backend/app/models/search.py`: the client picks how much
 * each thing matters, never a number that has to add up.
 */
export function balanceRequirements(requirements: Requirement[]): Requirement[] {
  const scored = requirements.filter((requirement) => requirement.id !== "activity");
  const shares = scored.map((requirement) => IMPORTANCE_SHARE[requirement.importance]);
  const total = shares.reduce((sum, share) => sum + share, 0);
  if (!total) return requirements.map((requirement) => ({ ...requirement, weight: 0 }));
  const points = shares.map((share) => Math.floor((100 * share) / total));
  const order = shares.map((_, index) => index).sort((a, b) => shares[b] - shares[a]);
  for (const index of order.slice(0, 100 - points.reduce((sum, value) => sum + value, 0))) {
    points[index] += 1;
  }
  const byId = new Map(scored.map((requirement, index) => [requirement.id, points[index]]));
  return requirements.map((requirement) => ({
    ...requirement,
    weight: byId.get(requirement.id) ?? 0,
  }));
}

/**
 * What a search is judged by. A search recorded before requirements existed is
 * read the way it was run: each scored signal with its points, a must-have
 * required (mirrors `SearchCriteria.effective_requirements`).
 */
export function effectiveRequirements(criteria: SearchCriteria): Requirement[] {
  if (criteria.requirements) return criteria.requirements;
  const weights = { ...DEFAULT_SIGNAL_WEIGHTS, ...criteria.signalWeights };
  const derived: Requirement[] = SCORED_SIGNALS.filter(
    (signal) => (weights[signal] ?? 0) > 0 || criteria.mustHave.includes(signal),
  ).map((signal) => ({
    id: signal,
    weight: weights[signal] ?? 0,
    importance: criteria.mustHave.includes(signal) ? "required" : "normal",
  }));
  if (criteria.mustHave.includes("activity")) {
    derived.push({ id: "activity", weight: 0, importance: "required" });
  }
  return derived;
}

export function emptyCriteria(): SearchCriteria {
  return {
    brief: "",
    aboutMe: "",
    brands: [],
    industry: [],
    businessTypes: [],
    keywords: [],
    negativeKeywords: [],
    location: {},
    languages: [],
    // The country and the languages are requirements by default: a search for one
    // country that returns another country is not that search (spec §32).
    requireLocation: true,
    requireLanguage: true,
    // "We could not tell" is not "somewhere else": an unproven criterion costs its
    // points, not the whole lead.
    requireConfirmedLocation: false,
    requireConfirmedLanguage: false,
    mustHave: [],
    niceToHave: [],
    signalWeights: { ...DEFAULT_SIGNAL_WEIGHTS },
    sources: [...DEFAULT_SOURCES],
    customQueries: [],
    requirements: [],
    targetLeads: DEFAULT_TARGET_LEADS,
  };
}

/**
 * How many leads a new search asks for out of the box.
 *
 * It is the client's spending control: the backend turns it into the page budget
 * and prices it before anything runs. Ten is a working session's worth of people
 * to contact, not a number the product needs to be right about.
 */
export const DEFAULT_TARGET_LEADS = 10;
