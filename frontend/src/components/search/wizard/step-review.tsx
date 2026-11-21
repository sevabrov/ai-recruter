"use client";

import { AlertTriangle, HelpCircle, Info, Minus, Plus, X } from "lucide-react";
import { useTranslations } from "next-intl";
import { useState, type ReactNode } from "react";
import {
  BUSINESS_TYPES,
  COUNTRIES,
  INDUSTRIES,
  effectiveRequirements,
  isPresetSignal,
  LANGUAGES,
  MAX_REQUIREMENTS,
  REQUIREMENT_IMPORTANCE,
  type VocabularyEntry,
} from "@/lib/domain";
import { useNumbers } from "@/lib/format";
import { cn } from "@/lib/utils";
import { useVocabulary } from "@/lib/vocabulary";
import type { EstimateWarning, SearchEstimate } from "@/services/types";
import { useSearchEstimate } from "@/services/hooks";
import {
  BLOCKING_GAPS,
  criteriaGaps,
  useWizardStore,
  type WizardGap,
} from "@/store/wizard-store";
import { Button } from "@/components/ui/button";
import { ChipInput } from "@/components/ui/chip-input";
import { Input } from "@/components/ui/field";
import { Eyebrow } from "@/components/ui/misc";
import { AdvancedSettings } from "@/components/search/wizard/advanced-settings";

/** What the wizard offers with one click. Any number can still be typed. */
const TARGETS = [5, 10, 25, 50];

/** Where each gap is answered, so the summary can take the client straight there. */
const GAP_FIELD: Record<WizardGap, string> = {
  terms: "wizard-brands",
  brands: "wizard-brands",
  requirements: "wizard-requirements",
  sources: "wizard-sources",
  country: "wizard-country",
  languages: "wizard-languages",
};

/**
 * Step two: what was understood, and what is still missing.
 *
 * Every criterion is editable here, in the interface language — tokens like
 * "Spain" or "Cosmetics" are what the backend stores, never what the client
 * reads. What the brief did not say is asked as a question, in place, on the
 * field that answers it; the two questions that make a search pointless to run
 * (nothing to search for, nowhere to look) keep the start button disabled.
 */
export function StepReview() {
  const t = useTranslations("wizard.review");
  const { criteria, worldwide, parser, patchCriteria } = useWizardStore();
  const estimate = useSearchEstimate(criteria);
  const gaps = criteriaGaps({ criteria, worldwide });
  const target = criteria.targetLeads ?? 0;
  // Said once: a warning that repeats an open question at the top is noise.
  const asked: Record<string, WizardGap> = {
    no_keywords: "terms",
    languages_without_country: "country",
  };
  const warnings = (estimate.data?.warnings ?? []).filter(
    (warning) => !gaps.includes(asked[warning.code]),
  );

  const setTarget = (leads: number) =>
    patchCriteria({ targetLeads: Math.max(1, Math.min(1000, leads)) });

  return (
    <div className="flex flex-col gap-6">
      {parser === "rules" ? (
        <p className="flex gap-2 rounded-card border border-line bg-surface-2 px-4 py-3 text-xs leading-relaxed text-fg-muted">
          <Info className="mt-0.5 size-3.5 shrink-0 text-fg-faint" />
          <span>{t("parsedByRules")}</span>
        </p>
      ) : null}

      {gaps.length ? <Gaps gaps={gaps} /> : null}

      <Understood gaps={gaps} />

      <section className="grid gap-4 rounded-card border border-line bg-surface-2 p-4 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.1fr)]">
        <div>
          <Eyebrow className="mb-2">{t("howMany")}</Eyebrow>
          <div className="flex items-center gap-2">
            <Button
              variant="ghost"
              size="sm"
              aria-label={t("fewer")}
              onClick={() => setTarget(target - 1)}
            >
              <Minus />
            </Button>
            <input
              type="number"
              min={1}
              max={1000}
              value={target || ""}
              onChange={(event) => setTarget(Number(event.target.value))}
              aria-label={t("leadsToFind")}
              className="num w-20 rounded-input border border-line bg-surface-1 px-3 py-1.5 text-center font-display text-xl font-semibold"
            />
            <Button
              variant="ghost"
              size="sm"
              aria-label={t("more")}
              onClick={() => setTarget(target + 1)}
            >
              <Plus />
            </Button>
            <div className="ml-2 flex flex-wrap gap-1">
              {TARGETS.map((leads) => (
                <Button
                  key={leads}
                  size="sm"
                  variant={target === leads ? "primary" : "ghost"}
                  onClick={() => setTarget(leads)}
                >
                  {leads}
                </Button>
              ))}
            </div>
          </div>
          <p className="mt-3 text-xs leading-relaxed text-fg-muted">{t("targetHint")}</p>
        </div>

        <Cost estimate={estimate.data} loading={estimate.isPending} failed={estimate.isError} />
      </section>

      {warnings.length ? <Warnings warnings={warnings} /> : null}

      <AdvancedSettings estimate={estimate.data} estimateLoading={estimate.isPending} />
    </div>
  );
}

