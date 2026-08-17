import type { ReactNode } from "react";
import { cn } from "@/lib/utils";
import type { Tone } from "@/lib/domain";

const TONES: Record<Tone, string> = {
  neutral: "bg-surface-2 text-fg-muted border-line",
  accent: "bg-accent-soft text-accent border-accent-line",
  good: "bg-good-soft text-good border-good/25",
  warn: "bg-warn-soft text-warn border-warn/25",
  bad: "bg-bad-soft text-bad border-bad/25",
  info: "bg-info-soft text-info border-info/25",
};

export function Badge({
  children,
  tone = "neutral",
  className,
  mono,
}: {
  children: ReactNode;
  tone?: Tone;
  className?: string;
  mono?: boolean;
}) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-pill border px-2 py-0.5 text-xs font-medium",
        mono && "label px-2 py-1",
        TONES[tone],
        className,
      )}
    >
      {children}
    </span>
  );
}

/** Small state dot — encodes status in form as well as color. */
export function Dot({ tone = "neutral", pulse }: { tone?: Tone; pulse?: boolean }) {
  const color: Record<Tone, string> = {
    neutral: "bg-fg-faint",
    accent: "bg-accent",
    good: "bg-good",
    warn: "bg-warn",
    bad: "bg-bad",
    info: "bg-info",
  };
  return (
    <span
      className={cn("size-1.5 shrink-0 rounded-full", color[tone], pulse && "animate-pulse-soft")}
    />
  );
}
