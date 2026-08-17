/**
 * MOCK SEARCH TIMELINE
 * ====================
 * Drives /search/:id/progress. The mock service derives progress from elapsed
 * wall-clock time, exactly as the real backend will derive it from worker state
 * — so the polling UI needs no change when Phase 7 lands.
 */

import type { SearchProgress, SearchStage } from "@/services/types";

/** Total simulated runtime (spec §13: seconds, not minutes). */
export const MOCK_SEARCH_DURATION_MS = 9_000;

type StageStep = {
  stage: SearchStage;
  /** Fraction of total runtime at which this stage completes. */
  until: number;
  note: string;
};

export const MOCK_STAGE_TIMELINE: StageStep[] = [
  { stage: "generating_queries", until: 0.12, note: "Generating search queries from your criteria" },
  { stage: "web_search", until: 0.34, note: "Searching the public web" },
  { stage: "discovering_profiles", until: 0.5, note: "Identifying candidate profiles" },
  { stage: "extracting", until: 0.78, note: "Extracting structured profiles" },
  { stage: "scoring", until: 0.92, note: "Detecting signals and calculating AI scores" },
  { stage: "deduplicating", until: 1, note: "Merging duplicate people across platforms" },
];

/** Counter targets reached at 100%. */
export const MOCK_PROGRESS_TARGETS = {
  queries: 14,
  urlsDiscovered: 187,
  profilesDiscovered: 126,
  profilesProcessed: 126,
} as const;

function ramp(fraction: number, from: number, to: number, target: number) {
  if (fraction <= from) return 0;
  const local = Math.min(1, (fraction - from) / (to - from));
  return Math.round(target * local);
}

export function progressAt(fraction: number, qualifiedTarget: number, highQualityTarget: number): SearchProgress {
  const clamped = Math.max(0, Math.min(1, fraction));
  const stage =
    MOCK_STAGE_TIMELINE.find((step) => clamped < step.until)?.stage ?? "done";

  const queriesCompleted = ramp(clamped, 0, 0.12, MOCK_PROGRESS_TARGETS.queries);
  const urlsDiscovered = ramp(clamped, 0.1, 0.34, MOCK_PROGRESS_TARGETS.urlsDiscovered);
  const profilesDiscovered = ramp(clamped, 0.3, 0.5, MOCK_PROGRESS_TARGETS.profilesDiscovered);
  const profilesProcessed = ramp(clamped, 0.5, 0.78, MOCK_PROGRESS_TARGETS.profilesProcessed);
  const qualified = ramp(clamped, 0.55, 0.95, qualifiedTarget);
  const highQuality = ramp(clamped, 0.6, 1, highQualityTarget);

  return {
    queries: MOCK_PROGRESS_TARGETS.queries,
    queriesCompleted,
    urlsDiscovered,
    profilesDiscovered,
    profilesProcessed,
    qualified,
    highQuality,
    percent: Math.round(clamped * 100),
    stage,
  };
}

export function stageNote(stage: SearchStage) {
  return (
    MOCK_STAGE_TIMELINE.find((step) => step.stage === stage)?.note ??
    "Search complete"
  );
}
