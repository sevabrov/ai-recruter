"use client";

import { ArrowRight, Pencil, RotateCcw, Sparkles, Wand2 } from "lucide-react";
import { useLocale, useTranslations } from "next-intl";
import { useRouter as useNextRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { useRouter } from "@/i18n/navigation";
import { PageHeader } from "@/components/layout/page-header";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Modal } from "@/components/ui/overlay";
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
    refining,
    setStep,
    applyParsed,
    reset,
  } = useWizardStore();
  const parseBrief = useParseBrief();
  const createSearch = useCreateSearch();

  // The draft is kept in sessionStorage so a refresh mid-flow keeps the input -
  // which also meant the next "New search" opened on whatever was here last. Two
  // drafts are dropped as this page leaves: a search that was started (it is no
  // longer a draft) and a refined copy of an old search that was not (it is that
  // search, not a new one). Dropped after leaving, not before: resetting first
  // would flash step 1 while navigating away. Deferred, so Strict Mode's
  // rehearsal unmount - which mounts again at once - doesn't wipe it.
  const started = useRef(false);
  useEffect(() => {
    clearTimeout(pendingReset);
    return () => {
      const { refining, reset } = useWizardStore.getState();
      if (started.current || refining) pendingReset = setTimeout(reset, 0);
    };
  }, []);

  const leaving = useLeaveGuard(refining);

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
    started.current = true;
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

      <Modal
        open={leaving.target !== null}
        onOpenChange={(open) => (open ? null : leaving.stay())}
        title={t("leaveRefine.title")}
        description={t("leaveRefine.description")}
        width="max-w-md"
        footer={
          <>
            <Button variant="ghost" onClick={leaving.stay}>
              {t("leaveRefine.stay")}
            </Button>
            <Button variant="primary" onClick={leaving.leave}>
              {t("leaveRefine.leave")}
            </Button>
          </>
        }
      >
        <p className="text-sm text-fg-muted">{t("leaveRefine.body")}</p>
      </Modal>
    </>
  );
}

let pendingReset: ReturnType<typeof setTimeout> | undefined;

/**
 * Asks before a link takes the client away from an unstarted refine. Every
 * in-app link is a plain `<a>` (sidebar, header, breadcrumb, dashboard), so one
 * capture-phase listener catches them all before Next's own click handler does,
 * instead of an `onNavigate` on each of them. Back/forward is not asked about; leaving
 * that way still drops the draft on unmount.
 */
function useLeaveGuard(active: boolean) {
  const router = useNextRouter();
  const [target, setTarget] = useState<string | null>(null);

  useEffect(() => {
    if (!active) return;
    const onClick = (event: MouseEvent) => {
      if (event.defaultPrevented || event.button !== 0) return;
      if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
      const anchor = (event.target as Element | null)?.closest?.("a[href]");
      if (!(anchor instanceof HTMLAnchorElement)) return;
      if (anchor.target && anchor.target !== "_self") return;
      if (anchor.hasAttribute("download")) return;
      const url = new URL(anchor.href, window.location.href);
      if (url.origin !== window.location.origin) return;
      // A jump within this page is not leaving it.
      if (url.hash && url.pathname === window.location.pathname && url.search === window.location.search) {
        return;
      }
      // Not stopped: the link's own onClick still runs (the mobile drawer closes),
      // and Next's Link does not navigate a click that is already prevented.
      event.preventDefault();
      setTarget(`${url.pathname}${url.search}${url.hash}`);
    };
    window.addEventListener("click", onClick, true);
    return () => window.removeEventListener("click", onClick, true);
  }, [active]);

  const stay = () => setTarget(null);
  const leave = () => {
    if (target === null) return;
    setTarget(null);
    if (target === window.location.pathname) {
      // "New search" from here: the empty form is this same page.
      useWizardStore.getState().reset();
      return;
    }
    // Already carries the locale prefix, so Next's router, not next-intl's.
    // The draft is dropped by the page's unmount.
    router.push(target);
  };

  return { target, stay, leave };
}
