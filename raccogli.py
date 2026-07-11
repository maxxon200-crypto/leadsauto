#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
raccogli.py — Raccolta lead di studi di architettura italiani da PagineGialle.

Dipendenze (SOLO librerie gratuite, come richiesto):
    py -m pip install requests beautifulsoup4 pandas
    (usa il parser 'html.parser' di serie: lxml NON è necessario)

Uso (Prompt dei comandi Windows — usa 'py'; su Mac/Linux usa 'python3'):
    py raccogli.py --inspect Lucca      # PARTE 0: ispeziona l'HTML reale di UNA pagina
    py raccogli.py --self-test          # verifica la logica offline (niente rete)
    py raccogli.py --test               # esegue su 2 città di prova (Lucca, Arezzo)
    py raccogli.py                       # esegue su tutte e 40 le città
    py raccogli.py --cities Milano Roma  # città a scelta
    py raccogli.py --resume              # riprende dai checkpoint esistenti

    I file (lead-architetti.csv, checkpoint, dump --inspect) vengono creati
    nella cartella da cui lanci il comando. Percorsi gestiti con pathlib,
    quindi funzionano identici su Windows e Unix.

Lo script fa 3 cose in sequenza:
    PARTE 1 — RACCOLTA:       scraping dei risultati PagineGialle per città (con paginazione).
    PARTE 2 — QUALIFICAZIONE: punteggio 1-10 del sito (10 = sito pessimo / lead migliore).
    PARTE 3 — EMAIL:          estrazione email dal sito, scartando PEC e indirizzi inutili.

Output: lead-architetti.csv  ordinato per punteggio decrescente.
        Colonne: nome_studio | citta | email | sito_attuale | punteggio | note

Regole tecniche rispettate:
    - solo requests / beautifulsoup4 / pandas (parser 'html.parser' di serie)
    - time.sleep(2) tra ogni richiesta di rete
    - try/except su TUTTO: una pagina che fallisce scrive "errore" e si prosegue
    - checkpoint CSV ogni 30 righe (ripartenza automatica)
    - avanzamento stampato a schermo

NOTA IMPORTANTE SULLA STRUTTURA HTML:
    PagineGialle cambia spesso il markup e talvolta protegge le pagine con
    anti-bot. Per questo il parser NON si affida a un singolo selettore fisso:
    prova una lista di selettori candidati e sceglie quello che estrae più
    risultati. Esegui prima `--inspect` per vedere la struttura reale e, se
    serve, adatta SEARCH_URL_TEMPLATES / ITEM_SELECTORS / i selettori dei campi.
