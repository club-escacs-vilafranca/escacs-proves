#!/usr/bin/env python3
"""Exploració de Vesus (vesus.org): cerca de jugadors. Desa data/vesus-exploracio.json."""
import json, os
from playwright.sync_api import sync_playwright

out = []
with sync_playwright() as p:
    b = p.chromium.launch()
    pg = b.new_page(user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36")
    reqs = []

    def resp(r):
        if r.request.resource_type in ("xhr", "fetch") and "graphql" in r.url:
            try:
                cos = r.text()[:4000]
            except Exception:
                cos = ""
            reqs.append({"post": (r.request.post_data or "")[:1500], "cos": cos})
    pg.on("response", resp)
    pg.goto("https://vesus.org/players", wait_until="networkidle", timeout=60000)
    pg.wait_for_timeout(2500)
    d = {"url": "players"}
    d["camps"] = pg.evaluate("() => [...document.querySelectorAll('input,select,button')].map(e => [e.tagName, e.type, e.name, e.placeholder, (e.innerText||'').trim().slice(0, 30), e.getAttribute('aria-label')]).slice(0, 40)")
    d["text"] = pg.evaluate("() => document.body.innerText")[:3000]
    d["enllacos"] = pg.evaluate("() => [...new Set([...document.querySelectorAll('a[href]')].map(a => a.getAttribute('href')))].slice(0, 60)")
    out.append(d)
    for cerca in ("54764130", "Serradell"):
        reqs.clear()
        e = {"cerca": cerca}
        try:
            inp = pg.locator("input[type=text], input[type=search], input:not([type])").first
            inp.fill(cerca)
            inp.press("Enter")
            pg.wait_for_timeout(4000)
            e["text"] = pg.evaluate("() => document.body.innerText")[:3500]
            e["taules"] = pg.evaluate("() => [...document.querySelectorAll('table')].map(t => [...t.querySelectorAll('tr')].slice(0, 6).map(r => [...r.children].map(c => c.innerText.trim().replace(/\\s+/g, ' ')).slice(0, 12)))")
            e["enllacos"] = pg.evaluate("() => [...new Set([...document.querySelectorAll('a[href]')].map(a => a.getAttribute('href')))].filter(h => /player|user|tournament|event/.test(h)).slice(0, 30)")
            e["peticions"] = list(reqs)
        except Exception as ex:
            e["error"] = f"{type(ex).__name__}: {str(ex)[:200]}"
        out.append(e)
        print(cerca, e.get("error") or "ok", flush=True)
    b.close()
os.makedirs("data", exist_ok=True)
json.dump(out, open("data/vesus-exploracio.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
