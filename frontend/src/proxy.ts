/**
 * Locale negotiation.
 *
 * `middleware` was renamed to `proxy` in Next 16; this is the same convention
 * under its new name. Every request without a locale prefix is redirected to
 * one: the cookie set by an earlier visit wins, then `Accept-Language`, then
 * Ukrainian.
 */

import createMiddleware from "next-intl/middleware";
import { routing } from "./i18n/routing";

export default createMiddleware(routing);

export const config = {
  // Everything except Next internals, the API proxy and files with an extension.
  matcher: "/((?!api|_next|_vercel|.*\\..*).*)",
};
