#!/usr/bin/env python3
"""Puntuació del Minicircuit del Penedès des de Chess-Results.

Per a cada jornada ja jugada que té enllaços de Chess-Results (camp «crs»), llegeix la classificació final
(art=1) i en treu els 5 primers de cada categoria:
  - grup general (o qualsevol enllaç que no digui «sub»)  -> Adults federats / Adults no federats
  - enllaç que diu «sub» (p. ex. «Grup sub-12»)           -> Sub-12 federats / Sub-12 no federats
Federat = té Elo a Chess-Results (>0); Elo 0 = no federat (criteri de l'Andrea).
Els noms es desen com «Nom Primer-cognom». Si la jornada ja té `puntuacio`, no es toca (el CMS mana)
llevat que es passi --refes.

Ús: python3 tools/classificacio_circuit.py [--refes] [--local carpeta]   (la carpeta té un .html per enllaç, per proves)
"""
import datetime, json, re, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from importar_chessresults import baixa, taula, nom_public, num, trobacol

F = Path(__file__).resolve().parent.parent / "data" / "torneig-minicircuit-penedes.json"


def classifica(html):
    """Llista de (ordre, nom, elo) des de la taula de classificació; None si no es reconeix."""
    files, _ = taula(html)
    if not files:
        return None
    cap = files[0]
    ix = {c: i for i, c in enumerate(cap)}
    c_nom, c_elo, c_rk = trobacol(ix, "Nom", "Name"), trobacol(ix, "Elo", "Rtg"), trobacol(ix, "Ordre", "Rk.", "Rk", "Lloc")
    if c_nom is None or c_elo is None:
        return None
    out = []
    for n, f in enumerate(files[1:], 1):
        if len(f) <= max(c_nom, c_elo):
            continue
        rk = f[c_rk] if c_rk is not None and c_rk < len(f) else ""
        out.append((int(rk) if rk.isdigit() else n, f[c_nom], num(f[c_elo], int) or 0))
    return out


def puntuacio(grups):
    """grups: [(és_sub12, classificació)] -> llista de {cat, lloc, nom}."""
    res = []
    for sub, cl in grups:
        for fed in (True, False):
            cat = ("Sub-12 " if sub else "Adults ") + ("federats" if fed else "no federats")
            sel = sorted([x for x in cl if (x[2] > 0) == fed])[:5]
            res += [{"cat": cat, "lloc": i, "nom": nom_public(x[1])} for i, x in enumerate(sel, 1)]
    return res


def main():
    refes = "--refes" in sys.argv
    local = sys.argv[sys.argv.index("--local") + 1] if "--local" in sys.argv else None
    d = json.load(open(F, encoding="utf-8"))
    avui = datetime.date.today().isoformat()
    canvis = 0
    for ed in d["editions"]:
        for j in ed.get("jornades", []):
            if j.get("estat") == "suspesa" or not j.get("crs") or j["d"] >= avui or (j.get("puntuacio") and not refes):
                continue
            grups = []
            for k, c in enumerate(j["crs"]):
                try:
                    if local:
                        h = open(Path(local) / f"{j['d']}_{k}.html", encoding="utf-8").read()
                    else:
                        time.sleep(1)
                        h = baixa(re.sub(r"&?art=\d+", "", c["url"]) + "&art=1&zeilen=99999")
                    cl = classifica(h)
                except Exception as e:
                    print(f"{j['d']} {c['nom']}: error {e}")
                    cl = None
                if not cl:
                    print(f"{j['d']} {c['nom']}: no s'ha pogut llegir la classificació; es deixa tal com està")
                    grups = None
                    break
                grups.append(("sub" in c["nom"].lower(), cl))
            if not grups:
                continue
            j["puntuacio"] = puntuacio(grups)
            canvis += 1
            print(f"{j['d']} {j['lloc'].split(' · ')[0]}: puntuació omplerta ({len(j['puntuacio'])} files)")
            for x in j["puntuacio"]:
                print("   ", x["cat"], x["lloc"], x["nom"])
    if canvis:
        json.dump(d, open(F, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        open(F, "a").write("\n")
    else:
        print("Res a canviar.")


if __name__ == "__main__":
    main()
