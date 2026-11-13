#!/usr/bin/env python3
"""Actualitza els jugadors del club i els seus últims resultats.

1. Llista del club a la FCE (club 290)  -> data/jugadors.json  (també dona el nombre de federats)
2. Codi FIDE de cada jugador nou (info.php de la FCE; es guarda i no es torna a demanar)
3. Per cada codi FIDE, els torneigs recents de Chess-Results  -> data/resultats-jugadors.json

Cada font és independent: si una falla, es conserven les últimes dades bones i es continua.
Ús:  python3 tools/jugadors.py [--dies 30] [--prova-cr fitxer.html]   (--prova-cr: només prova l'analitzador)
"""
import glob
import json, os, re, sys, time, html, datetime, unicodedata, urllib.request, urllib.parse, http.cookiejar
sys.path.insert(0, os.path.dirname(__file__))
from importar_chessresults import nom_public

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
FCE = "https://escacs.cat/components/com_fce/gmvw20/conn/"
ID_CLUB = "290"
CR = "https://s1.chess-results.com/SpielerSuche.aspx?lan=2&SNode=S0"   # sempre el mateix node: el viewstate no val entre nodes
D_JUG, D_RES = "data/jugadors.json", "data/resultats-jugadors.json"

cj = http.cookiejar.CookieJar()
op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))


def req(url, data=None, headers=None, intents=4, espera=3, temps=60):
    h = {"User-Agent": UA, "Accept-Language": "ca,es;q=0.8", "Accept": "*/*"}
    h.update(headers or {})
    if data is not None:
        data = urllib.parse.urlencode(data).encode()
        h.setdefault("Content-Type", "application/x-www-form-urlencoded; charset=UTF-8")
    for i in range(intents):
        try:
            with op.open(urllib.request.Request(url, data=data, headers=h), timeout=temps) as r:
                return r.read().decode("utf-8", "replace")
        except Exception as e:
            if i == intents - 1:
                raise
            time.sleep(espera * (i + 1))      # 429 i similars: esperar i reintentar


def carrega(p, per_defecte):
    try:
        return json.load(open(p, encoding="utf-8"))
    except Exception:
        return per_defecte


# ---------------------------------------------------------------- 1. llista del club a la FCE
def clau(d, *noms):
    for n in noms:
        for k in d:
            if k.lower() == n.lower():
                return d[k]
    return None


def llista_club():
    t = req(FCE + "resultatCerca.php", {
        "idJugador": "", "nomLLarg": "", "elo_XYZ1": "", "elo_XYZ2": "", "idClub": ID_CLUB, "titol": "", "edat": "", "sexe": "",
        "limitNoRows": "500", "nomFitxa": "c_jugadors_0.xml", "dadesCercar": "jugadors_0.xml"},
        {"X-Requested-With": "XMLHttpRequest", "Referer": "https://escacs.cat/index.php/component/fce?op=2", "Origin": "https://escacs.cat"})
    os.makedirs("data/brut", exist_ok=True)
    (None if os.environ.get("NOMES_PROVA") else open("data/brut/fce_club.json", "w", encoding="utf-8").write(t[:2_000_000]))   # per poder ajustar-ho si el format canvia
    j = json.loads(t)
    files = (j.get("source") or {}).get("localdata") or j.get("localdata") or j.get("rows") or []
    out = []
    for f in files:
        idj = clau(f, "idJugador", "codi", "id")
        nom = clau(f, "nomLlarg", "nomComplet", "nom")
        if not idj or not nom:
            continue
        out.append({"id": str(idj), "nom_cr": nom.strip(), "nom": nom_public(nom.title() if nom.isupper() else nom),
                    "sexe": clau(f, "sexe") or "", "elo": num(clau(f, "elo")), "elo_rapid": num(clau(f, "eloR")),
                    "var": fnum(clau(f, "variacio")), "var_rapid": fnum(clau(f, "variacioR")),
                    "titol": clau(f, "titol") or "", "categoria": clau(f, "descripcio") or ""})
    if not out and files:
        print("ATENCIÓ: claus del jugador no reconegudes:", list(files[0].keys()))
    return out


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


# ---------------------------------------------------------------- 2. codi FIDE
def codi_fide(idj):
    t = req(FCE + "info.php", {"finfo": "c_f_jugador", "idJugador": idj, "p1": "", "n1": "", "p2": "", "n2": "", "list1": ""},
            {"X-Requested-With": "XMLHttpRequest", "Referer": "https://escacs.cat/index.php/component/fce?op=2"})
    t = t.replace('\\"', '"')
    if not os.path.exists("data/brut/info_mostra.txt"):
        os.makedirs("data/brut", exist_ok=True)
        open("data/brut/info_mostra.txt", "w", encoding="utf-8").write(f"idJugador={idj}\n{t[:6000]}")
    m = re.search(r'codiFide[^>]{0,200}?value="(\d+)"', t) or re.search(r'value="(\d+)"[^>]{0,200}?codiFide', t)
    return m.group(1) if m else ""


# ---------------------------------------------------------------- 3. Chess-Results: torneigs d'un jugador
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


def norm(x):
    import unicodedata
    x = unicodedata.normalize("NFKD", x or "").encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z]+", " ", x).strip()


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


