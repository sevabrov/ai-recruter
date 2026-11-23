"use client";

import {
  History,
  LayoutDashboard,
  Plus,
  Settings,
  Users,
  type LucideIcon,
} from "lucide-react";
import { useTranslations } from "next-intl";
import { Link, usePathname } from "@/i18n/navigation";
import { API_BASE_URL } from "@/services/api/http";
import { useBackendHealth } from "@/services/hooks";
import { cn } from "@/lib/utils";
import { Dot } from "@/components/ui/badge";

type NavItem = {
  href: string;
  /** Key under the `nav` namespace. */
  label: string;
  icon: LucideIcon;
  /** Marks the section active for any nested route. */
  match?: (pathname: string) => boolean;
};

const NAV: NavItem[] = [
  { href: "/", label: "dashboard", icon: LayoutDashboard, match: (p) => p === "/" },
  {
    href: "/search/new",
    label: "newSearch",
    icon: Plus,
    match: (p) => p.startsWith("/search/new"),
  },
  { href: "/leads", label: "leads", icon: Users, match: (p) => p.startsWith("/leads") },
  {
    href: "/searches",
    label: "searchHistory",
    icon: History,
    match: (p) => p.startsWith("/searches") || (p.startsWith("/search/") && !p.startsWith("/search/new")),
  },
];

const SECONDARY: NavItem[] = [
  { href: "/settings", label: "settings", icon: Settings, match: (p) => p.startsWith("/settings") },
];

export function SidebarContent({ onNavigate }: { onNavigate?: () => void }) {
  // Locale-aware: the prefix is stripped, so the matchers above stay written
  // against plain paths.
  const pathname = usePathname();
  const t = useTranslations("nav");

  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center gap-2.5 px-4 py-4">
        <Mark />
        <div className="min-w-0">
          <p className="font-display text-[15px] leading-tight font-semibold tracking-tight">
            {t("brand")}
          </p>
          <p className="label text-fg-faint">{t("tagline")}</p>
        </div>
      </div>

      <nav className="flex flex-1 flex-col gap-0.5 px-2 py-2">
        {NAV.map((item) => (
          <NavLink key={item.href} item={item} pathname={pathname} onNavigate={onNavigate} />
        ))}

        <div className="hairline mx-2 my-3" />

        {SECONDARY.map((item) => (
          <NavLink key={item.href} item={item} pathname={pathname} onNavigate={onNavigate} />
        ))}
      </nav>

      <DataSourceFooter />
    </div>
  );
}

/**
 * A live connection indicator - an unreachable backend must not look like an
 * empty workspace.
 */
function DataSourceFooter() {
  const t = useTranslations("backend");
  const { data, isError, isPending } = useBackendHealth();

  const degraded = data?.database === false;

  const tone = isError ? "bad" : isPending ? "neutral" : degraded ? "warn" : "good";
  const title = isError
    ? t("unreachableTitle")
    : isPending
      ? t("connectingTitle")
      : degraded
        ? t("databaseDownTitle")
        : t("liveTitle", { version: data?.version ?? "" });
  const detail = isError
    ? t("unreachableDetail", { url: API_BASE_URL })
    : degraded
      ? t("databaseDownDetail")
      : data?.pipeline === "fixture"
        ? t("fixtureDetail")
        : data?.stages?.extraction === "scrapegraph"
          ? t("readingDetail", { provider: data.stages.search })
          : data?.stages?.search && data.stages.search !== "fixture"
            ? t("searchOnlyDetail", { provider: data.stages.search })
            : t("connectedDetail");

  return (
    <div className="border-t border-line px-4 py-3">
      <div className="flex items-center gap-2">
        <Dot tone={tone} pulse={isPending} />
        <p className="label truncate text-fg-faint">{title}</p>
      </div>
      <p className="mt-1.5 text-xs leading-relaxed text-fg-faint">{detail}</p>
    </div>
  );
}

function NavLink({
  item,
  pathname,
  onNavigate,
}: {
  item: NavItem;
  pathname: string;
  onNavigate?: () => void;
}) {
  const t = useTranslations("nav");
  const active = item.match ? item.match(pathname) : pathname.startsWith(item.href);
  const Icon = item.icon;

  return (
    <Link
      href={item.href}
      onClick={onNavigate}
      className={cn(
        "group relative flex items-center gap-2.5 rounded-ctl px-2.5 py-2 text-sm transition-colors",
        active ? "bg-accent-soft text-accent" : "text-fg-muted hover:bg-surface-2 hover:text-fg",
      )}
    >
      <span
        className={cn(
          "absolute top-1/2 left-0 h-4 w-0.5 -translate-y-1/2 rounded-pill bg-accent transition-opacity",
          active ? "opacity-100" : "opacity-0",
        )}
      />
      <Icon className="size-4 shrink-0" />
      <span className="truncate font-medium">{t(item.label)}</span>
    </Link>
  );
}

/** Wordmark: two overlapping apertures - search over a person. */
function Mark() {
  return (
    <span className="grid size-8 shrink-0 place-items-center rounded-[9px] border border-accent-line bg-accent-soft">
      <svg viewBox="0 0 24 24" className="size-4.5" aria-hidden>
        <circle cx="10" cy="10" r="6" className="stroke-accent" strokeWidth="2" fill="none" />
        <path d="M14.5 14.5 L20 20" className="stroke-accent" strokeWidth="2" strokeLinecap="round" />
        <circle cx="10" cy="8.4" r="2" className="fill-accent" />
        <path
          d="M6.4 13.4c.6-2 2-3 3.6-3s3 1 3.6 3"
          className="stroke-accent"
          strokeWidth="1.6"
          fill="none"
          strokeLinecap="round"
        />
      </svg>
    </span>
  );
}

export function Sidebar() {
  return (
    <aside className="sticky top-0 hidden h-dvh w-60 shrink-0 border-r border-line bg-surface lg:block">
      <SidebarContent />
    </aside>
  );
}

export { Mark as BrandMark };
