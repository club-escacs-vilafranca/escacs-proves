#!/usr/bin/env python3
"""Font Chess-Results: torneigs, classificacions, fitxes i partides dels jugadors del club.

`baixa()` fa tot el que cal a Chess-Results (consultes per jugador, classificacions, fitxes, rivals) i desa el resultat en brut a data/brut/cr-jugadors.json.
No calcula cap Elo: això ho fa tools/elo_calc.py. L'orquestra tools/jugadors.py.

Salvaguardes: si Chess-Results no respon (5 errors seguits) o es passa del temps màxim, deixa de consultar jugadors i conserva el que hi havia.
"""
import json, os, re, sys, time, html, datetime, unicodedata
sys.path.insert(0, os.path.dirname(__file__))
from xarxa import req as _req
from elo_calc import norm
from duplicats import deduplica_previs
from importar_chessresults import nom_public

CR = "https://s1.chess-results.com/SpielerSuche.aspx?lan=2&SNode=S0"   # sempre el mateix node: el viewstate no val entre nodes
D_CR = "data/brut/cr-jugadors.json"

# Salvaguardes de xarxa: després de 5 errors seguits, o passat el temps màxim, no es demana res més en aquesta execució (en lloc de gastar minuts esperant temps d'espera).
_estat = {"seguits": 0, "fins": None}


def req(url, *a, **k):
    if _estat["seguits"] >= 5:
        raise RuntimeError("Chess-Results no respon (5 errors seguits): no es torna a provar en aquesta execució")
    if _estat["fins"] and time.time() > _estat["fins"]:
        raise RuntimeError("s'ha esgotat el temps màxim de la lectura de Chess-Results")
    try:
        r = _req(url, *a, **k)
    except Exception:
        _estat["seguits"] += 1
        raise
    _estat["seguits"] = 0
    return r


def carrega(p, per_defecte):
    try:
        return json.load(open(p, encoding="utf-8"))
    except Exception:
        return per_defecte


def fnum(x):
    try:
        return float(str(x).replace(",", "."))
    except Exception:
        return None


def num(x):
    try:
        return int(float(str(x).replace(",", ".")))
    except Exception:
        return None


def analitza_cr(t, fide):
    """Taula de resultats de SpielerSuche -> llista de torneigs."""
    out = []
    for tr in re.findall(r"<tr[^>]*class=\"CRg[12]b?\"[^>]*>(.*?)</tr>", t, re.S):
        tds = re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", tr, re.S)
        if len(tds) < 10:
            continue
        net = [html.unescape(re.sub(r"<[^>]+>", "", x)).strip() for x in tds]
        if net[2] != str(fide):
            continue
        m = re.search(r'href="(tnr(\d+)\.aspx\?[^"]*snr=(\d+))"', tds[0])
        if not m:
            continue
        d = net[6].replace("/", "-")
        out.append({"tnr": m.group(2), "snr": m.group(3), "torneig": net[5], "fi": d, "club": net[3], "fed": net[4],
                    "lloc": num(net[7]) if net[7] not in ("-", "") else None, "rondes": num(net[8]), "de": num(net[9]),
                    "url": "https://s1.chess-results.com/" + html.unescape(m.group(1)).replace("lan=2", "lan=1")})
    return out


def cr_cerca(**camps_usuari):
    """Consulta SpielerSuche. Camps possibles: fide, cognom, nom, club."""
    f = req(CR)       # un formulari nou per consulta (viewstate)
    camps = {}
    for tag in re.findall(r"<input[^>]*>", f):
        n = re.search(r'name="([^"]+)"', tag)
        ty = re.search(r'type="([^"]+)"', tag)
        if not n or (ty and ty.group(1) in ("submit", "button", "checkbox", "image")):
            continue
        v = re.search(r'value="([^"]*)"', tag)
        camps[n.group(1)] = html.unescape(v.group(1)) if v else ""
    mapa = {"fide": "ctl00$P1$txt_fideID", "cognom": "ctl00$P1$txt_nachname", "nom": "ctl00$P1$txt_vorname", "club": "ctl00$P1$txt_verein"}
    for k, v in camps_usuari.items():
        camps[mapa[k]] = str(v)
    camps.update({"ctl00$P1$combo_Sort": "0", "ctl00$P1$cb_suchen": "Buscar", "ctl00$P1$combo_anzahl_zeilen": "1"})
    return req(CR, camps, {"Origin": "https://s1.chess-results.com", "Referer": CR, "Accept": "text/html,application/xhtml+xml"})


def analitza_cr_nom(t, nom_cr):
    """Torneigs on el jugador surt sense codi FIDE (p. ex. torneigs locals): files del club Vilafranca amb el mateix nom."""
    out = []
    for tr in re.findall(r"<tr[^>]*class=\"CRg[12]b?\"[^>]*>(.*?)</tr>", t, re.S):
        tds = re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", tr, re.S)
        if len(tds) < 10:
            continue
        net = [html.unescape(re.sub(r"<[^>]+>", "", x)).strip() for x in tds]
        if norm(net[0]) != norm(nom_cr) or "vilafranca" not in net[3].lower():
            continue
        m = re.search(r'href="(tnr(\d+)\.aspx\?[^"]*snr=(\d+))"', tds[0])
        if not m:
            continue
        d = net[6].replace("/", "-")
        out.append({"tnr": m.group(2), "snr": m.group(3), "torneig": net[5], "fi": d, "club": net[3], "fed": net[4],
                    "lloc": num(net[7]) if net[7] not in ("-", "") else None, "rondes": num(net[8]), "de": num(net[9]),
                    "url": "https://s1.chess-results.com/" + html.unescape(m.group(1)).replace("lan=2", "lan=1")})
    return out


def cr_torneigs_nom(j):
    cog, _, nom = j["nom_cr"].partition(",")
    t = cr_cerca(cognom=cog.strip().title(), nom=nom.strip().split(" ")[0].title(), club="Vilafranca")
    return analitza_cr_nom(t, j["nom_cr"])


def cr_torneigs(fide):
    t = cr_cerca(fide=fide)
    return analitza_cr(t, fide), t


def cr_per_nom(j):
    """Si la FCE no dona el codi FIDE: cerca per cognoms i nom, i es queda amb les files del club Vilafranca."""
    cog, _, nom = j["nom_cr"].partition(",")
    t = cr_cerca(cognom=cog.strip().title(), nom=nom.strip().split(" ")[0].title(), club="Vilafranca")
    files = []
    for tr in re.findall(r"<tr[^>]*class=\"CRg[12]b?\"[^>]*>(.*?)</tr>", t, re.S):
        tds = re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", tr, re.S)
        if len(tds) < 10:
            continue
        net = [html.unescape(re.sub(r"<[^>]+>", "", x)).strip() for x in tds]
        if norm(net[0]) == norm(j["nom_cr"]):
            files.append(net[2])
    fids = [f for f in files if f and f != "0"]
    return max(set(fids), key=fids.count) if fids else ""


