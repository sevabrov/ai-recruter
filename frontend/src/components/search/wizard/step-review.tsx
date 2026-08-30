"use client";

import { AlertTriangle, Minus, Plus, Terminal, X } from "lucide-react";
import {
  PLATFORM_LABELS,
  SCORED_SIGNALS,
  SIGNAL_LABELS,
  SITE_BY_SOURCE,
  SOURCE_KINDS,
  WEB_SOURCES,
} from "@/lib/domain";
import type { SourceKind } from "@/services/types";
import { useSearchEstimate } from "@/services/hooks";
import { useWizardStore } from "@/store/wizard-store";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/field";
import { Eyebrow } from "@/components/ui/misc";
import { useState, type ReactNode } from "react";

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

      {/* Said before the money is spent. The client's complaint was never that the
          filters were wrong — it was that a reasonable-looking set of them returned
          nothing, and the screen blamed the filters afterwards. */}
      {estimate.data?.warnings?.length ? (
        <section className="rounded-card border border-warn/30 bg-warn-soft px-4 py-3.5">
          <Eyebrow className="mb-2 text-warn">Worth knowing before you start</Eyebrow>
          <ul className="flex flex-col gap-2">
            {estimate.data.warnings.map((warning) => (
              <li key={warning} className="flex gap-2 text-xs leading-relaxed text-fg-muted">
                <AlertTriangle className="mt-0.5 size-3.5 shrink-0 text-warn" />
                <span>{warning}</span>
              </li>
            ))}
          </ul>
        </section>
      ) : null}

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

      <Queries
        own={criteria.customQueries ?? []}
        sources={criteria.sources}
        generated={estimate.data?.queries ?? []}
        loading={estimate.isPending}
        onChange={(customQueries) => patchCriteria({ customQueries })}
      />

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
 * The queries, with room to write your own.
 *
 * The generated ones are templates: they know the criteria, not the market. The
 * people a client is looking for label *themselves*, with a brand name nobody
 * outside that market would guess — so the panel that shows what will run is also
 * where a line of it can be written by hand. Hand-written queries run first and
 * are never dropped by the query cap.
 *
 * Where to look is a set of buttons rather than something to type. Asked to write
 * the query itself, the client wrote `джерелія` — a perfectly good question, put
 * to the whole indexed web, which answered with the brand's own site, four shops,
 * a catalogue and a hotel called Jerelia. Eighteen of those twenty results were
 * then thrown away for being off-source. Nobody should have to know that
 * `site:instagram.com` is what turns that into a question about people.
 */
