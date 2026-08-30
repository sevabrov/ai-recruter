"use client";

import { ShieldCheck } from "lucide-react";
import { useTranslations } from "next-intl";
import { SOURCE_KINDS } from "@/lib/domain";
import { CheckboxField } from "@/components/ui/controls";
import { PlatformIcon } from "@/components/ui/misc";
import { useWizardStore } from "@/store/wizard-store";

export function StepSources() {
  const t = useTranslations("wizard.sources");
  const sources = useTranslations("domain.source");
  const { criteria, toggleSource } = useWizardStore();

  return (
    <div className="flex flex-col gap-5">
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

      <div className="flex gap-3 rounded-card border border-line bg-surface-2 px-4 py-3.5">
        <ShieldCheck className="mt-0.5 size-4 shrink-0 text-good" />
        <div className="text-xs leading-relaxed text-fg-muted">
          <p className="mb-1 font-medium text-fg">{t("privacyTitle")}</p>
          <p>{t("privacyBody")}</p>
        </div>
      </div>

      {!criteria.sources.length ? (
        <p className="text-xs text-warn">{t("selectOne")}</p>
      ) : null}
    </div>
  );
}
