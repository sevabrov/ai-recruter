"use client";

import { Terminal } from "lucide-react";
import { SCORED_SIGNALS, SIGNAL_LABELS, SOURCE_KINDS } from "@/lib/domain";
import { generateQueryPreview } from "@/lib/query-preview";
import { useWizardStore } from "@/store/wizard-store";
import { Badge } from "@/components/ui/badge";
import { Eyebrow } from "@/components/ui/misc";
import type { ReactNode } from "react";

export function StepReview() {
  const { name, criteria } = useWizardStore();
  const queries = generateQueryPreview(criteria, 8);
  const [low, high] = estimateYield(criteria, queries.length);

  return (
    <div className="flex flex-col gap-6">
      <dl className="grid gap-x-8 gap-y-5 sm:grid-cols-2 lg:grid-cols-3">
        <Summary label="Search">{name || <Missing>unnamed search</Missing>}</Summary>
        <Summary label="Target">
          {[criteria.businessTypes.join(" / "), criteria.industry.join(" / ")]
            .filter(Boolean)
            .join(" · ") || <Missing>not specified</Missing>}
        </Summary>
        <Summary label="Geography">
          {[criteria.location.city, criteria.location.region, criteria.location.country]
            .filter(Boolean)
            .join(", ") || <Missing>worldwide</Missing>}
        </Summary>
        <Summary label="Languages">
          {criteria.languages.join(", ") || <Missing>any</Missing>}
        </Summary>
        <Summary label="Keywords">
          {criteria.keywords.length ? (
            <span className="flex flex-wrap gap-1">
              {criteria.keywords.map((keyword) => (
                <Badge key={keyword} tone="accent">
                  {keyword}
                </Badge>
              ))}
            </span>
          ) : (
            <Missing>none</Missing>
          )}
        </Summary>
        <Summary label="Excluded">
          {criteria.negativeKeywords.length ? (
            <span className="flex flex-wrap gap-1">
              {criteria.negativeKeywords.map((keyword) => (
                <Badge key={keyword} tone="bad">
                  {keyword}
                </Badge>
              ))}
            </span>
          ) : (
            <Missing>none</Missing>
          )}
        </Summary>
        <Summary label="Sources" className="sm:col-span-2">
          <span className="flex flex-wrap gap-1">
            {criteria.sources.map((source) => (
              <Badge key={source}>
                {SOURCE_KINDS.find((entry) => entry.id === source)?.label ?? source}
              </Badge>
            ))}
          </span>
        </Summary>
        <Summary label="Expected candidates">
          <span className="num font-display text-xl font-semibold">
            {low}–{high}
          </span>
        </Summary>
      </dl>

      <section className="rounded-card border border-line bg-surface-2">
        <header className="flex items-center gap-2 border-b border-line px-4 py-2.5">
          <Terminal className="size-3.5 text-fg-faint" />
          <Eyebrow>Queries the search will run</Eyebrow>
          <span className="num ml-auto text-2xs text-fg-faint">{queries.length} of ~14</span>
        </header>
        <ul className="divide-y divide-line/60">
          {queries.map((query) => (
            <li key={query} className="px-4 py-2 font-mono text-xs break-all text-fg-muted">
              {query}
            </li>
          ))}
        </ul>
      </section>

      <section>
        <Eyebrow className="mb-2">Scoring model</Eyebrow>
        <div className="flex flex-wrap gap-1.5">
          {SCORED_SIGNALS.map((signal) => (
            <Badge key={signal} mono tone={criteria.signalWeights[signal] >= 25 ? "accent" : "neutral"}>
              {SIGNAL_LABELS[signal]} +{criteria.signalWeights[signal]}
            </Badge>
          ))}
        </div>
      </section>
    </div>
  );
}

function Summary({
  label,
  children,
  className,
}: {
  label: string;
  children: ReactNode;
  className?: string;
}) {
  return (
    <div className={className}>
      <dt className="label mb-1 text-fg-faint">{label}</dt>
      <dd className="text-sm">{children}</dd>
    </div>
  );
}

function Missing({ children }: { children: ReactNode }) {
  return <span className="text-fg-faint italic">{children}</span>;
}

/** Rough breadth heuristic — replaced by a backend estimate in Phase 4. */
function estimateYield(
  criteria: ReturnType<typeof useWizardStore.getState>["criteria"],
  queryCount: number,
) {
  const breadth =
    queryCount * 6 +
    criteria.keywords.length * 8 +
    criteria.sources.length * 9 -
    (criteria.location.city ? 40 : 0) -
    criteria.negativeKeywords.length * 4;

  const low = Math.max(20, Math.round(breadth * 0.45));
  return [low, Math.max(low + 40, Math.round(breadth * 1.6))];
}
