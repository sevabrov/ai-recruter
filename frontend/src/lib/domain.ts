/**
 * Domain vocabulary: orderings, tones and small derivations shared by every
 * screen.
 *
 * The *words* live in `messages/<locale>.json` under the `domain` namespace and
 * are keyed by the ids below — a component reads them with
 * `t('domain.signal.mlm')` and friends, so wording stays consistent without
 * being pinned to one language. Anything here that is still a string is either
 * an id or an operator, never display copy.
 */

import type {
  LeadStatus,
  Platform,
  RejectionReason,
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
 * way it does belongs with the translation, not here — Threads, for instance,
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
 * `group` is the part that answers the question the list exists for — *are we
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

export function emptyCriteria(): SearchCriteria {
  return {
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
    sources: ["public_web", "instagram_public", "linkedin_public"],
    customQueries: [],
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
