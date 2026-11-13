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
    pg.goto("https://info64.org/search-player?name=serradell", wait_until="domcontentloaded", timeout=90000); pg.wait_for_timeout(5000)
    s = BeautifulSoup(pg.content(), "html.parser")
    rows = s.select("table tbody tr")
    print("Cerca sense hl=ca: URL", pg.url, "| files:", len(rows))
    print("Capçalera:", [th.get_text(strip=True) for th in s.select("table thead th")])
    mine = []
    for tr in rows:
        td = tr.select("td"); tx = re.sub(r"\s+", " ", tr.get_text(" ", strip=True))
        if re.search(r"silvia|andrea", I.sa(tx)) and "serradell" in I.sa(tx):
            a1 = td[1].select_one("a") if len(td) > 1 else None
            print("  ", tx[:210], "|", a1["href"] if a1 else "")
            mine.append(a1["href"] if a1 else None)
    print("Files de les dues:", len(mine))
    for h in [x for x in mine if x][:2]:
        for suf in ("", "?hl=ca"):
            r = pg.goto("https://info64.org" + h + suf, wait_until="domcontentloaded", timeout=90000); pg.wait_for_timeout(3000)
            print(f"fitxa {h}{suf} -> URL final {pg.url} | títol {pg.title()}")
    b.close()
raise SystemExit
