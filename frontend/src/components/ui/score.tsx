import { SCORE_TIER_LABELS, scoreTier, scoreTierTone } from "@/lib/domain";
import { cn } from "@/lib/utils";
import { Badge } from "./badge";

const TONE_TEXT = {
  good: "text-good",
  warn: "text-warn",
  neutral: "text-fg-muted",
  accent: "text-accent",
  bad: "text-bad",
  info: "text-info",
} as const;

const TONE_STROKE = {
  good: "stroke-good",
  warn: "stroke-warn",
  neutral: "stroke-fg-faint",
  accent: "stroke-accent",
  bad: "stroke-bad",
  info: "stroke-info",
} as const;

const TONE_BAR = {
  good: "bg-good",
  warn: "bg-warn",
  neutral: "bg-fg-faint",
  accent: "bg-accent",
  bad: "bg-bad",
  info: "bg-info",
} as const;

/** Compact readout used in tables: number plus a proportional bar. */
export function ScoreBar({ score, className }: { score: number; className?: string }) {
  const tone = scoreTierTone(score);
  return (
    <div className={cn("flex items-center gap-2.5", className)}>
      <span className={cn("num w-7 text-right text-sm font-semibold", TONE_TEXT[tone])}>
        {score}
      </span>
      <span className="h-1 w-12 overflow-hidden rounded-pill bg-surface-3">
        <span
          className={cn("block h-full rounded-pill", TONE_BAR[tone])}
          style={{ width: `${score}%` }}
        />
      </span>
    </div>
  );
}

/** Hero readout on the lead page: arc meter around the score. */
export function ScoreDial({ score, size = 132 }: { score: number; size?: number }) {
  const tone = scoreTierTone(score);
  const radius = 54;
  const circumference = 2 * Math.PI * radius;
  const sweep = 0.78; // leave a gap at the bottom so the arc reads as a gauge
  const arc = circumference * sweep;

  return (
    <div className="relative grid place-items-center" style={{ width: size, height: size }}>
      <svg viewBox="0 0 128 128" className="-rotate-[125deg] size-full">
        <circle
          cx="64"
          cy="64"
          r={radius}
          fill="none"
          strokeWidth="7"
          strokeLinecap="round"
          className="stroke-surface-3"
          strokeDasharray={`${arc} ${circumference}`}
        />
        <circle
          cx="64"
          cy="64"
          r={radius}
          fill="none"
          strokeWidth="7"
          strokeLinecap="round"
          className={cn(TONE_STROKE[tone], "transition-[stroke-dasharray] duration-700")}
          strokeDasharray={`${(arc * score) / 100} ${circumference}`}
        />
      </svg>
      <div className="absolute flex flex-col items-center">
        <span className={cn("num font-display text-4xl leading-none font-semibold", TONE_TEXT[tone])}>
          {score}
        </span>
        <span className="label mt-1 text-fg-faint">/ 100</span>
      </div>
    </div>
  );
}

export function ScoreTierBadge({ score }: { score: number }) {
  return <Badge tone={scoreTierTone(score)}>{SCORE_TIER_LABELS[scoreTier(score)]}</Badge>;
}