"""

from __future__ import annotations

import argparse
import re
import sys
import time
from pathlib import Path
from urllib.parse import quote, urljoin, urlparse

import pandas as pd
import requests
from bs4 import BeautifulSoup

# --------------------------------------------------------------------------- #
# CONFIGURAZIONE
# --------------------------------------------------------------------------- #

CITTA_TUTTE = [
    "Milano", "Torino", "Genova", "Bologna", "Firenze", "Roma", "Napoli",
    "Bari", "Palermo", "Verona", "Padova", "Venezia", "Brescia", "Bergamo",
    "Parma", "Modena", "Rimini", "Perugia", "Pisa", "Siena", "Lucca",
    "Ancona", "Pescara", "Cagliari", "Catania", "Trento", "Bolzano", "Udine",
    "Trieste", "Como", "Varese", "Vicenza", "Treviso", "Ferrara", "Ravenna",
    "Reggio Emilia", "Livorno", "Arezzo", "Salerno", "Lecce",
]
CITTA_TEST = ["Lucca", "Arezzo"]

# Header "da browser" per non essere scambiati per un bot banale.
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;q=0.9,"
        "image/avif,image/webp,*/*;q=0.8"
    ),
    "Accept-Language": "it-IT,it;q=0.9,en;q=0.8",
}

SLEEP_SECONDS = 2          # pausa tra ogni richiesta di rete
REQUEST_TIMEOUT = 15       # timeout raccolta pagine PagineGialle
SITE_TIMEOUT = 10          # timeout richiesto per i siti degli studi
MAX_PAGES = 10             # tetto di sicurezza alla paginazione per città
CHECKPOINT_EVERY = 30      # ogni quante righe salvare il checkpoint

# File di output/ripresa: sempre pathlib.Path (mai stringhe con "/"), relativi
# alla cartella da cui lanci lo script. Funzionano identici su Windows e Unix.
OUTPUT_DIR = Path.cwd()
OUTPUT_FILE = OUTPUT_DIR / "lead-architetti.csv"
CHECKPOINT_FILE = OUTPUT_DIR / "checkpoint.csv"       # righe qualificate (PARTE 2/3) — ripresa
RACCOLTA_FILE = OUTPUT_DIR / "studi_raccolti.csv"     # output grezzo PARTE 1 — ripresa

# Template URL di ricerca. Vengono provati in ordine: si usa il primo che
# restituisce risultati parsabili. `{q}` = query, `{slug}` = città, `{page}`.
SEARCH_URL_TEMPLATES = [
    "https://www.paginegialle.it/ricerca/{q}/{slug}{page}",
    "https://www.paginegialle.it/ricerca/architetti/{slug}{page}",
]
SEARCH_QUERY = "studi di architettura"

# Selettori candidati per il BLOCCO di ogni risultato (provati in ordine,
# vince quello che trova più blocchi). PagineGialle ha usato nel tempo:
# .search-itm, .vcard, .list-element, itemtype LocalBusiness, ecc.
ITEM_SELECTORS = [
    "div.search-itm",
    "div.vcard",
    "article.search-itm",
    "div.list-element",
    "[itemtype*='LocalBusiness']",
    "div[class*='search-itm']",
    "div[class*='listing']",
    "li[class*='item']",
    "article[class*='item']",
]

# Selettori candidati per i singoli campi dentro ogni blocco.
NAME_SELECTORS = [
    ".search-itm__rag-soc", "[itemprop='name']", "h2.search-itm__rag-soc",
    "h2 a", "h2", "h3 a", "h3", ".item-title", ".fn", ".company-name",
    "a[title]",
]
PHONE_SELECTORS = [
    "[href^='tel:']", "[itemprop='telephone']", ".search-itm__phone",
    ".tel", ".phone", "span[class*='phone']",
]
WEBSITE_SELECTORS = [
    "a.search-itm__link-web", "a[class*='web']", "[itemprop='url']",
    "a[href^='http']",
]

# Piattaforme "builder" -> segnale forte di sito debole (punteggio alto).
BUILDERS = [
    "wix.com", "wixsite.com", "jimdo.com", "jimdofree.com", "altervista.org",
    "weebly.com", "business.site", "myportfolio.com", "webnode",
    "flazio.com", "webmecanik", "1and1", "ionos.", "wordpress.com",
]

# Pagine "contatti" da provare se l'email non è in homepage
# (esattamente quelle richieste). "" = homepage, già scaricata e riusata.
CONTACT_PATHS = [
    "", "/contatti", "/contatto", "/contact", "/chi-siamo", "/studio",
]

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,24}")
PHONE_TEXT_RE = re.compile(r"(?:\+?39[\s.\-]?)?(?:0\d{1,3}|3\d{2})[\s./\-]?\d[\d\s./\-]{4,10}\d")
# Marcatore di copyright + finestra in cui cercare gli anni (gestisce i range).
COPYRIGHT_MARKER_RE = re.compile(r"(?:©|&copy;|&#169;|copyright|copyr\.)", re.IGNORECASE)
YEAR_TOKEN_RE = re.compile(r"(?:19|20)\d{2}")

# Modalità fixture (self-test): se valorizzato, get_html() serve da qui e NON
# tocca la rete né dorme. url -> html.
_FIXTURES: dict[str, str] | None = None


# --------------------------------------------------------------------------- #
# RETE — un solo punto di accesso, con sleep e gestione errori
# --------------------------------------------------------------------------- #

def get_html(url: str, timeout: int = REQUEST_TIMEOUT) -> str | None:
    """Scarica una URL e restituisce l'HTML, oppure None in caso di errore.

    - rispetta la modalità fixture (self-test) senza toccare la rete
    - dorme SLEEP_SECONDS dopo ogni richiesta reale (anti-ban)
    - non solleva MAI: qualunque problema -> None
    """
    if _FIXTURES is not None:
        return _FIXTURES.get(url)

    try:
        resp = requests.get(url, headers=HEADERS, timeout=timeout)
        status = resp.status_code
        # Segnala (ma non blocca) possibili pagine anti-bot.
        if status != 200:
            print(f"    [http {status}] {url}")
            return None
        # Migliora la decodifica (evita mojibake su accenti/email italiane).
        if not resp.encoding or resp.encoding.lower() == "iso-8859-1":
            resp.encoding = resp.apparent_encoding or resp.encoding
        text = resp.text
        low = text.lower()
        if any(m in low for m in ("_incapsula_resource", "captcha", "are you a human",
                                  "px-captcha", "access denied")):
            print(f"    [possibile anti-bot / captcha] {url}")
        return text
    except Exception as exc:  # noqa: BLE001 — vogliamo davvero catturare tutto
        print(f"    [errore rete] {type(exc).__name__}: {url}")
        return None
    finally:
        if _FIXTURES is None:
            time.sleep(SLEEP_SECONDS)


# --------------------------------------------------------------------------- #
# PARTE 0 — ISPEZIONE (guarda la struttura reale, non indovinare)
# --------------------------------------------------------------------------- #

def inspect_city(citta: str) -> None:
    """Scarica UNA pagina di esempio, salva l'HTML e analizza la struttura."""
    print(f"=== ISPEZIONE — {citta} ===")
    for tmpl in SEARCH_URL_TEMPLATES:
        url = build_search_url(tmpl, citta, page=1)
        print(f"\n--- provo: {url}")
        html = get_html(url)
        if not html:
            print("    nessuna risposta utile (vedi messaggio sopra).")
            continue

        fpath = OUTPUT_DIR / f"inspect_{slugify(citta)}.html"
        try:
            fpath.write_text(html, encoding="utf-8")
            print(f"    HTML salvato in {fpath} ({len(html)} caratteri)")
        except Exception as exc:  # noqa: BLE001
            print(f"    (impossibile salvare l'HTML: {exc})")

        soup = BeautifulSoup(html, "html.parser")

        # Anteprima leggibile dell'inizio del <body>.
        title = soup.title.get_text(strip=True) if soup.title else "(nessun <title>)"
        print(f"    <title>: {title}")

        # Auto-individuazione dei blocchi ripetuti: conta le classi dei <div>/<article>/<li>.
        print("    Classi più ripetute (candidati per il blocco risultato):")
        for cls, n in _frequent_block_classes(soup)[:12]:
            print(f"      {n:>3}×  .{cls}")

        # Quanto rende ciascun ITEM_SELECTOR conosciuto.
        print("    Risultati per selettore candidato:")
        best = None
        for sel in ITEM_SELECTORS:
            try:
                found = soup.select(sel)
            except Exception:  # selettore non valido su questo parser
                continue
            if found:
                print(f"      {len(found):>3}×  {sel}")
                if best is None:
                    best = (sel, found)
        if best:
            sel, found = best
            print(f"\n    Selettore scelto: {sel} -> {len(found)} blocchi. Primo blocco parsato:")
            rec = parse_item(found[0], base_url=url)
            for k, v in rec.items():
                print(f"      {k:12}: {v!r}")
        else:
            print("\n    NESSUN selettore candidato ha trovato blocchi.")
            print("    Apri il file HTML salvato, individua il contenitore dei risultati")
            print("    e aggiungi il suo selettore in ITEM_SELECTORS.")
        return  # ci basta il primo template che risponde
    print("\nNessun template ha restituito HTML. Il sito potrebbe essere bloccato/anti-bot.")


