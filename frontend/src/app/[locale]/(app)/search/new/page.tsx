"use client";

import { ArrowLeft, ArrowRight, RotateCcw, Sparkles, Wand2 } from "lucide-react";
import { useTranslations } from "next-intl";
import { useRouter } from "@/i18n/navigation";
import { PageHeader } from "@/components/layout/page-header";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { useToast } from "@/components/ui/toast";
import { StepCriteria } from "@/components/search/wizard/step-criteria";
import { StepGeography } from "@/components/search/wizard/step-geography";
import { StepIdentity } from "@/components/search/wizard/step-identity";
import { StepReview } from "@/components/search/wizard/step-review";
import { StepSources } from "@/components/search/wizard/step-sources";
import { WizardSteps } from "@/components/search/wizard/steps";
import { useCreateSearch } from "@/services/hooks";
import { stepIssues, useWizardStore } from "@/store/wizard-store";

export default function NewSearchPage() {
  const t = useTranslations("wizard");
  const common = useTranslations("common");
  const router = useRouter();
  const { toast } = useToast();
  const { step, name, criteria, setStep, next, back, reset, loadExample } = useWizardStore();
  const createSearch = useCreateSearch();

  const issues = stepIssues({ name, criteria }, step);
  const isLast = step === 5;

  const start = async () => {
    const blocking = stepIssues({ name, criteria }, 1);
    if (blocking.length) {
      setStep(1);
      toast({
        title: t("almostThere"),
        description: t(`issues.${blocking[0]}`),
        tone: "warn",
      });
      return;
    }

    const { searchId } = await createSearch.mutateAsync({
      name: name.trim() || t("untitled"),
      criteria,
    });
    router.push(`/search/${searchId}/progress`);
  };

  return (
    <>
      <PageHeader
        eyebrow={t("stepOf", { step })}
        title={t(`steps.${step}.title`)}
        description={t(`descriptions.${step}`)}
        actions={
          <>
            <Button variant="ghost" size="sm" onClick={loadExample}>
              <Wand2 />
              {t("fillExample")}
            </Button>
            <Button variant="ghost" size="sm" onClick={reset}>
              <RotateCcw />
              {common("clear")}
            </Button>
          </>
        }
      />

      <div className="mb-5">
        <WizardSteps current={step} onSelect={setStep} />
      </div>

      <Card>
        <div className="px-5 py-6 lg:px-7">
          {step === 1 ? <StepIdentity /> : null}
          {step === 2 ? <StepGeography /> : null}
          {step === 3 ? <StepCriteria /> : null}
          {step === 4 ? <StepSources /> : null}
          {step === 5 ? <StepReview /> : null}
        </div>

        <footer className="flex flex-wrap items-center justify-between gap-3 border-t border-line bg-surface-2 px-5 py-3.5">
          <Button variant="ghost" onClick={back} disabled={step === 1}>
            <ArrowLeft />
            {common("back")}
          </Button>

          <div className="flex items-center gap-3">
            {issues.length ? (
              <span className="text-xs text-warn">{t(`issues.${issues[0]}`)}</span>
            ) : null}

            {isLast ? (
              <Button
                variant="primary"
                size="lg"
                onClick={start}
                disabled={createSearch.isPending || !criteria.sources.length}
              >
                <Sparkles />
                {createSearch.isPending ? t("starting") : t("startSearch")}
              </Button>
            ) : (
              <Button variant="primary" onClick={next} disabled={issues.length > 0}>
                {common("continue")}
                <ArrowRight />
              </Button>
            )}
          </div>
        </footer>
      </Card>
    </>
  );
}