/* ------------------------------------------------------------------- gaps */

function Gaps({ gaps }: { gaps: WizardGap[] }) {
  const t = useTranslations("wizard.review");

  const goTo = (gap: WizardGap) => {
    // Sources live in the folded advanced section: open it first.
    if (gap === "sources") {
      const details = document.getElementById("wizard-advanced");
      if (details instanceof HTMLDetailsElement) details.open = true;
    }
    const field = document.getElementById(GAP_FIELD[gap]);
    field?.scrollIntoView({ behavior: "smooth", block: "center" });
    field?.querySelector<HTMLElement>("input, button, [role=combobox]")?.focus({ preventScroll: true });
  };

  return (
    <section className="rounded-card border border-warn/30 bg-warn-soft px-4 py-3.5">
      <Eyebrow className="mb-2 text-warn">{t("gapsTitle")}</Eyebrow>
      <ul className="flex flex-col gap-1.5">
        {gaps.map((gap) => (
          <li key={gap}>
            <button
              type="button"
              onClick={() => goTo(gap)}
              className="flex w-full items-start gap-2 text-left text-sm leading-relaxed text-fg transition-colors hover:text-accent"
            >
              <HelpCircle className="mt-1 size-3.5 shrink-0 text-warn" />
              <span>
                {t(`gap.${gap}.question`)}{" "}
                <span className="text-2xs text-fg-faint uppercase">
                  {BLOCKING_GAPS.includes(gap) ? t("gapRequired") : t("gapRecommended")}
                </span>
              </span>
            </button>
          </li>
        ))}
      </ul>
    </section>
  );
}

/* -------------------------------------------------------------- understood */

