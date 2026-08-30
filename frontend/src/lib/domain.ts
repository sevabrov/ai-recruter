/**
 * Display vocabulary for the domain: labels, orderings and small derivations
 * shared by every screen. Keeps wording consistent and out of components.
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

export const SIGNAL_LABELS: Record<SignalType, string> = {
  mlm: "MLM experience",
  beauty: "Beauty / cosmetics",
  recruiting: "Active recruiting",
  leadership: "Team leadership",
  location: "Geographic match",
  personalBrand: "Personal brand",
  activity: "Active social media",
};

export const SIGNAL_SHORT_LABELS: Record<SignalType, string> = {
  mlm: "MLM",
  beauty: "Beauty",
  recruiting: "Recruiting",
  leadership: "Leadership",
  location: "Location",
  personalBrand: "Brand",
  activity: "Activity",
};

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

export const PLATFORM_LABELS: Record<Platform, string> = {
  instagram: "Instagram",
  linkedin: "LinkedIn",
  facebook: "Facebook",
  threads: "Threads",
  website: "Website",
  blog: "Blog",
};

export const SOURCE_KINDS: {
  id: SourceKind;
  label: string;
  hint: string;
  platform?: Platform;
}[] = [
  {
    id: "public_web",
    label: "Public web",
    hint: "Indexed pages, directories, press",
  },
  {
    id: "instagram_public",
    label: "Instagram public pages",
    hint: "Public profiles and posts",
    platform: "instagram",
  },
  {
    id: "linkedin_public",
    label: "LinkedIn public pages",
    hint: "Public /in/ profiles",
    platform: "linkedin",
  },
  {
    id: "facebook_public",
    label: "Facebook public pages",
    hint: "Public pages and groups",
    platform: "facebook",
  },
  {
    id: "threads_public",
    label: "Threads public pages",
    // Not a guess: every Threads query in every measured run came back with
    // nothing, while still costing a search call.
    hint: "Public profiles — returns almost nothing",
    platform: "threads",
  },
  {
    id: "company_websites",
    label: "Company websites",
    hint: "Team and distributor pages",
    platform: "website",
  },
  {
    id: "blogs",
    label: "Blogs",
    hint: "Personal blogs, guest posts",
    platform: "blog",
  },
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

export const LEAD_STATUSES: { id: LeadStatus; label: string; tone: Tone }[] = [
  { id: "new", label: "New", tone: "neutral" },
  { id: "reviewed", label: "Reviewed", tone: "info" },
  { id: "qualified", label: "Qualified", tone: "good" },
  { id: "contact_later", label: "Contact later", tone: "warn" },
  { id: "contacted", label: "Contacted", tone: "accent" },
  { id: "rejected", label: "Rejected", tone: "bad" },
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
  label: string;
  tone: Tone;
  group: RejectionGroup;
  hint: string;
}[] = [
  {
    id: "unreadable",
    label: "Page would not open",
    tone: "warn",
    group: "unseen",
    hint: "The reader failed on the address. Nothing about these people was ever seen.",
  },
  {
    id: "not_examined",
    label: "Never opened",
    tone: "warn",
    group: "unseen",
    hint: "The search already had the leads it was asked for and stopped. Ask for more to reach these.",
  },
  {
    id: "not_a_profile",
    label: "Not a profile page",
    tone: "neutral",
    group: "unseen",
    hint: "A shop, an article, a login form or a numeric page id — refused for free, before anything was read.",
  },
  {
    id: "off_source",
    label: "Outside your sources",
    tone: "info",
    group: "excluded",
    hint: "Real profiles on a platform you did not pick. Add that platform to the sources to reach them.",
  },
  {
    id: "not_a_person",
    label: "No person on the page",
    tone: "neutral",
    group: "judged",
    hint: "A brand account, a community or a shop.",
  },
  {
    id: "wrong_country",
    label: "Another country",
    tone: "neutral",
    group: "judged",
    hint: "The profile places itself somewhere other than the country you asked for.",
  },
  {
    id: "wrong_language",
    label: "Another language",
    tone: "neutral",
    group: "judged",
    hint: "The profile publishes in a language this search did not ask for.",
  },
  {
    id: "missing_signals",
    label: "Missing a must-have",
    tone: "neutral",
    group: "judged",
    hint: "Every must-have signal is an AND. Keeping one is usually enough.",
  },
];

export function rejectionMeta(reason: RejectionReason) {
  return (
    REJECTION_REASONS.find((entry) => entry.id === reason) ?? {
      id: reason,
      label: reason,
      tone: "neutral" as Tone,
      group: "judged" as RejectionGroup,
      hint: "",
    }
  );
}

export const REJECTION_GROUPS: { id: RejectionGroup; label: string; note: string }[] = [
  {
    id: "unseen",
    label: "Never read",
    note: "Nobody opened these pages. If a lead was lost, it is here.",
  },
  {
    id: "excluded",
    label: "Excluded by your sources",
    note: "Real profiles, on platforms this search was not given.",
  },
  {
    id: "judged",
    label: "Read and refused",
    note: "The page was opened and failed one of your requirements.",
  },
];

export function leadStatusMeta(status: LeadStatus) {
  return LEAD_STATUSES.find((entry) => entry.id === status)!;
}

export const SEARCH_STATUS_LABELS: Record<SearchStatus, string> = {
  draft: "Draft",
  queued: "Queued",
  searching: "Searching",
  extracting: "Extracting",
  scoring: "Scoring",
  completed: "Completed",
  failed: "Failed",
  cancelled: "Cancelled",
};

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
export const PIPELINE_STAGES: { id: SearchStage; label: string }[] = [
  { id: "generating_queries", label: "Queries generated" },
  { id: "web_search", label: "Web search completed" },
  { id: "discovering_profiles", label: "Profiles identified" },
  { id: "extracting", label: "Analyzing candidates" },
  { id: "scoring", label: "Calculating AI scores" },
  { id: "deduplicating", label: "Removing duplicates" },
];

export type ScoreTier = "high" | "medium" | "low";

export function scoreTier(score: number): ScoreTier {
  if (score >= 85) return "high";
  if (score >= 70) return "medium";
  return "low";
}

export const SCORE_TIER_LABELS: Record<ScoreTier, string> = {
  high: "High match",
  medium: "Medium match",
  low: "Low match",
};

export function scoreTierTone(score: number): Tone {
  const tier = scoreTier(score);
  if (tier === "high") return "good";
  if (tier === "medium") return "warn";
  return "neutral";
}

export const HIGH_QUALITY_THRESHOLD = 85;

export function weightLevel(points: number) {
  if (points >= 25) return "HIGH";
  if (points >= 12) return "MEDIUM";
  return "LOW";
}

export function criteriaTarget(criteria: SearchCriteria) {
  const parts = [
    criteria.businessTypes.join(" / "),
    criteria.industry.join(" / "),
  ].filter(Boolean);
  return parts.join(" · ") || "Unspecified target";
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
