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
import { useTranslations } from "next-intl";
import { useParams } from "next/navigation";
import { Link } from "@/i18n/navigation";
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
import { LEAD_STATUSES } from "@/lib/domain";
import { useNumbers, useTimeAgo } from "@/lib/format";
import { cn } from "@/lib/utils";
import { useLead, useUpdateLead } from "@/services/hooks";
import type { LeadStatus } from "@/services/types";

export default function LeadDetailPage() {
  const t = useTranslations("leadDetail");
  const common = useTranslations("common");
  const statuses = useTranslations("domain.leadStatus");
  const platforms = useTranslations("domain.platform");
  const { number } = useNumbers();
  const timeAgo = useTimeAgo();

  const { id } = useParams<{ id: string }>();
  const { data: lead, isPending, isError } = useLead(id);
  const updateLead = useUpdateLead();
  const { toast } = useToast();

  if (isError) {
    return (
      <Card>
        <CardBody>
          <p className="text-sm text-fg-muted">{t("notFound")}</p>
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
      title: lead.saved ? t("toastUnsaved") : t("toastSaved"),
      description: lead.saved ? undefined : t("toastSavedBody"),
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
              ariaLabel={t("statusAria")}
              value={lead.status}
              onValueChange={(value) =>
                updateLead.mutate({ id: lead.id, input: { status: value as LeadStatus } })
              }
              options={LEAD_STATUSES.map((status) => ({
                value: status.id,
                label: statuses(status.id),
              }))}
            />
            <OutreachDialog lead={lead} />
            <Button variant={lead.saved ? "primary" : "secondary"} onClick={toggleSaved}>
              <Bookmark className={cn(lead.saved && "fill-current")} />
              {lead.saved ? t("saved") : t("save")}
            </Button>
            <Menu
              trigger={
                <Button variant="ghost" size="icon" aria-label={t("moreActions")}>
                  <MoreHorizontal />
                </Button>
              }
            >
              <MenuItem
                icon={<Archive />}
                onSelect={() => {
                  updateLead.mutate({ id: lead.id, input: { archived: !lead.archived } });
                  toast({
                    title: lead.archived ? t("toastRestored") : t("toastArchived"),
                    tone: "neutral",
                  });
                }}
              >
                {lead.archived ? t("restoreFromArchive") : t("archiveLead")}
              </MenuItem>
              <MenuItem
                icon={<SearchIcon />}
                onSelect={() => window.open(`https://www.google.com/search?q=${encodeURIComponent(lead.name)}`, "_blank")}
              >
                {t("verifyOnWeb")}
              </MenuItem>
            </Menu>
          </>
        }
      />

      <div className="grid gap-5 lg:grid-cols-[1.45fr_1fr]">
        <div className="flex flex-col gap-5">
          <Card>
            <CardHeader title={t("whyMatches")} hint={t("whyMatchesHint")} />
            <SignalEvidence signals={lead.signals} />
          </Card>

          <Card>
            <CardHeader title={t("aiSummary")} hint={t("aiSummaryHint")} />
            <CardBody>
              {/* Written by the model, in the language the profile was in. */}
              <p className="text-sm leading-relaxed text-fg-muted">{lead.summary}</p>
            </CardBody>
          </Card>

          <Card>
            <CardHeader
              title={t("sources")}
              hint={t("sourcesHint", { count: lead.sources.length })}
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
                        {platforms(source.platform)} ·{" "}
                        {t("discoveredAt", { when: timeAgo(source.discoveredAt) })}
                      </span>
                    </span>
                  </a>
                </li>
              ))}
            </ul>
          </Card>

          <Card>
            <CardHeader title={t("notes")} hint={t("notesHint")} />
            <NotesPanel leadId={lead.id} notes={lead.notes} />
          </Card>
        </div>

        <div className="flex flex-col gap-5">
          <Card>
            <CardBody className="flex flex-col items-center gap-3 py-6">
              <Eyebrow>{t("aiMatchScore")}</Eyebrow>
              <ScoreDial score={lead.score} />
              <ScoreTierBadge score={lead.score} />
            </CardBody>
            <div className="border-t border-line px-5 py-4">
              <Eyebrow className="mb-3">{t("howScoreBuilt")}</Eyebrow>
              <ScoreBreakdown breakdown={lead.scoreBreakdown} total={lead.score} />
            </div>
          </Card>

          <Card>
            <CardHeader title={t("overview")} />
            <CardBody className="grid grid-cols-2 gap-x-4 gap-y-4">
              <Detail label={t("location")}>
                {[lead.location?.city, lead.location?.region, lead.location?.country]
                  .filter(Boolean)
                  .join(", ") || common("dash")}
              </Detail>
              <Detail label={t("languages")}>{lead.languages.join(", ") || common("dash")}</Detail>
              <Detail label={t("company")}>{lead.company ?? common("dash")}</Detail>
              <Detail label={t("discovered")}>{timeAgo(lead.createdAt)}</Detail>
              <Detail label={t("fromSearch")} className="col-span-2">
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
            <CardHeader title={t("profilesContacts")} />
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
                        {number(platform.followers)}
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
                <p className="text-xs text-fg-faint">{t("noContacts")}</p>
              </CardBody>
            ) : null}
          </Card>

          {lead.archived ? (
            <Badge tone="warn" className="self-start">
              {t("archived")}
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
