"use client";

import { RotateCcw } from "lucide-react";
import { SCORED_SIGNALS, SIGNAL_LABELS, weightLevel } from "@/lib/domain";
import { totalWeight } from "@/lib/scoring";
import { cn } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { CheckboxField, WeightSlider } from "@/components/ui/controls";
import { useWizardStore } from "@/store/wizard-store";
import type { SignalType } from "@/services/types";

const SIGNAL_ORDER: SignalType[] = [
  "mlm",
  "beauty",
  "recruiting",
  "leadership",
  "activity",
  "personalBrand",
  "location",
];

const SIGNAL_HINTS: Record<SignalType, string> = {
  mlm: "Partner, distributor or consultant language in public bios",
  beauty: "Product category the person actually works in",
  recruiting: "Open calls to join a team, posted recently",
  leadership: "Mentions of a team, structure or the people they train",
  location: "Profile location or geotagged activity",
  personalBrand: "Own domain, course, podcast or press mentions",
  activity: "Posting cadence over the last 30 days",
};

export function StepCriteria() {
  const { criteria, toggleMustHave, toggleNiceToHave, setWeight, resetWeights } = useWizardStore();
  const total = totalWeight(criteria.signalWeights);

  return (
    <div className="flex flex-col gap-7">
      <section className="grid gap-6 md:grid-cols-2">
        <div>
          <h3 className="text-sm font-semibold">Must have</h3>
          <p className="mt-1 mb-2 text-xs text-fg-muted">
            A candidate missing any of these is dropped before scoring.
          </p>
          <div className="flex flex-col">
            {SIGNAL_ORDER.map((signal) => (
              <CheckboxField
                key={signal}
                checked={criteria.mustHave.includes(signal)}
                onCheckedChange={() => toggleMustHave(signal)}
                label={SIGNAL_LABELS[signal]}
                hint={SIGNAL_HINTS[signal]}
              />
            ))}
          </div>
        </div>

        <div>
          <h3 className="text-sm font-semibold">Nice to have</h3>
          <p className="mt-1 mb-2 text-xs text-fg-muted">
            Not required, but each one detected adds points.
          </p>
          <div className="flex flex-col">
            {SIGNAL_ORDER.map((signal) => (
              <CheckboxField
                key={signal}
                checked={criteria.niceToHave.includes(signal)}
                onCheckedChange={() => toggleNiceToHave(signal)}
                label={SIGNAL_LABELS[signal]}
              />
            ))}
          </div>
        </div>
      </section>

      <section>
        <header className="flex flex-wrap items-end justify-between gap-3 border-b border-line pb-3">
          <div>
            <h3 className="text-sm font-semibold">Signal weights</h3>
            <p className="mt-1 text-xs text-fg-muted">
              Points a fully-confident signal contributes. The score is the weighted
              sum — no model invents the total.
            </p>
          </div>
          <div className="flex items-center gap-2">
            <Badge tone={total === 100 ? "good" : "warn"} mono>
              {total} / 100 pts
            </Badge>
            <Button variant="ghost" size="sm" onClick={resetWeights}>
              <RotateCcw />
              Reset
            </Button>
          </div>
        </header>

        <ul className="divide-y divide-line">
          {SCORED_SIGNALS.map((signal) => {
            const points = criteria.signalWeights[signal];
            return (
              <li
                key={signal}
                className="grid grid-cols-[1fr_auto] items-center gap-x-4 gap-y-2 py-3 sm:grid-cols-[13rem_1fr_5.5rem]"
              >
                <span className="text-sm">{SIGNAL_LABELS[signal]}</span>
                <div className="col-span-2 sm:col-span-1">
                  <WeightSlider
                    value={points}
                    onValueChange={(next) => setWeight(signal, next)}
                    ariaLabel={`${SIGNAL_LABELS[signal]} weight`}
                  />
                </div>
                <span className="flex items-center justify-end gap-2">
                  <span className="num text-sm">{points}</span>
                  <span
                    className={cn(
                      "label w-16 text-right",
                      points >= 25 ? "text-accent" : points >= 12 ? "text-fg-muted" : "text-fg-faint",
                    )}
                  >
                    {weightLevel(points)}
                  </span>
                </span>
              </li>
            );
          })}
        </ul>

        {total !== 100 ? (
          <p className="mt-3 text-xs text-warn">
            Weights total {total}. Scores stay comparable inside this search, but a
            100-point scale keeps them comparable across searches.
          </p>
        ) : null}
      </section>
    </div>
  );
}
