"""Protecció contra duplicats: el mateix jugador no pot sortir dues vegades al mateix torneig.

Un torneig pot arribar per més d'una via: dues adreces de Chess-Results (grups o fases amb noms diferents, com Santa Margarida), Chess-Results i Info64,
Info64 i Vesus, un CSV entrat a mà... Dos resultats del mateix jugador són el mateix torneig si acaben el mateix dia, tenen el mateix ritme i els noms
comparteixen almenys la meitat de les paraules (el mateix jugador no pot jugar dos torneigs alhora). Se'n queda un de sol: el de la font més fiable
i, a igualtat, el que té més partides.
"""
import re
import unicodedata

ORDRE = ["chess-results", "info64", "ffe", "vesus", "manual"]      # primer = més fiable
SENSE_PARAULA = {"torneo", "torneig", "open", "campionat", "campeonato", "copa", "trofeu", "trofeo", "internacional", "internacionales", "memorial", "ronda", "rondas"}


def _norm(n):
    return "".join(c for c in unicodedata.normalize("NFD", (n or "").lower()) if unicodedata.category(c) != "Mn")


def mots(n):
    return {w for w in re.sub(r"[^a-z0-9]+", " ", _norm(n)).split() if len(w) > 2}


def semblants(a, b):
    """Dos noms de torneig que poden ser el mateix (comparteixen la meitat de les paraules que els distingeixen)."""
    ma, mb = mots(a), mots(b)
    da, db = ma - SENSE_PARAULA, mb - SENSE_PARAULA
    if da and db:                  # «Open Girona» i «Open Barcelona» no són el mateix: només compten les paraules que distingeixen el torneig
        ma, mb = da, db
    return bool(ma and mb) and len(ma & mb) >= max(1, min(len(ma), len(mb)) // 2)


def _rang(r):
    f = r.get("font") or "chess-results"
    return ORDRE.index(f) if f in ORDRE else len(ORDRE)


def mateix(x, r):
    return (x["jugador"] == r["jugador"] and x["tnr"] != r["tnr"] and x["fi"] == r["fi"]
            and (x.get("modalitat") or "Standard") == (r.get("modalitat") or "Standard") and semblants(x["torneig"], r["torneig"]))


def deduplica(resultats, tornejos):
    """Treu els resultats repetits (i els torneigs que es queden sense cap resultat). Torna (resultats, descartats) i modifica `tornejos`."""
    ordenats = sorted(range(len(resultats)), key=lambda i: (_rang(resultats[i]), -len(resultats[i].get("partides") or []), i))
    mantinguts, descartats = [], []
    for i in ordenats:
        r = resultats[i]
        pare = next((x for x in mantinguts if mateix(x, r)), None)
        if pare:
            descartats.append((r, pare))
        else:
            mantinguts.append(r)
    descartats_idx = {id(d[0]) for d in descartats}
    out = [r for r in resultats if id(r) not in descartats_idx]
    vius = {t for r in out for t in (r["tnr"], r.get("tnr_alt")) if t}
    for r, pare in descartats:
        print(f"  Duplicat descartat: {r['jugador']} · «{r['torneig']}» ({r.get('font') or 'chess-results'}, {r['tnr']}) = «{pare['torneig']}» ({pare.get('font') or 'chess-results'}, {pare['tnr']})")
        if r["tnr"] not in vius:
            tornejos.pop(r["tnr"], None)
        else:                          # el torneig segueix existint per a d'altres jugadors: es treu només el jugador de la seva classificació
            cl = (tornejos.get(r["tnr"]) or {}).get("classificacio") or {}
            if isinstance(cl.get("jugadors"), list) and not (tornejos[r["tnr"]].get("equips") or cl.get("equips")):
                cl["jugadors"] = [x for x in cl["jugadors"] if x["nom"] != r["jugador"]]
    return out, [d[0] for d in descartats]


def deduplica_previs(previs):
    """Torneigs per començar: el mateix dia d'inici i noms semblants són el mateix torneig; se sumen els jugadors."""
    out = []
    for p in previs:
        d = next((x for x in out if x["inici"] == p["inici"] and semblants(x["torneig"], p["torneig"])), None)
        if d:
            d["jugadors"] += [n for n in p["jugadors"] if n not in d["jugadors"]]
            for k in ("ordre", "equips"):
                if p.get(k) and not d.get(k):
                    d[k] = p[k]
        else:
            out.append(p)
    return out
