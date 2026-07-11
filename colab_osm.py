# ============================================================================
#  LEAD ARCHITETTI da OpenStreetMap (API Overpass) — cella unica per Colab.
#  Fonte pubblica, gratuita, dati strutturati, NIENTE anti-bot. Incolla e ▶.
# ============================================================================
import requests, pandas as pd

OVERPASS = ["https://overpass-api.de/api/interpreter",
            "https://overpass.kumi.systems/api/interpreter",
            "https://maps.mail.ru/osm/tools/overpass/api/interpreter"]
Q = """
[out:json][timeout:180];
area["ISO3166-1"="IT"][admin_level=2]->.it;
( nwr["office"="architect"](area.it); );
out center tags;
"""
PEC = ("pec.", "legalmail", "arubapec", "postecert")
def is_pec(e):
    e = (e or "").lower(); d = e.split("@")[-1]
    return d.startswith("pec.") or any(p in d for p in PEC)

def scarica():
    for url in OVERPASS:
        try:
            print("Interrogo", url, "...")
            r = requests.post(url, data={"data": Q}, timeout=200)
            if r.status_code == 200:
                return r.json()
            print("  risposta HTTP", r.status_code, "- provo un altro server")
        except Exception as e:
            print("  errore:", e, "- provo un altro server")
    return None

data = scarica()
rows = []
if data:
    for el in data.get("elements", []):
        t = el.get("tags", {})
        nome = t.get("name") or t.get("operator")
        if not nome:
            continue
        email = t.get("email") or t.get("contact:email") or ""
        if is_pec(email):
            email = ""
        rows.append({
            "nome_studio": nome,
            "citta": t.get("addr:city", "") or t.get("addr:town", ""),
            "provincia": t.get("addr:province", ""),
            "email": email,
            "telefono": t.get("phone", "") or t.get("contact:phone", "") or t.get("contact:mobile", ""),
            "sito": t.get("website", "") or t.get("contact:website", ""),
            "indirizzo": " ".join(x for x in [t.get("addr:street", ""), t.get("addr:housenumber", "")] if x),
        })

seen = set(); uniq = []
for r in rows:
    k = (r["nome_studio"].lower().strip(), r["citta"].lower().strip())
    if k in seen:
        continue
    seen.add(k); uniq.append(r)

df = pd.DataFrame(uniq)
if len(df):
    # in cima i lead più "lavorabili" (con telefono/sito/email)
    df["_c"] = (df.telefono != "").astype(int) + (df.sito != "").astype(int) + (df.email != "").astype(int)
    df = df.sort_values("_c", ascending=False).drop(columns="_c").reset_index(drop=True)
df.to_csv("architetti-osm.csv", index=False, encoding="utf-8-sig")
print(f"\n✔ TROVATI {len(df)} studi -> architetti-osm.csv")
if len(df):
    print(df.head(15).to_string(index=False))
try:
    from google.colab import files
    files.download("architetti-osm.csv")
except Exception:
    pass
