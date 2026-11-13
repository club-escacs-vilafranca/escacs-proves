#!/usr/bin/env python3
"""Dossier de dades per redactar la crònica d'un torneig a partir de data/resultats/<torneig>-<any>.json.

Ús:
  python3 tools/cronica_dades.py data/resultats/obert-vilafranca-2026.json [--club vilafranca] [--premis obert [--premis-text]]

Només calcula fets (participants, club, podi, resultats destacats, etc.); la redacció la fa la skill
«cronica-torneig». Els menors (tipus U8-U18) es mostren amb la categoria (p. ex. «(sub-14)»).
"""
import json, re, sys, math, collections

# Premis de l'Obert (mateixes regles que PRIZE_RULES de js/site.js); no acumulables, per ordre de prioritat
GEN = ["400 € + trofeu", "200 € + trofeu", "100 € + trofeu", "60 € + trofeu", "50 € + trofeu"]
TRAM = ["50 € + trofeu", "30 € + trofeu", "Trofeu"]
PREMIS_OBERT = [
    ("Classificació general", GEN, {}),
    ("Tram A (2000–2149)", TRAM, {"min": 2000, "max": 2149}),
    ("Tram B (1850–1999)", TRAM, {"min": 1850, "max": 1999}),
    ("Tram C (1700–1849)", TRAM, {"min": 1700, "max": 1849}),
    ("Tram D (fins a 1699)", TRAM, {"max": 1699}),
    ("Sub-16", ["Trofeu"], {"young": True}),
    ("Major de 65 anys", ["Trofeu"], {"old": True}),
    ("Local", ["Trofeu"], {"local": True}),
    ("Femení", ["Premi"], {"sex": "F"}),
]


def es_menor(j):
    return bool(re.match(r"^U(8|10|12|14|16|18)$", j.get("tipus") or ""))


def enriqueix(jug):
    """Chess-Results no sempre dona sexe i categoria (p. ex. a les ràpides): es completen amb els altres
    torneigs importats i amb el llistat de socis federats (data/jugadors.json)."""
    import glob, os
    ref = {}
    arrel = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data")
    for f in glob.glob(os.path.join(arrel, "resultats", "*.json")):
        if f.endswith("index.json"):
            continue
        for j in json.load(open(f)).get("jugadors", []):
            o = ref.setdefault(j["nom"], {})
            for k in ("sexe", "tipus"):
                if j.get(k) and (not o.get(k) or (k == "sexe" and j[k] == "F")):
                    o[k] = j[k]
    try:
        for j in json.load(open(os.path.join(arrel, "jugadors.json")))["jugadors"]:
            o = ref.setdefault(j["nom"], {})
            if j.get("sexe") and not o.get("sexe"):
                o["sexe"] = j["sexe"]
            m = re.match(r"Sub-(\d+)", j.get("categoria") or "")
            if m and not o.get("tipus"):
                o["tipus"] = "U" + m.group(1)
            elif (j.get("categoria") or "").startswith("Veterà") and not o.get("tipus"):
                o["tipus"] = "S65"
    except Exception:
        pass
    for j in jug:
        for k, v in ref.get(j["nom"], {}).items():
            if not j.get(k) or (k == "sexe" and v == "F" and j.get(k) == "M"):     # el sexe per defecte de Chess-Results és M
                j[k] = v


def norm(n):
    import unicodedata
    n = unicodedata.normalize("NFD", n.lower())
    n = "".join(c for c in n if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+[a-z]\.$", "", n.strip())          # «Daniel Uroz L.» -> «daniel uroz»


def noms_socis(font):
    """Jugadors del club d'aquest torneig (data/torneigs-jugadors.json), útil quan Chess-Results no dona el club."""
    import os
    m = re.search(r"tnr(\d+)", font)
    try:
        d = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "torneigs-jugadors.json")))["tornejos"]
    except Exception:
        return set()
    return {norm(j["nom"]) for t in d if m and t["tnr"] == m.group(1) for j in ((t.get("classificacio") or {}).get("jugadors") or [])}


def esperat(a, b):
    return 1 / (1 + 10 ** ((b - a) / 400))


def fmt(p):
    s = ("%g" % p).replace(".", ",")
    return s.replace(",5", "½") if p % 1 else s


