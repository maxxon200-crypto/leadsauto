# ============================================================================
#  LEAD ARCHITETTI ITALIANI  —  versione "tutto in una cella" per Google Colab
#  Non serve installare Python: gira nel browser. Incolla e premi ▶.
# ============================================================================
import time, re
import requests, pandas as pd
from bs4 import BeautifulSoup
from urllib.parse import quote, urlparse

CITTA = ["Milano","Torino","Genova","Bologna","Firenze","Roma","Napoli","Bari",
 "Palermo","Verona","Padova","Venezia","Brescia","Bergamo","Parma","Modena",
 "Rimini","Perugia","Pisa","Siena","Lucca","Ancona","Pescara","Cagliari",
 "Catania","Trento","Bolzano","Udine","Trieste","Como","Varese","Vicenza",
 "Treviso","Ferrara","Ravenna","Reggio Emilia","Livorno","Arezzo","Salerno","Lecce"]

HEADERS = {"User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
           "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0 Safari/537.36",
           "Accept-Language":"it-IT,it;q=0.9"}
SLEEP = 1.5
MAX_PAGES = 5
EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,24}")
TEMPLATES = ["https://www.paginegialle.it/ricerca/studi%20di%20architettura/{s}{p}",
             "https://www.paginegialle.it/ricerca/architetti/{s}{p}"]
ITEM_SEL = ["div.search-itm","div.vcard","div[class*='search-itm']",
            "[itemtype*='LocalBusiness']","li[class*='item']","article[class*='item']"]
NAME_SEL = [".search-itm__rag-soc","[itemprop='name']","h2 a","h2","h3","a[title]"]
PHONE_SEL= ["[href^='tel:']","[itemprop='telephone']",".search-itm__phone",".tel",".phone"]
WEB_SEL  = ["a.search-itm__link-web","a[class*='web']","a[href^='http']"]
PEC = ("legalmail.it","arubapec.it","pec.it","postecert.it")
JUNK = ("noreply","no-reply","wordpress","esempio","example","sentry","wixpress")
BUILDERS = ("wix.com","wixsite.com","jimdo","altervista","weebly","business.site")
ANTIBOT = ("incapsula","captcha","datadome","just a moment","cloudflare","access denied")

_FIX = None  # gancio per il test offline; in Colab resta None
def get(url, t=15):
    if _FIX is not None: return _FIX.get(url)
    try:
        r = requests.get(url, headers=HEADERS, timeout=t)
        if r.status_code != 200: return None
        if not r.encoding or r.encoding.lower()=="iso-8859-1":
            r.encoding = r.apparent_encoding or r.encoding
        return r.text
    except Exception:
        return None
    finally:
        if _FIX is None: time.sleep(SLEEP)

def is_pec(e):
    e=e.lower(); d=e.split("@")[-1]
    return d.startswith("pec.") or ".pec." in d or any(p in d for p in PEC) or "legalmail" in d or "arubapec" in d
def is_junk(e):
    e=e.lower(); l=e.split("@")[0]
    return any(l.startswith(j) for j in JUNK) or e.endswith((".png",".jpg",".gif",".svg"))

def emails_da(html):
    out=[]
    try:
        s=BeautifulSoup(html,"html.parser")
        for a in s.find_all("a",href=True):
            if a["href"].lower().startswith("mailto:"):
                out.append(a["href"][7:].split("?")[0])
        for t in s(["script","style","noscript"]): t.decompose()
        txt=s.get_text(" ")
    except Exception:
        txt=html
    out += EMAIL_RE.findall(txt)
    res=[]
    for e in out:
        e=e.strip().strip(".,;").lower()
        if e and e not in res and not is_pec(e) and not is_junk(e): res.append(e)
    return res

def _txt(b,sels):
    for s in sels:
        try: n=b.select_one(s)
        except Exception: n=None
        if n:
            t=n.get_text(" ",strip=True)
            if t: return t
    return ""
def _phone(b):
    for s in PHONE_SEL:
        try: n=b.select_one(s)
        except Exception: n=None
        if n:
            h=n.get("href","") if hasattr(n,"get") else ""
            if h.startswith("tel:"): return h[4:]
            t=n.get_text(" ",strip=True)
            if t: return t
    return ""
