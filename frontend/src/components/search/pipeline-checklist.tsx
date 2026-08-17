"use client";

import { Check, Loader2 } from "lucide-react";
import { PIPELINE_STAGES } from "@/lib/domain";
import { formatNumber } from "@/lib/utils";
import { cn } from "@/lib/utils";
import type { SearchProgress, SearchStage } from "@/services/types";

const STAGE_ORDER: SearchStage[] = [
  "queued",
  "generating_queries",
  "web_search",
  "discovering_profiles",
  "extracting",
  "scoring",
  "deduplicating",
  "done",
];

/** Per-stage detail so the list carries data, not just spinners. */
function stageDetail(stage: SearchStage, progress: SearchProgress) {
  switch (stage) {
    case "generating_queries":
      return `${progress.queriesCompleted} of ${progress.queries} queries`;
    case "web_search":
      return `${formatNumber(progress.urlsDiscovered)} pages discovered`;
    case "discovering_profiles":
      return `${formatNumber(progress.profilesDiscovered)} profiles identified`;
    case "extracting":
      return `${formatNumber(progress.profilesProcessed)} of ${formatNumber(progress.profilesDiscovered)} analyzed`;
    case "scoring":
      return `${formatNumber(progress.qualified)} candidates scored`;
    case "deduplicating":
      return `${formatNumber(progress.highQuality)} high-quality matches`;
    default:
      return "";
  }
}

export function PipelineChecklist({ progress }: { progress: SearchProgress }) {
  const currentIndex = STAGE_ORDER.indexOf(progress.stage);

  return (
    <ol className="flex flex-col">
      {PIPELINE_STAGES.map((stage) => {
        const index = STAGE_ORDER.indexOf(stage.id);
        const done = progress.stage === "done" || index < currentIndex;
        const active = index === currentIndex;

        return (
          <li
            key={stage.id}
            className={cn(
              "flex items-center gap-3 border-b border-line py-2.5 last:border-0",
              !done && !active && "opacity-45",
            )}
          >
            <span
              className={cn(
                "grid size-5 shrink-0 place-items-center rounded-full border",
                done && "border-good/30 bg-good-soft text-good",
                active && "border-accent-line bg-accent-soft text-accent",
                !done && !active && "border-line text-fg-faint",
              )}
            >
              {done ? (
                <Check className="size-3" strokeWidth={3} />
              ) : active ? (
                <Loader2 className="size-3 animate-spin" />
              ) : (
                <span className="size-1 rounded-full bg-current" />
              )}
            </span>

            <span className={cn("flex-1 text-sm", active && "font-medium")}>{stage.label}</span>

            <span className="num text-xs text-fg-faint">
              {done || active ? stageDetail(stage.id, progress) : ""}
            </span>
          </li>
        );
      })}
    </ol>
  );
}
