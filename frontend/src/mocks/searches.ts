/** Mock search history. Shapes match the `Search` contract exactly. */

import { criteriaTarget, DEFAULT_SIGNAL_WEIGHTS } from "@/lib/domain";
import { generateQueryPreview } from "@/lib/query-preview";
import { MOCK_LEADS_BY_SEARCH } from "./leads";
import type {
  GeneratedQuery,
  Search,
  SearchCriteria,
  SearchProgress,
  SearchStatus,
} from "@/services/types";

const NOW = new Date();
const HOUR = 3_600_000;
const isoHoursAgo = (hours: number) => new Date(NOW.getTime() - hours * HOUR).toISOString();

function criteria(partial: Partial<SearchCriteria>): SearchCriteria {
  return {
    industry: [],
    businessTypes: [],
    keywords: [],
    negativeKeywords: [],
    location: {},
    languages: [],
    mustHave: ["mlm", "beauty", "activity"],
    niceToHave: ["leadership", "recruiting", "personalBrand"],
    signalWeights: { ...DEFAULT_SIGNAL_WEIGHTS },
    sources: ["public_web", "instagram_public", "linkedin_public", "facebook_public"],
    ...partial,
  };
}

function queriesFor(searchCriteria: SearchCriteria, resultCounts: number[]): GeneratedQuery[] {
  return generateQueryPreview(searchCriteria, 12).map((query, index) => ({
    id: `q_${index + 1}`,
    query,
    provider: "brave",
    resultCount: resultCounts[index % resultCounts.length],
  }));
}

function completedProgress(overrides: Partial<SearchProgress>): SearchProgress {
  return {
    queries: 12,
    queriesCompleted: 12,
    urlsDiscovered: 213,
    profilesDiscovered: 128,
    profilesProcessed: 128,
    qualified: 0,
    highQuality: 0,
    percent: 100,
    stage: "done",
    ...overrides,
  };
}

const ES_CRITERIA = criteria({
  industry: ["Beauty", "Cosmetics"],
  businessTypes: ["MLM", "Network marketing"],
  keywords: ["MIHI", "beauty", "network marketing", "team leader", "distributor"],
  negativeKeywords: ["customer", "shop", "beauty salon"],
  location: { country: "Spain" },
  languages: ["Spanish", "English", "Russian", "Ukrainian"],
});

const DE_CRITERIA = criteria({
  industry: ["Beauty", "Cosmetics"],
  businessTypes: ["MLM", "Empfehlungsmarketing"],
  keywords: ["MIHI", "Kosmetik", "Teamleiterin", "Vertriebspartner"],
  negativeKeywords: ["Kundin", "Shop", "Kosmetikstudio"],
  location: { country: "Germany" },
  languages: ["German", "English", "Russian"],
});

const IT_CRITERIA = criteria({
  industry: ["Beauty", "Skincare"],
  businessTypes: ["Network marketing", "Direct sales"],
  keywords: ["beauty", "network marketing", "consulente", "team"],
  negativeKeywords: ["cliente", "negozio"],
  location: { country: "Italy" },
  languages: ["Italian", "English"],
  sources: ["public_web", "instagram_public", "linkedin_public", "blogs"],
});

const PL_CRITERIA = criteria({
  industry: ["Beauty", "Wellness"],
  businessTypes: ["MLM", "Network marketing"],
  keywords: ["network marketing", "lider zespołu", "kosmetyki"],
  negativeKeywords: ["sklep", "klientka"],
  location: { country: "Poland" },
  languages: ["Polish", "English", "Ukrainian"],
});

function leadStats(searchId: string) {
  const leads = MOCK_LEADS_BY_SEARCH[searchId] ?? [];
  return {
    leadCount: leads.length,
    highQualityCount: leads.filter((lead) => lead.score >= 85).length,
  };
}

