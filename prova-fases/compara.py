#!/usr/bin/env python3
"""Compara dos directoris data/ ignorant els camps «actualitzat». Resum (sense dades personals) a stdout; el detall, al fitxer indicat (xifrat després)."""
import difflib, os, re, sys
a, b, detall = sys.argv[1:4]
def llegeix(p):
    return re.sub(r'"actualitzat": "[^"]*"', '"actualitzat": "X"', open(p, "rb").read().decode("utf8", "ignore"))
fa = {os.path.relpath(os.path.join(r, f), a) for r, _, fs in os.walk(a) for f in fs}
fb = {os.path.relpath(os.path.join(r, f), b) for r, _, fs in os.walk(b) for f in fs}
dif, nomes_a, nomes_b = [], sorted(fa - fb), sorted(fb - fa)
for f in sorted(fa & fb):
    if llegeix(os.path.join(a, f)) != llegeix(os.path.join(b, f)):
        dif.append(f)
with open(detall, "w", encoding="utf-8") as o:
    for f in dif:
        o.write(f"=== {f}\n")
        o.writelines(list(difflib.unified_diff(llegeix(os.path.join(a, f)).splitlines(True), llegeix(os.path.join(b, f)).splitlines(True), "antic", "nou", n=1))[:120])
print(f"fitxers comuns: {len(fa & fb)}; només al codi antic: {len(nomes_a)}; només al nou: {len(nomes_b)}; amb diferències: {len(dif)}")
for f in dif[:30]: print("  difereix:", f)
for f in nomes_a[:15]: print("  només antic:", f)
for f in nomes_b[:15]: print("  només nou:", f)
