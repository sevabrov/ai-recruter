/**
 * PHASE 2 TARGET IMPLEMENTATION
 * =============================
 * These classes already speak the endpoints from spec §57. They are wired into
 * the registry but inactive until NEXT_PUBLIC_DATA_SOURCE=api, so the UI can be
 * switched over without touching a single component.
 */

import type {
  CreateSearchInput,
  CreateSearchResponse,
  DashboardData,
  DashboardService,
  Lead,
  LeadFilters,
  LeadService,
  OutreachMessage,
  OutreachRequest,
  Paginated,
  Platform,
  Search,
  SearchService,
  SearchSummary,
  UpdateLeadInput,
} from "@/services/types";
import { request } from "./http";

function leadQuery(filters: LeadFilters = {}) {
  return {
    search_id: filters.searchId,
    q: filters.query,
    min_score: filters.minScore,
    country: filters.countries,
    platform: filters.platforms,
    signal: filters.signals,
    status: filters.statuses,
    has_email: filters.hasEmail,
    has_social: filters.hasSocial,
    saved: filters.savedOnly,
    include_archived: filters.includeArchived,
    sort: filters.sort,
    page: filters.page,
    page_size: filters.pageSize,
  };
}

export class ApiSearchService implements SearchService {
  list() {
    return request<SearchSummary[]>("/searches");
  }

  get(id: string) {
    return request<Search>(`/searches/${id}`);
  }

  create(input: CreateSearchInput) {
    return request<CreateSearchResponse>("/searches", { method: "POST", body: input });
  }

  cancel(id: string) {
    return request<Search>(`/searches/${id}/cancel`, { method: "POST" });
  }

  leads(id: string, filters: LeadFilters = {}) {
    return request<Paginated<Lead>>(`/searches/${id}/leads`, { query: leadQuery(filters) });
  }
}

export class ApiLeadService implements LeadService {
  list(filters: LeadFilters = {}) {
    return request<Paginated<Lead>>("/leads", { query: leadQuery(filters) });
  }

  get(id: string) {
    return request<Lead>(`/leads/${id}`);
  }

  update(id: string, input: UpdateLeadInput) {
    return request<Lead>(`/leads/${id}`, { method: "PATCH", body: input });
  }

  addNote(id: string, body: string) {
    return request<Lead>(`/leads/${id}/notes`, { method: "POST", body: { body } });
  }

  generateOutreach(id: string, requestBody: OutreachRequest) {
    return request<OutreachMessage>(`/leads/${id}/outreach`, {
      method: "POST",
      body: requestBody,
    });
  }

  facets() {
    return request<{ countries: string[]; platforms: Platform[] }>("/leads/facets");
  }
}

export class ApiDashboardService implements DashboardService {
  get() {
    return request<DashboardData>("/dashboard");
  }
}