def analitza_classificacio(t, nostres):
    """Classificació d'un torneig (art=1): jugadors del club amb lloc i punts, i quantes rondes porta."""
    ronda = re.search(r"after\s+(\d+)\s+round", t, re.I) or re.search(r"despr[eé]s\s+de\s+(\d+)\s+ronda", t, re.I)
    taula = re.search(r"<table[^>]*class=\"CRs1\"[^>]*>(.*?)</table>", t, re.S) or re.search(r"<table[^>]*class=\"CRs[^\"]*\"[^>]*>(.*?)</table>", t, re.S)
    if not taula:
        return None
    trs = re.findall(r"<tr[^>]*>(.*?)</tr>", taula.group(1), re.S)
    cap = [html.unescape(re.sub(r"<[^>]+>", "", x)).strip().lower() for x in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", trs[0], re.S)]
    def idx(*noms):
        for i, c in enumerate(cap):
            if any(n in c for n in noms):
                return i
        return None
    i_nom, i_pts, i_rk = idx("name", "nom"), idx("pts"), idx("rk", "ordre")
    if i_nom is None or i_pts is None:
        return None
    ens, participants = [], 0
    for tr in trs[1:]:
        c = [html.unescape(re.sub(r"<[^>]+>", "", x)).strip() for x in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", tr, re.S)]
        if len(c) <= max(i_nom, i_pts):
            continue
        participants += 1
        if norm(c[i_nom]) in nostres:
            ens.append({"nom": nostres[norm(c[i_nom])], "lloc": num(c[i_rk]) if i_rk is not None else participants, "punts": c[i_pts]})
    return {"ronda": int(ronda.group(1)) if ronda else None, "participants": participants, "jugadors": ens}


def modalitat_per_ritme(text):
    """Modalitat (Standard/Rapid/Blitz) segons el temps de reflexió de Chess-Results, amb el criteri de la FIDE: base + 60 jugades d'increment.
    10 min o menys: blitz; més de 10 i menys de 60 min: ràpid; 60 min o més: estàndard (Lleis, apèndix A). None si no s'hi entén el ritme."""
    t = (text or "").replace("\u2019", "'").replace("\u2032", "'").replace("\u201d", '"')
    mb = re.search(r"(\d+(?:[.,]\d+)?)\s*(?:'|min\w*|m\b)", t, re.I) or re.search(r"\bG\s*/\s*(\d+)", t, re.I)
    if not mb:
        return None
    base = float(mb.group(1).replace(",", ".")) * 60
    mi = re.search(r"\+\s*(\d+)\s*(?:\"|''|s\b|sec\w*|seg\w*|per move|/\s*move)?", t[mb.end():], re.I)
    inc = int(mi.group(1)) if mi else 0
    total = base + 60 * inc
    return "Blitz" if total <= 600 else "Rapid" if total < 3600 else "Standard"


def analitza_fitxa(t, viu=True):
    """Fitxa d'un jugador en un torneig (art=9): resum (performance, variació FIDE) i partides ja jugades."""
    out = {"partides": [], "emparellaments": []}
    zero_byes, max_rd = [], 0
    mm = re.search(r"Time control\s*\((\w+)\)", t)
    if mm:
        out["modalitat"] = mm.group(1).capitalize()
        txt_ = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", t))
        mr = re.search(r"Time control\s*\(\w+\)\s*(.*?)\s+" + ETIQ, txt_)
        if mr:
            out["ritme"] = mr.group(1).strip()[:80]
            m2 = modalitat_per_ritme(mr.group(1))
            if m2:                      # el temps de reflexió mana sobre l'etiqueta de l'organitzador (que a vegades és incorrecta)
                out["modalitat"] = m2
    from bs4 import BeautifulSoup
    for tab in BeautifulSoup(t, "html.parser").select("table.CRs1"):
        files, colors = [], []
        for tr in tab.find_all("tr"):
            cel = tr.find_all(["td", "th"], recursive=False)
            f = [c.get_text(" ", strip=True) for c in cel]
            if f:
                files.append(f)
                dv = None
                for c in cel:
                    dv = dv or c.find("div", class_=re.compile(r"^Farbe[ws]T$"))
                colors.append(("w" if "FarbewT" in dv["class"] else "s") if dv else "")
        if files and len(files[0]) == 2 and files[0][0] in ("Name", "Nom", "Nombre"):
            d = {f[0]: f[1] for f in files if len(f) == 2}
            out["perf"] = num(d.get("Performance rating") or d.get("Rendiment") or "")
            v = d.get("FIDE rtg +/-")
            out["fide_var"] = float(v.replace(",", ".")) if v and re.match(r"^[+-]?\d+([.,]\d+)?$", v) else None
            out["rtg_n"], out["rtg_i"] = num(d.get("Rating national")), num(d.get("Rating international"))
            out["punts"], out["lloc"] = d.get("Points"), num(d.get("Rank"))
            out["fide_id"] = (d.get("Fide-ID") or d.get("FIDE-ID") or d.get("FIDE ID") or "").strip() or None
        elif files and files[0][:1] == ["Rd."]:
            cap = files[0]
            ix = {c: i for i, c in enumerate(cap) if c}
            if "Res." not in ix or "Name" not in ix:
                continue
            def cel_(f, *noms):
                for n in noms:
                    if n in ix and ix[n] < len(f):
                        return f[ix[n]]
                return ""
            for fi_, f in enumerate(files[1:], start=1):
                if not f or not f[0].isdigit() or len(f) <= ix["Res."]:
                    continue
                max_rd = max(max_rd, int(f[0]))
                rr = f[ix["Res."]].split()
                m = re.fullmatch(r"([01½])(K?)", rr[-1]) if rr else None
                if not m:                 # ronda no jugada encara; si ja hi ha rival, és un emparellament (no un resultat)
                    nom_p = cel_(f, "Name")
                    if f[0].isdigit() and nom_p and nom_p.lower() != "not paired" and not rr:
                        out["emparellaments"].append({"ronda": int(f[0]), "rival": nom_public(nom_p),
                                                      "rtg_i": num(cel_(f, "RtgI")) or None, "rtg_n": num(cel_(f, "RtgN")) or None,
                                                      "bo": num(cel_(f, "Bo.")), "club": cel_(f, "Club/City"),
                                                      "color": colors[fi_] if fi_ < len(colors) else ""})
                    continue
                nom = cel_(f, "Name")
                if nom.lower() == "not paired" and m.group(1) == "0":
                    zero_byes.append(int(f[0]))          # sense emparellar i 0 punts: bye de 0 punts o no era al torneig (es decideix a sota)
                    continue
                out["partides"].append({"ronda": int(f[0]), "rival": "Descans" if nom.lower() == "not paired" else (nom_public(nom) if nom else ""),
                                        "rtg_i": num(cel_(f, "RtgI")) or None, "rtg_n": num(cel_(f, "RtgN")) or None, "rtg_x": num(cel_(f, "Rtg")) or None,
                                        "snr_riv": int(cel_(f, "SNo")) if cel_(f, "SNo").isdigit() and int(cel_(f, "SNo")) > 0 else None, "club": cel_(f, "Club/City"),
                                        "bo": num(cel_(f, "Bo.")), "color": colors[fi_] if fi_ < len(colors) else "", "res": m.group(1),
                                        **({"inc": True} if m.group(2) or nom.lower() == "not paired" else {})})
    # byes de 0 punts: es mostren els que queden entre la primera i l'última partida del jugador (no els d'abans d'entrar-hi) i, si el torneig
    # encara es juga, el de l'última ronda publicada (pot ser un emparellament futur: sense emparellar)
    jug = [g["ronda"] for g in out["partides"]]
    if jug:
        for rd in zero_byes:
            if min(jug) < rd < max(jug):
                out["partides"].append({"ronda": rd, "rival": "Descans", "res": "-", "inc": True})
            elif viu and rd == max(jug) + 1 and rd == max_rd:
                out["emparellaments"].append({"ronda": rd, "rival": "Descans", "bye": True, "inc": True})
        out["partides"].sort(key=lambda g: g["ronda"])
    return out


def nom_joc(x):
    """«Puerto Fernandez Iris» (sense coma) -> «Iris Puerto»; amb coma, com sempre."""
    x = (x or "").strip()
    if "," in x:
        return nom_public(x)
    w = x.split()
    return (w[-1] + " " + w[0]) if len(w) >= 2 else x


def claus_aprox(x):
    """Claus (primer cognom, inicial del nom) d'un nom «COGNOM1 COGNOM2, NOM» o «Nom Cognom»/«Cognom Nom» (les dues ordenacions)."""
    x = (x or "").strip()
    if "," in x:
        cog, nom = x.split(",", 1)
        c, n = norm(cog).split(), norm(nom).split()
        return {(c[0], n[0][0])} if c and n else set()
    w = norm(x).split()
    if len(w) < 2:
        return set()
    return {(w[0], w[-1][0]), (w[-1], w[0][0])}


def troba_nostre(cr, nostres, aprox):
    """Clau de `nostres` d'un jugador del torneig: exacta, o aproximada si només hi ha un candidat (mateix cognom i inicial)."""
    if norm(cr) in nostres:
        return norm(cr)
    c = set()
    for k in claus_aprox(cr):
        c |= set(aprox.get(k, []))
    return next(iter(c)) if len(c) == 1 else None


def analitza_equips(p0, p20, nostres, noms_cr=None, fides=None):
    """Torneig per equips: classificació d'equips (art=0) i composició amb resultats de cada tauler (art=20).
    Retorna (equips del club, partides dels nostres jugadors, ronda màxima jugada)."""
    from bs4 import BeautifulSoup
    clas = {}
    for tab in BeautifulSoup(p0, "html.parser").select("table.CRs1"):
        files = [[c.get_text(" ", strip=True) for c in tr.find_all(["td", "th"], recursive=False)] for tr in tab.find_all("tr")]
        files = [f for f in files if f]
        if files and "Team" in files[0] and "Rk." in files[0]:
            cap = files[0]
            for f in files[1:]:
                if len(f) < len(cap):
                    continue
                d = dict(zip(cap, f))
                clas[norm(d["Team"])] = {"rk": num(d.get("Rk.")), "partits": num(d.get("Games")), "g": num(d.get("+")), "e": num(d.get("=")), "p": num(d.get("-")),
                                        "taulers": d.get("TB1"), "matx": d.get("TB3")}
    equips, joc, equip, jug, rmax = {}, {}, None, None, 0
    ini_eq = {}
    cap = None
    for tab in BeautifulSoup(p20, "html.parser").select("table.CRs1"):
        for tr in tab.find_all("tr"):
            if tr.find_parent("table") is not tab:
                continue
            f = [c.get_text(" ", strip=True) for c in tr.find_all(["td", "th"], recursive=False)]
            if not f or not any(f):
                continue
            if len(f) == 1:
                txt = f[0]
                m = re.match(r"^(\d+)\.\s+(.*?)\s*\(RtgAvg", txt)
                if m:
                    equip, jug, cap = m.group(2).strip(), None, None
                    equips.setdefault(equip, [])
                    ini_eq[equip] = int(m.group(1))        # número d'ordre inicial de l'equip
                elif equip:
                    jug, cap = re.sub(r"\s+\d+(\s+[A-Za-z]{1,4})?$", "", txt).strip(), None
                continue
            if f[0] == "Bo." and "Name" in f:
                cap = ("roster", f, f.index("Name"), f.index("Pts."), [i for i, c in enumerate(f) if c.isdigit()])
                continue
            if f[0] == "Rd.":
                cap = ("jocs",)
                continue
            if not cap or not equip:
                continue
            if cap[0] == "roster" and f[0].isdigit() and len(f) >= len(cap[1]):
                res = [f[i] for i in cap[4]]
                for k, v in enumerate(res):
                    if v:
                        rmax = max(rmax, k + 1)
                fid = f[cap[1].index("FideID")] if "FideID" in cap[1] else ""
                equips[equip].append({"bo": int(f[0]), "fid": fid if fid.isdigit() else "", "cr": f[cap[2]], "pts": f[cap[3]], "res": res})
            elif cap[0] == "jocs" and jug and f[0].isdigit() and len(f) >= 8:
                rr = f[7].split()
                if not rr or rr[-1] not in ("1", "0", "½", "+", "-"):
                    continue
                joc.setdefault(norm(jug), []).append({"ronda": int(f[0]), "rival": nom_joc(f[3]), "rtg_i": num(f[4]) or None, "rtg_n": num(f[5]) or None,
                                                       "snr_riv": int(f[1]) if f[1].isdigit() and int(f[1]) > 0 else None, "res": rr[-1], "color": rr[0] if len(rr) > 1 else "", "bo": num(f[8]) if len(f) > 8 else None, "equip": equip})
    nostres_eq, partides = [], {}
    noms_cr = noms_cr or {}
    aprox, orig = {}, {}
    for k_, n_ in noms_cr.items():
        for kk in claus_aprox(n_):
            aprox.setdefault(kk, []).append(k_)
    fide_de_k = {v: k for k, v in (fides or {}).items()}
    for nom, plant in equips.items():
        # 1) segurs: nom exacte o FideID; 2) aproximats (Pedro/Pere), només dins d'un equip que ja té algun jugador segur i si el FideID no el contradiu
        for x in plant:
            k_ = (fides or {}).get(x.get("fid"))
            if k_ and k_ != norm(x["cr"]):
                orig[norm(x["cr"])] = k_
                x["cr"] = noms_cr[k_]
        if any(norm(x["cr"]) in nostres for x in plant):
            for x in plant:
                if norm(x["cr"]) in nostres:
                    continue
                k_ = troba_nostre(x["cr"], nostres, aprox)
                if k_ and not (x.get("fid") and fide_de_k.get(k_) and fide_de_k[k_] != x["fid"]):
                    orig[norm(x["cr"])] = k_
                    x["cr"] = noms_cr[k_]
        if not any(norm(x["cr"]) in nostres for x in plant):
            continue
        c = clas.get(norm(nom), {})
        nostres_eq.append({"nom": nom, **({"ini": ini_eq[nom]} if nom in ini_eq else {}), **c, "jugadors": [{"nom": nostres.get(norm(x["cr"])) or nom_public(x["cr"]), "del_club": norm(x["cr"]) in nostres, "bo": x["bo"], "punts": x["pts"], "res": x["res"]} for x in plant]})
    equip_de = {norm(x["cr"]): nom for nom, plant in equips.items() for x in plant}
    joc2 = {}
    for kj, gs in joc.items():                       # el nom de la pàgina de partides pot diferir del de la plantilla (Pedro/Pere)
        k2 = orig.get(kj) or kj
        joc2.setdefault(k2, []).extend(gs)
    for n, j in nostres.items():
        if n in joc2:
            partides[j] = sorted(({**g, "equip": equip_de.get(n, g.get("equip"))} for g in joc2[n]), key=lambda g: g["ronda"])
    return nostres_eq, partides, rmax


def info_ronda(tnr, rd, cache, taules, vol_taules):
    """Data d'una ronda i, als torneigs per equips, el número de taula de cada equip (pàgina d'aparellaments); es guarda perquè no canvia."""
    k = f"{tnr}:{rd}"
    if k in cache and (not vol_taules or k in taules):
        return cache[k], taules.get(k, {})
    time.sleep(1.2)
    pag = req(f"https://s1.chess-results.com/tnr{tnr}.aspx?lan=1&art=2&rd={rd}")
    txt = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", pag))
    m = re.search(rf"Round\s*{rd}\b.{{0,40}}?(\d{{4}}/\d\d/\d\d)", txt) or re.search(rf"Ronda\s*{rd}\b.{{0,40}}?(\d{{4}}/\d\d/\d\d)", txt)
    d = m.group(1).replace("/", "-") if m else None
    if vol_taules:
        from bs4 import BeautifulSoup
        tl = {}
        for tab in BeautifulSoup(pag, "html.parser").select("table.CRs1"):
            cap = None
            for tr in tab.find_all("tr"):
                f = [c.get_text(" ", strip=True) for c in tr.find_all(["td", "th"], recursive=False)]
                if f and f[0] == "No." and "Team" in f:
                    cap = f
                elif cap and f and f[0].isdigit() and len(f) >= len(cap):
                    for i, c in enumerate(cap):
                        if c == "Team":
                            tl[norm(f[i])] = int(f[0])
        taules[k] = tl
    if rd == 1 and not os.path.exists(f"data/brut/mostres_cr/rd_{tnr}_{rd}.html"):
        os.makedirs("data/brut/mostres_cr", exist_ok=True)
        open(f"data/brut/mostres_cr/rd_{tnr}_{rd}.html", "w", encoding="utf-8").write(pag[:60000])
    if d:
        cache[k] = d
    return d, taules.get(k, {})


# Torneigs fora de Catalunya: la FCE no els avalua (no hi ha variació d'Elo FCE). S'hi afegeixen noms a mesura que apareguin.
FORA_FCE = re.compile(r"mini[\s-]?circuit|lignano|bella italia|benasque|portugal|lisboa|porto\b|coimbra|queima das fitas", re.I)


PROV_CAT = re.compile(r"barcelona|girona|gerona|lleida|l[eé]rida|tarragona|catalu|catalonia|andorra", re.I)
ALIES_CAT = ["villafranca del penedes", "hospitalet", "tarrasa", "lerida", "gerona", "gerona", "san cugat", "sant cugat", "rubi", "badalona", "granollers",
             "villanueva y geltru", "vilanova i la geltru", "lloret de mar", "cambrils", "reus"]


def _sa(t):
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9' ]+", " ", unicodedata.normalize("NFKD", t or "").encode("ascii", "ignore").decode().lower())).strip()


def _municipis_cat():
    """Noms dels municipis de Catalunya (data/municipis-catalunya.json, d'Idescat) en les formes que es poden trobar en un lloc."""
    out = set(ALIES_CAT)
    try:
        for n in json.load(open("data/municipis-catalunya.json", encoding="utf-8")):
            m = re.match(r"^(.*),\s*(l'|la|el|els|les)$", n)
            for v in ([n] if not m else [m.group(1), (m.group(2) + ("" if m.group(2).endswith("'") else " ") + m.group(1))]):
                v = _sa(v)
                if len(v) >= 4:
                    out.add(v)
    except Exception as e:
        print("  no s'ha pogut llegir la llista de municipis:", e)
    return out


MUNICIPIS_CAT = _municipis_cat()


def fora_de_catalunya(lloc, fed):
    """Per la pàgina del torneig a Chess-Results: federació («Catalonia (CAT)») i lloc («Hotel – Ciutat (Província - PAÍS)»).
    Dins de Catalunya: federació CAT, o lloc amb província catalana, Andorra o un municipi de la llista d'Idescat.
    Només se'n fa fora si es veu clar que no és Catalunya; si no hi ha dades, es manté la variació FCE."""
    lloc, fed = lloc or "", fed or ""
    if fed in ("CAT", "AND"):
        return False                         # federació catalana o andorrana: sempre dins
    if fed and fed != "ESP":
        return True                          # federació d'un altre país: sempre fora, sense mirar la llista
    if not lloc.strip():
        return bool(FORA_FCE.search(lloc))   # sense dades, es manté la variació
    par = re.search(r"\(([^)]*)\)\s*$", lloc.strip())
    if par and not PROV_CAT.search(par.group(1)):
        return True                          # (Alicante - SPAIN)...: província de fora
    if PROV_CAT.search(lloc):
        return False
    s = " " + _sa(lloc) + " "
    return not any((" " + v + " ") in s for v in MUNICIPIS_CAT)     # només els ESP es comparen amb la llista de municipis


ETIQ = r"(?:Number of rounds|Tournament type|Rating calculation|Date|Time control|Pairing program|Tournament selection|Links|Tournament director|Chief Arbiter|Deputy Chief Arbiter|Organizer\(s\)|Federation|Location)\b"


def ritme_de_pagina(text):
    """Ritme i modalitat d'un torneig, de la seva pàgina a Chess-Results («Time control (Rapid) 10' + 3''»). {} si no hi surt."""
    mr = re.search(r"Time control\s*\((\w+)\)\s*(.*?)\s+" + ETIQ + r"|Time control\s*\((\w+)\)\s*(.{0,60})$", text)
    if not mr:
        return {"ritme_ll": True}          # pàgina llegida però sense ritme: no es torna a llegir cada vegada
    etiqueta = (mr.group(1) or mr.group(3) or "").capitalize()
    ritme = (mr.group(2) or mr.group(4) or "").strip()[:80]
    return {"ritme_ll": True, "ritme": ritme, "modalitat": modalitat_per_ritme(ritme) or (etiqueta if etiqueta in ("Standard", "Rapid", "Blitz") else "")}


def llegeix_lloc(tnr):
    """Lloc i federació d'un torneig, de la seva pàgina a Chess-Results. Torna None si la pàgina no els dona (no es desa res)."""
    pag = req(f"https://s1.chess-results.com/tnr{tnr}.aspx?lan=1")
    text = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", pag))
    ml = re.search(r"\bLocation\s+(.*?)\s+" + ETIQ, text)
    mf = re.search(r"\bFederation\s+(.*?)\s+" + ETIQ, text)
    cf = re.search(r"\(\s*([A-Z]{3})\s*\)", mf.group(1)) if mf else None
    md = re.search(r"\bDate\s+(\d{4})/(\d\d)/(\d\d)", text)
    if md:
        ini_ = "%s-%s-%s" % md.groups()
    else:
        ini_ = ""
    rit = ritme_de_pagina(text)
    if not ml and not cf:
        try:
            os.makedirs("data/brut/mostres_cr", exist_ok=True)
            if not os.path.exists("data/brut/mostres_cr/sense_lloc.html"):
                open("data/brut/mostres_cr/sense_lloc.html", "w", encoding="utf-8").write(f"<!-- tnr{tnr} -->\n" + pag[:60000])
        except Exception:
            pass
        return None
    return {"lloc": ml.group(1).strip() if ml else "", "fed": cf.group(1) if cf else "", **({"inici": ini_} if ini_ else {}), **rit}


def analitza_llista(t, nostres):
    """Llista de participants (torneigs per equips): jugadors del club trobats a qualsevol fila, sense lloc ni punts."""
    ens, vistos = [], set()
    for tr in re.findall(r"<tr[^>]*class=\"CRg[12]b?\"[^>]*>(.*?)</tr>", t, re.S):
        for x in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", tr, re.S):
            n = norm(html.unescape(re.sub(r"<[^>]+>", "", x)).strip())
            if n in nostres and n not in vistos:
                vistos.add(n)
                ens.append({"nom": nostres[n], "lloc": None, "punts": ""})
    return ens

EQUIPS_RE = re.compile(r"\b(equipos|equips|teams?)\b", re.I)


def previs_equips(previs, club, maxim=4):
    """Torneigs per equips que encara no han començat: la plantilla de l'equip del club en ordre de taulers i el número d'ordre inicial de l'equip.
    Si Chess-Results encara no ho mostra (o no es pot llegir), el torneig es queda amb la simple llista d'inscrits."""
    nostres = {norm(j["nom_cr"]): j["nom"] for j in club}
    fets = 0
    for p in previs.values():
        if fets >= maxim or not EQUIPS_RE.search(p["torneig"]):
            continue
        fets += 1
        try:
            time.sleep(1.5)
            p0 = req(f"https://s1.chess-results.com/tnr{p['tnr']}.aspx?lan=1&art=0&zeilen=99999")
            time.sleep(1.5)
            p20 = req(f"https://s1.chess-results.com/tnr{p['tnr']}.aspx?lan=1&art=20&zeilen=99999")
            os.makedirs("data/brut/mostres_cr", exist_ok=True)
            for art, pl in ((0, p0), (20, p20)):                  # mostres per poder afinar el lector si cal
                open(f"data/brut/mostres_cr/previ{art}_{p['tnr']}.html", "w", encoding="utf-8").write(pl[:120000])
            eq, _, _ = analitza_equips(p0, p20, nostres, {norm(j["nom_cr"]): j["nom_cr"] for j in club},
                                       {str(j["fide"]): norm(j["nom_cr"]) for j in club if j.get("fide")})
            if eq:
                for e in eq:
                    e["jugadors"].sort(key=lambda x: x["bo"])
                p["equips"] = eq
            else:
                print("  previ per equips sense plantilla llegible:", p["tnr"])
        except Exception as e:
            print("  no s'ha pogut llegir l'equip del torneig", p["tnr"], e)


def baixa(club, des, seguiment, ara, t_inici, antiga, limit_cr=35 * 60, limit_total=50 * 60):
    """Baixa de Chess-Results els torneigs recents dels jugadors del club. `antiga` és el data/resultats-jugadors.json anterior."""
    _estat["seguits"], _estat["fins"] = 0, t_inici + limit_total      # temps màxim de tota la lectura (després, res més a la xarxa)
    resultats, errors = [], 0
    if seguiment:
        # seguiment: no es busquen torneigs nous (això ho fa el mode «descobriment»); només es tornen a llegir els ja trobats dels últims dies
        # Els torneigs partits en dues adreces de Chess-Results (p. ex. «Rondas 1» i «Rondas 6-8») només es poden unir si es troben tots dos: per als jugadors que hi són
        # es fa una cerca de descobriment (només d'ells); la resta es rellegeix tal com estava.
        fide_alt = {r.get("fide") for r in antiga.get("resultats", []) if r.get("tnr_alt") and r["fi"] >= des and r.get("fide")}
        resultats = [r for r in antiga.get("resultats", []) if r.get("font") not in ("info64", "ffe", "vesus", "manual") and r["fi"] >= des and r.get("fide") not in fide_alt]
        print(f"Seguiment: {len(resultats)} resultats ja coneguts des de {des}; {len(fide_alt)} jugadors amb torneigs en dues adreces es tornen a cercar")
    consecutius, aturat = 0, False       # salvaguardes: si la font no respon o s'esgota el temps, no es continua demanant (es conserva el que hi havia)
    for j in ([x for x in club if x.get("fide") in fide_alt] if seguiment else club):
        if not j["fide"]:
            continue
        if not aturat and time.time() - t_inici > limit_cr:
            aturat = True
            print(f"  Límit de temps ({limit_cr // 60} min): no es consulten més jugadors; es conserva el que hi havia")
        if aturat:
            resultats += [r for r in antiga.get("resultats", []) if r.get("fide") == j["fide"] and r.get("font") not in ("info64", "ffe", "vesus", "manual")]
            continue
        try:
            time.sleep(1.5)
            tt, _ = cr_torneigs(j["fide"])
            vistos = {x["tnr"] for x in tt}
            try:        # torneigs on el jugador surt sense codi FIDE (locals, d'altres clubs...): cerca per nom i club
                time.sleep(1.5)
                tt += [x for x in cr_torneigs_nom(j) if x["tnr"] not in vistos]
            except Exception as e:
                print("  Chess-Results (per nom): error amb", j["nom"], e)
            for x in tt:
                # sense data de finalització fiable: Chess-Results en dóna una de molt llunyana (p. ex. un torneig de temporada que encara no ha començat) i no se'n pot fer res
                if re.match(r"\d{4}-\d\d-\d\d$", x["fi"]) and x["fi"] >= des and x["fi"] <= (datetime.date.today() + datetime.timedelta(days=120)).isoformat():
                    resultats.append({"jugador": j["nom"], "fide": j["fide"], "font": "chess-results", **x})
            consecutius = 0
        except Exception as e:
            errors += 1
            consecutius += 1
            print("  Chess-Results: error amb", j["nom"], e)
            if consecutius >= 5:
                aturat = True
                print("  Chess-Results no respon (5 errors seguits): no es consulten més jugadors; es conserva el que hi havia")
            resultats += [r for r in antiga.get("resultats", []) if r.get("fide") == j["fide"] and r.get("font") not in ("info64", "ffe", "vesus", "manual")]   # conserva el que hi havia
    D_NOMS = "data/brut/noms_torneigs.json"
    noms = carrega(D_NOMS, {})
    for r in resultats:
        if r["tnr"] not in noms:
            try:
                time.sleep(1.5)
                pag = req(f"https://s1.chess-results.com/tnr{r['tnr']}.aspx?lan=1")
                m = re.search(r"<h2[^>]*>(.*?)</h2>", pag, re.S)
                if m:
                    noms[r["tnr"]] = html.unescape(re.sub(r"<[^>]+>", "", m.group(1))).strip()
            except Exception as e:
                print("  no s'ha pogut llegir el nom del torneig", r["tnr"], e)
        if noms.get(r["tnr"]):
            r["torneig"] = re.sub(r"\s+Rond(?:a|e)?s?\s+[\d\-, ]+.*$", "", noms[r["tnr"]], flags=re.I).strip()
    os.makedirs("data/brut", exist_ok=True)
    json.dump(noms, open(D_NOMS, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    # data d'inici de cada torneig (per no mostrar els que encara no han començat)
    D_DATES = "data/brut/dates_torneigs.json"
    dates = carrega(D_DATES, {})
    D_LLOC = "data/brut/lloc_torneigs.json"
    avui_lloc = datetime.date.today().isoformat()
    antic_lloc = (datetime.date.today() - datetime.timedelta(days=7)).isoformat()
    # les lectures buides (la pàgina del torneig no diu on es juga) es recorden 7 dies: abans es repetien a cada execució i costaven uns 10 minuts cada cop
    llocs = {k: v for k, v in carrega(D_LLOC, {}).items() if v and (v.get("lloc") or v.get("fed") or (v.get("buit") and v["buit"] >= antic_lloc))}
    for r in resultats:
        if r["tnr"] not in dates or r["tnr"] not in llocs or not llocs[r["tnr"]].get("ritme_ll"):
            try:
                time.sleep(1.2)
                pag = req(f"https://s1.chess-results.com/tnr{r['tnr']}.aspx?lan=1")
                text = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", pag))
                m = re.search(r"\bDate\s+(\d{4}/\d\d/\d\d)", text)
                if m:
                    dates[r["tnr"]] = m.group(1).replace("/", "-")
                ml = re.search(r"\bLocation\s+(.*?)\s+" + ETIQ, text)
                mf = re.search(r"\bFederation\s+(.*?)\s+" + ETIQ, text)
                cf = re.search(r"\(\s*([A-Z]{3})\s*\)", mf.group(1)) if mf else None
                if ml or cf:
                    llocs[r["tnr"]] = {"lloc": ml.group(1).strip() if ml else "", "fed": cf.group(1) if cf else "", **({"inici": dates[r["tnr"]]} if r["tnr"] in dates else {}), **ritme_de_pagina(text)}
                else:
                    llocs[r["tnr"]] = {"lloc": "", "fed": "", "buit": avui_lloc}
                    print("  sense lloc a la pàgina del torneig", r["tnr"])
            except Exception as e:
                print("  no s'ha pogut llegir la data del torneig", r["tnr"], e)
    json.dump(dates, open(D_DATES, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    json.dump(llocs, open(D_LLOC, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    avui_iso = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")
    for r in resultats:
        ll = llocs.get(r["tnr"]) or {}
        r["inici"] = dates.get(r["tnr"]) or ll.get("inici")
        if ll.get("modalitat"):          # el ritme de la pàgina del torneig mana sobre el que hagués quedat a la memòria cau de fitxes (sense ritme)
            r["modalitat"], r["ritme"] = ll["modalitat"], ll.get("ritme", "")
        if ll.get("lloc"):
            r["lloc"] = ll["lloc"]
        r["fora_cat"] = fora_de_catalunya(ll.get("lloc"), ll.get("fed")) or bool(FORA_FCE.search(r["torneig"]))
    # Torneigs que encara no han començat (fins a 30 dies endavant) amb jugadors del club inscrits: es desen a part (data/previs-jugadors.json),
    # només per mostrar a Competicions qui s'hi ha apuntat; no compten com a resultats (no tenen partides ni Elo).
    limit_previ = (datetime.date.today() + datetime.timedelta(days=30)).isoformat()
    previs = {}
    for r in resultats:
        if r["inici"] and avui_iso < r["inici"] <= limit_previ:
            p_ = previs.setdefault(r["tnr"], {"tnr": r["tnr"], "torneig": r["torneig"], "inici": r["inici"], "fi": r["fi"], "lloc": r.get("lloc", ""), "fed": r.get("fed", ""),
                                              "url": f"https://s1.chess-results.com/tnr{r['tnr']}.aspx?lan=1", "jugadors": []})
            if r["jugador"] not in p_["jugadors"]:
                p_["jugadors"].append(r["jugador"])
            if r.get("snr"):
                p_.setdefault("ordre", {})[r["jugador"]] = r["snr"]          # número d'ordre inicial (torneigs individuals)
    if not seguiment:
        previs_equips(previs, club)
    if seguiment:
        # el seguiment no cerca torneigs nous: només veu uns pocs jugadors i, si es desés, esborraria els inscrits dels altres fins a la propera cerca completa
        print("Seguiment: no es toca la llista de torneigs per començar")
    else:
        json.dump({"actualitzat": ara, "previs": sorted(deduplica_previs(list(previs.values())), key=lambda x: (x["inici"], x["torneig"]))}, open("data/previs-jugadors.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print(f"Torneigs per començar amb jugadors del club: {len(previs)}")
    resultats = [r for r in resultats if not r["inici"] or r["inici"] <= avui_iso]     # només els que ja han començat
    resultats.sort(key=lambda r: (r["fi"], r["jugador"]), reverse=True)
    print(f"Chess-Results: {len(resultats)} resultats des de {des}, {errors} errors")

    print(f"[{int(time.time() - t_inici) // 60} min] resultats de Chess-Results llegits", flush=True)
    # 4. resum global de cada torneig: quants dels nostres hi juguen i com els va (classificació)
    nostres = {norm(j["nom_cr"]): j["nom"] for j in club}
    tornejos, mostres, equips_mostres, jocs_equip, eq_de = {}, 0, 0, {}, {}
    for r in resultats:
        t = tornejos.setdefault(r["tnr"], {"tnr": r["tnr"], "torneig": r["torneig"], "fi": r["fi"], "rondes": r["rondes"], "de": r["de"],
                                          "inici": r.get("inici"), "url": f"https://s1.chess-results.com/tnr{r['tnr']}.aspx?lan=1", "classificacio": None})
    # Classificació dels torneigs ja acabats (fa més de 3 dies): no canvia, es llegeix una sola vegada i es guarda (abans costava uns 4 minuts a cada execució)
    D_CLA = "data/brut/classificacions_cr.json"
    c_cla = carrega(D_CLA, {})
    limit_acabat = (datetime.date.today() - datetime.timedelta(days=3)).isoformat()
    for tnr, t in list(tornejos.items())[:80]:
        cc = c_cla.get(tnr)
        if cc and t["fi"] < limit_acabat and cc.get("fi") == t["fi"]:
            t["classificacio"] = cc["classificacio"]
            if cc.get("equips"):
                t["equips"] = cc["equips"]
                jocs_equip[tnr] = cc["jocs"]
                eq_de[tnr] = cc["eq_de"]
            continue
        try:
            time.sleep(1.5)
            pag = req(f"https://s1.chess-results.com/tnr{tnr}.aspx?lan=1&art=1&zeilen=99999")
            t["classificacio"] = analitza_classificacio(pag, nostres)
            # el nom de la taula de classificació pot no coincidir amb el de Chess-Results del soci (ordre, accents, segon cognom):
            # els resultats ja identificats per ID FIDE o fitxa individual també compten
            if t["classificacio"] is not None:
                ja = {x["nom"] for x in t["classificacio"]["jugadors"]}
                for r in resultats:
                    if r["tnr"] == tnr and r["jugador"] not in ja and r.get("lloc"):
                        t["classificacio"]["jugadors"].append({"nom": r["jugador"], "lloc": r["lloc"], "punts": r["punts"]})
                t["classificacio"]["jugadors"].sort(key=lambda x: x["lloc"] or 99999)
            if not (t["classificacio"] or {}).get("jugadors"):      # torneig per equips
                time.sleep(1.5)
                p0 = req(f"https://s1.chess-results.com/tnr{tnr}.aspx?lan=1&art=0&zeilen=99999")
                time.sleep(1.5)
                p20 = req(f"https://s1.chess-results.com/tnr{tnr}.aspx?lan=1&art=20&zeilen=99999")
                if equips_mostres < 3:
                    os.makedirs("data/brut/mostres_cr", exist_ok=True)
                    for art, pl in ((0, p0), (20, p20)):
                        open(f"data/brut/mostres_cr/llista{art}_{tnr}.html", "w", encoding="utf-8").write(pl[:120000])
                    equips_mostres += 1
                eq, jocs, rmax = analitza_equips(p0, p20, nostres, {norm(j["nom_cr"]): j["nom_cr"] for j in club},
                                                  {str(j["fide"]): norm(j["nom_cr"]) for j in club if j.get("fide")})
                if eq:
                    t["equips"] = eq
                    jocs_equip[tnr] = jocs
                    eq_de[tnr] = {j["nom"]: e["nom"] for e in eq for j in e["jugadors"] if j["del_club"]}
                    t["classificacio"] = {"ronda": rmax or None, "participants": len(eq), "jugadors": [], "equips": True}
                else:
                    for art, pl in (("1", pag), ("0", p0), ("20", p20)):
                        open(f"data/brut/mostres_cr/nul_{tnr}_{art}.html", "w", encoding="utf-8").write(pl[:150000])
                    ens = analitza_llista(p20, nostres) or analitza_llista(p0, nostres)
                    if ens:
                        t["classificacio"] = {"ronda": None, "participants": None, "jugadors": ens, "llista": True}
            if t["classificacio"] is not None and t["fi"] < limit_acabat:
                c_cla[tnr] = {"fi": t["fi"], "classificacio": t["classificacio"]}
                if t.get("equips") and tnr in jocs_equip:
                    c_cla[tnr].update({"equips": t["equips"], "jocs": jocs_equip[tnr], "eq_de": eq_de[tnr]})
            if mostres < 3:     # mostres per poder afinar el lector (una per torneig, només les primeres)
                os.makedirs("data/brut/mostres_cr", exist_ok=True)
                open(f"data/brut/mostres_cr/classificacio_{tnr}.html", "w", encoding="utf-8").write(pag[:120000])
                mostres += 1
        except Exception as e:
            print("  classificació no disponible per al torneig", tnr, e)
    json.dump({k: v for k, v in c_cla.items() if k in tornejos or v.get("fi", "") >= (datetime.date.today() - datetime.timedelta(days=400)).isoformat()}, open(D_CLA, "w", encoding="utf-8"), ensure_ascii=False)
    # torneigs partits en diverses adreces (p. ex. «Rondas 1» i «Rondas 6-8»): un de sol, el que va més avançat
    def clau_t(n):
        return re.sub(r"[^a-z0-9]+", " ", re.sub(r"\s+Rond(?:a|e)?s?\s+[\d\-, ]+.*$", "", n or "", flags=re.I).lower()).strip()
    grups = {}
    for tnr, t in tornejos.items():
        grups.setdefault(clau_t(t["torneig"]), []).append(tnr)
    germans = {}
    for k, tn in grups.items():
        if len(tn) > 1:
            def punts_tot(x):
                return sum(float(str(p.get("punts") or 0).replace(",", ".") or 0) for p in ((tornejos[x]["classificacio"] or {}).get("jugadors") or []))
            mill = max(tn, key=lambda x: ((tornejos[x]["classificacio"] or {}).get("ronda") or 0, punts_tot(x), tornejos[x]["de"] or 0))
            germans[mill] = [x for x in tn if x != mill]
            for x in germans[mill]:
                del tornejos[x]
            tornejos[mill]["torneig"] = re.sub(r"\s+Rond(?:a|e)?s?\s+[\d\-, ]+.*$", "", tornejos[mill]["torneig"], flags=re.I).strip()
    pare = {x: m for m, l in germans.items() for x in l}
    for r in resultats:
        if r["tnr"] in pare:
            r["tnr_alt"] = r["tnr"]
            r["tnr"] = pare[r["tnr"]]
        if r["tnr"] in tornejos:
            r["torneig"] = tornejos[r["tnr"]]["torneig"]
    print(f"[{int(time.time() - t_inici) // 60} min] classificacions i equips llegits", flush=True)
    # fitxa de cada jugador en cada torneig: partides jugades, performance i variació FIDE de Chess-Results
    fets = {}
    ant_idx = {(x["jugador"], x["tnr"]): x for x in antiga.get("resultats", [])}
    D_FX = "data/brut/fitxes.json"
    c_fitxes = carrega(D_FX, {})
    avui_iso = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")
    print(f"[{int(time.time() - t_inici) // 60} min] fitxes de jugador: {len(c_fitxes)} en memoria cau", flush=True)
    for r in resultats:
        k = (r["jugador"], r["tnr"])
        try:
            ck = r["url"]
            if ck in c_fitxes and r["fi"] < avui_iso:        # torneig acabat: la fitxa ja no canvia
                f = c_fitxes[ck]
            else:
                time.sleep(1.2)
                f = analitza_fitxa(req(r["url"]), r["fi"] >= avui_iso)
                if r["fi"] < avui_iso and f.get("partides"):
                    c_fitxes[ck] = f
        except Exception as e:
            print("  fitxa no disponible", r["url"], e)
            vell = ant_idx.get(k)           # si la font no respon, es conserven les partides que ja teníem (no es publiquen buides)
            f = {"partides": [dict(g) for g in vell["partides"]], **{c: vell[c] for c in ("perf", "fide_var", "rtg_n", "rtg_i", "punts", "modalitat") if vell.get(c) is not None}} if vell and vell.get("partides") else {"partides": []}
        if r.get("tnr_alt"):      # mostra de la fitxa de l'altra adreça del torneig, per depurar
            print("  fitxa alternativa", r["tnr_alt"], r["jugador"], len(f["partides"]), "partides")
            if not os.path.exists(f"data/brut/mostres_cr/fitxa_alt_{r['tnr_alt']}.html"):
                try:
                    open(f"data/brut/mostres_cr/fitxa_alt_{r['tnr_alt']}.html", "w", encoding="utf-8").write(req(r["url"])[:120000])
                except Exception:
                    pass
        if (not f["partides"] and r["tnr"] not in jocs_equip) or r["tnr"] in germans:
            nom_m = f"data/brut/mostres_cr/fitxa_{'buida' if not f['partides'] else 'unida'}_{r['tnr_alt'] if r.get('tnr_alt') else r['tnr']}.html"
            if not os.path.exists(nom_m):
                try:
                    open(nom_m, "w", encoding="utf-8").write(req(r["url"])[:120000])
                except Exception:
                    pass
        for g in f["partides"]:
            g["tnr"] = r.get("tnr_alt") or r["tnr"]
        if r["tnr"] in jocs_equip:
            de_equip = [{**g, "tnr": r["tnr"]} for g in jocs_equip[r["tnr"]].get(r["jugador"], [])]
            vistes_e = {g["ronda"] for g in de_equip}
            equip_j = eq_de.get(r["tnr"], {}).get(r["jugador"])
            f = {**f, "partides": sorted(de_equip + [{**g, "equip": equip_j} for g in f["partides"] if g["ronda"] not in vistes_e], key=lambda g: g["ronda"])}
        if k in fets:                          # mateix jugador a una altra adreça del mateix torneig: suma les rondes que falten
            vell = fets[k]
            if not r.get("tnr_alt"):           # la fitxa de l'adreça bona mana en punts, lloc i performance
                f, vell = {**f, "partides": list(f["partides"])}, vell
                vistes = {x["ronda"] for x in f["partides"]}
                f["partides"] += [x for x in vell["partides"] if x["ronda"] not in vistes]
                fets[k] = f
            else:
                vistes = {x["ronda"] for x in vell["partides"]}
                vell["partides"] += [x for x in f["partides"] if x["ronda"] not in vistes]
            fets[k]["partides"].sort(key=lambda x: x["ronda"])
        else:
            fets[k] = f
        if len(fets) <= 2:
            os.makedirs("data/brut/mostres_cr", exist_ok=True)
    for r in resultats:
        f = fets.get((r["jugador"], r["tnr"]), {})
        r["partides"] = f.get("partides", [])
        r["emparellaments"] = f.get("emparellaments", []) if r["tnr"] not in jocs_equip else []
        for c in ("perf", "fide_var", "rtg_n", "rtg_i", "punts", "modalitat"):
            if f.get(c) is not None:
                r[c] = f[c]
    json.dump(c_fitxes, open(D_FX, "w", encoding="utf-8"), ensure_ascii=False)
    print(f"[{int(time.time() - t_inici) // 60} min] fitxes llegides", flush=True)
    # data de cada ronda jugada (per ordenar les partides per dia)
    D_RD, D_TL = "data/brut/dates_rondes.json", "data/brut/taules_rondes.json"
    cache_rd, cache_tl = carrega(D_RD, {}), carrega(D_TL, {})
    for r in resultats:
        for g in r["partides"]:
            try:
                d, tl = info_ronda(g["tnr"], g["ronda"], cache_rd, cache_tl, g["tnr"] in jocs_equip)
            except Exception as e:
                d, tl = None, {}
                print("  data de ronda no disponible", g["tnr"], g["ronda"], e)
            if d:
                g["data"] = d
            if g.get("equip") and tl.get(norm(g["equip"])):
                g["taula"] = tl[norm(g["equip"])]
    for r in resultats:           # data de la ronda dels emparellaments (una sola petició per ronda nova)
        for g in r.get("emparellaments", []):
            g["tnr"] = r.get("tnr_alt") or r["tnr"]
            try:
                d, _ = info_ronda(g["tnr"], g["ronda"], cache_rd, cache_tl, False)
            except Exception as e:
                d = None
                print("  data de ronda no disponible", g["tnr"], g["ronda"], e)
            if d:
                g["data"] = d
        passats = [g for g in r.get("emparellaments", []) if g.get("bye") and g.get("data") and g["data"] < avui_iso]
        if passats:          # el bye de 0 punts d'una ronda ja jugada és una partida (descans), no un emparellament
            r["emparellaments"] = [g for g in r["emparellaments"] if g not in passats]
            r["partides"] = sorted(r["partides"] + [{"ronda": g["ronda"], "rival": "Descans", "res": "-", "inc": True, "tnr": g["tnr"], "data": g["data"]} for g in passats], key=lambda g: g["ronda"])
    json.dump(cache_rd, open(D_RD, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    json.dump(cache_tl, open(D_TL, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    vistos, uniq = set(), []
    for r in resultats:                           # una sola fila per jugador i torneig
        k = (r["jugador"], r["tnr"])
        if k not in vistos:
            vistos.add(k)
            uniq.append(r)
    resultats = uniq
    # fitxa del rival a cada partida: el seu Elo FCE (nacional) i FIDE (internacional) del torneig
    D_RIV = "data/brut/rivals.json"
    riv = carrega(D_RIV, {})
    t0 = time.time()
    for r in resultats:
        for g in r.get("partides", []):
            sn = g.get("snr_riv")
            if not sn:
                continue
            k = f"{g['tnr']}:{sn}"
            acabat = r["fi"] < avui_iso
            v_ = riv.get(k)
            # rival sense cap Elo (ni nacional ni internacional; pot tenir codi FIDE sense Elo encara): amb el torneig acabat es guarda la seva performance (4t valor) per calcular les partides contra ell
            sense_elo = bool(v_) and len(v_) >= 3 and not (v_[0] or v_[1])
            if (k not in riv or len(riv[k]) < 3 or (acabat and sense_elo and len(v_) < 4)) and time.time() - t0 < 20 * 60:     # el que falti es completa a la propera execucio
                try:
                    time.sleep(1.0)
                    f = analitza_fitxa(req(f"https://s1.chess-results.com/tnr{g['tnr']}.aspx?lan=1&art=9&snr={sn}"))
                    riv[k] = [f.get("rtg_n"), f.get("rtg_i"), f.get("fide_id") or ""]
                    if acabat and not (riv[k][0] or riv[k][1]):
                        riv[k].append(f.get("perf"))
                    if len(riv) % 40 == 0:
                        json.dump(riv, open(D_RIV, "w", encoding="utf-8"), ensure_ascii=False)
                except Exception as e:
                    print("  fitxa del rival no disponible", k, e)
            if k in riv:
                g["rn"], g["ri"] = riv[k][0], riv[k][1]
                g["fid"] = riv[k][2] if len(riv[k]) > 2 else None
                if len(riv[k]) > 3 and riv[k][3]:
                    g["rp"] = riv[k][3]                   # performance del rival al final del torneig (només si no té cap Elo)
                g["rtg_n"], g["rtg_i"] = riv[k][0] or g.get("rtg_n"), riv[k][1] or g.get("rtg_i")
    json.dump(riv, open(D_RIV, "w", encoding="utf-8"), ensure_ascii=False)
    print(f"Fitxes de rivals: {len(riv)} desades")
    cr = {"actualitzat": ara, "des": des, "mode": "seguiment" if seguiment else "descobriment", "resultats": resultats, "tornejos": tornejos}
    os.makedirs("data/brut", exist_ok=True)
    json.dump(cr, open(D_CR, "w", encoding="utf-8"), ensure_ascii=False)
    return {"resultats": resultats, "tornejos": tornejos, "llocs": llocs, "errors": errors}
