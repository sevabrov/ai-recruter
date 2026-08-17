import { HIGH_QUALITY_THRESHOLD } from "@/lib/domain";
import type {
  Lead,
  LeadFilters,
  LeadService,
  OutreachMessage,
  OutreachRequest,
  Paginated,
  Platform,
  UpdateLeadInput,
} from "@/services/types";
import { allLeads, appendNote, findLead, latency, patchLead } from "./mock-db";

export function filterLeads(leads: Lead[], filters: LeadFilters = {}): Lead[] {
  const {
    searchId,
    query,
    minScore,
    countries,
    platforms,
    signals,
    statuses,
    hasEmail,
    hasSocial,
    savedOnly,
    includeArchived,
    sort = "score_desc",
  } = filters;

  const needle = query?.trim().toLowerCase();

  const filtered = leads.filter((lead) => {
    if (!includeArchived && lead.archived) return false;
    if (searchId && lead.searchId !== searchId) return false;
    if (savedOnly && !lead.saved) return false;
    if (minScore != null && lead.score < minScore) return false;
    if (statuses?.length && !statuses.includes(lead.status)) return false;
    if (countries?.length && !countries.includes(lead.location?.country ?? "")) return false;
    if (platforms?.length && !lead.platforms.some((entry) => platforms.includes(entry.platform)))
      return false;
    if (signals?.length) {
      const detected = new Set(
        lead.signals.filter((signal) => signal.detected).map((signal) => signal.type),
      );
      if (!signals.every((signal) => detected.has(signal))) return false;
    }
    if (hasEmail && !lead.contacts.email) return false;
    if (hasSocial && !lead.platforms.some((entry) => isSocial(entry.platform))) return false;
    if (needle) {
      const haystack = [
        lead.name,
        lead.headline,
        lead.company ?? "",
        lead.location?.city ?? "",
        lead.location?.country ?? "",
        lead.summary,
      ]
        .join(" ")
        .toLowerCase();
      if (!haystack.includes(needle)) return false;
    }
    return true;
  });

  return sortLeads(filtered, sort);
}

function isSocial(platform: Platform) {
  return platform === "instagram" || platform === "linkedin" || platform === "facebook" || platform === "threads";
}

function sortLeads(leads: Lead[], sort: NonNullable<LeadFilters["sort"]>) {
  const copy = [...leads];
  if (sort === "name_asc") return copy.sort((a, b) => a.name.localeCompare(b.name));
  if (sort === "newest")
    return copy.sort((a, b) => new Date(b.createdAt).getTime() - new Date(a.createdAt).getTime());
  return copy.sort((a, b) => b.score - a.score || a.name.localeCompare(b.name));
}

export function paginate<T>(items: T[], page = 1, pageSize = 50): Paginated<T> {
  const start = (page - 1) * pageSize;
  return {
    items: items.slice(start, start + pageSize),
    total: items.length,
    page,
    pageSize,
  };
}

export class MockLeadService implements LeadService {
  async list(filters: LeadFilters = {}): Promise<Paginated<Lead>> {
    await latency();
    const filtered = filterLeads(allLeads(), filters);
    return paginate(filtered, filters.page ?? 1, filters.pageSize ?? 50);
  }

  async get(id: string): Promise<Lead> {
    await latency(140);
    const lead = findLead(id);
    if (!lead) throw new Error(`Lead ${id} not found`);
    return lead;
  }

  async update(id: string, input: UpdateLeadInput): Promise<Lead> {
    await latency(120);
    return patchLead(id, input);
  }

  async addNote(id: string, body: string): Promise<Lead> {
    await latency(120);
    return appendNote(id, body);
  }

  async generateOutreach(id: string, request: OutreachRequest): Promise<OutreachMessage> {
    await latency(900);
    const lead = await this.get(id);
    return {
      id: `msg_${Date.now().toString(36)}`,
      leadId: id,
      ...request,
      subject:
        request.channel === "email"
          ? `${lead.name.split(" ")[0]} — quick question about your beauty team`
          : undefined,
      body: draftMessage(lead, request),
      createdAt: new Date().toISOString(),
    };
  }

  async facets(): Promise<{ countries: string[]; platforms: Platform[] }> {
    await latency(80);
    const leads = allLeads();
    return {
      countries: [
        ...new Set(leads.map((lead) => lead.location?.country).filter(Boolean) as string[]),
      ].sort(),
      platforms: [...new Set(leads.flatMap((lead) => lead.platforms.map((p) => p.platform)))],
    };
  }
}

/**
 * Placeholder copy generator. Phase 8 replaces this with an LLM call that gets
 * the same inputs: the lead's strongest evidence plus the chosen tone.
 */
function draftMessage(lead: Lead, request: OutreachRequest): string {
  const firstName = lead.name.split(" ")[0];
  const topSignals = lead.signals
    .filter((signal) => signal.detected)
    .sort((a, b) => b.confidence - a.confidence)
    .slice(0, 2);
  const hook = topSignals[0]?.evidence?.replace(/^["“]|["”]$/g, "") ?? lead.headline;
  const city = lead.location?.city ?? lead.location?.country ?? "your region";

  const openers: Record<OutreachRequest["tone"], string> = {
    warm: `Hi ${firstName}! I came across your profile and genuinely enjoyed your content.`,
    direct: `Hi ${firstName} — short and to the point.`,
    formal: `Dear ${firstName},`,
  };

  const closers: Record<OutreachRequest["tone"], string> = {
    warm: "Would you be open to a short call this week? No pressure either way.",
    direct: "Open to a 15-minute call this week?",
    formal: "I would be glad to arrange a call at your convenience.",
  };

  const scoreLine =
    lead.score >= HIGH_QUALITY_THRESHOLD
      ? `Your background in ${city} is exactly the profile our team is expanding with right now.`
      : `We are expanding our beauty team in ${city} and your experience looks relevant.`;

  return [
    openers[request.tone],
    `What caught my attention: ${hook}`,
    scoreLine,
    closers[request.tone],
    request.channel === "email" ? "\n— Sent from AI Recruiter (draft, mock data)" : "",
  ]
    .filter(Boolean)
    .join("\n\n");
}
