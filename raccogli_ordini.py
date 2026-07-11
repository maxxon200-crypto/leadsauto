#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
raccogli_ordini.py — PIANO B: lead architetti dagli Ordini provinciali.

Fonte alternativa a PagineGialle: gli **albi degli Ordini degli Architetti**
(uno per provincia). È la fonte anagrafica ufficiale ed è di norma MOLTO meno
protetta da anti-bot di PagineGialle, quindi con un semplice `requests` funziona
più spesso.

Riusa le parti già collaudate di raccogli.py:
    - PARTE 2 (qualificazione sito, punteggio 1-10)
    - PARTE 3 (estrazione email, scarto PEC/junk)
    - scrittura output ordinata
    - client HTTP educato (sleep 2s, mai crash), --inspect, fix console Windows

Dipendenze: SOLO requests, beautifulsoup4, pandas (+ raccogli.py nella stessa
cartella).

Uso (Prompt dei comandi Windows — 'py'; su Mac/Linux 'python3'):
    py raccogli_ordini.py --list                 # elenca gli Ordini noti (URL da verificare)
    py raccogli_ordini.py --inspect Lucca         # ispeziona la pagina albo di una provincia
    py raccogli_ordini.py --inspect-url https://...   # ispeziona un URL qualsiasi
    py raccogli_ordini.py --self-test             # verifica la logica offline (niente rete)
    py raccogli_ordini.py --scrape --config ordini.yaml   # scrapa gli Ordini configurati

FLUSSO CONSIGLIATO:
    1) `--inspect Lucca` (o `--inspect-url <pagina albo>`): guarda la struttura
       reale e i selettori suggeriti.
    2) crea/aggiorna `ordini.yaml` (vedi ordini.example.yaml) con search_url +
       selettori per le province che ti servono.
    3) `--scrape --config ordini.yaml` -> lead-architetti-ordini.csv

NOTA ONESTA: gli URL in ORDINI_HOMEPAGE sono punti di PARTENZA da VERIFICARE con
--inspect (gli Ordini cambiano sito/endpoint). Lo script non garantisce che un
URL sia ancora valido: per questo il primo passo è sempre --inspect.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from bs4 import BeautifulSoup

# Riuso del modulo principale (deve stare nella stessa cartella).
import raccogli as r

OUTPUT_DIR = Path.cwd()
OUTPUT_FILE = OUTPUT_DIR / "lead-architetti-ordini.csv"
CHECKPOINT_FILE = OUTPUT_DIR / "checkpoint-ordini.csv"

# --------------------------------------------------------------------------- #
# Mappa Ordini provinciali (homepage). PUNTI DI PARTENZA DA VERIFICARE.
# La pagina di ricerca "albo/iscritti" va trovata con --inspect: molti Ordini
# la espongono sotto /albo, /ricerca-iscritti, /trova-architetto, ecc.
# --------------------------------------------------------------------------- #
ORDINI_HOMEPAGE: dict[str, str] = {
    "Milano": "https://www.ordinearchitetti.mi.it",
    "Torino": "https://www.oato.it",
    "Genova": "https://www.ordinearchitetti.ge.it",
    "Bologna": "https://www.archibo.it",
    "Firenze": "https://www.ordinearchitetti.fi.it",
    "Roma": "https://www.architettiroma.it",
    "Napoli": "https://www.ordinearchitettinapoli.it",
    "Bari": "https://www.ordarchbari.it",
    "Palermo": "https://www.ordinearchitettipalermo.it",
    "Verona": "https://www.architettiverona.it",
    "Padova": "https://www.ordinearchitettipadova.it",
    "Venezia": "https://www.ordinearchitettivenezia.it",
    "Brescia": "https://www.ordinearchitetti.bs.it",
    "Bergamo": "https://www.ordinearchitettibergamo.it",
    "Parma": "https://www.archiparma.it",
    "Modena": "https://www.architettimodena.it",
    "Rimini": "https://www.rimini.archiworld.it",
    "Perugia": "https://www.ordinearchitettiperugia.it",
    "Pisa": "https://www.ordinearchitettipisa.it",
    "Siena": "https://www.architettisiena.it",
    "Lucca": "https://www.architettilucca.it",
    "Ancona": "https://www.ordinearchitettiancona.it",
    "Pescara": "https://www.pescara.archiworld.it",
    "Cagliari": "https://www.ordinearchitetticagliari.it",
    "Catania": "https://www.ordinearchitetticatania.it",
    "Trento": "https://www.archiworldtrento.it",
    "Bolzano": "https://www.arch.bz.it",
    "Udine": "https://www.ordinearchitettiudine.it",
    "Trieste": "https://www.ts.archiworld.it",
    "Como": "https://www.ordinearchitetticomo.it",
    "Varese": "https://www.ordinearchitettivarese.it",
    "Vicenza": "https://www.ordinearchitettivicenza.it",
    "Treviso": "https://www.archingtv.it",
    "Ferrara": "https://www.architettiferrara.it",
    "Ravenna": "https://www.ordinearchitettiravenna.it",
    "Reggio Emilia": "https://www.architetti.re.it",
    "Livorno": "https://www.ordinearchitettilivorno.it",
    "Arezzo": "https://www.architettiarezzo.it",
    "Salerno": "https://www.ordinearchitettisalerno.it",
    "Lecce": "https://www.ordarchlecce.it",
}

