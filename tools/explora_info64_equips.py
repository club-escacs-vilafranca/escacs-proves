#!/usr/bin/env python3
"""Exploració d'Info64: com surten els torneigs per equips (CEclub) a la cerca de jugadors i com és la pàgina d'un equip. Desa data/info64-equips-exploracio.json."""
import json, os, re
from playwright.sync_api import sync_playwright
out = {}
with sync_playwright() as p:
    b = p.chromium.launch()
    pg = b.new_page()
    pg.goto("https://info64.org/?hl=ca", wait_until="domcontentloaded", timeout=90000); pg.wait_for_timeout(2000)
    files = []
    for nom in ("Serradell", "Palou"):
        pg.goto("https://info64.org/search-player?name=" + nom, wait_until="domcontentloaded", timeout=90000); pg.wait_for_timeout(4000)
        files += pg.evaluate("""() => [...document.querySelectorAll('table tbody tr')].map(tr => [...tr.querySelectorAll('td')].map(td => td.innerText.trim().replace(/\\s+/g,' ') + ' ' + ([...td.querySelectorAll('a')].map(a => '<' + a.getAttribute('href') + '>').join(''))))""")
    out["cerca"] = files
    equips = [f for f in files if any('/team/' in c for c in f)]
    out["equips"] = equips
    for k, hrefs in enumerate(["CEclub", "Segunda"]):
        pass
    # torneig per equips de l'agost (Oviedo): prova de cercar-lo
    pg.goto("https://info64.org/search-tournament?name=CEclub", wait_until="domcontentloaded", timeout=90000); pg.wait_for_timeout(4000)
    out["cerca_torneig"] = pg.evaluate("() => document.body.innerText")[:1500]
    out["cerca_torneig_links"] = pg.evaluate("() => [...document.querySelectorAll('a[href]')].map(a => [a.getAttribute('href'), a.innerText.trim().slice(0,60)]).filter(x => /team|torneo|tournament|ceclub/i.test(x[0] + x[1]))")[:40]
    mostra = None
    for f in equips[:1]:
        for c in f:
            m = re.search(r"<(/team/[^>]+)>", c)
            if m: mostra = m.group(1)
    if mostra:
        pg.goto("https://info64.org" + mostra, wait_until="domcontentloaded", timeout=90000); pg.wait_for_timeout(6000)
        out["mostra_url"] = mostra
        out["mostra_text"] = pg.evaluate("() => document.body.innerText")[:5000]
        out["mostra_links"] = pg.evaluate("() => [...document.querySelectorAll('a[href]')].map(a => [a.getAttribute('href'), a.innerText.trim().slice(0,60)])")[:60]
    b.close()
os.makedirs("data", exist_ok=True)
json.dump(out, open("data/info64-equips-exploracio.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print({k: (len(v) if hasattr(v, "__len__") else v) for k, v in out.items()})
