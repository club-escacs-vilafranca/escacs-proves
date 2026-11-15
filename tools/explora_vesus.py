#!/usr/bin/env python3
"""Exploració de Vesus (vesus.org): estructura de les pàgines d'un esdeveniment i d'un torneig, peticions de xarxa (API) i enllaços. Desa data/vesus-exploracio.json."""
import json, re, sys, time
from playwright.sync_api import sync_playwright

PAGINES = ["https://vesus.org/event/sTwKTWvd", "https://vesus.org/tournament/MqLOlBXF", "https://vesus.org/tournament/gzam-Uzq", "https://vesus.org/tournament/2YMZzD3y"]
out = []
with sync_playwright() as p:
    b = p.chromium.launch()
    pg = b.new_page(user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36")
    reqs = []

    def resp(r):
        t = r.request.resource_type
        if t in ("xhr", "fetch", "document"):
            try:
                cos = r.text()[:400] if t != "document" else ""
            except Exception:
                cos = ""
            reqs.append({"estat": r.status, "tipus": t, "url": r.url[:200], "cos": cos})
    pg.on("response", resp)
    for u in PAGINES:
        reqs.clear()
        d = {"url": u}
        try:
            pg.goto(u, wait_until="networkidle", timeout=60000)
            pg.wait_for_timeout(3000)
            d["text"] = pg.evaluate("() => document.body.innerText")[:3500]
            d["titol"] = pg.title()
            d["enllacos"] = pg.evaluate("() => [...new Set([...document.querySelectorAll('a[href]')].map(a => a.getAttribute('href')))].slice(0, 60)")
            d["taules"] = pg.evaluate("() => [...document.querySelectorAll('table')].map(t => [...t.querySelectorAll('th')].map(h => h.innerText.trim()).slice(0, 14))")
            d["peticions"] = list(reqs)[:30]
        except Exception as e:
            d["error"] = f"{type(e).__name__}: {str(e)[:200]}"
        out.append(d)
        print(u, "->", d.get("error") or f"{len(d.get('text',''))} car., {len(d.get('peticions',[]))} peticions", flush=True)
    b.close()
import os
os.makedirs("data", exist_ok=True)
json.dump(out, open("data/vesus-exploracio.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
