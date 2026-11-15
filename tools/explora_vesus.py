#!/usr/bin/env python3
"""Exploració de Vesus: pàgina d'inici (propers esdeveniments) i resum ESP d'un esdeveniment amb les rondes desplegades. Desa data/vesus-exploracio.json."""
import json, os
from playwright.sync_api import sync_playwright

out = []
with sync_playwright() as p:
    b = p.chromium.launch()
    pg = b.new_page(user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36")
    pg.goto("https://vesus.org/", wait_until="networkidle", timeout=60000); pg.wait_for_timeout(3000)
    out.append({"url": "home", "text": pg.evaluate("() => document.body.innerText")[:6000],
                "events": pg.evaluate("() => [...new Set([...document.querySelectorAll('a[href^=\"/event/\"]')].map(a => a.getAttribute('href')))]")})
    pg.goto("https://vesus.org/event/sTwKTWvd/federationSummary?federation=ESP", wait_until="networkidle", timeout=60000); pg.wait_for_timeout(3000)
    n = 0
    for l in pg.get_by_text("UNFOLD ALL").all():
        try: l.click(timeout=3000); n += 1
        except Exception as e: print("clic", str(e)[:80])
    pg.wait_for_timeout(3000)
    out.append({"url": "federationSummary", "clics": n, "text": pg.evaluate("() => document.body.innerText")[:9000]})
    pg.goto("https://vesus.org/tournament/2YMZzD3y?selectedTab=tournament.participants&rankedId=12&summaryType=PLAYER", wait_until="networkidle", timeout=60000); pg.wait_for_timeout(4000)
    out.append({"url": "jugador", "text": pg.evaluate("() => document.body.innerText")[:9000]})
    b.close()
os.makedirs("data", exist_ok=True)
json.dump(out, open("data/vesus-exploracio.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
