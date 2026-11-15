#!/usr/bin/env python3
"""Exploració de la FFE: grille americana de Narbona i el desplegable amb les partides d'un jugador. Desa data/ffe-grille-exploracio.json."""
import json, os, re
from playwright.sync_api import sync_playwright
URL = "https://www.echecs.asso.fr/Resultats.aspx?URL=Tournois/Id/70352/70352&Action=Ga"
out = {}
with sync_playwright() as p:
    b = p.chromium.launch()
    pg = b.new_page(user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36")
    xhr = []
    pg.on("response", lambda r: xhr.append([r.url, r.request.method, (r.request.post_data or "")[:200]]) if "echecs.asso.fr" in r.url and not re.search(r"\.(png|jpg|gif|css|js|ico|woff2?)(\?|$)", r.url) else None)
    try:
        pg.goto(URL, wait_until="domcontentloaded", timeout=90000); pg.wait_for_timeout(6000)
        out["caixes"] = pg.evaluate("""() => [...document.querySelectorAll('.papi_joueur_box')].filter(b => /SERRADELL/i.test(b.innerText)).map(b => b.outerHTML)""")
        out["n_caixes"] = pg.evaluate("() => document.querySelectorAll('.papi_joueur_box').length")
    except Exception as e:
        out["error"] = f"{type(e).__name__}: {str(e)[:300]}"
    b.close()
os.makedirs("data", exist_ok=True)
json.dump(out, open("data/ffe-grille-exploracio.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print({k: (len(v) if hasattr(v, "__len__") else v) for k, v in out.items()})
