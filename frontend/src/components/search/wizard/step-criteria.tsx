"use client";

import { RotateCcw } from "lucide-react";
import { useTranslations } from "next-intl";
import { SCORED_SIGNALS, SIGNAL_TYPES, weightLevel } from "@/lib/domain";
import { totalWeight } from "@/lib/scoring";
import { cn } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { CheckboxField, WeightSlider } from "@/components/ui/controls";
import { useWizardStore } from "@/store/wizard-store";

export function StepCriteria() {
  const t = useTranslations("wizard.criteria");
  const common = useTranslations("common");
  const signals = useTranslations("domain.signal");
  const hints = useTranslations("domain.signalHint");
  const levels = useTranslations("domain.weightLevel");

  const { criteria, toggleMustHave, toggleNiceToHave, setWeight, resetWeights } = useWizardStore();
  const total = totalWeight(criteria.signalWeights);

  return (
    <div className="flex flex-col gap-7">
      <section className="grid gap-6 md:grid-cols-2">
        <div>
          <h3 className="text-sm font-semibold">{t("mustHave")}</h3>
          <p className="mt-1 mb-2 text-xs text-fg-muted">{t("mustHaveHint")}</p>
          <div className="flex flex-col">
            {SIGNAL_TYPES.map((signal) => (
              <CheckboxField
                key={signal}
                checked={criteria.mustHave.includes(signal)}
                onCheckedChange={() => toggleMustHave(signal)}
                label={signals(signal)}
                hint={hints(signal)}
              />
            ))}
          </div>
        </div>

        <div>
          <h3 className="text-sm font-semibold">{t("niceToHave")}</h3>
          <p className="mt-1 mb-2 text-xs text-fg-muted">{t("niceToHaveHint")}</p>
          <div className="flex flex-col">
            {SIGNAL_TYPES.map((signal) => (
              <CheckboxField
                key={signal}
                checked={criteria.niceToHave.includes(signal)}
                onCheckedChange={() => toggleNiceToHave(signal)}
                label={signals(signal)}
              />
            ))}
          </div>
        </div>
      </section>

      <section>
        <header className="flex flex-wrap items-end justify-between gap-3 border-b border-line pb-3">
          <div>
            <h3 className="text-sm font-semibold">{t("weights")}</h3>
            <p className="mt-1 text-xs text-fg-muted">{t("weightsHint")}</p>
          </div>
          <div className="flex items-center gap-2">
            <Badge tone={total === 100 ? "good" : "warn"} mono>
              {t("points", { total })}
            </Badge>
            <Button variant="ghost" size="sm" onClick={resetWeights}>
              <RotateCcw />
              {common("reset")}
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
                <span className="text-sm">{signals(signal)}</span>
                <div className="col-span-2 sm:col-span-1">
                  <WeightSlider
                    value={points}
                    onValueChange={(next) => setWeight(signal, next)}
                    ariaLabel={t("weightAria", { signal: signals(signal) })}
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
                    {levels(weightLevel(points))}
                  </span>
                </span>
              </li>
            );
          })}
        </ul>

        {total !== 100 ? (
          <p className="mt-3 text-xs text-warn">{t("totalWarning", { total })}</p>
        ) : null}
      </section>
    </div>
  );
}
