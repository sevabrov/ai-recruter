/**
 * Theme registry.
 *
 * Adding a theme is two steps and touches no component:
 *   1. add a palette block in src/app/globals.css keyed by [data-theme="<id>"]
 *   2. add an entry here
 */

export const THEMES = [
  {
    id: "daylight",
    name: "Daylight",
    hint: "Paper-cool light",
    scheme: "light",
    /** Swatch preview: [ground, surface, accent] */
    swatch: ["#f6f5f8", "#ffffff", "#a63d62"],
  },
  {
    id: "graphite",
    name: "Graphite",
    hint: "Violet-tinted dark",
    scheme: "dark",
    swatch: ["#0f0e13", "#1c1b24", "#d9648a"],
  },
] as const;

export type ThemeId = (typeof THEMES)[number]["id"];
export type ThemePreference = ThemeId | "system";

export const THEME_STORAGE_KEY = "air.theme";
export const DEFAULT_THEME: ThemePreference = "system";

export function isThemeId(value: unknown): value is ThemeId {
  return THEMES.some((theme) => theme.id === value);
}

export function isThemePreference(value: unknown): value is ThemePreference {
  return value === "system" || isThemeId(value);
}

export function themeMeta(id: ThemeId) {
  return THEMES.find((theme) => theme.id === id)!;
}
