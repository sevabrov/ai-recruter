"use client";

import { ArrowRight, Plus, Search } from "lucide-react";
import { useTranslations } from "next-intl";
import { Link } from "@/i18n/navigation";
import { PageHeader } from "@/components/layout/page-header";
import { Button } from "@/components/ui/button";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { EmptyState, Skeleton } from "@/components/ui/misc";
import { ScoreHistogram, SourceShareBars, WeeklyLeadsChart } from "@/components/dashboard/charts";
import { StatTile } from "@/components/dashboard/stat-tile";
import { SearchRow } from "@/components/search/search-row";
import { useDashboard } from "@/services/hooks";

export default function DashboardPage() {
  const t = useTranslations("dashboard");
  const nav = useTranslations("nav");
  const { data, isPending } = useDashboard();

  return (
    <>
      <PageHeader
        eyebrow={t("eyebrow")}
        title={t("title")}
        description={t("description")}
        actions={
          <Button asChild variant="primary">
            <Link href="/search/new">
              <Plus />
              {nav("newSearch")}
            </Link>
          </Button>
        }
      />

      {isPending || !data ? (
        <DashboardSkeleton />
      ) : (
        <div className="flex flex-col gap-5">
          <Card className="grid grid-cols-1 divide-y divide-line sm:grid-cols-2 sm:divide-x lg:grid-cols-4 lg:divide-y-0">
            {/* The data source returns one label per stat; the tile is told which
                stat it is showing, so the heading follows the interface. */}
            <StatTile stat={data.stats.totalLeads} label={t("stats.totalLeads")} emphasis />
            <StatTile stat={data.stats.highQuality} label={t("stats.highQuality")} />
            <StatTile stat={data.stats.searches} label={t("stats.searches")} />
            <StatTile stat={data.stats.savedLeads} label={t("stats.savedLeads")} />
          </Card>

          <div className="grid gap-5 lg:grid-cols-[1.55fr_1fr]">
            <Card>
              <CardHeader
                title={t("recentSearches")}
                hint={t("recentSearchesHint")}
                action={
                  <Button asChild variant="ghost" size="sm">
                    <Link href="/searches">
                      {t("allSearches")}
                      <ArrowRight />
                    </Link>
                  </Button>
                }
              />
              {data.recentSearches.length ? (
                <ul className="divide-y divide-line">
                  {data.recentSearches.map((search) => (
                    <li key={search.id}>
                      <SearchRow search={search} />
                    </li>
                  ))}
                </ul>
              ) : (
                <EmptyState
                  icon={<Search className="size-4" />}
                  title={t("emptyTitle")}
                  body={t("emptyBody")}
                  action={
                    <Button asChild variant="primary" size="sm">
                      <Link href="/search/new">{t("emptyAction")}</Link>
                    </Button>
                  }
                />
              )}
            </Card>

            <Card>
              <CardHeader title={t("topSources")} hint={t("topSourcesHint")} />
              <CardBody>
                <SourceShareBars items={data.sourceBreakdown} />
              </CardBody>
            </Card>
          </div>

          <div className="grid gap-5 lg:grid-cols-2">
            <Card>
              <CardHeader title={t("scoreDistribution")} hint={t("scoreDistributionHint")} />
              <CardBody>
                <ScoreHistogram buckets={data.scoreDistribution} />
              </CardBody>
            </Card>

            <Card>
              <CardHeader title={t("leadsDiscovered")} hint={t("leadsDiscoveredHint")} />
              <CardBody>
                <WeeklyLeadsChart data={data.weeklyLeads} />
              </CardBody>
            </Card>
          </div>
        </div>
      )}
    </>
  );
}

function DashboardSkeleton() {
  return (
    <div className="flex flex-col gap-5">
      <Card className="grid grid-cols-2 divide-x divide-y divide-line lg:grid-cols-4 lg:divide-y-0">
        {[0, 1, 2, 3].map((index) => (
          <div key={index} className="flex flex-col gap-3 px-5 py-4">
            <Skeleton className="h-3 w-20" />
            <Skeleton className="h-7 w-24" />
            <Skeleton className="h-3 w-28" />
          </div>
        ))}
      </Card>
      <div className="grid gap-5 lg:grid-cols-[1.55fr_1fr]">
        <Skeleton className="h-72 rounded-card" />
        <Skeleton className="h-72 rounded-card" />
      </div>
    </div>
  );
}
