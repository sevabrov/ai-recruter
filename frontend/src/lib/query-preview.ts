/**
 * Deterministic query templates — a front-end preview of the backend's
 * QueryGeneratorService (spec §29). Templates only, no LLM. Once the backend
 * owns generation, this file is used for the wizard preview only, or dropped in
 * favour of a `POST /searches/preview` call returning the same strings.
 */

import type { SearchCriteria, SourceKind } from "@/services/types";

const SITE_BY_SOURCE: Partial<Record<SourceKind, string>> = {
  instagram_public: "site:instagram.com",
  linkedin_public: "site:linkedin.com/in",
  facebook_public: "site:facebook.com",
  threads_public: "site:threads.net",
};

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
    if (keywords[1]) push([site, `"${keywords[1]}"`, industries[0], country]);
  }

  push([`"${keywords[0]} distributor"`, country]);
  push([`"${industries[0]} team leader"`, `"${businessTypes[0]}"`, country]);
  push([`"${businessTypes[0]}"`, industries[0], country, "leader"]);

  if (criteria.sources.includes("company_websites")) {
    push([`"${keywords[0]}"`, "distributor", country, "-shop", "-tienda"]);
  }
  if (criteria.sources.includes("blogs")) {
    push([`"${industries[0]}"`, `"${businessTypes[0]}"`, "blog", country]);
  }

  const negatives = criteria.negativeKeywords.slice(0, 2).map((word) => `-"${word}"`);
  return queries
    .slice(0, limit)
    .map((query) => (negatives.length ? `${query} ${negatives.join(" ")}` : query));
}
