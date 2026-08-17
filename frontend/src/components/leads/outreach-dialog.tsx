"use client";

import { Copy, Sparkles } from "lucide-react";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { SelectField } from "@/components/ui/controls";
import { Field } from "@/components/ui/field";
import { Modal } from "@/components/ui/overlay";
import { useToast } from "@/components/ui/toast";
import { useGenerateOutreach } from "@/services/hooks";
import type { Lead, OutreachChannel, OutreachTone } from "@/services/types";

const CHANNELS: { value: OutreachChannel; label: string }[] = [
  { value: "instagram_dm", label: "Instagram DM" },
  { value: "linkedin_dm", label: "LinkedIn message" },
  { value: "email", label: "Email" },
];

const TONES: { value: OutreachTone; label: string }[] = [
  { value: "warm", label: "Warm" },
  { value: "direct", label: "Direct" },
  { value: "formal", label: "Formal" },
];

/**
 * Personalised outreach draft (spec §1, step 11). In Phase 1 the copy comes
 * from a template; the request shape already matches POST /leads/:id/outreach.
 */
export function OutreachDialog({ lead }: { lead: Lead }) {
  const [open, setOpen] = useState(false);
  const [channel, setChannel] = useState<OutreachChannel>(
    lead.contacts.email ? "email" : "instagram_dm",
  );
  const [tone, setTone] = useState<OutreachTone>("warm");
  const [language, setLanguage] = useState(lead.languages[0] ?? "English");
  const generate = useGenerateOutreach(lead.id);
  const { toast } = useToast();

  const message = generate.data;

  const copy = async () => {
    if (!message) return;
    try {
      await navigator.clipboard.writeText(
        [message.subject, message.body].filter(Boolean).join("\n\n"),
      );
      toast({ title: "Copied to clipboard", tone: "good" });
    } catch {
      toast({ title: "Copy failed", description: "Select the text and copy manually.", tone: "warn" });
    }
  };

  return (
    <>
      <Button variant="secondary" onClick={() => setOpen(true)}>
        <Sparkles />
        Draft outreach
      </Button>

      <Modal
        open={open}
        onOpenChange={setOpen}
        title={`Message ${lead.name.split(" ")[0]}`}
        description="Generated from the evidence on this profile — review before sending."
        footer={
          <>
            <Button variant="ghost" onClick={() => setOpen(false)}>
              Close
            </Button>
            <Button
              variant="primary"
              onClick={() => generate.mutate({ channel, tone, language })}
              disabled={generate.isPending}
            >
              <Sparkles />
              {generate.isPending ? "Writing…" : message ? "Regenerate" : "Generate draft"}
            </Button>
          </>
        }
      >
        <div className="flex flex-col gap-4">
          <div className="grid gap-4 sm:grid-cols-3">
            <Field label="Channel">
              <SelectField
                ariaLabel="Channel"
                value={channel}
                onValueChange={(value) => setChannel(value as OutreachChannel)}
                options={CHANNELS}
                className="w-full"
              />
            </Field>
            <Field label="Tone">
              <SelectField
                ariaLabel="Tone"
                value={tone}
                onValueChange={(value) => setTone(value as OutreachTone)}
                options={TONES}
                className="w-full"
              />
            </Field>
            <Field label="Language">
              <SelectField
                ariaLabel="Language"
                value={language}
                onValueChange={setLanguage}
                options={(lead.languages.length ? lead.languages : ["English"]).map((entry) => ({
                  value: entry,
                  label: entry,
                }))}
                className="w-full"
              />
            </Field>
          </div>

          {message ? (
            <div className="rounded-card border border-line bg-surface-2 p-4">
              {message.subject ? (
                <p className="mb-2 text-sm font-medium">{message.subject}</p>
              ) : null}
              <p className="text-sm leading-relaxed whitespace-pre-wrap text-fg-muted">
                {message.body}
              </p>
              <div className="mt-3 flex justify-end">
                <Button variant="ghost" size="sm" onClick={copy}>
                  <Copy />
                  Copy
                </Button>
              </div>
            </div>
          ) : (
            <p className="rounded-card border border-dashed border-line px-4 py-8 text-center text-sm text-fg-faint">
              No draft yet. Pick a channel and generate one.
            </p>
          )}
        </div>
      </Modal>
    </>
  );
}
