"use client";

import { Check, Loader2 } from "lucide-react";
import { useTranslations } from "next-intl";
import { PIPELINE_STAGES } from "@/lib/domain";
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

export function PipelineChecklist({ progress }: { progress: SearchProgress }) {
  const stages = useTranslations("domain.pipelineStage");
  const detail = useTranslations("progress.stageDetail");
  const currentIndex = STAGE_ORDER.indexOf(progress.stage);

  /** Per-stage detail so the list carries data, not just spinners. */
  const stageDetail = (stage: SearchStage) => {
    switch (stage) {
      case "generating_queries":
        return detail("generating_queries", {
          done: progress.queriesCompleted,
          total: progress.queries,
        });
      case "web_search":
        return detail("web_search", { count: progress.urlsDiscovered });
      case "discovering_profiles":
        return detail("discovering_profiles", { count: progress.profilesDiscovered });
      case "extracting":
        return detail("extracting", {
          done: progress.profilesProcessed,
          total: progress.profilesDiscovered,
        });
      case "scoring":
        return detail("scoring", { count: progress.qualified });
      case "deduplicating":
        return detail("deduplicating", { count: progress.highQuality });
      default:
        return "";
    }
  };

  return (
    <ol className="flex flex-col">
      {PIPELINE_STAGES.map((stage) => {
        const index = STAGE_ORDER.indexOf(stage);
        const done = progress.stage === "done" || index < currentIndex;
        const active = index === currentIndex;

        return (
          <li
            key={stage}
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

            <span className={cn("flex-1 text-sm", active && "font-medium")}>{stages(stage)}</span>

            <span className="num text-xs text-fg-faint">
              {done || active ? stageDetail(stage) : ""}
            </span>
          </li>
        );
      })}
    </ol>
  );
}
