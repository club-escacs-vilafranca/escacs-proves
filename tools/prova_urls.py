#!/usr/bin/env python3
"""Baixa pàgines concretes (FFE i Vesus) i les deixa a mostres_brut/ (que després es xifra). Al log només hi surt estat, mida, títol i les línies de la jugadora autoritzada."""
import os, re, sys, time, urllib.request
from playwright.sync_api import sync_playwright
FFE = [("ffe_fitxa", "https://www.echecs.asso.fr/FicheTournoi.aspx?Ref=70352"),
       ("ffe_jugadors", "https://www.echecs.asso.fr/Resultats.aspx?URL=Tournois/Id/70352/70352&Action=Ls"),
       ("ffe_graella", "https://www.echecs.asso.fr/Resultats.aspx?URL=Tournois/Id/70352/70352&Action=Ga"),
       ("ffe_classificacio", "https://www.echecs.asso.fr/Resultats.aspx?URL=Tournois/Id/70352/70352&Action=Cl"),
       ("ffe_ronda01", "https://www.echecs.asso.fr/Resultats.aspx?URL=Tournois/Id/70352/70352&Action=01")]
VESUS = [("vesus_event", "https://vesus.org/event/sTwKTWvd"), ("vesus_grupA", "https://vesus.org/tournament/MqLOlBXF"),
         ("vesus_grupC", "https://vesus.org/tournament/gzam-Uzq"), ("vesus_blitz", "https://vesus.org/tournament/2YMZzD3y")]
os.makedirs("mostres_brut", exist_ok=True)
def mostra(nom, url, h, codi):
    open(f"mostres_brut/{nom}.html", "w", encoding="utf-8").write(h)
    t = re.search(r"<title[^>]*>(.*?)</title>", h, re.S | re.I)
    print(f"{nom}: estat {codi}, {len(h)} bytes, títol: {re.sub(chr(10), ' ', t.group(1).strip())[:90] if t else '-'}")
    txt = re.sub(r"<[^>]+>", " ", h)
    for l in [re.sub(r"\s+", " ", x) for x in re.split(r"(?<=[a-z0-9])\s{2,}|\n", txt) if re.search(r"serradell", x, re.I)][:3]:
        print("    ", l[:200])
for nom, u in FFE:
    try:
        r = urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0 (compatible; club-escacs-vilafranca-proves)"}), timeout=60)
        mostra(nom, u, r.read().decode("utf-8", "replace"), r.status)
    except Exception as e:
        print(nom, "ERROR", str(e)[:100])
    time.sleep(1)
with sync_playwright() as p:
    b = p.chromium.launch(); pg = b.new_page()
    for nom, u in VESUS:
        try:
            r = pg.goto(u, wait_until="networkidle", timeout=90000); pg.wait_for_timeout(4000)
            mostra(nom, u, pg.content(), r.status if r else "?")
        except Exception as e:
            print(nom, "ERROR", str(e)[:100])
    b.close()