# Selettori candidati per il BLOCCO di ogni iscritto (provati in ordine; vince
# quello con più blocchi). Gli Ordini usano markup vari: card, righe di tabella,
# elementi di lista con microdata Person.
ITEM_SELECTORS = [
    "[itemtype*='Person']",
    "div.iscritto", "li.iscritto", "tr.iscritto",
    "div.architetto", "div.member", "article.iscritto",
    "div[class*='iscritt']", "li[class*='iscritt']",
    "tr[class*='iscritt']", "div[class*='member']",
    "table.albo tr", "div.card",
]
NAME_SELECTORS = [
    "[itemprop='name']", ".nome", ".cognome", ".fullname", ".nominativo",
    "h3", "h4", "td.nome", "a[href*='iscritto']", "strong",
]
CITY_SELECTORS = [
    "[itemprop='addressLocality']", ".comune", ".citta", ".localita", "td.comune",
]
EMAIL_SELECTORS = [
    "a[href^='mailto:']", "[itemprop='email']", ".email", "td.email",
]
PHONE_SELECTORS = [
    "a[href^='tel:']", "[itemprop='telephone']", ".telefono", ".tel", "td.telefono",
]
WEBSITE_SELECTORS = [
    "a[href^='http']", "[itemprop='url']", ".sito", "a.website",
]


# --------------------------------------------------------------------------- #
# ESTRAZIONE (config-driven quando c'è ordini.yaml, altrimenti euristica)
# --------------------------------------------------------------------------- #

def _text(block, selectors: list[str]) -> str:
    for sel in selectors:
        try:
            node = block.select_one(sel)
        except Exception:
            continue
        if node is not None:
            txt = node.get_text(" ", strip=True)
            if txt:
                return txt
    return ""


def _email(block) -> str:
    for sel in EMAIL_SELECTORS:
        try:
            node = block.select_one(sel)
        except Exception:
            continue
        if node is None:
            continue
        href = node.get("href", "") if hasattr(node, "get") else ""
        if href.lower().startswith("mailto:"):
            addr = href[7:].split("?")[0].strip()
            if addr:
                return addr
        txt = node.get_text(" ", strip=True)
        if "@" in txt:
            return txt
    m = r.EMAIL_RE.search(block.get_text(" "))
    return m.group(0) if m else ""


def _phone(block) -> str:
    for sel in PHONE_SELECTORS:
        try:
            node = block.select_one(sel)
        except Exception:
            continue
        if node is None:
            continue
        href = node.get("href", "") if hasattr(node, "get") else ""
        if href.lower().startswith("tel:"):
            return href[4:].strip()
        txt = node.get_text(" ", strip=True)
        if txt:
            return txt
    return ""


def _website(block, base_url: str) -> str:
    bad = ("mailto:", "tel:", "javascript:", "#", "facebook.", "instagram.",
           "linkedin.", "twitter.", "archiworld", "cnappc")
    for sel in WEBSITE_SELECTORS:
        try:
            nodes = block.select(sel)
        except Exception:
            continue
        for node in nodes:
            href = (node.get("href") or "").strip()
            low = href.lower()
            if not href or any(b in low for b in bad):
                continue
            # scarta il link all'Ordine stesso
            if base_url and r.urlparse(base_url).netloc in low:
                continue
            if href.startswith("//"):
                href = "https:" + href
            if href.startswith("http"):
                return href
    return ""


