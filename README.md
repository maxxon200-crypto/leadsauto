# leadsauto

A polite, config-driven **lead-scraping toolkit** for finding and collecting
architect (*architetti*) business contacts, enriching them from their websites,
de-duplicating, and exporting to CSV or SQLite.

It is deliberately backend-first and framework-light: a small, tested core
(`Lead` model → source → enrich → dedupe → storage) driven by a simple CLI, with
new directories added through **configuration, not code**.

> **Cerchi lo script PagineGialle?** Vedi [`raccogli.py`](#script-raccoglipy--paginegialle--architetti-italiani)
> più in basso: uno script standalone (solo `requests` / `beautifulsoup4` /
> `pandas`) che raccoglie studi di architettura da PagineGialle su 40 città,
> qualifica i siti (punteggio 1–10) ed estrae le email (scartando le PEC).

```
┌─────────┐   ┌─────────┐   ┌────────┐   ┌────────┐   ┌──────────────┐
│ source  │──▶│ enrich  │──▶│ dedupe │──▶│ store  │──▶│ CSV / SQLite │
│(scrape) │   │(website)│   │(merge) │   │        │   │              │
└─────────┘   └─────────┘   └────────┘   └────────┘   └──────────────┘
```

## Features

- **Config-driven directory scraper** — describe a directory's search URL and
  CSS selectors in YAML; no Python needed to add a new source.
- **Offline `sample` source** — demo/verify the whole pipeline with zero network.
- **Contact enrichment** — visit a lead's website and pull email/phone out of
  the homepage and common contact pages.
- **Smart de-duplication** — merges duplicates by email → website domain →
  normalised name+city, combining partial records into one.
- **Two output formats** — plain CSV or an upserting SQLite table.
- **Good scraping citizenship** — honours `robots.txt`, per-host rate limiting,
  a descriptive User-Agent, and automatic retries with backoff.
- **Tested** — 28 unit tests covering models, enrichment, dedupe, storage, and
  the config-driven scraper.

## Install

Requires Python 3.10+.

```bash
# from the repo root
pip install -e .          # installs the `leadsauto` command
# or, without installing the package:
pip install -r requirements.txt
export PYTHONPATH=src
```

## Quickstart

Run the offline sample end-to-end (no network required):

```bash
# preview to stdout
leadsauto scrape --source sample --query milano

# write results to CSV
leadsauto scrape --source sample --query milano --out leads.csv

# write to SQLite instead (upserts on the dedupe key)
leadsauto scrape --source sample --out leads.sqlite --format sqlite
```

List what sources are available:

```bash
leadsauto list-sources --config config/sources.example.yaml
```

Enrich an existing CSV (fills missing email/phone from each lead's website):

```bash
leadsauto enrich leads.csv --out leads.enriched.csv
```

## Adding a real directory (config-driven)

Most professional directories render results as a repeating HTML block. Point
the built-in `generic_directory` scraper at one by copying the example config
and editing the selectors — **no code changes**:

```bash
cp config/sources.example.yaml config/sources.yaml
# edit config/sources.yaml: base_url, search_url, list_selector, fields
leadsauto scrape --source example_directory --query "Milano" \
    --config config/sources.yaml --out milano.csv --enrich
```

Config shape (see [`config/sources.example.yaml`](config/sources.example.yaml)
for the fully-commented version):

```yaml
sources:
  my_directory:
    type: generic_directory
    base_url: "https://directory.example.it"
    search_url: "https://directory.example.it/architetti?citta={query}&pagina={page}"
    start_page: 1
    max_pages: 5
    list_selector: "div.professional-card"   # one per result
    fields:
      name:    { selector: "h3.pro-name" }
      email:   { selector: "a.pro-email", attr: "href", strip_prefix: "mailto:" }
      phone:   { selector: ".pro-phone" }
      website: { selector: "a.pro-website", attr: "href" }
      city:    { selector: ".pro-city" }
    defaults:
      profession: "Architetto"
      country: "IT"
```

`{query}` is URL-encoded and `{page}` iterates from `start_page`. Scraping stops
early when a page returns no results or `--limit` is reached.

## CLI reference

| Command | What it does |
| --- | --- |
| `leadsauto list-sources [--config F]` | Show built-in and configured sources. |
| `leadsauto scrape --source S [--query Q] [--limit N] [--out F] [--format csv\|sqlite] [--append] [--enrich] [--no-dedupe] [--config F]` | Scrape, optionally enrich/dedupe, and store. |
| `leadsauto enrich FILE [--out F]` | Enrich an existing CSV in place (or to `--out`). |

Global/network flags: `-v/-vv` (verbosity), `--delay` (min seconds between
requests to a host, default `1.0`), `--ignore-robots` (use responsibly).

## Project layout

```
src/leadsauto/
  models.py            Lead dataclass + normalisation
  http.py              polite HTTP client (robots.txt, rate limit, retries)
  enrich.py            email/phone extraction + website enrichment
  dedupe.py            key cascade + merge
  storage.py           CsvStore / SqliteStore
  pipeline.py          scrape → enrich → dedupe → store orchestration
  config.py            YAML config loading
  cli.py               argparse CLI
  sources/
    base.py            Source ABC
    generic_directory.py   config-driven CSS-selector scraper
    sample.py          offline demo source
config/sources.example.yaml
tests/                 pytest suite
```

## Development

```bash
pip install -e ".[dev]"
pytest -q
```

## Using this responsibly (please read)

This tool collects **business** contact information, but architects' details are
often **personal data** under the EU **GDPR**. Before scraping and contacting
anyone:

- **Only scrape sources you are permitted to.** Check each site's Terms of
  Service and `robots.txt` (the client honours `robots.txt` by default — don't
  pass `--ignore-robots` unless you have permission).
- **Have a lawful basis** for processing and for outreach. B2B marketing to EU
  contacts is also subject to ePrivacy rules — unsolicited email may require
  prior consent or a pre-existing relationship depending on the country.
- **Respect opt-outs**, keep data accurate, minimise what you store, and be
  ready to honour access/erasure requests.

You are responsible for how you use scraped data. This project ships with only
fictional sample data and an *example* (non-real) directory config.

---

## Script `raccogli.py` — PagineGialle → architetti italiani

Script **standalone** (indipendente dal package `leadsauto`) che raccoglie lead
di studi di architettura da **PagineGialle** su 40 città italiane, in 3 fasi:

1. **RACCOLTA** — scraping dei risultati per città con paginazione → nome, città,
   telefono, sito.
2. **QUALIFICAZIONE** — punteggio **1–10** del sito (10 = sito pessimo = lead
   migliore): nessun sito → 10; builder (wix/jimdo/altervista/weebly/business.site)
   o sito irraggiungibile → 9; manca `<meta viewport>` → +3; copyright < 2022 → +2;
   `<table>` di layout / `<center>` / `<marquee>` → +2; jQuery o Bootstrap 3 → +1;
   sito moderno/responsive → base 2.
3. **EMAIL** — estrazione dal sito (homepage + `/contatti`, `/contatto`,
   `/contact`, `/chi-siamo`, `/studio`), **scartando le PEC** (`pec.`,
   `@pec.it`, `@legalmail.it`, `@arubapec.it`) e gli indirizzi inutili
   (`noreply@`, `wordpress@`, `esempio@`).

Output: **`lead-architetti.csv`** ordinato per punteggio decrescente
(`nome_studio | citta | email | sito_attuale | punteggio | note`).

Dipendenze: **solo** `requests`, `beautifulsoup4`, `pandas` (parser `html.parser`
di serie — niente `lxml`). Rispetta `time.sleep(2)` tra ogni richiesta, avvolge
**tutto** in `try/except` (non crasha mai a metà), salva un **checkpoint ogni 30
righe** e riprende con `--resume`.

```bash
pip install requests beautifulsoup4 pandas

# 0) ISPEZIONA prima la struttura reale di UNA pagina (non indovinare i selettori)
python raccogli.py --inspect Lucca
#    -> salva inspect_lucca.html, elenca le classi ripetute e prova i selettori.
#    Se PagineGialle ha cambiato markup, adatta SEARCH_URL_TEMPLATES / ITEM_SELECTORS.

# 1) prova la logica OFFLINE (nessuna rete, fixture incluse)
python raccogli.py --self-test

# 2) test su 2 città
python raccogli.py --test            # Lucca, Arezzo

# 3) run completo su tutte e 40 le città
python raccogli.py

python raccogli.py --resume          # riprende dai checkpoint dopo un'interruzione
python raccogli.py --cities Milano Roma
```

> **Nota su PagineGialle e anti-bot.** Il parser non si affida a un singolo
> selettore fisso: prova più selettori candidati e sceglie quello che estrae più
> risultati. PagineGialle può però servire pagine protette da anti-bot a un
> semplice `requests.get`: per questo il primo passo è **`--inspect`**, che ti
> mostra la struttura reale così puoi adattare selettori/URL. Scrapa solo ciò che
> ti è consentito e ricorda che i dati degli architetti sono dati personali (GDPR):
> le PEC sono già escluse perché per legge non vanno usate per fini commerciali.

## License

MIT
