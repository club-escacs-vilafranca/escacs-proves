#!/usr/bin/env python3
"""Revisió de federats/no federats del Minicircuit amb la llista de la FCE.

Compara cada jugador de la «Puntuació del circuit» (federat / no federat segons el web) amb la llista de jugadors
federats de la FCE (data/brut/fce_tots.json.gz, que baixa l'acció mensual de la llista d'inscripció) i escriu les
possibles discrepàncies a data/revisio-federats.json perquè l'Andrea les valida o corregeix al CMS.
  - consta com a no federat al web però és a la FCE      -> possible federat
  - consta com a federat al web però no és a la FCE      -> possible no federat
Un nom que coincideix amb diversos jugadors de la FCE no es marca (no es pot saber qui és).
Es conserva el que l'Andrea ja hagi marcat (revisat, decisió, nota) de cada element.

Ús: python3 tools/revisio_federats.py
"""
import gzip, json, re, unicodedata
from datetime import date
from pathlib import Path

ARREL = Path(__file__).resolve().parent.parent
FCE = ARREL / "data/brut/fce_tots.json.gz"
CIRCUIT = ARREL / "data/torneig-minicircuit-penedes.json"
SORTIDA = ARREL / "data/revisio-federats.json"


def norm(s):
    s = unicodedata.normalize("NFD", s or "")
    return re.sub(r"[^a-z0-9 ]+", " ", "".join(c for c in s if unicodedata.category(c) != "Mn").lower()).strip()


def main():
    if not FCE.exists():
        print("Falta data/brut/fce_tots.json.gz (el baixa l'acció «Llista de jugadors per a les inscripcions»).")
        return
    fce = json.load(gzip.open(FCE, "rt", encoding="utf-8"))["jugadors"]
    for x in fce:
        x["_tk"] = set(norm(x["n"]).split())
    antic = {}
    if SORTIDA.exists():
        for e in json.load(open(SORTIDA, encoding="utf-8")).get("elements", []):
            antic[(e["jornada"], e["nom"])] = e
    elements = []
    d = json.load(open(CIRCUIT, encoding="utf-8"))
    for ed in d["editions"]:
        for j in ed.get("jornades", []):
            etiq = j["d"] + " · " + j["lloc"].split(" · ")[0]
            for p in j.get("puntuacio") or []:
                tk = set(norm(p["nom"]).split())
                c = [x for x in fce if tk <= x["_tk"]] if tk else []
                fed = p["cat"].split()[1] == "federats"
                if fed and c:
                    continue                      # federat al web i a la FCE (o nom ambigu): res a revisar
                if not fed and len(c) != 1:
                    continue                      # no federat al web i no és a la FCE (o nom ambigu): res a revisar
                if fed:
                    fce_txt, prop = "No és a la llista de la FCE", "Passar-lo a «no federat»"
                else:
                    x = c[0]
                    fce_txt = "Federat a la FCE: %s · %s · Elo %s" % (x["n"], x["cl"].title(), x["e"] or "—")
                    prop = "Passar-lo a «federat» (si és la mateixa persona)"
                prev = antic.get((etiq, p["nom"]), {})
                elements.append({"jornada": etiq, "nom": p["nom"], "web": "%s (lloc %s)" % (p["cat"], p["lloc"]), "fce": fce_txt, "proposta": prop,
                                 "revisat": bool(prev.get("revisat")), "decisio": prev.get("decisio", ""), "nota": prev.get("nota", "")})
    out = {"actualitzat": date.today().isoformat(), "elements": elements}
    json.dump(out, open(SORTIDA, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    open(SORTIDA, "a").write("\n")
    print(len(elements), "possibles discrepàncies")
    for e in elements:
        print("  ", e["jornada"], "|", e["nom"], "|", e["web"], "|", e["fce"])


if __name__ == "__main__":
    main()
