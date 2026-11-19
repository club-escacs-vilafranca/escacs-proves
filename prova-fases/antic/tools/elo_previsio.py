"""Previsió de l'Elo FIDE estàndard de la propera llista (sense xarxa).

Què fa (validat amb les llistes de juliol a novembre del 2026: 145 de 176 casos a 2 punts o menys de l'Elo real):
  - Cada partida entra a la primera llista (1 de mes) tal que la seva data <= 1 del mes - 3 dies (Reglament FIDE B.02, 7.1.3). Als tornejos de més de 30 dies
    cada ronda entra per la seva data; a la resta, tot el torneig pel dia que acaba.
  - Només compten les partides contra rivals que ja tenien Elo FIDE a Chess-Results; no compten byes ni incompareixences.
  - Variació = suma de K x (resultat - esperat) amb la taula d'esperats de la FIDE. La K és la «completa» (40/20/10) que el jugador va tenir a la llista anterior,
    inferida de la variació real publicada per la FIDE (la K de jugador nou no es pot deduir de l'Elo); si en una llista K x n > 700, K = 700 / n (només dins del càlcul).
  - Previsió = Elo de l'última llista + variació arrodonida de les partides que entren a la llista següent.
Només estàndard; només tornejos amb validesa FIDE «si» i modalitat Standard a data/elo-compilat.json.
"""
import re
import datetime, itertools, json, math, os, sys

sys.path.insert(0, os.path.dirname(__file__))
from elo_calc import esperat_fide, llista_de, ym_ref, es_llarg, torneig_llarg

PUNTS = {"1": 1, "+": 1, "½": .5, "0": 0, "-": 0}


def mes_seguent(ym):
    y, m = int(ym[:4]), int(ym[4:]) + 1
    return f"{y + (m > 12)}{(m - 1) % 12 + 1:02d}"


def arrodoneix(x):
    return int(math.floor(abs(x) + .5)) * (1 if x >= 0 else -1)


def compta(g):
    """Partida calculable: rival amb Elo FIDE a Chess-Results, no incompareixença/descans."""
    return bool(not g.get("inc") and g.get("fide") and g["fide"].get("opp") and (g.get("ri") or g.get("rtg_i") or g.get("fid")) and g.get("res") in PUNTS)


def per_llista(resultats_jugador, compilat, hist_riv=None, h_propi=None, categoria=None, previes=None):
    """{llista: [{"tnr", "torneig", "S", "n", "kreg", "partides"}]} de les partides calculables d'un jugador."""
    out = {}
    valides = _partides_valides(resultats_jugador, compilat, hist_riv)
    for r in resultats_jugador:
        c = compilat.get(r["tnr"])
        if c is None:  # sense entrada al CMS: només els manuals estàndard amb variació FIDE (p. ex. Narbona)
            if r.get("font") not in ("manual", "lliga") or not r.get("elo_fide") or (r.get("modalitat") or "Standard") != "Standard":
                continue
        elif c.get("modalitat") != "Standard" or c.get("fide") != "si":
            continue
        dates = [g["data"] for g in r.get("partides", []) if g.get("data")]
        llarg = r.get("llarg") or torneig_llarg(dates, r.get("inici"), r.get("fi"))   # llarg segons el torneig sencer, no només les partides del jugador
        sub = {}
        for g in r.get("partides", []):
            if not compta(g):
                continue
            g = dict(g, fide=dict(g["fide"]))
            hr = (hist_riv or {}).get(str(g.get("fid"))) if g.get("fid") else None
            if r.get("font") != "lliga" and g.get("fid") is not None:
                ym = ym_ref(dates or [r["fi"]], g.get("data") or r["fi"], llarg)   # ratings de la llista del primer dia del torneig/tram, com la FIDE
                if hr and hr.get("h"):
                    opp = (hr["h"].get(ym) or {}).get("standard")
                    if not opp:
                        continue
                    g["fide"]["opp"] = opp
                if h_propi:
                    R = (h_propi.get(ym) or {}).get("standard")
                    if not R:
                        continue
                    g["fide"]["r"] = R
            L = llista_de((g.get("data") or r["fi"]) if llarg else r["fi"])
            x = sub.setdefault(L, {"tnr": r["tnr"], "torneig": r["torneig"], "S": 0.0, "n": 0, "kreg": g["fide"]["k"], "partides": [], "d0": g.get("data") or r["fi"]})
            x["d0"] = min(x["d0"], g.get("data") or r["fi"])
            x["S"] += PUNTS[g["res"]] - esperat_fide(g["fide"]["opp"] - g["fide"]["r"])
            x["n"] += 1
            x["partides"].append({"ronda": g.get("ronda"), "rival": g.get("rival"), "opp": g["fide"]["opp"], "res": g["res"]})
        for L, x in sub.items():
            x["k"] = k_comptador(x["d0"], h_propi, valides, categoria, previes)
            out.setdefault(L, []).append(x)
    for ts in out.values():
        ts.sort(key=lambda x: x["d0"])   # ordre cronològic: l'última K deduïda és la del darrer torneig
    return out


