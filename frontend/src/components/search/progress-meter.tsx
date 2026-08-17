"use client";

import { Progress } from "radix-ui";
import { cn } from "@/lib/utils";

const SEGMENTS = 36;

/**
 * Segmented meter — reads as an instrument rather than a loading bar, and the
 * leading segment animates so a slow stage still looks alive.
 */
export function ProgressMeter({
  percent,
  label,
  tone = "accent",
}: {
  percent: number;
  label?: string;
  tone?: "accent" | "good";
}) {
  const filled = Math.round((percent / 100) * SEGMENTS);

  return (
    <div className="flex flex-col gap-2.5">
      <div className="flex items-baseline justify-between gap-4">
        <p className="text-sm text-fg-muted">{label}</p>
        <p className="num font-display text-2xl leading-none font-semibold">{percent}%</p>
      </div>

      <Progress.Root
        value={percent}
        max={100}
        className="flex h-3 gap-[3px] overflow-hidden"
        aria-label={label ?? "Search progress"}
      >
        {Array.from({ length: SEGMENTS }, (_, index) => {
          const isFilled = index < filled;
          const isLeading = index === filled && percent < 100;
          return (
            <span
              key={index}
              className={cn(
                "h-full flex-1 rounded-[2px] transition-colors duration-300",
                isFilled
                  ? tone === "good"
                    ? "bg-good"
                    : "bg-accent"
                  : isLeading
                    ? "animate-pulse-soft bg-accent/50"
                    : "bg-surface-3",
              )}
            />
          );
        })}
      </Progress.Root>
    </div>
  );
}