def _frequent_block_classes(soup: BeautifulSoup) -> list[tuple[str, int]]:
    counts: dict[str, int] = {}
    for tag in soup.find_all(["div", "article", "li", "section"]):
        for cls in (tag.get("class") or []):
            counts[cls] = counts.get(cls, 0) + 1
    return sorted(counts.items(), key=lambda kv: kv[1], reverse=True)


# --------------------------------------------------------------------------- #
# PARTE 1 — RACCOLTA
# --------------------------------------------------------------------------- #

def slugify(citta: str) -> str:
    return citta.strip().lower().replace(" ", "-")


def build_search_url(template: str, citta: str, page: int) -> str:
    page_part = "" if page <= 1 else f"/p-{page}"
    return template.format(
        q=quote(SEARCH_QUERY),
        slug=quote(slugify(citta)),
        page=page_part,
    )


def _select_first_text(block, selectors: list[str]) -> str:
    for sel in selectors:
        try:
            node = block.select_one(sel)
        except Exception:
            continue
        if node is None:
            continue
        txt = node.get_text(" ", strip=True)
        if txt:
            return txt
    return ""


def _select_phone(block) -> str:
    # 1) link tel:  2) selettori testuali  3) regex sul testo del blocco
    for sel in PHONE_SELECTORS:
        try:
            node = block.select_one(sel)
        except Exception:
            continue
        if node is None:
            continue
        href = node.get("href", "") if hasattr(node, "get") else ""
        if href.startswith("tel:"):
            return href[4:].strip()
        txt = node.get_text(" ", strip=True)
        if txt:
            return txt
    m = PHONE_TEXT_RE.search(block.get_text(" ", strip=True))
    return m.group(0).strip() if m else ""


def _select_website(block, base_url: str) -> str:
    # Cerca un link esterno che NON sia PagineGialle/social/mailto/tel.
    bad = ("paginegialle", "facebook.", "instagram.", "twitter.", "x.com",
           "linkedin.", "youtube.", "tripadvisor", "google.", "wa.me",
           "whatsapp", "tel:", "mailto:")
    candidates = []
    for sel in WEBSITE_SELECTORS:
        try:
            nodes = block.select(sel)
        except Exception:
            continue
        for node in nodes:
            href = (node.get("href") or "").strip()
            if not href:
                continue
            low = href.lower()
            if low.startswith(("tel:", "mailto:", "#", "javascript:")):
                continue
            if any(b in low for b in bad):
                continue
            if href.startswith("//"):
                href = "https:" + href
            elif href.startswith("/"):
                href = urljoin(base_url, href)
            if href.startswith("http"):
                candidates.append(href)
    return candidates[0] if candidates else ""


def parse_item(block, base_url: str) -> dict:
    """Estrae nome / telefono / sito da un singolo blocco risultato."""
    return {
        "nome": _select_first_text(block, NAME_SELECTORS),
        "telefono": _select_phone(block),
        "sito": _select_website(block, base_url),
    }


def parse_listing(html: str, base_url: str) -> list[dict]:
    """Trova i blocchi risultato con il selettore migliore e li estrae."""
    soup = BeautifulSoup(html, "html.parser")
    best: list = []
    for sel in ITEM_SELECTORS:
        try:
            found = soup.select(sel)
        except Exception:
            continue
        if len(found) > len(best):
            best = found
    records = []
    for block in best:
        try:
            rec = parse_item(block, base_url)
        except Exception:
            continue
        if rec["nome"]:  # scarta blocchi senza nome (banner, ecc.)
            records.append(rec)
    return records


