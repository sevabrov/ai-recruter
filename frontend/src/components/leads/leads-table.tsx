"use client";

import { Bookmark, Mail, Minus } from "lucide-react";
import Link from "next/link";
import { leadStatusMeta, SIGNAL_SHORT_LABELS } from "@/lib/domain";
import { cn, initials } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import { Hint } from "@/components/ui/controls";
import { PlatformIcon, Skeleton } from "@/components/ui/misc";
import { ScoreBar } from "@/components/ui/score";
import { useUpdateLead } from "@/services/hooks";
import type { Lead, SignalType } from "@/services/types";

const SIGNAL_COLUMNS: SignalType[] = ["mlm", "beauty", "leadership"];

export function LeadsTable({
  leads,
  isPending,
  showStatus = true,
}: {
  leads: Lead[];
  isPending?: boolean;
  showStatus?: boolean;
}) {
  const updateLead = useUpdateLead();

  if (isPending) {
    return (
      <div className="flex flex-col gap-px p-4">
        {[0, 1, 2, 3, 4, 5].map((index) => (
          <Skeleton key={index} className="h-12" />
        ))}
      </div>
    );
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[52rem] border-collapse text-sm">
        <thead>
          <tr className="border-b border-line">
            <Th className="pl-5">Candidate</Th>
            <Th className="w-28">Score</Th>
            <Th className="w-28">Platforms</Th>
            <Th className="w-36">Location</Th>
            {SIGNAL_COLUMNS.map((signal) => (
              <Th key={signal} className="w-20 text-center">
                {SIGNAL_SHORT_LABELS[signal]}
              </Th>
            ))}
            {showStatus ? <Th className="w-32">Status</Th> : null}
            <Th className="w-12 pr-5 text-right">
              <span className="sr-only">Save</span>
            </Th>
          </tr>
        </thead>

        <tbody>
          {leads.map((lead) => {
            const status = leadStatusMeta(lead.status);
            return (
              <tr
                key={lead.id}
                className="group border-b border-line last:border-0 transition-colors hover:bg-surface-2"
              >
                <td className="py-2.5 pl-5">
                  <Link href={`/leads/${lead.id}`} className="flex items-center gap-3">
                    <span className="grid size-8 shrink-0 place-items-center rounded-full border border-line bg-surface-2 text-2xs font-medium text-fg-muted">
                      {initials(lead.name)}
                    </span>
                    <span className="min-w-0">
                      <span className="flex items-center gap-1.5">
                        <span className="truncate font-medium group-hover:text-accent">
                          {lead.name}
                        </span>
                        {lead.contacts.email ? (
                          <Hint label={lead.contacts.email}>
                            <Mail className="size-3 shrink-0 text-fg-faint" />
                          </Hint>
                        ) : null}
                      </span>
                      <span className="block truncate text-xs text-fg-muted">{lead.headline}</span>
                    </span>
                  </Link>
                </td>

                <td>
                  <ScoreBar score={lead.score} />
                </td>

                <td>
                  <span className="flex items-center gap-1.5 text-fg-muted">
                    {lead.platforms.slice(0, 4).map((platform) => (
                      <Hint key={platform.url} label={platform.handle ?? platform.url}>
                        <a
                          href={platform.url}
                          target="_blank"
                          rel="noreferrer noopener"
                          className="transition-colors hover:text-accent"
                          onClick={(event) => event.stopPropagation()}
                        >
                          <PlatformIcon platform={platform.platform} />
                        </a>
                      </Hint>
                    ))}
                  </span>
                </td>

                <td className="text-fg-muted">
                  <span className="block truncate">
                    {[lead.location?.city, lead.location?.country].filter(Boolean).join(", ") || "—"}
                  </span>
                </td>

                {SIGNAL_COLUMNS.map((signalType) => {
                  const signal = lead.signals.find((entry) => entry.type === signalType);
                  return (
                    <td key={signalType} className="text-center">
                      {signal?.detected ? (
                        <Hint
                          label={
                            <span>
                              {signal.evidence}
                              <span className="mt-1 block text-fg-faint">
                                confidence {Math.round(signal.confidence * 100)}%
                              </span>
                            </span>
                          }
                        >
                          <span className="num inline-flex cursor-help items-center gap-1 text-good">
                            <span className="text-sm">✓</span>
                            <span className="text-2xs opacity-70">
                              {Math.round(signal.confidence * 100)}
                            </span>
                          </span>
                        </Hint>
                      ) : (
                        <Minus className="mx-auto size-3 text-fg-faint" />
                      )}
                    </td>
                  );
                })}

                {showStatus ? (
                  <td>
                    <Badge tone={status.tone}>{status.label}</Badge>
                  </td>
                ) : null}

                <td className="pr-5 text-right">
                  <button
                    type="button"
                    aria-label={lead.saved ? `Unsave ${lead.name}` : `Save ${lead.name}`}
                    onClick={() => updateLead.mutate({ id: lead.id, input: { saved: !lead.saved } })}
                    className={cn(
                      "rounded-ctl p-1.5 transition-colors",
                      lead.saved
                        ? "text-accent hover:bg-accent-soft"
                        : "text-fg-faint hover:bg-surface-3 hover:text-fg",
                    )}
                  >
                    <Bookmark className={cn("size-4", lead.saved && "fill-current")} />
                  </button>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function Th({ children, className }: { children: React.ReactNode; className?: string }) {
  return (
    <th className={cn("label px-2 py-2.5 text-left font-normal text-fg-faint", className)}>
      {children}
    </th>
  );
}
