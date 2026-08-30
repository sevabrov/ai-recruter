"use client";

import { Copy, Sparkles } from "lucide-react";
import { useTranslations } from "next-intl";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { SelectField } from "@/components/ui/controls";
import { Field } from "@/components/ui/field";
import { Modal } from "@/components/ui/overlay";
import { useToast } from "@/components/ui/toast";
import { useGenerateOutreach } from "@/services/hooks";
import type { Lead, OutreachChannel, OutreachTone } from "@/services/types";

const CHANNELS: OutreachChannel[] = ["instagram_dm", "linkedin_dm", "email"];
const TONES: OutreachTone[] = ["warm", "direct", "formal"];

/**
 * Personalised outreach draft (spec §1, step 11). In Phase 1 the copy comes
 * from a template; the request shape already matches POST /leads/:id/outreach.
 *
 * The `language` field is the *lead's* language, not the interface language:
 * a Ukrainian-speaking recruiter still writes to a Spanish prospect in Spanish.
 */
export function OutreachDialog({ lead }: { lead: Lead }) {
  const t = useTranslations("outreach");
  const common = useTranslations("common");
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
      toast({ title: t("copied"), tone: "good" });
    } catch {
      toast({ title: t("copyFailed"), description: t("copyFailedBody"), tone: "warn" });
    }
  };

  return (
    <>
      <Button variant="secondary" onClick={() => setOpen(true)}>
        <Sparkles />
        {t("draft")}
      </Button>

      <Modal
        open={open}
        onOpenChange={setOpen}
        title={t("modalTitle", { name: lead.name.split(" ")[0] })}
        description={t("modalDescription")}
        footer={
          <>
            <Button variant="ghost" onClick={() => setOpen(false)}>
              {common("close")}
            </Button>
            <Button
              variant="primary"
              onClick={() => generate.mutate({ channel, tone, language })}
              disabled={generate.isPending}
            >
              <Sparkles />
              {generate.isPending
                ? t("writing")
                : message
                  ? t("regenerate")
                  : t("generate")}
            </Button>
          </>
        }
      >
        <div className="flex flex-col gap-4">
          <div className="grid gap-4 sm:grid-cols-3">
            <Field label={t("channel")}>
              <SelectField
                ariaLabel={t("channel")}
                value={channel}
                onValueChange={(value) => setChannel(value as OutreachChannel)}
                options={CHANNELS.map((value) => ({ value, label: t(`channels.${value}`) }))}
                className="w-full"
              />
            </Field>
            <Field label={t("tone")}>
              <SelectField
                ariaLabel={t("tone")}
                value={tone}
                onValueChange={(value) => setTone(value as OutreachTone)}
                options={TONES.map((value) => ({ value, label: t(`tones.${value}`) }))}
                className="w-full"
              />
            </Field>
            <Field label={t("language")}>
              <SelectField
                ariaLabel={t("language")}
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
                  {common("copy")}
                </Button>
              </div>
            </div>
          ) : (
            <p className="rounded-card border border-dashed border-line px-4 py-8 text-center text-sm text-fg-faint">
              {t("noDraft")}
            </p>
          )}
        </div>
      </Modal>
    </>
  );
}
