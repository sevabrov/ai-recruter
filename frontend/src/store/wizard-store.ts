"use client";

/**
 * New-search wizard draft state (Zustand, persisted to sessionStorage so a
 * refresh mid-wizard doesn't lose the client's input).
 */

import { create } from "zustand";
import { persist, createJSONStorage } from "zustand/middleware";
import { DEFAULT_SIGNAL_WEIGHTS, emptyCriteria } from "@/lib/domain";
import type { ScoredSignalType, SearchCriteria, SignalType, SourceKind } from "@/services/types";

export const WIZARD_STEPS = [
  { id: 1, label: "Who", title: "Who are we looking for?" },
  { id: 2, label: "Where", title: "Geography" },
  { id: 3, label: "Signals", title: "Candidate criteria" },
  { id: 4, label: "Sources", title: "Where to look" },
  { id: 5, label: "Review", title: "Search preview" },
] as const;

export type WizardStepId = (typeof WIZARD_STEPS)[number]["id"];

type WizardState = {
  step: WizardStepId;
  name: string;
  criteria: SearchCriteria;
  setStep: (step: WizardStepId) => void;
  next: () => void;
  back: () => void;
  setName: (name: string) => void;
  patchCriteria: (patch: Partial<SearchCriteria>) => void;
  setLocation: (patch: Partial<SearchCriteria["location"]>) => void;
  toggleSource: (source: SourceKind) => void;
  toggleMustHave: (signal: SignalType) => void;
  toggleNiceToHave: (signal: SignalType) => void;
  setWeight: (signal: ScoredSignalType, points: number) => void;
  resetWeights: () => void;
  reset: () => void;
  loadExample: () => void;
};

const EXAMPLE = {
  name: "MIHI Beauty Leaders Spain",
  criteria: {
    industry: ["Beauty", "Cosmetics"],
    businessTypes: ["MLM", "Network marketing"],
    keywords: ["MIHI", "beauty", "network marketing", "team leader", "distributor"],
    negativeKeywords: ["customer", "shop", "beauty salon"],
    location: { country: "Spain", region: "", city: "" },
    languages: ["Spanish", "English", "Russian", "Ukrainian"],
    mustHave: ["mlm", "beauty", "activity"] as SignalType[],
    niceToHave: ["leadership", "recruiting", "personalBrand"] as SignalType[],
    signalWeights: { ...DEFAULT_SIGNAL_WEIGHTS },
    sources: [
      "public_web",
      "instagram_public",
      "linkedin_public",
      "facebook_public",
    ] as SourceKind[],
  },
};

export const useWizardStore = create<WizardState>()(
  persist(
    (set) => ({
      step: 1,
      name: "",
      criteria: emptyCriteria(),

      setStep: (step) => set({ step }),
      next: () =>
        set((state) => ({ step: Math.min(5, state.step + 1) as WizardStepId })),
      back: () => set((state) => ({ step: Math.max(1, state.step - 1) as WizardStepId })),

      setName: (name) => set({ name }),
      patchCriteria: (patch) =>
        set((state) => ({ criteria: { ...state.criteria, ...patch } })),
      setLocation: (patch) =>
        set((state) => ({
          criteria: { ...state.criteria, location: { ...state.criteria.location, ...patch } },
        })),

      toggleSource: (source) =>
        set((state) => ({
          criteria: {
            ...state.criteria,
            sources: toggle(state.criteria.sources, source),
          },
        })),

      toggleMustHave: (signal) =>
        set((state) => ({
          criteria: {
            ...state.criteria,
            mustHave: toggle(state.criteria.mustHave, signal),
            niceToHave: state.criteria.niceToHave.filter((entry) => entry !== signal),
          },
        })),

      toggleNiceToHave: (signal) =>
        set((state) => ({
          criteria: {
            ...state.criteria,
            niceToHave: toggle(state.criteria.niceToHave, signal),
            mustHave: state.criteria.mustHave.filter((entry) => entry !== signal),
          },
        })),

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

      reset: () => set({ step: 1, name: "", criteria: emptyCriteria() }),

      loadExample: () =>
        set({ step: 1, name: EXAMPLE.name, criteria: { ...EXAMPLE.criteria } }),
    }),
    {
      name: "air.wizard.draft",
      storage: createJSONStorage(() => sessionStorage),
    },
  ),
);

function toggle<T>(list: T[], value: T): T[] {
  return list.includes(value) ? list.filter((entry) => entry !== value) : [...list, value];
}

/** Step gating: only the essentials block progress (spec §9: fields are optional). */
export function stepIssues(state: { name: string; criteria: SearchCriteria }, step: WizardStepId) {
  const issues: string[] = [];
  if (step === 1) {
    if (!state.name.trim()) issues.push("Give the search a name");
    if (!state.criteria.keywords.length && !state.criteria.industry.length)
      issues.push("Add at least one keyword or industry");
  }
  if (step === 4 && !state.criteria.sources.length) {
    issues.push("Select at least one source");
  }
  return issues;
}
