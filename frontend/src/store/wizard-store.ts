"use client";

/**
 * New-search draft state (Zustand, persisted to sessionStorage so a refresh
 * mid-flow doesn't lose the client's input).
 *
 * Two steps. The client describes the search in their own words; the backend
 * reads that into criteria; the client checks what was understood and answers
 * what was not. The five-step form this replaced asked for twenty-odd fields, most
 * of which nobody could say the effect of - and the three that matter (brands,
 * country, who to exclude) looked no more important than the rest.
 */

import { create } from "zustand";
import { persist, createJSONStorage } from "zustand/middleware";
import {
  balanceRequirements,
  DEFAULT_SIGNAL_WEIGHTS,
  DEFAULT_TARGET_LEADS,
  effectiveRequirements,
  emptyCriteria,
  isPresetSignal,
  LANGUAGES,
  MAX_REQUIREMENTS,
  vocabularyEntry,
} from "@/lib/domain";
import type {
  GeoLocation,
  ParsedBrief,
  Requirement,
  RequirementImportance,
  SearchCriteria,
  SourceKind,
} from "@/services/types";

/** Describe, then review. Labels are `wizard.steps.<id>.label` / `.title`. */
export const WIZARD_STEPS = [1, 2] as const;

export type WizardStepId = (typeof WIZARD_STEPS)[number];


type WizardState = {
  step: WizardStepId;
  /** The client's own description, as typed. */
  brief: string;
  name: string;
  criteria: SearchCriteria;
  /** Which reader answered the last parse - "rules" means no model did. */
  parser: string | null;
  /**
   * The text the current criteria were read from. While the brief still says
   * that, going forward again is a step, not another (billed) parse.
   */
  parsedFrom: string | null;
  /**
   * The client chose "anywhere" on purpose. An empty country is otherwise a
   * question the review screen asks, because it silently disables every query in
   * a language other than English.
   */
  worldwide: boolean;
  /**
   * The draft was loaded from an existing search ("Refine and re-run"), not
   * typed. Leaving it unstarted asks first and then drops it - otherwise the
   * next "New search" opens on that old search instead of an empty form.
   */
  refining: boolean;
  setStep:(step: WizardStepId) => void;
  setBrief: (brief: string) => void;
  setName: (name: string) => void;
  setWorldwide: (worldwide: boolean) => void;
  applyParsed: (parsed: ParsedBrief) => void;
  patchCriteria: (patch: Partial<SearchCriteria>) => void;
  /**
   * Where to look: countries (most important first) and a region. One country
   * alone is stored as the single `location.country` the backend has always read.
   */
  setPlaces: (countries: string[], region: string) => void;
  toggleSource: (source: SourceKind) => void;
  /** Requirements: every change re-shares the 100 points by importance. */
  setRequirementImportance: (id: string, importance: RequirementImportance) => void;
  renameRequirement: (id: string, label: string) => void;
  addRequirement: (label: string) => void;
  removeRequirement: (id: string) => void;
  /** Start again from an existing search: its description and its criteria. */
  loadSearch: (name: string, criteria: SearchCriteria) => void;
  reset: () => void;
};

export const useWizardStore = create<WizardState>()(
  persist(
    (set) => ({
      step: 1,
      brief: "",
      name: "",
      criteria: emptyCriteria(),
      parser: null,
      parsedFrom: null,
      worldwide: false,
      refining: false,

      setStep:(step) => set({ step }),
      setBrief: (brief) => set({ brief }),
      setName: (name) => set({ name }),
      setWorldwide: (worldwide) => set({ worldwide }),

      applyParsed: (parsed) =>
        set((state) => ({
          step: 2,
          name: parsed.name || state.name,
          parser: parsed.parser,
          parsedFrom: state.brief,
          worldwide: false,
          criteria: {
            ...emptyCriteria(),
            ...parsed.criteria,
            location: withoutCity(parsed.criteria.location),
            brief: state.brief,
            // Weights are not something a brief talks about; the defaults stand.
            signalWeights: { ...DEFAULT_SIGNAL_WEIGHTS },
            targetLeads: parsed.criteria.targetLeads || DEFAULT_TARGET_LEADS,
          },
        })),

      patchCriteria: (patch) =>
        set((state) => ({ criteria: { ...state.criteria, ...patch } })),

      setPlaces: (countries, region) =>
        set((state) => {
          const single = countries.length === 1 && !region;
          return {
            worldwide: !countries.length && !region,
            criteria: {
              ...state.criteria,
              countries: single ? [] : countries,
              region,
              location: {
                ...withoutCity(state.criteria.location),
                country: single ? countries[0] : undefined,
              },
            },
          };
        }),

      toggleSource: (source) =>
        set((state) => ({
          criteria: { ...state.criteria, sources: toggle(state.criteria.sources, source) },
        })),

      setRequirementImportance: (id, importance) =>
        set((state) => withRequirements(state.criteria, (list) =>
          list.map((requirement) =>
            requirement.id === id ? { ...requirement, importance } : requirement,
          ),
        )),

      renameRequirement: (id, label) =>
        set((state) => withRequirements(state.criteria, (list) =>
          list.map((requirement) =>
            requirement.id === id
              ? // A renamed requirement is looked for by its new name, not the old words.
                { ...requirement, label, terms: isPresetSignal(id) ? requirement.terms : [label] }
              : requirement,
          ),
        )),

      addRequirement: (label) =>
        set((state) => withRequirements(state.criteria, (list) => {
          const name = label.trim();
          if (!name || list.length >= MAX_REQUIREMENTS) return list;
          if (list.some((entry) => (entry.label ?? "").toLowerCase() === name.toLowerCase())) {
            return list;
          }
          return [...list, { id: nextRequirementId(list), label: name, terms: [name], importance: "high", weight: 0 }];
        })),

      removeRequirement: (id) =>
        set((state) => withRequirements(state.criteria, (list) =>
          list.filter((requirement) => requirement.id !== id),
        )),

      loadSearch: (name, criteria) =>
        set({
          step: 2,
          name,
          brief: criteria.brief ?? "",
          parser: null,
          parsedFrom: criteria.brief ?? "",
          worldwide: !criteria.location.country,
          refining: true,
          // An older search is edited as requirements from the start.
          criteria: {
            ...emptyCriteria(),
            ...criteria,
            location: withoutCity(criteria.location),
            requirements: effectiveRequirements(criteria),
          },
        }),

      reset: () =>
        set({
          step: 1,
          brief: "",
          name: "",
          criteria: emptyCriteria(),
          parser: null,
          parsedFrom: null,
          worldwide: false,
          refining: false,
        }),
    }),
    {
      // v2: the five-step draft shape is not this one.
      name: "air.wizard.draft.v2",
      storage: createJSONStorage(() => sessionStorage),
    },
  ),
);

