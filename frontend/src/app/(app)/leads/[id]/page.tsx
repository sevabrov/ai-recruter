"use client";

import {
  Archive,
  ArrowLeft,
  Bookmark,
  ExternalLink,
  Globe,
  Mail,
  MoreHorizontal,
  Search as SearchIcon,
} from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { NotesPanel } from "@/components/leads/notes-panel";
import { OutreachDialog } from "@/components/leads/outreach-dialog";
import { ScoreBreakdown } from "@/components/leads/score-breakdown";
import { SignalEvidence } from "@/components/leads/signal-evidence";
import { PageHeader } from "@/components/layout/page-header";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { SelectField } from "@/components/ui/controls";
import { Menu, MenuItem } from "@/components/ui/overlay";
import { Eyebrow, PlatformIcon, Skeleton } from "@/components/ui/misc";
import { ScoreDial, ScoreTierBadge } from "@/components/ui/score";
import { useToast } from "@/components/ui/toast";
import { LEAD_STATUSES, PLATFORM_LABELS } from "@/lib/domain";
import { cn, formatNumber, formatRelativeTime } from "@/lib/utils";
import { useLead, useUpdateLead } from "@/services/hooks";
import type { LeadStatus } from "@/services/types";

export default function LeadDetailPage() {
  const { id } = useParams<{ id: string }>();
  const { data: lead, isPending, isError } = useLead(id);
  const updateLead = useUpdateLead();
  const { toast } = useToast();

  if (isError) {
    return (
      <Card>
        <CardBody>
          <p className="text-sm text-fg-muted">This lead could not be found.</p>
        </CardBody>
      </Card>
    );
  }

  if (isPending || !lead) {
    return (
      <div className="flex flex-col gap-5">
        <Skeleton className="h-10 w-64" />
        <div className="grid gap-5 lg:grid-cols-[1.45fr_1fr]">
          <Skeleton className="h-96 rounded-card" />
          <Skeleton className="h-72 rounded-card" />
        </div>
      </div>
    );
  }

  const toggleSaved = () => {
    updateLead.mutate({ id: lead.id, input: { saved: !lead.saved } });
    toast({
      title: lead.saved ? "Removed from saved" : "Saved",
      description: lead.saved ? undefined : "Find it under Leads → Saved.",
      tone: lead.saved ? "neutral" : "accent",
    });
  };

  return (
    <>
      <Button asChild variant="ghost" size="sm" className="mb-3 -ml-2">
        <Link href={`/search/${lead.searchId}/results`}>
          <ArrowLeft />
          {lead.searchName}
        </Link>
      </Button>

      <PageHeader
        title={lead.name}
        description={
          <span className="flex flex-wrap items-center gap-x-3 gap-y-1">
            <span>{lead.headline}</span>
            {lead.company ? (
              <>
                <span className="text-fg-faint">·</span>
                <span>{lead.company}</span>
              </>
            ) : null}
          </span>
        }
        actions={
          <>
            <SelectField
              ariaLabel="Lead status"
              value={lead.status}
              onValueChange={(value) =>
                updateLead.mutate({ id: lead.id, input: { status: value as LeadStatus } })
              }
              options={LEAD_STATUSES.map((status) => ({ value: status.id, label: status.label }))}
            />
            <OutreachDialog lead={lead} />
            <Button variant={lead.saved ? "primary" : "secondary"} onClick={toggleSaved}>
              <Bookmark className={cn(lead.saved && "fill-current")} />
              {lead.saved ? "Saved" : "Save"}
            </Button>
            <Menu
              trigger={
                <Button variant="ghost" size="icon" aria-label="More actions">
                  <MoreHorizontal />
                </Button>
              }
            >
              <MenuItem
                icon={<Archive />}
                onSelect={() => {
                  updateLead.mutate({ id: lead.id, input: { archived: !lead.archived } });
                  toast({
                    title: lead.archived ? "Restored" : "Archived",
                    tone: "neutral",
                  });
                }}
              >
                {lead.archived ? "Restore from archive" : "Archive lead"}
              </MenuItem>
              <MenuItem
                icon={<SearchIcon />}
                onSelect={() => window.open(`https://www.google.com/search?q=${encodeURIComponent(lead.name)}`, "_blank")}
              >
                Verify on the web
              </MenuItem>
            </Menu>
          </>
        }
      />

      <div className="grid gap-5 lg:grid-cols-[1.45fr_1fr]">
        <div className="flex flex-col gap-5">
          <Card>
            <CardHeader
              title="Why this candidate matches"
              hint="Each signal keeps the quote and page it came from"
            />
            <SignalEvidence signals={lead.signals} />
          </Card>

          <Card>
            <CardHeader title="AI summary" hint="Generated from the extracted profile" />
            <CardBody>
              <p className="text-sm leading-relaxed text-fg-muted">{lead.summary}</p>
            </CardBody>
          </Card>

          <Card>
            <CardHeader
              title="Sources"
              hint={`${lead.sources.length} pages kept for re-analysis`}
            />
            <ul className="divide-y divide-line">
              {lead.sources.map((source) => (
                <li key={source.id}>
                  <a
                    href={source.url}
                    target="_blank"
                    rel="noreferrer noopener"
                    className="group flex items-start gap-3 px-5 py-3.5 transition-colors hover:bg-surface-2"
                  >
                    <span className="mt-0.5 grid size-7 shrink-0 place-items-center rounded-full border border-line bg-surface-2 text-fg-muted">
                      <PlatformIcon platform={source.platform} />
                    </span>
                    <span className="min-w-0 flex-1">
                      <span className="flex items-center gap-1.5">
                        <span className="truncate text-sm font-medium group-hover:text-accent">
                          {source.title}
                        </span>
                        <ExternalLink className="size-3 shrink-0 text-fg-faint" />
                      </span>
                      <span className="mt-0.5 block truncate text-xs text-fg-muted">
                        {source.snippet}
                      </span>
                      <span className="label mt-1 block text-fg-faint">
                        {PLATFORM_LABELS[source.platform]} · discovered{" "}
                        {formatRelativeTime(source.discoveredAt)}
                      </span>
                    </span>
                  </a>
                </li>
              ))}
            </ul>
          </Card>

          <Card>
            <CardHeader title="Notes" hint="Private to your workspace" />
            <NotesPanel leadId={lead.id} notes={lead.notes} />
          </Card>
        </div>

        <div className="flex flex-col gap-5">
          <Card>
            <CardBody className="flex flex-col items-center gap-3 py-6">
              <Eyebrow>AI match score</Eyebrow>
              <ScoreDial score={lead.score} />
              <ScoreTierBadge score={lead.score} />
            </CardBody>
            <div className="border-t border-line px-5 py-4">
              <Eyebrow className="mb-3">How the score was built</Eyebrow>
              <ScoreBreakdown breakdown={lead.scoreBreakdown} total={lead.score} />
            </div>
          </Card>

          <Card>
            <CardHeader title="Overview" />
            <CardBody className="grid grid-cols-2 gap-x-4 gap-y-4">
              <Detail label="Location">
                {[lead.location?.city, lead.location?.region, lead.location?.country]
                  .filter(Boolean)
                  .join(", ") || "—"}
              </Detail>
              <Detail label="Languages">{lead.languages.join(", ") || "—"}</Detail>
              <Detail label="Company">{lead.company ?? "—"}</Detail>
              <Detail label="Discovered">{formatRelativeTime(lead.createdAt)}</Detail>
              <Detail label="From search" className="col-span-2">
                <Link
                  href={`/search/${lead.searchId}/results`}
                  className="text-accent hover:underline"
                >
                  {lead.searchName}
                </Link>
              </Detail>
            </CardBody>
          </Card>

          <Card>
            <CardHeader title="Profiles & contacts" />
            <ul className="divide-y divide-line">
              {lead.platforms.map((platform) => (
                <li key={platform.url}>
                  <a
                    href={platform.url}
                    target="_blank"
                    rel="noreferrer noopener"
                    className="flex items-center gap-3 px-5 py-2.5 text-sm transition-colors hover:bg-surface-2"
                  >
                    <PlatformIcon platform={platform.platform} className="text-fg-faint" />
                    <span className="min-w-0 flex-1 truncate">
                      {platform.handle ?? platform.url}
                    </span>
                    {platform.followers ? (
                      <span className="num text-xs text-fg-faint">
                        {formatNumber(platform.followers)}
                      </span>
                    ) : null}
                    <ExternalLink className="size-3 text-fg-faint" />
                  </a>
                </li>
              ))}

              {lead.contacts.email ? (
                <li>
                  <a
                    href={`mailto:${lead.contacts.email}`}
                    className="flex items-center gap-3 px-5 py-2.5 text-sm transition-colors hover:bg-surface-2"
                  >
                    <Mail className="size-3.5 text-fg-faint" />
                    <span className="min-w-0 flex-1 truncate">{lead.contacts.email}</span>
                  </a>
                </li>
              ) : null}

              {lead.contacts.website ? (
                <li>
                  <a
                    href={lead.contacts.website}
                    target="_blank"
                    rel="noreferrer noopener"
                    className="flex items-center gap-3 px-5 py-2.5 text-sm transition-colors hover:bg-surface-2"
                  >
                    <Globe className="size-3.5 text-fg-faint" />
                    <span className="min-w-0 flex-1 truncate">{lead.contacts.website}</span>
                    <ExternalLink className="size-3 text-fg-faint" />
                  </a>
                </li>
              ) : null}
            </ul>
            {!lead.contacts.email && !lead.contacts.website ? (
              <CardBody className="pt-0">
                <p className="text-xs text-fg-faint">
                  No public contact details found. Outreach would go through a platform message.
                </p>
              </CardBody>
            ) : null}
          </Card>

          {lead.archived ? (
            <Badge tone="warn" className="self-start">
              Archived
            </Badge>
          ) : null}
        </div>
      </div>
    </>
  );
}

function Detail({
  label,
  children,
  className,
}: {
  label: string;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <div className={className}>
      <Eyebrow className="mb-1">{label}</Eyebrow>
      <p className="text-sm">{children}</p>
    </div>
  );
}
