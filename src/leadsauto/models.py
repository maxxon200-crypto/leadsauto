"""Core data model for a scraped lead.

The :class:`Lead` dataclass is the single record type that flows through the
whole pipeline (source -> enrich -> dedupe -> storage). Keeping it small and
serialisable makes it trivial to persist as CSV rows or SQLite columns.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field, fields, asdict
from datetime import datetime, timezone
from typing import Any


# Ordered list of columns used when writing CSV/SQLite so the output schema is
# stable regardless of dict ordering.
FIELD_ORDER: list[str] = [
    "name",
    "studio",
    "profession",
    "email",
    "phone",
    "website",
    "address",
    "city",
    "province",
    "region",
    "postal_code",
    "country",
    "source",
    "source_url",
    "tags",
    "notes",
    "scraped_at",
]


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def normalize_email(value: str | None) -> str:
    if not value:
        return ""
    return value.strip().strip(".,;").lower()


def normalize_phone(value: str | None) -> str:
    """Normalise a phone number to digits with an optional leading ``+``.

    Preserves an international prefix but strips spaces, dots, slashes and
    parentheses so two spellings of the same number compare equal.
    """
    if not value:
        return ""
    value = value.strip()
    plus = value.startswith("+") or value.startswith("00")
    digits = re.sub(r"\D", "", value)
    if not digits:
        return ""
    if value.startswith("00"):
        digits = digits[2:]
    return ("+" if plus else "") + digits


def normalize_website(value: str | None) -> str:
    if not value:
        return ""
    value = value.strip()
    if value.startswith("mailto:") or value.startswith("tel:"):
        return ""
    if not re.match(r"^https?://", value, re.IGNORECASE):
        value = "https://" + value
    return value.rstrip("/")


@dataclass
class Lead:
    """A single business contact (typically an architect / studio)."""

    name: str = ""
    studio: str = ""
    profession: str = ""
    email: str = ""
    phone: str = ""
    website: str = ""
    address: str = ""
    city: str = ""
    province: str = ""
    region: str = ""
    postal_code: str = ""
    country: str = "IT"
    source: str = ""
    source_url: str = ""
    tags: str = ""
    notes: str = ""
    scraped_at: str = field(default_factory=_now_iso)

    def __post_init__(self) -> None:
        self.normalize()

    def normalize(self) -> "Lead":
        self.name = (self.name or "").strip()
        self.studio = (self.studio or "").strip()
        self.email = normalize_email(self.email)
        self.phone = normalize_phone(self.phone)
        self.website = normalize_website(self.website)
        self.city = (self.city or "").strip()
        return self

    @property
    def display_name(self) -> str:
        return self.name or self.studio or self.email or self.website or "(unknown)"

    def is_empty(self) -> bool:
        """True when there is nothing worth keeping (no name/studio/contact)."""
        return not any(
            [self.name, self.studio, self.email, self.phone, self.website]
        )

    def merge(self, other: "Lead") -> "Lead":
        """Fill blank fields on this lead from ``other`` (non-destructive)."""
        for f in fields(self):
            if f.name == "scraped_at":
                continue
            if not getattr(self, f.name) and getattr(other, f.name):
                setattr(self, f.name, getattr(other, f.name))
        return self

    def to_row(self) -> dict[str, Any]:
        data = asdict(self)
        return {k: data.get(k, "") for k in FIELD_ORDER}

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> "Lead":
        known = {f.name for f in fields(cls)}
        clean = {k: (v if v is not None else "") for k, v in row.items() if k in known}
        return cls(**clean)