def parse_ordine(html: str, provincia: str, base_url: str, cfg: dict | None = None) -> list[dict]:
    """Estrae gli iscritti da una pagina albo. Usa i selettori del config se
    presenti, altrimenti l'euristica multi-selettore."""
    soup = BeautifulSoup(html, "html.parser")

    if cfg and cfg.get("list_selector"):
        try:
            blocks = soup.select(cfg["list_selector"])
        except Exception:
            blocks = []
    else:
        blocks = []
        for sel in ITEM_SELECTORS:
            try:
                found = soup.select(sel)
            except Exception:
                continue
            if len(found) > len(blocks):
                blocks = found

    fields = (cfg or {}).get("fields") or {}
    studi: list[dict] = []
    for block in blocks:
        try:
            if fields:
                nome = _cfg_field(block, fields.get("nome"))
                citta = _cfg_field(block, fields.get("citta")) or provincia
                email = _cfg_field(block, fields.get("email"))
                telefono = _cfg_field(block, fields.get("telefono"))
                sito = _cfg_field(block, fields.get("sito"), base_url)
            else:
                nome = _text(block, NAME_SELECTORS)
                citta = _text(block, CITY_SELECTORS) or provincia
                email = _email(block)
                telefono = _phone(block)
                sito = _website(block, base_url)
        except Exception:
            continue
        if not nome:
            continue
        studi.append({
            "nome": nome, "citta": citta, "email": email,
            "telefono": telefono, "sito": sito, "source": f"ordine:{provincia}",
        })
    return studi


def _cfg_field(block, spec: dict | None, base_url: str = "") -> str:
    if not spec:
        return ""
    sel = spec.get("selector")
    try:
        node = block.select_one(sel) if sel else block
    except Exception:
        return ""
    if node is None:
        return ""
    attr = spec.get("attr")
    val = (node.get(attr, "") if attr else node.get_text(" ", strip=True)) or ""
    prefix = spec.get("strip_prefix")
    if prefix and val.startswith(prefix):
        val = val[len(prefix):]
    if spec.get("absolute") and val and base_url:
        val = r.urljoin(base_url, val)
    return val.strip()


# --------------------------------------------------------------------------- #
# COLLEZIONE + INSPECT
# --------------------------------------------------------------------------- #

def _search_url(cfg: dict, page: int) -> str:
    url = cfg["search_url"]
    if "{page}" in url:
        return url.format(page=page)
    return url


def scrape_ordine(provincia: str, cfg: dict) -> list[dict]:
    if not cfg.get("search_url"):
        print(f"  [ordine] {provincia}: manca 'search_url' nel config -> salto "
              "(usa --inspect per trovarlo).")
        return []
    base_url = cfg.get("base_url") or ORDINI_HOMEPAGE.get(provincia, "")
    max_pages = int(cfg.get("max_pages", 5))
    print(f"  [ordine] {provincia} ...")
    studi: list[dict] = []
    visti: set[str] = set()
    for page in range(1, max_pages + 1):
        url = _search_url(cfg, page)
        html = r.get_html(url)
        if not html:
            break
        recs = parse_ordine(html, provincia, base_url, cfg)
        if not recs:
            break
        nuovi = 0
        for rec in recs:
            k = f"{rec['nome'].lower()}|{rec.get('email','')}"
            if k in visti:
                continue
            visti.add(k)
            studi.append(rec)
            nuovi += 1
        print(f"    pagina {page}: {len(recs)} iscritti, {nuovi} nuovi (tot {len(studi)})")
        if nuovi == 0 or "{page}" not in cfg["search_url"]:
            break
    print(f"    -> {len(studi)} iscritti da {provincia}")
    return studi


