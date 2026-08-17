import { SIGNAL_LABELS } from "@/lib/domain";
import { cn } from "@/lib/utils";
import type { ScoreComponent } from "@/services/types";

/** Explainable scoring: every point is attributed (spec §38). */
export function ScoreBreakdown({
  breakdown,
  total,
}: {
  breakdown: ScoreComponent[];
  total: number;
}) {
  return (
    <ul className="flex flex-col gap-2">
      {breakdown.map((component) => {
        const full = component.awarded === component.max;
        const empty = component.awarded === 0;
        return (
          <li key={component.type} className="grid grid-cols-[1fr_auto] items-center gap-x-3">
            <span className="flex items-center gap-2">
              <span
                className={cn(
                  "num w-8 text-right text-sm font-medium",
                  empty ? "text-fg-faint" : full ? "text-good" : "text-fg",
                )}
              >
                {empty ? "—" : `+${component.awarded}`}
              </span>
              <span className={cn("text-sm", empty ? "text-fg-faint" : "text-fg-muted")}>
                {SIGNAL_LABELS[component.type]}
              </span>
            </span>

            <span className="flex items-center gap-2">
              <span className="h-1 w-14 overflow-hidden rounded-pill bg-surface-3">
                <span
                  className={cn("block h-full rounded-pill", empty ? "bg-transparent" : "bg-accent")}
                  style={{ width: `${(component.awarded / Math.max(component.max, 1)) * 100}%` }}
                />
              </span>
              <span className="num w-8 text-right text-2xs text-fg-faint">/ {component.max}</span>
            </span>
          </li>
        );
      })}

      <li className="mt-1 flex items-baseline justify-between border-t border-line pt-2.5">
        <span className="label text-fg-faint">Total</span>
        <span className="num font-display text-lg font-semibold">{total} / 100</span>
      </li>
    </ul>
  );
}
