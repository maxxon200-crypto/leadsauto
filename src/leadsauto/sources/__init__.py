"""Source registry.

Built-in sources register themselves here; directory scrapers defined in a
YAML config file are loaded on demand via :func:`load_config_sources`.
"""

from __future__ import annotations

from typing import Optional

from ..http import HttpClient
from .base import Source
from .generic_directory import GenericDirectorySource
from .sample import SampleSource

# name -> zero-arg (or client-arg) factory for built-in sources
_BUILTIN: dict[str, type[Source]] = {
    SampleSource.name: SampleSource,
}


def builtin_names() -> list[str]:
    return sorted(_BUILTIN)


def get_source(name: str, client: Optional[HttpClient] = None) -> Source:
    """Instantiate a built-in source by name."""
    try:
        cls = _BUILTIN[name]
    except KeyError:
        raise KeyError(
            f"Unknown source {name!r}. Built-in sources: {', '.join(builtin_names())}"
        ) from None
    return cls(client=client)


def load_config_sources(
    config: dict, client: Optional[HttpClient] = None
) -> dict[str, Source]:
    """Build :class:`GenericDirectorySource` instances from a parsed config.

    Expects a mapping like ``{"sources": {name: {type: generic_directory, ...}}}``.
    """
    sources: dict[str, Source] = {}
    for name, spec in (config or {}).get("sources", {}).items():
        stype = spec.get("type", "generic_directory")
        if stype != "generic_directory":
            raise ValueError(
                f"Source {name!r}: unsupported type {stype!r} "
                "(only 'generic_directory' is configurable)"
            )
        sources[name] = GenericDirectorySource(name=name, config=spec, client=client)
    return sources


__all__ = [
    "Source",
    "SampleSource",
    "GenericDirectorySource",
    "builtin_names",
    "get_source",
    "load_config_sources",
]