def analitza_fitxa(t):
    """Fitxa d'un jugador en un torneig (art=9): resum (performance, variació FIDE) i partides ja jugades."""
    out = {"partides": []}
    mm = re.search(r"Time control\s*\((\w+)\)", t)
    if mm:
        out["modalitat"] = mm.group(1).capitalize()
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
                rr = f[ix["Res."]].split()
                m = re.fullmatch(r"([01½])(K?)", rr[-1]) if rr else None
                if not m:
                    continue          # ronda no jugada encara
                nom = cel_(f, "Name")
                if nom.lower() == "not paired" and m.group(1) == "0":
                    continue          # no apareada i sense punts: no era al torneig aquella ronda
                out["partides"].append({"ronda": int(f[0]), "rival": "Descans" if nom.lower() == "not paired" else (nom_public(nom) if nom else ""),
                                        "rtg_i": num(cel_(f, "RtgI")) or None, "rtg_n": num(cel_(f, "RtgN")) or None, "rtg_x": num(cel_(f, "Rtg")) or None,
                                        "snr_riv": int(cel_(f, "SNo")) if cel_(f, "SNo").isdigit() and int(cel_(f, "SNo")) > 0 else None, "club": cel_(f, "Club/City"),
                                        "bo": num(cel_(f, "Bo.")), "color": colors[fi_] if fi_ < len(colors) else "", "res": m.group(1),
                                        **({"inc": True} if m.group(2) or nom.lower() == "not paired" else {})})
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
                m = re.match(r"^\d+\.\s+(.*?)\s*\(RtgAvg", txt)
                if m:
                    equip, jug, cap = m.group(1).strip(), None, None
                    equips.setdefault(equip, [])
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
        nostres_eq.append({"nom": nom, **c, "jugadors": [{"nom": nostres.get(norm(x["cr"])) or nom_public(x["cr"]), "del_club": norm(x["cr"]) in nostres, "bo": x["bo"], "punts": x["pts"], "res": x["res"]} for x in plant]})
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


# ---------------------------------------------------------------- Elo FCE estimat per torneig
DIF_FIDE_FCE = [(2401, 25, 2450), (2250, 50, 2325), (2100, 75, 2205), (1950, 105, 2095), (1800, 145, 1990), (1650, 190, 1890), (0, 240, 0)]


def fce_a_partir_de(base):
    """Taula d'equivalència FIDE -> Elo català de la FCE (factor corrector, amb mínim)."""
    for llindar, suma, minim in DIF_FIDE_FCE:
        if base >= llindar:
            return max(base + suma, minim)
    return base


def hist_fce(idj):
    """Elo mensual (estàndard, ràpid) d'un jugador: {YYYYMM: (std, ràpid)} de cercaelo.php."""
    txt = req(f"https://escacs.cat/components/com_fce/gmvw20/conn/cercaelo.php?idJugador={idj}&type=1", intents=2, espera=2, temps=20)
    txt = html.unescape(re.sub(r"<[^>]+>", " ", txt))
    if not os.path.exists("data/brut/cercaelo_mostra.txt"):
        os.makedirs("data/brut", exist_ok=True)
        open("data/brut/cercaelo_mostra.txt", "w", encoding="utf-8").write(f"idJugador={idj}\n{txt[:3000]}")
    out = {}
    parts = re.split(r"\b(20\d{2}(?:0[1-9]|1[0-2]))\b", txt)
    for i in range(1, len(parts) - 1, 2):
        nums = [int(x) for x in re.findall(r"\b\d{3,4}\b", parts[i + 1])[:2]]
        if nums:
            out[parts[i]] = (nums[0], nums[1] if len(nums) > 1 else None)
    return out


def elo_a(hist, ym, rapid):
    """Elo d'un jugador a la llista del mes ym: l'últim valor amb mes <= ym."""
    ms = [m for m in hist if m <= ym and hist[m][1 if rapid else 0]]
    return hist[max(ms)][1 if rapid else 0] if ms else None


def k_fce(elo, categoria, rapid):
    m = re.search(r"Sub-?\s*(\d+)", categoria or "")
    k = 40 if (m and int(m.group(1)) <= 18 and elo < 2300) else (20 if elo < 2400 else 10)
    return k / 2 if rapid else k


def k_fide(elo, categoria):
    m = re.search(r"Sub-?\s*(\d+)", categoria or "")
    return 40 if (m and int(m.group(1)) <= 18 and elo < 2300) else (20 if elo < 2400 else 10)


def esperat(d):
    """Resultat esperat del jugador; d = Elo del rival - Elo del jugador (limit de 400 punts)."""
    d = max(-400, min(400, d))
    return 1 / (1 + 10 ** (d / 400))


# Taula de conversio de la FIDE (Handbook B.02, 8.1.2): diferencia d'Elo -> puntuacio esperada del jugador amb mes Elo. La FIDE usa la taula, no la formula.
_TAULA_FIDE = [(3, .50), (10, .51), (17, .52), (25, .53), (32, .54), (39, .55), (46, .56), (53, .57), (61, .58), (68, .59), (76, .60), (83, .61), (91, .62),
               (98, .63), (106, .64), (113, .65), (121, .66), (129, .67), (137, .68), (145, .69), (153, .70), (162, .71), (170, .72), (179, .73), (188, .74),
               (197, .75), (206, .76), (215, .77), (225, .78), (235, .79), (245, .80), (256, .81), (267, .82), (278, .83), (290, .84), (302, .85), (315, .86),
               (328, .87), (344, .88), (357, .89), (374, .90), (391, .91), (411, .92)]


def esperat_fide(d):
    """Puntuacio esperada del jugador segons la taula de la FIDE; d = Elo del rival - Elo del jugador (maxim 400 de diferencia)."""
    a = min(abs(d), 400)
    pd = next((p for lim, p in _TAULA_FIDE if a <= lim), .92)
    return 1 - pd if d > 0 else pd


def ratings_rival(g):
    """(Elo FCE, Elo FIDE) del rival: de la seva fitxa del torneig si la tenim; si no, de les columnes RtgN / RtgI."""
    return g.get("rn") or g.get("rtg_n"), g.get("ri") or g.get("rtg_i")


def modalitat_elo(r):
    m = (r.get("modalitat") or "Standard").lower()
    return m if m in ("standard", "rapid", "blitz") else "standard"


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


