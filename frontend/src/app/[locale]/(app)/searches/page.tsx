"use client";

import { Plus, Search } from "lucide-react";
import { useTranslations } from "next-intl";
import { Link } from "@/i18n/navigation";
import { PageHeader } from "@/components/layout/page-header";
import { SearchRow } from "@/components/search/search-row";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { EmptyState, Skeleton } from "@/components/ui/misc";
import { isSearchRunning } from "@/lib/domain";
import { useSearches } from "@/services/hooks";

export default function SearchesPage() {
  const t = useTranslations("searches");
  const nav = useTranslations("nav");
  const { data: searches, isPending } = useSearches();

  const running = (searches ?? []).filter((search) => isSearchRunning(search.status));
  const finished = (searches ?? []).filter((search) => !isSearchRunning(search.status));

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

      {isPending ? (
        <Skeleton className="h-64 rounded-card" />
      ) : searches?.length ? (
        <div className="flex flex-col gap-5">
          {running.length ? (
            <Card>
              <header className="flex items-center justify-between border-b border-line px-5 py-3">
                <h2 className="text-sm font-semibold">{t("runningNow")}</h2>
                <span className="text-xs text-fg-muted">{t("count", { count: running.length })}</span>
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
              <h2 className="text-sm font-semibold">{t("allSearches")}</h2>
              <span className="text-xs text-fg-muted">{t("count", { count: finished.length })}</span>
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
            title={t("emptyTitle")}
            body={t("emptyBody")}
            action={
              <Button asChild variant="primary" size="sm">
                <Link href="/search/new">{t("emptyAction")}</Link>
              </Button>
            }
          />
        </Card>
      )}
    </>
  );
}
