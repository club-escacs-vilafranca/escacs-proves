#!/usr/bin/env python3
"""Resum d'una prova SENSE noms de rivals ni d'altres jugadors (el repositori és públic): només torneig, dates, rondes, punts i recompte de partides."""
import glob, json, os, sys
out = ["## Resum de la prova (sense dades d'altres jugadors)", ""]
for f in sorted(glob.glob("data/*-jugadors.json")) + ["data/resultats-jugadors.json"]:
    if not os.path.exists(f):
        continue
    try:
        r = json.load(open(f, encoding="utf-8")).get("resultats", [])
    except Exception as e:
        out.append(f"- {f}: no es pot llegir ({e})"); continue
    out += [f"### {f}: {len(r)} resultats", "", "| Font | Torneig | Fi | Rondes | Partides |", "|---|---|---|---|---|"]
    for x in sorted(r, key=lambda x: x.get("fi", ""), reverse=True):
        out.append(f"| {x.get('font','')} | {x.get('torneig','')} | {x.get('fi','')} | {x.get('rondes','')} | {len(x.get('partides', []))} |")
    out.append("")
txt = "\n".join(out); print(txt)
open(os.environ.get("GITHUB_STEP_SUMMARY", "/dev/null"), "a").write(txt + "\n")
