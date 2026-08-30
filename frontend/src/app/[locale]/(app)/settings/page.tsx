"use client";

import { Check, Database, FileSearch, Monitor, Radio, Trash2 } from "lucide-react";
import { useTranslations } from "next-intl";
import { useState } from "react";
import { PageHeader } from "@/components/layout/page-header";
import { Badge, Dot } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { SwitchField } from "@/components/ui/controls";
import { Eyebrow } from "@/components/ui/misc";
import { Modal } from "@/components/ui/overlay";
import { useToast } from "@/components/ui/toast";
import { useTheme } from "@/lib/theme-provider";
import { THEMES } from "@/lib/themes";
import { useNumbers } from "@/lib/format";
import { cn } from "@/lib/utils";
import { DATA_SOURCE, IS_MOCK } from "@/services";
import { API_BASE_URL } from "@/services/api/http";
import { useBackendHealth, useResetWorkspace, useSourceReport } from "@/services/hooks";
import type { HealthStatus } from "@/services/types";

/**
 * Concurrency + provider settings are server-owned (spec §52); shown read-only.
 * `name` is a product name and stays as it is in every language; `role` and the
 * "not configured yet" badge are `settings.providerRole.<id>` and either an
 * environment key or a phase number.
 */
const PROVIDERS: {
  id: string;
  name: string;
  /** Environment variable still missing, if that is what is holding it up. */
  envKey?: string;
  /** Otherwise, the phase that will deliver it. */
  phase?: number;
  configured?: (health: HealthStatus) => boolean;
}[] = [
  {
    id: "brave",
    name: "Brave Search",
    // Implemented in Phase 4: the only thing missing is a subscription token.
    envKey: "BRAVE_SEARCH_API_KEY",
    configured: (health) => health.providers.braveSearch,
  },
  {
    id: "scrapegraph",
    name: "ScrapeGraphAI",
    // Implemented in Phase 5: the only thing missing is an API key.
    envKey: "SCRAPEGRAPH_API_KEY",
    configured: (health) => health.providers.scrapegraph,
  },
  {
    id: "openai",
    name: "OpenAI",
    phase: 6,
    configured: (health) => health.providers.openai,
  },
  {
    id: "postgres",
    name: "PostgreSQL",
    phase: 3,
    configured: (health) => health.storage === "postgres" && health.database !== false,
  },
  {
    id: "redis",
    name: "Redis + Celery",
    phase: 7,
  },
];

const LIMITS = [
  { key: "SEARCH_CONCURRENCY", value: "10" },
  { key: "EXTRACTION_CONCURRENCY", value: "10" },
  { key: "LLM_CONCURRENCY", value: "10" },
  { key: "BRAVE_RATE_LIMIT_PER_SECOND", value: "1" },
  { key: "SCRAPEGRAPH_RATE_LIMIT_PER_SECOND", value: "1" },
  // A page the service served is billed whatever we do with the answer, so a paid
  // read is attempted once and then falls back to the search snippet.
  { key: "SCRAPEGRAPH_READ_ATTEMPTS", value: "1" },
];

/**
 * What each pipeline stage is actually running. The backend reports it, because
 * "is this real?" should be answerable without reading the server's environment.
 */
const STAGES: (keyof NonNullable<HealthStatus["stages"]>)[] = [
  "search",
  "extraction",
  "signals",
];

/** Adapter product names, and whether the adapter does the real thing. */
const ADAPTERS: Record<string, { name: string; live: boolean }> = {
  brave: { name: "Brave Search", live: true },
  scrapegraph: { name: "ScrapeGraphAI", live: true },
  llm: { name: "OpenAI", live: true },
  snippet: { name: "Search snippets", live: false },
  fixture: { name: "Fixture", live: false },
};

/** What each recorded outcome means, in the order the columns should read. */
const OUTCOMES: ("usable" | "notAPerson" | "blocked" | "empty" | "failed")[] = [
  "usable",
  "notAPerson",
  "blocked",
  "empty",
  "failed",
];

