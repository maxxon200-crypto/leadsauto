"""End-to-end orchestration: scrape -> enrich -> dedupe -> store."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional

from .dedupe import dedupe as dedupe_leads
from .enrich import enrich_lead
from .http import HttpClient
from .models import Lead
from .sources.base import Source
from .storage import LeadStore

log = logging.getLogger(__name__)


@dataclass
class RunResult:
    scraped: int = 0
    enriched: int = 0
    after_dedupe: int = 0
    written: int = 0
    leads: list[Lead] = field(default_factory=list)


def run(
    source: Source,
    query: str,
    limit: int = 100,
    *,
    enrich: bool = False,
    dedupe: bool = True,
    client: Optional[HttpClient] = None,
    store: Optional[LeadStore] = None,
) -> RunResult:
    """Run the full lead pipeline and (optionally) persist the results."""
    result = RunResult()

    leads: list[Lead] = []
    for lead in source.search(query, limit=limit):
        leads.append(lead)
    result.scraped = len(leads)
    log.info("scraped %d lead(s) from %s", result.scraped, source.name)

    if enrich:
        enrich_client = client or HttpClient()
        for lead in leads:
            if lead.website and not (lead.email and lead.phone):
                enrich_lead(lead, enrich_client)
                result.enriched += 1
        log.info("enriched %d lead(s)", result.enriched)

    if dedupe:
        leads = dedupe_leads(leads)
    result.after_dedupe = len(leads)
    result.leads = leads

    if store is not None:
        result.written = store.write(leads)
        log.info("wrote %d lead(s) to store", result.written)

    return result