def scrape_citta(citta: str) -> list[dict]:
    """PARTE 1: raccoglie tutti gli studi di una città gestendo la paginazione."""
    print(f"  [raccolta] {citta} ...")
    # Sceglie il primo template che produce risultati in pagina 1.
    template = None
    first_page: list[dict] = []
    for tmpl in SEARCH_URL_TEMPLATES:
        url = build_search_url(tmpl, citta, page=1)
        html = get_html(url)
        if not html:
            continue
        recs = parse_listing(html, url)
        if recs:
            template, first_page = tmpl, recs
            break
    if template is None:
        print(f"    nessun risultato per {citta} (URL/selettori da adattare o sito bloccato)")
        return []

    risultati: list[dict] = []
    visti: set[str] = set()

    def _aggiungi(recs: list[dict], page: int) -> int:
        nuovi = 0
        for r in recs:
            chiave = (r["nome"].lower().strip(), r.get("telefono", ""))
            k = "|".join(chiave)
            if k in visti:
                continue
            visti.add(k)
            r["citta"] = citta
            risultati.append(r)
            nuovi += 1
        print(f"    pagina {page}: {len(recs)} blocchi, {nuovi} nuovi (tot {len(risultati)})")
        return nuovi

    _aggiungi(first_page, 1)

    for page in range(2, MAX_PAGES + 1):
        url = build_search_url(template, citta, page=page)
        html = get_html(url)
        if not html:
            break
        recs = parse_listing(html, url)
        if not recs:
            break
        nuovi = _aggiungi(recs, page)
        if nuovi == 0:  # pagina duplicata -> fine paginazione
            break

    print(f"    -> {len(risultati)} studi raccolti per {citta}")
    return risultati


# --------------------------------------------------------------------------- #
# PARTE 2 — QUALIFICAZIONE (punteggio 1-10, 10 = sito pessimo)
# --------------------------------------------------------------------------- #

def _has_layout_table(soup: BeautifulSoup) -> bool:
    """True se il markup usa tecniche di layout "vecchia scuola".

    <center>/<marquee> sono segnali diretti. Per le <table> NON basta l'assenza
    di <th> (una tabella-dati moderna può non averlo): richiediamo indizi di
    layout — attributi width/border/cellpadding/align/bgcolor, role=presentation
    o tabelle annidate — così una tabella dati legittima non fa falso positivo.
    """
    if soup.find("center") or soup.find("marquee"):
        return True
    for table in soup.find_all("table"):
        if table.get("role", "").lower() == "presentation":
            return True
        if any(table.get(attr) for attr in
               ("width", "border", "cellpadding", "cellspacing", "bgcolor", "background")):
            # una tabella con questi attributi e senza intestazioni = layout
            if table.find("th") is None:
                return True
        if table.find("table") is not None:  # tabelle annidate = layout
            return True
    return False


def _old_copyright(text: str) -> int | None:
    """Ritorna l'anno di copyright PIÙ RECENTE trovato vicino a un marcatore.

    Cerca gli anni in una finestra dopo ogni "©/copyright" così da catturare
    anche i range ("© 2010-2023" -> 2023) ed evitare di penalizzare un sito
    aggiornato solo perché il range parte da un anno vecchio.
    """
    anni: list[int] = []
    for m in COPYRIGHT_MARKER_RE.finditer(text):
        finestra = text[m.end(): m.end() + 25]
        for ym in YEAR_TOKEN_RE.finditer(finestra):
            y = int(ym.group(0))
            if 1990 <= y <= 2035:
                anni.append(y)
    return max(anni) if anni else None


def qualifica_sito(sito: str) -> tuple[int, str]:
    """PARTE 2: assegna punteggio 1-10 al sito (scarica e delega). Non solleva mai.

    La logica di punteggio vive in _qualifica_da_html(): questa funzione si
    limita a scaricare l'HTML, così esiste UNA sola implementazione del calcolo.
    """
    if not sito:
        return 10, "nessun sito web"
    html = get_html(sito, timeout=SITE_TIMEOUT)
    if html is None:
        return 9, "sito irraggiungibile/errore"
    return _qualifica_da_html(sito, html)


# --------------------------------------------------------------------------- #
# PARTE 3 — EMAIL (scarta PEC e indirizzi inutili)
# --------------------------------------------------------------------------- #

PEC_PROVIDERS = ("legalmail.it", "arubapec.it", "pec.it", "postecert.it",
                 "sicurezzapostale.it", "pec.aruba.it", "ingpec.eu",
                 "pec.giovanni.it", "cert.legalmail.it")
# Local-part "placeholder/tecnici" da scartare (match esatto o come prefisso).
# Volutamente conservativo: NON includo "email"/"test" per non scartare indirizzi
# studio legittimi (es. "email@studio.it" usato letteralmente).
JUNK_LOCAL = ("noreply", "no-reply", "wordpress", "esempio", "example",
              "your", "sentry", "wixpress", "mailer-daemon", "postmaster",
              "abuse", "hostmaster")
# Domini "tecnici" (monitoring/builder/placeholder) da scartare.
JUNK_DOMAINS = ("sentry.io", "wixpress.com", "example.com", "example.org",
                "godaddy.com", "sentry-next.wixpress.com")


def is_pec(email: str) -> bool:
    """True se è una casella PEC (per legge non usabile per marketing)."""
    e = email.lower().strip()
    if "@" not in e:
        return True
    dominio = e.split("@", 1)[1]
    if dominio.startswith("pec.") or ".pec." in dominio:
        return True
    if any(dominio == p or dominio.endswith("." + p) or dominio == p for p in PEC_PROVIDERS):
        return True
    if "legalmail" in dominio or "arubapec" in dominio:
        return True
    return False


