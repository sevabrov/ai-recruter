"use client";

import { AlertTriangle, Minus, Plus, Terminal } from "lucide-react";
import { SCORED_SIGNALS, SIGNAL_LABELS, SOURCE_KINDS } from "@/lib/domain";
import { useSearchEstimate } from "@/services/hooks";
import { useWizardStore } from "@/store/wizard-store";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Eyebrow } from "@/components/ui/misc";
import type { ReactNode } from "react";

/** What the wizard offers with one click. Any number can still be typed. */
const TARGETS = [5, 10, 25, 50];

export function StepReview() {
  const { name, criteria, patchCriteria } = useWizardStore();
  const estimate = useSearchEstimate(criteria);
  const target = criteria.targetLeads ?? 0;

  const setTarget = (leads: number) =>
    patchCriteria({ targetLeads: Math.max(1, Math.min(1000, leads)) });

  return (
    <div className="flex flex-col gap-6">
      <section className="grid gap-4 rounded-card border border-line bg-surface-2 p-4 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.1fr)]">
        <div>
          <Eyebrow className="mb-2">How many leads do you want?</Eyebrow>
          <div className="flex items-center gap-2">
            <Button
              variant="ghost"
              size="sm"
              aria-label="Fewer leads"
              onClick={() => setTarget(target - 1)}
            >
              <Minus />
            </Button>
            <input
              type="number"
              min={1}
              max={1000}
              value={target || ""}
              onChange={(event) => setTarget(Number(event.target.value))}
              aria-label="Leads to find"
              className="num w-20 rounded-input border border-line bg-surface-1 px-3 py-1.5 text-center font-display text-xl font-semibold"
            />
            <Button
              variant="ghost"
              size="sm"
              aria-label="More leads"
              onClick={() => setTarget(target + 1)}
            >
              <Plus />
            </Button>
            <div className="ml-2 flex flex-wrap gap-1">
              {TARGETS.map((leads) => (
                <Button
                  key={leads}
                  size="sm"
                  variant={target === leads ? "primary" : "ghost"}
                  onClick={() => setTarget(leads)}
                >
                  {leads}
                </Button>
              ))}
            </div>
          </div>
          <p className="mt-3 text-xs leading-relaxed text-fg-muted">
            The search stops once it has this many leads that pass every
            requirement. Candidates are read best first, so what a limit drops is
            the weakest tail — and the pages it never pays for still become leads
            from their search result.
          </p>
        </div>

        <Cost estimate={estimate.data} loading={estimate.isPending} failed={estimate.isError} />
      </section>

      <dl className="grid gap-x-8 gap-y-5 sm:grid-cols-2 lg:grid-cols-3">
        <Summary label="Search">{name || <Missing>unnamed search</Missing>}</Summary>
        <Summary label="Target">
          {[criteria.businessTypes.join(" / "), criteria.industry.join(" / ")]
            .filter(Boolean)
            .join(" · ") || <Missing>not specified</Missing>}
        </Summary>
        <Summary label="Geography">
          <span className="flex flex-wrap items-center gap-1.5">
            {[criteria.location.city, criteria.location.region, criteria.location.country]
              .filter(Boolean)
              .join(", ") || <Missing>worldwide</Missing>}
            {criteria.location.country && (criteria.requireLocation ?? true) ? (
              <Badge tone="accent">required</Badge>
            ) : null}
          </span>
        </Summary>
        <Summary label="Languages">
          <span className="flex flex-wrap items-center gap-1.5">
            {criteria.languages.join(", ") || <Missing>any</Missing>}
            {criteria.languages.length && (criteria.requireLanguage ?? true) ? (
              <Badge tone="accent">required</Badge>
            ) : null}
          </span>
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
        <Summary label="Sources" className="sm:col-span-2 lg:col-span-3">
          <span className="flex flex-wrap gap-1">
            {criteria.sources.map((source) => (
              <Badge key={source}>
                {SOURCE_KINDS.find((entry) => entry.id === source)?.label ?? source}
              </Badge>
            ))}
          </span>
        </Summary>
      </dl>

      <section className="rounded-card border border-line bg-surface-2">
        <header className="flex items-center gap-2 border-b border-line px-4 py-2.5">
          <Terminal className="size-3.5 text-fg-faint" />
          <Eyebrow>Queries the search will run</Eyebrow>
          <span className="num ml-auto text-2xs text-fg-faint">
            {estimate.data ? `${estimate.data.queries.length} queries` : "…"}
          </span>
        </header>
        <ul className="divide-y divide-line/60">
          {(estimate.data?.queries ?? []).map(({ query, language }) => (
            <li
              key={`${language ?? "any"}:${query}`}
              className="flex items-start gap-2 px-4 py-2 font-mono text-xs break-all text-fg-muted"
            >
              <span className="min-w-0 flex-1">{query}</span>
              {language ? <Badge mono>{language}</Badge> : null}
            </li>
          ))}
          {estimate.isPending ? (
            <li className="px-4 py-2 text-xs text-fg-faint">Asking the backend…</li>
          ) : null}
        </ul>
      </section>

      <section>
        <Eyebrow className="mb-2">Scoring model</Eyebrow>
        <div className="flex flex-wrap gap-1.5">
          {SCORED_SIGNALS.map((signal) => (
            <Badge
              key={signal}
              mono
              tone={criteria.signalWeights[signal] >= 25 ? "accent" : "neutral"}
            >
              {SIGNAL_LABELS[signal]} +{criteria.signalWeights[signal]}
            </Badge>
          ))}
        </div>
      </section>
    </div>
  );
}

/**
 * The price, as a ceiling rather than a forecast.
 *
 * The backend derives this figure and the run's page budget from the same
 * function, so it is a promise the search cannot break — which is the only kind
 * of number worth showing before somebody presses start.
 */
function Cost({
  estimate,
  loading,
  failed,
}: {
  estimate?: {
    searchCalls: number;
    maxPages: number;
    credits: number;
    maxCostEur: number;
    pagesPerLead: number;
    readsPages: boolean;
  };
  loading: boolean;
  failed: boolean;
}) {
  if (failed) {
    return (
      <div className="flex items-start gap-2 rounded-card border border-line bg-surface-1 p-4 text-xs text-warn">
        <AlertTriangle className="mt-0.5 size-3.5 shrink-0" />
        <span>
          The backend could not price this search. It can still be started — the
          limits configured on the server apply either way.
        </span>
      </div>
    );
  }

  return (
    <div className="rounded-card border border-line bg-surface-1 p-4">
      <Eyebrow className="mb-2">This search will cost at most</Eyebrow>
      <p className="num font-display text-3xl font-semibold">
        {loading || !estimate ? "—" : `€${estimate.maxCostEur.toFixed(2)}`}
      </p>
      <dl className="mt-3 space-y-1 text-xs text-fg-muted">
        <Line label="Search queries" value={estimate ? `${estimate.searchCalls} calls` : "—"} />
        <Line
          label="Pages read"
          value={
            !estimate
              ? "—"
              : !estimate.readsPages
                ? "none — no page reader configured"
                : estimate.maxPages
                  ? `up to ${estimate.maxPages} (${estimate.credits} credits)`
                  : "unlimited"
          }
        />
        {estimate?.readsPages && estimate.maxPages ? (
          <p className="pt-1 text-fg-faint">
            {estimate.pagesPerLead} pages per lead, measured from earlier runs. A
            page already read this week is free.
          </p>
        ) : null}
      </dl>
    </div>
  );
}

function Line({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-baseline justify-between gap-3">
      <dt>{label}</dt>
      <dd className="num text-fg">{value}</dd>
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
