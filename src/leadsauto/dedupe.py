"""Deduplication of leads.

Directory scrapes routinely surface the same architect more than once (paged
listings, multiple sources). We collapse duplicates using a cascade of keys:

1. email (strongest signal)
2. website domain
3. normalised name + city

When two records match, their fields are merged so partial rows combine into
one complete lead.
"""

from __future__ import annotations

import re
import unicodedata
from urllib.parse import urlparse

from .models import Lead


def _slug(value: str) -> str:
    """Lowercase, strip accents and punctuation -> comparable token."""
    value = unicodedata.normalize("NFKD", value or "")
    value = "".join(c for c in value if not unicodedata.combining(c))
    value = value.lower()
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def _domain(website: str) -> str:
    if not website:
        return ""
    host = urlparse(website).netloc.lower()
    return host[4:] if host.startswith("www.") else host


def dedupe_key(lead: Lead) -> str | None:
    if lead.email:
        return f"email:{lead.email}"
    domain = _domain(lead.website)
    if domain:
        return f"site:{domain}"
    name_slug = _slug(lead.name) or _slug(lead.studio)
    if name_slug:
        return f"name:{name_slug}|{_slug(lead.city)}"
    return None


def dedupe(leads: list[Lead]) -> list[Lead]:
    """Return a de-duplicated list, preserving first-seen order and merging."""
    merged: dict[str, Lead] = {}
    passthrough: list[Lead] = []  # leads with no usable key are kept as-is

    for lead in leads:
        key = dedupe_key(lead)
        if key is None:
            passthrough.append(lead)
            continue
        if key in merged:
            merged[key].merge(lead)
        else:
            merged[key] = lead

    return list(merged.values()) + passthrough