def is_junk(email: str) -> bool:
    e = email.lower().strip()
    if "@" not in e:
        return True
    local, dominio = e.split("@", 1)
    if any(local == j or local.startswith(j) for j in JUNK_LOCAL):
        return True
    if any(dominio == d or dominio.endswith("." + d) for d in JUNK_DOMAINS):
        return True
    # scarta "email" che sono in realtà nomi di file/asset (es. logo@2x.png)
    if any(e.endswith(ext) for ext in (".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg")):
        return True
    return False


def _emails_from_html(html: str) -> list[str]:
    """Estrae email da mailto: e dal TESTO VISIBILE, già filtrate PEC/junk.

    La regex gira sul testo visibile (non sui <script>/<style>): questo evita
    di catturare come "email" chiavi di analytics/monitoring tipo i DSN Sentri
    (es. abc@o123.ingest.sentry.io) incastonate nel JavaScript.
    """
    trovate: list[str] = []
    testo = html  # fallback se il parsing fallisce
    try:
        soup = BeautifulSoup(html, "html.parser")
        # 1) link mailto: (fonte più pulita, hanno priorità)
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if href.lower().startswith("mailto:"):
                addr = href[7:].split("?")[0].strip()
                if addr:
                    trovate.append(addr)
        # 2) rimuovi script/style, poi prendi il testo visibile
        for tag in soup(["script", "style", "noscript"]):
            tag.decompose()
        testo = soup.get_text(" ")
    except Exception:
        pass

    # 3) regex sul testo visibile
    trovate.extend(EMAIL_RE.findall(testo))
    # 4) semplice deoffuscamento "nome (at) dominio (dot) it" sul testo
    deoff = re.sub(r"\s*[\(\[]?\s*(?:at|chiocciola)\s*[\)\]]?\s*", "@",
                   testo, flags=re.IGNORECASE)
    deoff = re.sub(r"\s*[\(\[]?\s*(?:dot|punto)\s*[\)\]]?\s*", ".", deoff, flags=re.IGNORECASE)
    trovate.extend(EMAIL_RE.findall(deoff))

    pulite: list[str] = []
    for e in trovate:
        e = e.strip().strip(".,;:").lower()
        if not e or e in pulite:
            continue
        if is_pec(e) or is_junk(e):
            continue
        pulite.append(e)
    return pulite


def trova_email(sito: str, homepage_html: str | None = None) -> str:
    """PARTE 3: cerca l'email sul sito (homepage + pagine contatti). Non solleva mai."""
    if not sito:
        return ""

    # Homepage (riusa l'HTML già scaricato in PARTE 2 se disponibile).
    if homepage_html is None:
        homepage_html = get_html(sito, timeout=SITE_TIMEOUT)
    if homepage_html:
        emails = _emails_from_html(homepage_html)
        if emails:
            return emails[0]

    # Pagine contatti candidate.
    base = sito.rstrip("/")
    provate = {base}
    for path in CONTACT_PATHS:
        if not path:
            continue
        url = base + path
        if url in provate:
            continue
        provate.add(url)
        html = get_html(url, timeout=SITE_TIMEOUT)
        if not html:
            continue
        emails = _emails_from_html(html)
        if emails:
            return emails[0]
    return ""


# --------------------------------------------------------------------------- #
# CHECKPOINT / RIPRESA
# --------------------------------------------------------------------------- #

COLS = ["nome_studio", "citta", "email", "sito_attuale", "punteggio", "note"]


def _row_key(nome: str, citta: str, sito: str) -> str:
    """Chiave di ripresa. Include il sito per non far collidere due studi
    con lo stesso nome nella stessa città (che andrebbero altrimenti persi)."""
    return f"{(nome or '').strip().lower()}|{(citta or '').strip().lower()}|{(sito or '').strip().lower()}"


def _save_csv(rows: list[dict], path: Path) -> None:
    try:
        pd.DataFrame(rows, columns=COLS).to_csv(
            path, index=False, encoding="utf-8-sig"
        )
    except Exception as exc:  # noqa: BLE001
        print(f"    [attenzione] impossibile salvare {path}: {exc}")


def _load_done_keys(path: Path) -> tuple[list[dict], set[str]]:
    """Carica le righe già qualificate dal checkpoint per la ripresa."""
    if not Path(path).exists():
        return [], set()
    try:
        df = pd.read_csv(path, encoding="utf-8-sig", dtype=str).fillna("")
        rows = df.to_dict("records")
        keys = {_row_key(r.get("nome_studio", ""), r.get("citta", ""),
                         r.get("sito_attuale", "")) for r in rows}
        print(f"  ripresa: {len(rows)} righe già presenti in {path}")
        return rows, keys
    except Exception as exc:  # noqa: BLE001
        print(f"  [attenzione] checkpoint illeggibile ({exc}); riparto da zero")
        return [], set()


# --------------------------------------------------------------------------- #
# ORCHESTRAZIONE
# --------------------------------------------------------------------------- #

