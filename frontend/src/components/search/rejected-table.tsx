"use client";

import { ExternalLink, Eye, EyeOff, ShieldCheck } from "lucide-react";
import { useTranslations } from "next-intl";
import { useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Hint } from "@/components/ui/controls";
import { EmptyState, Eyebrow, PlatformIcon, Skeleton } from "@/components/ui/misc";
import {
  isKnownRejectionReason,
  REJECTION_GROUPS,
  rejectionMeta,
  type RejectionGroup,
} from "@/lib/domain";
import { useNumbers } from "@/lib/format";
import { cn } from "@/lib/utils";
import type { RejectedCandidate, RejectedList, RejectionReason } from "@/services/types";

/**
 * Everything the search turned away.
 *
 * The list is not an apology for a thin result — it is the only way to check one.
 * So it opens with the three groups that decide whether a lead was lost: pages
 * nobody opened, profiles the chosen sources excluded, and candidates that were
 * read and failed a requirement. Only the first can be hiding somebody.
 */
export function RejectedTable({
  list,
  isPending,
}: {
  list?: RejectedList;
  isPending?: boolean;
}) {
  const t = useTranslations("rejected");
  const common = useTranslations("common");
  const reasons = useTranslations("domain.rejectionReason");
  const groups = useTranslations("domain.rejectionGroup");
  const [reason, setReason] = useState<RejectionReason | null>(null);

  /** Unknown ids from a newer backend render raw rather than as a message path. */
  const reasonLabel = (id: RejectionReason) =>
    isKnownRejectionReason(id) ? reasons(`${id}.label`) : id;
  const reasonHint = (id: RejectionReason) =>
    isKnownRejectionReason(id) ? reasons(`${id}.hint`) : "";

  if (isPending) {
    return (
      <div className="flex flex-col gap-px p-4">
        {[0, 1, 2, 3, 4, 5].map((index) => (
          <Skeleton key={index} className="h-12" />
        ))}
      </div>
    );
  }

  if (!list || list.total === 0) {
    return (
      <EmptyState
        icon={<ShieldCheck className="size-4" />}
        title={t("nothingTurnedAwayTitle")}
        body={t("nothingTurnedAwayBody")}
      />
    );
  }

  const counts = list.byReason;
  const chips = REJECTION_GROUPS.flatMap((group) =>
    Object.entries(counts)
      .map(([id, count]) => ({ id: id as RejectionReason, count: count ?? 0 }))
      .filter((entry) => entry.count > 0 && rejectionMeta(entry.id).group === group),
  );
  const shown = reason ? list.items.filter((entry) => entry.reason === reason) : list.items;

  return (
    <div className="flex flex-col">
      <div className="grid grid-cols-1 gap-px border-b border-line bg-line sm:grid-cols-3">
        {REJECTION_GROUPS.map((group) => (
          <GroupTile
            key={group}
            group={group}
            label={groups(`${group}.label`)}
            note={groups(`${group}.note`)}
            counts={counts}
          />
        ))}
      </div>

      <div className="flex flex-wrap items-center gap-1.5 border-b border-line px-4 py-3">
        <Chip active={reason === null} onClick={() => setReason(null)}>
          {t("all", { count: list.total })}
        </Chip>
        {chips.map((entry) => (
          <Hint key={entry.id} label={reasonHint(entry.id)}>
            <Chip active={reason === entry.id} onClick={() => setReason(entry.id)}>
              {t("chip", { label: reasonLabel(entry.id), count: entry.count })}
            </Chip>
          </Hint>
        ))}
      </div>

      {shown.length ? (
        <div className="overflow-x-auto">
          <table className="w-full min-w-[52rem] table-fixed border-collapse text-sm">
            <thead>
              <tr className="border-b border-line">
                <Th className="pl-5">{t("candidate")}</Th>
                <Th className="w-24">{t("promise")}</Th>
                <Th className="w-64">{t("refusedBecause")}</Th>
                <Th className="w-64 pr-5">{t("whichIs")}</Th>
              </tr>
            </thead>
            <tbody>
              {shown.map((entry) => (
                <Row key={entry.id} entry={entry} label={reasonLabel(entry.reason)} />
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <EmptyState
          title={t("nothingUnderReasonTitle")}
          body={t("nothingUnderReasonBody")}
          action={
            <Button variant="secondary" size="sm" onClick={() => setReason(null)}>
              {common("showAll")}
            </Button>
          }
        />
      )}

      {list.items.length < list.total ? (
        <p className="px-5 py-3 text-xs text-fg-faint">
          {t("showingMostPromising", { shown: list.items.length, total: list.total })}
        </p>
      ) : null}
    </div>
  );
}

function Row({ entry, label }: { entry: RejectedCandidate; label: string }) {
  const t = useTranslations("rejected");
  const common = useTranslations("common");
  const meta = rejectionMeta(entry.reason);

  return (
    <tr className="group border-b border-line last:border-0 transition-colors hover:bg-surface-2">
      <td className="py-2.5 pl-5">
        <a
          href={entry.url}
          target="_blank"
          rel="noreferrer noopener"
          className="flex items-start gap-2.5"
        >
          <PlatformIcon platform={entry.platform} className="mt-0.5 shrink-0 text-fg-faint" />
          <span className="min-w-0 flex-1">
            <span className="flex items-center gap-1.5">
              <span className="truncate font-medium group-hover:text-accent">
                {entry.name || entry.title || entry.url}
              </span>
              <ExternalLink className="size-3 shrink-0 text-fg-faint" />
            </span>
            <span className="block truncate text-xs text-fg-muted">
              {entry.title || entry.snippet || entry.url}
            </span>
          </span>
        </a>
      </td>

      <td className="num text-fg-muted text-center">
        {typeof entry.promise === "number" ? entry.promise : common("dash")}
      </td>

      <td className="px-2">
        <Badge tone={meta.tone} className="max-w-full">
          <span className="truncate" title={label}>
            {label}
          </span>
        </Badge>
      </td>

      <td className="max-w-md pr-5 py-2.5 text-xs leading-relaxed text-fg-muted">
        <span className="flex items-start gap-1.5">
          {entry.read ? (
            <Hint label={t("wasRead")}>
              <Eye className="mt-0.5 size-3 shrink-0 text-fg-faint" />
            </Hint>
          ) : (
            <Hint label={t("wasNotRead")}>
              <EyeOff className="mt-0.5 size-3 shrink-0 text-warn" />
            </Hint>
          )}
          {/* Written by the pipeline, so it arrives in the backend's language. */}
          <span>{entry.detail}</span>
        </span>
        {entry.authorUrl ? <PostAuthor entry={entry} /> : null}
      </td>
    </tr>
  );
}

/**
 * What became of the person who published a refused post. Without it a post
 * reads as a lost lead, when its author was followed and judged — and the
 * answer is in the other list, or further down this one.
 */
function PostAuthor({ entry }: { entry: RejectedCandidate }) {
  const t = useTranslations("rejected");
  const reasons = useTranslations("domain.rejectionReason");
  const outcome = entry.authorOutcome;

  if (!outcome) {
    return <p className="mt-1.5 text-fg-faint">{t("authorNotJudged")}</p>;
  }

  const verdict =
    outcome === "lead"
      ? t("authorBecameLead")
      : t("authorRefused", {
          reason: isKnownRejectionReason(outcome) ? reasons(`${outcome}.label`) : outcome,
        });

  return (
    <p className="mt-1.5 flex flex-wrap items-center gap-1">
      <span>{t("authorChecked")}</span>
      <a
        href={entry.authorUrl ?? undefined}
        target="_blank"
        rel="noreferrer noopener"
        className="font-medium text-fg hover:text-accent"
      >
        {entry.authorName || entry.authorUrl}
      </a>
      <span>—</span>
      <span className={outcome === "lead" ? "font-medium text-accent" : undefined}>{verdict}</span>
    </p>
  );
}

function GroupTile({
  group,
  label,
  note,
  counts,
}: {
  group: RejectionGroup;
  label: string;
  note: string;
  counts: RejectedList["byReason"];
}) {
  const { number } = useNumbers();
  const total = Object.entries(counts).reduce(
    (sum, [id, count]) =>
      rejectionMeta(id as RejectionReason).group === group ? sum + (count ?? 0) : sum,
    0,
  );

  return (
    <div className="bg-surface px-5 py-4">
      <Eyebrow>{label}</Eyebrow>
      <p
        className={cn(
          "num font-display mt-1.5 text-2xl leading-none font-semibold",
          group === "unseen" && total > 0 && "text-warn",
        )}
      >
        {number(total)}
      </p>
      <p className="mt-1.5 text-xs leading-relaxed text-fg-muted">{note}</p>
    </div>
  );
}

function Chip({
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
      className={cn(
        "rounded-pill border px-2.5 py-1 text-xs font-medium transition-colors",
        active
          ? "border-accent-line bg-accent-soft text-accent"
          : "border-line text-fg-muted hover:bg-surface-2 hover:text-fg",
      )}
    >
      {children}
    </button>
  );
}

function Th({ children, className }: { children: React.ReactNode; className?: string }) {
  return (
    <th className={cn("label px-2 py-2.5 text-left font-normal text-fg-faint", className)}>
      {children}
    </th>
  );
}
