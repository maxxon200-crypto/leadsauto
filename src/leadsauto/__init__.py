"""leadsauto — a polite, config-driven lead-scraping toolkit for architects.

Public API surface kept small and stable:

    from leadsauto import Lead, run, HttpClient
"""

from __future__ import annotations

from .http import HttpClient
from .models import Lead
from .pipeline import RunResult, run

__version__ = "0.1.0"

__all__ = ["Lead", "HttpClient", "run", "RunResult", "__version__"]
