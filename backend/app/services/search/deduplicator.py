"""
Lead deduplication (spec §45).

One person is usually four search results: Instagram, LinkedIn, Facebook, a
personal site. Four leads for one human makes the whole product feel broken, so
merging happens before anything is stored.

Phase 2 merges on the strong keys the spec lists — canonical profile URL, email,
website, exact username — and keeps the richer record while absorbing the other's
platforms and sources. Fuzzy entity resolution (name + location + bio similarity)
is deliberately not attempted yet: a wrong merge destroys data, while a missed
merge only shows a duplicate.
"""

from app.models.lead import Lead
from app.services.search.url_tools import canonicalize


def merge_keys(lead: Lead) -> set[str]:
    keys: set[str] = set()
    for entry in lead.platforms:
        canonical = canonicalize(entry.url)
        keys.add(f"url:{canonical}")
        if entry.handle:
            keys.add(f"handle:{entry.platform.value}:{entry.handle.lstrip('@').lower()}")
    if lead.contacts.email:
        keys.add(f"email:{lead.contacts.email.strip().lower()}")
    if lead.contacts.website:
        keys.add(f"site:{canonicalize(lead.contacts.website)}")
    return keys


def deduplicate(leads: list[Lead]) -> tuple[list[Lead], int]:
    """Returns the merged leads and how many duplicates were absorbed."""
    merged: list[Lead] = []
    index: dict[str, int] = {}
    duplicates = 0

    for lead in leads:
        keys = merge_keys(lead)
        hit = next((index[key] for key in keys if key in index), None)

        if hit is None:
            merged.append(lead)
            position = len(merged) - 1
        else:
            merged[hit] = _absorb(merged[hit], lead)
            position = hit
            duplicates += 1

        for key in merge_keys(merged[position]):
            index[key] = position

    return merged, duplicates


def _absorb(keeper: Lead, other: Lead) -> Lead:
    """Keep the better-scored record; take everything the other one knew."""
    winner, loser = (keeper, other) if keeper.score >= other.score else (other, keeper)

    platforms = list(winner.platforms)
    known = {canonicalize(entry.url) for entry in platforms}
    platforms.extend(entry for entry in loser.platforms if canonicalize(entry.url) not in known)

    sources = list(winner.sources)
    seen_sources = {canonicalize(source.url) for source in sources}
    sources.extend(
        source for source in loser.sources if canonicalize(source.url) not in seen_sources
    )

    contacts = winner.contacts.model_copy(
        update={
            "email": winner.contacts.email or loser.contacts.email,
            "website": winner.contacts.website or loser.contacts.website,
            "phone": winner.contacts.phone or loser.contacts.phone,
        }
    )

    trail = {
        *winner.merged_urls,
        *loser.merged_urls,
        *(canonicalize(entry.url) for entry in loser.platforms),
    }

    return winner.model_copy(
        update={
            "platforms": platforms,
            "sources": sources,
            "contacts": contacts,
            "languages": list(dict.fromkeys([*winner.languages, *loser.languages])),
            "merged_urls": sorted(trail),
        }
    )
