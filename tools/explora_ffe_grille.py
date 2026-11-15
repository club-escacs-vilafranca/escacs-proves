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
        out["xhr"] = list(xhr)[:20]
        out["titol"] = pg.title()
        out["fila"] = pg.evaluate("""() => { const tds = [...document.querySelectorAll('td')].filter(t => /SERRADELL/i.test(t.innerText)); return tds.slice(0, 3).map(t => ({txt: t.innerText.slice(0, 80), html: t.outerHTML.slice(0, 1500), tr: t.closest('tr') ? t.closest('tr').outerHTML.slice(0, 3000) : ''})); }""")
        out["scripts_tooltip"] = pg.evaluate("() => [...document.querySelectorAll('[onmouseover],[onmouseenter],[data-tooltip],[title]')].filter(e => /SERRADELL|Serradell/i.test(e.outerHTML)).slice(0, 5).map(e => e.outerHTML.slice(0, 1500))")
        # passa el ratolí sobre el nom
        loc = pg.get_by_text(re.compile("SERRADELL", re.I)).first
        loc.hover(); pg.wait_for_timeout(2500)
        out["despres_hover"] = pg.evaluate("() => document.body.innerText")[:200]
        out["tooltips_visibles"] = pg.evaluate("() => [...document.querySelectorAll('div,span,table')].filter(e => { const s = getComputedStyle(e); return (s.position === 'absolute' || s.position === 'fixed') && e.offsetWidth > 50 && e.offsetHeight > 30 && s.display !== 'none' && s.visibility !== 'hidden'; }).slice(0, 8).map(e => e.outerHTML.slice(0, 2500))")
        out["xhr_final"] = list(xhr)[:30]
    except Exception as e:
        out["error"] = f"{type(e).__name__}: {str(e)[:300]}"
    b.close()
os.makedirs("data", exist_ok=True)
json.dump(out, open("data/ffe-grille-exploracio.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print({k: (len(v) if hasattr(v, "__len__") else v) for k, v in out.items()})
