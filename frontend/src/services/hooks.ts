"use client";

/**
 * Data access for every screen. Components use these hooks only — no component
 * imports a service or a fixture directly, which is what makes the Phase 2
 * swap a configuration change instead of a refactor.
 */

import {
  useMutation,
  useQuery,
  useQueryClient,
  type UseQueryOptions,
} from "@tanstack/react-query";
import { isSearchRunning } from "@/lib/domain";
import { services } from "@/services";
import type {
  CreateSearchInput,
  Lead,
  LeadFilters,
  OutreachRequest,
  Paginated,
  Search,
  SearchSummary,
  UpdateLeadInput,
} from "@/services/types";

export const queryKeys = {
  health: ["health"] as const,
  sources: ["sources"] as const,
  dashboard: ["dashboard"] as const,
  searches: ["searches"] as const,
  search: (id: string) => ["search", id] as const,
  searchLeads: (id: string, filters?: LeadFilters) => ["search", id, "leads", filters ?? {}] as const,
  leads: (filters?: LeadFilters) => ["leads", filters ?? {}] as const,
  lead: (id: string) => ["lead", id] as const,
  facets: ["leads", "facets"] as const,
};

/**
 * Liveness of whatever is answering. In API mode this is the difference between
 * "no leads yet" and "the backend is not running", which the UI has to be able
 * to tell the user.
 */
export function useBackendHealth() {
  return useQuery({
    queryKey: queryKeys.health,
    queryFn: () => services.workspace.health(),
    refetchInterval: 20_000,
    staleTime: 10_000,
    retry: false,
  });
}

/**
 * Which sources the backend has managed to read. Not polled: it changes when a
 * search runs, not by the second.
 */
export function useSourceReport() {
  return useQuery({
    queryKey: queryKeys.sources,
    queryFn: () => services.workspace.sources(),
    staleTime: 60_000,
    retry: false,
  });
}

export function useResetWorkspace() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => services.workspace.reset(),
    onSuccess: () => queryClient.clear(),
  });
}

export function useDashboard() {
  return useQuery({
    queryKey: queryKeys.dashboard,
    queryFn: () => services.dashboard.get(),
  });
}

export function useSearches() {
  return useQuery<SearchSummary[]>({
    queryKey: queryKeys.searches,
    queryFn: () => services.searches.list(),
    // A running search keeps the history list moving.
    refetchInterval: (query) =>
      query.state.data?.some((search) => isSearchRunning(search.status)) ? 2500 : false,
  });
}

/**
 * Polls while the search is running (spec §43: 2–3s). Identical behaviour
 * against the mock service and the real backend.
 */
export function useSearch(id: string, options?: Partial<UseQueryOptions<Search>>) {
  return useQuery<Search>({
    queryKey: queryKeys.search(id),
    queryFn: () => services.searches.get(id),
    refetchInterval: (query) =>
      query.state.data && isSearchRunning(query.state.data.status) ? 700 : false,
    staleTime: 0,
    ...options,
  });
}

export function useSearchLeads(id: string, filters: LeadFilters = {}, enabled = true) {
  return useQuery<Paginated<Lead>>({
    queryKey: queryKeys.searchLeads(id, filters),
    queryFn: () => services.searches.leads(id, filters),
    enabled,
  });
}

export function useLeads(filters: LeadFilters = {}) {
  return useQuery<Paginated<Lead>>({
    queryKey: queryKeys.leads(filters),
    queryFn: () => services.leads.list(filters),
  });
}

export function useLead(id: string) {
  return useQuery<Lead>({
    queryKey: queryKeys.lead(id),
    queryFn: () => services.leads.get(id),
  });
}

export function useLeadFacets() {
  return useQuery({
    queryKey: queryKeys.facets,
    queryFn: () => services.leads.facets(),
    staleTime: 5 * 60_000,
  });
}

export function useCreateSearch() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: CreateSearchInput) => services.searches.create(input),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.searches });
      queryClient.invalidateQueries({ queryKey: queryKeys.dashboard });
    },
  });
}

export function useCancelSearch() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => services.searches.cancel(id),
    onSuccess: (search) => {
      queryClient.setQueryData(queryKeys.search(search.id), search);
      queryClient.invalidateQueries({ queryKey: queryKeys.searches });
    },
  });
}

export function useUpdateLead() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, input }: { id: string; input: UpdateLeadInput }) =>
      services.leads.update(id, input),
    onSuccess: (lead) => {
      queryClient.setQueryData(queryKeys.lead(lead.id), lead);
      invalidateLeadCollections(queryClient);
    },
  });
}

export function useAddLeadNote() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, body }: { id: string; body: string }) => services.leads.addNote(id, body),
    onSuccess: (lead) => {
      queryClient.setQueryData(queryKeys.lead(lead.id), lead);
      invalidateLeadCollections(queryClient);
    },
  });
}

export function useGenerateOutreach(leadId: string) {
  return useMutation({
    mutationFn: (request: OutreachRequest) => services.leads.generateOutreach(leadId, request),
  });
}

function invalidateLeadCollections(queryClient: ReturnType<typeof useQueryClient>) {
  queryClient.invalidateQueries({ queryKey: ["leads"] });
  queryClient.invalidateQueries({ queryKey: ["search"] });
  queryClient.invalidateQueries({ queryKey: queryKeys.dashboard });
}
