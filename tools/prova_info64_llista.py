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
    for q in ("serradell", "serradell munoz", "serradell villa", "munoz serradell"):
        try:
            files = I.cerca(pg, q)
        except Exception as e:
            print(f"cerca '{q}': ERROR {str(e)[:100]}"); continue
        print(f"cerca '{q}': {len(files)} files")
        for f in files:
            n = I.sa(f["nom"].replace(",", " "))
            if "serradell" not in n or not any(x in n for x in NOMS): continue
            k = (f["nom"], f["href_t"])
            if k in vistos: continue
            vistos.add(k)
            quin = next(x for x in NOMS if x in n)
            motius = []
            if n != ESPERATS[quin]: motius.append(f"nom diferent de «{ESPERATS[quin]}»")
            if re.search(r"tecnificaci", f["torneig"], re.I): motius.append("tecnificació")
            print(f"  {f['nom']} | {f['torneig']} | {f['inici']} → {f['fi']} | {'DESCARTAT: ' + ', '.join(motius) if motius else 'passa el filtre de nom'}")
    b.close()
print(f"Total files úniques de les dues: {len(vistos)}")
