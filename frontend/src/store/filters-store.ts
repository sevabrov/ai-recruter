"use client";

/**
 * Lead filter state, kept in Zustand so a user can move between a search's
 * results and the saved-leads list without losing their filters. Scoped by key
 * ("results" / "leads") because the two screens filter independently.
 */

import { create } from "zustand";
import type { LeadFilters, LeadSort, LeadStatus, Platform, SignalType } from "@/services/types";

export type FilterScope = "results" | "leads";

const DEFAULTS: LeadFilters = {
  query: "",
  minScore: 0,
  countries: [],
  platforms: [],
  signals: [],
  statuses: [],
  hasEmail: false,
  hasSocial: false,
  sort: "score_desc",
};

type FiltersState = {
  scopes: Record<FilterScope, LeadFilters>;
  patch: (scope: FilterScope, patch: Partial<LeadFilters>) => void;
  toggleIn: <K extends "countries" | "platforms" | "signals" | "statuses">(
    scope: FilterScope,
    key: K,
    value: NonNullable<LeadFilters[K]>[number],
  ) => void;
  clear: (scope: FilterScope) => void;
};

export const useFiltersStore = create<FiltersState>((set) => ({
  scopes: {
    results: { ...DEFAULTS },
    leads: { ...DEFAULTS },
  },

  patch: (scope, patch) =>
    set((state) => ({
      scopes: { ...state.scopes, [scope]: { ...state.scopes[scope], ...patch } },
    })),

  toggleIn: (scope, key, value) =>
    set((state) => {
      const current = (state.scopes[scope][key] ?? []) as typeof value[];
      const next = current.includes(value)
        ? current.filter((entry) => entry !== value)
        : [...current, value];
      return {
        scopes: { ...state.scopes, [scope]: { ...state.scopes[scope], [key]: next } },
      };
    }),

  clear: (scope) =>
    set((state) => ({ scopes: { ...state.scopes, [scope]: { ...DEFAULTS } } })),
}));

export function activeFilterCount(filters: LeadFilters) {
  let count = 0;
  if (filters.query) count++;
  if (filters.minScore) count++;
  count += filters.countries?.length ?? 0;
  count += filters.platforms?.length ?? 0;
  count += filters.signals?.length ?? 0;
  count += filters.statuses?.length ?? 0;
  if (filters.hasEmail) count++;
  if (filters.hasSocial) count++;
  return count;
}

/** Offered orderings; each one's wording is `domain.sort.<id>`. */
export const SORT_OPTIONS: LeadSort[] = ["score_desc", "newest", "name_asc"];

export type { LeadStatus, Platform, SignalType };
