"""Command-line interface for leadsauto.

Commands
--------
* ``list-sources``  – show built-in and configured sources
* ``scrape``        – run a source, enrich/dedupe, and write results
* ``enrich``        – enrich an existing CSV of leads in place
"""

from __future__ import annotations

import argparse
import logging
import sys
from typing import Optional, Sequence

from . import __version__
from .config import load_config
from .enrich import enrich_lead
from .http import HttpClient
from .pipeline import run as run_pipeline
from .sources import builtin_names, get_source, load_config_sources
from .storage import CsvStore, open_store


def _build_client(args: argparse.Namespace) -> HttpClient:
    return HttpClient(
        min_delay=args.delay,
        respect_robots=not args.ignore_robots,
    )


def _resolve_source(name: str, config: dict, client: HttpClient):
    if name in builtin_names():
        return get_source(name, client=client)
    configured = load_config_sources(config, client=client)
    if name in configured:
        return configured[name]
    available = builtin_names() + sorted(configured)
    raise SystemExit(
        f"error: unknown source {name!r}. Available: {', '.join(available) or '(none)'}"
    )


def cmd_list_sources(args: argparse.Namespace) -> int:
    config = load_config(args.config) if args.config else {}
    print("Built-in sources:")
    client = HttpClient()
    for name in builtin_names():
        src = get_source(name, client=client)
        net = "network" if src.requires_network else "offline"
        print(f"  {name:<20} [{net}]  {src.description}")

    configured = load_config_sources(config, client=client)
    if configured:
        print("\nConfigured sources ({}):".format(args.config))
        for name, src in configured.items():
            print(f"  {name:<20} [network]  {src.description}")
    elif args.config:
        print(f"\nNo sources found in {args.config}.")
    else:
        print("\n(Pass --config <file.yaml> to load directory scrapers.)")
    return 0


def cmd_scrape(args: argparse.Namespace) -> int:
    config = load_config(args.config) if args.config else {}
    client = _build_client(args)
    source = _resolve_source(args.source, config, client)

    store = open_store(args.out, fmt=args.format, append=args.append) if args.out else None

    result = run_pipeline(
        source,
        query=args.query,
        limit=args.limit,
        enrich=args.enrich,
        dedupe=not args.no_dedupe,
        client=client,
        store=store,
    )
    client.close()

    print(
        f"scraped={result.scraped} enriched={result.enriched} "
        f"deduped={result.after_dedupe} written={result.written}"
    )
    if args.out:
        print(f"-> {args.out}")
    else:
        # No output file: print a compact preview to stdout.
        for lead in result.leads[:20]:
            print(f"  - {lead.display_name} | {lead.email} | {lead.phone} | {lead.city}")
        if len(result.leads) > 20:
            print(f"  ... and {len(result.leads) - 20} more")
    return 0


def cmd_enrich(args: argparse.Namespace) -> int:
    src_store = CsvStore(args.infile)
    leads = src_store.read()
    if not leads:
        print(f"error: no leads read from {args.infile}", file=sys.stderr)
        return 1

    client = _build_client(args)
    enriched = 0
    for lead in leads:
        if lead.website and not (lead.email and lead.phone):
            before = (lead.email, lead.phone)
            enrich_lead(lead, client)
            if (lead.email, lead.phone) != before:
                enriched += 1
    client.close()

    out = args.out or args.infile
    written = CsvStore(out).write(leads)
    print(f"read={len(leads)} enriched={enriched} written={written} -> {out}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="leadsauto",
        description="Polite, config-driven lead scraping for architects (architetti).",
    )
    parser.add_argument("--version", action="version", version=f"leadsauto {__version__}")
    parser.add_argument(
        "-v", "--verbose", action="count", default=0, help="increase log verbosity"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # list-sources
    p_list = sub.add_parser("list-sources", help="list available sources")
    p_list.add_argument("--config", help="YAML file defining directory sources")
    p_list.set_defaults(func=cmd_list_sources)

    # shared scraping options
    def add_net_opts(p: argparse.ArgumentParser) -> None:
        p.add_argument("--delay", type=float, default=1.0,
                       help="min seconds between requests to a host (default: 1.0)")
        p.add_argument("--ignore-robots", action="store_true",
                       help="do not consult robots.txt (use responsibly)")

    # scrape
    p_scrape = sub.add_parser("scrape", help="scrape leads from a source")
    p_scrape.add_argument("--source", required=True, help="source name (see list-sources)")
    p_scrape.add_argument("--query", default="", help="search query (e.g. a city)")
    p_scrape.add_argument("--limit", type=int, default=100, help="max leads to collect")
    p_scrape.add_argument("--out", help="output file (.csv or .sqlite); omit to preview")
    p_scrape.add_argument("--format", choices=["csv", "sqlite"],
                          help="force output format (default: infer from extension)")
    p_scrape.add_argument("--append", action="store_true", help="append to an existing CSV")
    p_scrape.add_argument("--enrich", action="store_true",
                          help="visit websites to fill in missing email/phone")
    p_scrape.add_argument("--no-dedupe", action="store_true", help="disable deduplication")
    p_scrape.add_argument("--config", help="YAML file defining directory sources")
    add_net_opts(p_scrape)
    p_scrape.set_defaults(func=cmd_scrape)

    # enrich
    p_enrich = sub.add_parser("enrich", help="enrich an existing CSV of leads")
    p_enrich.add_argument("infile", help="input CSV file")
    p_enrich.add_argument("--out", help="output CSV (default: overwrite input)")
    add_net_opts(p_enrich)
    p_enrich.set_defaults(func=cmd_enrich)

    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    level = logging.WARNING
    if args.verbose == 1:
        level = logging.INFO
    elif args.verbose >= 2:
        level = logging.DEBUG
    logging.basicConfig(level=level, format="%(levelname)s %(name)s: %(message)s")

    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
