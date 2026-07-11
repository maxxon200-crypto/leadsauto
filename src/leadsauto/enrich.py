"""Contact enrichment helpers.

Given a lead that has a website but no email/phone (a common case in scraped
directory listings), we can visit the site's homepage and likely "contact"
pages and pull business contact details out of the markup.

The extraction functions are pure and network-free so they are easy to test;
:func:`enrich_lead` wires them to an :class:`~leadsauto.http.HttpClient`.
"""

from __future__ import annotations

import logging
import re
from urllib.parse import urljoin

from .http import HttpClient, RobotsDisallowed
from .models import Lead, normalize_email, normalize_phone

log = logging.getLogger(__name__)

# Email addresses. Deliberately conservative to avoid matching asset filenames.
EMAIL_RE = re.compile(
    r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,24}\b"
)

# Reject obvious non-contact matches (tracking pixels, placeholder addresses,
# image files that happen to look like emails).
_EMAIL_BLOCKLIST = re.compile(
    r"(\.png|\.jpg|\.jpeg|\.gif|\.webp|\.svg|@sentry|@example\.|@2x|"
    r"noreply|no-reply|@domain\.|your@|email@example)",
    re.IGNORECASE,
)

# Italian + generic phone numbers. Matches +39 / 0039 prefixes, landlines and
# mobiles with common separators. Italian national numbers vary in length, so
# the trailing block accepts a run of digits (each optionally separated) rather
# than a fixed grouping; :func:`_looks_like_phone` validates the digit count.
PHONE_RE = re.compile(
    r"(?:(?:\+|00)\s?39[\s.\-]?)?"     # optional Italy country code (+39 / 0039)
    r"(?:0\d{1,3}|3\d{2})"           # area code (landline) or mobile prefix
    r"(?:[\s./\-]?\d){5,9}"           # 5-9 further digits with optional separators
)

# Paths commonly used for contact information.
CONTACT_PATHS = ["", "/contatti", "/contact", "/contact-us", "/chi-siamo", "/about"]


def extract_emails(text: str) -> list[str]:
    seen: list[str] = []
    for raw in EMAIL_RE.findall(text or ""):
        if _EMAIL_BLOCKLIST.search(raw):
            continue
        email = normalize_email(raw)
        if email and email not in seen:
            seen.append(email)
    return seen


def _looks_like_phone(candidate: str) -> bool:
    digits = re.sub(r"\D", "", candidate)
    return 6 <= len(digits) <= 15


def extract_phones(text: str) -> list[str]:
    seen: list[str] = []
    for raw in PHONE_RE.findall(text or ""):
        if not _looks_like_phone(raw):
            continue
        phone = normalize_phone(raw)
        if phone and phone not in seen:
            seen.append(phone)
    return seen


def _html_to_text(html: str) -> str:
    """Best-effort text extraction; uses BeautifulSoup when available."""
    try:
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(html, "lxml")
        # mailto/tel links carry the cleanest data — surface them explicitly.
        extra = []
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if href.startswith("mailto:"):
                extra.append(href[len("mailto:"):].split("?")[0])
            elif href.startswith("tel:"):
                extra.append(href[len("tel:"):])
        return soup.get_text(" ") + " " + " ".join(extra)
    except Exception:  # pragma: no cover - fallback path
        return re.sub(r"<[^>]+>", " ", html)


def enrich_lead(lead: Lead, client: HttpClient, max_pages: int = 3) -> Lead:
    """Populate a lead's ``email``/``phone`` from its website, in place."""
    if not lead.website:
        return lead
    if lead.email and lead.phone:
        return lead

    checked = 0
    for path in CONTACT_PATHS:
        if checked >= max_pages:
            break
        url = urljoin(lead.website + "/", path.lstrip("/")) if path else lead.website
        try:
            html = client.get_text(url)
        except RobotsDisallowed:
            log.debug("robots.txt disallows %s", url)
            continue
        except Exception as exc:  # network error, 404, etc.
            log.debug("enrich fetch failed for %s: %s", url, exc)
            continue
        checked += 1

        text = _html_to_text(html)
        if not lead.email:
            emails = extract_emails(text)
            if emails:
                lead.email = emails[0]
        if not lead.phone:
            phones = extract_phones(text)
            if phones:
                lead.phone = phones[0]
        if lead.email and lead.phone:
            break

    lead.normalize()
    return lead
