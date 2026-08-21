"use client";

import { Check, Database, FileSearch, Monitor, Radio, Trash2 } from "lucide-react";
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
import { cn, formatNumber } from "@/lib/utils";
import { DATA_SOURCE, IS_MOCK } from "@/services";
import { API_BASE_URL } from "@/services/api/http";
import { useBackendHealth, useResetWorkspace, useSourceReport } from "@/services/hooks";
import type { HealthStatus } from "@/services/types";

/** Concurrency + provider settings are server-owned (spec §52); shown read-only. */
const PROVIDERS: {
  name: string;
  role: string;
  /** What the badge says while this one is not configured. */
  pending: string;
  configured?: (health: HealthStatus) => boolean;
}[] = [
  {
    name: "Brave Search",
    role: "Primary web search provider",
    // Implemented in Phase 4: the only thing missing is a subscription token.
    pending: "add BRAVE_SEARCH_API_KEY",
    configured: (health) => health.providers.braveSearch,
  },
  {
    name: "ScrapeGraphAI",
    role: "Structured extraction from candidate pages",
    // Implemented in Phase 5: the only thing missing is an API key.
    pending: "add SCRAPEGRAPH_API_KEY",
    configured: (health) => health.providers.scrapegraph,
  },
  {
    name: "OpenAI",
    role: "Signal detection on extracted profiles",
    pending: "Phase 6",
    configured: (health) => health.providers.openai,
  },
  {
    name: "PostgreSQL",
    role: "Where searches, leads and notes live",
    pending: "Phase 3",
    configured: (health) => health.storage === "postgres" && health.database !== false,
  },
  {
    name: "Redis + Celery",
    role: "Distributed job queue for the workers",
    pending: "Phase 7",
  },
];

const LIMITS = [
  { key: "SEARCH_CONCURRENCY", value: "10" },
  { key: "EXTRACTION_CONCURRENCY", value: "10" },
  { key: "LLM_CONCURRENCY", value: "10" },
  { key: "BRAVE_RATE_LIMIT_PER_SECOND", value: "1" },
  { key: "SCRAPEGRAPH_RATE_LIMIT_PER_SECOND", value: "5" },
];

/**
 * What each pipeline stage is actually running. The backend reports it, because
 * "is this real?" should be answerable without reading the server's environment.
 */
const STAGES: { key: keyof NonNullable<HealthStatus["stages"]>; label: string }[] = [
  { key: "search", label: "Web search" },
  { key: "extraction", label: "Page extraction" },
  { key: "signals", label: "Signal detection" },
];

const ADAPTERS: Record<string, { name: string; live: boolean; hint: string }> = {
  brave: { name: "Brave Search", live: true, hint: "Live public web results" },
  scrapegraph: {
    name: "ScrapeGraphAI",
    live: true,
    hint: "Opens each candidate page and extracts the profile it states",
  },
  llm: { name: "OpenAI", live: true, hint: "Judges each signal on the profile" },
  snippet: {
    name: "Search snippets",
    live: false,
    hint: "Profiles built from result metadata, not from the page — add SCRAPEGRAPH_API_KEY",
  },
  fixture: { name: "Fixture", live: false, hint: "The seeded catalogue of 24 candidates" },
};

/** What each recorded outcome means, in the order the columns should read. */
const OUTCOMES: { key: "usable" | "notAPerson" | "blocked" | "empty" | "failed"; label: string }[] =
  [
    { key: "usable", label: "read" },
    { key: "notAPerson", label: "not a person" },
    { key: "blocked", label: "blocked" },
    { key: "empty", label: "empty" },
    { key: "failed", label: "failed" },
  ];

const PLATFORM_LABELS: Record<string, string> = {
  instagram: "Instagram",
  linkedin: "LinkedIn",
  facebook: "Facebook",
  threads: "Threads",
  website: "Personal sites",
  blog: "Blogs",
};

