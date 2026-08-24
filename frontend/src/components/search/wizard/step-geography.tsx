"use client";

import { ChipInput } from "@/components/ui/chip-input";
import { SelectField, SwitchField } from "@/components/ui/controls";
import { Field, Input } from "@/components/ui/field";
import { Eyebrow } from "@/components/ui/misc";
import { useWizardStore } from "@/store/wizard-store";

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
  const { criteria, setLocation, patchCriteria } = useWizardStore();

  return (
    <div className="flex flex-col gap-6">
      <div className="grid gap-6 md:grid-cols-3">
        <Field label="Country" optional hint="Appended to every generated query.">
          <SelectField
            ariaLabel="Country"
            value={criteria.location.country || undefined}
            onValueChange={(country) => setLocation({ country })}
            placeholder="Any country"
            options={COUNTRIES.map((country) => ({ value: country, label: country }))}
            className="w-full"
          />
        </Field>

        <Field label="Region" optional htmlFor="region">
          <Input
            id="region"
            value={criteria.location.region ?? ""}
            onChange={(event) => setLocation({ region: event.target.value })}
            placeholder="Catalonia"
          />
        </Field>

        <Field label="City" optional htmlFor="city">
          <Input
            id="city"
            value={criteria.location.city ?? ""}
            onChange={(event) => setLocation({ city: event.target.value })}
            placeholder="Barcelona"
          />
        </Field>
      </div>

      <Field
        label="Languages"
        optional
        hint="Used for query wording and, later, for the language of outreach drafts. Migrant communities are often the strongest match — Russian and Ukrainian speakers in Spain, for example."
      >
        <ChipInput
          values={criteria.languages}
          onChange={(languages) => patchCriteria({ languages })}
          placeholder="Spanish, English…"
          suggestions={LANGUAGE_SUGGESTIONS}
        />
      </Field>

      <section className="rounded-card border border-line bg-surface-2 px-4 py-3">
        <Eyebrow className="mb-1">Requirements, not preferences</Eyebrow>
        <SwitchField
          checked={criteria.requireLocation ?? true}
          onCheckedChange={(requireLocation) => patchCriteria({ requireLocation })}
          label={
            criteria.location.country
              ? `Only people in ${criteria.location.country}`
              : "Only people in the chosen country"
          }
          hint="A candidate whose profile does not place them there never becomes a lead. Turn this off and geographic match goes back to being worth points instead."
        />
        <SwitchField
          checked={criteria.requireLanguage ?? true}
          onCheckedChange={(requireLanguage) => patchCriteria({ requireLanguage })}
          label={
            criteria.languages.length
              ? `Only people publishing in ${criteria.languages.join(" / ")}`
              : "Only people publishing in the chosen languages"
          }
          hint="Judged on what the profile is written in. Off is worth trying when a country returns very few people: not every bio gives its language away."
        />
      </section>

      <p className="rounded-card border border-line bg-surface-2 px-4 py-3 text-xs leading-relaxed text-fg-muted">
        The country and languages also shape the questions asked: a search for
        Ukraine in Ukrainian is run against the Ukrainian index, in Ukrainian
        words. Leaving both empty widens the search to the whole public web, and
        the switches above then have nothing to apply.
      </p>
    </div>
  );
}