function Understood({ gaps }: { gaps: WizardGap[] }) {
  const t = useTranslations("wizard.review");
  const vocabulary = useVocabulary();
  const { name, setName, criteria, patchCriteria, setLocation } = useWizardStore();

  const toggleToken = (list: string[], token: string) =>
    list.some((entry) => entry.toLowerCase() === token.toLowerCase())
      ? list.filter((entry) => entry.toLowerCase() !== token.toLowerCase())
      : [...list, token];

  return (
    <section className="flex flex-col gap-5">
      <Eyebrow>{t("understoodTitle")}</Eyebrow>

      <div className="grid gap-5 md:grid-cols-2">
        <ReviewField id="wizard-name" label={t("fieldName")}>
          <Input value={name} onChange={(event) => setName(event.target.value)} />
        </ReviewField>
        <ReviewField id="wizard-about" label={t("fieldAboutMe")} hint={t("fieldAboutMeHint")}>
          <Input
            value={criteria.aboutMe ?? ""}
            onChange={(event) => patchCriteria({ aboutMe: event.target.value })}
            placeholder={t("fieldAboutMePlaceholder")}
          />
        </ReviewField>
      </div>

      <div className="grid gap-5 md:grid-cols-2">
        <ReviewField
          id="wizard-brands"
          label={t("fieldBrands")}
          hint={t("fieldBrandsHint")}
          question={
            gaps.includes("terms")
              ? t("gap.terms.question")
              : gaps.includes("brands")
                ? t("gap.brands.question")
                : undefined
          }
        >
          <ChipInput
            values={criteria.brands ?? []}
            onChange={(brands) => patchCriteria({ brands })}
            placeholder={t("fieldBrandsPlaceholder")}
          />
        </ReviewField>
        <ReviewField
          id="wizard-keywords"
          label={t("fieldKeywords")}
          hint={t("fieldKeywordsHint")}
          question={gaps.includes("terms") ? t("gap.terms.question") : undefined}
        >
          <ChipInput
            values={criteria.keywords}
            onChange={(keywords) => patchCriteria({ keywords })}
            placeholder={t("fieldKeywordsPlaceholder")}
          />
        </ReviewField>
      </div>

      <div className="grid gap-5 md:grid-cols-2">
        <ReviewField
          id="wizard-country"
          label={t("fieldCountry")}
          hint={t("fieldCountryHint")}
          question={gaps.includes("country") ? t("gap.country.question") : undefined}
        >
          <Places />
        </ReviewField>
        <ReviewField id="wizard-city" label={t("fieldCity")} hint={t("fieldCityHint")}>
          <Input
            value={criteria.location.city ?? ""}
            onChange={(event) => setLocation({ city: event.target.value || undefined })}
            placeholder={t("fieldCityPlaceholder")}
            disabled={!criteria.location.country}
          />
        </ReviewField>
      </div>

      <ReviewField
        id="wizard-languages"
        label={t("fieldLanguages")}
        hint={t("fieldLanguagesHint")}
        question={gaps.includes("languages") ? t("gap.languages.question") : undefined}
      >
        <ToggleChips
          entries={LANGUAGES}
          selected={criteria.languages}
          label={vocabulary.language}
          onToggle={(token) => patchCriteria({ languages: toggleToken(criteria.languages, token) })}
        />
      </ReviewField>

      <ReviewField id="wizard-negatives" label={t("fieldNegatives")} hint={t("fieldNegativesHint")}>
        <ChipInput
          values={criteria.negativeKeywords}
          onChange={(negativeKeywords) => patchCriteria({ negativeKeywords })}
          placeholder={t("fieldNegativesPlaceholder")}
          tone="negative"
        />
      </ReviewField>

      <div className="grid gap-5 md:grid-cols-2">
        <ReviewField id="wizard-industry" label={t("fieldIndustry")}>
          <ToggleChips
            entries={INDUSTRIES}
            selected={criteria.industry}
            label={vocabulary.industry}
            onToggle={(token) => patchCriteria({ industry: toggleToken(criteria.industry, token) })}
          />
        </ReviewField>
        <ReviewField id="wizard-business" label={t("fieldBusiness")}>
          <ToggleChips
            entries={BUSINESS_TYPES}
            selected={criteria.businessTypes}
            label={vocabulary.businessType}
            onToggle={(token) =>
              patchCriteria({ businessTypes: toggleToken(criteria.businessTypes, token) })
            }
          />
        </ReviewField>
      </div>

      <Requirements />
    </section>
  );
}

/**
 * Where to look, as chips: any number of countries, "any European country", or
 * the whole world. "Ukraine or Europe" used to become the whole world, because
 * the field only held one country — and the search came back from Indonesia.
 */
