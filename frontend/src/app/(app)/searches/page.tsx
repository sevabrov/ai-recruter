"use client";

import { Plus, Search } from "lucide-react";
import Link from "next/link";
import { PageHeader } from "@/components/layout/page-header";
import { SearchRow } from "@/components/search/search-row";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { EmptyState, Skeleton } from "@/components/ui/misc";
import { isSearchRunning } from "@/lib/domain";
import { pluralize } from "@/lib/utils";
import { useSearches } from "@/services/hooks";

export default function SearchesPage() {
  const { data: searches, isPending } = useSearches();

  const running = (searches ?? []).filter((search) => isSearchRunning(search.status));
  const finished = (searches ?? []).filter((search) => !isSearchRunning(search.status));

  return (
    <>
      <PageHeader
        eyebrow="History"
        title="Searches"
        description="Every search keeps its criteria, so any result set can be re-run or refined later."
        actions={
          <Button asChild variant="primary">
            <Link href="/search/new">
              <Plus />
              New search
            </Link>
          </Button>
        }
      />

      {isPending ? (
        <Skeleton className="h-64 rounded-card" />
      ) : searches?.length ? (
        <div className="flex flex-col gap-5">
          {running.length ? (
            <Card>
              <header className="flex items-center justify-between border-b border-line px-5 py-3">
                <h2 className="text-sm font-semibold">Running now</h2>
                <span className="text-xs text-fg-muted">{pluralize(running.length, "search", "searches")}</span>
              </header>
              <ul className="divide-y divide-line">
                {running.map((search) => (
                  <li key={search.id}>
                    <SearchRow search={search} />
                  </li>
                ))}
              </ul>
            </Card>
          ) : null}

          <Card>
            <header className="flex items-center justify-between border-b border-line px-5 py-3">
              <h2 className="text-sm font-semibold">All searches</h2>
              <span className="text-xs text-fg-muted">{pluralize(finished.length, "search", "searches")}</span>
            </header>
            <ul className="divide-y divide-line">
              {finished.map((search) => (
                <li key={search.id}>
                  <SearchRow search={search} />
                </li>
              ))}
            </ul>
          </Card>
        </div>
      ) : (
        <Card>
          <EmptyState
            icon={<Search className="size-4" />}
            title="No searches yet"
            body="Every search starts with criteria: who the person is, where they are, and which signals matter."
            action={
              <Button asChild variant="primary" size="sm">
                <Link href="/search/new">Create a search</Link>
              </Button>
            }
          />
        </Card>
      )}
    </>
  );
}
