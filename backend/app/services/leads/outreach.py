"""
Outreach drafting (spec §1, item 11).

Template-based for now, and structured so the Phase 8 model call is a drop-in:
the inputs a good message needs are already assembled here — the lead's
strongest evidence, their location, the chosen channel and tone.
"""

import uuid
from datetime import UTC, datetime

from app.models.common import HIGH_QUALITY_THRESHOLD, OutreachChannel, OutreachTone
from app.models.lead import Lead, OutreachMessage

OPENERS: dict[OutreachTone, str] = {
    OutreachTone.WARM: "Hi {first}! I came across your profile and genuinely enjoyed your content.",
    OutreachTone.DIRECT: "Hi {first} — short and to the point.",
    OutreachTone.FORMAL: "Dear {first},",
}

CLOSERS: dict[OutreachTone, str] = {
    OutreachTone.WARM: "Would you be open to a short call this week? No pressure either way.",
    OutreachTone.DIRECT: "Open to a 15-minute call this week?",
    OutreachTone.FORMAL: "I would be glad to arrange a call at your convenience.",
}


class OutreachService:
    def draft(
        self,
        lead: Lead,
        *,
        channel: OutreachChannel,
        tone: OutreachTone,
        language: str,
    ) -> OutreachMessage:
        first_name = lead.name.split(" ")[0]
        return OutreachMessage(
            id=f"msg_{uuid.uuid4().hex[:10]}",
            lead_id=lead.id,
            channel=channel,
            tone=tone,
            language=language,
            subject=(
                f"{first_name} — quick question about your beauty team"
                if channel is OutreachChannel.EMAIL
                else None
            ),
            body=_body(lead, first_name, channel, tone),
            created_at=datetime.now(UTC),
        )


def _body(lead: Lead, first_name: str, channel: OutreachChannel, tone: OutreachTone) -> str:
    strongest = sorted(
        (signal for signal in lead.signals if signal.detected),
        key=lambda signal: signal.confidence,
        reverse=True,
    )
    hook = next((s.evidence for s in strongest if s.evidence), None) or lead.headline
    hook = hook.strip('"“” ').strip()
    where = (lead.location.city or lead.location.country) if lead.location else None
    place = where or "your region"

    relevance = (
        f"Your background in {place} is exactly the profile our team is expanding with right now."
        if lead.score >= HIGH_QUALITY_THRESHOLD
        else f"We are expanding our beauty team in {place} and your experience looks relevant."
    )

    lines = [
        OPENERS[tone].format(first=first_name),
        f"What caught my attention: {hook}",
        relevance,
        CLOSERS[tone],
    ]
    if channel is OutreachChannel.EMAIL:
        lines.append("\n— Drafted by AI Recruiter (template; the model writes these from Phase 8)")
    return "\n\n".join(lines)
