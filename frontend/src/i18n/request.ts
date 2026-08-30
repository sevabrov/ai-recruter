/**
 * Per-request i18n configuration consumed by next-intl on the server.
 *
 * Messages are loaded for the matched locale only, so a page never ships the
 * other two catalogues to the browser. Ukrainian is the source language and is
 * merged underneath as a fallback, so a key a translation has not caught up
 * with renders in Ukrainian rather than as its own dotted path.
 */

import { getRequestConfig } from "next-intl/server";
import { DEFAULT_LOCALE, isAppLocale } from "./routing";

type Messages = Record<string, unknown>;

function mergeMessages(base: Messages, override: Messages): Messages {
  const result: Messages = { ...base };
  for (const [key, value] of Object.entries(override)) {
    const current = result[key];
    result[key] =
      isPlainObject(current) && isPlainObject(value)
        ? mergeMessages(current, value)
        : value;
  }
  return result;
}

function isPlainObject(value: unknown): value is Messages {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

async function load(locale: string): Promise<Messages> {
  return (await import(`../../messages/${locale}.json`)).default as Messages;
}

export default getRequestConfig(async ({ requestLocale }) => {
  const requested = await requestLocale;
  const locale = isAppLocale(requested) ? requested : DEFAULT_LOCALE;

  const fallback = await load(DEFAULT_LOCALE);
  const messages =
    locale === DEFAULT_LOCALE ? fallback : mergeMessages(fallback, await load(locale));

  return {
    locale,
    messages,
    timeZone: "Europe/Kyiv",
    formats: {
      number: {
        eur: { style: "currency", currency: "EUR", maximumFractionDigits: 2 },
      },
      dateTime: {
        short: { month: "short", day: "numeric" },
        stamp: { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" },
      },
    },
  };
});
