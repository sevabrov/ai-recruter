import { generateQueryPreview } from "@/lib/query-preview";
import { rejectedFor } from "@/mocks/rejected";
import type {
  CreateSearchInput,
  CreateSearchResponse,
  Lead,
  LeadFilters,
  Paginated,
  ParseBriefInput,
  ParsedBrief,
  RejectedList,
  RejectionReason,
  Search,
  SearchCriteria,
  SearchEstimate,
  SearchService,
  SearchSummary,
} from "@/services/types";
import {
  allLeads,
  allSearches,
  cancelSearch,
  createSearch,
  findSearch,
  latency,
  projectSearch,
} from "./mock-db";
import { parseBriefOffline } from "./mock-brief-parser";
import { filterLeads, paginate } from "./mock-lead-service";

/** The backend's defaults, mirrored so the demo quotes the same shape of number. */
const MAX_QUERIES = 24;
const MAX_PAGES = 25;
const PAGES_PER_LEAD = 3;
const CREDITS_PER_PAGE = 10;
const COST_PER_CALL = 0.005;
const COST_PER_PAGE = 0.01;

export class MockSearchService implements SearchService {
  async list(): Promise<SearchSummary[]> {
    await latency();
    return allSearches().map(projectSearch).map(toSummary);
  }

  async get(id: string): Promise<Search> {
    await latency(120);
    const search = findSearch(id);
    if (!search) throw new Error(`Search ${id} not found`);
    return search;
  }

  /** The offline twin of `POST /searches/parse`: the rule reader, no model. */
  async parse(input: ParseBriefInput): Promise<ParsedBrief> {
    await latency(400);
    return parseBriefOffline(input.text);
  }

  /**
   * The offline twin of `POST /searches/estimate`. The live backend translates
   * the queries and owns the unit prices; here they are the demo's own constants,
   * which is enough for the wizard to behave identically without a server.
   */
  async estimate(criteria: SearchCriteria): Promise<SearchEstimate> {
    await latency(140);
    const queries = generateQueryPreview(criteria, MAX_QUERIES).map((query) => ({ query }));
    const target = criteria.targetLeads ?? 0;
    const maxPages = target > 0 ? Math.min(MAX_PAGES, target * PAGES_PER_LEAD) : MAX_PAGES;

    return {
      queries,
      searchCalls: queries.length,
      maxPages,
      credits: maxPages * CREDITS_PER_PAGE,
      targetLeads: target,
      pagesPerLead: PAGES_PER_LEAD,
      maxCostEur:
        Math.round((queries.length * COST_PER_CALL + maxPages * COST_PER_PAGE) * 100) / 100,
      expectedCostEur:
        Math.round((queries.length * COST_PER_CALL + maxPages * COST_PER_PAGE) * 100) / 100,
      readsPages: true,
    };
  }

  /** Returns immediately with a queued search — mirrors POST /searches (§39). */
  async create(input: CreateSearchInput): Promise<CreateSearchResponse> {
    await latency(320);
    const search = createSearch(input);
    return { searchId: search.id, status: search.status };
  }

  async cancel(id: string): Promise<Search> {
    await latency(160);
    return cancelSearch(id);
  }

  async leads(id: string, filters: LeadFilters = {}): Promise<Paginated<Lead>> {
    await latency();
    const filtered = filterLeads(allLeads(), { ...filters, searchId: id });
    return paginate(filtered, filters.page ?? 1, filters.pageSize ?? 50);
  }

  /**
   * The other half of the result. Offline there is no web to be refused by, so
   * the spread is generated from the search's own counters — see mocks/rejected.
   */
  async rejected(id: string, reason?: RejectionReason): Promise<RejectedList> {
    await latency();
    const search = findSearch(id);
    if (!search) throw new Error(`Search ${id} not found`);
    const list = rejectedFor(search);
    if (!reason) return list;
    return { ...list, items: list.items.filter((entry) => entry.reason === reason) };
  }
}

function toSummary(search: Search): SearchSummary {
  const {
    id,
    name,
    status,
    createdAt,
    startedAt,
    completedAt,
    leadCount,
    highQualityCount,
    target,
    country,
    sources,
  } = search;
  return {
    id,
    name,
    status,
    createdAt,
    startedAt,
    completedAt,
    leadCount,
    highQualityCount,
    target,
    country,
    sources,
  };
}