def raccolta_grezza(citta_list: list[str], use_cache: bool) -> list[dict]:
    """PARTE 1 completa, con cache su RACCOLTA_FILE per la ripresa."""
    if use_cache and RACCOLTA_FILE.exists():
        try:
            df = pd.read_csv(RACCOLTA_FILE, encoding="utf-8-sig", dtype=str).fillna("")
            studi = df.to_dict("records")
            print(f"PARTE 1: uso raccolta esistente {RACCOLTA_FILE} ({len(studi)} studi)")
            return studi
        except Exception as exc:  # noqa: BLE001
            print(f"  [attenzione] {RACCOLTA_FILE} illeggibile ({exc}); riparto la raccolta")

    print(f"PARTE 1 — RACCOLTA su {len(citta_list)} città")
    studi: list[dict] = []
    for i, citta in enumerate(citta_list, 1):
        print(f"[{i}/{len(citta_list)}] {citta}")
        try:
            studi.extend(scrape_citta(citta))
        except Exception as exc:  # noqa: BLE001 — non deve MAI crashare
            print(f"    [errore città {citta}] {type(exc).__name__}: {exc}")
        # salvataggio incrementale della raccolta grezza
        try:
            pd.DataFrame(studi).to_csv(RACCOLTA_FILE, index=False, encoding="utf-8-sig")
        except Exception:
            pass
    print(f"PARTE 1 completata: {len(studi)} studi totali\n")
    return studi


def qualifica_e_email(studi: list[dict]) -> list[dict]:
    """PARTE 2 + PARTE 3 con checkpoint ogni CHECKPOINT_EVERY righe."""
    print("PARTE 2+3 — QUALIFICAZIONE ed EMAIL")
    rows, done = _load_done_keys(CHECKPOINT_FILE)

    processate_da_ultimo_salvataggio = 0
    try:
        for i, studio in enumerate(studi, 1):
            nome = (studio.get("nome") or studio.get("nome_studio") or "").strip()
            citta = (studio.get("citta") or "").strip()
            sito = (studio.get("sito") or studio.get("sito_attuale") or "").strip()
            key = _row_key(nome, citta, sito)
            if key in done:
                continue

            print(f"  [{i}/{len(studi)}] {nome} ({citta})")
            try:
                # PARTE 2 — punteggio (riusa l'HTML della homepage per la PARTE 3)
                homepage_html = get_html(sito, timeout=SITE_TIMEOUT) if sito else None
                if not sito:
                    punteggio, note = 10, "nessun sito web"
                elif homepage_html is None:
                    punteggio, note = 9, "sito irraggiungibile/errore"
                else:
                    punteggio, note = _qualifica_da_html(sito, homepage_html)
                # PARTE 3 — email
                email = trova_email(sito, homepage_html) if sito else ""
            except Exception as exc:  # noqa: BLE001 — mai crashare a metà
                punteggio, note, email = 0, f"errore: {type(exc).__name__}", ""
                print(f"      [errore studio] {exc}")

            rows.append({
                "nome_studio": nome,
                "citta": citta,
                "email": email,
                "sito_attuale": sito,
                "punteggio": punteggio,
                "note": note,
            })
            done.add(key)
            processate_da_ultimo_salvataggio += 1
            print(f"      punteggio={punteggio}  email={email or '—'}  ({note})")

            if processate_da_ultimo_salvataggio >= CHECKPOINT_EVERY:
                _save_csv(rows, CHECKPOINT_FILE)
                print(f"  >> checkpoint salvato ({len(rows)} righe)")
                processate_da_ultimo_salvataggio = 0
    except KeyboardInterrupt:
        # Interruzione manuale: salva comunque quanto fatto per poter riprendere.
        print("\n  interruzione: salvo il checkpoint prima di uscire...")
        _save_csv(rows, CHECKPOINT_FILE)
        raise

    _save_csv(rows, CHECKPOINT_FILE)
    return rows


def _qualifica_da_html(sito: str, html: str) -> tuple[int, str]:
    """Come qualifica_sito() ma su HTML già scaricato (evita doppia richiesta)."""
    note: list[str] = []
    dominio = (urlparse(sito).netloc or sito).lower()
    low = html.lower()

    builder = next((b for b in BUILDERS if b in dominio or b in low), None)
    score = 9 if builder else 2
    if builder:
        note.append(f"builder ({builder})")

    try:
        soup = BeautifulSoup(html, "html.parser")
    except Exception:
        return 9, "sito illeggibile"

    if soup.find("meta", attrs={"name": re.compile("^viewport$", re.I)}) is None:
        score += 3
        note.append("no viewport (non responsive)")
    anno = _old_copyright(soup.get_text(" ", strip=True))
    if anno is not None and anno < 2022:
        score += 2
        note.append(f"copyright {anno}")
    if _has_layout_table(soup):
        score += 2
        note.append("layout table/center/marquee")
    if "jquery" in low or "bootstrap-3" in low or "bootstrap/3" in low \
            or "col-xs-" in low or "panel-default" in low:
        score += 1
        note.append("jquery/bootstrap3")

    score = max(1, min(10, score))
    if not note:
        note.append("sito moderno/responsive")
    return score, "; ".join(note)


