"use client";

import { AlertTriangle, ChevronRight, ShieldCheck } from "lucide-react";
import { useTranslations } from "next-intl";
import { SOURCE_KINDS, WEB_SOURCES } from "@/lib/domain";
import { useVocabulary } from "@/lib/vocabulary";
import type { SearchEstimate } from "@/services/types";
import { CheckboxField, SwitchField } from "@/components/ui/controls";
import { PlatformIcon } from "@/components/ui/misc";
import { QueriesPanel } from "@/components/search/wizard/queries-panel";
import { useWizardStore } from "@/store/wizard-store";

/**
 * Everything the old five-step wizard asked up front that a brief does not need
 * to answer: where to look, how strict the gates are, and the exact queries. Defaults that work, folded away - open for the
 * client who wants to tune, out of the way of the one who does not.
 */
export function AdvancedSettings({
  estimate,
  estimateLoading,
}: {
  estimate?: SearchEstimate;
  estimateLoading: boolean;
}) {
  const t = useTranslations("wizard.review");
  const { criteria, patchCriteria } = useWizardStore();

  return (
    <details id="wizard-advanced" className="group rounded-card border border-line">
      <summary className="flex cursor-pointer list-none items-center gap-2 px-4 py-3 select-none">
        <ChevronRight className="size-4 text-fg-faint transition-transform group-open:rotate-90" />
        <span className="text-sm font-semibold">{t("advanced")}</span>
        <span className="text-xs text-fg-faint">{t("advancedHint")}</span>
      </summary>

      <div className="flex flex-col gap-7 border-t border-line px-4 py-5">
        <Sources />
        <Requirements />
        <QueriesPanel
          own={criteria.customQueries ?? []}
          sources={criteria.sources}
          generated={estimate?.queries ?? []}
          loading={estimateLoading}
          onChange={(customQueries) => patchCriteria({ customQueries })}
        />
      </div>
    </details>
  );
}

function Sources() {
  const t = useTranslations("wizard.sources");
  const review = useTranslations("wizard.review");
  const sources = useTranslations("domain.source");
  const { criteria, toggleSource } = useWizardStore();

  return (
    <section id="wizard-sources" className="flex flex-col gap-3">
      <h3 className="text-sm font-semibold">{review("sourcesTitle")}</h3>
      <div className="grid gap-x-6 sm:grid-cols-2">
        {SOURCE_KINDS.map((source) => (
          <CheckboxField
            key={source.id}
            checked={criteria.sources.includes(source.id)}
            onCheckedChange={() => toggleSource(source.id)}
            label={
              <span className="flex items-center gap-2">
                {source.platform ? (
                  <PlatformIcon platform={source.platform} className="text-fg-faint" />
                ) : null}
                {sources(`${source.id}.label`)}
              </span>
            }
            hint={sources(`${source.id}.hint`)}
          />
        ))}
      </div>
      <div className="flex gap-3 rounded-card border border-line bg-surface-2 px-4 py-3">
        <ShieldCheck className="mt-0.5 size-4 shrink-0 text-good" />
        <div className="text-xs leading-relaxed text-fg-muted">
          <p className="mb-1 font-medium text-fg">{t("privacyTitle")}</p>
          <p>{t("privacyBody")}</p>
        </div>
      </div>
    </section>
  );
}

function Requirements() {
  const t = useTranslations("wizard.geography");
  const review = useTranslations("wizard.review");
  const vocabulary = useVocabulary();
  const { criteria, patchCriteria } = useWizardStore();

  const socialOnly =
    criteria.sources.length > 0 &&
    !criteria.sources.some((source) => WEB_SOURCES.includes(source));
  const strictOverSocialOnly =
    socialOnly &&
    Boolean(criteria.requireConfirmedLocation || criteria.requireConfirmedLanguage);
  // One country, several, or a region: named as the client chose them.
  const places = [
    ...(criteria.location.country ? [criteria.location.country] : (criteria.countries ?? [])).map(
      vocabulary.country,
    ),
    ...(criteria.region === "europe" ? [review("regionEurope")] : []),
  ];
  const country = places.join(" / ");

  return (
    <section className="flex flex-col gap-1">
      <h3 className="text-sm font-semibold">{review("strictnessTitle")}</h3>
      <SwitchField
        checked={criteria.requireLocation ?? true}
        onCheckedChange={(requireLocation) => patchCriteria({ requireLocation })}
        label={
          country
            ? t("noOutsideCountry", { country })
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
            ? t("noOtherLanguages", {
                languages: criteria.languages.map(vocabulary.language).join(" / "),
              })
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

      {/* Confirmation has to come from the profile page, and a social page is the
          one kind that most often will not open - a measured run refused 19
          candidates this way and 18 had simply said nothing about where they were. */}
      {strictOverSocialOnly ? (
        <p className="mt-2 flex gap-2 rounded-card border border-warn/30 bg-warn-soft px-3 py-2 text-xs leading-relaxed text-fg-muted">
          <AlertTriangle className="mt-0.5 size-3.5 shrink-0 text-warn" />
          <span>{t("socialOnlyWarning")}</span>
        </p>
      ) : null}
    </section>
  );
}