def inspect_target(target: str) -> None:
    """Ispeziona una provincia nota o un URL diretto (--inspect-url)."""
    if target.startswith("http"):
        url, nome = target, "url"
    else:
        url = ORDINI_HOMEPAGE.get(target)
        nome = target
        if not url:
            print(f"Provincia '{target}' non in elenco. Usa --list, oppure --inspect-url <URL>.")
            return
    print(f"=== ISPEZIONE ORDINE — {nome} ===\n--- {url}")
    res = r._raw_fetch(url)
    fpath = OUTPUT_DIR / f"inspect_ordine_{r.slugify(nome)}.html"
    if "error" in res:
        print(f"    [errore rete] {res['error']}")
        try:
            fpath.write_text(f"<html><body>Errore: {res['error']}</body></html>", encoding="utf-8")
            print(f"    (artefatto diagnostico in {fpath})")
        except Exception:
            pass
        return
    status, html, ctype = res["status"], res.get("text", ""), res.get("ctype", "?")
    print(f"    HTTP {status} | {ctype} | {len(html)} caratteri")
    try:
        fpath.write_text(html or f"<!-- HTTP {status} -->", encoding="utf-8")
        print(f"    -> salvato in {fpath}   (aprilo con:  start {fpath.name})")
    except Exception as exc:
        print(f"    (impossibile salvare: {exc})")

    markers = [m for m in r.ANTIBOT_MARKERS if m in html.lower()]
    if status != 200 or markers:
        print(f"    /!\\ status={status}, anti-bot={markers or 'nessuno'}. "
              "Se è una verifica/captcha, prova un altro Ordine o l'Albo Unico CNAPPC.")
        return

    soup = BeautifulSoup(html, "html.parser")
    title = soup.title.get_text(strip=True) if soup.title else "(nessun title)"
    print(f"    <title>: {title}")
    print("    Classi più ripetute (candidati blocco iscritto):")
    for cls, n in r._frequent_block_classes(soup)[:12]:
        print(f"      {n:>3}x  .{cls}")
    print("    Resa selettori candidati (iscritti):")
    trovato = False
    for sel in ITEM_SELECTORS:
        try:
            found = soup.select(sel)
        except Exception:
            continue
        if found:
            trovato = True
            print(f"      {len(found):>3}x  {sel}")
    if not trovato:
        print("      nessun selettore candidato. Questa è probabilmente la HOMEPAGE:")
        print("      cerca il link 'Albo / Iscritti / Trova architetto' e rifai")
        print("      --inspect-url su QUELLA pagina.")
    print("\n    Suggerimento: molti Ordini hanno la ricerca albo sotto /albo,")
    print("    /iscritti, /ricerca-iscritti, /trova-architetto.")


# --------------------------------------------------------------------------- #
# SELF-TEST OFFLINE
# --------------------------------------------------------------------------- #

def _fixtures() -> dict[str, str]:
    albo = """
    <html><head><title>Albo Architetti Lucca</title></head><body>
      <table class="albo">
        <tr class="iscritto">
          <td class="nome">Arch. Giulia Ferrari</td>
          <td class="comune">Lucca</td>
          <td class="email"><a href="mailto:giulia.ferrari@architetti.example">email</a></td>
          <td class="telefono"><a href="tel:+390583111222">0583 111222</a></td>
          <td class="sito"><a href="https://studioferrari.example">sito</a></td>
        </tr>
        <tr class="iscritto">
          <td class="nome">Arch. Marco Bianchi</td>
          <td class="comune">Capannori</td>
          <td class="email"><a href="mailto:m.bianchi@pec.it">pec</a></td>
        </tr>
        <tr class="iscritto">
          <td class="nome">Arch. Sofia Romano</td>
          <td class="comune">Viareggio</td>
        </tr>
      </table>
    </body></html>
    """
    sito_ferrari = """
    <html><head><title>Studio Ferrari</title>
    <script>var t="jquery-1.9.js";</script></head>
    <body><table width="100%"><tr><td>
      Contatti: <a href="mailto:info@studioferrari.example">info@studioferrari.example</a>
    </td></tr></table><footer>© 2016</footer></body></html>
    """
    return {
        "https://albo.example/lucca": albo,
        "https://studioferrari.example": sito_ferrari,
    }


