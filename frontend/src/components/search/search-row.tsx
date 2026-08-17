import { ChevronRight } from "lucide-react";
import Link from "next/link";
import {
  isSearchRunning,
  SEARCH_STATUS_LABELS,
  searchStatusTone,
} from "@/lib/domain";
import { formatRelativeTime, pluralize } from "@/lib/utils";
import { Badge, Dot } from "@/components/ui/badge";
import type { SearchSummary } from "@/services/types";

export function searchHref(search: SearchSummary) {
  return isSearchRunning(search.status)
    ? `/search/${search.id}/progress`
    : `/search/${search.id}/results`;
}

export function SearchRow({ search }: { search: SearchSummary }) {
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
          <span className="text-xs text-fg-faint">in progress</span>
        ) : (
          <>
            <p className="num text-sm">{pluralize(search.leadCount, "lead")}</p>
            <p className="num mt-0.5 text-2xs text-fg-faint">
              {search.highQualityCount} high quality
            </p>
          </>
        )}
      </div>

      <Badge tone={tone} className="shrink-0">
        <Dot tone={tone} pulse={running} />
        {SEARCH_STATUS_LABELS[search.status]}
      </Badge>

      <span className="hidden w-16 shrink-0 text-right text-xs text-fg-faint md:block">
        {formatRelativeTime(search.createdAt)}
      </span>

      <ChevronRight className="size-4 shrink-0 text-fg-faint transition-transform group-hover:translate-x-0.5 group-hover:text-fg" />
    </Link>
  );
}
