#!/usr/bin/env python3
"""Exploració d'Info64: fitxa d'un jugador en un torneig per equips. Desa data/info64-equips-exploracio.json."""
import json, os
from playwright.sync_api import sync_playwright
URLS = ["/team/ceclub-segunda-division-norte-2026/club-ajedrez-alfaro/serradell-munoz-silvia",
        "/team/xvi-copa-de-espana-por-equipos-edades-sub-12/vilafranca/serradell-munoz-silvia",
        "/team/ceclub-segunda-division-norte-2026"]
out = {}
with sync_playwright() as p:
    b = p.chromium.launch()
    pg = b.new_page()
    pg.goto("https://info64.org/?hl=ca", wait_until="domcontentloaded", timeout=90000); pg.wait_for_timeout(2000)
    for u in URLS:
        d = {}
        try:
            pg.goto("https://info64.org" + u, wait_until="domcontentloaded", timeout=90000); pg.wait_for_timeout(6000)
            d["text"] = pg.evaluate("() => document.body.innerText")[:6000]
            d["ids"] = pg.evaluate("() => [...document.querySelectorAll('table')].map(t => [t.id, t.className, t.querySelectorAll('tr').length])")
            d["taula1"] = pg.evaluate("() => { const t = document.querySelector('#player-results') || document.querySelectorAll('table')[1]; return t ? t.outerHTML.slice(0, 3500) : ''; }")
            d["links"] = pg.evaluate("() => [...document.querySelectorAll('a[href]')].map(a => [a.getAttribute('href'), a.innerText.trim().slice(0,50)]).filter(x => x[0].startsWith('/team') || x[0].startsWith('#'))")[:40]
        except Exception as e:
            d["error"] = str(e)[:200]
        out[u] = d
    b.close()
os.makedirs("data", exist_ok=True)
json.dump(out, open("data/info64-equips-exploracio.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
