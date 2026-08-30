"use client";

import { CircleSlash, Terminal } from "lucide-react";
import { useTranslations } from "next-intl";
import { useParams } from "next/navigation";
import { useEffect } from "react";
import { useRouter } from "@/i18n/navigation";
import { PageHeader } from "@/components/layout/page-header";
import { PipelineChecklist } from "@/components/search/pipeline-checklist";
import { ProgressMeter } from "@/components/search/progress-meter";
import { Badge, Dot } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { Eyebrow, Skeleton } from "@/components/ui/misc";
import { isSearchRunning, searchStatusTone } from "@/lib/domain";
import { useNumbers } from "@/lib/format";
import { useCancelSearch, useSearch } from "@/services/hooks";
import type { SearchProgress } from "@/services/types";

/** Stages the meter has a sentence for; see `domain.stageNote`. */
const NARRATED_STAGES: string[] = [
  "generating_queries",
  "web_search",
  "discovering_profiles",
  "extracting",
  "scoring",
  "deduplicating",
];

export default function SearchProgressPage() {
  const t = useTranslations("progress");
  const statuses = useTranslations("domain.searchStatus");
  const stageNotes = useTranslations("domain.stageNote");
  const { number, eur } = useNumbers();

  /** `queued` and anything the catalogue has no line for read as "finished". */
  const stageNote = (stage: string) =>
    NARRATED_STAGES.includes(stage) ? stageNotes(stage) : stageNotes("done");

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
          <p className="text-sm text-fg-muted">{t("notFound")}</p>
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
        eyebrow={t("eyebrow")}
        title={search.name}
        description={`${search.target}${search.country ? ` · ${search.country}` : ""}`}
        actions={
          <>
            <Badge tone={tone}>
              <Dot tone={tone} pulse={running} />
              {statuses(search.status)}
            </Badge>
            {running ? (
              <Button
                variant="secondary"
                onClick={() => cancelSearch.mutate(search.id)}
                disabled={cancelSearch.isPending}
              >
                <CircleSlash />
                {t("cancel")}
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
                    ? t("complete")
                    : search.status === "cancelled"
                      ? t("cancelled")
                      : `${stageNote(progress.stage)}…`
                }
                tone={finished ? "good" : "accent"}
              />
            </CardBody>
          </Card>

          <Card>
            <CardHeader title={t("pipeline")} hint={t("pipelineHint")} />
            <CardBody className="py-2">
              <PipelineChecklist progress={progress} />
            </CardBody>
          </Card>
        </div>

        <div className="flex flex-col gap-5">
          <Card>
            <CardHeader title={t("liveCounters")} />
            <div className="grid grid-cols-2 divide-x divide-y divide-line">
              <Counter label={t("pagesDiscovered")} value={progress.urlsDiscovered} />
              <Counter label={t("profilesFound")} value={progress.profilesDiscovered} />
              <Counter label={t("relevantCandidates")} value={progress.qualified} />
              <Counter label={t("highQuality")} value={progress.highQuality} tone="good" />
            </div>
          </Card>

          {/* Only once something has been turned away. A search that admits two of
              forty has to be able to say which requirement did it, or a strict
              result is indistinguishable from a broken one. */}
          {refused(progress) > 0 && (
            <Card>
              <CardHeader
                title={t("notTakenForward")}
                hint={t("notTakenForwardHint", { count: refused(progress) })}
              />
              <CardBody className="flex flex-col gap-2 text-sm">
                {(progress.rejectedOffSource ?? 0) > 0 && (
                  <Row
                    label={t("reasonOffSource")}
                    value={number(progress.rejectedOffSource ?? 0)}
                  />
                )}
                {(progress.rejectedNotAPerson ?? 0) > 0 && (
                  <Row
                    label={t("reasonNotAPerson")}
                    value={number(progress.rejectedNotAPerson ?? 0)}
                  />
                )}
                {(progress.rejectedCountry ?? 0) > 0 && (
                  <Row
                    label={
                      search.criteria.location.country
                        ? t("reasonCountry", { country: search.criteria.location.country })
                        : t("reasonCountryGeneric")
                    }
                    value={number(progress.rejectedCountry ?? 0)}
                  />
                )}
                {(progress.rejectedLanguage ?? 0) > 0 && (
                  <Row
                    label={t("reasonLanguage")}
                    value={number(progress.rejectedLanguage ?? 0)}
                  />
                )}
                {(progress.rejectedSignals ?? 0) > 0 && (
                  <Row
                    label={t("reasonSignals")}
                    value={number(progress.rejectedSignals ?? 0)}
                  />
                )}
              </CardBody>
            </Card>
          )}

          <Card>
            <CardHeader title={t("usage")} hint={t("usageHint")} />
            <CardBody className="flex flex-col gap-2 text-sm">
              <Row label={t("searchApiCalls")} value={number(search.usage.searchApiCalls)} />
              <Row label={t("pagesAnalyzed")} value={number(search.usage.pagesAnalyzed)} />
              {/* Read is what was paid for; cached is what an earlier search paid for. */}
              <Row label={t("pagesRead")} value={number(search.usage.pagesRead)} />
              <Row label={t("fromCache")} value={number(search.usage.pagesCached)} />
              {/* Only shown when the budget actually refused something, so the row is
                  an explanation of a thinner result rather than a permanent zero. */}
              {search.usage.pagesSkipped > 0 && (
                <Row label={t("pagesSkipped")} value={number(search.usage.pagesSkipped)} />
              )}
              {search.usage.scrapeCredits > 0 && (
                <Row label={t("readerCredits")} value={number(search.usage.scrapeCredits)} />
              )}
              <Row label={t("llmCalls")} value={number(search.usage.llmCalls)} />
              <div className="hairline my-1" />
              <Row
                label={t("estimatedCost")}
                value={eur(search.usage.estimatedCostEur)}
                emphasis
              />
            </CardBody>
          </Card>

          <Card>
            <CardHeader
              title={t("generatedQueries")}
              hint={t("generatedQueriesHint", { count: search.queries.length })}
              action={<Terminal className="size-3.5 text-fg-faint" />}
            />
            <ul className="max-h-64 divide-y divide-line overflow-y-auto">
              {search.queries.map((query) => (
                <li
                  key={query.id}
                  className="flex items-start justify-between gap-3 px-5 py-2 text-xs"
                >
                  <span className="font-mono break-all text-fg-muted">{query.query}</span>
                  <span className="num shrink-0 text-fg-faint">
                    {/* Which index it was put to: a Ukrainian query goes to the
                        Ukrainian one, which is half of why it finds anybody. */}
                    {query.language ? `${query.language} · ` : ""}
                    {query.resultCount}
                  </span>
                </li>
              ))}
            </ul>
          </Card>
        </div>
      </div>
    </>
  );
}

/** How many candidates a requirement turned away, across all four of them. */
function refused(progress: SearchProgress): number {
  return (
    (progress.rejectedOffSource ?? 0) +
    (progress.rejectedNotAPerson ?? 0) +
    (progress.rejectedCountry ?? 0) +
    (progress.rejectedLanguage ?? 0) +
    (progress.rejectedSignals ?? 0)
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
  const { number } = useNumbers();

  return (
    <div className="px-5 py-4">
      <Eyebrow>{label}</Eyebrow>
      <p
        className={`num font-display mt-1.5 text-2xl leading-none font-semibold ${
          tone === "good" ? "text-good" : ""
        }`}
      >
        {number(value)}
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
