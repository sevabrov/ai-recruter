"use client";

import { useTranslations } from "next-intl";
import { useParams } from "next/navigation";
import { useEffect } from "react";
import { useRouter } from "@/i18n/navigation";
import { searchHref } from "@/components/search/search-row";
import { Card, CardBody } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/misc";
import { useSearch } from "@/services/hooks";

/**
 * `/search/:id` has no view of its own; the breadcrumb links to it. Send it to
 * where the search is now: the progress while it runs, the results after.
 */
export default function SearchIndexPage() {
  const t = useTranslations("progress");
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const { data: search, isError } = useSearch(id);

  useEffect(() => {
    if (search) router.replace(searchHref(search));
  }, [search, router]);

  if (isError) {
    return (
      <Card>
        <CardBody>
          <p className="text-sm text-fg-muted">{t("notFound")}</p>
        </CardBody>
      </Card>
    );
  }

  return (
    <div className="flex flex-col gap-5">
      <Skeleton className="h-9 w-80" />
      <Skeleton className="h-96 rounded-card" />
    </div>
  );
}
