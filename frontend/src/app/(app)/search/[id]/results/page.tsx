"use client";

import { Activity, RefreshCw, SlidersHorizontal, Users } from "lucide-react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { PageHeader } from "@/components/layout/page-header";
import { FiltersBar } from "@/components/leads/filters-bar";
import { LeadsTable } from "@/components/leads/leads-table";
import { Badge, Dot } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardBody } from "@/components/ui/card";
import { EmptyState, Eyebrow, Skeleton } from "@/components/ui/misc";
import {
  HIGH_QUALITY_THRESHOLD,
  isSearchRunning,
  SEARCH_STATUS_LABELS,
  searchStatusTone,
} from "@/lib/domain";
import { formatCurrencyEur, formatNumber } from "@/lib/utils";
import { useSearch, useSearchLeads } from "@/services/hooks";
import { useFiltersStore } from "@/store/filters-store";
import { useWizardStore } from "@/store/wizard-store";

export default function SearchResultsPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const filters = useFiltersStore((state) => state.scopes.results);
  const clear = useFiltersStore((state) => state.clear);
  const { data: search, isPending: searchPending } = useSearch(id);
  const { data: page, isPending } = useSearchLeads(id, filters);

  const patchCriteria = useWizardStore((state) => state.patchCriteria);
  const setName = useWizardStore((state) => state.setName);
  const setStep = useWizardStore((state) => state.setStep);

  const rerun = () => {
    if (!search) return;
    setName(`${search.name} (v2)`);
    patchCriteria(search.criteria);
    setStep(1);
    router.push("/search/new");
  };

  if (searchPending || !search) {
    return (
      <div className="flex flex-col gap-5">
        <Skeleton className="h-9 w-80" />
        <Skeleton className="h-96 rounded-card" />
      </div>
    );
  }

  const leads = page?.items ?? [];
  const tone = searchStatusTone(search.status);
  const averageScore = leads.length
    ? Math.round(leads.reduce((total, lead) => total + lead.score, 0) / leads.length)
    : 0;
  const highQuality = leads.filter((lead) => lead.score >= HIGH_QUALITY_THRESHOLD).length;

  return (
    <>
      <PageHeader
        eyebrow="Search results"
        title={search.name}
        description={`${search.target}${search.country ? ` · ${search.country}` : ""}`}
        actions={
          <>
            <Badge tone={tone}>
              <Dot tone={tone} pulse={isSearchRunning(search.status)} />
              {SEARCH_STATUS_LABELS[search.status]}
            </Badge>
            {isSearchRunning(search.status) ? (
              <Button asChild variant="secondary">
                <Link href={`/search/${search.id}/progress`}>
                  <Activity />
                  Live progress
                </Link>
              </Button>
            ) : null}
            <Button variant="secondary" onClick={rerun}>
              <RefreshCw />
              Refine and re-run
            </Button>
          </>
        }
      />

      <Card className="mb-5 grid grid-cols-2 divide-x divide-y divide-line sm:grid-cols-4 sm:divide-y-0">
        <Metric label="Candidates" value={formatNumber(page?.total ?? 0)} />
        <Metric label="High quality" value={formatNumber(highQuality)} tone="good" />
        <Metric label="Average score" value={String(averageScore)} />
        <Metric label="Cost" value={formatCurrencyEur(search.usage.estimatedCostEur)} />
      </Card>

      <div className="mb-4">
        <FiltersBar scope="results" showStatus={false} />
      </div>

      <Card>
        {leads.length ? (
          <LeadsTable leads={leads} isPending={isPending} />
        ) : isPending ? (
          <LeadsTable leads={[]} isPending />
        ) : (
          <EmptyState
            icon={<SlidersHorizontal className="size-4" />}
            title="No candidates match these filters"
            body="Loosen the score threshold or clear a filter to see the rest of this search."
            action={
              <Button variant="secondary" size="sm" onClick={() => clear("results")}>
                Clear filters
              </Button>
            }
          />
        )}
      </Card>

      {leads.length ? (
        <p className="mt-3 flex items-center gap-1.5 text-xs text-fg-faint">
          <Users className="size-3" />
          Showing {formatNumber(leads.length)} of {formatNumber(page?.total ?? 0)} candidates.
          Duplicates across platforms are already merged into single people.
        </p>
      ) : null}
    </>
  );
}

function Metric({ label, value, tone }: { label: string; value: string; tone?: "good" }) {
  return (
    <CardBody>
      <Eyebrow>{label}</Eyebrow>
      <p
        className={`num font-display mt-1.5 text-2xl leading-none font-semibold ${
          tone === "good" ? "text-good" : ""
        }`}
      >
        {value}
      </p>
    </CardBody>
  );
}
