"use client";

import { Bookmark, SlidersHorizontal } from "lucide-react";
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
      <PageHeader
        eyebrow="Pipeline"
        title="Leads"
        description="Everything discovered across searches. Status and notes stay with the person, not the search."
      />

      <TabsRoot
        value={view}
        onValueChange={(value) => setView(value as View)}
        tabs={[
          { value: "all", label: "All leads", count: allPage?.total },
          { value: "saved", label: "Saved", count: savedPage?.total },
          { value: "archived", label: "Archived" },
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
                  title="No saved leads yet"
                  body="Use the bookmark in a results table or on a lead page to keep candidates here."
                />
              ) : view === "archived" ? (
                <EmptyState
                  icon={<Bookmark className="size-4" />}
                  title="Nothing archived"
                  body="Archiving hides a candidate from the main list without deleting the evidence."
                />
              ) : (
                <EmptyState
                  icon={<SlidersHorizontal className="size-4" />}
                  title="No leads match these filters"
                  action={
                    <Button variant="secondary" size="sm" onClick={() => clear("leads")}>
                      Clear filters
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
