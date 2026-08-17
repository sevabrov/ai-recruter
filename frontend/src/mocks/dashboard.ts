/** Mock dashboard aggregates (spec §7). Numbers are illustrative. */

import type { DashboardData } from "@/services/types";

export const MOCK_DASHBOARD: Omit<DashboardData, "recentSearches"> = {
  stats: {
    totalLeads: { label: "Total leads", value: 1284, delta: 12.4, hint: "across 27 searches" },
    highQuality: { label: "High quality", value: 342, delta: 8.1, hint: "score 85 and above" },
    searches: { label: "Searches", value: 27, delta: 3.7, hint: "4 in the last 7 days" },
    savedLeads: { label: "Saved leads", value: 186, delta: -2.3, hint: "31 awaiting outreach" },
  },
  sourceBreakdown: [
    { platform: "instagram", share: 42, leads: 539 },
    { platform: "linkedin", share: 28, leads: 359 },
    { platform: "facebook", share: 12, leads: 154 },
    { platform: "website", share: 10, leads: 129 },
    { platform: "blog", share: 5, leads: 64 },
    { platform: "threads", share: 3, leads: 39 },
  ],
  scoreDistribution: [
    { label: "90–100", from: 90, to: 100, count: 148 },
    { label: "85–89", from: 85, to: 89, count: 194 },
    { label: "70–84", from: 70, to: 84, count: 461 },
    { label: "50–69", from: 50, to: 69, count: 337 },
    { label: "< 50", from: 0, to: 49, count: 144 },
  ],
  weeklyLeads: [
    { day: "Mon", count: 34 },
    { day: "Tue", count: 61 },
    { day: "Wed", count: 48 },
    { day: "Thu", count: 92 },
    { day: "Fri", count: 76 },
    { day: "Sat", count: 27 },
    { day: "Sun", count: 18 },
  ],
};
