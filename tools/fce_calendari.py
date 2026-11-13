#!/usr/bin/env python3
"""Calendari de la FCE (escacs.cat) -> data/calendari-oficial.json (nous esdeveniments pendents de validar).
La FCE publica el calendari oficial i els quatre territorials (Barcelona, Girona, Lleida, Tarragona) com a IMATGES amb una taula
(Campionats | Data inici | Data final | Ritme de joc). Aquí es baixen, es detecta la quadrícula, es llegeix cada cel·la amb OCR (Tesseract)
i es crea un esdeveniment per fila. Com que l'OCR pot fallar (accents, xifres), tot el que es llegeix entra com a «Pendent de validar»;
només s'hi afegeix el que NO és ja al calendari i es torna a llegir una imatge només si ha canviat (no es toca mai el que ja hi ha).
Ús: python3 tools/fce_calendari.py   (necessita opencv, pytesseract i tesseract-ocr amb l'idioma «cat»; FCE_LOCAL=carpeta per provar sense xarxa)"""
import difflib, hashlib, json, os, re, sys, unicodedata, urllib.request
from datetime import datetime, timezone

import cv2
import numpy as np
import pytesseract

BASE = "https://escacs.cat"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
PAGINES = [   # (pàgina, lloc, imatge si la pàgina no es pot llegir). Només el calendari general i el de Barcelona (els altres delegacions no cal)
    ("/index.php/competicio/competicions/calendaris-oficial-fce", "Catalunya", "/images/2025/CALENDARI2026.png"),
    ("/index.php/federacio/territorial-bcn/calendari-territorial-bcn", "Delegació de Barcelona", "/images/Barcelona/CALENDARI2026BCN.png"),
]
HASHES = "data/brut/fce-calendari-imatges.json"
OFICIAL = "data/calendari-oficial.json"
MESOS = ["GENER", "FEBRER", "MARC", "ABRIL", "MAIG", "JUNY", "JULIOL", "AGOST", "SETEMBRE", "OCTUBRE", "NOVEMBRE", "DESEMBRE"]
RITMES = ["Tradicional", "Actiu", "Llampec", "Blitz - Online", "Blitz"]
LANG = "cat" if "cat" in pytesseract.get_languages() else "eng"


def sa(t):
    return re.sub(r"[^a-z0-9]+", " ", unicodedata.normalize("NFKD", t or "").encode("ascii", "ignore").decode().lower()).strip()


def baixa(url):
    loc = os.environ.get("FCE_LOCAL")
    if loc and os.path.exists(os.path.join(loc, os.path.basename(url))):
        return open(os.path.join(loc, os.path.basename(url)), "rb").read()
    rq = urllib.request.Request(url if url.startswith("http") else BASE + url, headers={"User-Agent": UA})
    return urllib.request.urlopen(rq, timeout=60).read()


def capcalera(url):
    """Last-Modified i mida de la imatge sense baixar-la (si el servidor els dona)."""
    try:
        rq = urllib.request.Request(url if url.startswith("http") else BASE + url, headers={"User-Agent": UA}, method="HEAD")
        r = urllib.request.urlopen(rq, timeout=30)
        return (r.headers.get("Last-Modified") or "") + "|" + (r.headers.get("Content-Length") or "")
    except Exception:
        return ""


def imatge_de(pagina, per_defecte):
    try:
        html = baixa(pagina).decode("utf-8", "ignore")
        m = re.search(r'<img[^>]+src="([^"]*CALENDARI[^"]*\.(?:png|jpg|jpeg))"', html, re.I)
        if m:
            return m.group(1)
    except Exception as e:
        print("  pàgina no llegible", pagina, str(e)[:80])
    return per_defecte


def grup(v):
    out = []
    for a in v:
        if out and a - out[-1][-1] <= 3:
            out[-1].append(a)
        else:
            out.append([a])
    return [int(np.mean(o)) for o in out]


