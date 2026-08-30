/**
 * Locale-aware replacements for `next/link` and `next/navigation`.
 *
 * Import `Link`, `useRouter` and `usePathname` from here, never from Next
 * directly: these keep the active locale prefix on every href, and
 * `usePathname` returns the path *without* it, so route matching in the
 * sidebar stays written the way it always was (`/leads`, `/search/new`).
 */

import { createNavigation } from "next-intl/navigation";
import { routing } from "./routing";

export const { Link, redirect, usePathname, useRouter, getPathname } =
  createNavigation(routing);
