"use client";

import { Activity, Filter, RefreshCw, SlidersHorizontal, Users } from "lucide-react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useState } from "react";
import { PageHeader } from "@/components/layout/page-header";
import { FiltersBar } from "@/components/leads/filters-bar";
import { LeadsTable } from "@/components/leads/leads-table";
import { RejectedTable } from "@/components/search/rejected-table";
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
import { cn, formatCurrencyEur, formatNumber } from "@/lib/utils";
import { useSearch, useSearchLeads, useSearchRejected } from "@/services/hooks";
import { useFiltersStore } from "@/store/filters-store";
import { useWizardStore } from "@/store/wizard-store";
import type { Search } from "@/services/types";

/**
 * The result is two lists, not one.
 *
 * A search that returns four people out of fifty candidates used to show the four
 * and a set of counters for the rest. The counters cannot be checked, and the
 * question they raise — *are we losing leads in there?* — can only be answered by
 * opening the addresses that were refused. So the refused ones are a list of their
 * own, kept behind a tab because they are a diagnostic, not the deliverable.
 */
type Tab = "selected" | "rejected";

export default function SearchResultsPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const [tab, setTab] = useState<Tab>("selected");
  const filters = useFiltersStore((state) => state.scopes.results);
  const clear = useFiltersStore((state) => state.clear);
  const { data: search, isPending: searchPending } = useSearch(id);
  const { data: page, isPending } = useSearchLeads(id, filters);
  const { data: rejected, isPending: rejectedPending } = useSearchRejected(id);

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

      <Card className="mb-5 grid grid-cols-2 divide-x divide-y divide-line sm:grid-cols-5 sm:divide-y-0">
        <Metric label="Selected" value={formatNumber(page?.total ?? 0)} />
        <Metric label="High quality" value={formatNumber(highQuality)} tone="good" />
        <Metric label="Average score" value={String(averageScore)} />
        <Metric label="Filtered out" value={formatNumber(rejected?.total ?? 0)} />
        <Metric label="Cost" value={formatCurrencyEur(search.usage.estimatedCostEur)} />
      </Card>

      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-1">
          <Tab active={tab === "selected"} onClick={() => setTab("selected")}>
            <Users className="size-3.5" />
            Selected {formatNumber(page?.total ?? 0)}
          </Tab>
          <Tab active={tab === "rejected"} onClick={() => setTab("rejected")}>
            <Filter className="size-3.5" />
            Filtered out {formatNumber(rejected?.total ?? 0)}
          </Tab>
        </div>
        {tab === "selected" ? <FiltersBar scope="results" showStatus={false} /> : null}
      </div>

      {tab === "selected" ? (
        <>
          <Card>
            {leads.length ? (
              <LeadsTable leads={leads} isPending={isPending} />
            ) : isPending ? (
              <LeadsTable leads={[]} isPending />
            ) : search.leadCount === 0 ? (
              // The search itself produced nobody. Blaming the on-screen filters
              // for that was a lie: the candidates were refused by the search's
              // own requirements, and the counters say which one (spec §43).
              <NothingFound search={search} onInspect={() => setTab("rejected")} />
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
      ) : (
        <>
          <Card>
            <RejectedTable list={rejected} isPending={rejectedPending} />
          </Card>
          <p className="mt-3 text-xs leading-relaxed text-fg-faint">
            Every address this search discovered is in one of the two lists, so the pair is the
            whole of what it saw. A refusal that turns out to be a real person is worth reporting:
            it is a bug with a URL attached to it.
          </p>
        </>
      )}
    </>
  );
}

function Tab({
  active,
  onClick,
  children,
}: {
  active: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={active}
      className={cn(
        "inline-flex items-center gap-1.5 rounded-ctl px-3 py-1.5 text-sm font-medium transition-colors",
        active
          ? "bg-accent-soft text-accent"
          : "text-fg-muted hover:bg-surface-2 hover:text-fg",
      )}
    >
      {children}
    </button>
  );
}

/**
 * Why a finished search has no leads, and what to change.
 *
 * The refusal counters make this answerable: 46 candidates, 23 not people, 19
 * unconfirmed country, 4 missing a must-have signal is a diagnosis. The advice
 * below is derived from whichever counter dominates, so it points at the one
 * setting worth changing rather than listing everything that could be relaxed.
 */
function NothingFound({ search, onInspect }: { search: Search; onInspect: () => void }) {
  const progress = search.progress;
  const reasons = [
    {
      count: progress.rejectedUnreadable ?? 0,
      label: "pages the reader could not open",
      fix: "Nothing about these people was ever seen, so this is not a verdict on them. Open the filtered-out list and check the addresses.",
    },
    {
      count: progress.rejectedOffSource ?? 0,
      // The old wording ("found on a platform you did not select") read as though
      // the search had gone somewhere it was not asked to. It had not: the search
      // engine answers with whatever it likes, and these were refused for free.
      label: "offered by the search engine outside your sources, and refused",
      fix: "Nothing was read or paid for here. If one of your own queries has no site: operator it is asked of the whole web — the wizard now scopes those to the platforms you picked.",
    },
    {
      count: progress.rejectedNotAPerson ?? 0,
      label: "not people (brand accounts, communities, articles)",
      fix: "Narrow the wording: add a role word to your own query (консультант, дистриб’ютор), or exclude shops with -shop -магазин.",
    },
    {
      count: progress.rejectedCountry ?? 0,
      label: search.criteria.location.country
        ? `not confirmed to be in ${search.criteria.location.country}`
        : "refused on geography",
      fix: "Turn off “only if it can be confirmed” on the Geography step, or put the city into your own query so the description carries it.",
    },
    {
      count: progress.rejectedLanguage ?? 0,
      label: "publishing in another language",
      fix: "Turn off the language requirement: a two-line profile description often shows no language at all.",
    },
    {
      count: progress.rejectedSignals ?? 0,
      label: "missing a must-have signal",
      fix: "Keep one must-have. Every extra one is an AND, proven by a quote from a profile that may not have opened.",
    },
  ]
    .filter((reason) => reason.count > 0)
    .sort((first, second) => second.count - first.count);

  if (!reasons.length) {
    return (
      <EmptyState
        icon={<Users className="size-4" />}
        title="This search found nobody"
        body="No candidate reached the scoring stage. Widen the keywords or add a source, then run it again."
        action={
          <Button variant="secondary" size="sm" onClick={onInspect}>
            <Filter />
            See what was filtered out
          </Button>
        }
      />
    );
  }

  return (
    <CardBody className="flex flex-col gap-4">
      <div>
        <h3 className="font-display text-base font-semibold">This search found nobody</h3>
        <p className="mt-1 text-sm text-fg-muted">
          {formatNumber(search.progress.profilesDiscovered)} candidates were looked at
          and every one was refused by a requirement. Which requirement, and what to
          change:
        </p>
      </div>

      <ul className="flex flex-col divide-y divide-line rounded-card border border-line">
        {reasons.map((reason) => (
          <li key={reason.label} className="flex flex-col gap-1 px-3.5 py-3">
            <span className="flex items-baseline gap-2">
              <b className="num font-display text-lg font-semibold">
                {formatNumber(reason.count)}
              </b>
              <span className="text-sm">{reason.label}</span>
            </span>
            <span className="text-xs leading-relaxed text-fg-muted">{reason.fix}</span>
          </li>
        ))}
      </ul>

      <div>
        <Button variant="secondary" size="sm" onClick={onInspect}>
          <Filter />
          See every candidate that was filtered out
        </Button>
      </div>
    </CardBody>
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
