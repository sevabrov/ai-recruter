"use client";

import { Check, Monitor, Moon, Sun } from "lucide-react";
import { useTheme } from "@/lib/theme-provider";
import { THEMES, type ThemePreference } from "@/lib/themes";
import { Button } from "@/components/ui/button";
import { Menu, MenuItem, MenuLabel, MenuSeparator } from "@/components/ui/overlay";
import { Hint } from "@/components/ui/controls";

/**
 * Two palettes plus "follow system". Themes come from the registry, so a third
 * palette appears here automatically.
 */
export function ThemeSwitcher() {
  const { preference, resolved, setPreference } = useTheme();

  return (
    <Menu
      trigger={
        <Hint label={`Theme: ${labelFor(preference)}`}>
          <Button variant="ghost" size="icon" aria-label="Change theme">
            {resolved === "graphite" ? <Moon /> : <Sun />}
          </Button>
        </Hint>
      }
    >
      <MenuLabel>Theme</MenuLabel>
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
              {theme.name}
              <span className="ml-2 text-xs text-fg-faint">{theme.hint}</span>
            </span>
            {preference === theme.id ? <Check className="size-3.5 text-accent" /> : null}
          </span>
        </MenuItem>
      ))}
      <MenuSeparator />
      <MenuItem onSelect={() => setPreference("system")} icon={<Monitor />}>
        <span className="flex flex-1 items-center justify-between gap-3">
          Follow system
          {preference === "system" ? <Check className="size-3.5 text-accent" /> : null}
        </span>
      </MenuItem>
    </Menu>
  );
}

function labelFor(preference: ThemePreference) {
  if (preference === "system") return "follow system";
  return THEMES.find((theme) => theme.id === preference)?.name ?? preference;
}
