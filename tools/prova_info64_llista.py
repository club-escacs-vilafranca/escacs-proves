#!/usr/bin/env python3
"""Diagnòstic d'Info64: llista TOTES les files que la cerca torna per als cognoms indicats i que contenen els noms autoritzats, sense cap filtre
(ni data, ni partides jugades, ni coincidència exacta del nom), i diu per què l'importador les descartaria. No desa res."""
import re, sys
from playwright.sync_api import sync_playwright
sys.path.insert(0, "tools")
import info64 as I
NOMS = ("silvia", "andrea")
ESPERATS = {"silvia": "serradell munoz silvia", "andrea": "serradell villa andrea"}
with sync_playwright() as p:
    b = p.chromium.launch(); pg = b.new_page()
    vistos = set()
    from bs4 import BeautifulSoup
    pg.goto("https://info64.org/?hl=ca", wait_until="domcontentloaded", timeout=90000); pg.wait_for_timeout(3000)
    s0 = BeautifulSoup(pg.content(), "html.parser")
    print("ENLLAÇOS del menú:", [(a.get_text(" ", strip=True)[:30], a["href"]) for a in s0.select("a[href]") if re.search(r"search|cerca|player|jugador|buscar", (a["href"] + a.get_text()).lower())][:20])
    print("FORMULARIS:", [(f.get("action"), [i.get("name") for i in f.select("input")]) for f in s0.select("form")][:6])
    for u in ("/search-player", "/search-player?hl=ca", "/search-player?hl=ca&name=serradell", "/search-player?name=serradell"):
        r = pg.goto("https://info64.org" + u, wait_until="domcontentloaded", timeout=90000); pg.wait_for_timeout(3000)
        s = BeautifulSoup(pg.content(), "html.parser")
        print(f"GET {u} -> estat {r.status if r else '?'} | URL final {pg.url} | títol {pg.title()}")
        print("   inputs:", [(i.get("name"), i.get("type"), i.get("placeholder")) for i in s.select("input")][:10], "| botons:", [b.get_text(strip=True)[:20] for b in s.select("button")][:6])
    pg.goto("https://info64.org/search-player?hl=ca", wait_until="domcontentloaded", timeout=90000); pg.wait_for_timeout(3000)
    try:
        pg.fill("input[name=name], input[type=text], input[type=search]", "serradell")
        pg.keyboard.press("Enter"); pg.wait_for_timeout(5000)
        s = BeautifulSoup(pg.content(), "html.parser")
        print("Després d'escriure i Enter -> URL", pg.url, "| files tbody:", len(s.select("table tbody tr")))
        for tr in s.select("table tbody tr")[:40]:
            tx = re.sub(r"\s+", " ", tr.get_text(" ", strip=True))
            if re.search(r"silvia|andrea", I.sa(tx)): print("   ", tx[:200])
    except Exception as e:
        print("no s'ha pogut escriure a la cerca:", str(e)[:150])
    b.close()
raise SystemExit