def _partides_valides(resultats_jugador, compilat, hist_riv):
    """Dates (i llista d'entrada) de les partides estàndard vàlides per a l'Elo FIDE contra rival amb Elo FIDE (compten per a les 30 partides de la K 40)."""
    out = []
    for r in resultats_jugador:
        c = compilat.get(r["tnr"])
        if c is None:
            if r.get("font") not in ("manual", "lliga") or not r.get("elo_fide") or (r.get("modalitat") or "Standard") != "Standard":
                continue
        elif c.get("modalitat") != "Standard" or c.get("fide") != "si":
            continue
        dates = [g["data"] for g in r.get("partides", []) if g.get("data")]
        llarg = r.get("llarg") or torneig_llarg(dates, r.get("inici"), r.get("fi"))   # llarg segons el torneig sencer, no només les partides del jugador
        for g in r.get("partides", []):
            if g.get("inc") or g.get("res") not in ("1", "0", "½", "+") or not g.get("data"):
                continue
            hr = (hist_riv or {}).get(str(g.get("fid"))) if g.get("fid") else None
            if hr and hr.get("h"):
                ok = bool(((hr["h"].get(ym_ref(dates, g["data"], llarg)) or {}).get("standard")))
            else:
                ok = bool(g.get("fide") and g["fide"].get("opp"))
            if ok:
                out.append(g["data"])
    return out


def k_comptador(d0, h, valides, categoria=None, previes=None):
    """K del tram que comença el dia d0 segons el comptador de partides: K 40 des que l'Elo apareix (o torna a aparèixer després d'un forat) fins que
    s'han jugat 30 partides; després 40 als menors de 18 amb Elo < 2300, 10 amb 2400 i 20 en la resta. None si no es pot saber (Elo anterior al 2026)."""
    if not h or not d0:
        return None
    ym = d0[:7].replace("-", "")
    a = (h.get(ym) or {}).get("standard")
    if not a:
        return None
    ini = ym
    while (h.get(mes_ant(ini)) or {}).get("standard"):
        ini = mes_ant(ini)
    nou = ini >= "202602"
    junior = re.search(r"Sub-?\s*(\d+)", categoria or "")
    if junior and int(junior.group(1)) <= 18 and a < 2300:
        return 40
    if previes:   # partides anteriors al 2026 anotades a mà (data/elo-partides-previes.json)
        n = previes["partides"] + sum(1 for d in valides if d < d0 and llista_de(d) > previes["fins"])
        return 40 if n < 30 else (10 if a >= 2400 else 20)
    if not nou:
        return None
    n = sum(1 for d in valides if d < d0 and llista_de(d) >= ini)
    if n < 30:
        return 40
    return 10 if a >= 2400 else 20


def variacio(ts, ks):
    n = sum(t["n"] for t in ts)
    tot = 0.0
    for t, k in zip(ts, ks):
        ke = 700 // n if n and k * n > 700 else k
        tot += ke * t["S"]
    return tot


def k_inferida(llistes, h):
    """K completa (40/20/10) de l'últim torneig amb variació real coneguda: la que fa quadrar la variació de la FIDE de cada llista."""
    kult = None
    for L in sorted(llistes):
        a, b = (h.get(mes_ant(L)) or {}).get("standard"), (h.get(L) or {}).get("standard")
        if not a or not b:
            continue
        ts, real = llistes[L], b - a
        cands = []
        for ks in itertools.product((40, 20, 10), repeat=len(ts)):
            err = round(abs(variacio(ts, ks) - real))
            if err <= 3:
                cands.append(ks[-1])
        if len(set(cands)) == 1:  # només compta si la variació real identifica una K; si n'hi ha diverses de possibles (variació petita) no s'infereix res
            kult = cands[0]
    return kult


def k_per(L, h, kinf, categoria=None):
    """K de la llista L (B.02 de la FIDE): 40 als menors de 18 amb Elo < 2300, i si el mes anterior no té Elo o la K d'aquell mes era 40; si no, 20 (10 amb 2400)."""
    a = (h.get(mes_ant(L)) or {}).get("standard")
    m = re.search(r"Sub-?\s*(\d+)", categoria or "")
    if not a or (m and int(m.group(1)) <= 18 and a < 2300):
        return 40
    if kinf:
        return kinf
    return 10 if a >= 2400 else 20


def mes_ant(ym):
    y, m = int(ym[:4]), int(ym[4:]) - 1
    return f"{y - (m == 0)}{(m - 1) % 12 + 1:02d}"


def previsio(j, resultats_jugador, compilat, h, hist_riv=None, previes=None):
    """{'prev_fide', 'prev_n', 'prev_k', 'prev_ant'} de la llista següent, o None si no n'hi ha cap partida pendent."""
    ms = [m for m in h if (h[m] or {}).get("standard")]
    if not ms:
        return None
    ult = max(ms)
    seg = mes_seguent(ult)
    llistes = per_llista(resultats_jugador, compilat, hist_riv, h, j.get("categoria"), (previes or {}).get(str(j.get("fide"))))
    ts = llistes.get(seg)
    if not ts:
        return None
    a = h[ult]["standard"]
    k = k_per(seg, h, k_inferida({L: v for L, v in llistes.items() if L <= ult}, h), j.get("categoria"))
    n = sum(t["n"] for t in ts)
    v = variacio(ts, [t.get("k") or k for t in ts])
    return {"prev_fide": a + arrodoneix(v), "prev_n": n, "prev_k": k, "prev_ant": a}


