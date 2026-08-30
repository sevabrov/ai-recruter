"use client";

import { ChevronDown, Search, X } from "lucide-react";
import { useTranslations } from "next-intl";
import { LEAD_STATUSES } from "@/lib/domain";
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

const SCORE_THRESHOLDS = [0, 70, 85, 90];

/** One row of controls above the table (spec §14). */
export function FiltersBar({
  scope,
  showStatus = true,
}: {
  scope: FilterScope;
  showStatus?: boolean;
}) {
  const t = useTranslations("filters");
  const common = useTranslations("common");
  const platforms = useTranslations("domain.platform");
  const signals = useTranslations("domain.signal");
  const statuses = useTranslations("domain.leadStatus");
  const sorts = useTranslations("domain.sort");

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
          placeholder={t("searchPlaceholder")}
          className="pl-8.5"
          aria-label={t("searchAria")}
        />
      </div>

      <SelectField
        ariaLabel={t("minScoreAria")}
        value={String(filters.minScore ?? 0)}
        onValueChange={(value) => patch(scope, { minScore: Number(value) })}
        options={SCORE_THRESHOLDS.map((score) => ({
          value: String(score),
          label: score === 0 ? t("anyScore") : t("scoreAtLeast", { score }),
        }))}
      />

      <MultiFilter
        label={t("country")}
        selected={filters.countries ?? []}
        options={(facets?.countries ?? []).map((country) => ({ value: country, label: country }))}
        onToggle={(value) => toggleIn(scope, "countries", value)}
      />

      <MultiFilter
        label={t("platform")}
        selected={filters.platforms ?? []}
        options={(facets?.platforms ?? []).map((platform) => ({
          value: platform,
          label: platforms(platform as Platform),
        }))}
        onToggle={(value) => toggleIn(scope, "platforms", value as Platform)}
      />

      <MultiFilter
        label={t("signals")}
        selected={filters.signals ?? []}
        options={SIGNAL_FILTERS.map((signal) => ({ value: signal, label: signals(signal) }))}
        onToggle={(value) => toggleIn(scope, "signals", value as SignalType)}
      />

      {showStatus ? (
        <MultiFilter
          label={t("status")}
          selected={filters.statuses ?? []}
          options={LEAD_STATUSES.map((status) => ({
            value: status.id,
            label: statuses(status.id),
          }))}
          onToggle={(value) => toggleIn(scope, "statuses", value as never)}
        />
      ) : null}

      <ToggleChip
        active={Boolean(filters.hasEmail)}
        onClick={() => patch(scope, { hasEmail: !filters.hasEmail })}
      >
        {t("hasEmail")}
      </ToggleChip>
      <ToggleChip
        active={Boolean(filters.hasSocial)}
        onClick={() => patch(scope, { hasSocial: !filters.hasSocial })}
      >
        {t("hasSocial")}
      </ToggleChip>

      <div className="ml-auto flex items-center gap-2">
        {active ? (
          <Button variant="ghost" size="sm" onClick={() => clear(scope)}>
            <X />
            {common("clear")}
            <Badge tone="accent" className="ml-0.5">
              {active}
            </Badge>
          </Button>
        ) : null}
        <SelectField
          ariaLabel={t("sortAria")}
          value={filters.sort ?? "score_desc"}
          onValueChange={(value) => patch(scope, { sort: value as LeadSort })}
          options={SORT_OPTIONS.map((option) => ({ value: option, label: sorts(option) }))}
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
  const t = useTranslations("filters");

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
        <p className="px-2.5 py-1.5 text-xs text-fg-faint">{t("nothingToFilter")}</p>
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
