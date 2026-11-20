"use client";

import { Activity, Filter, RefreshCw, SlidersHorizontal, Users } from "lucide-react";
import { useTranslations } from "next-intl";
import { useParams } from "next/navigation";
import { useState } from "react";
import { Link, useRouter } from "@/i18n/navigation";
import { PageHeader } from "@/components/layout/page-header";
import { FiltersBar } from "@/components/leads/filters-bar";
import { LeadsTable } from "@/components/leads/leads-table";
import { RejectedTable } from "@/components/search/rejected-table";
import { Badge, Dot } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardBody } from "@/components/ui/card";
import { EmptyState, Eyebrow, Skeleton } from "@/components/ui/misc";
import { HIGH_QUALITY_THRESHOLD, isSearchRunning, searchStatusTone } from "@/lib/domain";
import { useNumbers } from "@/lib/format";
import { cn } from "@/lib/utils";
import { useVocabulary } from "@/lib/vocabulary";
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
type TabId = "selected" | "rejected";

export default function SearchResultsPage() {
  const t = useTranslations("results");
  const common = useTranslations("common");
  const vocabulary = useVocabulary();
  const statuses = useTranslations("domain.searchStatus");
  const { number, eur } = useNumbers();

  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const [tab, setTab] = useState<TabId>("selected");
  const filters = useFiltersStore((state) => state.scopes.results);
  const clear = useFiltersStore((state) => state.clear);
  const { data: search, isPending: searchPending } = useSearch(id);
  const { data: page, isPending } = useSearchLeads(id, filters);
  const { data: rejected, isPending: rejectedPending } = useSearchRejected(id);

  const loadSearch = useWizardStore((state) => state.loadSearch);

  // Straight to the review: the criteria are already there to check, and the
  // description they came from is one click back.
  const rerun = () => {
    if (!search) return;
    loadSearch(`${search.name} ${t("rerunSuffix")}`, search.criteria);
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
        eyebrow={t("eyebrow")}
        title={search.name}
        description={`${vocabulary.target(search.target)}${search.country ? ` · ${vocabulary.country(search.country)}` : ""}`}
        actions={
          <>
            <Badge tone={tone}>
              <Dot tone={tone} pulse={isSearchRunning(search.status)} />
              {statuses(search.status)}
            </Badge>
            {isSearchRunning(search.status) ? (
              <Button asChild variant="secondary">
                <Link href={`/search/${search.id}/progress`}>
                  <Activity />
                  {t("liveProgress")}
                </Link>
              </Button>
            ) : null}
            <Button variant="secondary" onClick={rerun}>
              <RefreshCw />
              {t("refineRerun")}
            </Button>
          </>
        }
      />

      <Card className="mb-5 grid grid-cols-2 divide-x divide-y divide-line sm:grid-cols-5 sm:divide-y-0">
        <Metric label={t("selected")} value={number(page?.total ?? 0)} />
        <Metric label={t("highQuality")} value={number(highQuality)} tone="good" />
        <Metric label={t("averageScore")} value={String(averageScore)} />
        <Metric label={t("filteredOut")} value={number(rejected?.total ?? 0)} />
        <Metric label={t("cost")} value={eur(search.usage.estimatedCostEur)} />
      </Card>

      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-1">
          <Tab active={tab === "selected"} onClick={() => setTab("selected")}>
            <Users className="size-3.5" />
            {t("tabSelected", { count: page?.total ?? 0 })}
          </Tab>
          <Tab active={tab === "rejected"} onClick={() => setTab("rejected")}>
            <Filter className="size-3.5" />
            {t("tabFilteredOut", { count: rejected?.total ?? 0 })}
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
                title={t("noMatchTitle")}
                body={t("noMatchBody")}
                action={
                  <Button variant="secondary" size="sm" onClick={() => clear("results")}>
                    {common("clearFilters")}
                  </Button>
                }
              />
            )}
          </Card>

          {leads.length ? (
            <p className="mt-3 flex items-center gap-1.5 text-xs text-fg-faint">
              <Users className="size-3" />
              {t("showing", { shown: leads.length, total: page?.total ?? 0 })}
            </p>
          ) : null}
        </>
      ) : (
        <>
          <Card>
            <RejectedTable list={rejected} isPending={rejectedPending} />
          </Card>
          <p className="mt-3 text-xs leading-relaxed text-fg-faint">{t("rejectedNote")}</p>
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
  const t = useTranslations("results");
  const { number } = useNumbers();
  const vocabulary = useVocabulary();
  const progress = search.progress;
  const country = vocabulary.country(search.criteria.location.country);

  const reasons = [
    {
      id: "unreadable",
      count: progress.rejectedUnreadable ?? 0,
      label: t("reason.unreadable.label"),
      fix: t("reason.unreadable.fix"),
    },
    {
      id: "offSource",
      count: progress.rejectedOffSource ?? 0,
      // The old wording ("found on a platform you did not select") read as though
      // the search had gone somewhere it was not asked to. It had not: the search
      // engine answers with whatever it likes, and these were refused for free.
      label: t("reason.offSource.label"),
      fix: t("reason.offSource.fix"),
    },
    {
      id: "notAPerson",
      count: progress.rejectedNotAPerson ?? 0,
      label: t("reason.notAPerson.label"),
      fix: t("reason.notAPerson.fix"),
    },
    {
      id: "country",
      count: progress.rejectedCountry ?? 0,
      label: country
        ? t("reason.country.label", { country })
        : t("reason.country.labelGeneric"),
      fix: t("reason.country.fix"),
    },
    {
      id: "language",
      count: progress.rejectedLanguage ?? 0,
      label: t("reason.language.label"),
      fix: t("reason.language.fix"),
    },
    {
      id: "signals",
      count: progress.rejectedSignals ?? 0,
      label: t("reason.signals.label"),
      fix: t("reason.signals.fix"),
    },
  ]
    .filter((reason) => reason.count > 0)
    .sort((first, second) => second.count - first.count);

  if (!reasons.length) {
    return (
      <EmptyState
        icon={<Users className="size-4" />}
        title={t("nothingFoundTitle")}
        body={t("nothingFoundBody")}
        action={
          <Button variant="secondary" size="sm" onClick={onInspect}>
            <Filter />
            {t("seeFilteredOut")}
          </Button>
        }
      />
    );
  }

  return (
    <CardBody className="flex flex-col gap-4">
      <div>
        <h3 className="font-display text-base font-semibold">{t("nothingFoundTitle")}</h3>
        <p className="mt-1 text-sm text-fg-muted">
          {t("nothingFoundIntro", { count: progress.profilesDiscovered })}
        </p>
      </div>

      <ul className="flex flex-col divide-y divide-line rounded-card border border-line">
        {reasons.map((reason) => (
          <li key={reason.id} className="flex flex-col gap-1 px-3.5 py-3">
            <span className="flex items-baseline gap-2">
              <b className="num font-display text-lg font-semibold">{number(reason.count)}</b>
              <span className="text-sm">{reason.label}</span>
            </span>
            <span className="text-xs leading-relaxed text-fg-muted">{reason.fix}</span>
          </li>
        ))}
      </ul>

      <div>
        <Button variant="secondary" size="sm" onClick={onInspect}>
          <Filter />
          {t("seeEveryFilteredOut")}
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
