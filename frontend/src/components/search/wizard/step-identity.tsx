"use client";

import { useTranslations } from "next-intl";
import { ChipInput } from "@/components/ui/chip-input";
import { Field, Input } from "@/components/ui/field";
import { useWizardStore } from "@/store/wizard-store";

/**
 * Suggestion chips are market vocabulary, not interface copy: they go into a
 * search query verbatim, so they stay in the language the market uses whatever
 * the interface is set to.
 */
const INDUSTRY_SUGGESTIONS = [
  "Beauty",
  "Cosmetics",
  "Skincare",
  "Wellness",
  "Hair",
  "Nails",
  "Supplements",
];

const BUSINESS_SUGGESTIONS = [
  "MLM",
  "Network marketing",
  "Direct sales",
  "Affiliate",
  "Franchise",
];

const KEYWORD_SUGGESTIONS = [
  "MIHI",
  "network marketing",
  "team leader",
  "distributor",
  "beauty coach",
  "consultant",
];

const NEGATIVE_SUGGESTIONS = ["customer", "shop", "beauty salon", "vacancy", "wholesale"];

export function StepIdentity() {
  const t = useTranslations("wizard.identity");
  const { name, criteria, setName, patchCriteria } = useWizardStore();

  return (
    <div className="flex flex-col gap-6">
      <Field label={t("nameLabel")} htmlFor="search-name" hint={t("nameHint")}>
        <Input
          id="search-name"
          value={name}
          onChange={(event) => setName(event.target.value)}
          placeholder={t("namePlaceholder")}
        />
      </Field>

      <div className="grid gap-6 md:grid-cols-2">
        <Field label={t("industryLabel")} hint={t("industryHint")}>
          <ChipInput
            values={criteria.industry}
            onChange={(industry) => patchCriteria({ industry })}
            placeholder={t("industryPlaceholder")}
            suggestions={INDUSTRY_SUGGESTIONS}
          />
        </Field>

        <Field label={t("businessLabel")} hint={t("businessHint")}>
          <ChipInput
            values={criteria.businessTypes}
            onChange={(businessTypes) => patchCriteria({ businessTypes })}
            placeholder={t("businessPlaceholder")}
            suggestions={BUSINESS_SUGGESTIONS}
          />
        </Field>
      </div>

      <Field label={t("keywordsLabel")} hint={t("keywordsHint")}>
        <ChipInput
          values={criteria.keywords}
          onChange={(keywords) => patchCriteria({ keywords })}
          placeholder={t("keywordsPlaceholder")}
          suggestions={KEYWORD_SUGGESTIONS}
        />
      </Field>

      <Field label={t("negativeLabel")} hint={t("negativeHint")}>
        <ChipInput
          values={criteria.negativeKeywords}
          onChange={(negativeKeywords) => patchCriteria({ negativeKeywords })}
          placeholder={t("negativePlaceholder")}
          suggestions={NEGATIVE_SUGGESTIONS}
          tone="negative"
        />
      </Field>
    </div>
  );
}
