"""A configuration-driven directory scraper.

Most professional directories (e.g. an *Ordine degli Architetti* member list)
render results as a repeating block of HTML. Rather than hard-code a scraper
per site, this source is driven entirely by a YAML/dict config describing:

* the search URL template (with ``{query}`` and ``{page}`` placeholders),
* the CSS selector that isolates each result block, and
* per-field CSS selectors (optionally reading an attribute).

That makes adding a new directory a config change, not a code change. See
``config/sources.example.yaml`` for a documented example.
"""

from __future__ import annotations

import logging
from typing import Any, Iterator, Optional
from urllib.parse import quote_plus, urljoin

from ..http import HttpClient
from ..models import Lead
from .base import Source

log = logging.getLogger(__name__)


class GenericDirectorySource(Source):
    requires_network = True

    def __init__(
        self,
        name: str,
        config: dict[str, Any],
        client: Optional[HttpClient] = None,
    ) -> None:
        super().__init__(client=client)
        self.name = name
        self.description = config.get("description", f"Directory scraper: {name}")
        self.config = config
        self.base_url: str = config.get("base_url", "")
        self.search_url: str = config["search_url"]
        self.list_selector: str = config["list_selector"]
        self.fields: dict[str, dict[str, Any]] = config.get("fields", {})
        self.defaults: dict[str, str] = config.get("defaults", {})
        self.start_page: int = int(config.get("start_page", 1))
        self.max_pages: int = int(config.get("max_pages", 5))

    # -- field extraction ---------------------------------------------------
    def _extract_field(self, block, spec: dict[str, Any]) -> str:
        selector = spec.get("selector")
        node = block.select_one(selector) if selector else block
        if node is None:
            return ""
        attr = spec.get("attr")
        if attr:
            value = node.get(attr, "") or ""
        else:
            value = node.get_text(" ", strip=True)
        prefix = spec.get("strip_prefix")
        if prefix and value.startswith(prefix):
            value = value[len(prefix):]
        if spec.get("absolute") and value:
            value = urljoin(self.base_url or self.search_url, value)
        return value.strip()

    def _parse_page(self, html: str) -> list[Lead]:
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(html, "lxml")
        leads: list[Lead] = []
        for block in soup.select(self.list_selector):
            data: dict[str, str] = dict(self.defaults)
            for field_name, spec in self.fields.items():
                value = self._extract_field(block, spec)
                if value:
                    data[field_name] = value
            data["source"] = self.name
            lead = Lead.from_row(data)
            if not lead.is_empty():
                leads.append(lead)
        return leads

    def _page_url(self, query: str, page: int) -> str:
        return self.search_url.format(query=quote_plus(query), page=page)

    # -- Source API ---------------------------------------------------------
    def search(self, query: str, limit: int = 100) -> Iterator[Lead]:
        if self.client is None:
            self.client = HttpClient()

        emitted = 0
        for page in range(self.start_page, self.start_page + self.max_pages):
            if emitted >= limit:
                return
            url = self._page_url(query, page)
            try:
                html = self.client.get_text(url)
            except Exception as exc:
                log.warning("failed to fetch %s: %s", url, exc)
                break

            page_leads = self._parse_page(html)
            if not page_leads:
                log.debug("no results on page %s (%s); stopping", page, url)
                break

            for lead in page_leads:
                if emitted >= limit:
                    return
                yield lead
                emitted += 1