def self_test() -> int:
    print("=== SELF-TEST OFFLINE ordini (nessuna rete) ===\n")
    r._FIXTURES = _fixtures()
    try:
        cfg = {"search_url": "https://albo.example/lucca", "base_url": "https://albo.example",
               "max_pages": 1}
        studi = scrape_ordine("Lucca", cfg)
        assert len(studi) == 3, f"attesi 3 iscritti, trovati {len(studi)}"
        assert studi[0]["nome"] == "Arch. Giulia Ferrari", studi[0]
        assert studi[0]["email"] == "giulia.ferrari@architetti.example", studi[0]
        assert studi[0]["citta"] == "Lucca"
        assert studi[1]["citta"] == "Capannori", "città per-iscritto non estratta"

        rows = r.qualifica_e_email(studi, checkpoint_file=CHECKPOINT_FILE)
        by = {x["nome_studio"]: x for x in rows}

        # Ferrari: email diretta valida CONSERVATA (non sovrascritta dal sito),
        # ma il sito è vecchio (table layout + jquery + © 2016 + no viewport) -> alto.
        g = by["Arch. Giulia Ferrari"]
        assert g["email"] == "giulia.ferrari@architetti.example", g["email"]
        assert g["punteggio"] >= 8, g

        # Bianchi: email è PEC -> scartata -> nessuna email, nessun sito -> 10.
        b = by["Arch. Marco Bianchi"]
        assert b["email"] == "", f"PEC non scartata: {b}"
        assert b["punteggio"] == 10, b

        # Romano: nessun sito -> 10.
        assert by["Arch. Sofia Romano"]["punteggio"] == 10

        assert all("pec" not in (x["email"] or "") for x in rows), "PEC passata!"
        print("\nTutti i controlli superati ✓")
        r.scrivi_output(rows, output_file=OUTPUT_FILE)
        return 0
    except AssertionError as exc:
        print(f"\n✗ SELF-TEST FALLITO: {exc}")
        return 1
    finally:
        r._FIXTURES = None


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #

def _load_config(path: str) -> dict:
    if not path:
        return {}
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Config non trovato: {p}")
    import yaml  # PyYAML: opzionale, solo per --scrape con config
    with p.open(encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def main(argv: list[str] | None = None) -> int:
    r._fix_console_encoding()
    ap = argparse.ArgumentParser(description="Piano B: lead architetti dagli Ordini provinciali.")
    ap.add_argument("--list", action="store_true", help="elenca gli Ordini noti (URL da verificare)")
    ap.add_argument("--inspect", metavar="PROVINCIA", help="ispeziona la pagina di una provincia nota")
    ap.add_argument("--inspect-url", metavar="URL", help="ispeziona un URL qualsiasi (pagina albo)")
    ap.add_argument("--self-test", action="store_true", help="verifica la logica offline")
    ap.add_argument("--scrape", action="store_true", help="scrapa gli Ordini definiti in --config")
    ap.add_argument("--config", help="file YAML con la config di scraping per provincia")
    ap.add_argument("--resume", action="store_true", help="riprende dal checkpoint")
    args = ap.parse_args(argv)

    if args.self_test:
        return self_test()
    if args.list:
        print("Ordini noti (URL DI PARTENZA, da verificare con --inspect):")
        for prov, url in ORDINI_HOMEPAGE.items():
            print(f"  {prov:<16} {url}")
        return 0
    if args.inspect_url:
        inspect_target(args.inspect_url)
        return 0
    if args.inspect:
        inspect_target(args.inspect)
        return 0
    if args.scrape:
        cfg_all = _load_config(args.config) if args.config else {}
        province = cfg_all.get("ordini") or {}
        if not province:
            print("Nessuna provincia in --config. Vedi ordini.example.yaml.")
            print("Prima ispeziona con --inspect <Provincia> per trovare selettori/URL.")
            return 1
        studi: list[dict] = []
        for prov, cfg in province.items():
            try:
                studi.extend(scrape_ordine(prov, cfg))
            except Exception as exc:  # noqa: BLE001 — mai crashare a metà
                print(f"    [errore ordine {prov}] {type(exc).__name__}: {exc}")
        rows = r.qualifica_e_email(studi, checkpoint_file=CHECKPOINT_FILE)
        r.scrivi_output(rows, output_file=OUTPUT_FILE)
        return 0

    ap.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
