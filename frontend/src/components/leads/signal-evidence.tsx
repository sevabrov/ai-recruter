"use client";

import { ExternalLink, Minus } from "lucide-react";
import { PLATFORM_LABELS, SIGNAL_LABELS } from "@/lib/domain";
import { cn } from "@/lib/utils";
import { ConfidenceMeter, PlatformIcon } from "@/components/ui/misc";
import type { LeadSignal } from "@/services/types";

/**
 * The evidence panel. A signal is never rendered as a bare boolean — the quote
 * that triggered it and the page it came from travel with it (spec §16).
 */
export function SignalEvidence({ signals }: { signals: LeadSignal[] }) {
  const detected = signals.filter((signal) => signal.detected);
  const missing = signals.filter((signal) => !signal.detected);

  return (
    <div className="flex flex-col">
      {detected.map((signal) => (
        <article key={signal.type} className="border-b border-line px-5 py-4 last:border-0">
          <header className="flex flex-wrap items-center justify-between gap-3">
            <h3 className="flex items-center gap-2 text-sm font-medium">
              <span className="text-good" aria-hidden>
                ✓
              </span>
              {SIGNAL_LABELS[signal.type]}
            </h3>
            <ConfidenceMeter value={signal.confidence} />
          </header>

          {signal.evidence ? (
            <blockquote
              className={cn(
                "mt-2.5 border-l-2 border-accent-line pl-3 text-sm leading-relaxed text-fg-muted",
              )}
            >
              {signal.evidence}
            </blockquote>
          ) : null}

          {signal.sourceUrl ? (
            <a
              href={signal.sourceUrl}
              target="_blank"
              rel="noreferrer noopener"
              className="mt-2.5 inline-flex items-center gap-1.5 text-xs text-fg-faint transition-colors hover:text-accent"
            >
              {signal.sourcePlatform ? <PlatformIcon platform={signal.sourcePlatform} /> : null}
              {signal.sourcePlatform ? PLATFORM_LABELS[signal.sourcePlatform] : "Source"}
              <ExternalLink className="size-3" />
            </a>
          ) : null}
        </article>
      ))}

      {missing.length ? (
        <div className="flex flex-wrap items-center gap-x-4 gap-y-2 border-t border-line bg-surface-2 px-5 py-3">
          <span className="label text-fg-faint">Not detected</span>
          {missing.map((signal) => (
            <span key={signal.type} className="flex items-center gap-1.5 text-xs text-fg-faint">
              <Minus className="size-3" />
              {SIGNAL_LABELS[signal.type]}
            </span>
          ))}
        </div>
      ) : null}
    </div>
  );
}
