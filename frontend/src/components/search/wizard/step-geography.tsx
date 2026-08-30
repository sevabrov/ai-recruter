"use client";

import { AlertTriangle } from "lucide-react";
import { useTranslations } from "next-intl";
import { ChipInput } from "@/components/ui/chip-input";
import { SelectField, SwitchField } from "@/components/ui/controls";
import { Field, Input } from "@/components/ui/field";
import { Eyebrow } from "@/components/ui/misc";
import { WEB_SOURCES } from "@/lib/domain";
import { useWizardStore } from "@/store/wizard-store";

/**
 * Country and language names are query tokens, not interface copy: the backend
 * appends them to the generated queries verbatim and picks the market index
 * from them. They stay in one spelling across all three interface languages, or
 * the same search would ask a different question depending on who opened it.
 */
const COUNTRIES = [
  "Spain",
  "Germany",
  "Italy",
  "Poland",
  "Portugal",
  "France",
  "Netherlands",
  "Czechia",
  "Austria",
  "Switzerland",
  "United Kingdom",
  "Ukraine",
];

const LANGUAGE_SUGGESTIONS = [
  "Spanish",
  "English",
  "Russian",
  "Ukrainian",
  "German",
  "Italian",
  "Polish",
  "Portuguese",
  "French",
];

export function StepGeography() {
  const t = useTranslations("wizard.geography");
  const { criteria, setLocation, patchCriteria } = useWizardStore();

  const socialOnly =
    criteria.sources.length > 0 &&
    !criteria.sources.some((source) => WEB_SOURCES.includes(source));
  const strictOverSocialOnly =
    socialOnly &&
    Boolean(criteria.requireConfirmedLocation || criteria.requireConfirmedLanguage);

  return (
    <div className="flex flex-col gap-6">
      <div className="grid gap-6 md:grid-cols-3">
        <Field label={t("countryLabel")} optional hint={t("countryHint")}>
          <SelectField
            ariaLabel={t("countryLabel")}
            value={criteria.location.country || undefined}
            onValueChange={(country) => setLocation({ country })}
            placeholder={t("anyCountry")}
            options={COUNTRIES.map((country) => ({ value: country, label: country }))}
            className="w-full"
          />
        </Field>

        <Field label={t("regionLabel")} optional htmlFor="region">
          <Input
            id="region"
            value={criteria.location.region ?? ""}
            onChange={(event) => setLocation({ region: event.target.value })}
            placeholder={t("regionPlaceholder")}
          />
        </Field>

        <Field label={t("cityLabel")} optional htmlFor="city">
          <Input
            id="city"
            value={criteria.location.city ?? ""}
            onChange={(event) => setLocation({ city: event.target.value })}
            placeholder={t("cityPlaceholder")}
          />
        </Field>
      </div>

      <Field label={t("languagesLabel")} optional hint={t("languagesHint")}>
        <ChipInput
          values={criteria.languages}
          onChange={(languages) => patchCriteria({ languages })}
          placeholder={t("languagesPlaceholder")}
          suggestions={LANGUAGE_SUGGESTIONS}
        />
      </Field>

      <section className="rounded-card border border-line bg-surface-2 px-4 py-3">
        <Eyebrow className="mb-1">{t("requirementsTitle")}</Eyebrow>
        <SwitchField
          checked={criteria.requireLocation ?? true}
          onCheckedChange={(requireLocation) => patchCriteria({ requireLocation })}
          label={
            criteria.location.country
              ? t("noOutsideCountry", { country: criteria.location.country })
              : t("noOutsideCountryGeneric")
          }
          hint={t("noOutsideCountryHint")}
        />
        {(criteria.requireLocation ?? true) ? (
          <SwitchField
            checked={criteria.requireConfirmedLocation ?? false}
            onCheckedChange={(requireConfirmedLocation) =>
              patchCriteria({ requireConfirmedLocation })
            }
            label={t("confirmedOnly")}
            hint={t("confirmedLocationHint")}
          />
        ) : null}
        <SwitchField
          checked={criteria.requireLanguage ?? true}
          onCheckedChange={(requireLanguage) => patchCriteria({ requireLanguage })}
          label={
            criteria.languages.length
              ? t("noOtherLanguages", { languages: criteria.languages.join(" / ") })
              : t("noOtherLanguagesGeneric")
          }
          hint={t("noOtherLanguagesHint")}
        />
        {(criteria.requireLanguage ?? true) ? (
          <SwitchField
            checked={criteria.requireConfirmedLanguage ?? false}
            onCheckedChange={(requireConfirmedLanguage) =>
              patchCriteria({ requireConfirmedLanguage })
            }
            label={t("confirmedOnly")}
            hint={t("confirmedLanguageHint")}
          />
        ) : null}

        {/* Said where the switch is, not three steps later on the review screen.
            Confirmation has to come from the profile page, and a social page is
            the one kind that most often will not open — so over social sources
            alone, "confirmed only" is a requirement most candidates cannot meet
            however good they are. A measured run refused 19 candidates this way
            and 18 of them had simply said nothing about where they were. */}
        {strictOverSocialOnly ? (
          <p className="mt-2 flex gap-2 rounded-card border border-warn/30 bg-warn-soft px-3 py-2 text-xs leading-relaxed text-fg-muted">
            <AlertTriangle className="mt-0.5 size-3.5 shrink-0 text-warn" />
            <span>{t("socialOnlyWarning")}</span>
          </p>
        ) : null}
      </section>

      <p className="rounded-card border border-line bg-surface-2 px-4 py-3 text-xs leading-relaxed text-fg-muted">
        {t("footnote")}
      </p>
    </div>
  );
}
