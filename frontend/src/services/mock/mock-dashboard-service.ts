import { HIGH_QUALITY_THRESHOLD } from "@/lib/domain";
import { MOCK_DASHBOARD } from "@/mocks/dashboard";
import { MOCK_LEADS } from "@/mocks/leads";
import type { DashboardData, DashboardService, SearchSummary } from "@/services/types";
import { allLeads, allSearches, latency, projectSearch } from "./mock-db";

export class MockDashboardService implements DashboardService {
  async get(): Promise<DashboardData> {
    await latency(200);

    const searches = allSearches().map(projectSearch);
    const leads = allLeads();

    // Fixture aggregates describe a fuller workspace; anything the demo user
    // creates is added on top so the dashboard reacts to their own actions.
    const created = searches.filter((search) => search.id.startsWith("srch_local_"));
    const createdLeads = leads.filter((lead) => lead.searchId.startsWith("srch_local_"));

    const stats: DashboardData["stats"] = {
      totalLeads: bump(MOCK_DASHBOARD.stats.totalLeads, createdLeads.length),
      highQuality: bump(
        MOCK_DASHBOARD.stats.highQuality,
        createdLeads.filter((lead) => lead.score >= HIGH_QUALITY_THRESHOLD).length,
      ),
      searches: bump(MOCK_DASHBOARD.stats.searches, created.length),
      savedLeads: savedStat(leads.filter((lead) => lead.saved).length),
    };

    const recentSearches: SearchSummary[] = searches.slice(0, 5).map((search) => ({
      id: search.id,
      name: search.name,
      status: search.status,
      createdAt: search.createdAt,
      startedAt: search.startedAt,
      completedAt: search.completedAt,
      leadCount: search.leadCount,
      highQualityCount: search.highQualityCount,
      target: search.target,
      country: search.country,
      sources: search.sources,
    }));

    return {
      stats,
      recentSearches,
      sourceBreakdown: MOCK_DASHBOARD.sourceBreakdown,
      scoreDistribution: MOCK_DASHBOARD.scoreDistribution,
      weeklyLeads: MOCK_DASHBOARD.weeklyLeads,
    };
  }
}

function bump(stat: DashboardData["stats"]["totalLeads"], extra: number) {
  return extra ? { ...stat, value: stat.value + extra } : stat;
}

/** Saving or unsaving a lead moves the counter, so the tile feels wired up. */
const INITIAL_SAVED = MOCK_LEADS.filter((lead) => lead.saved).length;

function savedStat(savedNow: number) {
  const base = MOCK_DASHBOARD.stats.savedLeads;
  return {
    ...base,
    value: base.value - INITIAL_SAVED + savedNow,
    hint: `${savedNow} saved in this workspace`,
  };
}
