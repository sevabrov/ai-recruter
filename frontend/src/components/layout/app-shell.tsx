"use client";

import { Menu as MenuIcon, Plus, X } from "lucide-react";
import { Dialog } from "radix-ui";
import { useTranslations } from "next-intl";
import { useState, type ReactNode } from "react";
import { Link, usePathname } from "@/i18n/navigation";
import { Button } from "@/components/ui/button";
import { Sidebar, SidebarContent } from "./sidebar";
import { LanguageSwitcher } from "./language-switcher";
import { ThemeSwitcher } from "./theme-switcher";

export function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const t = useTranslations("nav");
  // The drawer closes from SidebarContent's onNavigate, so no route effect.
  const [drawerOpen, setDrawerOpen] = useState(false);

  return (
    <div className="flex min-h-dvh">
      <Sidebar />

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-30 flex h-14 items-center gap-3 border-b border-line bg-bg/85 px-4 backdrop-blur-md lg:px-8">
          <Dialog.Root open={drawerOpen} onOpenChange={setDrawerOpen}>
            <Dialog.Trigger asChild>
              <Button variant="ghost" size="icon" className="lg:hidden" aria-label={t("openNavigation")}>
                <MenuIcon />
              </Button>
            </Dialog.Trigger>
            <Dialog.Portal>
              <Dialog.Overlay className="fixed inset-0 z-50 bg-black/45 lg:hidden" />
              <Dialog.Content className="fixed top-0 left-0 z-50 h-dvh w-64 border-r border-line bg-surface lg:hidden">
                <Dialog.Title className="sr-only">{t("navigation")}</Dialog.Title>
                <Dialog.Close
                  className="absolute top-3.5 right-3 rounded-ctl p-1 text-fg-faint hover:text-fg"
                  aria-label={t("closeNavigation")}
                >
                  <X className="size-4" />
                </Dialog.Close>
                <SidebarContent onNavigate={() => setDrawerOpen(false)} />
              </Dialog.Content>
            </Dialog.Portal>
          </Dialog.Root>

          <Breadcrumb pathname={pathname} />

          <div className="ml-auto flex items-center gap-1.5">
            <LanguageSwitcher />
            <ThemeSwitcher />
            <Button asChild variant="primary" size="sm" className="hidden sm:inline-flex">
              <Link href="/search/new">
                <Plus />
                {t("newSearch")}
              </Link>
            </Button>
          </div>
        </header>

        <main className="flex-1 px-4 py-6 lg:px-8 lg:py-8">
          <div className="mx-auto w-full max-w-6xl">{children}</div>
        </main>
      </div>
    </div>
  );
}

/** Segments this build has a name for; anything else is an id and gets shortened. */
const NAMED_CRUMBS = new Set([
  "search",
  "new",
  "searches",
  "leads",
  "settings",
  "progress",
  "results",
]);

function Breadcrumb({ pathname }: { pathname: string }) {
  const t = useTranslations("nav");
  const crumbs = useTranslations("crumbs");
  const segments = pathname.split("/").filter(Boolean);

  return (
    <nav aria-label={t("breadcrumb")} className="flex min-w-0 items-center gap-2 text-sm">
      <Link href="/" className="label text-fg-faint transition-colors hover:text-fg">
        {t("workspace")}
      </Link>
      {segments.map((segment, index) => {
        const label = NAMED_CRUMBS.has(segment) ? crumbs(segment) : shorten(segment);
        const href = `/${segments.slice(0, index + 1).join("/")}`;
        const isLast = index === segments.length - 1;
        return (
          <span key={href} className="flex min-w-0 items-center gap-2">
            <span className="text-fg-faint">/</span>
            {isLast ? (
              <span className="label truncate text-fg">{label}</span>
            ) : (
              <Link href={href} className="label truncate text-fg-faint transition-colors hover:text-fg">
                {label}
              </Link>
            )}
          </span>
        );
      })}
    </nav>
  );
}

/** Ids are long; show enough to identify without wrapping the bar. */
function shorten(segment: string) {
  if (segment.length <= 14) return segment;
  return `${segment.slice(0, 6)}…${segment.slice(-4)}`;
}
