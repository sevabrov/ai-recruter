"use client";

import { Bookmark, Mail, Minus } from "lucide-react";
import { useTranslations } from "next-intl";
import { Link } from "@/i18n/navigation";
import { leadStatusMeta } from "@/lib/domain";
import { cn, initials } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import { Hint } from "@/components/ui/controls";
import { PlatformIcon, Skeleton } from "@/components/ui/misc";
import { ScoreBar } from "@/components/ui/score";
import { useUpdateLead } from "@/services/hooks";
import { useVocabulary } from "@/lib/vocabulary";
import type { Lead, Requirement } from "@/services/types";

/** How many of a search's requirements get a column of their own. */
const REQUIREMENT_COLUMNS = 3;

export function LeadsTable({
  leads,
  isPending,
  showStatus = true,
  requirements,
}: {
  leads: Lead[];
  isPending?: boolean;
  showStatus?: boolean;
  /**
   * The search's requirements, when the list is one search's results: its
   * weightiest ones become columns. Across searches every lead was judged by
   * requirements of its own, so one column says how many of them it met.
   */
  requirements?: Requirement[];
}) {
  const t = useTranslations("leadsTable");
  const vocabulary = useVocabulary();
  const columns = (requirements ?? [])
    .filter((requirement) => requirement.id !== "location" && requirement.weight > 0)
    .sort((a, b) => b.weight - a.weight)
    .slice(0, REQUIREMENT_COLUMNS);
  const statuses = useTranslations("domain.leadStatus");
  const common = useTranslations("common");
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
            <Th className="pl-5">{t("candidate")}</Th>
            <Th className="w-28">{t("score")}</Th>
            <Th className="w-28">{t("platforms")}</Th>
            <Th className="w-36">{t("location")}</Th>
            {columns.length ? (
              columns.map((requirement) => (
                <Th key={requirement.id} className="w-24 text-center">
                  <span className="block truncate" title={vocabulary.requirement(requirement)}>
                    {vocabulary.requirement(requirement)}
                  </span>
                </Th>
              ))
            ) : (
              <Th className="w-24 text-center">{t("requirementsMet")}</Th>
            )}
            {showStatus ? <Th className="w-32">{t("status")}</Th> : null}
            <Th className="w-12 pr-5 text-right">
              <span className="sr-only">{t("save")}</span>
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
                    {[lead.location?.city, lead.location?.country].filter(Boolean).join(", ") ||
                      common("dash")}
                  </span>
                </td>

                {!columns.length ? (
                  <td className="text-center">
                    <RequirementsMet lead={lead} />
                  </td>
                ) : null}
                {columns.map((requirement) => {
                  const signal = lead.signals.find((entry) => entry.type === requirement.id);
                  return (
                    <td key={requirement.id} className="text-center">
                      {signal?.detected ? (
                        <Hint
                          label={
                            <span>
                              {signal.evidence}
                              <span className="mt-1 block text-fg-faint">
                                {t("confidence", {
                                  percent: Math.round(signal.confidence * 100),
                                })}
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
                    <Badge tone={status.tone}>{statuses(status.id)}</Badge>
                  </td>
                ) : null}

                <td className="pr-5 text-right">
                  <button
                    type="button"
                    aria-label={
                      lead.saved
                        ? t("unsaveLead", { name: lead.name })
                        : t("saveLead", { name: lead.name })
                    }
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

/** "3 / 4": how many of the requirements this lead was judged by it visibly met. */
function RequirementsMet({ lead }: { lead: Lead }) {
  const t = useTranslations("leadsTable");
  const vocabulary = useVocabulary();
  const judged = lead.scoreBreakdown.filter((row) => row.max > 0);
  const met = judged.filter((row) => row.awarded > 0);
  if (!judged.length) return <Minus className="mx-auto size-3 text-fg-faint" />;
  return (
    <Hint
      label={
        <span className="flex flex-col gap-0.5">
          {judged.map((row) => (
            <span key={row.type} className={row.awarded > 0 ? "" : "text-fg-faint"}>
              {row.awarded > 0 ? "✓" : "-"} {vocabulary.requirement(row)}
            </span>
          ))}
        </span>
      }
    >
      <span className="num cursor-help text-xs text-fg-muted">
        {t("metOf", { met: met.length, total: judged.length })}
      </span>
    </Hint>
  );
}

function Th({ children, className }: { children: React.ReactNode; className?: string }) {
  return (
    <th className={cn("label px-2 py-2.5 text-left font-normal text-fg-faint", className)}>
      {children}
    </th>
  );
}
