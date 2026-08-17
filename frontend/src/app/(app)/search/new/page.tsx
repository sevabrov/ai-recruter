"use client";

import { ArrowLeft, ArrowRight, RotateCcw, Sparkles, Wand2 } from "lucide-react";
import { useRouter } from "next/navigation";
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
import { stepIssues, WIZARD_STEPS, useWizardStore } from "@/store/wizard-store";

export default function NewSearchPage() {
  const router = useRouter();
  const { toast } = useToast();
  const { step, name, criteria, setStep, next, back, reset, loadExample } = useWizardStore();
  const createSearch = useCreateSearch();

  const issues = stepIssues({ name, criteria }, step);
  const current = WIZARD_STEPS.find((entry) => entry.id === step)!;
  const isLast = step === 5;

  const start = async () => {
    const blocking = stepIssues({ name, criteria }, 1);
    if (blocking.length) {
      setStep(1);
      toast({ title: "Almost there", description: blocking[0], tone: "warn" });
      return;
    }

    const { searchId } = await createSearch.mutateAsync({
      name: name.trim() || "Untitled search",
      criteria,
    });
    router.push(`/search/${searchId}/progress`);
  };

  return (
    <>
      <PageHeader
        eyebrow={`Step ${step} of 5`}
        title={current.title}
        description={DESCRIPTIONS[step]}
        actions={
          <>
            <Button variant="ghost" size="sm" onClick={loadExample}>
              <Wand2 />
              Fill example
            </Button>
            <Button variant="ghost" size="sm" onClick={reset}>
              <RotateCcw />
              Clear
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
            Back
          </Button>

          <div className="flex items-center gap-3">
            {issues.length ? (
              <span className="text-xs text-warn">{issues[0]}</span>
            ) : null}

            {isLast ? (
              <Button
                variant="primary"
                size="lg"
                onClick={start}
                disabled={createSearch.isPending || !criteria.sources.length}
              >
                <Sparkles />
                {createSearch.isPending ? "Starting…" : "Start search"}
              </Button>
            ) : (
              <Button variant="primary" onClick={next} disabled={issues.length > 0}>
                Continue
                <ArrowRight />
              </Button>
            )}
          </div>
        </footer>
      </Card>
    </>
  );
}

const DESCRIPTIONS: Record<number, string> = {
  1: "Describe the person you want to find. Keywords here become the search queries the pipeline runs.",
  2: "Narrow by geography and language. Everything on this step is optional.",
  3: "Define the signals that matter and how many points each one is worth.",
  4: "Choose which public sources to look at. No account, login or cookie is ever used.",
  5: "Review what will run, then start the search.",
};
