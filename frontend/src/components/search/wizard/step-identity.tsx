"use client";

import { ChipInput } from "@/components/ui/chip-input";
import { Field, Input } from "@/components/ui/field";
import { useWizardStore } from "@/store/wizard-store";

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
  const { name, criteria, setName, patchCriteria } = useWizardStore();

  return (
    <div className="flex flex-col gap-6">
      <Field
        label="Search name"
        htmlFor="search-name"
        hint="Only for your workspace — it never reaches a search query."
      >
        <Input
          id="search-name"
          value={name}
          onChange={(event) => setName(event.target.value)}
          placeholder="MIHI Beauty Leaders Spain"
        />
      </Field>

      <div className="grid gap-6 md:grid-cols-2">
        <Field label="Industry" hint="Narrows the vocabulary used to build queries.">
          <ChipInput
            values={criteria.industry}
            onChange={(industry) => patchCriteria({ industry })}
            placeholder="Beauty, cosmetics…"
            suggestions={INDUSTRY_SUGGESTIONS}
          />
        </Field>

        <Field label="Business type" hint="How these people earn — the strongest single signal.">
          <ChipInput
            values={criteria.businessTypes}
            onChange={(businessTypes) => patchCriteria({ businessTypes })}
            placeholder="MLM, network marketing…"
            suggestions={BUSINESS_SUGGESTIONS}
          />
        </Field>
      </div>

      <Field
        label="Keywords"
        hint="Brand names, role titles and phrases these people use about themselves. Each keyword multiplies into several search queries."
      >
        <ChipInput
          values={criteria.keywords}
          onChange={(keywords) => patchCriteria({ keywords })}
          placeholder="MIHI, team leader, distributor…"
          suggestions={KEYWORD_SUGGESTIONS}
        />
      </Field>

      <Field
        label="Negative keywords"
        hint="Pages containing these are dropped before analysis — the cheapest way to keep customers and shops out of your results."
      >
        <ChipInput
          values={criteria.negativeKeywords}
          onChange={(negativeKeywords) => patchCriteria({ negativeKeywords })}
          placeholder="customer, shop, salon…"
          suggestions={NEGATIVE_SUGGESTIONS}
          tone="negative"
        />
      </Field>
    </div>
  );
}