def llegeix_lloc(tnr):
    """Lloc i federació d'un torneig, de la seva pàgina a Chess-Results. Torna None si la pàgina no els dona (no es desa res)."""
    pag = req(f"https://s1.chess-results.com/tnr{tnr}.aspx?lan=1")
    text = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", pag))
    ml = re.search(r"\bLocation\s+(.*?)\s+" + ETIQ, text)
    mf = re.search(r"\bFederation\s+(.*?)\s+" + ETIQ, text)
    cf = re.search(r"\(\s*([A-Z]{3})\s*\)", mf.group(1)) if mf else None
    if not ml and not cf:
        try:
            os.makedirs("data/brut/mostres_cr", exist_ok=True)
            if not os.path.exists("data/brut/mostres_cr/sense_lloc.html"):
                open("data/brut/mostres_cr/sense_lloc.html", "w", encoding="utf-8").write(f"<!-- tnr{tnr} -->\n" + pag[:60000])
        except Exception:
            pass
        return None
    return {"lloc": ml.group(1).strip() if ml else "", "fed": cf.group(1) if cf else ""}


def variacio_fce(r, hist, categoria):
    """Variacio estimada de l'Elo FCE d'un torneig: suma de K*(resultat - esperat) amb l'Elo FCE del jugador del mes de cada ronda.
    El blitz (llampec) compta amb l'Elo rapid. Rival sense Elo FCE: FIDE + diferencial; sense cap: performance + diferencial."""
    rapid = modalitat_elo(r) in ("rapid", "blitz")
    tot, n, inici = 0.0, 0, None
    for g in r.get("partides", []):
        if g.get("inc") or g["res"] not in ("1", "0", "½", "+", "-"):
            continue
        ym = (g.get("data") or r.get("inici") or r["fi"])[:7].replace("-", "")
        R = elo_a(hist, ym, rapid)
        rn, ri = ratings_rival(g)
        opp = rn
        if not opp:
            base = ri or r.get("perf") or None
            opp = fce_a_partir_de(base) if base else None
        if not R or not opp:
            continue
        s = {"1": 1, "+": 1, "½": 0.5, "0": 0, "-": 0}[g["res"]]
        k = k_fce(R, categoria, rapid)
        g["fce"] = {"d": round(k * (s - esperat(opp - R)), 1), "k": k, "r": R, "opp": opp}
        tot += k * (s - esperat(opp - R))
        n += 1
        inici = inici or R
    return {"var": round(tot, 1), "partides": n, "elo_inici": inici, "estimat": True} if n else None


