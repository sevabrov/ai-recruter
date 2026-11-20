"use client";

import { AlertTriangle, HelpCircle, Info, Minus, Plus } from "lucide-react";
import { useTranslations } from "next-intl";
import { useMemo, type ReactNode } from "react";
import {
  BUSINESS_TYPES,
  COUNTRIES,
  INDUSTRIES,
  LANGUAGES,
  SIGNAL_TYPES,
  type VocabularyEntry,
} from "@/lib/domain";
import { useNumbers } from "@/lib/format";
import { cn } from "@/lib/utils";
import { useVocabulary } from "@/lib/vocabulary";
import type { EstimateWarning, SearchEstimate, SignalType } from "@/services/types";
import { useSearchEstimate } from "@/services/hooks";
import {
  BLOCKING_GAPS,
  criteriaGaps,
  importanceOf,
  useWizardStore,
  type SignalImportance,
  type WizardGap,
} from "@/store/wizard-store";
import { Button } from "@/components/ui/button";
import { ChipInput } from "@/components/ui/chip-input";
import { SelectField } from "@/components/ui/controls";
import { Input } from "@/components/ui/field";
import { Eyebrow } from "@/components/ui/misc";
import { AdvancedSettings } from "@/components/search/wizard/advanced-settings";

/** What the wizard offers with one click. Any number can still be typed. */
const TARGETS = [5, 10, 25, 50];

/** The select value for "anywhere": Radix has no empty option, and none is a choice. */
const ANYWHERE = "__anywhere__";

/** Where each gap is answered, so the summary can take the client straight there. */
const GAP_FIELD: Record<WizardGap, string> = {
  terms: "wizard-brands",
  brands: "wizard-brands",
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
  const { name, setName, criteria, patchCriteria, setLocation, worldwide, setWorldwide } =
    useWizardStore();

  const countryOptions = useMemo(
    () => [
      { value: ANYWHERE, label: t("anywhere") },
      ...COUNTRIES.map((entry) => ({ value: entry.token, label: vocabulary.country(entry.token) }))
        .sort((a, b) => a.label.localeCompare(b.label)),
    ],
    [t, vocabulary],
  );

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
          <SelectField
            ariaLabel={t("fieldCountry")}
            value={criteria.location.country || (worldwide ? ANYWHERE : undefined)}
            onValueChange={(value) => {
              if (value === ANYWHERE) {
                setLocation({ country: undefined, city: undefined });
                setWorldwide(true);
              } else {
                setLocation({ country: value });
              }
            }}
            placeholder={t("fieldCountryPlaceholder")}
            options={countryOptions}
            className="w-full"
          />
        </ReviewField>
        <ReviewField id="wizard-city" label={t("fieldCity")} hint={t("fieldCityHint")}>
          <Input
            value={criteria.location.city ?? ""}
            onChange={(event) => setLocation({ city: event.target.value || undefined })}
            placeholder={t("fieldCityPlaceholder")}
            disabled={worldwide && !criteria.location.country}
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

      <Signals />
    </section>
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

const IMPORTANCE: SignalImportance[] = ["required", "preferred", "ignored"];

/**
 * What matters in a candidate, one choice per signal. The old wizard had two
 * checkbox lists for this — "must have" and "nice to have" — side by side, with
 * the same seven names in each.
 */
function Signals() {
  const t = useTranslations("wizard.review");
  const signals = useTranslations("domain.signal");
  const hints = useTranslations("domain.signalHint");
  const { criteria, setImportance } = useWizardStore();

  return (
    <div className="flex flex-col gap-1.5">
      <span className="label text-fg-muted">{t("fieldSignals")}</span>
      <p className="text-xs leading-relaxed text-fg-faint">{t("fieldSignalsHint")}</p>
      <ul className="divide-y divide-line rounded-card border border-line">
        {SIGNAL_TYPES.map((signal: SignalType) => {
          const current = importanceOf(criteria, signal);
          return (
            <li
              key={signal}
              className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2 px-3 py-2.5"
            >
              <div className="min-w-0">
                <p className="text-sm">{signals(signal)}</p>
                <p className="text-xs text-fg-faint">{hints(signal)}</p>
              </div>
              <div role="radiogroup" aria-label={signals(signal)} className="flex rounded-pill border border-line p-0.5">
                {IMPORTANCE.map((level) => (
                  <button
                    key={level}
                    type="button"
                    role="radio"
                    aria-checked={current === level}
                    onClick={() => setImportance(signal, level)}
                    className={cn(
                      "rounded-pill px-2.5 py-0.5 text-xs transition-colors",
                      current === level
                        ? level === "required"
                          ? "bg-accent text-accent-on"
                          : level === "preferred"
                            ? "bg-accent-soft text-accent"
                            : "bg-surface-2 text-fg-muted"
                        : "text-fg-faint hover:text-fg",
                    )}
                  >
                    {t(`importance.${level}`)}
                  </button>
                ))}
              </div>
            </li>
          );
        })}
      </ul>
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
      <Eyebrow className="mb-2">{t("costTitle")}</Eyebrow>
      <p className="num font-display text-3xl font-semibold">
        {loading || !estimate ? common("dash") : eur(estimate.maxCostEur)}
      </p>
      <dl className="mt-3 space-y-1 text-xs text-fg-muted">
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
                ? t("costNoReader")
                : estimate.maxPages
                  ? t("costUpTo", { pages: estimate.maxPages, credits: estimate.credits })
                  : t("costUnlimited")
          }
        />
        {estimate?.readsPages && estimate.maxPages ? (
          <p className="pt-1 text-fg-faint">
            {t("costPerLead", { pages: estimate.pagesPerLead })}
          </p>
        ) : null}
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
