/**
 * API CONTRACTS
 * =============
 * The single source of truth shared by the mock services (Phase 1) and the
 * FastAPI client that replaces them (Phase 2+). UI components import types from
 * here only — never from the mock modules — so swapping the implementation is a
 * one-line change in src/services/index.ts.
 */

/* ------------------------------------------------------------------ search */

export type SearchStatus =
  | "draft"
  | "queued"
  | "searching"
  | "extracting"
  | "scoring"
  | "completed"
  | "failed"
  | "cancelled";

export type SourceKind =
  | "public_web"
  | "instagram_public"
  | "linkedin_public"
  | "facebook_public"
  | "threads_public"
  | "company_websites"
  | "blogs";

export type SignalType =
  | "mlm"
  | "beauty"
  | "recruiting"
  | "leadership"
  | "location"
  | "personalBrand"
  | "activity";

/** Signals that carry score points. `activity` is detected but not scored. */
export type ScoredSignalType = Exclude<SignalType, "activity">;

export type SignalWeightLevel = "low" | "medium" | "high";

export interface GeoLocation {
  country?: string;
  region?: string;
  city?: string;
}

export interface SearchCriteria {
  industry: string[];
  businessTypes: string[];
  keywords: string[];
  negativeKeywords: string[];
  location: GeoLocation;
  languages: string[];
  mustHave: SignalType[];
  niceToHave: SignalType[];
  /**
   * Country and language as requirements rather than as points: a candidate who
   * fails one never becomes a lead. Both default to on, and both are per search —
   * the price of a hard filter is the person whose bio never says where they live.
   */
  requireLocation?: boolean;
  requireLanguage?: boolean;
  /**
   * …and whether a profile that says nothing about it is refused too. Off by
   * default: "we could not tell" is not "somewhere else", and treating the two as
   * one answer emptied a search — 18 of 19 geographic refusals in one run were
   * profiles with no location on them at all.
   */
  requireConfirmedLocation?: boolean;
  requireConfirmedLanguage?: boolean;
  /** Score points per signal. Must total 100 — the backend owns the arithmetic. */
  signalWeights: Record<ScoredSignalType, number>;
  sources: SourceKind[];
  /**
   * Queries written by hand, run ahead of the generated ones and never dropped by
   * the query cap. No template is going to guess that
   * `site:instagram.com "#млмукраина"` is how a particular market labels itself.
   */
  customQueries?: string[];
  /**
   * How many leads to look for. It buys the page budget, so it is also what the
   * wizard prices. 0 means "whatever the server allows".
   */
  targetLeads?: number;
}

export interface SearchProgress {
  queries: number;
  queriesCompleted: number;
  urlsDiscovered: number;
  profilesDiscovered: number;
  profilesProcessed: number;
  qualified: number;
  highQuality: number;
  /**
   * Why the rest did not qualify. Optional because searches recorded before the
   * criteria became gates have no such counters and are still valid history.
   */
  /** Found on a platform that was not among the chosen sources. */
  rejectedOffSource?: number;
  /** The reader failed on the address, so nothing was read and nothing judged. */
  rejectedUnreadable?: number;
  rejectedNotAPerson?: number;
  rejectedCountry?: number;
  rejectedLanguage?: number;
  rejectedSignals?: number;
  /** 0–100, backend-owned once Phase 7 lands. */
  percent: number;
  stage: SearchStage;
}

export type SearchStage =
  | "queued"
  | "generating_queries"
  | "web_search"
  | "discovering_profiles"
  | "extracting"
  | "scoring"
  | "deduplicating"
  | "done";

export interface GeneratedQuery {
  id: string;
  query: string;
  provider: string;
  resultCount: number;
  /** Which language's index this query was put to. Absent means the default market. */
  language?: string | null;
}

export interface SearchUsage {
  searchApiCalls: number;
  /** Candidate pages the extraction stage handled. */
  pagesAnalyzed: number;
  /** …of which were actually fetched, and are what the page bill is based on. */
  pagesRead: number;
  /** …and of which came from the scrape cache, at no cost. */
  pagesCached: number;
  /** …and of which the search's page budget refused: snippet leads, no credits. */
  pagesSkipped: number;
  /** In the plan's own units, counting every request the reader's service served. */
  scrapeCredits: number;
  llmCalls: number;
  estimatedCostEur: number;
}

export interface SearchSummary {
  id: string;
  name: string;
  status: SearchStatus;
  createdAt: string;
  startedAt?: string;
  completedAt?: string;
  leadCount: number;
  highQualityCount: number;
  /** Short human label, e.g. "Beauty / MLM · Spain". */
  target: string;
  country?: string;
  sources: SourceKind[];
}

export interface Search extends SearchSummary {
  criteria: SearchCriteria;
  progress: SearchProgress;
  usage: SearchUsage;
  queries: GeneratedQuery[];
  error?: string;
}

export interface CreateSearchInput {
  name: string;
  criteria: SearchCriteria;
}

