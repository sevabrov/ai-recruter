"use client";

import { X } from "lucide-react";
import { useState, type KeyboardEvent } from "react";
import { cn } from "@/lib/utils";

/**
 * Token input for keyword-style criteria. Enter or comma commits a value,
 * Backspace on an empty field removes the last one.
 */
export function ChipInput({
  values,
  onChange,
  placeholder,
  suggestions = [],
  tone = "neutral",
  id,
}: {
  values: string[];
  onChange: (values: string[]) => void;
  placeholder?: string;
  suggestions?: string[];
  tone?: "neutral" | "negative";
  id?: string;
}) {
  const [draft, setDraft] = useState("");

  const commit = (raw: string) => {
    const value = raw.trim().replace(/,$/, "");
    if (!value) return;
    if (!values.some((entry) => entry.toLowerCase() === value.toLowerCase())) {
      onChange([...values, value]);
    }
    setDraft("");
  };

  const onKeyDown = (event: KeyboardEvent<HTMLInputElement>) => {
    if (event.key === "Enter" || event.key === ",") {
      event.preventDefault();
      commit(draft);
    } else if (event.key === "Backspace" && !draft && values.length) {
      onChange(values.slice(0, -1));
    }
  };

  const unusedSuggestions = suggestions.filter(
    (suggestion) => !values.some((value) => value.toLowerCase() === suggestion.toLowerCase()),
  );

  return (
    <div className="flex flex-col gap-2">
      <div
        className={cn(
          "flex min-h-9.5 flex-wrap items-center gap-1.5 rounded-ctl border border-line bg-surface px-2 py-1.5",
          "transition-colors focus-within:border-accent hover:border-line-strong",
        )}
      >
        {values.map((value) => (
          <span
            key={value}
            className={cn(
              "inline-flex items-center gap-1 rounded-pill border px-2 py-0.5 text-[13px]",
              tone === "negative"
                ? "border-bad/25 bg-bad-soft text-bad"
                : "border-accent-line bg-accent-soft text-accent",
            )}
          >
            {value}
            <button
              type="button"
              onClick={() => onChange(values.filter((entry) => entry !== value))}
              className="rounded-full p-0.5 opacity-60 transition hover:opacity-100"
              aria-label={`Remove ${value}`}
            >
              <X className="size-3" />
            </button>
          </span>
        ))}
        <input
          id={id}
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          onKeyDown={onKeyDown}
          onBlur={() => commit(draft)}
          placeholder={values.length ? "" : placeholder}
          className="min-w-24 flex-1 bg-transparent px-1 py-0.5 text-sm outline-none placeholder:text-fg-faint"
        />
      </div>

      {unusedSuggestions.length ? (
        <div className="flex flex-wrap items-center gap-1.5">
          <span className="text-2xs text-fg-faint">Suggestions</span>
          {unusedSuggestions.slice(0, 6).map((suggestion) => (
            <button
              key={suggestion}
              type="button"
              onClick={() => commit(suggestion)}
              className="rounded-pill border border-dashed border-line-strong px-2 py-0.5 text-[13px] text-fg-muted transition hover:border-accent hover:text-accent"
            >
              + {suggestion}
            </button>
          ))}
        </div>
      ) : null}
    </div>
  );
}
