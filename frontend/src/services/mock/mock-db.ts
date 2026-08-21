/**
 * In-browser mock database.
 *
 * Holds everything the Phase 1 demo needs to feel real across reloads:
 * user-created searches, the leads those searches "found", and per-lead user
 * state (status, saved, archived, notes). Backed by localStorage so a client
 * demo survives a refresh; entirely disposable once the FastAPI services land.
 */

import { criteriaTarget } from "@/lib/domain";
import { generateQueryPreview } from "@/lib/query-preview";
import { computeScore } from "@/lib/scoring";
import { hashString, seededRandom } from "@/lib/utils";
import { MOCK_LEADS } from "@/mocks/leads";
import { MOCK_SEARCHES } from "@/mocks/searches";
import { MOCK_SEARCH_DURATION_MS, progressAt } from "@/mocks/search-progress";
import type {
  CreateSearchInput,
  Lead,
  LeadNote,
  LeadSignal,
  LeadStatus,
  Search,
  SearchStatus,
} from "@/services/types";

const STORAGE_KEY = "air.mock.state.v2";

type LeadOverride = {
  status?: LeadStatus;
  saved?: boolean;
  archived?: boolean;
  notes?: LeadNote[];
  updatedAt?: string;
};

type MockState = {
  /** User-created searches only; fixtures stay immutable. */
  searches: Search[];
  /** Leads produced by user-created searches. */
  leads: Lead[];
  overrides: Record<string, LeadOverride>;
};

const EMPTY_STATE: MockState = { searches: [], leads: [], overrides: {} };

let cache: MockState | null = null;

function read(): MockState {
  if (cache) return cache;
  if (typeof window === "undefined") return EMPTY_STATE;
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    cache = raw ? { ...EMPTY_STATE, ...(JSON.parse(raw) as MockState) } : { ...EMPTY_STATE };
  } catch {
    cache = { ...EMPTY_STATE };
  }
  return cache;
}

function write(next: MockState) {
  cache = next;
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
  } catch {
    /* private mode / quota — the in-memory cache still serves this session */
  }
}

export function resetMockState() {
  cache = { ...EMPTY_STATE };
  if (typeof window !== "undefined") {
    try {
      window.localStorage.removeItem(STORAGE_KEY);
    } catch {
      /* ignore */
    }
  }
}

/** Simulated network latency so loading states are visible in the demo. */
export function latency(ms = 180) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

/* ------------------------------------------------------------------ leads */

function applyOverride(lead: Lead, override?: LeadOverride): Lead {
  if (!override) return lead;
  return {
    ...lead,
    status: override.status ?? lead.status,
    saved: override.saved ?? lead.saved,
    archived: override.archived ?? lead.archived,
    notes: override.notes ?? lead.notes,
    updatedAt: override.updatedAt ?? lead.updatedAt,
  };
}

/** Every lead visible to the demo user, fixtures plus generated, overrides applied. */
export function allLeads(): Lead[] {
  const state = read();
  return [...MOCK_LEADS, ...state.leads].map((lead) =>
    applyOverride(lead, state.overrides[lead.id]),
  );
}

export function findLead(id: string): Lead | undefined {
  return allLeads().find((lead) => lead.id === id);
}

export function patchLead(id: string, patch: LeadOverride): Lead {
  const state = read();
  const current = state.overrides[id] ?? {};
  const next: MockState = {
    ...state,
    overrides: {
      ...state.overrides,
      [id]: { ...current, ...patch, updatedAt: new Date().toISOString() },
    },
  };
  write(next);
  const lead = findLead(id);
  if (!lead) throw new Error(`Lead ${id} not found`);
  return lead;
}

export function appendNote(id: string, body: string): Lead {
  const lead = findLead(id);
  if (!lead) throw new Error(`Lead ${id} not found`);
  const note: LeadNote = {
    id: `note_${hashString(id + body + lead.notes.length).toString(36)}`,
    body,
    author: "You",
    createdAt: new Date().toISOString(),
  };
  return patchLead(id, { notes: [...lead.notes, note] });
}

/* --------------------------------------------------------------- searches */

export function allSearches(): Search[] {
  const state = read();
  return [...state.searches, ...MOCK_SEARCHES].sort(
    (a, b) => new Date(b.createdAt).getTime() - new Date(a.createdAt).getTime(),
  );
}

/**
 * Derives status + progress from elapsed time, the same way `GET /searches/:id`
 * will derive them from worker state. The UI polls; nothing is faked in React.
 */
