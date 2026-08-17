"use client";

import { ChevronDown, Search, X } from "lucide-react";
import {
  LEAD_STATUSES,
  PLATFORM_LABELS,
  SIGNAL_LABELS,
} from "@/lib/domain";
import { cn } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { SelectField } from "@/components/ui/controls";
import { Input } from "@/components/ui/field";
import { Menu, MenuCheckboxItem, MenuLabel } from "@/components/ui/overlay";
import { activeFilterCount, SORT_OPTIONS, useFiltersStore, type FilterScope } from "@/store/filters-store";
import { useLeadFacets } from "@/services/hooks";
import type { LeadSort, Platform, SignalType } from "@/services/types";

const SIGNAL_FILTERS: SignalType[] = ["mlm", "beauty", "leadership", "recruiting", "personalBrand"];

const SCORE_OPTIONS = [
  { value: "0", label: "Any score" },
  { value: "70", label: "70 and above" },
  { value: "85", label: "85 and above" },
  { value: "90", label: "90 and above" },
];

/** One row of controls above the table (spec §14). */
export function FiltersBar({
  scope,
  showStatus = true,
}: {
  scope: FilterScope;
  showStatus?: boolean;
}) {
  const filters = useFiltersStore((state) => state.scopes[scope]);
  const patch = useFiltersStore((state) => state.patch);
  const toggleIn = useFiltersStore((state) => state.toggleIn);
  const clear = useFiltersStore((state) => state.clear);
  const { data: facets } = useLeadFacets();

  const active = activeFilterCount(filters);

  return (
    <div className="flex flex-wrap items-center gap-2">
      <div className="relative min-w-56 flex-1">
        <Search className="pointer-events-none absolute top-1/2 left-3 size-3.5 -translate-y-1/2 text-fg-faint" />
        <Input
          value={filters.query ?? ""}
          onChange={(event) => patch(scope, { query: event.target.value })}
          placeholder="Search name, company, city…"
          className="pl-8.5"
          aria-label="Search leads"
        />
      </div>

      <SelectField
        ariaLabel="Minimum score"
        value={String(filters.minScore ?? 0)}
        onValueChange={(value) => patch(scope, { minScore: Number(value) })}
        options={SCORE_OPTIONS}
      />

      <MultiFilter
        label="Country"
        selected={filters.countries ?? []}
        options={(facets?.countries ?? []).map((country) => ({ value: country, label: country }))}
        onToggle={(value) => toggleIn(scope, "countries", value)}
      />

      <MultiFilter
        label="Platform"
        selected={filters.platforms ?? []}
        options={(facets?.platforms ?? []).map((platform) => ({
          value: platform,
          label: PLATFORM_LABELS[platform as Platform],
        }))}
        onToggle={(value) => toggleIn(scope, "platforms", value as Platform)}
      />

      <MultiFilter
        label="Signals"
        selected={filters.signals ?? []}
        options={SIGNAL_FILTERS.map((signal) => ({ value: signal, label: SIGNAL_LABELS[signal] }))}
        onToggle={(value) => toggleIn(scope, "signals", value as SignalType)}
      />

      {showStatus ? (
        <MultiFilter
          label="Status"
          selected={filters.statuses ?? []}
          options={LEAD_STATUSES.map((status) => ({ value: status.id, label: status.label }))}
          onToggle={(value) => toggleIn(scope, "statuses", value as never)}
        />
      ) : null}

      <ToggleChip
        active={Boolean(filters.hasEmail)}
        onClick={() => patch(scope, { hasEmail: !filters.hasEmail })}
      >
        Has email
      </ToggleChip>
      <ToggleChip
        active={Boolean(filters.hasSocial)}
        onClick={() => patch(scope, { hasSocial: !filters.hasSocial })}
      >
        Has social
      </ToggleChip>

      <div className="ml-auto flex items-center gap-2">
        {active ? (
          <Button variant="ghost" size="sm" onClick={() => clear(scope)}>
            <X />
            Clear
            <Badge tone="accent" className="ml-0.5">
              {active}
            </Badge>
          </Button>
        ) : null}
        <SelectField
          ariaLabel="Sort leads"
          value={filters.sort ?? "score_desc"}
          onValueChange={(value) => patch(scope, { sort: value as LeadSort })}
          options={SORT_OPTIONS.map((option) => ({ value: option.id, label: option.label }))}
        />
      </div>
    </div>
  );
}

function MultiFilter({
  label,
  options,
  selected,
  onToggle,
}: {
  label: string;
  options: { value: string; label: string }[];
  selected: string[];
  onToggle: (value: string) => void;
}) {
  return (
    <Menu
      align="start"
      trigger={
        <Button variant="secondary" size="md" className="gap-1.5">
          {label}
          {selected.length ? (
            <span className="num rounded-pill bg-accent-soft px-1.5 text-2xs text-accent">
              {selected.length}
            </span>
          ) : null}
          <ChevronDown className="text-fg-faint" />
        </Button>
      }
    >
      <MenuLabel>{label}</MenuLabel>
      {options.length ? (
        options.map((option) => (
          <MenuCheckboxItem
            key={option.value}
            checked={selected.includes(option.value)}
            onCheckedChange={() => onToggle(option.value)}
          >
            {option.label}
          </MenuCheckboxItem>
        ))
      ) : (
        <p className="px-2.5 py-1.5 text-xs text-fg-faint">Nothing to filter yet</p>
      )}
    </Menu>
  );
}

function ToggleChip({
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
        "h-9 rounded-ctl border px-3 text-sm transition-colors",
        active
          ? "border-accent-line bg-accent-soft text-accent"
          : "border-line bg-surface text-fg-muted hover:border-line-strong hover:text-fg",
      )}
    >
      {children}
    </button>
  );
}
