"use client";

import { ChevronRight } from "lucide-react";
import { useTranslations } from "next-intl";
import { Link } from "@/i18n/navigation";
import { isSearchRunning, searchStatusTone } from "@/lib/domain";
import { useTimeAgo } from "@/lib/format";
import { Badge, Dot } from "@/components/ui/badge";
import type { SearchSummary } from "@/services/types";

export function searchHref(search: SearchSummary) {
  return isSearchRunning(search.status)
    ? `/search/${search.id}/progress`
    : `/search/${search.id}/results`;
}

export function SearchRow({ search }: { search: SearchSummary }) {
  const t = useTranslations("searchRow");
  const statuses = useTranslations("domain.searchStatus");
  const timeAgo = useTimeAgo();
  const running = isSearchRunning(search.status);
  const tone = searchStatusTone(search.status);

  return (
    <Link
      href={searchHref(search)}
      className="group flex items-center gap-4 px-5 py-3.5 transition-colors hover:bg-surface-2"
    >
      <div className="min-w-0 flex-1">
        <p className="truncate text-sm font-medium">{search.name}</p>
        <p className="mt-0.5 truncate text-xs text-fg-muted">
          {search.target}
          {search.country ? ` · ${search.country}` : ""}
        </p>
      </div>

      <div className="hidden w-28 shrink-0 text-right sm:block">
        {running ? (
          <span className="text-xs text-fg-faint">{t("inProgress")}</span>
        ) : (
          <>
            <p className="num text-sm">{t("leads", { count: search.leadCount })}</p>
            <p className="num mt-0.5 text-2xs text-fg-faint">
              {t("highQuality", { count: search.highQualityCount })}
            </p>
          </>
        )}
      </div>

      <Badge tone={tone} className="shrink-0">
        <Dot tone={tone} pulse={running} />
        {statuses(search.status)}
      </Badge>

      <span className="hidden w-16 shrink-0 text-right text-xs text-fg-faint md:block">
        {timeAgo(search.createdAt)}
      </span>

      <ChevronRight className="size-4 shrink-0 text-fg-faint transition-transform group-hover:translate-x-0.5 group-hover:text-fg" />
    </Link>
  );
}
