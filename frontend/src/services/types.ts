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
  /** Score points per signal. Must total 100 — the backend owns the arithmetic. */
  signalWeights: Record<ScoredSignalType, number>;
  sources: SourceKind[];
}

export interface SearchProgress {
  queries: number;
  queriesCompleted: number;
  urlsDiscovered: number;
  profilesDiscovered: number;
  profilesProcessed: number;
  qualified: number;
  highQuality: number;
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
}

export interface SearchUsage {
  searchApiCalls: number;
  pagesAnalyzed: number;
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
  /** "fixture" until the real providers are configured (Phases 4–6). */
  pipeline: "fixture" | "live";
  storage: "browser" | "memory" | "postgres";
  /** Whether the store answered a query just now (API mode only). */
  database?: boolean;
  /** Whether a provider key is configured — never the key itself. */
  providers: { braveSearch: boolean; scrapegraph: boolean; openai: boolean };
}

/* ------------------------------------------------------- service interfaces */

export interface SearchService {
  list(): Promise<SearchSummary[]>;
  get(id: string): Promise<Search>;
  create(input: CreateSearchInput): Promise<CreateSearchResponse>;
  cancel(id: string): Promise<Search>;
  leads(id: string, filters?: LeadFilters): Promise<Paginated<Lead>>;
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
  reset(): Promise<void>;
}
