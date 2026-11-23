"use client";

import { Check, ChevronDown, Search, X } from "lucide-react";
import { Popover } from "radix-ui";
import { useTranslations } from "next-intl";
import { useEffect, useId, useMemo, useRef, useState, type KeyboardEvent } from "react";
import { cn } from "@/lib/utils";

/** Space the open list wants under the field, in px: its full height and a margin. */
const ROOM_BELOW = 320;

export type ComboOption = {
  value: string;
  label: string;
  /** Extra text the search also matches — the stored token, say, so "Spain" finds "Іспанія". */
  keywords?: string;
};

/** Case- and accent-insensitive, so "cesko" finds "Česko". */
const fold = (text: string) =>
  text
    .normalize("NFD")
    .replace(/\p{Diacritic}/gu, "")
    .toLowerCase();

/**
 * Pick any number of entries from a closed list by typing.
 *
 * What is chosen sits above the field, and the list opens below it: that way the
 * open list never covers the choices, and the client sees each one land as they
 * pick. (Near the bottom of the screen the page scrolls to make room below.) The list
 * stays open between picks — choosing three languages is three clicks, not six.
 *
 * `pinned` entries ("Anywhere", "Any European country") come first, apart from
 * the rest, and are never filtered out of sight by a sort. What each pick means
 * is the caller's business: `onToggle` gets the value, and the caller decides
 * whether it excludes others.
 */
