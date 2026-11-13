#!/usr/bin/env python3
"""FIDE: veu quines peticions fa la pestanya «Calculations» del perfil i què retornen; desa les respostes a mostres_brut/ (es xifren). Al log: només URL, estat i mida."""
import os, re, sys
from playwright.sync_api import sync_playwright
os.makedirs("mostres_brut", exist_ok=True)
ID = sys.argv[1] if len(sys.argv) > 1 else "54764130"
with sync_playwright() as p:
    b = p.chromium.launch(); ctx = b.new_context(user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"); pg = ctx.new_page()
    n = [0]
    def resp(r):
        u = r.url
        if "fide.com" in u and re.search(r"a_|ajax|calc|profile|rating", u) and not re.search(r"\.(js|css|png|jpg|svg|woff2?)(\?|$)", u):
            try:
                body = r.body()
            except Exception:
                body = b""
            n[0] += 1
            print(f"  {r.request.method} {r.status} {len(body)} B  {u[:150]}")
            open(f"mostres_brut/fide_{n[0]:02d}.html", "wb").write(body)
    pg.on("response", resp)
    for intent in range(1, 6):
        try:
            pg.goto(f"https://ratings.fide.com/profile/{ID}/calculations", wait_until="domcontentloaded", timeout=45000); pg.wait_for_timeout(8000)
            print(f"càrrega correcta a l'intent {intent}"); break
        except Exception as e:
            print(f"intent {intent}: timeout"); pg.wait_for_timeout(10000)
    else:
        raise SystemExit("FIDE no respon després de 5 intents")
    print("selectors de període:", pg.eval_on_selector_all("select option", "els => els.slice(0,6).map(e => e.value + '|' + e.textContent.trim())"))
    # canvia el període a l'últim i a un de més antic
    for sel in pg.query_selector_all("select"):
        try:
            vals = sel.eval_on_selector_all("option", "els => els.map(e => e.value)")
            if len(vals) > 3 and any(re.match(r"20\d\d-\d\d", v) for v in vals):
                for v in (vals[1], vals[5]):
                    sel.select_option(v); pg.wait_for_timeout(3000)
                break
        except Exception as e:
            print("select error", str(e)[:80])
    b.close()