function Places() {
  const t = useTranslations("wizard.review");
  const vocabulary = useVocabulary();
  const { criteria, worldwide, setPlaces } = useWizardStore();
  const chosen = criteria.location.country
    ? [criteria.location.country]
    : (criteria.countries ?? []);
  const region = criteria.region ?? "";
  const anywhere = worldwide && !chosen.length && !region;

  const toggleCountry = (token: string) =>
    setPlaces(
      chosen.includes(token) ? chosen.filter((entry) => entry !== token) : [...chosen, token],
      region,
    );

  const chip = (on: boolean) =>
    cn(
      "rounded-pill border px-2.5 py-1 text-[13px] transition-colors",
      on
        ? "border-accent-line bg-accent-soft text-accent"
        : "border-line text-fg-muted hover:border-line-strong hover:text-fg",
    );

  return (
    <div className="flex flex-col gap-2">
      <div className="flex flex-wrap gap-1.5">
        <button
          type="button"
          aria-pressed={region === "europe"}
          onClick={() => setPlaces(chosen, region === "europe" ? "" : "europe")}
          className={chip(region === "europe")}
        >
          {t("regionEurope")}
        </button>
        <button
          type="button"
          aria-pressed={anywhere}
          onClick={() => setPlaces([], "")}
          className={chip(anywhere)}
        >
          {t("anywhere")}
        </button>
      </div>
      <div className="flex flex-wrap gap-1.5">
        {[...COUNTRIES]
          .sort((a, b) => vocabulary.country(a.token).localeCompare(vocabulary.country(b.token)))
          .map((entry) => (
            <button
              key={entry.id}
              type="button"
              aria-pressed={chosen.includes(entry.token)}
              onClick={() => toggleCountry(entry.token)}
              className={chip(chosen.includes(entry.token))}
            >
              {vocabulary.country(entry.token)}
            </button>
          ))}
      </div>
    </div>
  );
}

function ReviewField({
  id,
  label,
  hint,
  question,
  children,
}: {
  id: string;
  label: string;
  hint?: string;
  /** Set when this field answers an open question: the field is then highlighted. */
  question?: string;
  children: ReactNode;
}) {
  return (
    <div
      id={id}
      className={cn(
        "flex scroll-mt-24 flex-col gap-1.5",
        question && "rounded-card border border-warn/40 bg-warn-soft/40 p-3",
      )}
    >
      <span className="label text-fg-muted">{label}</span>
      {question ? (
        <p className="flex gap-1.5 text-xs font-medium text-warn">
          <HelpCircle className="mt-0.5 size-3.5 shrink-0" />
          {question}
        </p>
      ) : null}
      {children}
      {hint ? <p className="text-xs leading-relaxed text-fg-faint">{hint}</p> : null}
    </div>
  );
}

/** A closed list as buttons: the client picks, and never sees a stored token. */
function ToggleChips({
  entries,
  selected,
  label,
  onToggle,
}: {
  entries: VocabularyEntry[];
  selected: string[];
  label: (token: string) => string;
  onToggle: (token: string) => void;
}) {
  const chosen = new Set(selected.map((token) => token.toLowerCase()));
  // A value from an older search that is not in the list is still shown, so it
  // can be seen and removed rather than silently kept.
  const unknown = selected.filter(
    (token) => !entries.some((entry) => entry.token.toLowerCase() === token.toLowerCase()),
  );

  return (
    <div className="flex flex-wrap gap-1.5">
      {[...entries.map((entry) => entry.token), ...unknown].map((token) => {
        const on = chosen.has(token.toLowerCase());
        return (
          <button
            key={token}
            type="button"
            aria-pressed={on}
            onClick={() => onToggle(token)}
            className={cn(
              "rounded-pill border px-2.5 py-1 text-[13px] transition-colors",
              on
                ? "border-accent-line bg-accent-soft text-accent"
                : "border-line text-fg-muted hover:border-line-strong hover:text-fg",
            )}
          >
            {label(token)}
          </button>
        );
      })}
    </div>
  );
}

