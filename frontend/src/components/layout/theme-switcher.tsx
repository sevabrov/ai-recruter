"use client";

import { Check, Monitor, Moon, Sun } from "lucide-react";
import { useTranslations } from "next-intl";
import { useTheme } from "@/lib/theme-provider";
import { THEMES, type ThemePreference } from "@/lib/themes";
import { Button } from "@/components/ui/button";
import { Menu, MenuItem, MenuLabel, MenuSeparator } from "@/components/ui/overlay";

/**
 * Two palettes plus "follow system". Themes come from the registry, so a third
 * palette appears here automatically - its name and hint come from the message
 * catalogue under `theme.<id>`.
 */
export function ThemeSwitcher() {
  const t = useTranslations("theme");
  const { preference, resolved, setPreference } = useTheme();

  const labelFor = (value: ThemePreference) =>
    value === "system" ? t("followSystemLower") : t(`${value}.name`);

  return (
    <Menu
      hint={t("tooltip", { name: labelFor(preference) })}
      trigger={
        <Button variant="ghost" size="icon" aria-label={t("change")}>
          {resolved === "graphite" ? <Moon /> : <Sun />}
        </Button>
      }
    >
      <MenuLabel>{t("label")}</MenuLabel>
      {THEMES.map((theme) => (
        <MenuItem
          key={theme.id}
          onSelect={() => setPreference(theme.id)}
          icon={
            <span className="flex gap-0.5">
              {theme.swatch.map((color) => (
                <span
                  key={color}
                  className="size-2.5 rounded-[2px] border border-line"
                  style={{ background: color }}
                />
              ))}
            </span>
          }
        >
          <span className="flex flex-1 items-center justify-between gap-3">
            <span>
              {t(`${theme.id}.name`)}
              <span className="ml-2 text-xs text-fg-faint">{t(`${theme.id}.hint`)}</span>
            </span>
            {preference === theme.id ? <Check className="size-3.5 text-accent" /> : null}
          </span>
        </MenuItem>
      ))}
      <MenuSeparator />
      <MenuItem onSelect={() => setPreference("system")} icon={<Monitor />}>
        <span className="flex flex-1 items-center justify-between gap-3">
          {t("followSystem")}
          {preference === "system" ? <Check className="size-3.5 text-accent" /> : null}
        </span>
      </MenuItem>
    </Menu>
  );
}
