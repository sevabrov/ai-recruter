"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/field";
import { formatRelativeTime } from "@/lib/utils";
import { useAddLeadNote } from "@/services/hooks";
import type { LeadNote } from "@/services/types";

export function NotesPanel({ leadId, notes }: { leadId: string; notes: LeadNote[] }) {
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
                {note.author} · {formatRelativeTime(note.createdAt)}
              </p>
            </li>
          ))}
        </ul>
      ) : (
        <p className="text-sm text-fg-faint">No notes yet.</p>
      )}

      <Textarea
        value={draft}
        onChange={(event) => setDraft(event.target.value)}
        placeholder="What did you notice about this candidate?"
        rows={3}
      />
      <div className="flex justify-end">
        <Button variant="primary" size="sm" onClick={submit} disabled={!draft.trim() || addNote.isPending}>
          {addNote.isPending ? "Saving…" : "Add note"}
        </Button>
      </div>
    </div>
  );
}