export default function SettingsPage() {
  const t = useTranslations("settings");
  const common = useTranslations("common");
  const theme = useTranslations("theme");
  const { number } = useNumbers();

  const { preference, resolved, setPreference } = useTheme();
  const [confirmReset, setConfirmReset] = useState(false);
  const [autoSaveHigh, setAutoSaveHigh] = useState(false);
  const [notifyDone, setNotifyDone] = useState(true);
  const { toast } = useToast();
  const health = useBackendHealth();
  const sources = useSourceReport();
  const resetWorkspace = useResetWorkspace();

  // A backend whose database stopped answering is not "connected" — it is degraded,
  // and saying so beats letting every screen fail with an empty state.
  const degraded = health.data?.database === false;
  const sourceTone = IS_MOCK
    ? "warn"
    : health.isError
      ? "bad"
      : degraded
        ? "warn"
        : health.data
          ? "good"
          : "neutral";

  const reset = () => {
    setConfirmReset(false);
    resetWorkspace.mutate(undefined, {
      onSuccess: () =>
        toast({ title: t("resetToastTitle"), description: t("resetToastBody") }),
      onError: (error) =>
        toast({
          title: t("resetFailedTitle"),
          description: error instanceof Error ? error.message : t("resetFailedBody"),
        }),
    });
  };

  return (
    <>
      <PageHeader eyebrow={t("eyebrow")} title={t("title")} description={t("description")} />

      <div className="flex flex-col gap-5">
        <Card>
          <CardHeader title={t("appearance")} hint={t("appearanceHint")} />
          <CardBody>
            <div className="grid gap-3 sm:grid-cols-3">
              {THEMES.map((entry) => (
                <button
                  key={entry.id}
                  type="button"
                  onClick={() => setPreference(entry.id)}
                  className={cn(
                    "flex flex-col gap-3 rounded-card border p-3 text-left transition-colors",
                    preference === entry.id
                      ? "border-accent bg-accent-soft"
                      : "border-line hover:border-line-strong",
                  )}
                >
                  <span className="flex gap-1.5">
                    {entry.swatch.map((color) => (
                      <span
                        key={color}
                        className="size-6 rounded-[6px] border border-black/10"
                        style={{ background: color }}
                      />
                    ))}
                  </span>
                  <span>
                    <span className="flex items-center gap-1.5 text-sm font-medium">
                      {theme(`${entry.id}.name`)}
                      {preference === entry.id ? <Check className="size-3.5 text-accent" /> : null}
                    </span>
                    <span className="block text-xs text-fg-muted">{theme(`${entry.id}.hint`)}</span>
                  </span>
                </button>
              ))}

              <button
                type="button"
                onClick={() => setPreference("system")}
                className={cn(
                  "flex flex-col gap-3 rounded-card border p-3 text-left transition-colors",
                  preference === "system"
                    ? "border-accent bg-accent-soft"
                    : "border-line hover:border-line-strong",
                )}
              >
                <span className="grid size-6 place-items-center rounded-[6px] border border-line text-fg-muted">
                  <Monitor className="size-3.5" />
                </span>
                <span>
                  <span className="flex items-center gap-1.5 text-sm font-medium">
                    {theme("followSystem")}
                    {preference === "system" ? <Check className="size-3.5 text-accent" /> : null}
                  </span>
                  <span className="block text-xs text-fg-muted">
                    {theme("currently", { theme: theme(`${resolved}.name`) })}
                  </span>
                </span>
              </button>
            </div>
          </CardBody>
        </Card>

        <Card>
          <CardHeader title={t("searchDefaults")} />
          <CardBody className="flex flex-col divide-y divide-line">
            <SwitchField
              checked={autoSaveHigh}
              onCheckedChange={setAutoSaveHigh}
              label={t("autoSaveHigh")}
              hint={t("autoSaveHighHint")}
            />
            <SwitchField
              checked={notifyDone}
              onCheckedChange={setNotifyDone}
              label={t("notifyDone")}
              hint={t("notifyDoneHint")}
            />
          </CardBody>
        </Card>

        <Card>
          <CardHeader
            title={t("dataSource")}
            action={
              <Badge tone={sourceTone} mono>
                <Dot tone={sourceTone} />
                {DATA_SOURCE}
              </Badge>
            }
          />
          <CardBody className="flex flex-col gap-4">
            <p className="text-sm text-fg-muted">
              {IS_MOCK ? (
                t("dataSourceMock")
              ) : health.isError ? (
                // The address and the shell command are values, not copy, so
                // they are injected as empty tags rather than sitting in the
                // catalogue where a translation pass could reword them.
                t.rich("dataSourceUnreachable", {
                  url: () => <Mono>{API_BASE_URL}</Mono>,
                  command: () => <Mono>docker compose up -d backend</Mono>,
                })
              ) : degraded ? (
                t.rich("dataSourceDegraded", {
                  service: health.data?.service ?? "",
                  command: () => <Mono>docker compose ps postgres</Mono>,
                })
              ) : health.data ? (
                <>
                  {t("dataSourceConnected", {
                    service: health.data.service,
                    version: health.data.version,
                    phase: health.data.phase,
                    storage: health.data.storage,
                  })}{" "}
                  {health.data.pipeline === "fixture"
                    ? t("dataSourcePipelineFixture")
                    : health.data.pipeline === "partial"
                      ? t("dataSourcePipelinePartial")
                      : t("dataSourcePipelineLive")}
                </>
              ) : (
                t("dataSourceConnecting")
              )}
            </p>

            <div>
              <Eyebrow className="mb-2">{t("backendIntegrations")}</Eyebrow>
              <ul className="divide-y divide-line rounded-card border border-line">
                {PROVIDERS.map((provider) => {
                  const configured = health.data ? provider.configured?.(health.data) : false;
                  return (
                    <li key={provider.id} className="flex items-center gap-3 px-3.5 py-2.5">
                      <Database className="size-3.5 shrink-0 text-fg-faint" />
                      <span className="min-w-0 flex-1">
                        <span className="block text-sm">{provider.name}</span>
                        <span className="block truncate text-xs text-fg-muted">
                          {t(`providerRole.${provider.id}`)}
                        </span>
                      </span>
                      {configured ? (
                        <Badge tone="good">
                          <Dot tone="good" />
                          {t("configured")}
                        </Badge>
                      ) : (
                        <Badge>
                          {provider.envKey
                            ? t("addKey", { key: provider.envKey })
                            : t("phase", { number: provider.phase ?? 0 })}
                        </Badge>
                      )}
                    </li>
                  );
                })}
              </ul>
            </div>

            {health.data?.stages ? (
              <div>
                <Eyebrow className="mb-2">{t("pipelineStages")}</Eyebrow>
                <ul className="divide-y divide-line rounded-card border border-line">
                  {STAGES.map((stage) => {
                    const value = health.data?.stages?.[stage] ?? "fixture";
                    const adapter = ADAPTERS[value];
                    return (
                      <li key={stage} className="flex items-center gap-3 px-3.5 py-2.5">
                        <Radio className="size-3.5 shrink-0 text-fg-faint" />
                        <span className="min-w-0 flex-1">
                          <span className="block text-sm">
                            {t(`stage.${stage}`)} · {adapter?.name ?? value}
                          </span>
                          <span className="block truncate text-xs text-fg-muted">
                            {adapter ? t(`adapter.${value}`) : t("adapter.unknown")}
                          </span>
                        </span>
                        <Badge tone={adapter?.live ? "good" : undefined}>
                          {adapter?.live ? (
                            <>
                              <Dot tone="good" />
                              {t("live")}
                            </>
                          ) : (
                            t("standIn")
                          )}
                        </Badge>
                      </li>
                    );
                  })}
                </ul>
              </div>
            ) : null}

            <div>
              <Eyebrow className="mb-2">{t("concurrencyLimits")}</Eyebrow>
              <ul className="flex flex-wrap gap-2">
                {LIMITS.map((limit) => (
                  <li
                    key={limit.key}
                    className="num rounded-ctl border border-line bg-surface-2 px-2.5 py-1 font-mono text-xs text-fg-muted"
                  >
                    {limit.key}={limit.value}
                  </li>
                ))}
              </ul>
            </div>
          </CardBody>
        </Card>

        <Card>
          <CardHeader
            title={t("readingSources")}
            hint={t("readingSourcesHint")}
            action={<FileSearch className="size-3.5 text-fg-faint" />}
          />
          <CardBody className="flex flex-col gap-4">
            <p className="text-sm text-fg-muted">
              {sources.data
                ? // `fallback` is one sentence written by the backend.
                  t("readingSourcesText", {
                    fallback: sources.data.fallback,
                    hours: sources.data.cacheTtlHours,
                  })
                : sources.isError
                  ? t("readingSourcesFailed")
                  : t("readingSourcesLoading")}
            </p>

            {sources.data?.live ? (
              <div>
                <Eyebrow className="mb-2">{t("whatOneSearchMaySpend")}</Eyebrow>
                <ul className="flex flex-wrap gap-2">
                  {[
                    {
                      key: "MAX_PAGES_PER_SEARCH",
                      value: sources.data.maxPagesPerSearch ?? t("unlimited"),
                    },
                    { key: "TARGET_LEADS", value: sources.data.targetLeads ?? t("noTarget") },
                    { key: "PAGES_PER_LEAD", value: sources.data.pagesPerLead ?? t("unknown") },
                    {
                      key: "SCRAPEGRAPH_CREDITS_PER_PAGE",
                      value: sources.data.creditsPerPage ?? t("unknown"),
                    },
                  ].map((limit) => (
                    <li
                      key={limit.key}
                      className="num rounded-ctl border border-line bg-surface-2 px-2.5 py-1 font-mono text-xs text-fg-muted"
                    >
                      {limit.key}={limit.value}
                    </li>
                  ))}
                </ul>
                <p className="mt-2 text-xs text-fg-muted">
                  {t.rich("budgetNote", {
                    mono: (chunks) => <span className="num font-mono">{chunks}</span>,
                  })}
                </p>
              </div>
            ) : null}

            {sources.data && sources.data.items.length > 0 ? (
              <ul className="divide-y divide-line rounded-card border border-line">
                {sources.data.items.map((row) => {
                  const share = Math.round(row.usableShare * 100);
                  return (
                    <li key={row.platform} className="flex flex-col gap-2 px-3.5 py-2.5">
                      <span className="flex items-baseline justify-between gap-3">
                        <span className="text-sm">
                          {PLATFORM_KEYS.includes(row.platform)
                            ? t(`platform.${row.platform}`)
                            : row.platform}
                        </span>
                        <Badge tone={share >= 60 ? "good" : share > 0 ? "warn" : undefined} mono>
                          {t("usableShare", { share })}
                        </Badge>
                      </span>
                      <span className="flex flex-wrap items-center gap-1.5 text-xs text-fg-muted">
                        <span className="num">{t("pages", { count: row.pages })}</span>
                        {OUTCOMES.filter((outcome) => row[outcome] > 0).map((outcome) => (
                          <span
                            key={outcome}
                            className="num rounded-ctl border border-line bg-surface-2 px-2 py-0.5"
                          >
                            {number(row[outcome])} {t(`outcome.${outcome}`)}
                          </span>
                        ))}
                      </span>
                    </li>
                  );
                })}
              </ul>
            ) : sources.data ? (
              <p className="rounded-card border border-line bg-surface-2 px-3.5 py-2.5 text-xs text-fg-muted">
                {t("noPageRead")}{" "}
                {sources.data.live ? t("noPageReadLive") : t("noPageReadFixture")}
              </p>
            ) : null}
          </CardBody>
        </Card>

        <Card className="border-bad/30">
          <CardHeader title={t("resetTitle")} hint={t("resetHint")} />
          <CardBody>
            <Button variant="danger" onClick={() => setConfirmReset(true)}>
              <Trash2 />
              {t("resetButton")}
            </Button>
          </CardBody>
        </Card>
      </div>

      <Modal
        open={confirmReset}
        onOpenChange={setConfirmReset}
        title={t("resetModalTitle")}
        description={t("resetModalDescription")}
        footer={
          <>
            <Button variant="ghost" onClick={() => setConfirmReset(false)}>
              {common("cancel")}
            </Button>
            <Button variant="danger" onClick={reset}>
              {common("reset")}
            </Button>
          </>
        }
      >
        <p className="text-sm text-fg-muted">
          {IS_MOCK ? t("resetBodyMock") : t("resetBodyApi")}
        </p>
      </Modal>
    </>
  );
}

/** Platforms this screen names; the report may carry others, shown raw. */
const PLATFORM_KEYS = ["instagram", "linkedin", "facebook", "threads", "website", "blog"];

function Mono({ children }: { children: React.ReactNode }) {
  return <span className="font-mono text-xs">{children}</span>;
}