def hist_fide(fide):
    """Elo FIDE mensual d'un jugador (ratings.fide.com): {YYYYMM: {"standard": x, "rapid": y, "blitz": z}}. Si no es pot llegir, {}."""
    txt = req(f"https://ratings.fide.com/a_chart_data.phtml?event={fide}&period=0", data={}, headers={"X-Requested-With": "XMLHttpRequest"}, intents=2, espera=2, temps=20).strip().lstrip("\ufeff").strip()
    if not txt:
        raise RuntimeError("resposta buida de la FIDE (limit de consultes?)")
    if not os.path.exists("data/brut/fide_mostra.txt"):
        os.makedirs("data/brut", exist_ok=True)
        open("data/brut/fide_mostra.txt", "w", encoding="utf-8").write(f"event={fide}\n{txt[:3000]}")
    MES = {m: i + 1 for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"])}
    try:
        dades = json.loads(txt)
    except Exception:
        return {}
    if isinstance(dades, dict):
        dades = next((v for v in dades.values() if isinstance(v, list)), [])
    out = {}
    for it in dades if isinstance(dades, list) else []:
        if not isinstance(it, dict):
            continue
        ym = None
        per = str(it.get("period") or it.get("date") or "")
        mm = re.match(r"(\d{4})-(\d\d)", per)
        if mm:
            ym = mm.group(1) + mm.group(2)
        else:
            mm = re.match(r"(\d{4})-([A-Za-z]{3})", str(it.get("date_2") or ""))
            if mm and mm.group(2).lower() in MES:
                ym = f"{mm.group(1)}{MES[mm.group(2).lower()]:02d}"
        if not ym:
            continue

        def val(*ks):
            for k in ks:
                for kk in it:
                    if kk.lower() == k and str(it[kk]).strip().isdigit() and int(it[kk]) > 0:
                        return int(it[kk])
        out[ym] = {"standard": val("rating"), "rapid": val("rapid_rtng"), "blitz": val("blitz_rtng")}
    return out


def fide_a(hist, ym, modal):
    ms = [m for m in hist if m <= ym and hist[m].get(modal)]
    return hist[max(ms)][modal] if ms else None


def variacio_fide(r, hist, categoria, hist_riv=None):
    """Variacio de l'Elo FIDE calculada per nosaltres amb l'Elo FIDE del mes de cada ronda; els rivals sense Elo FIDE no compten.
    Si no tenim l'historial de la FIDE, s'usa l'Elo internacional de la llista inicial del torneig."""
    modal = modalitat_elo(r)
    tot, n, inici = 0.0, 0, None
    for g in r.get("partides", []):
        if g.get("inc") or g["res"] not in ("1", "0", "½", "+", "-"):
            continue
        ym = (g.get("data") or r.get("inici") or r["fi"])[:7].replace("-", "")
        R = fide_a(hist, ym, modal) or (r.get("rtg_i") if modal == "standard" else None)
        hr = (hist_riv or {}).get(str(g.get("fid"))) if g.get("fid") else None
        ri = fide_a(hr["h"], ym, modal) if hr and hr.get("h") else (None if hr else ratings_rival(g)[1])
        if not R or not ri:
            continue
        s = {"1": 1, "+": 1, "½": 0.5, "0": 0, "-": 0}[g["res"]]
        k = k_fide(R, categoria)
        g["fide"] = {"d": round(k * (s - esperat_fide(ri - R)), 1), "k": k, "r": R, "opp": ri}
        tot += k * (s - esperat_fide(ri - R))
        n += 1
        inici = inici or R
    return {"var": round(tot, 1), "partides": n, "elo_inici": inici, "estimat": True} if n else None


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


def socis_csv():
    """Nombre de socis: una pestanya del Google Sheets del club publicada com a CSV amb una sola cel·la (veure data/fonts.json)."""
    cfg = carrega("data/fonts.json", {})
    url = (cfg.get("socis_csv") or "").strip()
    if not url:
        return None
    t = req(url)
    m = re.search(r"\d+", t.split("\n")[0].replace(".", ""))
    return int(m.group(0)) if m else None


def desambigua(club):
    """Si dos jugadors del club tenen el mateix «Nom Cognom», s'afegeix la inicial del segon cognom (Daniel Uroz L. / Daniel Uroz M.)."""
    from collections import Counter
    c = Counter(j["nom"] for j in club)
    for j in club:
        if c[j["nom"]] > 1:
            cog = (j["nom_cr"].split(",")[0]).split()
            j["nom"] = f'{j["nom"]} {cog[1][0].upper()}.' if len(cog) > 1 else f'{j["nom"]} ({j["id"][-3:]})'
    c = Counter(j["nom"] for j in club)
    for nom, n in list(c.items()):                    # encara repetits (mateixa inicial): es van allargant les lletres del segon cognom (Pal. / Par.)
        if n < 2:
            continue
        grup = [j for j in club if j["nom"] == nom]
        cogs = [(j["nom_cr"].split(",")[0]).split() for j in grup]
        if all(len(x) > 1 for x in cogs):
            for L in range(2, 12):
                pref = [x[1][:L].title() for x in cogs]
                if len(set(pref)) == len(grup):
                    for j, p in zip(grup, pref):
                        j["nom"] = nom.rsplit(" ", 1)[0] + f" {p}."
                    break
    c = Counter(j["nom"] for j in club)
    for j in club:
        if c[j["nom"]] > 1:
            j["nom"] = f'{j["nom"]} ({j["id"][-3:]})'
    return club


# ---------------------------------------------------------------- principal
def desa_elo_fide(c_fide, c_fce=None):
    """Afegeix a data/jugadors.json l'Elo FIDE actual i, per a la FCE i la FIDE, l'Elo de fa 12 mesos i l'increment des d'aquest registre. Tot llegit dels historials
    oficials, no calculat a partir dels torneigs."""
    d = carrega(D_JUG, None)
    if not d:
        return
    any_ = datetime.date.today().year

    def val(x, clau_):
        if isinstance(x, dict):
            return x.get(clau_)
        if isinstance(x, (list, tuple)) and x:
            return x[0] if clau_ == "standard" else (x[1] if len(x) > 1 else None)
        return None

    # Variació dels darrers 12 mesos: es compara amb l'Elo del mateix mes de l'any anterior (últim registre fins aquell mes, perquè l'Elo es manté
    # entre llistes); si el jugador encara no tenia registre, s'usa el seu primer registre dins l'any.
    ult = max([max(h) for h in [((c_fide.get(str(j.get("fide"))) or {}).get("h") or {}) for j in d.get("jugadors", [])]
               + [((c_fce or {}).get(str(j.get("id"))) or {}).get("h") or {} for j in d.get("jugadors", [])] if h] or ["%d%02d" % (any_, datetime.date.today().month)])
    objectiu = "%d%s" % (int(ult[:4]) - 1, ult[4:6])

    def ref(h, clau_):
        """(mes de referència, Elo de referència, Elo actual, mes actual)"""
        mesos = [(ym, val(h[ym], clau_)) for ym in sorted(h) if val(h[ym], clau_)]
        if not mesos:
            return None
        act = mesos[-1]
        abans = [x for x in mesos if x[0] <= objectiu]
        r = abans[-1] if abans else next((x for x in mesos if x[0] > objectiu), None)
        return (r[0], r[1], act[1], act[0]) if r else None

    for j in d.get("jugadors", []):
        hf = (c_fide.get(str(j.get("fide"))) or {}).get("h") or {}
        hc = ((c_fce or {}).get(str(j.get("id"))) or {}).get("h") or {}
        for camp, clau_ in (("elo_fide", "standard"), ("elo_fide_rapid", "rapid")):
            v = [x for x in (val(hf[ym], clau_) for ym in sorted(hf)) if x]
            j[camp] = v[-1] if v else None
        for sufix, h in (("fce", hc), ("fide", hf)):
            r = ref(h, "standard")
            j["ref_" + sufix] = r[1] if r else None
            j["ref_" + sufix + "_mes"] = r[0] if r else None
            j["inc_" + sufix] = (r[2] - r[1]) if r and r[0] != r[3] else None      # si el registre de referència és l'actual, no hi ha diferència que mostrar
    d["inc_des"] = "%s-%s-01" % (objectiu[:4], objectiu[4:])      # mes de referència de la variació (fa 12 mesos)
    json.dump(d, open(D_JUG, "w", encoding="utf-8"), ensure_ascii=False, indent=1)


SEGUIMENT = "--seguiment" in sys.argv


def main(des="2026-09-01"):
    T_INICI = time.time()
    LIMIT = 40 * 60     # temps maxim de feina: el que falti es completa a la propera execucio (el workflow talla als 60 min)
    ara = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%MZ")
    antic = carrega(D_JUG, {"jugadors": []})
    per_id = {j["id"]: j for j in antic.get("jugadors", [])}

    # 1. llista del club
    try:
        club = llista_club()
        club = [x for x in club if x.get('id') in ('382950', '400411')] if os.environ.get('NOMES_PROVA') else club     # REPO DE PROVES: només les dues jugadores autoritzades
        print(f"FCE: {len(club)} jugadors del club")
    except Exception as e:
        print("FCE: no s'ha pogut llegir la llista (es conserva l'anterior):", e)
        club = antic.get("jugadors", [])
    club = desambigua(club)
    if os.environ.get("LOGS_ANONIMS"):        # repositori de proves públic: cap nom de jugador (ni de menors) als logs; el detall va xifrat
        import builtins, re as _re
        _noms = sorted({n for j in club for n in (j.get("nom"), j.get("nom_cr")) if n and len(n) > 3}, key=len, reverse=True)
        _pat = _re.compile("|".join(_re.escape(n) for n in _noms), _re.I) if _noms else None
        _ids = {}
        def _masca(m):
            return _ids.setdefault(m.group(0).lower(), f"jugador-{len(_ids) + 1}")
        _print0 = builtins.print
        builtins.print = lambda *a, **k: _print0(*[(_pat.sub(_masca, x) if _pat and isinstance(x, str) else x) for x in a], **k)
    # 2. codi FIDE (de la FCE; si no, per nom a Chess-Results)
    errors_fide = 0
    for j in club:
        j["fide"] = per_id.get(j["id"], {}).get("fide", "")
        if not j["fide"]:
            try:
                time.sleep(2)
                j["fide"] = codi_fide(j["id"])
            except Exception as e:
                errors_fide += 1
                if errors_fide <= 3:
                    print("  FCE: sense codi FIDE per", j["nom"], "->", e)
    manual = carrega("data/fide-manual.json", {})        # codis FIDE que la FCE no dona: {"id FCE": "codi FIDE"}
    for j in club:
        if not j["fide"] and manual.get(str(j["id"])):
            j["fide"] = str(manual[str(j["id"])])
    sense = [j for j in club if not j["fide"]]
    print(f"Codi FIDE via FCE: {len(club) - len(sense)} de {len(club)}")
    for j in sense:
        try:
            time.sleep(1.5)
            j["fide"] = cr_per_nom(j)
        except Exception as e:
            print("  Chess-Results: no s'ha trobat per nom", j["nom"], e)
    print(f"Codi FIDE (total): {sum(1 for j in club if j['fide'])} de {len(club)}")
    socis = None
    try:
        socis = None if os.environ.get('NOMES_PROVA') else socis_csv()
    except Exception as e:
        print("Socis (Google Sheets): error", e)
    json.dump({"actualitzat": ara, "federats": len(club), "socis": socis if socis is not None else antic.get("socis"), "jugadors": club},
              open(D_JUG, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    # 3. torneigs recents de cada jugador (Chess-Results)
    antiga = carrega(D_RES, {"resultats": []})
    resultats, errors = [], 0
    if SEGUIMENT:
        # seguiment: no es busquen torneigs nous (això ho fa el mode «descobriment»); només es tornen a llegir els ja trobats dels últims dies
        resultats = [r for r in antiga.get("resultats", []) if r.get("font") not in ("info64", "ffe") and r["fi"] >= des]
        print(f"Seguiment: {len(resultats)} resultats ja coneguts des de {des}")
    for j in ([] if SEGUIMENT else club):
        if not j["fide"]:
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
        except Exception as e:
            errors += 1
            print("  Chess-Results: error amb", j["nom"], e)
            resultats += [r for r in antiga.get("resultats", []) if r.get("fide") == j["fide"] and r.get("font") not in ("info64", "ffe")]   # conserva el que hi havia
    D_HF, D_HI = "data/brut/hist_fce.json", "data/brut/hist_fide.json"
    mes_ara = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m")
    c_fce, c_fide = carrega(D_HF, {}), carrega(D_HI, {})       # {id: {"mes": mes de la consulta, "h": {YYYYMM: [...]}}}
    estat = {"fallades": 0}
    def amb_cache(cache, clau, fn):
        e = cache.get(str(clau))
        if e and (e["mes"] == mes_ara or time.time() - T_INICI > LIMIT):
            return e["h"]                                     # el passat no canvia: nomes es torna a demanar un cop al mes
        if time.time() - T_INICI > LIMIT:
            return None
        fide_ = fn is hist_fide
        if fide_ and estat["fallades"] >= 4:                  # la FIDE ens limita: es deixa per a la propera execucio
            return e["h"] if e else None
        time.sleep(3.0 if fide_ else 1.2)
        try:
            h = fn(clau)
        except Exception:
            if fide_:
                estat["fallades"] += 1
            raise
        if fide_:
            estat["fallades"] = 0
        if h or fide_:                                        # FIDE: una llista sense Elo vol dir jugador sense Elo, i es desa igualment
            cache[str(clau)] = {"mes": mes_ara, "h": h}
        return h
    # historials d'Elo FCE i FIDE dels jugadors amb resultats: es demanen aviat (son pocs i barats) i es desen a la memoria cau
    LIMIT = 55 * 60
    for j in club:
        for cache, clau, fn in ((c_fce, j["id"], hist_fce), (c_fide, j.get("fide"), hist_fide)):
            if not clau:
                continue
            try:
                amb_cache(cache, clau, fn)
            except Exception as e:
                print("  historial no disponible per a", j["nom"], e)
    json.dump(c_fce, open(D_HF, "w", encoding="utf-8"), ensure_ascii=False)
    json.dump(c_fide, open(D_HI, "w", encoding="utf-8"), ensure_ascii=False)
    LIMIT = 40 * 60
    # noms complets dels torneigs (la llista de jugador els talla a 30 caràcters); es guarden per no tornar-los a demanar
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
    llocs = {k: v for k, v in carrega(D_LLOC, {}).items() if v and (v.get("lloc") or v.get("fed"))}      # no es conserven les lectures buides
    for r in resultats:
        if r["tnr"] not in dates or not llocs.get(r["tnr"]):
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
                    llocs[r["tnr"]] = {"lloc": ml.group(1).strip() if ml else "", "fed": cf.group(1) if cf else ""}
                else:
                    print("  sense lloc a la pàgina del torneig", r["tnr"])
            except Exception as e:
                print("  no s'ha pogut llegir la data del torneig", r["tnr"], e)
    json.dump(dates, open(D_DATES, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    json.dump(llocs, open(D_LLOC, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    avui_iso = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")
    for r in resultats:
        r["inici"] = dates.get(r["tnr"])
        ll = llocs.get(r["tnr"]) or {}
        if ll.get("lloc"):
            r["lloc"] = ll["lloc"]
        r["fora_cat"] = fora_de_catalunya(ll.get("lloc"), ll.get("fed")) or bool(FORA_FCE.search(r["torneig"]))
    resultats = [r for r in resultats if not r["inici"] or r["inici"] <= avui_iso]     # només els que ja han començat
    resultats.sort(key=lambda r: (r["fi"], r["jugador"]), reverse=True)
    json.dump({"actualitzat": ara, "des": des, "resultats": resultats}, open(D_RES, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"Chess-Results: {len(resultats)} resultats des de {des}, {errors} errors")

    print(f"[{int(time.time() - T_INICI) // 60} min] resultats de Chess-Results llegits", flush=True)
    # 4. resum global de cada torneig: quants dels nostres hi juguen i com els va (classificació)
    nostres = {norm(j["nom_cr"]): j["nom"] for j in club}
    tornejos, mostres, equips_mostres, jocs_equip, eq_de = {}, 0, 0, {}, {}
    for r in resultats:
        t = tornejos.setdefault(r["tnr"], {"tnr": r["tnr"], "torneig": r["torneig"], "fi": r["fi"], "rondes": r["rondes"], "de": r["de"],
                                          "inici": r.get("inici"), "url": f"https://s1.chess-results.com/tnr{r['tnr']}.aspx?lan=1", "classificacio": None})
    for tnr, t in list(tornejos.items())[:80]:
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
            if mostres < 3:     # mostres per poder afinar el lector (una per torneig, només les primeres)
                os.makedirs("data/brut/mostres_cr", exist_ok=True)
                open(f"data/brut/mostres_cr/classificacio_{tnr}.html", "w", encoding="utf-8").write(pag[:120000])
                mostres += 1
        except Exception as e:
            print("  classificació no disponible per al torneig", tnr, e)
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
    print(f"[{int(time.time() - T_INICI) // 60} min] classificacions i equips llegits", flush=True)
    # fitxa de cada jugador en cada torneig: partides jugades, performance i variació FIDE de Chess-Results
    fets = {}
    D_FX = "data/brut/fitxes.json"
    c_fitxes = carrega(D_FX, {})
    avui_iso = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")
    print(f"[{int(time.time() - T_INICI) // 60} min] fitxes de jugador: {len(c_fitxes)} en memoria cau", flush=True)
    for r in resultats:
        k = (r["jugador"], r["tnr"])
        try:
            ck = r["url"]
            if ck in c_fitxes and r["fi"] < avui_iso:        # torneig acabat: la fitxa ja no canvia
                f = c_fitxes[ck]
            else:
                time.sleep(1.2)
                f = analitza_fitxa(req(r["url"]))
                if r["fi"] < avui_iso and f.get("partides"):
                    c_fitxes[ck] = f
        except Exception as e:
            print("  fitxa no disponible", r["url"], e)
            f = {"partides": []}
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
        for c in ("perf", "fide_var", "rtg_n", "rtg_i", "punts", "modalitat"):
            if f.get(c) is not None:
                r[c] = f[c]
    json.dump(c_fitxes, open(D_FX, "w", encoding="utf-8"), ensure_ascii=False)
    print(f"[{int(time.time() - T_INICI) // 60} min] fitxes llegides", flush=True)
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
            if (k not in riv or len(riv[k]) < 3) and time.time() - t0 < 20 * 60:     # el que falti es completa a la propera execucio
                try:
                    time.sleep(1.0)
                    f = analitza_fitxa(req(f"https://s1.chess-results.com/tnr{g['tnr']}.aspx?lan=1&art=9&snr={sn}"))
                    riv[k] = [f.get("rtg_n"), f.get("rtg_i"), f.get("fide_id") or ""]
                    if len(riv) % 40 == 0:
                        json.dump(riv, open(D_RIV, "w", encoding="utf-8"), ensure_ascii=False)
                except Exception as e:
                    print("  fitxa del rival no disponible", k, e)
            if k in riv:
                g["rn"], g["ri"] = riv[k][0], riv[k][1]
                g["fid"] = riv[k][2] if len(riv[k]) > 2 else None
                g["rtg_n"], g["rtg_i"] = riv[k][0] or g.get("rtg_n"), riv[k][1] or g.get("rtg_i")
    json.dump(riv, open(D_RIV, "w", encoding="utf-8"), ensure_ascii=False)
    print(f"Fitxes de rivals: {len(riv)} desades")

    # Elo FIDE mensual dels rivals (per codi FIDE a ratings.fide.com); es desa a la memoria cau i es completa en diverses execucions
    LIMIT = 75 * 60
    for r in resultats:
        for g in r.get("partides", []):
            if g.get("fid"):
                try:
                    amb_cache(c_fide, g["fid"], hist_fide)
                except Exception as e:
                    pass
    json.dump(c_fide, open(D_HI, "w", encoding="utf-8"), ensure_ascii=False)
    print(f"[{int(time.time() - T_INICI) // 60} min] historials FIDE desats: {len(c_fide)}", flush=True)
    LIMIT = 40 * 60
    # variacio de l'Elo FCE i FIDE de cada torneig, calculada amb l'Elo mensual de cada jugador
    per_nom = {j["nom"]: j for j in club}
    hist, hist_f, n_elo, n_fide = {}, {}, 0, 0
    MOD_CMS = {str(o["tnr"]): o.get("modalitat") for o in carrega("data/elo-compilat.json", {}).get("tornejos", [])}
    for r in resultats:
        r.pop("modalitat_dubtosa", None)
        if not r.get("modalitat"):          # si la pagina no ho diu, pel nom del torneig
            n_ = norm(r["torneig"])
            kw = re.search(r"llampec|blitz|actius|rapid|rapides", n_)
            r["modalitat"] = "Blitz" if re.search(r"llampec|blitz", n_) else "Rapid" if re.search(r"actius|rapid|rapides", n_) else "Standard"
            r["modalitat_dubtosa"] = not kw             # deduïda pel nom i sense cap paraula clau: ho ha de revisar el club
        r["modalitat_dubtosa"] = bool(r.get("modalitat_dubtosa"))
        if MOD_CMS.get(str(r["tnr"])) in ("Standard", "Rapid", "Blitz"):      # el que el club ha marcat al backoffice (Validesa per a l'Elo)
            r["modalitat"], r["modalitat_dubtosa"] = MOD_CMS[str(r["tnr"])], False
        j = per_nom.get(r["jugador"])
        if not j or not r.get("partides"):
            continue
        try:
            if j["id"] not in hist:
                hist[j["id"]] = amb_cache(c_fce, j["id"], hist_fce)
            v = variacio_fce(r, hist[j["id"]], j.get("categoria")) if hist[j["id"]] and not r.get("fora_cat") else None
            if v:
                r["elo_fce"] = v
                n_elo += 1
            elif r.get("fora_cat"):
                r.pop("elo_fce", None)
        except Exception as e:
            print("  Elo FCE no disponible per a", r["jugador"], e)
        try:
            if j.get("fide") and j["fide"] not in hist_f:
                try:
                    hist_f[j["fide"]] = amb_cache(c_fide, j["fide"], hist_fide) or {}
                except Exception as e:
                    hist_f[j["fide"]] = {}
                    print("  historial FIDE no disponible per a", r["jugador"], e)
            v = None if re.search(r"sub[\s-]?8\b|mini[\s-]?circuit", r["torneig"].lower()) else variacio_fide(r, hist_f.get(j.get("fide"), {}), j.get("categoria"), c_fide)   # els sub-8 i el Minicircuit no valen per a l'EloIDE
            if v:
                r["elo_fide"] = v
                n_fide += 1
        except Exception as e:
            print("  Elo FIDE no calculable per a", r["jugador"], e)
    # variacio d'Elo FIDE de les partides de la Lliga (data/lliga-<any>.json): codi FCE -> codi FIDE -> historial mensual
    try:
        D_CF = "data/brut/codis_fide.json"
        codis = carrega(D_CF, {})
        per_id = {str(j["id"]): j for j in club}
        n_ll = 0
        LIMIT = 70 * 60

        def fide_de(idf):
            if idf in per_id and per_id[idf].get("fide"):
                return str(per_id[idf]["fide"])
            if idf not in codis:
                if time.time() - T_INICI > LIMIT:
                    return ""
                time.sleep(1.0)
                try:
                    codis[idf] = codi_fide(idf)
                except Exception:
                    return ""
            return codis[idf]

        def hist_de(f):
            if not f:
                return None
            e = c_fide.get(f)
            if e and (e["mes"] == mes_ara or time.time() - T_INICI > LIMIT):
                return e["h"]
            try:
                return amb_cache(c_fide, f, hist_fide)
            except Exception:
                return e["h"] if e else None

        for fl in sorted(glob.glob("data/lliga-*.json")):
            ll = json.load(open(fl, encoding="utf-8"))
            for g in ll.get("grups", []):
                for rd in g.get("rondes", []):
                    ym = (rd.get("data") or "")[:7].replace("-", "")
                    for t in rd.get("taulers") or []:
                        if t.get("fide") is not None or not (t.get("idn") and t.get("idr") and ym) or t.get("res") not in ("1", "0", "½"):
                            continue
                        fn, fr = fide_de(t["idn"]), fide_de(t["idr"])
                        hn, hr = hist_de(fn), hist_de(fr)
                        R = fide_a(hn, ym, "standard") if hn else None
                        ri = fide_a(hr, ym, "standard") if hr else None
                        if not R or not ri:
                            if hn is not None and hr is not None:
                                t["fide"] = {}               # sense Elo FIDE: no es torna a provar
                            continue
                        k = k_fide(R, per_id.get(t["idn"], {}).get("categoria"))
                        sc = {"1": 1, "½": 0.5, "0": 0}[t["res"]]
                        t["fide"] = {"d": round(k * (sc - esperat_fide(ri - R)), 1), "k": k, "r": R, "opp": ri}
                        n_ll += 1
            open(fl, "w", encoding="utf-8").write(json.dumps(ll, ensure_ascii=False, indent=1) + "\n")
        json.dump(codis, open(D_CF, "w", encoding="utf-8"), ensure_ascii=False)
        print(f"Lliga: variacio FIDE de {n_ll} partides")
    except Exception as e:
        print("  Lliga: Elo FIDE no calculable", e)
    json.dump(c_fce, open(D_HF, "w", encoding="utf-8"), ensure_ascii=False)
    json.dump(c_fide, open(D_HI, "w", encoding="utf-8"), ensure_ascii=False)
    # el que és anterior a `des` no es torna a calcular: es conserva de l'execució anterior (així es pot anar enrere mes a mes sense perdre res)
    try:
        ant_t = {t["tnr"]: t for t in carrega("data/torneigs-jugadors.json", {"tornejos": []}).get("tornejos", [])}
        ja = {(r["jugador"], r["tnr"]) for r in resultats}
        n_ant, n_lloc = 0, 0
        for r in antiga.get("resultats", []):
            if r.get("font") in ("info64", "ffe") or r["fi"] >= des or (r["jugador"], r["tnr"]) in ja:
                continue
            if r["tnr"] not in llocs and n_lloc < 60:                      # els antics no tenien el lloc llegit
                n_lloc += 1
                try:
                    time.sleep(1.2)
                    ll = llegeix_lloc(r["tnr"])
                    if ll:
                        llocs[r["tnr"]] = ll
                except Exception as e:
                    print("  no s'ha pogut llegir el lloc", r["tnr"], e)
            ll = llocs.get(r["tnr"]) or {}
            r["fora_cat"] = fora_de_catalunya(ll.get("lloc"), ll.get("fed")) or bool(FORA_FCE.search(r["torneig"]))
            if r["fora_cat"]:
                r.pop("elo_fce", None)
            resultats.append(r)
            n_ant += 1
            for tn in {r["tnr"], r.get("tnr_alt")}:
                if tn and tn in ant_t and tn not in tornejos:
                    tornejos[tn] = ant_t[tn]
        json.dump(llocs, open(D_LLOC, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        des = min(des, antiga.get("des") or des)
        print(f"Conservats {n_ant} resultats anteriors a {ara[:10] and des}")
    except Exception as e:
        print("  No s'han pogut conservar els resultats anteriors", e)
    # resultats d'Info64 (FEDA: Campionats d'Espanya, oberts...), llegits per tools/info64.py; ja porten la variació FIDE de cada partida
    try:
        i64 = carrega("data/info64-jugadors.json", {"resultats": []}).get("resultats", []) + carrega("data/ffe-jugadors.json", {"resultats": []}).get("resultats", [])   # + FFE (França)
        mots = lambda n: set(w for w in re.sub(r"[^a-z0-9]+", " ", norm(n)).split() if len(w) > 2)
        n_i64 = 0
        resultats = [r for r in resultats if r.get("font") not in ("info64", "ffe")]
        for r in i64:
            dup = any(x["jugador"] == r["jugador"] and x["fi"] == r["fi"] and len(mots(x["torneig"]) & mots(r["torneig"])) >= max(1, min(len(mots(x["torneig"])), len(mots(r["torneig"]))) // 2)
                      for x in resultats if x.get("font") not in ("info64", "ffe"))
            if dup:
                continue
            resultats.append(r)
            n_i64 += 1
            t = tornejos.setdefault(r["tnr"], {"tnr": r["tnr"], "torneig": r["torneig"], "fi": r["fi"], "rondes": r["rondes"], "de": r["de"], "inici": r.get("inici"),
                                              "url": r["url"], "classificacio": {"ronda": r["rondes"], "participants": r["de"], "jugadors": []}})
            t["classificacio"]["jugadors"].append({"nom": r["jugador"], "lloc": r["lloc"], "punts": r["punts"]})
        # no són torneigs: les concentracions de tecnificació (entrenaments) i els que els nostres no van arribar a jugar (0 punts i cap partida)
        def jugada(g):
            return not g.get("inc") and g.get("res") in ("1", "0", "½", "+", "-") and g.get("rival")
        fora = set()
        for r in resultats:
            sense = r.get("punts") is not None and str(r.get("punts") or "0").replace(",", ".").strip() in ("0", "0.0", "") and not any(jugada(g) for g in r.get("partides", []))
            if re.search(r"tecnificaci", r["torneig"], re.I) or sense:
                fora.add((r["jugador"], r["tnr"]))
        resultats = [r for r in resultats if (r["jugador"], r["tnr"]) not in fora]
        for tnr in list(tornejos):
            t = tornejos[tnr]
            cl = t.get("classificacio") or {}
            if cl.get("jugadors"):
                cl["jugadors"] = [x for x in cl["jugadors"] if (x["nom"], tnr) not in fora]
                if not cl["jugadors"] and not t.get("equips") and not cl.get("equips") and not cl.get("llista"):
                    del tornejos[tnr]
            elif re.search(r"tecnificaci", t["torneig"], re.I):
                del tornejos[tnr]
        print(f"Info64: {n_i64} resultats afegits; {len(fora)} descartats (tecnificació o sense partides jugades)")
        resultats.sort(key=lambda r: (r["fi"], r["jugador"]), reverse=True)
    except Exception as e:
        print("  Info64: no s'ha pogut afegir", e)
    # cada resultat individual ha de sortir a la classificació del seu torneig (si es reaprofita el torneig d'una execució anterior, hi pot faltar algú)
    for r in resultats:
        t = tornejos.get(r["tnr"]); cl = (t or {}).get("classificacio") or {}
        if t and isinstance(cl.get("jugadors"), list) and not t.get("equips") and r.get("lloc") is not None and not any(x["nom"] == r["jugador"] for x in cl["jugadors"]):
            cl["jugadors"].append({"nom": r["jugador"], "lloc": r["lloc"], "punts": r["punts"]})
    print(f"Elo estimat: FCE {n_elo} resultats, FIDE {n_fide} resultats; historial FCE de {len(hist)} jugadors, FIDE de {sum(1 for v in hist_f.values() if v)} jugadors")
    json.dump({"actualitzat": ara, "des": des, "resultats": resultats}, open(D_RES, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    json.dump({"actualitzat": ara, "tornejos": sorted(tornejos.values(), key=lambda x: x["fi"], reverse=True)},
              open("data/torneigs-jugadors.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    desa_elo_fide(c_fide, c_fce)
    print(f"Resum de torneigs: {len(tornejos)}")


if __name__ == "__main__":
    a = sys.argv[1:]
    if "--prova-cr" in a:
        t = open(a[a.index("--prova-cr") + 1], encoding="utf-8").read()
        r = analitza_cr(t, a[a.index("--prova-cr") + 2])
        print(len(r), "torneigs"); print(json.dumps(r[:3], ensure_ascii=False, indent=1))
    else:
        main(a[a.index("--des") + 1] if "--des" in a else "2026-09-01")