def _web(b):
    for s in WEB_SEL:
        try: nodes=b.select(s)
        except Exception: nodes=[]
        for n in nodes:
            h=(n.get("href") or "").strip()
            low=h.lower()
            if not h or low.startswith(("tel:","mailto:","#","javascript:")): continue
            if any(x in low for x in ("paginegialle","facebook","instagram","linkedin","wa.me","google.")): continue
            if h.startswith("//"): h="https:"+h
            if h.startswith("http"): return h
    return ""
def parse(html):
    s=BeautifulSoup(html,"html.parser"); best=[]
    for sel in ITEM_SEL:
        try: f=s.select(sel)
        except Exception: f=[]
        if len(f)>len(best): best=f
    out=[]
    for b in best:
        nome=_txt(b,NAME_SEL)
        if nome: out.append({"nome":nome,"telefono":_phone(b),"sito":_web(b)})
    return out

def run():
    studi=[]
    print("PARTE 1 — raccolta da PagineGialle")
    for i,c in enumerate(CITTA,1):
        print(f"[{i}/40] {c} ...", end=" ")
        tmpl=None
        for t in TEMPLATES:
            u=t.format(s=quote(c.lower().replace(' ','-')),p="")
            h=get(u)
            if h and any(m in h.lower() for m in ANTIBOT):
                print("[ANTI-BOT: PagineGialle blocca requests]"); return _blocco()
            if h and parse(h): tmpl=t; break
        if not tmpl: print("0"); continue
        visti=set(); n0=len(studi)
        for pg in range(1,MAX_PAGES+1):
            u=tmpl.format(s=quote(c.lower().replace(' ','-')),p="" if pg==1 else f"/p-{pg}")
            h=get(u)
            if not h: break
            recs=parse(h)
            if not recs: break
            nuovi=0
            for r in recs:
                k=r["nome"].lower()+"|"+r.get("telefono","")
                if k in visti: continue
                visti.add(k); r["citta"]=c; studi.append(r); nuovi+=1
            if nuovi==0: break
        print(len(studi)-n0)
    print(f"\nRaccolti {len(studi)} studi. PARTE 2+3 — punteggio + email")
    rows=[]
    for i,s in enumerate(studi,1):
        sito=s.get("sito","")
        try:
            hp=get(sito,10) if sito else None
            if not sito: sc,note=10,"nessun sito"
            elif hp is None: sc,note=9,"irraggiungibile"
            else: sc,note=_score_html(sito,hp)
            em=emails_da(hp)[0] if hp else ""
        except Exception as e:
            sc,note,em=0,f"errore",""
        rows.append({"nome_studio":s["nome"],"citta":s["citta"],"email":em,
                     "telefono":s.get("telefono",""),"sito_attuale":sito,
                     "punteggio":sc,"note":note})
        if i%25==0: print(f"  {i}/{len(studi)} qualificati")
    df=pd.DataFrame(rows).sort_values("punteggio",ascending=False)
    df.to_csv("lead-architetti.csv",index=False,encoding="utf-8-sig")
    print(f"\n✔ FATTO: {len(df)} righe -> lead-architetti.csv")
    try:
        from google.colab import files; files.download("lead-architetti.csv")
    except Exception: pass
    return df

def _score_html(sito,html):
    low=html.lower(); dom=(urlparse(sito).netloc or sito).lower()
    sc=9 if any(x in dom or x in low for x in BUILDERS) else 2
    note=["builder"] if sc==9 else []
    try: s=BeautifulSoup(html,"html.parser")
    except Exception: return 9,"illeggibile"
    if s.find("meta",attrs={"name":re.compile("^viewport$",re.I)}) is None: sc+=3; note.append("no viewport")
    yrs=[int(x) for x in re.findall(r"©\s*((?:19|20)\d{2})",html)]
    if yrs and max(yrs)<2022: sc+=2; note.append(f"copyright {max(yrs)}")
    if s.find("center") or s.find("marquee"): sc+=2; note.append("layout vecchio")
    if "jquery" in low or "col-xs-" in low: sc+=1; note.append("jquery/bs3")
    return max(1,min(10,sc)),"; ".join(note) or "moderno"

def _blocco():
    print("\n>>> PagineGialle sta bloccando le richieste automatiche.")
    print(">>> Scrivi a Claude: 'PagineGialle bloccato, usa gli Ordini' e ti do il piano B.")
    return None

run()
