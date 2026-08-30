import type { ReactNode } from "react";
import { setRequestLocale } from "next-intl/server";
import { AppShell } from "@/components/layout/app-shell";

export default async function AppLayout({
  children,
  params,
}: {
  children: ReactNode;
  params: Promise<{ locale: string }>;
}) {
  const { locale } = await params;
  setRequestLocale(locale);

  return <AppShell>{children}</AppShell>;
}
