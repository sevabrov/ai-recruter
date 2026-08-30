"use client";

import { Check, Languages } from "lucide-react";
import { useLocale, useTranslations } from "next-intl";
import { useTransition } from "react";
import { usePathname, useRouter } from "@/i18n/navigation";
import { LOCALE_META, routing, type AppLocale } from "@/i18n/routing";
import { Button } from "@/components/ui/button";
import { Menu, MenuItem, MenuLabel } from "@/components/ui/overlay";

/**
 * Switching language re-renders the current route under the new prefix, so the
 * user stays on the page they were reading. The choice is written to the
 * locale cookie by the proxy, which is what makes a later visit to `/` open in
 * the same language.
 */
export function LanguageSwitcher() {
  const t = useTranslations("language");
  const active = useLocale() as AppLocale;
  const router = useRouter();
  // Already stripped of the locale prefix and carrying real segment values, so
  // it can be handed straight back with a different prefix.
  const pathname = usePathname();
  const [pending, startTransition] = useTransition();

  const select = (locale: AppLocale) => {
    if (locale === active) return;
    startTransition(() => router.replace(pathname, { locale }));
  };

  return (
    <Menu
      hint={t("label")}
      trigger={
        <Button
          variant="ghost"
          size="icon"
          aria-label={t("change")}
          disabled={pending}
          className="relative"
        >
          <Languages />
          <span className="label absolute -bottom-0.5 right-0.5 text-[9px] leading-none text-fg-faint">
            {LOCALE_META[active].short}
          </span>
        </Button>
      }
    >
      <MenuLabel>{t("label")}</MenuLabel>
      {routing.locales.map((locale) => (
        <MenuItem
          key={locale}
          onSelect={() => select(locale)}
          icon={<span className="label text-[10px]">{LOCALE_META[locale].short}</span>}
        >
          <span className="flex flex-1 items-center justify-between gap-3">
            {LOCALE_META[locale].name}
            {locale === active ? <Check className="size-3.5 text-accent" /> : null}
          </span>
        </MenuItem>
      ))}
    </Menu>
  );
}
