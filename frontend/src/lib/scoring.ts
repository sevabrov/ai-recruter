/**
 * SCORING ENGINE (spec §37–38)
 * ============================
 * Deterministic and explainable: a judge decides whether each requirement is
 * met, this function turns that into points. It lives in `lib` rather than
 * `mocks` because the same rule is mirrored by the backend — the front end only
 * ever renders the breakdown it receives, but the mock phase needs the identical
 * arithmetic.
 */

import { SCORED_SIGNALS } from "@/lib/domain";
import type {
  LeadSignal,
  Requirement,
  ScoreComponent,
  ScoredSignalType,
} from "@/services/types";

export function computeScore(
  signals: LeadSignal[],
  requirements: Requirement[] | Record<ScoredSignalType, number>,
): { score: number; breakdown: ScoreComponent[] } {
  // A bare `{signal: points}` map is how a search was scored before requirements
  // existed: every built-in signal, a zero-point one included.
  const legacy = !Array.isArray(requirements);
  const list: Requirement[] = Array.isArray(requirements)
    ? requirements
    : SCORED_SIGNALS.map((id) => ({ id, weight: requirements[id] ?? 0, importance: "normal" }));

  const breakdown: ScoreComponent[] = list
    .filter((requirement) => legacy || requirement.weight > 0)
    .map((requirement) => {
      const signal = signals.find((entry) => entry.type === requirement.id);
      const awarded = signal?.detected ? Math.round(requirement.weight * signal.confidence) : 0;
      return {
        type: requirement.id,
        label: requirement.label || undefined,
        awarded,
        max: requirement.weight,
      };
    });

  return {
    score: breakdown.reduce((total, component) => total + component.awarded, 0),
    breakdown,
  };
}

export function totalWeight(requirements: Requirement[]) {
  return requirements.reduce((total, requirement) => total + requirement.weight, 0);
}
