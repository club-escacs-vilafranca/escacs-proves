#!/usr/bin/env python3
"""Prova: ratings.fide.com des de GitHub amb navegador real. Per a cada ID: títol, estat i els torneigs que surten al llistat de càlculs de cada període des del gener."""
import re, sys
from playwright.sync_api import sync_playwright
IDS = sys.argv[1:] or ["54764130", "94761418"]
with sync_playwright() as p:
    b = p.chromium.launch(); pg = b.new_page(user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36")
    for i in IDS:
        for u in (f"https://ratings.fide.com/profile/{i}", f"https://ratings.fide.com/profile/{i}/calculations"):
            try:
                r = pg.goto(u, wait_until="domcontentloaded", timeout=45000); pg.wait_for_timeout(3000)
                t = re.sub(r"\s+", " ", pg.inner_text("body"))
                print(f"{u} -> {r.status if r else '?'} | {pg.title()[:60]} | {len(t)} car.")
                for m in re.finditer(r"(20\d\d-\d\d-\d\d)[^|]{0,120}", t[:20000]):
                    pass
                print("   ", t[:300])
            except Exception as e:
                print(f"{u} -> ERROR {str(e)[:100]}")
        for per in ("2026-10-01", "2026-05-01"):
            u = f"https://ratings.fide.com/a_indv_calculations.php?id_number={i}&rating_period={per}&t=0"
            try:
                r = pg.goto(u, wait_until="domcontentloaded", timeout=45000); pg.wait_for_timeout(2000)
                t = re.sub(r"\s+", " ", pg.inner_text("body"))
                print(f"{u} -> {r.status if r else '?'} | {len(t)} car. | {t[:400]}")
            except Exception as e:
                print(f"{u} -> ERROR {str(e)[:100]}")
    b.close()