/**
 * What makes a candidate right for this search — written for it, editable here.
 *
 * The client chooses how much each thing matters; the points follow (100 in all)
 * and are shown, not typed. The old wizard asked for seven fixed network-marketing
 * signals in two checkbox lists and a page of sliders that had to add up to 100.
 */
function Requirements() {
  const t = useTranslations("wizard.review");
  const common = useTranslations("common");
  const vocabulary = useVocabulary();
  const {
    criteria,
    setRequirementImportance,
    renameRequirement,
    addRequirement,
    removeRequirement,
  } = useWizardStore();
  const [draft, setDraft] = useState("");
  const requirements = effectiveRequirements(criteria);
  const full = requirements.length >= MAX_REQUIREMENTS;

  const add = () => {
    addRequirement(draft);
    setDraft("");
  };

  return (
    <div id="wizard-requirements" className="flex scroll-mt-24 flex-col gap-1.5">
      <span className="label text-fg-muted">{t("fieldRequirements")}</span>
      <p className="text-xs leading-relaxed text-fg-faint">{t("fieldRequirementsHint")}</p>

      <ul className="divide-y divide-line rounded-card border border-line">
        {requirements.map((requirement) => {
          const preset = isPresetSignal(requirement.id);
          const name = vocabulary.requirement(requirement);
          return (
            <li
              key={requirement.id}
              className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2 px-3 py-2.5"
            >
              <div className="min-w-0 flex-1">
                {preset ? (
                  <p className="text-sm">{name}</p>
                ) : (
                  <input
                    value={requirement.label ?? ""}
                    onChange={(event) => renameRequirement(requirement.id, event.target.value)}
                    aria-label={t("requirementName")}
                    className="w-full rounded-ctl border border-transparent bg-transparent px-1 py-0.5 text-sm hover:border-line focus:border-accent focus:outline-none"
                  />
                )}
                {requirement.description ? (
                  <p className="px-1 text-xs text-fg-faint">{requirement.description}</p>
                ) : null}
              </div>
              <div className="flex items-center gap-2">
                <div
                  role="radiogroup"
                  aria-label={name}
                  className="flex rounded-pill border border-line p-0.5"
                >
                  {REQUIREMENT_IMPORTANCE.map((level) => (
                    <button
                      key={level}
                      type="button"
                      role="radio"
                      aria-checked={requirement.importance === level}
                      onClick={() => setRequirementImportance(requirement.id, level)}
                      className={cn(
                        "rounded-pill px-2.5 py-0.5 text-xs transition-colors",
                        requirement.importance === level
                          ? level === "required"
                            ? "bg-accent text-accent-on"
                            : "bg-accent-soft text-accent"
                          : "text-fg-faint hover:text-fg",
                      )}
                    >
                      {t(`importance.${level}`)}
                    </button>
                  ))}
                </div>
                <span className="num w-12 text-right text-xs text-fg-muted">
                  {requirement.weight ? t("points", { points: requirement.weight }) : common("dash")}
                </span>
                <button
                  type="button"
                  onClick={() => removeRequirement(requirement.id)}
                  aria-label={t("requirementRemove", { name })}
                  className="text-fg-faint transition-colors hover:text-bad"
                >
                  <X className="size-3.5" />
                </button>
              </div>
            </li>
          );
        })}
        {!requirements.length ? (
          <li className="px-3 py-2.5 text-xs text-fg-faint">{t("requirementsEmpty")}</li>
        ) : null}
      </ul>

      <div className="flex gap-2">
        <Input
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter") {
              event.preventDefault();
              add();
            }
          }}
          placeholder={t("requirementPlaceholder")}
          aria-label={t("requirementAdd")}
          disabled={full}
        />
        <Button variant="secondary" onClick={add} disabled={full || !draft.trim()}>
          <Plus />
          {t("requirementAdd")}
        </Button>
      </div>
    </div>
  );
}

/* --------------------------------------------------------------- warnings */