export interface CreateSearchResponse {
  searchId: string;
  status: SearchStatus;
}

/**
 * What a search would cost, asked before it is started.
 *
 * A ceiling, not a forecast: the backend derives this figure and the run's page
 * budget from the same function, so a search cannot cost more than was quoted.
 */
export interface SearchEstimate {
  queries: { query: string; language?: string | null }[];
  /** One query is one billed call. */
  searchCalls: number;
  /** The most pages this search may pay to read. 0 = no page is ever paid for. */
  maxPages: number;
  /** …in the reader plan's own units. */
  credits: number;
  targetLeads: number;
  /** How many paid pages one lead is assumed to take. Measured, not fixed. */
  pagesPerLead: number;
  maxCostEur: number;
  /** Whether pages are read at all right now, so the UI can say why it is free. */
  readsPages: boolean;
  /** What these criteria are likely to do to the result, before it is paid for. */
  warnings?: string[];
}

/* ---------------------------------------------------------------- rejected */

/**
 * Why a candidate is not in the lead list.
 *
 * Four of these are the requirements the search was given; the other four happen
 * before anything is judged — the address was not a profile, it was on a platform
 * nobody asked for, the reader failed, or the search already had enough leads.
 */
export type RejectionReason =
  | "not_a_profile"
  | "off_source"
  | "unreadable"
  | "not_a_person"
  | "wrong_country"
  | "wrong_language"
  | "missing_signals"
  | "not_examined";

export interface RejectedCandidate {
  id: string;
  url: string;
  platform: Platform;
  reason: RejectionReason;
  /** The sentence that explains this refusal, written where it happened. */
  detail: string;
  /**
   * Whether the page itself was opened. False means the verdict rests on a
   * two-line search result — which is where a missed lead would be hiding.
   */
  read: boolean;
  name: string;
  title: string;
  snippet: string;
  query: string;
  /** What the search result alone supported, 0–100. Absent when never ranked. */
  promise?: number | null;
  createdAt: string;
}

/**
 * The other half of a search result: everything the run turned away.
 *
 * Every discovered address ends up in exactly one of the two lists, so leads plus
 * these are a complete account of what the search saw.
 */
export interface RejectedList {
  items: RejectedCandidate[];
  total: number;
  /** Counted over the whole run, not over `items` — see the backend schema. */
  byReason: Partial<Record<RejectionReason, number>>;
  /** Refusals decided without the page ever being opened. */
  unseen: number;
}

/* -------------------------------------------------------------------- lead */

export type Platform =
  | "instagram"
  | "linkedin"
  | "facebook"
  | "threads"
  | "website"
  | "blog";

export type LeadStatus =
  | "new"
  | "reviewed"
  | "qualified"
  | "contact_later"
  | "contacted"
  | "rejected";

export interface LeadPlatform {
  platform: Platform;
  handle?: string;
  url: string;
  followers?: number;
}

/** Never a bare boolean: every signal carries confidence, evidence and origin. */
export interface LeadSignal {
  type: SignalType;
  detected: boolean;
  confidence: number;
  evidence?: string;
  sourceUrl?: string;
  sourcePlatform?: Platform;
}

export interface LeadSource {
  id: string;
  platform: Platform;
  url: string;
  title: string;
  snippet: string;
  discoveredAt: string;
}

export interface ScoreComponent {
  type: ScoredSignalType;
  awarded: number;
  max: number;
}

export interface LeadContacts {
  email?: string;
  website?: string;
  phone?: string;
}

export interface LeadNote {
  id: string;
  body: string;
  author: string;
  createdAt: string;
}

export interface Lead {
  id: string;
  searchId: string;
  searchName: string;
  name: string;
  headline: string;
  company?: string;
  location?: GeoLocation;
  languages: string[];
  score: number;
  scoreBreakdown: ScoreComponent[];
  platforms: LeadPlatform[];
  summary: string;
  signals: LeadSignal[];
  sources: LeadSource[];
  contacts: LeadContacts;
  status: LeadStatus;
  saved: boolean;
  archived: boolean;
  notes: LeadNote[];
  createdAt: string;
  updatedAt?: string;
}

export type LeadSort = "score_desc" | "newest" | "name_asc";

export interface LeadFilters {
  searchId?: string;
  query?: string;
  minScore?: number;
  countries?: string[];
  platforms?: Platform[];
  signals?: SignalType[];
  statuses?: LeadStatus[];
  hasEmail?: boolean;
  hasSocial?: boolean;
  savedOnly?: boolean;
  includeArchived?: boolean;
  sort?: LeadSort;
  page?: number;
  pageSize?: number;
}

export interface Paginated<T> {
  items: T[];
  total: number;
  page: number;
  pageSize: number;
}

export interface UpdateLeadInput {
  status?: LeadStatus;
  saved?: boolean;
  archived?: boolean;
}

/* ---------------------------------------------------------------- outreach */

