"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/field";
import { useTimeAgo } from "@/lib/format";
import { useAddLeadNote } from "@/services/hooks";
import type { LeadNote } from "@/services/types";

export function NotesPanel({ leadId, notes }: { leadId: string; notes: LeadNote[] }) {
  const t = useTranslations("notes");
  const timeAgo = useTimeAgo();
  const [draft, setDraft] = useState("");
  const addNote = useAddLeadNote();

  const submit = async () => {
    const body = draft.trim();
    if (!body) return;
    await addNote.mutateAsync({ id: leadId, body });
    setDraft("");
  };

  return (
    <div className="flex flex-col gap-3 px-5 py-4">
      {notes.length ? (
        <ul className="flex flex-col gap-3">
          {notes.map((note) => (
            <li key={note.id} className="rounded-card border border-line bg-surface-2 px-3.5 py-3">
              <p className="text-sm leading-relaxed">{note.body}</p>
              <p className="mt-1.5 text-2xs text-fg-faint">
                {note.author} · {timeAgo(note.createdAt)}
              </p>
            </li>
          ))}
        </ul>
      ) : (
        <p className="text-sm text-fg-faint">{t("empty")}</p>
      )}

      <Textarea
        value={draft}
        onChange={(event) => setDraft(event.target.value)}
        placeholder={t("placeholder")}
        rows={3}
      />
      <div className="flex justify-end">
        <Button variant="primary" size="sm" onClick={submit} disabled={!draft.trim() || addNote.isPending}>
          {addNote.isPending ? t("saving") : t("add")}
        </Button>
      </div>
    </div>
  );
}