def scrivi_output(rows: list[dict]) -> None:
    """Ordina per punteggio decrescente e salva l'output finale."""
    if not rows:
        print("Nessuna riga da salvare.")
        _save_csv([], OUTPUT_FILE)
        return
    df = pd.DataFrame(rows, columns=COLS)
    df["punteggio"] = pd.to_numeric(df["punteggio"], errors="coerce").fillna(0).astype(int)
    df = df.sort_values("punteggio", ascending=False, kind="stable").reset_index(drop=True)
    df.to_csv(OUTPUT_FILE, index=False, encoding="utf-8-sig")
    print(f"\n✓ Output salvato: {OUTPUT_FILE} ({len(df)} righe)")
    print("\n=== PRIME 10 RIGHE ===")
    with pd.option_context("display.max_colwidth", 40, "display.width", 200):
        print(df.head(10).to_string(index=False))


def esegui(citta_list: list[str], use_cache: bool = True) -> None:
    studi = raccolta_grezza(citta_list, use_cache=use_cache)
    rows = qualifica_e_email(studi)
    scrivi_output(rows)


# --------------------------------------------------------------------------- #
# SELF-TEST OFFLINE (prova la logica senza rete, con fixture realistiche)
# --------------------------------------------------------------------------- #

def _fixtures() -> dict[str, str]:
    """HTML finti ma realistici: 1 pagina PagineGialle + 3 siti studio."""
    pg = """
    <html><head><title>Studi di architettura a Lucca | PagineGialle</title></head>
    <body>
      <div class="search-itm" itemtype="http://schema.org/LocalBusiness">
        <h2 class="search-itm__rag-soc" itemprop="name">Studio Rossi Architetti</h2>
        <a class="search-itm__phone" href="tel:+390583111222">0583 111222</a>
        <a class="search-itm__link-web" href="https://studiorossi-vecchio.example">Sito</a>
      </div>
      <div class="search-itm">
        <h2 class="search-itm__rag-soc" itemprop="name">Bianchi Design Studio</h2>
        <a class="search-itm__phone" href="tel:0583999888">0583 999888</a>
        <a class="search-itm__link-web" href="https://bianchidesign.example">Sito web</a>
      </div>
      <div class="search-itm">
        <h2 class="search-itm__rag-soc" itemprop="name">Arch. Verdi Maria</h2>
        <a class="search-itm__phone" href="tel:0583555444">0583 555444</a>
      </div>
      <div class="search-itm">
        <h2 class="search-itm__rag-soc" itemprop="name">Neri Studio (Wix)</h2>
        <a class="search-itm__link-web" href="https://neristudio.wixsite.com/home">Sito</a>
      </div>
    </body></html>
    """
    # Sito 1: vecchio, non responsive, tabellare, copyright 2015, jquery -> punteggio alto
    sito_vecchio = """
    <html><head><title>Studio Rossi</title>
      <script src="/js/jquery-1.11.min.js"></script></head>
    <body><center><table><tr><td>
      <h1>Studio Rossi Architetti</h1>
      Email: <a href="mailto:info@studiorossi.example">info@studiorossi.example</a><br>
      PEC: studiorossi@pec.it
      </td></tr></table></center>
      <footer>© 2015 Studio Rossi</footer>
    </body></html>
    """
    # Sito 2: moderno, responsive, mail in pagina contatti -> punteggio basso
    sito_moderno = """
    <html><head><title>Bianchi Design</title>
      <meta name="viewport" content="width=device-width, initial-scale=1"></head>
    <body><h1>Bianchi Design Studio</h1>
      <p>Scrivici dalla pagina contatti.</p>
    </body></html>
    """
    sito_moderno_contatti = """
    <html><head><meta name="viewport" content="width=device-width, initial-scale=1"></head>
    <body>Contatti: <a href="mailto:studio@bianchidesign.example">studio@bianchidesign.example</a>
      — PEC (da scartare): bianchi@legalmail.it
    </body></html>
    """
    base = "https://www.paginegialle.it/ricerca/studi%20di%20architettura/lucca"
    return {
        base: pg,
        "https://studiorossi-vecchio.example": sito_vecchio,
        "https://bianchidesign.example": sito_moderno,
        "https://bianchidesign.example/contatti": sito_moderno_contatti,
        # neristudio.wixsite.com e il sito senza web -> irraggiungibili (assenti)
    }


