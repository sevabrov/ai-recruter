/**
 * ROUTING / LOCALES
 * =================
 * Ukrainian is the primary language of this workspace, so it is the default and
 * the fallback for anything a translation file has not caught up with yet.
 *
 * Every route carries its prefix (`/uk/leads`, `/en/leads`, `/ru/leads`) so a
 * URL is never ambiguous about the language it renders in - a link pasted into
 * a chat opens in the language it was written in.
 */

import { defineRouting } from "next-intl/routing";

export const LOCALES = ["uk", "en", "ru"] as const;

export type AppLocale = (typeof LOCALES)[number];

export const DEFAULT_LOCALE: AppLocale = "uk";

export const routing = defineRouting({
  locales: LOCALES,
  defaultLocale: DEFAULT_LOCALE,
  localePrefix: "always",
  // A year: the choice is a workspace preference, not a session detail.
  localeCookie: { maxAge: 60 * 60 * 24 * 365 },
});

/** How each language names itself, plus the two letters shown in the switcher. */
export const LOCALE_META: Record<AppLocale, { name: string; short: string }> = {
  uk: { name: "Українська", short: "UA" },
  en: { name: "English", short: "EN" },
  ru: { name: "Русский", short: "RU" },
};

export function isAppLocale(value: unknown): value is AppLocale {
  return typeof value === "string" && (LOCALES as readonly string[]).includes(value);
}

/**
 * Font subsets each language needs. Ukrainian and Russian are Cyrillic; the
 * Latin subsets stay loaded for brand names and query operators, which appear
 * in every language.
 */
export const LOCALE_DIR: Record<AppLocale, "ltr"> = {
  uk: "ltr",
  en: "ltr",
  ru: "ltr",
};