def quadricula(g):
    ink = (g < 120).astype(np.uint8) * 255
    h, w = ink.shape
    hl = cv2.morphologyEx(ink, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (w // 4, 1)))
    ys = grup(np.where(hl.sum(axis=1) > w // 4 * 255 * 0.9)[0])
    if len(ys) < 3:
        return [], []
    y0, y1 = ys[1], ys[-1]            # ys[0] és la capçalera; les files són a partir de la segona línia
    reg = ink[y0:y1]
    vl = cv2.morphologyEx(reg, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (1, max(int((y1 - y0) * 0.8), 5))))
    return ys[1:], grup(np.where(vl.sum(axis=0) > 0)[0])


def ocr(cel):
    c = cv2.resize(cel, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
    _, b = cv2.threshold(c, 130, 255, cv2.THRESH_BINARY)
    b = cv2.copyMakeBorder(b, 10, 10, 10, 10, cv2.BORDER_CONSTANT, value=255)
    return pytesseract.image_to_string(b, lang=LANG, config="--psm 7").strip()


def data(t):
    """'12 MARÇ 2026' (amb soroll d'OCR) -> 'AAAA-MM-DD' o None."""
    m = re.search(r"(\d{1,2})\D{0,6}?([A-ZÀ-Ü]{3,10})\D{0,4}?(20\d\d)", (t or "").upper().replace("DE ", " "))
    if not m:
        return None
    mes = difflib.get_close_matches(sa(m.group(2)).upper(), MESOS, n=1, cutoff=0.6)
    if not mes:
        return None
    any_, dia = int(m.group(3)), int(m.group(1))
    if any_ not in (2025, 2026, 2027, 2028) or not 1 <= dia <= 31:
        return None
    try:
        return datetime(any_, MESOS.index(mes[0]) + 1, dia).strftime("%Y-%m-%d")
    except ValueError:
        return None


def llegeix(img):
    g = cv2.imdecode(np.frombuffer(img, np.uint8), cv2.IMREAD_GRAYSCALE)
    ys, xs = quadricula(g)
    if len(xs) < 5:
        print("  no s'ha trobat la quadrícula")
        return []
    files = []
    for a, b in zip(ys, ys[1:]):
        if b - a < 25:
            continue
        cel = [ocr(g[a + 4:b - 3, x0 + 4:x1 - 3]) for x0, x1 in list(zip(xs, xs[1:]))[:4]]
        nom = re.sub(r"^[^\wÀ-ÿ]*(?:[o°©•]\s+)?", "", cel[0]).strip(" -")
        nom = re.sub(r"^[a-z]{1,2}\s+(?=[A-ZÀ-Ü])", "", nom)            # soroll d'OCR davant el nom
        if "circuit" in sa(nom):
            continue                                                   
        ini, fi = data(cel[1]), data(cel[2])
        rit = difflib.get_close_matches(cel[3].strip().capitalize(), RITMES, n=1, cutoff=0.6)
        if nom and ini and fi and fi >= ini:
            files.append({"nom": nom, "ini": ini, "fi": fi, "ritme": rit[0] if rit else ""})
        else:
            print("  fila no vàlida:", cel)
    return files


def igual(e, nom, ini, fi, lloc):
    if e.get("place") != lloc:
        return False
    s = difflib.SequenceMatcher(None, sa(e["name"]).replace(" territorial de", ""), sa(nom).replace(" territorial de", "")).ratio()
    return s >= 0.78 and (e["sch"].get("start") == ini or e["sch"].get("end") == fi or e["sch"].get("start") == fi)


def main():
    oficial_d = json.load(open(OFICIAL, encoding="utf-8")) if os.path.exists(OFICIAL) else {"events": []}
    events = oficial_d.get("events", [])
    hashes = json.load(open(HASHES, encoding="utf-8")) if os.path.exists(HASHES) else {}
    nous_h, afegits, treballat = dict(hashes), 0, False
    for pagina, lloc, per_defecte in PAGINES:
        url = imatge_de(pagina, per_defecte)
        cap = capcalera(url)
        if cap and cap != "|" and hashes.get(url + "#cap") == cap:
            print(lloc, ": la imatge no ha canviat (data i mida iguals), no cal mirar-la")
            continue
        try:
            img = baixa(url)
        except Exception as e:
            print("  no s'ha pogut baixar", url, str(e)[:80])
            continue
        h = hashlib.sha256(img).hexdigest()[:16]
        if hashes.get(url) == h:
            print(lloc, ": imatge sense canvis")
            if cap:
                nous_h[url + "#cap"] = cap
                treballat = True
            continue
        print(lloc, ": llegint", url)
        llegides = llegeix(img)
        if not llegides:
            continue                                         # no es desa el hash: es tornarà a provar
        ids_nous = set()
        for f in llegides:
            if any(igual(e, f["nom"], f["ini"], f["fi"], lloc) for e in events):
                continue                                     # ja és al calendari (validat a mà o d'una lectura anterior)
            ident = "fceimg-" + sa(f["nom"]).replace(" ", "-")[:50] + "-" + f["ini"]
            ids_nous.add(ident)
            dia = f["ini"] == f["fi"]
            events.append({"id": ident, "name": f["nom"], "type": "oficial", "scope": "CAT", "place": lloc,
                           "format": ("Ritme de joc: " + f["ritme"]) if f["ritme"] else "Calendari de la FCE",
                           "sch": {"kind": "dia" if dia else "dies", "start": f["ini"], "end": "" if dia else f["fi"], "weeks": None},
                           "source": "fce", "status": "pend", "url": BASE + pagina})
            afegits += 1
            print("  +", f["ini"], f["fi"], f["nom"])
        nous_h[url] = h
        if cap:
            nous_h[url + "#cap"] = cap
        treballat = True
    if treballat:
        oficial_d["events"] = events
        json.dump(oficial_d, open(OFICIAL, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        os.makedirs(os.path.dirname(HASHES), exist_ok=True)
        json.dump(nous_h, open(HASHES, "w", encoding="utf-8"), indent=1)
    print(afegits, "esdeveniments nous (pendents de validar) del calendari de la FCE")


if __name__ == "__main__":
    main()
