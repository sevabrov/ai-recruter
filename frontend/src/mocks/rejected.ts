/**
 * The refused half of a mock search result.
 *
 * The offline demo has no web to be refused by, so this generates a spread that
 * behaves like a real one: the counts add up to what the search's own progress
 * says it discovered but did not keep, the addresses are shaped like the ones a
 * provider really returns, and the reasons appear in the proportions the measured
 * runs actually produced — most refusals happen before anything is read.
 *
 * Deterministic per search id, so the demo does not reshuffle on every render.
 */

import { hashString, seededRandom } from "@/lib/utils";
import type {
  Platform,
  RejectedCandidate,
  RejectedList,
  RejectionReason,
  Search,
} from "@/services/types";

/** Roughly the shape of a measured run: the free refusals dominate. */
const MIX: { reason: RejectionReason; share: number; read: boolean }[] = [
  { reason: "not_a_profile", share: 0.34, read: false },
  { reason: "off_source", share: 0.16, read: false },
  { reason: "not_a_person", share: 0.18, read: true },
  { reason: "wrong_country", share: 0.12, read: true },
  { reason: "wrong_language", share: 0.06, read: true },
  { reason: "missing_signals", share: 0.08, read: true },
  { reason: "unreadable", share: 0.06, read: false },
];

const HANDLES = [
  "beauty.by.marta",
  "kosmetyka_ewa",
  "mihi.team.eu",
  "anna_wellness",
  "sklep.uroda24",
  "network.pro.club",
  "lucia.beauty",
  "team.leader.pl",
  "hurtownia.kosmetyki",
  "olga.skincare",
  "beautyblog.example.com",
  "profile.php",
];

const DETAILS: Record<RejectionReason, string> = {
  not_a_profile: "A shop page rather than somebody's profile.",
  off_source: "Found on a platform that is not among this search's sources.",
  unreadable: "The reader failed on this address, so nothing here was ever seen.",
  not_a_person: "The page was read and named no person: a brand account or a shop.",
  wrong_country: "This profile is somewhere else, not the country that was asked for.",
  wrong_language: "This profile publishes in a language this search did not ask for.",
  missing_signals: "Nothing on this profile showed: mlm.",
  not_examined: "The search already had the leads it was asked for and stopped here.",
};

const PLATFORMS: Platform[] = ["instagram", "facebook", "linkedin", "website"];

/** How many candidates this search saw and did not keep. */
function refusedCount(search: Search): number {
  const seen = search.progress.urlsDiscovered || 0;
  return Math.max(0, seen - search.leadCount);
}

export function rejectedFor(search: Search): RejectedList {
  const total = refusedCount(search);
  if (total === 0) return { items: [], total: 0, byReason: {}, unseen: 0 };

  const random = seededRandom(hashString(search.id));
  const byReason: Partial<Record<RejectionReason, number>> = {};
  let assigned = 0;
  MIX.forEach((entry, index) => {
    const count =
      index === MIX.length - 1 ? total - assigned : Math.round(total * entry.share);
    byReason[entry.reason] = Math.max(0, count);
    assigned += Math.max(0, count);
  });

  // Only the first page is materialised — the same thing the API does.
  const items: RejectedCandidate[] = [];
  for (const entry of MIX) {
    const count = Math.min(byReason[entry.reason] ?? 0, 8);
    for (let index = 0; index < count; index += 1) {
      const handle = HANDLES[Math.floor(random() * HANDLES.length)];
      const platform = PLATFORMS[Math.floor(random() * PLATFORMS.length)];
      items.push({
        id: `${search.id}__rej_${entry.reason}_${index}`,
        url: addressOf(platform, handle),
        platform,
        reason: entry.reason,
        detail: DETAILS[entry.reason],
        read: entry.read,
        name: handle,
        title: `${handle} — ${search.target}`,
        snippet: search.queries[0]?.query ?? "",
        query: search.queries[index % Math.max(1, search.queries.length)]?.query ?? "",
        promise: Math.round(30 + random() * 45),
        createdAt: search.createdAt,
      });
    }
  }

  items.sort((first, second) => (second.promise ?? 0) - (first.promise ?? 0));
  const unseen = MIX.filter((entry) => !entry.read).reduce(
    (sum, entry) => sum + (byReason[entry.reason] ?? 0),
    0,
  );
  return { items, total, byReason, unseen };
}

function addressOf(platform: Platform, handle: string): string {
  if (platform === "website") return `https://${handle.replace(/[._]/g, "-")}.example.com`;
  if (platform === "linkedin") return `https://linkedin.com/in/${handle}`;
  return `https://${platform}.com/${handle}`;
}
