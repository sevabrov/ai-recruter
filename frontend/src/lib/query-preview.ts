/**
 * Deterministic query templates — a front-end preview of the backend's
 * QueryGeneratorService (spec §29). Templates only, no LLM. Once the backend
 * owns generation, this file is used for the wizard preview only, or dropped in
 * favour of a `POST /searches/preview` call returning the same strings.
 */

import { SITE_BY_SOURCE, WEB_SOURCES } from "@/lib/domain";
import type { SearchCriteria } from "@/services/types";

export function generateQueryPreview(criteria: SearchCriteria, limit = 8): string[] {
  const country = criteria.location.city
    ? `${criteria.location.city} ${criteria.location.country ?? ""}`.trim()
    : (criteria.location.country ?? "");
  const keywords = criteria.keywords.length ? criteria.keywords : ["network marketing"];
  const industries = criteria.industry.length ? criteria.industry : ["beauty"];
  const businessTypes = criteria.businessTypes.length
    ? criteria.businessTypes
    : ["network marketing"];

  const queries: string[] = [];
  const push = (parts: (string | undefined)[]) => {
    const query = parts.filter(Boolean).join(" ").replace(/\s+/g, " ").trim();
    if (query && !queries.includes(query)) queries.push(query);
  };

  for (const source of criteria.sources) {
    const site = SITE_BY_SOURCE[source];
    if (!site) continue;
    push([site, `"${keywords[0]}"`, country]);
    if (keywords[1]) {
      push([site, `"${keywords[1]}"`, industries[0], country]);
      continue;
    }
    // With one keyword — and with none, that one is the niche's generic name —
    // the query returns the niche's brands. The industry and a role word are
    // what turn it back into a description of a person (see the backend's
    // generator, which does the same in each chosen language).
    if (criteria.industry.length) push([site, `"${keywords[0]}"`, industries[0], country]);
    push([site, `"${keywords[0]}"`, "distributor", country]);
  }

  // Only when the open web was actually asked for: these carry no `site:`
  // operator, and with three social sources selected they were a third of the
  // billed calls spent outside the sources (see the backend's generator).
  if (criteria.sources.some((source) => WEB_SOURCES.includes(source))) {
    push([`"${keywords[0]} distributor"`, country]);
    push([`"${industries[0]} team leader"`, `"${businessTypes[0]}"`, country]);
    push([`"${businessTypes[0]}"`, industries[0], country, "leader"]);

    if (criteria.sources.includes("company_websites")) {
      push([`"${keywords[0]}"`, "distributor", country, "-shop", "-tienda"]);
    }
    if (criteria.sources.includes("blogs")) {
      push([`"${industries[0]}"`, `"${businessTypes[0]}"`, "blog", country]);
    }
  }

  const negatives = criteria.negativeKeywords.slice(0, 2).map((word) => `-"${word}"`);
  const templates = queries
    .slice(0, limit)
    .map((query) => (negatives.length ? `${query} ${negatives.join(" ")}` : query));

  // Hand-written queries come first and are never dropped by the cap, exactly as
  // the backend orders them — and one without a `site:` inherits the sources, so
  // a bare word is not a question to the whole web when only social was asked for.
  const sites = criteria.sources
    .map((source) => SITE_BY_SOURCE[source])
    .filter((site): site is string => Boolean(site));
  const scopeToSites =
    sites.length > 0 && !criteria.sources.some((source) => WEB_SOURCES.includes(source));
  const own = (criteria.customQueries ?? [])
    .map((query) => query.trim())
    .filter(Boolean)
    .flatMap((query) =>
      scopeToSites && !/\bsite:/i.test(query) ? sites.map((site) => `${site} ${query}`) : [query],
    );
  return [...own, ...templates].slice(0, Math.max(limit, own.length));
}
