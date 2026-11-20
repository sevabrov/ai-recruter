"use client";

/**
 * New-search draft state (Zustand, persisted to sessionStorage so a refresh
 * mid-flow doesn't lose the client's input).
 *
 * Two steps. The client describes the search in their own words; the backend
 * reads that into criteria; the client checks what was understood and answers
 * what was not. The five-step form this replaced asked for twenty-odd fields, most
 * of which nobody could say the effect of — and the three that matter (brands,
 * country, who to exclude) looked no more important than the rest.
 */

import { create } from "zustand";
import { persist, createJSONStorage } from "zustand/middleware";
import {
  DEFAULT_SIGNAL_WEIGHTS,
  DEFAULT_TARGET_LEADS,
  emptyCriteria,
  LANGUAGES,
  vocabularyEntry,
} from "@/lib/domain";
import type {
  ParsedBrief,
  ScoredSignalType,
  SearchCriteria,
  SignalType,
  SourceKind,
} from "@/services/types";

/** Describe, then review. Labels are `wizard.steps.<id>.label` / `.title`. */
export const WIZARD_STEPS = [1, 2] as const;

export type WizardStepId = (typeof WIZARD_STEPS)[number];

/** How much a signal matters to this search, as one choice instead of two lists. */
export type SignalImportance = "required" | "preferred" | "ignored";

type WizardState = {
  step: WizardStepId;
  /** The client's own description, as typed. */
  brief: string;
  name: string;
  criteria: SearchCriteria;
  /** Which reader answered the last parse — "rules" means no model did. */
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
  setStep: (step: WizardStepId) => void;
  setBrief: (brief: string) => void;
  setName: (name: string) => void;
  setWorldwide: (worldwide: boolean) => void;
  applyParsed: (parsed: ParsedBrief) => void;
  patchCriteria: (patch: Partial<SearchCriteria>) => void;
  setLocation: (patch: Partial<SearchCriteria["location"]>) => void;
  toggleSource: (source: SourceKind) => void;
  setImportance: (signal: SignalType, importance: SignalImportance) => void;
  setWeight: (signal: ScoredSignalType, points: number) => void;
  resetWeights: () => void;
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

      setStep: (step) => set({ step }),
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
            brief: state.brief,
            // Weights are not something a brief talks about; the defaults stand.
            signalWeights: { ...DEFAULT_SIGNAL_WEIGHTS },
            targetLeads: parsed.criteria.targetLeads || DEFAULT_TARGET_LEADS,
          },
        })),

      patchCriteria: (patch) =>
        set((state) => ({ criteria: { ...state.criteria, ...patch } })),
      setLocation: (patch) =>
        set((state) => ({
          criteria: { ...state.criteria, location: { ...state.criteria.location, ...patch } },
          worldwide: patch.country ? false : state.worldwide,
        })),

      toggleSource: (source) =>
        set((state) => ({
          criteria: { ...state.criteria, sources: toggle(state.criteria.sources, source) },
        })),

      setImportance: (signal, importance) =>
        set((state) => {
          const mustHave = state.criteria.mustHave.filter((entry) => entry !== signal);
          const niceToHave = state.criteria.niceToHave.filter((entry) => entry !== signal);
          if (importance === "required") mustHave.push(signal);
          if (importance === "preferred") niceToHave.push(signal);
          return { criteria: { ...state.criteria, mustHave, niceToHave } };
        }),

      setWeight: (signal, points) =>
        set((state) => ({
          criteria: {
            ...state.criteria,
            signalWeights: { ...state.criteria.signalWeights, [signal]: points },
          },
        })),

      resetWeights: () =>
        set((state) => ({
          criteria: { ...state.criteria, signalWeights: { ...DEFAULT_SIGNAL_WEIGHTS } },
        })),

      loadSearch: (name, criteria) =>
        set({
          step: 2,
          name,
          brief: criteria.brief ?? "",
          parser: null,
          parsedFrom: criteria.brief ?? "",
          worldwide: !criteria.location.country,
          criteria: { ...emptyCriteria(), ...criteria },
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
        }),
    }),
    {
      // v2: the five-step draft shape is not this one.
      name: "air.wizard.draft.v2",
      storage: createJSONStorage(() => sessionStorage),
    },
  ),
);

function toggle<T>(list: T[], value: T): T[] {
  return list.includes(value) ? list.filter((entry) => entry !== value) : [...list, value];
}

export function importanceOf(criteria: SearchCriteria, signal: SignalType): SignalImportance {
  if (criteria.mustHave.includes(signal)) return "required";
  if (criteria.niceToHave.includes(signal)) return "preferred";
  return "ignored";
}

/**
 * What the review screen has to ask about. Decided here, by rules, not by the
 * model — the questions are fixed copy in the interface language, so they read
 * the same every time and cannot be phrased into something misleading.
 *
 * Each gap is one a measured run paid for:
 *
 * * `terms` (blocks the start) — no brand and no self-description: the queries
 *   fall back to the niche's generic name and come back with its famous accounts.
 * * `brands` — words, but no brand: it runs, and finds fewer of the right people.
 * * `sources` (blocks the start) — nowhere to look.
 * * `country` — without one, no query is written in any language but English.
 * * `languages` — the country is known but not who in it to look for; a diaspora
 *   (Ukrainians in Spain) writes in a different language from the country.
 */
export type WizardGap = "terms" | "brands" | "sources" | "country" | "languages";

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
  if (!criteria.sources.length) gaps.push("sources");
  if (!criteria.location.country && !state.worldwide) gaps.push("country");
  const knownLanguages = criteria.languages.filter((name) => vocabularyEntry(LANGUAGES, name));
  if (!knownLanguages.length) gaps.push("languages");
  return gaps;
}
