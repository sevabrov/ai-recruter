"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useSyncExternalStore,
  type ReactNode,
} from "react";
import {
  DEFAULT_THEME,
  isThemePreference,
  THEME_STORAGE_KEY,
  type ThemeId,
  type ThemePreference,
} from "./themes";

/* ---------------------------------------------------------------------------
   Two tiny external stores — the stored preference and the OS setting. Reading
   them through useSyncExternalStore keeps the server render deterministic and
   avoids setState-in-effect entirely; the <html data-theme> stamp is written
   from the setter, which is where a DOM side effect belongs.
   ------------------------------------------------------------------------- */

const preferenceListeners = new Set<() => void>();
let cachedPreference: ThemePreference | null = null;

function readStoredPreference(): ThemePreference {
  if (cachedPreference !== null) return cachedPreference;
  let stored: string | null = null;
  try {
    stored = window.localStorage.getItem(THEME_STORAGE_KEY);
  } catch {
    stored = null;
  }
  cachedPreference = isThemePreference(stored) ? stored : DEFAULT_THEME;
  return cachedPreference;
}

function stamp(preference: ThemePreference) {
  const root = document.documentElement;
  if (preference === "system") delete root.dataset.theme;
  else root.dataset.theme = preference;
}

function writePreference(preference: ThemePreference) {
  cachedPreference = preference;
  try {
    window.localStorage.setItem(THEME_STORAGE_KEY, preference);
  } catch {
    /* storage unavailable — the in-memory value still drives this session */
  }
  stamp(preference);
  preferenceListeners.forEach((listener) => listener());
}

function subscribePreference(listener: () => void) {
  preferenceListeners.add(listener);
  return () => preferenceListeners.delete(listener);
}

const DARK_QUERY = "(prefers-color-scheme: dark)";

function subscribeSystem(listener: () => void) {
  const media = window.matchMedia(DARK_QUERY);
  media.addEventListener("change", listener);
  return () => media.removeEventListener("change", listener);
}

function systemSnapshot(): ThemeId {
  return window.matchMedia(DARK_QUERY).matches ? "graphite" : "daylight";
}

/** Inlined in <head> so the first paint already carries the stored palette. */
export const themeBootstrapScript = `
(function(){
  try {
    var stored = localStorage.getItem(${JSON.stringify(THEME_STORAGE_KEY)});
    if (stored === "daylight" || stored === "graphite") {
      document.documentElement.dataset.theme = stored;
    }
  } catch (e) {}
})();
`;

type ThemeContextValue = {
  /** What the user picked — may be "system". */
  preference: ThemePreference;
  /** What is actually painted right now. */
  resolved: ThemeId;
  setPreference: (preference: ThemePreference) => void;
  /** Flips between the two palettes, leaving "system" behind. */
  toggle: () => void;
};

const ThemeContext = createContext<ThemeContextValue | null>(null);

export function ThemeProvider({ children }: { children: ReactNode }) {
  const preference = useSyncExternalStore(
    subscribePreference,
    readStoredPreference,
    () => DEFAULT_THEME,
  );

  const systemTheme = useSyncExternalStore(
    subscribeSystem,
    systemSnapshot,
    () => "daylight" as ThemeId,
  );

  // Reconcile the DOM with storage once on mount: the bootstrap script covers
  // the common case, this covers a stamp written by another tab.
  useEffect(() => {
    stamp(readStoredPreference());
  }, []);

  const resolved: ThemeId = preference === "system" ? systemTheme : preference;

  const setPreference = useCallback((next: ThemePreference) => writePreference(next), []);

  const toggle = useCallback(() => {
    writePreference(resolved === "graphite" ? "daylight" : "graphite");
  }, [resolved]);

  const value = useMemo(
    () => ({ preference, resolved, setPreference, toggle }),
    [preference, resolved, setPreference, toggle],
  );

  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}

export function useTheme() {
  const context = useContext(ThemeContext);
  if (!context) throw new Error("useTheme must be used inside <ThemeProvider>");
  return context;
}