export type OutreachChannel = "instagram_dm" | "linkedin_dm" | "email";
export type OutreachTone = "warm" | "direct" | "formal";

export interface OutreachRequest {
  channel: OutreachChannel;
  tone: OutreachTone;
  language: string;
}

export interface OutreachMessage extends OutreachRequest {
  id: string;
  leadId: string;
  subject?: string;
  body: string;
  createdAt: string;
}

/* --------------------------------------------------------------- dashboard */

export interface DashboardStat {
  label: string;
  value: number;
  /** Percentage change vs. previous period; omitted when not applicable. */
  delta?: number;
  hint?: string;
}

export interface SourceShare {
  platform: Platform;
  share: number;
  leads: number;
}

export interface ScoreBucket {
  label: string;
  from: number;
  to: number;
  count: number;
}

export interface DashboardData {
  stats: {
    totalLeads: DashboardStat;
    highQuality: DashboardStat;
    searches: DashboardStat;
    savedLeads: DashboardStat;
  };
  recentSearches: SearchSummary[];
  sourceBreakdown: SourceShare[];
  scoreDistribution: ScoreBucket[];
  weeklyLeads: { day: string; count: number }[];
}

/* --------------------------------------------------------------- workspace */

export interface HealthStatus {
  status: "ok" | "degraded";
  service: string;
  version: string;
  /** Which delivery phase the data source belongs to. */
  phase: number;
  /**
   * "fixture" while nothing external is called, "live" once every stage has a real
   * service behind it, "partial" in between — Phase 4 with a Brave key searches the
   * real web but still reads and judges with stand-ins.
   */
  pipeline: "fixture" | "partial" | "live";
  storage: "browser" | "memory" | "postgres";
  /** Whether the store answered a query just now (API mode only). */
  database?: boolean;
  /** Which adapter is behind each pipeline stage (API mode only). */
  stages?: { search: string; extraction: string; signals: string };
  /** Whether a provider key is configured — never the key itself. */
  providers: { braveSearch: boolean; scrapegraph: boolean; openai: boolean };
}

/**
 * How one platform responds to being read. Measured, not assumed: the backend
 * counts the outcome of every page it has opened, because "nobody was found on
 * Instagram" and "Instagram showed us a login wall" are different problems.
 */
export interface SourceReliability {
  platform: Platform;
  pages: number;
  usable: number;
  notAPerson: number;
  empty: number;
  blocked: number;
  failed: number;
  /** `usable / pages`, 0–1. */
  usableShare: number;
  lastReadAt?: string;
}

export interface SourcesReport {
  /** Which adapter reads pages, or the stand-in that stands in for one. */
  reader: string;
  /** Whether pages are fetched at all, as opposed to read off the search results. */
  live: boolean;
  cacheTtlHours: number;
  /** What happens to a page that will not open. */
  fallback: string;
  /** Paid page reads one search may make. Null means no ceiling. */
  maxPagesPerSearch?: number | null;
  /** Leads a search stops at. Null means "as many as there are". */
  targetLeads?: number | null;
  /** Assumed cost of one page in the plan's units — the API reports none. */
  creditsPerPage?: number;
  /** How many paid pages one lead is assumed to cost, which is what turns the
   *  lead target the wizard asks for into a page budget and a price. */
  pagesPerLead?: number;
  items: SourceReliability[];
}

/* ------------------------------------------------------- service interfaces */

export interface SearchService {
  list(): Promise<SearchSummary[]>;
  get(id: string): Promise<Search>;
  /** Price a search and preview its queries. Creates nothing, spends nothing. */
  estimate(criteria: SearchCriteria): Promise<SearchEstimate>;
  create(input: CreateSearchInput): Promise<CreateSearchResponse>;
  cancel(id: string): Promise<Search>;
  leads(id: string, filters?: LeadFilters): Promise<Paginated<Lead>>;
  /** Everything the run turned away, so a thin result can be checked, not believed. */
  rejected(id: string, reason?: RejectionReason): Promise<RejectedList>;
}

export interface LeadService {
  list(filters?: LeadFilters): Promise<Paginated<Lead>>;
  get(id: string): Promise<Lead>;
  update(id: string, input: UpdateLeadInput): Promise<Lead>;
  addNote(id: string, body: string): Promise<Lead>;
  generateOutreach(id: string, request: OutreachRequest): Promise<OutreachMessage>;
  facets(): Promise<{ countries: string[]; platforms: Platform[] }>;
}

export interface DashboardService {
  get(): Promise<DashboardData>;
}

/**
 * Workspace-level concerns that both implementations can answer, so no screen
 * has to know which one is active: "is the data source reachable?" and "put the
 * demo data back".
 */
export interface WorkspaceService {
  health(): Promise<HealthStatus>;
  /** Which sources can actually be read, from the backend's own record. */
  sources(): Promise<SourcesReport>;
  reset(): Promise<void>;
}