export function MultiCombobox({
  options,
  pinned = [],
  selected,
  onToggle,
  placeholder,
  ariaLabel,
}: {
  options: ComboOption[];
  pinned?: ComboOption[];
  /** Values currently chosen, in the order they are shown above the field. */
  selected: string[];
  onToggle: (value: string) => void;
  placeholder: string;
  ariaLabel: string;
}) {
  const t = useTranslations("common");
  const listId = useId();
  const inputRef = useRef<HTMLInputElement>(null);
  const anchorRef = useRef<HTMLDivElement>(null);
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [active, setActive] = useState(0);

  // The choices sit above the field, so a list that flips up would cover them.
  // Make room below instead; flipping is left for the very end of the page.
  useEffect(() => {
    const anchor = anchorRef.current;
    if (!open || !anchor) return;
    const room = window.innerHeight - anchor.getBoundingClientRect().bottom;
    if (room < ROOM_BELOW) window.scrollBy({ top: ROOM_BELOW - room, behavior: "smooth" });
  }, [open]);

  const all = useMemo(() => [...pinned, ...options], [pinned, options]);
  const chosen = new Set(selected);

  const matches = (option: ComboOption) => {
    const needle = fold(query.trim());
    return !needle || fold(`${option.label} ${option.keywords ?? ""}`).includes(needle);
  };
  const shownPinned = pinned.filter(matches);
  const shownOptions = options.filter(matches);
  const shown = [...shownPinned, ...shownOptions];
  const current = Math.min(active, Math.max(shown.length - 1, 0));

  // A value from an older search that is not in the list is still shown, so it
  // can be seen and removed rather than silently kept.
  const labelOf = (value: string) => all.find((option) => option.value === value)?.label ?? value;

  const pick = (value: string) => {
    onToggle(value);
    setQuery("");
    setActive(0);
    inputRef.current?.focus();
  };

  const onKeyDown = (event: KeyboardEvent<HTMLInputElement>) => {
    if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      event.preventDefault();
      if (!open) return setOpen(true);
      const step = event.key === "ArrowDown" ? 1 : -1;
      setActive((current + step + shown.length) % Math.max(shown.length, 1));
    } else if (event.key === "Enter") {
      event.preventDefault();
      if (open && shown[current]) pick(shown[current].value);
      else setOpen(true);
    } else if (event.key === "Escape") {
      if (open) {
        event.preventDefault();
        setOpen(false);
      }
    } else if (event.key === "Backspace" && !query && selected.length) {
      onToggle(selected[selected.length - 1]);
    }
  };

  const optionId = (index: number) => `${listId}-${index}`;

  const renderOption = (option: ComboOption, index: number) => {
    const on = chosen.has(option.value);
    return (
      <li
        key={option.value}
        id={optionId(index)}
        role="option"
        aria-selected={on}
        // Keep the focus in the field: a click must not blur it shut.
        onMouseDown={(event) => event.preventDefault()}
        onMouseMove={() => index !== current && setActive(index)}
        onClick={() => pick(option.value)}
        className={cn(
          "flex cursor-pointer items-center justify-between gap-3 rounded-[7px] px-2.5 py-1.5 text-sm",
          index === current && "bg-surface-2",
          on ? "text-accent" : "text-fg",
        )}
      >
        <span className="truncate">{option.label}</span>
        {on ? <Check className="size-3.5 shrink-0" /> : null}
      </li>
    );
  };

  return (
    <div className="flex flex-col gap-2">
      {selected.length ? (
        <ul className="flex flex-wrap gap-1.5" aria-label={ariaLabel}>
          {selected.map((value) => (
            <li
              key={value}
              className="inline-flex items-center gap-1 rounded-pill border border-accent-line bg-accent-soft py-0.5 pr-1 pl-2.5 text-[13px] text-accent"
            >
              {labelOf(value)}
              <button
                type="button"
                onClick={() => onToggle(value)}
                className="rounded-full p-0.5 opacity-60 transition hover:opacity-100"
                aria-label={t("removeValue", { value: labelOf(value) })}
              >
                <X className="size-3" />
              </button>
            </li>
          ))}
        </ul>
      ) : null}

      <Popover.Root open={open} onOpenChange={setOpen}>
        <Popover.Anchor asChild>
          <div
            ref={anchorRef}
            onClick={() => {
              setOpen(true);
              inputRef.current?.focus();
            }}
            className={cn(
              "flex h-9.5 cursor-text items-center gap-2 rounded-ctl border border-line bg-surface px-2.5",
              "transition-colors hover:border-line-strong",
              open && "border-accent hover:border-accent",
            )}
          >
            <Search className="size-3.5 shrink-0 text-fg-faint" />
            <input
              ref={inputRef}
              role="combobox"
              aria-label={ariaLabel}
              aria-expanded={open}
              aria-controls={listId}
              aria-autocomplete="list"
              aria-activedescendant={open && shown.length ? optionId(current) : undefined}
              value={query}
              onChange={(event) => {
                setQuery(event.target.value);
                setActive(0);
                setOpen(true);
              }}
              onFocus={() => setOpen(true)}
              onKeyDown={onKeyDown}
              placeholder={placeholder}
              className="min-w-0 flex-1 bg-transparent py-1 text-sm outline-none placeholder:text-fg-faint"
            />
            <ChevronDown
              className={cn(
                "size-3.5 shrink-0 text-fg-faint transition-transform",
                open && "rotate-180",
              )}
            />
          </div>
        </Popover.Anchor>
        <Popover.Portal>
          <Popover.Content
            side="bottom"
            align="start"
            sideOffset={6}
            // The field keeps the focus; the list is driven from it.
            onOpenAutoFocus={(event) => event.preventDefault()}
            onCloseAutoFocus={(event) => event.preventDefault()}
            onInteractOutside={(event) => {
              if (anchorRef.current?.contains(event.target as Node)) event.preventDefault();
            }}
            className="z-50 w-(--radix-popover-trigger-width) overflow-hidden rounded-card border border-line bg-surface shadow-pop"
          >
            <ul
              id={listId}
              role="listbox"
              aria-multiselectable
              aria-label={ariaLabel}
              className="max-h-[min(18rem,var(--radix-popover-content-available-height))] overflow-y-auto p-1"
            >
              {shownPinned.map((option, index) => renderOption(option, index))}
              {shownPinned.length && shownOptions.length ? (
                <li role="presentation" className="hairline mx-1 my-1" />
              ) : null}
              {shownOptions.map((option, index) => renderOption(option, shownPinned.length + index))}
              {!shown.length ? (
                <li role="presentation" className="px-2.5 py-1.5 text-sm text-fg-faint">
                  {t("noMatches")}
                </li>
              ) : null}
            </ul>
          </Popover.Content>
        </Popover.Portal>
      </Popover.Root>
    </div>
  );
}
