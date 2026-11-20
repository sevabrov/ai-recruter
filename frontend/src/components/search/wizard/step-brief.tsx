"use client";

import { Check, Wand2 } from "lucide-react";
import { useTranslations } from "next-intl";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/field";
import { Eyebrow } from "@/components/ui/misc";
import { useWizardStore } from "@/store/wizard-store";

export const BRIEF_MAX = 4000;
/** Below this there is nothing to read: "косметика" is a word, not a search. */
export const BRIEF_MIN = 15;

/** What a useful description mentions — the things the review would otherwise ask. */
const TIPS = ["who", "whom", "brands", "where", "languages", "exclude", "count"] as const;

/**
 * Step one: the search in the client's own words.
 *
 * Any language: the brands and the phrases people use about themselves are kept
 * as written, because those are the search terms, and `джерелія` finds the people
 * a Ukrainian client means where a translation into English does not.
 */
export function StepBrief() {
  const t = useTranslations("wizard.brief");
  const { brief, setBrief } = useWizardStore();

  return (
    <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_15rem]">
      <div className="flex flex-col gap-2">
        <label htmlFor="brief" className="label text-fg-muted">
          {t("label")}
        </label>
        <Textarea
          id="brief"
          autoFocus
          value={brief}
          maxLength={BRIEF_MAX}
          onChange={(event) => setBrief(event.target.value)}
          placeholder={t("placeholder")}
          className="min-h-56 text-[15px]"
        />
        <div className="flex flex-wrap items-center justify-between gap-2">
          <p className="text-xs leading-relaxed text-fg-faint">{t("hint")}</p>
          <span className="num text-2xs text-fg-faint">
            {t("chars", { count: brief.length, max: BRIEF_MAX })}
          </span>
        </div>
        {!brief.trim() ? (
          <div>
            <Button variant="ghost" size="sm" onClick={() => setBrief(t("example"))}>
              <Wand2 />
              {t("useExample")}
            </Button>
          </div>
        ) : null}
      </div>

      <aside className="rounded-card border border-line bg-surface-2 px-4 py-3.5">
        <Eyebrow className="mb-2">{t("tipsTitle")}</Eyebrow>
        <ul className="flex flex-col gap-1.5">
          {TIPS.map((tip) => (
            <li key={tip} className="flex gap-2 text-xs leading-relaxed text-fg-muted">
              <Check className="mt-0.5 size-3 shrink-0 text-fg-faint" />
              <span>{t(`tips.${tip}`)}</span>
            </li>
          ))}
        </ul>
      </aside>
    </div>
  );
}