def _unit_checks() -> None:
    """Controlli mirati sulle funzioni pure (coprono i casi limite corretti)."""
    # --- PEC: scarta le vere PEC, NON i domini simili (spec.it, aspec.it) ---
    assert is_pec("studio@pec.it")
    assert is_pec("nome@arubapec.it")
    assert is_pec("x@legalmail.it")
    assert is_pec("y@pec.aruba.it")
    assert is_pec("z@pec.mystudio.it")          # sottodominio PEC
    assert not is_pec("info@spec.it"), "falso positivo: spec.it non è PEC"
    assert not is_pec("info@aspec.it"), "falso positivo: aspec.it non è PEC"
    assert not is_pec("info@studiopec.it"), "falso positivo: studiopec.it non è PEC"

    # --- junk: scarta placeholder/monitoring, NON indirizzi reali ---
    assert is_junk("noreply@studio.it")
    assert is_junk("wordpress@studio.it")
    assert is_junk("esempio@studio.it")
    assert is_junk("abc@o123.ingest.sentry.io"), "DSN Sentry non scartato"
    assert not is_junk("info@studio.it")
    assert not is_junk("email@studio.it"), "email@ reale non deve essere scartata"

    # --- copyright: range con anno finale recente NON è 'vecchio' ---
    assert _old_copyright("© 2015 Studio") == 2015
    assert _old_copyright("© 2010-2023 Studio") == 2023, "range: deve vincere 2023"
    assert _old_copyright("Copyright 2019, tutti i diritti") == 2019
    assert _old_copyright("&copy;2018") == 2018
    assert _old_copyright("nessun anno qui") is None

    # --- layout table: <table> dati (con <th>) NON è layout; con attributi sì ---
    from bs4 import BeautifulSoup as BS
    tabella_dati = BS("<table><tr><th>Orario</th></tr><tr><td>9-18</td></tr></table>", "html.parser")
    assert not _has_layout_table(tabella_dati), "falso positivo su tabella dati"
    tabella_layout = BS("<table width='100%' border='0'><tr><td>x</td></tr></table>", "html.parser")
    assert _has_layout_table(tabella_layout), "layout table non rilevata"
    assert _has_layout_table(BS("<center>x</center>", "html.parser"))

    # --- email da HTML: ignora i <script>, prende il mailto ---
    html = ('<html><head><script>var dsn="https://k@o1.ingest.sentry.io/2";</script></head>'
            '<body><a href="mailto:info@studio.it">scrivici</a></body></html>')
    emails = _emails_from_html(html)
    assert emails and emails[0] == "info@studio.it", emails
    assert all("sentry" not in e for e in emails), "DSN estratta come email"

    print("  unit-check funzioni pure: OK")


def self_test() -> int:
    """Esegue l'intera pipeline su fixture offline e verifica i risultati."""
    global _FIXTURES
    print("=== SELF-TEST OFFLINE (nessuna rete) ===\n")
    _FIXTURES = _fixtures()
    try:
        _unit_checks()
        studi = scrape_citta("Lucca")
        assert len(studi) == 4, f"attesi 4 studi, trovati {len(studi)}"
        nomi = {s["nome"] for s in studi}
        assert "Studio Rossi Architetti" in nomi, nomi
        assert any(s["telefono"] for s in studi), "nessun telefono estratto"

        rows = qualifica_e_email(studi)
        by_name = {r["nome_studio"]: r for r in rows}

        rossi = by_name["Studio Rossi Architetti"]
        assert rossi["email"] == "info@studiorossi.example", rossi["email"]
        assert rossi["punteggio"] >= 8, f"Rossi doveva avere punteggio alto: {rossi}"

        bianchi = by_name["Bianchi Design Studio"]
        assert bianchi["email"] == "studio@bianchidesign.example", bianchi["email"]
        assert bianchi["punteggio"] <= 3, f"Bianchi (moderno) punteggio basso atteso: {bianchi}"

        verdi = by_name["Arch. Verdi Maria"]
        assert verdi["punteggio"] == 10, f"Verdi (senza sito) = 10 atteso: {verdi}"

        neri = by_name["Neri Studio (Wix)"]
        # wixsite irraggiungibile nelle fixture -> 9 (irraggiungibile)
        assert neri["punteggio"] == 9, f"Neri (wix/irraggiungibile) = 9 atteso: {neri}"

        # PEC scartate ovunque
        assert all("pec" not in (r["email"] or "") for r in rows), "una PEC è passata!"
        assert all("legalmail" not in (r["email"] or "") for r in rows)

        print("\nTutti i controlli superati ✓")
        scrivi_output(rows)
        return 0
    except AssertionError as exc:
        print(f"\n✗ SELF-TEST FALLITO: {exc}")
        return 1
    finally:
        _FIXTURES = None


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #

def _fix_console_encoding() -> None:
    """Evita UnicodeEncodeError sui simboli (✓ © — →) nel Prompt dei comandi.

    La console di Windows usa spesso una code page legacy (cp1252/cp850) che
    non sa stampare questi caratteri e solleverebbe UnicodeEncodeError. Con
    errors='replace' la stampa non fa mai crashare lo script.
    """
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:  # Python <3.7 o stream non riconfigurabile
            pass


def main(argv: list[str] | None = None) -> int:
    _fix_console_encoding()
    parser = argparse.ArgumentParser(
        description="Raccolta lead studi di architettura da PagineGialle."
    )
    parser.add_argument("--inspect", metavar="CITTA",
                        help="PARTE 0: scarica e ispeziona UNA pagina reale")
    parser.add_argument("--self-test", action="store_true",
                        help="verifica la logica offline (nessuna rete)")
    parser.add_argument("--test", action="store_true",
                        help="esegue sulle 2 città di prova (Lucca, Arezzo)")
    parser.add_argument("--cities", nargs="+", metavar="CITTA",
                        help="esegue sulle città indicate")
    parser.add_argument("--resume", action="store_true",
                        help="riprende dai file di checkpoint esistenti")
    args = parser.parse_args(argv)

    if args.self_test:
        return self_test()
    if args.inspect:
        inspect_city(args.inspect)
        return 0

    if args.cities:
        citta_list = args.cities
    elif args.test:
        citta_list = CITTA_TEST
    else:
        citta_list = CITTA_TUTTE

    esegui(citta_list, use_cache=args.resume)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
