"use client";

/**
 * Small charts, one measure each.
 *
 * Colour does no identifying work here: every series is single-hue, and identity
 * comes from the platform icon and the text label. Score buckets are the one
 * exception — they reuse the app's score-tier semantics (high / medium / low),
 * always alongside the numeric range, so the tier is never colour-alone.
 */

import { PLATFORM_LABELS } from "@/lib/domain";
import { cn, formatNumber } from "@/lib/utils";
import { Hint } from "@/components/ui/controls";
import { PlatformIcon } from "@/components/ui/misc";
import type { ScoreBucket, SourceShare } from "@/services/types";

export function SourceShareBars({ items }: { items: SourceShare[] }) {
  const max = Math.max(...items.map((item) => item.share), 1);

  return (
    <ul className="flex flex-col gap-2.5">
      {items.map((item) => (
        <li key={item.platform} className="grid grid-cols-[7.5rem_1fr_2.75rem] items-center gap-3">
          <span className="flex items-center gap-2 text-sm text-fg-muted">
            <PlatformIcon platform={item.platform} className="text-fg-faint" />
            <span className="truncate">{PLATFORM_LABELS[item.platform]}</span>
          </span>

          <Hint label={`${formatNumber(item.leads)} leads discovered via ${PLATFORM_LABELS[item.platform]}`}>
            <span className="block h-2 cursor-default overflow-hidden rounded-r-[4px] bg-surface-2">
              <span
                className="block h-full rounded-r-[4px] bg-accent transition-[width] duration-500"
                style={{ width: `${(item.share / max) * 100}%` }}
              />
            </span>
          </Hint>

          <span className="num text-right text-sm text-fg">{item.share}%</span>
        </li>
      ))}
    </ul>
  );
}

const BUCKET_TONE = (from: number) =>
  from >= 85 ? "bg-good" : from >= 70 ? "bg-warn" : "bg-fg-faint";

export function ScoreHistogram({ buckets }: { buckets: ScoreBucket[] }) {
  const max = Math.max(...buckets.map((bucket) => bucket.count), 1);

  return (
    <ul className="flex flex-col gap-2.5">
      {buckets.map((bucket) => (
        <li key={bucket.label} className="grid grid-cols-[4.25rem_1fr_3rem] items-center gap-3">
          <span className="num text-sm text-fg-muted">{bucket.label}</span>
          <span className="block h-2 overflow-hidden rounded-r-[4px] bg-surface-2">
            <span
              className={cn("block h-full rounded-r-[4px] transition-[width] duration-500", BUCKET_TONE(bucket.from))}
              style={{ width: `${(bucket.count / max) * 100}%` }}
            />
          </span>
          <span className="num text-right text-sm text-fg-muted">{formatNumber(bucket.count)}</span>
        </li>
      ))}
    </ul>
  );
}

export function WeeklyLeadsChart({ data }: { data: { day: string; count: number }[] }) {
  const max = Math.max(...data.map((point) => point.count), 1);
  const peak = data.reduce((best, point) => (point.count > best.count ? point : best), data[0]);

  return (
    <div className="flex flex-col gap-3">
      <div className="flex h-28 items-end gap-2" role="img" aria-label="Leads discovered per day this week">
        {data.map((point) => (
          <Hint key={point.day} label={`${point.day}: ${formatNumber(point.count)} leads`}>
            <div className="flex h-full flex-1 cursor-default flex-col justify-end gap-1.5">
              <span
                className={cn(
                  "num text-center text-2xs",
                  point.day === peak.day ? "text-fg" : "text-transparent",
                )}
              >
                {point.count}
              </span>
              <span
                className={cn(
                  "block w-full rounded-t-[4px] transition-[height] duration-500",
                  point.day === peak.day ? "bg-accent" : "bg-accent/45",
                )}
                style={{ height: `${(point.count / max) * 100}%` }}
              />
            </div>
          </Hint>
        ))}
      </div>
      <div className="flex gap-2 border-t border-line pt-2">
        {data.map((point) => (
          <span key={point.day} className="flex-1 text-center text-2xs text-fg-faint">
            {point.day}
          </span>
        ))}
      </div>
    </div>
  );
}
