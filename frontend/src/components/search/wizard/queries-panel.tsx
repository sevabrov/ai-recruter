"use client";

import { Plus, Terminal, X } from "lucide-react";
import { useTranslations } from "next-intl";
import { useState } from "react";
import { SITE_BY_SOURCE, SOURCE_KINDS, WEB_SOURCES } from "@/lib/domain";
import type { SourceKind } from "@/services/types";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/field";
import { Eyebrow } from "@/components/ui/misc";

/**
 * The queries, with room to write your own.
 *
 * The generated ones are templates: they know the criteria, not the market. The
 * people a client is looking for label *themselves*, with a brand name nobody
 * outside that market would guess — so the panel that shows what will run is also
 * where a line of it can be written by hand. Hand-written queries run first and
 * are never dropped by the query cap.
 *
 * Where to look is a set of buttons rather than something to type. Asked to write
 * the query itself, the client wrote `джерелія` — a perfectly good question, put
 * to the whole indexed web, which answered with the brand's own site, four shops,
 * a catalogue and a hotel called Jerelia. Eighteen of those twenty results were
 * then thrown away for being off-source. Nobody should have to know that
 * `site:instagram.com` is what turns that into a question about people.
 */
export function QueriesPanel({
  own,
  sources,
  generated,
  loading,
  onChange,
}: {
  own: string[];
  sources: SourceKind[];
  generated: { query: string; language?: string | null }[];
  loading: boolean;
  onChange: (queries: string[]) => void;
}) {
  const t = useTranslations("wizard.review");
  const common = useTranslations("common");
  const platforms = useTranslations("domain.platform");
  const sourceNames = useTranslations("domain.source");

  const [draft, setDraft] = useState("");
  const [picked, setPicked] = useState<string[] | null>(null);

  // Only the sources this search actually looks at: a query aimed anywhere else
  // would be answered and then discarded.
  const places: { id: string; label: string; operator: string | null }[] = [
    ...SOURCE_KINDS.filter(
      (kind) => sources.includes(kind.id) && SITE_BY_SOURCE[kind.id],
    ).map((kind) => ({
      id: kind.id as string,
      label: kind.platform ? platforms(kind.platform) : sourceNames(`${kind.id}.label`),
      operator: SITE_BY_SOURCE[kind.id]!,
    })),
    ...(sources.some((source) => WEB_SOURCES.includes(source))
      ? [{ id: "web", label: t("wholeWeb"), operator: null }]
      : []),
  ];

  // Null means "none of them touched yet", which reads as all of them.
  const chosen = places.filter(
    (place) => picked === null || picked.includes(place.id),
  );
  const toggle = (id: string) => {
    const current = chosen.map((place) => place.id);
    setPicked(
      current.includes(id)
        ? current.filter((entry) => entry !== id)
        : [...current, id],
    );
  };

  // The backend returns the client's own queries first, so showing both lists
  // would show them twice.
  const templates = generated.filter((entry) => !own.includes(entry.query));

  const cleaned = draft.trim().replace(/\s+/g, " ");
  const written = /\bsite:/i.test(cleaned);
  const composed = !cleaned
    ? []
    : written
      ? [cleaned]
      : chosen.map((place) =>
          place.operator ? `${place.operator} ${cleaned}` : cleaned,
        );
  const fresh = composed.filter((query) => !own.includes(query));

  const add = () => {
    if (!fresh.length) return;
    onChange([...own, ...fresh]);
    setDraft("");
  };

  return (
    <section className="rounded-card border border-line bg-surface-2">
      <header className="flex items-center gap-2 border-b border-line px-4 py-2.5">
        <Terminal className="size-3.5 text-fg-faint" />
        <Eyebrow>{t("queriesTitle")}</Eyebrow>
        <span className="num ml-auto text-2xs text-fg-faint">
          {loading ? "…" : t("queriesCount", { count: own.length + templates.length })}
        </span>
      </header>

      <div className="flex flex-col gap-2.5 border-b border-line px-4 py-3">
        {places.length ? (
          <div className="flex flex-wrap items-center gap-1.5">
            <Eyebrow className="mr-1">{t("searchIn")}</Eyebrow>
            {places.map((place) => {
              const on = chosen.some((entry) => entry.id === place.id);
              return (
                <button
                  key={place.id}
                  type="button"
                  aria-pressed={on}
                  onClick={() => toggle(place.id)}
                  className={`rounded-full border px-2.5 py-1 text-xs transition-colors ${
                    on
                      ? "border-accent bg-accent-soft text-accent"
                      : "border-line text-fg-faint hover:text-fg"
                  }`}
                >
                  {place.label}
                </button>
              );
            })}
          </div>
        ) : null}

        <div className="flex gap-2">
          <Input
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter") {
                event.preventDefault();
                add();
              }
            }}
            placeholder={t("queryPlaceholder")}
            aria-label={t("queryAria")}
            className="text-xs"
          />
          <Button variant="secondary" onClick={add} disabled={!fresh.length}>
            <Plus />
            {common("add")}
          </Button>
        </div>

        {/* What the buttons and the words add up to, before it is added. */}
        {composed.length ? (
          <ul className="flex flex-col gap-1">
            {composed.map((query) => (
              <li
                key={query}
                className={`font-mono text-2xs break-all ${
                  own.includes(query) ? "text-fg-faint line-through" : "text-fg-muted"
                }`}
              >
                {query}
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-xs leading-relaxed text-fg-muted">
            {chosen.length ? t("queryHint") : t("queryPickPlace")}
          </p>
        )}
        {written ? (
          <p className="text-xs text-fg-muted">
            {t.rich("queryOwnSite", {
              code: (chunks) => <code className="font-mono">{chunks}</code>,
            })}
          </p>
        ) : null}
      </div>

      <ul className="divide-y divide-line/60">
        {own.map((query) => (
          <li key={query} className="flex items-start gap-2 px-4 py-2 text-xs">
            <span className="min-w-0 flex-1 font-mono break-all">{query}</span>
            <Badge tone="accent">{t("queryYours")}</Badge>
            <button
              type="button"
              aria-label={t("queryRemove", { query })}
              onClick={() => onChange(own.filter((entry) => entry !== query))}
              className="text-fg-faint transition-colors hover:text-bad"
            >
              <X className="size-3.5" />
            </button>
          </li>
        ))}
        {templates.map(({ query, language }) => (
          <li
            key={`${language ?? "any"}:${query}`}
            className="flex items-start gap-2 px-4 py-2 font-mono text-xs break-all text-fg-muted"
          >
            <span className="min-w-0 flex-1">{query}</span>
            {language ? <Badge mono>{language}</Badge> : null}
          </li>
        ))}
        {loading ? (
          <li className="px-4 py-2 text-xs text-fg-faint">{t("queryLoading")}</li>
        ) : null}
      </ul>
    </section>
  );
}
