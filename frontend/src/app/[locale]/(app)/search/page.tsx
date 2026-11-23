import { redirect } from "@/i18n/navigation";

/**
 * `/search` has no page of its own: it is the parent of `/search/new` and
 * `/search/:id`, and the breadcrumb links to it. The list of searches lives at
 * `/searches`, so send the breadcrumb there instead of to a 404.
 */
export default async function SearchIndexPage({
  params,
}: {
  params: Promise<{ locale: string }>;
}) {
  const { locale } = await params;
  redirect({ href: "/searches", locale });
}
