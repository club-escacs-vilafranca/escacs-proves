#!/usr/bin/env python3
"""Exploració de Vesus: com es passa d'un torneig d'un llistat al seu esdeveniment."""
import json, os
from playwright.sync_api import sync_playwright
out = {}
with sync_playwright() as p:
    b = p.chromium.launch()
    pg = b.new_page(user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36")
    pg.goto("https://vesus.org/inprogress", wait_until="networkidle", timeout=60000); pg.wait_for_timeout(3000)
    out["cards"] = pg.evaluate("""() => [...document.querySelectorAll('a[href^="/tournament/"]')].slice(0, 6).map(a => ({href: a.getAttribute('href'), txt: a.innerText.slice(0, 80), pare: (a.closest('[class]') || {}).className, html: (a.parentElement.parentElement.outerHTML || '').slice(0, 700)}))""")
    out["event_links"] = pg.evaluate("""() => [...document.querySelectorAll('a[href^="/event/"]')].map(a => [a.getAttribute('href'), a.innerText.slice(0, 60), (a.closest('[class]')||{}).className])""")
    t0 = out["cards"][0]["href"]
    pg.goto("https://vesus.org" + t0, wait_until="networkidle", timeout=60000); pg.wait_for_timeout(3000)
    out["tornejos_enllacos"] = pg.evaluate("() => [...document.querySelectorAll('a[href]')].map(a => [a.getAttribute('href'), a.innerText.slice(0, 50)]).filter(x => !/^\\/(account|content|shop|contacts|donate|games|players|archive|inprogress)/.test(x[0]))")[:40]
    out["tornejos_text"] = pg.evaluate("() => document.body.innerText")[:1500]
    b.close()
os.makedirs("data", exist_ok=True)
json.dump(out, open("data/vesus-exploracio.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
