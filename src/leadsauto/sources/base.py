"""Base class and shared types for lead sources.

A *source* knows how to turn a search query into a stream of :class:`Lead`
objects. Concrete sources may hit the network (a directory scraper) or not
(the offline sample source). Sources are intentionally thin — enrichment,
dedupe and persistence are handled by the pipeline, not here.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Iterator, Optional

from ..http import HttpClient
from ..models import Lead


class Source(ABC):
    """Abstract lead source."""

    #: short, stable identifier used on the CLI and stored on each lead
    name: str = "base"
    #: one-line human description shown by ``leadsauto list-sources``
    description: str = ""
    #: whether :meth:`search` performs network requests
    requires_network: bool = True

    def __init__(self, client: Optional[HttpClient] = None) -> None:
        self.client = client

    @abstractmethod
    def search(self, query: str, limit: int = 100) -> Iterator[Lead]:
        """Yield up to ``limit`` leads matching ``query``."""
        raise NotImplementedError