/** Apply a change to the requirements and share the points out again. */
function withRequirements(
  criteria: SearchCriteria,
  change: (list: Requirement[]) => Requirement[],
): { criteria: SearchCriteria } {
  const next = change(effectiveRequirements(criteria));
  return { criteria: { ...criteria, requirements: balanceRequirements(next) } };
}

function nextRequirementId(list: Requirement[]): string {
  const taken = new Set(list.map((requirement) => requirement.id));
  let index = list.length + 1;
  while (taken.has(`r${index}`)) index += 1;
  return `r${index}`;
}

function toggle<T>(list: T[], value: T): T[] {
  return list.includes(value) ? list.filter((entry) => entry !== value) : [...list, value];
}

/**
 * Searches are by country only. A city the brief named, or one an older search
 * carried, is dropped here - with no field to show it, it would narrow every
 * query without the client ever seeing why.
 */
function withoutCity(location: GeoLocation = {}): GeoLocation {
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  const { city, ...rest } = location;
  return rest;
}

/**
 * What the review screen has to ask about. Decided here, by rules, not by the
 * model - the questions are fixed copy in the interface language, so they read
 * the same every time and cannot be phrased into something misleading.
 *
 * Each gap is one a measured run paid for:
 *
 * * `terms` (blocks the start) - no brand and no self-description: the queries
 *   fall back to the niche's generic name and come back with its famous accounts.
 * * `brands` - words, but no brand: it runs, and finds fewer of the right people.
 * * `requirements` - nothing to judge candidates by, so every lead scores alike.
 * * `sources` (blocks the start) - nowhere to look.
 * * `country` - without one, no query is written in any language but English.
 * * `languages` - the country is known but not who in it to look for; a diaspora
 *   (Ukrainians in Spain) writes in a different language from the country.
 */
export type WizardGap =
  | "terms"
  | "brands"
  | "requirements"
  | "sources"
  | "country"
  | "languages";

export const BLOCKING_GAPS: WizardGap[] = ["terms", "sources"];

export function criteriaGaps(
  state: { criteria: SearchCriteria; worldwide: boolean },
): WizardGap[] {
  const { criteria } = state;
  const gaps: WizardGap[] = [];
  const brands = (criteria.brands ?? []).length;
  if (!brands && !criteria.keywords.length) gaps.push("terms");
  // Self-descriptions alone do run, so this one only asks. But a brand is the
  // query that reached the people a client actually meant, and a model reading a
  // vague brief fills in "мережевий маркетинг" rather than leaving it empty.
  else if (!brands) gaps.push("brands");
  // Nothing to judge a candidate by but the country: every lead would score alike.
  const judged = effectiveRequirements(criteria).filter(
    (requirement) => requirement.id !== "location" && requirement.weight > 0,
  );
  if (!judged.length) gaps.push("requirements");
  if (!criteria.sources.length) gaps.push("sources");
  const placed =
    Boolean(criteria.location.country) ||
    Boolean(criteria.countries?.length) ||
    Boolean(criteria.region);
  if (!placed && !state.worldwide) gaps.push("country");
  const knownLanguages = criteria.languages.filter((name) => vocabularyEntry(LANGUAGES, name));
  if (!knownLanguages.length) gaps.push("languages");
  return gaps;
}