function search(
  id: string,
  name: string,
  searchCriteria: SearchCriteria,
  status: SearchStatus,
  hoursAgo: number,
  overrides: Partial<Search> = {},
): Search {
  const stats = leadStats(id);
  return {
    id,
    name,
    status,
    createdAt: isoHoursAgo(hoursAgo),
    startedAt: isoHoursAgo(hoursAgo),
    completedAt: status === "completed" ? isoHoursAgo(hoursAgo - 0.2) : undefined,
    target: criteriaTarget(searchCriteria),
    country: searchCriteria.location.country,
    sources: searchCriteria.sources,
    criteria: searchCriteria,
    leadCount: stats.leadCount,
    highQualityCount: stats.highQualityCount,
    progress: completedProgress({
      qualified: stats.leadCount,
      highQuality: stats.highQualityCount,
    }),
    usage: {
      searchApiCalls: 12,
      pagesAnalyzed: 104,
      // Read + cached add up to analyzed: a page the cache answered cost nothing.
      pagesRead: 96,
      pagesCached: 8,
      scrapeCredits: 96,
      llmCalls: 67,
      estimatedCostEur: 1.84,
    },
    queries: queriesFor(searchCriteria, [24, 18, 31, 12, 9, 27, 15, 21]),
    ...overrides,
  };
}

/**
 * Note the numbers in the demo dashboard describe a fuller workspace than this
 * fixture list — the demo pretends earlier searches were pruned.
 */
export const MOCK_SEARCHES: Search[] = [
  search("srch_es_mihi", "MIHI Beauty Leaders Spain", ES_CRITERIA, "completed", 3, {
    leadCount: 153,
    usage: {
      searchApiCalls: 14,
      pagesAnalyzed: 187,
      pagesRead: 173,
      pagesCached: 14,
      scrapeCredits: 173,
      llmCalls: 126,
      estimatedCostEur: 2.41,
    },
    progress: completedProgress({
      queries: 14,
      queriesCompleted: 14,
      urlsDiscovered: 187,
      profilesDiscovered: 126,
      profilesProcessed: 126,
      qualified: 153,
      highQuality: leadStats("srch_es_mihi").highQualityCount,
    }),
  }),
  search("srch_de_mihi", "MIHI distributors — Germany", DE_CRITERIA, "completed", 28, {
    leadCount: 84,
    usage: {
      searchApiCalls: 11,
      pagesAnalyzed: 132,
      pagesRead: 118,
      pagesCached: 14,
      scrapeCredits: 118,
      llmCalls: 88,
      estimatedCostEur: 1.63,
    },
    progress: completedProgress({
      queries: 11,
      queriesCompleted: 11,
      urlsDiscovered: 132,
      profilesDiscovered: 88,
      profilesProcessed: 88,
      qualified: 84,
      highQuality: leadStats("srch_de_mihi").highQualityCount,
    }),
  }),
  search("srch_pl_network", "Network Marketing Leaders — Poland", PL_CRITERIA, "extracting", 0.4, {
    completedAt: undefined,
    leadCount: 0,
    highQualityCount: 0,
    progress: {
      queries: 12,
      queriesCompleted: 12,
      urlsDiscovered: 164,
      profilesDiscovered: 97,
      profilesProcessed: 41,
      qualified: 19,
      highQuality: 6,
      percent: 58,
      stage: "extracting",
    },
    usage: {
      searchApiCalls: 12,
      pagesAnalyzed: 41,
      pagesRead: 33,
      pagesCached: 8,
      scrapeCredits: 33,
      llmCalls: 24,
      estimatedCostEur: 0.62,
    },
  }),
  search("srch_it_beauty", "Beauty founders — Italy", IT_CRITERIA, "completed", 76, {
    leadCount: 61,
    usage: {
      searchApiCalls: 9,
      pagesAnalyzed: 96,
      pagesRead: 96,
      pagesCached: 0,
      scrapeCredits: 96,
      llmCalls: 58,
      estimatedCostEur: 1.12,
    },
    progress: completedProgress({
      queries: 9,
      queriesCompleted: 9,
      urlsDiscovered: 96,
      profilesDiscovered: 58,
      profilesProcessed: 58,
      qualified: 61,
      highQuality: leadStats("srch_it_beauty").highQualityCount,
    }),
  }),
];
