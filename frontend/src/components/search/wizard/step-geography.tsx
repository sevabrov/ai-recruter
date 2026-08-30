"use client";

import { AlertTriangle } from "lucide-react";
import { ChipInput } from "@/components/ui/chip-input";
import { SelectField, SwitchField } from "@/components/ui/controls";
import { Field, Input } from "@/components/ui/field";
import { Eyebrow } from "@/components/ui/misc";
import type { SourceKind } from "@/services/types";
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

/** Sources that mean "anywhere on the indexed web", where a page usually opens. */
const WEB_SOURCES: SourceKind[] = ["public_web", "company_websites", "blogs"];

export function StepGeography() {
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
              ? `Nobody from outside ${criteria.location.country}`
              : "Nobody from outside the chosen country"
          }
          hint="A profile that places the person somewhere else is refused. Turn this off and geographic match goes back to being worth points instead."
        />
        {(criteria.requireLocation ?? true) ? (
          <SwitchField
            checked={criteria.requireConfirmedLocation ?? false}
            onCheckedChange={(requireConfirmedLocation) =>
              patchCriteria({ requireConfirmedLocation })
            }
            label="…and only if it can be confirmed"
            hint="Strict: a profile that says nothing about where the person is gets dropped too. Off, it becomes a lead that scores lower — which is usually what you want, because most social profiles never name a city and their pages will not open."
          />
        ) : null}
        <SwitchField
          checked={criteria.requireLanguage ?? true}
          onCheckedChange={(requireLanguage) => patchCriteria({ requireLanguage })}
          label={
            criteria.languages.length
              ? `Nobody publishing only in other languages than ${criteria.languages.join(" / ")}`
              : "Nobody publishing only in other languages"
          }
          hint="Judged on what the profile is written in."
        />
        {(criteria.requireLanguage ?? true) ? (
          <SwitchField
            checked={criteria.requireConfirmedLanguage ?? false}
            onCheckedChange={(requireConfirmedLanguage) =>
              patchCriteria({ requireConfirmedLanguage })
            }
            label="…and only if it can be confirmed"
            hint="A two-line profile description often shows no language at all. Leave this off unless you would rather have five certain people than fifty likely ones."
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
            <span>
              Only social sources are selected. Profiles there rarely state a
              country or a language, so “only if it can be confirmed” will drop
              most of what this search finds. Worth turning on once you have seen
              what it returns without it.
            </span>
          </p>
        ) : null}
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
