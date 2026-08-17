"use client";

import { ArrowRight, Plus, Search } from "lucide-react";
import Link from "next/link";
import { PageHeader } from "@/components/layout/page-header";
import { Button } from "@/components/ui/button";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { EmptyState, Skeleton } from "@/components/ui/misc";
import { ScoreHistogram, SourceShareBars, WeeklyLeadsChart } from "@/components/dashboard/charts";
import { StatTile } from "@/components/dashboard/stat-tile";
import { SearchRow } from "@/components/search/search-row";
import { useDashboard } from "@/services/hooks";

export default function DashboardPage() {
  const { data, isPending } = useDashboard();

  return (
    <>
      <PageHeader
        eyebrow="Workspace"
        title="Dashboard"
        description="Candidates discovered from public web sources, scored against your criteria."
        actions={
          <Button asChild variant="primary">
            <Link href="/search/new">
              <Plus />
              New search
            </Link>
          </Button>
        }
      />

      {isPending || !data ? (
        <DashboardSkeleton />
      ) : (
        <div className="flex flex-col gap-5">
          <Card className="grid grid-cols-1 divide-y divide-line sm:grid-cols-2 sm:divide-x lg:grid-cols-4 lg:divide-y-0">
            <StatTile stat={data.stats.totalLeads} emphasis />
            <StatTile stat={data.stats.highQuality} />
            <StatTile stat={data.stats.searches} />
            <StatTile stat={data.stats.savedLeads} />
          </Card>

          <div className="grid gap-5 lg:grid-cols-[1.55fr_1fr]">
            <Card>
              <CardHeader
                title="Recent searches"
                hint="Open a completed search to review its candidates"
                action={
                  <Button asChild variant="ghost" size="sm">
                    <Link href="/searches">
                      All searches
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
                  title="No searches yet"
                  body="Define who you are looking for and the AI pipeline takes it from there."
                  action={
                    <Button asChild variant="primary" size="sm">
                      <Link href="/search/new">Create the first search</Link>
                    </Button>
                  }
                />
              )}
            </Card>

            <Card>
              <CardHeader title="Top sources" hint="Share of discovered candidates" />
              <CardBody>
                <SourceShareBars items={data.sourceBreakdown} />
              </CardBody>
            </Card>
          </div>

          <div className="grid gap-5 lg:grid-cols-2">
            <Card>
              <CardHeader title="Score distribution" hint="All leads in the workspace" />
              <CardBody>
                <ScoreHistogram buckets={data.scoreDistribution} />
              </CardBody>
            </Card>

            <Card>
              <CardHeader title="Leads discovered" hint="Last 7 days" />
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
