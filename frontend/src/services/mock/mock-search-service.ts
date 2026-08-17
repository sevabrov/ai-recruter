import type {
  CreateSearchInput,
  CreateSearchResponse,
  Lead,
  LeadFilters,
  Paginated,
  Search,
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
import { filterLeads, paginate } from "./mock-lead-service";

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