def previsio_rb(resultats_jugador, compilat, h, modal):
    """Previsió FIDE de ràpid o llampec (modal = "rapid"/"blitz") de la llista següent: Elo de l'última llista + suma de les variacions que ja calcula elo_calc
    per als tornejos d'aquesta modalitat vàlids per a l'Elo FIDE i que acaben dins el tall de la llista següent. {'prev', 'n', 'ant'} o None si no n'hi ha cap."""
    ms = [m for m in h if (h[m] or {}).get(modal)]
    if not ms:
        return None
    ult = max(ms)
    seg = mes_seguent(ult)
    tot, n = 0.0, 0
    for r in resultats_jugador:
        c = compilat.get(r["tnr"])
        if not c or c.get("fide") != "si" or (r.get("modalitat") or "").lower() != modal or not isinstance(r.get("elo_fide"), dict):
            continue
        if llista_de(r["fi"]) != seg:
            continue
        tot += r["elo_fide"].get("var") or 0
        n += r["elo_fide"].get("partides") or 0
    if not n:
        return None
    a = h[ult][modal]
    return {"prev": a + arrodoneix(tot), "n": n, "ant": a}


def lliga_com_resultats(lliga, noms):
    """Partides de la Lliga Catalana (data/lliga-<any>.json, amb fide per taulell) com a files de resultats per jugador."""
    out = {}
    for g in (lliga or {}).get("grups", []):
        for ron in g.get("rondes", []):
            for t in ron.get("taulers", []):
                f = t.get("fide") or {}
                nom = noms.get(str(t.get("idn"))) or t.get("nostre")
                if not f.get("opp") or not ron.get("data") or not nom:
                    continue
                r = out.setdefault((nom, g["id"]), {"llarg": True, "jugador": nom, "tnr": "lliga-" + g["id"], "torneig": "Lliga Catalana " + g["nom"], "font": "lliga",
                                                    "modalitat": "Standard", "elo_fide": True, "fi": ron["data"], "partides": []})
                r["fi"] = max(r["fi"], ron["data"])
                r["partides"].append({"ronda": ron["ronda"], "data": ron["data"], "rival": t.get("rival"), "res": {"1": "1", "0": "0", "½": "½"}.get(t.get("res"), t.get("res")),
                                      "ri": int(f["r"]), "fide": f})
    return list(out.values())


def calcula(arrel="."):
    """Escriu a data/jugadors.json els camps prev_* de cada jugador (previsió FIDE estàndard de la llista següent)."""
    def carrega(x, d):
        try:
            return json.load(open(os.path.join(arrel, x), encoding="utf-8"))
        except Exception:
            return d
    dj = carrega("data/jugadors.json", None)
    if not dj:
        return 0
    res = carrega("data/resultats-jugadors.json", {}).get("resultats", [])
    comp = {t["tnr"]: t for t in carrega("data/elo-compilat.json", {}).get("tornejos", [])}
    hist = carrega("data/brut/hist_fide.json", {})
    previes = {k: v for k, v in carrega("data/elo-partides-previes.json", {}).items() if not k.startswith("_")}
    per = {}
    for r in res:
        per.setdefault(r["jugador"], []).append(r)
    for r in lliga_com_resultats(carrega("data/lliga-2026.json", {}), {j["id"]: j["nom"] for j in dj.get("jugadors", [])}):
        per.setdefault(r["jugador"], []).append(r)
    n_ = 0
    ult_global = ""
    for j in dj.get("jugadors", []):
        for c in ("prev_fide", "prev_n", "prev_k", "prev_ant", "prev_fide_r", "prev_fide_r_n", "prev_fide_r_ant", "prev_fide_b", "prev_fide_b_n", "prev_fide_b_ant"):
            j.pop(c, None)
        h = (hist.get(str(j.get("fide"))) or {}).get("h") or {}
        ms = [m for m in h if (h[m] or {}).get("standard")]
        if ms:
            ult_global = max(ult_global, max(ms))
        p = previsio(j, per.get(j["nom"], []), comp, h, hist, previes) if h else None
        if p:
            j.update(p)
            n_ += 1
        for modal, sf in (("rapid", "_r"), ("blitz", "_b")):
            q = previsio_rb(per.get(j["nom"], []), comp, h, modal) if h else None
            if q:
                j.update({"prev_fide" + sf: q["prev"], "prev_fide" + sf + "_n": q["n"], "prev_fide" + sf + "_ant": q["ant"]})
    if ult_global:
        dj["llista_mes"], dj["prev_mes"] = ult_global, mes_seguent(ult_global)
    open(os.path.join(arrel, "data/jugadors.json"), "w", encoding="utf-8").write(json.dumps(dj, ensure_ascii=False, indent=1))
    return n_


if __name__ == "__main__":
    print("Previsió d'Elo FIDE:", calcula("."), "jugadors")
