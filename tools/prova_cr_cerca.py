#!/usr/bin/env python3
"""Diagnòstic de la cerca de jugador de Chess-Results (el que fa jugadors.py): quantes files torna, en quin ordre, si hi ha paginació, i quines files de 2026 hi surten."""
import re, sys, html
sys.argv = ["x"]
sys.path.insert(0, "tools")
import jugadors as J
for fide in ("54764130",):
    t = J.cr_cerca(fide=fide)
    trs = re.findall(r"<tr[^>]*class=\"CRg[12]b?\"[^>]*>(.*?)</tr>", t, re.S)
    rows = []
    for tr in trs:
        tds = re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", tr, re.S)
        if len(tds) >= 10:
            rows.append([html.unescape(re.sub(r"<[^>]+>", "", x)).strip() for x in tds])
    print(f"fide {fide}: {len(trs)} files de taula, {len(rows)} amb ≥10 columnes; mida pàgina {len(t)}")
    print("paginació/avís:", re.findall(r"(?i)(page\s*\d+|siguiente|next|more than|m[aà]s de|only the first|mostrant[^<]{0,60}|\d+\s*(?:rows|files|filas)[^<]{0,40})", re.sub(r"<[^>]+>", " ", t))[:8])
    print("ordre de dates (primeres 3 / últimes 3):", [r[6] for r in rows[:3]], [r[6] for r in rows[-3:]])
    for r in rows:
        if r[6].startswith(("2026", "2027")) and r[6] >= "2026/10":
            print("  ", r[6], "|", r[5][:70], "| lloc", r[7], "| rondes", r[8], "| de", r[9])
    print("Sunway/Bali a la llista:", [r[5][:50] for r in rows if re.search(r"sunway|bali", r[5], re.I)][:6])