export function projectSearch(search: Search): Search {
  if (!search.startedAt || search.status === "completed" || search.status === "cancelled") {
    return search;
  }
  if (!search.id.startsWith("srch_local_")) return search;

  const elapsed = Date.now() - new Date(search.startedAt).getTime();
  const fraction = Math.min(1, elapsed / MOCK_SEARCH_DURATION_MS);
  const leads = read().leads.filter((lead) => lead.searchId === search.id);
  const highQualityTarget = leads.filter((lead) => lead.score >= 85).length;
  const progress = progressAt(fraction, leads.length, highQualityTarget);

  const status: SearchStatus =
    fraction >= 1
      ? "completed"
      : progress.stage === "scoring" || progress.stage === "deduplicating"
        ? "scoring"
        : progress.stage === "extracting"
          ? "extracting"
          : "searching";

  return {
    ...search,
    status,
    progress,
    completedAt: fraction >= 1 ? new Date().toISOString() : undefined,
    leadCount: fraction >= 1 ? leads.length : progress.qualified,
    highQualityCount: fraction >= 1 ? highQualityTarget : progress.highQuality,
    usage: {
      searchApiCalls: progress.queriesCompleted,
      pagesAnalyzed: progress.profilesProcessed,
      // The mock has no scrape cache, so every page it "analyzed" it also read.
      pagesRead: progress.profilesProcessed,
      pagesCached: 0,
      pagesSkipped: 0,
      scrapeCredits: progress.profilesProcessed * 10,
      llmCalls: Math.round(progress.profilesProcessed * 1.4),
      estimatedCostEur: Number((progress.profilesProcessed * 0.0142).toFixed(2)),
    },
  };
}

export function findSearch(id: string): Search | undefined {
  const search = allSearches().find((entry) => entry.id === id);
  return search ? projectSearch(search) : undefined;
}

export function cancelSearch(id: string): Search {
  const state = read();
  const index = state.searches.findIndex((entry) => entry.id === id);
  if (index === -1) throw new Error(`Search ${id} cannot be cancelled`);
  const projected = projectSearch(state.searches[index]);
  const cancelled: Search = {
    ...projected,
    status: "cancelled",
    completedAt: new Date().toISOString(),
  };
  const searches = [...state.searches];
  searches[index] = cancelled;
  write({ ...state, searches });
  return cancelled;
}

/**
 * "Runs" a search: clones a plausible result set out of the fixture pool,
 * re-scoring every candidate against the weights the user actually chose, so
 * the wizard's criteria visibly change the outcome.
 */
export function createSearch(input: CreateSearchInput): Search {
  const state = read();
  const id = `srch_local_${Date.now().toString(36)}`;
  const now = new Date().toISOString();
  const targetCountry = input.criteria.location.country?.trim().toLowerCase();

  const random = seededRandom(hashString(id + input.name));
  const matching = targetCountry
    ? MOCK_LEADS.filter((lead) => lead.location?.country?.toLowerCase() === targetCountry)
    : [];
  const basePool = matching.length >= 6 ? matching : MOCK_LEADS;
  const shuffled = [...basePool].sort(() => random() - 0.5);
  const take = Math.min(shuffled.length, 14 + Math.floor(random() * 6));

  const leads: Lead[] = shuffled.slice(0, take).map((source, index) => {
    const signals = retargetSignals(source.signals, source.location?.country, input.criteria.location.country);
    const { score, breakdown } = computeScore(signals, input.criteria.signalWeights);
    return {
      ...source,
      id: `${id}__${source.id}`,
      searchId: id,
      searchName: input.name,
      signals,
      score,
      scoreBreakdown: breakdown,
      status: "new",
      saved: false,
      archived: false,
      notes: [],
      createdAt: new Date(Date.now() - index * 1000).toISOString(),
      updatedAt: undefined,
    };
  });

  const search: Search = {
    id,
    name: input.name,
    status: "queued",
    createdAt: now,
    startedAt: now,
    target: criteriaTarget(input.criteria),
    country: input.criteria.location.country,
    sources: input.criteria.sources,
    criteria: input.criteria,
    leadCount: 0,
    highQualityCount: 0,
    progress: progressAt(0, leads.length, leads.filter((lead) => lead.score >= 85).length),
    usage: {
      searchApiCalls: 0,
      pagesAnalyzed: 0,
      pagesRead: 0,
      pagesCached: 0,
      pagesSkipped: 0,
      scrapeCredits: 0,
      llmCalls: 0,
      estimatedCostEur: 0,
    },
    queries: generateQueryPreview(input.criteria, 12).map((query, index) => ({
      id: `q_${index + 1}`,
      query,
      provider: "mock",
      resultCount: 8 + Math.floor(random() * 26),
    })),
  };

  write({
    ...state,
    searches: [search, ...state.searches],
    leads: [...state.leads, ...leads],
  });

  return search;
}

/** Geographic match is criteria-relative, so re-derive it per search. */
function retargetSignals(
  signals: LeadSignal[],
  leadCountry?: string,
  targetCountry?: string,
): LeadSignal[] {
  if (!targetCountry) return signals;
  const matches = leadCountry?.toLowerCase() === targetCountry.trim().toLowerCase();
  return signals.map((signal) => {
    if (signal.type !== "location") return signal;
    if (matches) return signal;
    return {
      ...signal,
      detected: false,
      confidence: 0.15,
      evidence: `Profile location ${leadCountry ?? "unknown"} does not match target ${targetCountry}.`,
    };
  });
}
