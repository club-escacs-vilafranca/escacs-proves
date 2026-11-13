#!/usr/bin/env python3
"""Notícies del web = publicacions d'Instagram de @escacsvilafranca (API oficial de Meta).
Llegeix les últimes publicacions, baixa les imatges a assets/noticies/ (els enllaços d'Instagram caduquen) i ho desa a data/noticies.json.
- Una publicació nova surt sola. Una que ja hi és NO es torna a sobreescriure (així el que s'editi al CMS es conserva).
- Al CMS (Notícies) es pot marcar «Amaga aquesta notícia»; la publicació es queda a Instagram i només desapareix de la web.
- Si es treu una publicació d'Instagram, a la web es conserva fins que s'amagui o s'esborri a mà.
Necessita els secrets INSTAGRAM_TOKEN i INSTAGRAM_ID. El token mai no s'escriu enlloc."""
import io, json, os, re, sys, urllib.parse, urllib.request
try:
    from PIL import Image
except ImportError:
    Image = None

TOKEN = os.environ.get("INSTAGRAM_TOKEN", "").strip()
IG_ID = os.environ.get("INSTAGRAM_ID", "").strip()
API = "https://graph.facebook.com/v21.0/"
FITXER = "data/noticies.json"
CARPETA = "assets/noticies"
MAXIM = int(os.environ.get("INSTAGRAM_MAX", "60"))
DES = os.environ.get("INSTAGRAM_DES", "").strip()      # AAAA-MM-DD: si hi és, es llegeix tot des d'aquesta data (sense el límit MAXIM)
CAMPS = "id,caption,media_type,media_url,thumbnail_url,permalink,timestamp,children{media_type,media_url,thumbnail_url}"


def get(url, binari=False):
    try:
        r = urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "club-escacs-vilafranca"}), timeout=60)
        return r.read() if binari else json.load(r)
    except urllib.error.HTTPError as e:
        cos = e.read().decode("utf-8", "ignore").replace(TOKEN, "***")
        raise RuntimeError("HTTP %s %s" % (e.code, cos[:300]))


def publicacions():
    url = API + (IG_ID or "me") + "/media?" + urllib.parse.urlencode({"fields": CAMPS, "limit": 25, "access_token": TOKEN})
    out = []
    while url and (DES or len(out) < MAXIM):
        d = get(url)
        dades = d.get("data", [])
        out += dades
        if DES and dades and (dades[-1].get("timestamp") or "9999")[:10] < DES:
            break                                   # ja som per sota de la data: Instagram les dona de més noves a més velles
        url = d.get("paging", {}).get("next")
    if DES:
        return [p for p in out if (p.get("timestamp") or "")[:10] >= DES]
    return out[:MAXIM]


def imatge(m):
    """URL de la imatge d'un element (en un vídeo, la miniatura)."""
    return m.get("thumbnail_url") if m.get("media_type") == "VIDEO" else m.get("media_url")


def baixa(url, nom):
    cami = "%s/%s.jpg" % (CARPETA, nom)
    if os.path.exists(cami):
        return cami
    os.makedirs(CARPETA, exist_ok=True)
    dades = get(url, True)
    if Image:                                    # es redueix (màx. 1080 px) perquè el repositori no creixi massa
        try:
            im = Image.open(io.BytesIO(dades)).convert("RGB")
            im.thumbnail((1080, 1080))
            im.save(cami, "JPEG", quality=80, optimize=True)
            return cami
        except Exception as ex:
            print("  no s'ha pogut reduir una imatge:", str(ex)[:60])
    open(cami, "wb").write(dades)
    return cami


def nova(p):
    elems = (p.get("children") or {}).get("data") or [p]
    imgs = []
    for i, e in enumerate(elems[:10]):
        u = imatge(e)
        if not u:
            continue
        try:
            imgs.append(baixa(u, "%s-%d" % (p["id"], i + 1)))
        except Exception as ex:
            print("  no s'ha pogut baixar una imatge de", p["id"], str(ex)[:80])
    return {"id": p["id"], "data": p["timestamp"][:10], "text": p.get("caption") or "", "url": p.get("permalink", ""),
            "video": p.get("media_type") == "VIDEO", "imatges": imgs, "ocult": False}


def main():
    if not TOKEN:
        print("Falta el secret INSTAGRAM_TOKEN"); sys.exit(1)
    antic = json.load(open(FITXER, encoding="utf-8")) if os.path.exists(FITXER) else {"posts": []}
    posts = {x["id"]: x for x in antic.get("posts", [])}
    afegides = 0
    for p in publicacions():
        if p["id"] in posts:
            continue
        posts[p["id"]] = nova(p)
        afegides += 1
        print("+", p["timestamp"][:10], (p.get("caption") or "").replace("\n", " ")[:60])
    ordre = sorted(posts.values(), key=lambda x: x["data"], reverse=True)
    json.dump({"posts": ordre}, open(FITXER, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("%d notícies noves (%d en total)" % (afegides, len(ordre)))


if __name__ == "__main__":
    main()
