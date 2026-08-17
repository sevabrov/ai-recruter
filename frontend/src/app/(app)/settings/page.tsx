"use client";

import { useQueryClient } from "@tanstack/react-query";
import { Check, Database, Monitor, Trash2 } from "lucide-react";
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
import { cn } from "@/lib/utils";
import { DATA_SOURCE, IS_MOCK } from "@/services";
import { resetMockState } from "@/services/mock/mock-db";

/** Concurrency + provider settings are server-owned (spec §52); shown read-only. */
const PROVIDERS = [
  { name: "Brave Search", role: "Primary web search provider", phase: "Phase 4" },
  { name: "ScrapeGraphAI", role: "Structured extraction from candidate pages", phase: "Phase 5" },
  { name: "OpenAI", role: "Signal detection on extracted profiles", phase: "Phase 6" },
  { name: "PostgreSQL + Redis", role: "Persistence and the worker queue", phase: "Phase 3 / 7" },
];

const LIMITS = [
  { key: "SEARCH_CONCURRENCY", value: "10" },
  { key: "EXTRACTION_CONCURRENCY", value: "10" },
  { key: "LLM_CONCURRENCY", value: "10" },
];

export default function SettingsPage() {
  const { preference, resolved, setPreference } = useTheme();
  const [confirmReset, setConfirmReset] = useState(false);
  const [autoSaveHigh, setAutoSaveHigh] = useState(false);
  const [notifyDone, setNotifyDone] = useState(true);
  const queryClient = useQueryClient();
  const { toast } = useToast();

  const reset = () => {
    resetMockState();
    queryClient.clear();
    setConfirmReset(false);
    toast({ title: "Demo data reset", description: "Fixtures are back to their original state." });
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
              <Badge tone={IS_MOCK ? "warn" : "good"} mono>
                <Dot tone={IS_MOCK ? "warn" : "good"} />
                {DATA_SOURCE}
              </Badge>
            }
          />
          <CardBody className="flex flex-col gap-4">
            <p className="text-sm text-fg-muted">
              {IS_MOCK
                ? "The app is running on in-browser fixtures. No search API, scraper or model is called. Switch by setting NEXT_PUBLIC_DATA_SOURCE=api once the backend is live."
                : "The app is talking to the FastAPI backend."}
            </p>

            <div>
              <Eyebrow className="mb-2">Backend integrations</Eyebrow>
              <ul className="divide-y divide-line rounded-card border border-line">
                {PROVIDERS.map((provider) => (
                  <li key={provider.name} className="flex items-center gap-3 px-3.5 py-2.5">
                    <Database className="size-3.5 shrink-0 text-fg-faint" />
                    <span className="min-w-0 flex-1">
                      <span className="block text-sm">{provider.name}</span>
                      <span className="block truncate text-xs text-fg-muted">{provider.role}</span>
                    </span>
                    <Badge>{provider.phase}</Badge>
                  </li>
                ))}
              </ul>
            </div>

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
          This only touches browser storage — nothing is stored on a server in Phase 1.
        </p>
      </Modal>
    </>
  );
}
