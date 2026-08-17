import { ArrowDownRight, ArrowUpRight } from "lucide-react";
import { formatNumber } from "@/lib/utils";
import { cn } from "@/lib/utils";
import type { DashboardStat } from "@/services/types";

/**
 * A hero number, not a chart: one measure, no plot, so no legend or tooltip.
 * The delta is the only comparison shown, and it carries an arrow so direction
 * is never color-alone.
 */
export function StatTile({ stat, emphasis }: { stat: DashboardStat; emphasis?: boolean }) {
  const up = (stat.delta ?? 0) >= 0;

  return (
    <div
      className={cn(
        "flex flex-col gap-2 px-5 py-4",
        emphasis && "bg-linear-to-b from-accent-soft/60 to-transparent",
      )}
    >
      <p className="label text-fg-faint">{stat.label}</p>
      <p className="num font-display text-[30px] leading-none font-semibold tracking-tight">
        {formatNumber(stat.value)}
      </p>
      <div className="flex items-center gap-2 text-xs">
        {stat.delta != null ? (
          <span
            className={cn(
              "inline-flex items-center gap-0.5 font-medium",
              up ? "text-good" : "text-bad",
            )}
          >
            {up ? <ArrowUpRight className="size-3" /> : <ArrowDownRight className="size-3" />}
            <span className="num">{Math.abs(stat.delta).toFixed(1)}%</span>
          </span>
        ) : null}
        {stat.hint ? <span className="truncate text-fg-faint">{stat.hint}</span> : null}
      </div>
    </div>
  );
}
