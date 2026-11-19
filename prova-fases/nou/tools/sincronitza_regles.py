"""Sincronitza data/inscripcio-regles.json amb els camps estructurats `dades`
de l'edició de l'any configurat (regles["any"]). Només s'escriuen els camps
que tenen valor; res de xarxa. Ús: python tools/sincronitza_regles.py [arrel]"""
import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from edicions import tornejos

TORNEIGS = {"obert-vilafranca": "obert", "rapides-obert": "rapides", "rapides-festa-major": "rapides-festa-major",
            "nadal": "nadal", "torneig-femeni": "femeni", "final-de-curs": "final-de-curs", "marato-tv3": "marato", "gegant-escolar": "gegant"}
RITME = {"classic": "std", "rapid": "rapid", "blitz": "blitz"}
CAMPS = ["preu_general", "preu_menor", "preu_major", "preu_club",
         "elo_gratis", "menor_fins_sub", "major_des_de"]


def sincronitza(arrel="."):
    pr = os.path.join(arrel, "data", "inscripcio-regles.json")
    with open(pr, encoding="utf-8") as f:
        text = f.read()
    regles = json.loads(text)
    canvis = []
    for fitxer, clau in TORNEIGS.items():
        t = next((d for f, d in tornejos(arrel) if d.get("id") == fitxer), None)
        if t is None or clau not in regles.get("tornejos", {}):
            continue
        ed = next((e for e in t.get("editions", [])
                   if str(e.get("year")) == str(regles.get("any"))), None)
        d = (ed or {}).get("abans", {}).get("dades") or {}
        dest = regles["tornejos"][clau]
        nou = {k: d[k] for k in CAMPS if d.get(k) not in (None, "")}
        if d.get("dies"):
            nou["data_inici"] = sorted(d["dies"])[0]
        if d.get("modalitat") in RITME:
            nou["ritme"] = RITME[d["modalitat"]]
        for k, v in nou.items():
            if dest.get(k) != v:
                canvis.append((clau, k, dest.get(k), v))
                dest[k] = v
    if canvis:
        with open(pr, "w", encoding="utf-8") as f:
            f.write(json.dumps(regles, ensure_ascii=False, indent=1))
    return canvis


if __name__ == "__main__":
    for c in sincronitza(sys.argv[1] if len(sys.argv) > 1 else "."):
        print("canvi", *c)
