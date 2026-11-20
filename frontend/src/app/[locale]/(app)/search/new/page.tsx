"use client";

import { ArrowRight, Pencil, RotateCcw, Sparkles, Wand2 } from "lucide-react";
import { useLocale, useTranslations } from "next-intl";
import { useRouter } from "@/i18n/navigation";
import { PageHeader } from "@/components/layout/page-header";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { useToast } from "@/components/ui/toast";
import { BRIEF_MIN, StepBrief } from "@/components/search/wizard/step-brief";
import { StepReview } from "@/components/search/wizard/step-review";
import { WizardSteps } from "@/components/search/wizard/steps";
import { useCreateSearch, useParseBrief } from "@/services/hooks";
import { BLOCKING_GAPS, criteriaGaps, useWizardStore } from "@/store/wizard-store";

export default function NewSearchPage() {
  const t = useTranslations("wizard");
  const common = useTranslations("common");
  const locale = useLocale();
  const router = useRouter();
  const { toast } = useToast();
  const {
    step,
    brief,
    name,
    criteria,
    worldwide,
    parsedFrom,
    setStep,
    applyParsed,
    reset,
  } = useWizardStore();
  const parseBrief = useParseBrief();
  const createSearch = useCreateSearch();

  // The description has not changed since it was read: going forward is a step,
  // not another (billed) parse that would also throw away edits made on review.
  const unchanged = parsedFrom !== null && parsedFrom === brief;
  const blocking = criteriaGaps({ criteria, worldwide }).filter((gap) =>
    BLOCKING_GAPS.includes(gap),
  );

  const parse = async () => {
    if (unchanged) {
      setStep(2);
      return;
    }
    try {
      applyParsed(await parseBrief.mutateAsync({ text: brief, locale }));
    } catch {
      toast({ title: t("brief.failed"), tone: "warn" });
    }
  };

  const start = async () => {
    if (blocking.length) {
      toast({
        title: t("almostThere"),
        description: t(`issues.${blocking[0]}`),
        tone: "warn",
      });
      return;
    }
    const { searchId } = await createSearch.mutateAsync({
      name: name.trim() || t("untitled"),
      criteria: { ...criteria, brief },
    });
    router.push(`/search/${searchId}/progress`);
  };

  return (
    <>
      <PageHeader
        eyebrow={t("stepOf", { step, total: 2 })}
        title={t(`steps.${step}.title`)}
        description={t(`descriptions.${step}`)}
        actions={
          <Button variant="ghost" size="sm" onClick={reset}>
            <RotateCcw />
            {common("clear")}
          </Button>
        }
      />

      <div className="mb-5">
        <WizardSteps
          current={step}
          onSelect={(next) => (next === 2 ? void parse() : setStep(next))}
          reachable={unchanged ? [2] : []}
        />
      </div>

      <Card>
        <div className="px-5 py-6 lg:px-7">
          {step === 1 ? <StepBrief /> : <StepReview />}
        </div>

        <footer className="flex flex-wrap items-center justify-between gap-3 border-t border-line bg-surface-2 px-5 py-3.5">
          {step === 1 ? (
            <span />
          ) : (
            <Button variant="ghost" onClick={() => setStep(1)}>
              <Pencil />
              {t("editBrief")}
            </Button>
          )}

          <div className="flex items-center gap-3">
            {step === 2 && blocking.length ? (
              <span className="text-xs text-warn">{t(`issues.${blocking[0]}`)}</span>
            ) : null}

            {step === 1 ? (
              <Button
                variant="primary"
                size="lg"
                onClick={parse}
                disabled={parseBrief.isPending || brief.trim().length < BRIEF_MIN}
              >
                {unchanged ? <ArrowRight /> : <Wand2 />}
                {parseBrief.isPending
                  ? t("brief.parsing")
                  : unchanged
                    ? common("continue")
                    : t("brief.parse")}
              </Button>
            ) : (
              <Button
                variant="primary"
                size="lg"
                onClick={start}
                disabled={createSearch.isPending || blocking.length > 0}
              >
                <Sparkles />
                {createSearch.isPending ? t("starting") : t("startSearch")}
              </Button>
            )}
          </div>
        </footer>
      </Card>

      {step === 1 && brief.trim() && brief.trim().length < BRIEF_MIN ? (
        <p className="mt-3 text-right text-xs text-fg-faint">{t("brief.tooShort")}</p>
      ) : null}
    </>
  );
}
