#!/usr/bin/env python3
"""Baixa de la FCE les partides amb la variació d'Elo de cada avaluació (mes) dels jugadors del club.

Mateixa crida que fa la pàgina «Avaluació ELO» (op=13): POST a resultatCerca.php amb tb=fce_partides i idAvaluacio.
  9999 = «Variació pendent» (partides ja jugades que encara no han entrat a cap llista; és la previsió de la FCE)
  188 = nov26, 187 = oct26 ... 179 = feb26, 178 = gen26
Desa data/brut/fce_aval/<avaluacio>.json.gz  ->  {idJugador: [files de partides tal com les dona la FCE]}.
Reprèn on s'havia quedat (les avaluacions tancades no es tornen a demanar; la 9999 es refà sempre).
Ús:  python3 tools/fce_avaluacions.py --aval 9999,188 [--jugadors 382950,...] [--max 20]
"""
import argparse, gzip, json, os, sys, time
sys.path.insert(0, os.path.dirname(__file__))
from xarxa import req

FCE = "https://escacs.cat/components/com_fce/gmvw20/conn/resultatCerca.php"
CAP = {"X-Requested-With": "XMLHttpRequest", "Referer": "https://escacs.cat/index.php/component/fce?op=13", "Origin": "https://escacs.cat"}
DIR = "data/brut/fce_aval"


def partides(idj, aval):
    t = req(FCE, {"tb": "fce_partides", "idJugador": idj, "nom": "", "torneig": "", "idAvaluacio": aval,
                  "nomFitxa": "c_partides_elo_0.xml", "dadesCercar": "partides_elo_0.xml"}, CAP)
    j = json.loads(t)
    src = j.get("source") or {}
    return src.get("localdata") if isinstance(src, dict) else j.get("localdata") or []


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--aval", default="9999")
    ap.add_argument("--jugadors", default="")
    ap.add_argument("--max", type=int, default=0, help="màxim de crides en aquesta execució (0 = sense límit)")
    a = ap.parse_args()
    ids = [x for x in a.jugadors.split(",") if x] or [str(j["id"]) for j in json.load(open("data/jugadors.json", encoding="utf-8"))["jugadors"]]
    os.makedirs(DIR, exist_ok=True)
    crides = errors_seguits = 0
    for aval in [x for x in a.aval.split(",") if x]:
        fitxer = os.path.join(DIR, aval + ".json.gz")
        dades = {}
        if os.path.exists(fitxer) and aval != "9999":
            dades = json.load(gzip.open(fitxer, "rt", encoding="utf-8"))
        nous = 0
        for idj in ids:
            if idj in dades:
                continue
            if a.max and crides >= a.max:
                break
            try:
                dades[idj] = partides(idj, aval)
                errors_seguits = 0
                nous += 1
            except Exception as e:
                errors_seguits += 1
                print("  error", aval, idj, str(e)[:80])
                if errors_seguits >= 6:
                    print("Massa errors seguits: paro (possible bloqueig o 429)."); break
            crides += 1
            time.sleep(1.2)
        with gzip.open(fitxer, "wt", encoding="utf-8") as f:
            json.dump(dades, f, ensure_ascii=False, separators=(",", ":"))
        print(f"avaluació {aval}: {nous} jugadors nous, {len(dades)} en total, {sum(1 for v in dades.values() if v)} amb partides")
        if errors_seguits >= 6 or (a.max and crides >= a.max):
            break


if __name__ == "__main__":
    main()