/**
 * Said before the money is spent. The backend decides *what* is likely to go
 * wrong and sends a code; the words are the interface's. It used to send English
 * sentences, which then sat in the middle of a Ukrainian screen.
 */
function Warnings({ warnings }: { warnings: EstimateWarning[] }) {
  const t = useTranslations("wizard.review");
  const vocabulary = useVocabulary();

  return (
    <section className="rounded-card border border-warn/30 bg-warn-soft px-4 py-3.5">
      <Eyebrow className="mb-2 text-warn">{t("warningsTitle")}</Eyebrow>
      <ul className="flex flex-col gap-2">
        {warnings.map((warning) => {
          const key = `warning.${warning.code}`;
          const params = {
            ...warning.params,
            country: vocabulary.country(warning.params?.country),
          };
          return (
            <li key={warning.code} className="flex gap-2 text-xs leading-relaxed text-fg-muted">
              <AlertTriangle className="mt-0.5 size-3.5 shrink-0 text-warn" />
              <span>{t.has(key) ? t(key, params) : warning.code}</span>
            </li>
          );
        })}
      </ul>
    </section>
  );
}

/* ------------------------------------------------------------------- cost */

/**
 * The price, as a ceiling rather than a forecast.
 *
 * The backend derives this figure and the run's page budget from the same
 * function, so it is a promise the search cannot break — which is the only kind
 * of number worth showing before somebody presses start.
 */
function Cost({
  estimate,
  loading,
  failed,
}: {
  estimate?: SearchEstimate;
  loading: boolean;
  failed: boolean;
}) {
  const t = useTranslations("wizard.review");
  const common = useTranslations("common");
  const { eur } = useNumbers();

  if (failed) {
    return (
      <div className="flex items-start gap-2 rounded-card border border-line bg-surface-1 p-4 text-xs text-warn">
        <AlertTriangle className="mt-0.5 size-3.5 shrink-0" />
        <span>{t("costFailed")}</span>
      </div>
    );
  }

  return (
    <div className="rounded-card border border-line bg-surface-1 p-4">
      <Eyebrow className="mb-2">{t("costExpectedTitle")}</Eyebrow>
      <p className="num font-display text-3xl font-semibold">
        {loading || !estimate
          ? common("dash")
          : t("costAbout", { amount: eur(estimate.expectedCostEur ?? estimate.maxCostEur) })}
      </p>
      <dl className="mt-3 space-y-1 text-xs text-fg-muted">
        <Line
          label={t("costCeiling")}
          value={estimate ? eur(estimate.maxCostEur) : common("dash")}
        />
        <Line
          label={t("costQueries")}
          value={estimate ? t("costCalls", { count: estimate.searchCalls }) : common("dash")}
        />
        <Line
          label={t("costPagesRead")}
          value={
            !estimate
              ? common("dash")
              : !estimate.readsPages
                ? estimate.browserPages
                  ? t("costBrowserFree")
                  : t("costNoReader")
                : estimate.maxPages
                  ? t("costUpTo", { pages: estimate.maxPages, credits: estimate.credits })
                  : t("costUnlimited")
          }
        />
        {estimate?.maxJudgements ? (
          <Line
            label={t("costJudging")}
            value={t("costJudgingUpTo", { count: estimate.maxJudgements })}
          />
        ) : null}
        {estimate?.readsPages && estimate.maxPages ? (
          <p className="pt-1 text-fg-faint">
            {t("costPerLead", { pages: estimate.pagesPerLead })}
          </p>
        ) : null}
        {estimate?.readsPages && estimate.browserPages ? (
          <p className="pt-1 text-fg-faint">{t("costBrowserNote")}</p>
        ) : null}
        <p className="pt-1 text-fg-faint">{t("costExpectedNote")}</p>
      </dl>
    </div>
  );
}

function Line({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-baseline justify-between gap-3">
      <dt>{label}</dt>
      <dd className="num text-fg">{value}</dd>
    </div>
  );
}