def main():
    a = sys.argv[1:]
    if not a:
        sys.exit(__doc__)
    club = re.compile(a[a.index("--club") + 1] if "--club" in a else "vilafranca", re.I)
    prem = a[a.index("--premis") + 1] if "--premis" in a else None
    r = json.load(open(a[0]))
    enriqueix(r["jugadors"])
    J = {j["n"]: j for j in r["jugadors"]}
    pl = sorted(r["jugadors"], key=lambda j: j.get("ordre") or 999)
    N, R = len(pl), len(r["rondes"])
    socis = noms_socis(r.get("font") or "")
    loc = [j for j in pl if club.search(j.get("club") or "") or norm(j["nom"]) in socis]     # club a Chess-Results o soci conegut (jugadors sense club)

    def nm(j):
        return j["nom"] + (f" (sub-{j['tipus'][1:]})" if es_menor(j) else "")

    # partides: b = blanques, n = negres (convenció de l'importador)
    stats = collections.defaultdict(lambda: {"exp": 0.0, "n": 0, "wins": []})
    taules = decis = 0
    sorpreses = []
    acum = collections.defaultdict(lambda: [0.0] * (R + 1))
    for k, rd in enumerate(r["rondes"], 1):
        ptsr = collections.defaultdict(float)
        for g in rd:
            w, b = J.get(g["b"]), J.get(g["n"])
            res = g["res"]
            sw = {"1-0": 1, "0-1": 0, "½-½": .5}.get(res)
            if sw is None or not w or not b:
                continue
            ptsr[w["n"]] += sw
            ptsr[b["n"]] += 1 - sw
            if g.get("inc"):
                continue
            if sw == .5:
                taules += 1
            else:
                decis += 1
            ew, eb = w.get("elo") or 0, b.get("elo") or 0
            if ew and eb:
                for x, ex, sc, rival_elo in ((w, ew, sw, eb), (b, eb, 1 - sw, ew)):
                    stats[x["n"]]["exp"] += esperat(ex, rival_elo)
                    stats[x["n"]]["n"] += 1
                guanyador, perdedor = (w, b) if sw == 1 else (b, w) if sw == 0 else (None, None)
                if guanyador:
                    d = (perdedor.get("elo") or 0) - (guanyador.get("elo") or 0)
                    sorpreses.append((d, guanyador, perdedor, k))
        for n in J:
            acum[n][k] = acum[n][k - 1] + ptsr.get(n, 0)

    out = []
    P = out.append
    P(f"# {r.get('nom_torneig')}  ({r.get('font')})")
    P(f"- Participants: {N} · rondes: {R} · clubs diferents: {len({j.get('club') for j in pl})}")
    elos = [j["elo"] for j in pl if j.get("elo")]
    if elos:
        P(f"- Elo mitjà dels inscrits: {round(sum(elos) / len(elos))} (de {min(elos)} a {max(elos)})")
    tit = [j for j in pl if j.get("titol")]
    if tit:
        P("- Jugadors amb títol: " + ", ".join(f"{j['titol']} {nm(j)} ({j.get('club')})" for j in tit))
    dones = [j for j in pl if j.get("sexe") == "F"]
    P(f"- Dones: {len(dones)} ({round(100 * len(dones) / N)} %) · menors (sub-18): {sum(es_menor(j) for j in pl)} · majors de 65: {sum(j.get('tipus') == 'S65' for j in pl)}")
    cl = collections.Counter(j.get("club") for j in pl).most_common(6)
    P("- Clubs amb més jugadors: " + ", ".join(f"{c} ({n})" for c, n in cl))
    P(f"- Partides: {taules + decis} jugades, {taules} taules ({round(100 * taules / max(1, taules + decis))} %)")

    P("\n## Podi i classificació")
    for j in pl[:5]:
        P(f"{j['ordre']}. {nm(j)} ({j.get('club')}, Elo {j.get('elo') or '–'}) · {fmt(j['pts'])} punts" + (f" · títol {j['titol']}" if j.get("titol") else ""))
    guanyador = pl[0]
    P(f"- Guanyador: {guanyador['nom']} amb {fmt(guanyador['pts'])}/{R}" + (" (pleno)" if guanyador["pts"] == R else ""))
    if R >= 2:
        lid = sorted(J.values(), key=lambda j: -acum[j["n"]][R - 1])[:3]
        P("- Líders abans de l'última ronda: " + ", ".join(f"{j['nom']} {fmt(acum[j['n']][R - 1])}" for j in lid))
    if r["rondes"]:
        t1 = r["rondes"][-1][0]
        P(f"- Taula 1 de l'última ronda: {J[t1['b']]['nom']} – {J[t1['n']]['nom']} ({t1['res']})")

    P(f"\n## Club ({len(loc)} jugadors, {round(100 * len(loc) / N)} % dels inscrits)")
    for j in sorted(loc, key=lambda j: j.get("ordre") or 999)[:10]:
        s = stats[j["n"]]
        d = j["pts"] - s["exp"] if s["n"] else None
        P(f"{j['ordre']}è lloc · {nm(j)} · Elo {j.get('elo') or '–'} · {fmt(j['pts'])} punts" + (f" · esperat {s['exp']:.1f} ({'+' if d >= 0 else ''}{d:.1f})" if d is not None else ""))
    sob = sorted([j for j in loc if stats[j["n"]]["n"] >= 4], key=lambda j: -(j["pts"] - stats[j["n"]]["exp"]))[:3]
    if sob:
        P("- Millors resultats respecte l'Elo: " + ", ".join(f"{nm(j)} ({'+' if j['pts'] - stats[j['n']]['exp'] >= 0 else ''}{j['pts'] - stats[j['n']]['exp']:.1f})" for j in sob))
    locn = {j["n"] for j in loc}
    gl = [s for s in sorpreses if s[1]["n"] in locn and s[0] >= 100]
    gl.sort(key=lambda s: -s[0])
    if gl:
        P("- Victòries de jugadors del club contra rivals amb més Elo: " + "; ".join(f"{nm(g)} guanya a {nm(p)} (+{d} Elo, ronda {k})" for d, g, p, k in gl[:4]))
    P(f"- Punts totals dels jugadors del club: {fmt(sum(j['pts'] for j in loc))}")
    fem = [j for j in loc if j.get("sexe") == "F"]
    if fem:
        P("- Dones del club: " + ", ".join(f"{nm(j)} ({j['ordre']}è, {fmt(j['pts'])})" for j in fem))

    sorpreses.sort(key=lambda s: -s[0])
    P("\n## Sorpreses generals (victòria contra més Elo)")
    for d, g, p, k in sorpreses[:3]:
        P(f"- Ronda {k}: {nm(g)} ({g.get('elo')}) guanya a {nm(p)} ({p.get('elo')}), +{d}")

    if prem == "obert":
        P("\n## Premis (regles de les bases, no acumulables)")
        got = set()
        lines = []
        for cat, premis, c in PREMIS_OBERT:
            n = len(premis)
            k = 0
            for j in pl:
                if k >= n:
                    break
                e = j.get("elo") or 0
                if "min" in c and e < c["min"] or "max" in c and e > c["max"]:
                    continue
                if "sex" in c and j.get("sexe") != c["sex"]:
                    continue
                if c.get("young") and not re.match(r"^U(8|10|12|14|16)$", j.get("tipus") or ""):
                    continue
                if c.get("old") and j.get("tipus") != "S65":
                    continue
                if c.get("local") and not club.search(j.get("club") or ""):
                    continue
                if j["n"] in got:
                    continue
                got.add(j["n"])
                k += 1
                if "--premis-text" in a:
                    lines.append(f"{cat} | {k} | {j['nom']} | {premis[k - 1]}")
                P(f"- {cat} · {k}r: {nm(j)} ({j.get('club')})")
    else:
        P("\n## Premis\n- (Sense regles automàtiques: les bases diuen «en funció de les inscripcions».) Millor jugador del club: "
          + (nm(sorted(loc, key=lambda j: j['ordre'])[0]) + f" ({sorted(loc, key=lambda j: j['ordre'])[0]['ordre']}è)" if loc else "–"))
    if "--premis-text" in a and prem == "obert":
        print("\n".join(lines))        # text per al camp «Premis» del CMS (Categoria | Lloc | Jugador | Premi)
        return
    print("\n".join(out))


if __name__ == "__main__":
    main()
