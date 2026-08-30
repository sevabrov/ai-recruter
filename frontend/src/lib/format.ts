"use client";

/**
 * Locale-aware formatting.
 *
 * Numbers, currency and dates all follow the active locale, so 1 284 reads as
 * `1,284` in English and `1 284` in Ukrainian and Russian without a component
 * knowing which language it is in. Everything here is a hook because the locale
 * comes from the request, never from a module-level constant.
 */

import { useFormatter, useTranslations } from "next-intl";

export function useNumbers() {
  const format = useFormatter();

  return {
    /** Plain count: thousands separated the way the locale separates them. */
    number: (value: number) => format.number(value),
    /** Euro amount; the currency is the product's, the placement is the locale's. */
    eur: (value: number) => format.number(value, "eur"),
    /** Whole-percent readout used by confidence meters and share bars. */
    percent: (fraction: number) => `${Math.round(fraction * 100)}%`,
  };
}

/**
 * Coarse "how long ago" used next to discovered dates. Deliberately compact:
 * these sit inside table rows, so anything past a week becomes a short date.
 */
export function useTimeAgo() {
  const t = useTranslations("format");
  const format = useFormatter();

  return (iso: string, now = Date.now()) => {
    const diff = now - new Date(iso).getTime();
    const minute = 60_000;
    const hour = 60 * minute;
    const day = 24 * hour;

    if (diff < minute) return t("justNow");
    if (diff < hour) return t("minutesAgo", { count: Math.floor(diff / minute) });
    if (diff < day) return t("hoursAgo", { count: Math.floor(diff / hour) });
    if (diff < 7 * day) return t("daysAgo", { count: Math.floor(diff / day) });
    return format.dateTime(new Date(iso), "short");
  };
}

export function useDateTime() {
  const format = useFormatter();
  return (iso: string) => format.dateTime(new Date(iso), "stamp");
}