function Queries({
  own,
  sources,
  generated,
  loading,
  onChange,
}: {
  own: string[];
  sources: SourceKind[];
  generated: { query: string; language?: string | null }[];
  loading: boolean;
  onChange: (queries: string[]) => void;
}) {
  const [draft, setDraft] = useState("");
  const [picked, setPicked] = useState<string[] | null>(null);

  // Only the sources this search actually looks at: a query aimed anywhere else
  // would be answered and then discarded.
  const places: { id: string; label: string; operator: string | null }[] = [
    ...SOURCE_KINDS.filter(
      (kind) => sources.includes(kind.id) && SITE_BY_SOURCE[kind.id],
    ).map((kind) => ({
      id: kind.id as string,
      label: kind.platform ? PLATFORM_LABELS[kind.platform] : kind.label,
      operator: SITE_BY_SOURCE[kind.id]!,
    })),
    ...(sources.some((source) => WEB_SOURCES.includes(source))
      ? [{ id: "web", label: "Whole web", operator: null }]
      : []),
  ];

  // Null means "none of them touched yet", which reads as all of them.
  const chosen = places.filter(
    (place) => picked === null || picked.includes(place.id),
  );
  const toggle = (id: string) => {
    const current = chosen.map((place) => place.id);
    setPicked(
      current.includes(id)
        ? current.filter((entry) => entry !== id)
        : [...current, id],
    );
  };

  // The backend returns the client's own queries first, so showing both lists
  // would show them twice.
  const templates = generated.filter((entry) => !own.includes(entry.query));

  const cleaned = draft.trim().replace(/\s+/g, " ");
  const written = /\bsite:/i.test(cleaned);
  const composed = !cleaned
    ? []
    : written
      ? [cleaned]
      : chosen.map((place) =>
          place.operator ? `${place.operator} ${cleaned}` : cleaned,
        );
  const fresh = composed.filter((query) => !own.includes(query));

  const add = () => {
    if (!fresh.length) return;
    onChange([...own, ...fresh]);
    setDraft("");
  };

  return (
    <section className="rounded-card border border-line bg-surface-2">
      <header className="flex items-center gap-2 border-b border-line px-4 py-2.5">
        <Terminal className="size-3.5 text-fg-faint" />
        <Eyebrow>Queries the search will run</Eyebrow>
        <span className="num ml-auto text-2xs text-fg-faint">
          {loading ? "…" : `${own.length + templates.length} queries`}
        </span>
      </header>

      <div className="flex flex-col gap-2.5 border-b border-line px-4 py-3">
        {places.length ? (
          <div className="flex flex-wrap items-center gap-1.5">
            <Eyebrow className="mr-1">Search in</Eyebrow>
            {places.map((place) => {
              const on = chosen.some((entry) => entry.id === place.id);
              return (
                <button
                  key={place.id}
                  type="button"
                  aria-pressed={on}
                  onClick={() => toggle(place.id)}
                  className={`rounded-full border px-2.5 py-1 text-xs transition-colors ${
                    on
                      ? "border-accent bg-accent-soft text-accent"
                      : "border-line text-fg-faint hover:text-fg"
                  }`}
                >
                  {place.label}
                </button>
              );
            })}
          </div>
        ) : null}

        <div className="flex gap-2">
          <Input
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter") {
                event.preventDefault();
                add();
              }
            }}
            placeholder="джерелія"
            aria-label="What to search for"
            className="text-xs"
          />
          <Button variant="secondary" onClick={add} disabled={!fresh.length}>
            <Plus />
            Add
          </Button>
        </div>

        {/* What the buttons and the words add up to, before it is added. */}
        {composed.length ? (
          <ul className="flex flex-col gap-1">
            {composed.map((query) => (
              <li
                key={query}
                className={`font-mono text-2xs break-all ${
                  own.includes(query) ? "text-fg-faint line-through" : "text-fg-muted"
                }`}
              >
                {query}
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-xs leading-relaxed text-fg-muted">
            {chosen.length
              ? "Type the brand people distribute, or how they describe themselves — джерелія, фармасі, консультант. One query is one billed call, and a name your market uses beats any template."
              : "Pick at least one place to search."}
          </p>
        )}
        {written ? (
          <p className="text-xs text-fg-muted">
            This query names its own <code className="font-mono">site:</code>, so
            it is added exactly as written.
          </p>
        ) : null}
      </div>

      <ul className="divide-y divide-line/60">
        {own.map((query) => (
          <li key={query} className="flex items-start gap-2 px-4 py-2 text-xs">
            <span className="min-w-0 flex-1 font-mono break-all">{query}</span>
            <Badge tone="accent">yours</Badge>
            <button
              type="button"
              aria-label={`Remove query ${query}`}
              onClick={() => onChange(own.filter((entry) => entry !== query))}
              className="text-fg-faint transition-colors hover:text-bad"
            >
              <X className="size-3.5" />
            </button>
          </li>
        ))}
        {templates.map(({ query, language }) => (
          <li
            key={`${language ?? "any"}:${query}`}
            className="flex items-start gap-2 px-4 py-2 font-mono text-xs break-all text-fg-muted"
          >
            <span className="min-w-0 flex-1">{query}</span>
            {language ? <Badge mono>{language}</Badge> : null}
          </li>
        ))}
        {loading ? (
          <li className="px-4 py-2 text-xs text-fg-faint">Asking the backend…</li>
        ) : null}
      </ul>
    </section>
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