export default function SettingsPage() {
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
        toast({
          title: "Demo data reset",
          description: "Fixtures are back to their original state.",
        }),
      onError: (error) =>
        toast({
          title: "Reset failed",
          description: error instanceof Error ? error.message : "The data source did not respond.",
        }),
    });
  };

  return (
    <>
      <PageHeader
        eyebrow="Workspace"
        title="Settings"
        description="Appearance is yours; provider keys and concurrency limits live on the server and are never sent to the browser."
      />

      <div className="flex flex-col gap-5">
        <Card>
          <CardHeader title="Appearance" hint="Themes are defined as token sets, so new palettes drop in without touching components" />
          <CardBody>
            <div className="grid gap-3 sm:grid-cols-3">
              {THEMES.map((theme) => (
                <button
                  key={theme.id}
                  type="button"
                  onClick={() => setPreference(theme.id)}
                  className={cn(
                    "flex flex-col gap-3 rounded-card border p-3 text-left transition-colors",
                    preference === theme.id
                      ? "border-accent bg-accent-soft"
                      : "border-line hover:border-line-strong",
                  )}
                >
                  <span className="flex gap-1.5">
                    {theme.swatch.map((color) => (
                      <span
                        key={color}
                        className="size-6 rounded-[6px] border border-black/10"
                        style={{ background: color }}
                      />
                    ))}
                  </span>
                  <span>
                    <span className="flex items-center gap-1.5 text-sm font-medium">
                      {theme.name}
                      {preference === theme.id ? <Check className="size-3.5 text-accent" /> : null}
                    </span>
                    <span className="block text-xs text-fg-muted">{theme.hint}</span>
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
                    Follow system
                    {preference === "system" ? <Check className="size-3.5 text-accent" /> : null}
                  </span>
                  <span className="block text-xs text-fg-muted">
                    Currently {resolved === "graphite" ? "Graphite" : "Daylight"}
                  </span>
                </span>
              </button>
            </div>
          </CardBody>
        </Card>

        <Card>
          <CardHeader title="Search defaults" />
          <CardBody className="flex flex-col divide-y divide-line">
            <SwitchField
              checked={autoSaveHigh}
              onCheckedChange={setAutoSaveHigh}
              label="Auto-save high matches"
              hint="Candidates scoring 90 or above land in Saved leads automatically"
            />
            <SwitchField
              checked={notifyDone}
              onCheckedChange={setNotifyDone}
              label="Notify me when a search finishes"
              hint="A toast while the app is open; email once accounts exist"
            />
          </CardBody>
        </Card>

        <Card>
          <CardHeader
            title="Data source"
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
                "The app is running on in-browser fixtures. No search API, scraper or model is called. Switch by setting NEXT_PUBLIC_DATA_SOURCE=api once the backend is live."
              ) : health.isError ? (
                <>
                  No answer from <span className="font-mono text-xs">{API_BASE_URL}</span>. Start it
                  with <span className="font-mono text-xs">docker compose up -d backend</span>.
                </>
              ) : degraded ? (
                <>
                  {health.data?.service} is up but its database is not answering. Check it with{" "}
                  <span className="font-mono text-xs">docker compose ps postgres</span>.
                </>
              ) : health.data ? (
                <>
                  Connected to {health.data.service} v{health.data.version} (phase{" "}
                  {health.data.phase}), storing the workspace in {health.data.storage}.{" "}
                  {health.data.pipeline === "fixture"
                    ? "No external service is called: searches run over the seeded catalogue."
                    : health.data.pipeline === "partial"
                      ? "New searches query the live web; the stages below say what is real and what is still a stand-in."
                      : "Every pipeline stage is running against a real provider."}
                </>
              ) : (
                "Connecting to the backend…"
              )}
            </p>

            <div>
              <Eyebrow className="mb-2">Backend integrations</Eyebrow>
              <ul className="divide-y divide-line rounded-card border border-line">
                {PROVIDERS.map((provider) => {
                  const configured = health.data ? provider.configured?.(health.data) : false;
                  return (
                    <li key={provider.name} className="flex items-center gap-3 px-3.5 py-2.5">
                      <Database className="size-3.5 shrink-0 text-fg-faint" />
                      <span className="min-w-0 flex-1">
                        <span className="block text-sm">{provider.name}</span>
                        <span className="block truncate text-xs text-fg-muted">{provider.role}</span>
                      </span>
                      {configured ? (
                        <Badge tone="good">
                          <Dot tone="good" />
                          configured
                        </Badge>
                      ) : (
                        <Badge>{provider.pending}</Badge>
                      )}
                    </li>
                  );
                })}
              </ul>
            </div>

            {health.data?.stages ? (
              <div>
                <Eyebrow className="mb-2">Pipeline stages</Eyebrow>
                <ul className="divide-y divide-line rounded-card border border-line">
                  {STAGES.map((stage) => {
                    const value = health.data?.stages?.[stage.key] ?? "fixture";
                    const adapter = ADAPTERS[value] ?? {
                      name: value,
                      live: false,
                      hint: "Unknown adapter",
                    };
                    return (
                      <li key={stage.key} className="flex items-center gap-3 px-3.5 py-2.5">
                        <Radio className="size-3.5 shrink-0 text-fg-faint" />
                        <span className="min-w-0 flex-1">
                          <span className="block text-sm">
                            {stage.label} · {adapter.name}
                          </span>
                          <span className="block truncate text-xs text-fg-muted">
                            {adapter.hint}
                          </span>
                        </span>
                        <Badge tone={adapter.live ? "good" : undefined}>
                          {adapter.live ? (
                            <>
                              <Dot tone="good" />
                              live
                            </>
                          ) : (
                            "stand-in"
                          )}
                        </Badge>
                      </li>
                    );
                  })}
                </ul>
              </div>
            ) : null}

            <div>
              <Eyebrow className="mb-2">Concurrency limits (server-side)</Eyebrow>
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
            title="Reading the sources"
            hint="Measured from the pages this workspace has opened — not an assumption about the platforms"
            action={<FileSearch className="size-3.5 text-fg-faint" />}
          />
          <CardBody className="flex flex-col gap-4">
            <p className="text-sm text-fg-muted">
              {sources.data ? (
                <>
                  {sources.data.fallback} A page is read once and reused for{" "}
                  {sources.data.cacheTtlHours} hours, so the same profile is never paid for twice.
                </>
              ) : sources.isError ? (
                "The backend did not answer this one."
              ) : (
                "Loading the reading record…"
              )}
            </p>

            {sources.data && sources.data.items.length > 0 ? (
              <ul className="divide-y divide-line rounded-card border border-line">
                {sources.data.items.map((row) => {
                  const share = Math.round(row.usableShare * 100);
                  return (
                    <li key={row.platform} className="flex flex-col gap-2 px-3.5 py-2.5">
                      <span className="flex items-baseline justify-between gap-3">
                        <span className="text-sm">
                          {PLATFORM_LABELS[row.platform] ?? row.platform}
                        </span>
                        <Badge tone={share >= 60 ? "good" : share > 0 ? "warn" : undefined} mono>
                          {share}% usable
                        </Badge>
                      </span>
                      <span className="flex flex-wrap items-center gap-1.5 text-xs text-fg-muted">
                        <span className="num">{formatNumber(row.pages)} pages</span>
                        {OUTCOMES.filter((outcome) => row[outcome.key] > 0).map((outcome) => (
                          <span
                            key={outcome.key}
                            className="num rounded-ctl border border-line bg-surface-2 px-2 py-0.5"
                          >
                            {row[outcome.key]} {outcome.label}
                          </span>
                        ))}
                      </span>
                    </li>
                  );
                })}
              </ul>
            ) : sources.data ? (
              <p className="rounded-card border border-line bg-surface-2 px-3.5 py-2.5 text-xs text-fg-muted">
                No page has been read yet.{" "}
                {sources.data.live
                  ? "Run a search and this fills in per platform."
                  : "Reading starts once SCRAPEGRAPH_API_KEY is set."}
              </p>
            ) : null}
          </CardBody>
        </Card>

        <Card className="border-bad/30">
          <CardHeader title="Reset demo data" hint="Clears searches you created, saved flags, statuses and notes" />
          <CardBody>
            <Button variant="danger" onClick={() => setConfirmReset(true)}>
              <Trash2 />
              Reset demo data
            </Button>
          </CardBody>
        </Card>
      </div>

      <Modal
        open={confirmReset}
        onOpenChange={setConfirmReset}
        title="Reset demo data?"
        description="Searches you started, saved leads, statuses and notes are removed. Fixture leads come back unchanged."
        footer={
          <>
            <Button variant="ghost" onClick={() => setConfirmReset(false)}>
              Cancel
            </Button>
            <Button variant="danger" onClick={reset}>
              Reset
            </Button>
          </>
        }
      >
        <p className="text-sm text-fg-muted">
          {IS_MOCK
            ? "This only touches browser storage — nothing is stored on a server in mock mode."
            : "This empties the workspace tables in PostgreSQL and re-applies the seed. Nothing outside this demo is affected."}
        </p>
      </Modal>
    </>
  );
}
