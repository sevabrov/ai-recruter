"use client";

import { Bookmark, SlidersHorizontal } from "lucide-react";
import { useTranslations } from "next-intl";
import { useState } from "react";
import { PageHeader } from "@/components/layout/page-header";
import { FiltersBar } from "@/components/leads/filters-bar";
import { LeadsTable } from "@/components/leads/leads-table";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { TabPanel, TabsRoot } from "@/components/ui/controls";
import { EmptyState } from "@/components/ui/misc";
import { useLeads } from "@/services/hooks";
import { useFiltersStore } from "@/store/filters-store";

type View = "all" | "saved" | "archived";

export default function LeadsPage() {
  const t = useTranslations("leads");
  const common = useTranslations("common");
  const [view, setView] = useState<View>("all");
  const filters = useFiltersStore((state) => state.scopes.leads);
  const clear = useFiltersStore((state) => state.clear);

  const scopedFilters = {
    ...filters,
    savedOnly: view === "saved" ? true : undefined,
    includeArchived: view === "archived" ? true : undefined,
  };

  const { data: page, isPending } = useLeads(scopedFilters);
  const { data: allPage } = useLeads({ pageSize: 500 });
  const { data: savedPage } = useLeads({ savedOnly: true, pageSize: 500 });

  const leads =
    view === "archived"
      ? (page?.items ?? []).filter((lead) => lead.archived)
      : (page?.items ?? []);

  return (
    <>
      <PageHeader eyebrow={t("eyebrow")} title={t("title")} description={t("description")} />

      <TabsRoot
        value={view}
        onValueChange={(value) => setView(value as View)}
        tabs={[
          { value: "all", label: t("tabAll"), count: allPage?.total },
          { value: "saved", label: t("tabSaved"), count: savedPage?.total },
          { value: "archived", label: t("tabArchived") },
        ]}
      >
        <div className="pt-4">
          <div className="mb-4">
            <FiltersBar scope="leads" />
          </div>

          <TabPanel value={view} forceMount>
            <Card>
              {leads.length || isPending ? (
                <LeadsTable leads={leads} isPending={isPending} />
              ) : view === "saved" ? (
                <EmptyState
                  icon={<Bookmark className="size-4" />}
                  title={t("emptySavedTitle")}
                  body={t("emptySavedBody")}
                />
              ) : view === "archived" ? (
                <EmptyState
                  icon={<Bookmark className="size-4" />}
                  title={t("emptyArchivedTitle")}
                  body={t("emptyArchivedBody")}
                />
              ) : (
                <EmptyState
                  icon={<SlidersHorizontal className="size-4" />}
                  title={t("emptyFilteredTitle")}
                  action={
                    <Button variant="secondary" size="sm" onClick={() => clear("leads")}>
                      {common("clearFilters")}
                    </Button>
                  }
                />
              )}
            </Card>
          </TabPanel>
        </div>
      </TabsRoot>
    </>
  );
}
