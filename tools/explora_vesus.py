#!/usr/bin/env python3
"""Exploració de Vesus (vesus.org): llistats d'esdeveniments i resum per federació. Desa data/vesus-exploracio.json."""
import json, os
from playwright.sync_api import sync_playwright

PAGINES = ["https://vesus.org/inprogress", "https://vesus.org/archive", "https://vesus.org/event/sTwKTWvd/federationSummary?federation=ESP"]
out = []
with sync_playwright() as p:
    b = p.chromium.launch()
    pg = b.new_page(user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36")
    reqs = []
    pg.on("response", lambda r: reqs.append({"post": (r.request.post_data or "")[:600], "cos": ""}) if "graphql" in r.url and r.request.method == "POST" else None)
    for u in PAGINES:
        reqs.clear()
        d = {"url": u}
        try:
            pg.goto(u, wait_until="networkidle", timeout=60000)
            pg.wait_for_timeout(3000)
            d["text"] = pg.evaluate("() => document.body.innerText")[:4500]
            d["n_events"] = pg.evaluate("() => new Set([...document.querySelectorAll('a[href^=\"/event/\"]')].map(a => a.getAttribute('href'))).size")
            d["enllacos"] = pg.evaluate("() => [...new Set([...document.querySelectorAll('a[href]')].map(a => a.getAttribute('href')))].filter(h => !/^\\/(account|content|shop|contacts|donate|games)/.test(h)).slice(0, 50)")
            d["camps"] = pg.evaluate("() => [...document.querySelectorAll('input,select')].map(e => [e.tagName, e.type, e.name, e.placeholder, e.value]).slice(0, 20)")
            d["taules"] = pg.evaluate("() => [...document.querySelectorAll('table')].map(t => [...t.querySelectorAll('tr')].slice(0, 8).map(r => [...r.children].map(c => c.innerText.trim().replace(/\\s+/g, ' ')).slice(0, 12)))")
            d["peticions"] = list(reqs)[:8]
            h0 = pg.evaluate("() => document.body.scrollHeight")
            pg.mouse.wheel(0, 6000); pg.wait_for_timeout(2500)
            d["scroll"] = [h0, pg.evaluate("() => document.body.scrollHeight"), pg.evaluate("() => new Set([...document.querySelectorAll('a[href^=\"/event/\"]')].map(a => a.getAttribute('href'))).size")]
        except Exception as e:
            d["error"] = f"{type(e).__name__}: {str(e)[:200]}"
        out.append(d)
        print(u, d.get("error") or f"events={d.get('n_events')} scroll={d.get('scroll')}", flush=True)
    b.close()
os.makedirs("data", exist_ok=True)
json.dump(out, open("data/vesus-exploracio.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
