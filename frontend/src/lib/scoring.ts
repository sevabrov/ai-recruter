/**
 * SCORING ENGINE (spec §37–38)
 * ============================
 * Deterministic and explainable: the LLM detects signals, this function turns
 * them into points. It lives in `lib` rather than `mocks` because the same rule
 * is mirrored by the backend — the front end only ever renders the breakdown it
 * receives, but the mock phase needs the identical arithmetic.
 */

import { SCORED_SIGNALS } from "@/lib/domain";
import type {
  LeadSignal,
  ScoreComponent,
  ScoredSignalType,
} from "@/services/types";

export function computeScore(
  signals: LeadSignal[],
  weights: Record<ScoredSignalType, number>,
): { score: number; breakdown: ScoreComponent[] } {
  const breakdown: ScoreComponent[] = SCORED_SIGNALS.map((type) => {
    const signal = signals.find((entry) => entry.type === type);
    const max = weights[type] ?? 0;
    const awarded = signal?.detected ? Math.round(max * signal.confidence) : 0;
    return { type, awarded, max };
  });

  return {
    score: breakdown.reduce((total, component) => total + component.awarded, 0),
    breakdown,
  };
}

export function totalWeight(weights: Record<ScoredSignalType, number>) {
  return SCORED_SIGNALS.reduce((total, type) => total + (weights[type] ?? 0), 0);
}
