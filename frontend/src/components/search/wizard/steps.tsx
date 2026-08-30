"use client";

import { Check } from "lucide-react";
import { useTranslations } from "next-intl";
import { cn } from "@/lib/utils";
import { WIZARD_STEPS, type WizardStepId } from "@/store/wizard-store";

/**
 * The wizard is a genuine sequence, so the markers are numbered. Completed
 * steps stay clickable — the client can jump back without losing input.
 */
export function WizardSteps({
  current,
  onSelect,
}: {
  current: WizardStepId;
  onSelect: (step: WizardStepId) => void;
}) {
  const t = useTranslations("wizard.steps");

  return (
    <ol className="flex flex-wrap items-center gap-x-1 gap-y-2">
      {WIZARD_STEPS.map((step, index) => {
        const done = step < current;
        const active = step === current;

        return (
          <li key={step} className="flex items-center gap-1">
            <button
              type="button"
              onClick={() => (done || active ? onSelect(step) : undefined)}
              disabled={!done && !active}
              className={cn(
                "flex items-center gap-2 rounded-pill border px-2.5 py-1 transition-colors",
                active && "border-accent-line bg-accent-soft text-accent",
                done && "border-line bg-surface text-fg-muted hover:text-fg",
                !active && !done && "border-transparent text-fg-faint",
              )}
            >
              <span
                className={cn(
                  "num grid size-4.5 place-items-center rounded-full text-2xs font-medium",
                  active && "bg-accent text-accent-on",
                  done && "bg-good-soft text-good",
                  !active && !done && "border border-line text-fg-faint",
                )}
              >
                {done ? <Check className="size-2.5" strokeWidth={3} /> : index + 1}
              </span>
              <span className="label">{t(`${step}.label`)}</span>
            </button>
            {index < WIZARD_STEPS.length - 1 ? (
              <span className="h-px w-4 bg-line" aria-hidden />
            ) : null}
          </li>
        );
      })}
    </ol>
  );
}
