"use client";

/**
 * Criteria tokens, in the interface language.
 *
 * The criteria store a country as "Spain" and an industry as "Cosmetics" because
 * that is what the backend keys on; a person reading the screen should see
 * "Іспанія" and "Косметика". Anything that is not a known token - a brand, a
 * city, a search from before the vocabularies existed - is shown as written.
 */

import { useTranslations } from "next-intl";
import { useCallback, useMemo } from "react";
import {
  BUSINESS_TYPES,
  COUNTRIES,
  INDUSTRIES,
  isPresetSignal,
  LANGUAGES,
  vocabularyEntry,
  type VocabularyEntry,
} from "@/lib/domain";
import type { SearchCriteria } from "@/services/types";

export function useVocabulary() {
  const t = useTranslations("domain");

  const label = useCallback(
    (namespace: string, list: VocabularyEntry[], token?: string | null) => {
      const entry = vocabularyEntry(list, token);
      return entry ? t(`${namespace}.${entry.id}`) : (token ?? "");
    },
    [t],
  );

  return useMemo(() => {
    const country = (token?: string | null) => label("country", COUNTRIES, token);
    const language = (token?: string | null) => label("language", LANGUAGES, token);
    const industry = (token?: string | null) => label("industry", INDUSTRIES, token);
    const businessType = (token?: string | null) =>
      label("businessType", BUSINESS_TYPES, token);

    /** Any token of either list - the joined target line mixes both. */
    const anyTerm = (token: string) =>
      vocabularyEntry(INDUSTRIES, token)
        ? industry(token)
        : vocabularyEntry(BUSINESS_TYPES, token)
          ? businessType(token)
          : token;

    /**
     * A requirement's name: the client's own words if it has them, the built-in
     * signal's translation otherwise, the bare id as a last resort.
     */
    const requirement = (entry: { type?: string; id?: string; label?: string | null }) => {
      const id = entry.id ?? entry.type ?? "";
      if (entry.label) return entry.label;
      return isPresetSignal(id) ? t(`signal.${id}`) : id;
    };

    return {
      requirement,
      country,
      language,
      industry,
      businessType,
      /**
       * The backend's `target` line ("MLM / Network marketing · Cosmetics"),
       * translated token by token. It is joined server-side, so it is split here.
       */
      target: (target: string) =>
        target
          .split(" · ")
          .map((part) => part.split(" / ").map((token) => anyTerm(token.trim())).join(" / "))
          .join(" · "),
      /** The same line, built from criteria directly. */
      criteriaTarget: (criteria: SearchCriteria) =>
        [
          criteria.businessTypes.map(businessType).join(" / "),
          criteria.industry.map(industry).join(" / "),
        ]
          .filter(Boolean)
          .join(" · "),
    };
  }, [label, t]);
}
