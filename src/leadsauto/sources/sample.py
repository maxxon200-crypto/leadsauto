"""An offline sample source.

Returns a handful of fictional architect studios so the whole pipeline
(scrape -> enrich -> dedupe -> store) can be demoed and tested without any
network access. Use it to sanity-check an install:

    leadsauto scrape --source sample --query milano --out demo.csv
"""

from __future__ import annotations

from typing import Iterator

from ..models import Lead
from .base import Source

# Fictional data. Any resemblance to real studios is coincidental.
_SAMPLE_LEADS: list[dict] = [
    {
        "name": "Giulia Ferrari",
        "studio": "Studio Ferrari Architettura",
        "profession": "Architetto",
        "email": "info@ferrari-arch.example",
        "phone": "+39 02 1234 5678",
        "website": "https://ferrari-arch.example",
        "city": "Milano",
        "province": "MI",
        "region": "Lombardia",
    },
    {
        "name": "Marco Bianchi",
        "studio": "Bianchi & Partners",
        "profession": "Architetto",
        "phone": "02 8765 4321",
        "website": "https://bianchipartners.example",
        "city": "Milano",
        "province": "MI",
        "region": "Lombardia",
    },
    {
        "name": "Sofia Romano",
        "studio": "Romano Design Studio",
        "profession": "Architetto",
        "email": "sofia@romanostudio.example",
        "city": "Torino",
        "province": "TO",
        "region": "Piemonte",
    },
    # Intentional near-duplicate of the first entry (same email) to exercise
    # the dedupe/merge path.
    {
        "name": "Giulia Ferrari",
        "studio": "Studio Ferrari",
        "profession": "Architetto",
        "email": "info@ferrari-arch.example",
        "address": "Via Roma 12",
        "postal_code": "20100",
        "city": "Milano",
    },
]


class SampleSource(Source):
    name = "sample"
    description = "Offline demo data (fictional architect studios)"
    requires_network = False

    def search(self, query: str, limit: int = 100) -> Iterator[Lead]:
        q = (query or "").strip().lower()
        count = 0
        for data in _SAMPLE_LEADS:
            if count >= limit:
                return
            # Treat the query as a simple city/name filter; empty = all.
            haystack = " ".join(str(v) for v in data.values()).lower()
            if q and q not in haystack:
                continue
            lead = Lead.from_row({**data, "source": self.name})
            count += 1
            yield lead
