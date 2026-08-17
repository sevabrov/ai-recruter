/**
 * Display vocabulary for the domain: labels, orderings and small derivations
 * shared by every screen. Keeps wording consistent and out of components.
 */

import type {
  LeadStatus,
  Platform,
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
    hint: "Public profiles",
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

export const LEAD_STATUSES: { id: LeadStatus; label: string; tone: Tone }[] = [
  { id: "new", label: "New", tone: "neutral" },
  { id: "reviewed", label: "Reviewed", tone: "info" },
  { id: "qualified", label: "Qualified", tone: "good" },
  { id: "contact_later", label: "Contact later", tone: "warn" },
  { id: "contacted", label: "Contacted", tone: "accent" },
  { id: "rejected", label: "Rejected", tone: "bad" },
];

export type Tone = "neutral" | "accent" | "good" | "warn" | "bad" | "info";

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
    mustHave: [],
    niceToHave: [],
    signalWeights: { ...DEFAULT_SIGNAL_WEIGHTS },
    sources: ["public_web", "instagram_public", "linkedin_public"],
  };
}
