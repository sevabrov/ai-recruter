"use client";

import { ExternalLink, Eye, EyeOff, ShieldCheck } from "lucide-react";
import { useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Hint } from "@/components/ui/controls";
import { EmptyState, Eyebrow, PlatformIcon, Skeleton } from "@/components/ui/misc";
import {
  REJECTION_GROUPS,
  rejectionMeta,
  type RejectionGroup,
} from "@/lib/domain";
import { cn, formatNumber } from "@/lib/utils";
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
  const [reason, setReason] = useState<RejectionReason | null>(null);

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
        title="Nothing was turned away"
        body="Every candidate this search discovered became a lead. Searches that ran before this list existed show nothing here."
      />
    );
  }

  const counts = list.byReason;
  const chips = REJECTION_GROUPS.flatMap((group) =>
    Object.entries(counts)
      .map(([id, count]) => ({ id: id as RejectionReason, count: count ?? 0 }))
      .filter((entry) => entry.count > 0 && rejectionMeta(entry.id).group === group.id),
  );
  const shown = reason ? list.items.filter((entry) => entry.reason === reason) : list.items;

  return (
    <div className="flex flex-col">
      <div className="grid grid-cols-1 gap-px border-b border-line bg-line sm:grid-cols-3">
        {REJECTION_GROUPS.map((group) => (
          <GroupTile key={group.id} group={group.id} label={group.label} note={group.note} counts={counts} />
        ))}
      </div>

      <div className="flex flex-wrap items-center gap-1.5 border-b border-line px-4 py-3">
        <Chip active={reason === null} onClick={() => setReason(null)}>
          All {formatNumber(list.total)}
        </Chip>
        {chips.map((entry) => {
          const meta = rejectionMeta(entry.id);
          return (
            <Hint key={entry.id} label={meta.hint}>
              <Chip active={reason === entry.id} onClick={() => setReason(entry.id)}>
                {meta.label} {formatNumber(entry.count)}
              </Chip>
            </Hint>
          );
        })}
      </div>

      {shown.length ? (
        <div className="overflow-x-auto">
          <table className="w-full min-w-[48rem] border-collapse text-sm">
            <thead>
              <tr className="border-b border-line">
                <Th className="pl-5">Candidate</Th>
                <Th className="w-24">Promise</Th>
                <Th className="w-44">Refused because</Th>
                <Th className="pr-5">Which is</Th>
              </tr>
            </thead>
            <tbody>
              {shown.map((entry) => (
                <Row key={entry.id} entry={entry} />
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <EmptyState
          title="Nothing under this reason"
          body="The counts above cover the whole run; this page of the list does not reach it."
          action={
            <Button variant="secondary" size="sm" onClick={() => setReason(null)}>
              Show all
            </Button>
          }
        />
      )}

      {list.items.length < list.total ? (
        <p className="px-5 py-3 text-xs text-fg-faint">
          Showing the {formatNumber(list.items.length)} most promising of{" "}
          {formatNumber(list.total)}. The counts above are over the whole run.
        </p>
      ) : null}
    </div>
  );
}

function Row({ entry }: { entry: RejectedCandidate }) {
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
          <span className="min-w-0">
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

      <td className="num text-fg-muted">
        {typeof entry.promise === "number" ? entry.promise : "—"}
      </td>

      <td>
        <Badge tone={meta.tone}>{meta.label}</Badge>
      </td>

      <td className="max-w-md pr-5 py-2.5 text-xs leading-relaxed text-fg-muted">
        <span className="flex items-start gap-1.5">
          {entry.read ? (
            <Hint label="The page itself was opened and read.">
              <Eye className="mt-0.5 size-3 shrink-0 text-fg-faint" />
            </Hint>
          ) : (
            <Hint label="Nobody opened this page — the verdict rests on the search result alone.">
              <EyeOff className="mt-0.5 size-3 shrink-0 text-warn" />
            </Hint>
          )}
          <span>{entry.detail}</span>
        </span>
      </td>
    </tr>
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
        {formatNumber(total)}
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
