"use client";

import { CircleSlash, Terminal } from "lucide-react";
import { useParams, useRouter } from "next/navigation";
import { useEffect } from "react";
import { PageHeader } from "@/components/layout/page-header";
import { PipelineChecklist } from "@/components/search/pipeline-checklist";
import { ProgressMeter } from "@/components/search/progress-meter";
import { Badge, Dot } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { Eyebrow, Skeleton } from "@/components/ui/misc";
import { isSearchRunning, SEARCH_STATUS_LABELS, searchStatusTone } from "@/lib/domain";
import { stageNote } from "@/mocks/search-progress";
import { formatCurrencyEur, formatNumber } from "@/lib/utils";
import { useCancelSearch, useSearch } from "@/services/hooks";

export default function SearchProgressPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const { data: search, isPending, isError } = useSearch(id);
  const cancelSearch = useCancelSearch();

  const finished = search?.status === "completed";

  // The moment the pipeline reports completion, move to the results (§13).
  useEffect(() => {
    if (!finished) return;
    const timer = setTimeout(() => router.replace(`/search/${id}/results`), 900);
    return () => clearTimeout(timer);
  }, [finished, id, router]);

  if (isError) {
    return (
      <Card>
        <CardBody>
          <p className="text-sm text-fg-muted">This search could not be found.</p>
        </CardBody>
      </Card>
    );
  }

  if (isPending || !search) {
    return (
      <div className="flex flex-col gap-5">
        <Skeleton className="h-9 w-72" />
        <Skeleton className="h-56 rounded-card" />
      </div>
    );
  }

  const { progress } = search;
  const running = isSearchRunning(search.status);
  const tone = searchStatusTone(search.status);

  return (
    <>
      <PageHeader
        eyebrow="Search in progress"
        title={search.name}
        description={`${search.target}${search.country ? ` · ${search.country}` : ""}`}
        actions={
          <>
            <Badge tone={tone}>
              <Dot tone={tone} pulse={running} />
              {SEARCH_STATUS_LABELS[search.status]}
            </Badge>
            {running ? (
              <Button
                variant="secondary"
                onClick={() => cancelSearch.mutate(search.id)}
                disabled={cancelSearch.isPending}
              >
                <CircleSlash />
                Cancel
              </Button>
            ) : null}
          </>
        }
      />

      <div className="grid gap-5 lg:grid-cols-[1.35fr_1fr]">
        <div className="flex flex-col gap-5">
          <Card>
            <CardBody className="py-5">
              <ProgressMeter
                percent={progress.percent}
                label={
                  finished
                    ? "Search complete — opening results"
                    : search.status === "cancelled"
                      ? "Search cancelled"
                      : `${stageNote(progress.stage)}…`
                }
                tone={finished ? "good" : "accent"}
              />
            </CardBody>
          </Card>

          <Card>
            <CardHeader title="Pipeline" hint="Each step reports from the worker, not the browser" />
            <CardBody className="py-2">
              <PipelineChecklist progress={progress} />
            </CardBody>
          </Card>
        </div>

        <div className="flex flex-col gap-5">
          <Card>
            <CardHeader title="Live counters" />
            <div className="grid grid-cols-2 divide-x divide-y divide-line">
              <Counter label="Pages discovered" value={progress.urlsDiscovered} />
              <Counter label="Profiles found" value={progress.profilesDiscovered} />
              <Counter label="Relevant candidates" value={progress.qualified} />
              <Counter label="High quality" value={progress.highQuality} tone="good" />
            </div>
          </Card>

          <Card>
            <CardHeader title="Usage this search" hint="Tracked from the first request" />
            <CardBody className="flex flex-col gap-2 text-sm">
              <Row label="Search API calls" value={formatNumber(search.usage.searchApiCalls)} />
              <Row label="Pages analyzed" value={formatNumber(search.usage.pagesAnalyzed)} />
              {/* Read is what was paid for; cached is what an earlier search paid for. */}
              <Row label="Pages read" value={formatNumber(search.usage.pagesRead)} />
              <Row label="From cache" value={formatNumber(search.usage.pagesCached)} />
              {/* Only shown when the budget actually refused something, so the row is
                  an explanation of a thinner result rather than a permanent zero. */}
              {search.usage.pagesSkipped > 0 && (
                <Row
                  label="Skipped (page budget)"
                  value={formatNumber(search.usage.pagesSkipped)}
                />
              )}
              {search.usage.scrapeCredits > 0 && (
                <Row label="Reader credits" value={formatNumber(search.usage.scrapeCredits)} />
              )}
              <Row label="LLM calls" value={formatNumber(search.usage.llmCalls)} />
              <div className="hairline my-1" />
              <Row
                label="Estimated cost"
                value={formatCurrencyEur(search.usage.estimatedCostEur)}
                emphasis
              />
            </CardBody>
          </Card>

          <Card>
            <CardHeader
              title="Generated queries"
              hint={`${search.queries.length} deterministic templates`}
              action={<Terminal className="size-3.5 text-fg-faint" />}
            />
            <ul className="max-h-64 divide-y divide-line overflow-y-auto">
              {search.queries.map((query) => (
                <li
                  key={query.id}
                  className="flex items-start justify-between gap-3 px-5 py-2 text-xs"
                >
                  <span className="font-mono break-all text-fg-muted">{query.query}</span>
                  <span className="num shrink-0 text-fg-faint">{query.resultCount}</span>
                </li>
              ))}
            </ul>
          </Card>
        </div>
      </div>
    </>
  );
}

function Counter({
  label,
  value,
  tone,
}: {
  label: string;
  value: number;
  tone?: "good";
}) {
  return (
    <div className="px-5 py-4">
      <Eyebrow>{label}</Eyebrow>
      <p
        className={`num font-display mt-1.5 text-2xl leading-none font-semibold ${
          tone === "good" ? "text-good" : ""
        }`}
      >
        {formatNumber(value)}
      </p>
    </div>
  );
}

function Row({
  label,
  value,
  emphasis,
}: {
  label: string;
  value: string;
  emphasis?: boolean;
}) {
  return (
    <div className="flex items-baseline justify-between gap-4">
      <span className="text-fg-muted">{label}</span>
      <span className={`num ${emphasis ? "font-semibold" : ""}`}>{value}</span>
    </div>
  );
}
