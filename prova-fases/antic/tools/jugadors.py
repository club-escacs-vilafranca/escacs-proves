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
from xarxa import UA, cj, op, req
from cr_font import (CR, fnum, num, analitza_cr, cr_cerca, analitza_cr_nom, cr_torneigs_nom, cr_torneigs, cr_per_nom, analitza_classificacio, analitza_fitxa, nom_joc, claus_aprox, troba_nostre, analitza_equips, info_ronda, FORA_FCE, fora_de_catalunya, ETIQ, llegeix_lloc, analitza_llista, baixa)
from elo_mensual import hist_fce, hist_fide, amb_cache as _amb_cache, mes_partida, mes_consulta_fide
from duplicats import deduplica, deduplica_previs, semblants
from elo_calc import (calcula_lliga, norm, aplica_elo, DIF_FIDE_FCE, fce_a_partir_de, elo_a, k_fce, k_fide, esperat, esperat_fide, ratings_rival, modalitat_elo, fide_a, variacio_fce, variacio_fide)

FCE = "https://escacs.cat/components/com_fce/gmvw20/conn/"
ID_CLUB = "290"
CR = "https://s1.chess-results.com/SpielerSuche.aspx?lan=2&SNode=S0"   # sempre el mateix node: el viewstate no val entre nodes
D_JUG, D_RES = "data/jugadors.json", "data/resultats-jugadors.json"
D_LLOC = "data/brut/lloc_torneigs.json"


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
    open("data/brut/fce_club.json", "w", encoding="utf-8").write(t[:2_000_000])   # per poder ajustar-ho si el format canvia
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


def resultats_manuals():
    """Torneigs entrats a mà des del CMS (data/manual-jugadors.json): una fila per jugador, com les d'Info64; l'Elo es calcula després igual que per a la resta."""
    out = []
    for t in carrega("data/manual-jugadors.json", {}).get("torneigs", []):
        if not (t.get("nom") and t.get("fi")):
            continue
        tnr = "manual-" + re.sub(r"[^a-z0-9]+", "-", norm(t["nom"])).strip("-") + "-" + t["fi"][:7]
        for j in t.get("jugadors", []):
            if not j.get("jugador"):
                continue
            ps = []
            for g in sorted(j.get("partides") or [], key=lambda g: g.get("ronda") or 0):
                if g.get("res") not in ("1", "0", "½", "+", "-") or not g.get("rival"):
                    continue
                ps.append({"ronda": g.get("ronda"), "rival": g["rival"], "rtg_i": g.get("rtg_i") or None, "color": g.get("color") or "", "res": g["res"], "club": g.get("club") or "",
                           "fid": str(g.get("fid") or "").strip(), "data": g.get("data") or t.get("inici") or t["fi"], "bo": None})
            out.append({"jugador": j["jugador"], "fide": "", "font": "manual", "v": 1, "tnr": tnr, "snr": None, "torneig": t["nom"], "fi": t["fi"], "inici": t.get("inici") or t["fi"],
                        "club": "", "fed": "ESP", "lloc": j.get("lloc"), "rondes": t.get("rondes") or len(ps) or None, "de": t.get("participants"), "url": t.get("url") or "",
                        "punts": str(j.get("punts") or ""), "modalitat": t.get("modalitat") or "Standard", "rtg_i": None, "partides": ps})
    return out


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
        for camp, clau_ in (("elo_fide", "standard"), ("elo_fide_rapid", "rapid"), ("elo_fide_blitz", "blitz")):
            v = [x for x in (val(hf[ym], clau_) for ym in sorted(hf)) if x]
            j[camp] = v[-1] if v else None
        for sufix, h in (("fce", hc), ("fide", hf)):
            r = ref(h, "standard")
            j["ref_" + sufix] = r[1] if r else None
            j["ref_" + sufix + "_mes"] = r[0] if r else None
            j["inc_" + sufix] = (r[2] - r[1]) if r and r[0] != r[3] else None      # si el registre de referència és l'actual, no hi ha diferència que mostrar
    d["inc_des"] = "%s-%s-01" % (objectiu[:4], objectiu[4:])      # mes de referència de la variació (fa 12 mesos)
    json.dump(d, open(D_JUG, "w", encoding="utf-8"), ensure_ascii=False, indent=1)



def previs_info64():
    """Afegeix a data/previs-jugadors.json els torneigs que encara no han començat d'Info64 (llegits per tools/info64.py) amb jugadors del club inscrits.
    Les entrades d'Info64 es refan a cada execució (marca «font»: «info64»); si el torneig ja surt de Chess-Results, només s'hi afegeixen els jugadors que hi falten."""
    dades = carrega("data/previs-jugadors.json", {"previs": []})
    previs = [x for x in dades.get("previs", []) if x.get("font") != "info64"]
    avui = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")
    for t in carrega("data/info64-jugadors.json", {}).get("propers", []):
        if t.get("inici", "0") <= avui or not t.get("jugadors"):
            continue
        dup = next((x for x in previs if x["inici"] == t["inici"] and semblants(x["torneig"], t["torneig"])), None)
        if dup:
            dup["jugadors"] += [n for n in t["jugadors"] if n not in dup["jugadors"]]
            continue
        previs.append({"tnr": t["tnr"], "torneig": t["torneig"], "inici": t["inici"], "fi": t["fi"], "lloc": "", "fed": "", "url": t["url"], "jugadors": t["jugadors"], "font": "info64"})
    previs = deduplica_previs(previs)
    previs.sort(key=lambda x: (x["inici"], x["torneig"]))
    nou = {"actualitzat": dades.get("actualitzat") or datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%MZ"), "previs": previs}
    if nou != dades:
        json.dump(nou, open("data/previs-jugadors.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    return len([x for x in previs if x.get("font") == "info64"])

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
        print(f"FCE: {len(club)} jugadors del club")
    except Exception as e:
        print("FCE: no s'ha pogut llegir la llista (es conserva l'anterior):", e)
        club = antic.get("jugadors", [])
    club = desambigua(club)
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
        socis = socis_csv()
    except Exception as e:
        print("Socis (Google Sheets): error", e)
    json.dump({"actualitzat": ara, "federats": len(club), "socis": socis if socis is not None else antic.get("socis"), "jugadors": club},
              open(D_JUG, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    # 3. torneigs recents de cada jugador (Chess-Results)
    antiga = carrega(D_RES, {"resultats": []})
    cr = baixa(club, des, SEGUIMENT, ara, T_INICI, antiga)         # tools/cr_font.py: tot el que es llegeix de Chess-Results
    resultats, tornejos, llocs, errors = cr["resultats"], cr["tornejos"], cr["llocs"], cr["errors"]
    D_HF, D_HI = "data/brut/hist_fce.json", "data/brut/hist_fide.json"
    mes_ara = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m")
    c_fce, c_fide = carrega(D_HF, {}), carrega(D_HI, {})       # {id: {"mes": mes de la consulta, "h": {YYYYMM: [...]}}}
    estat = {"fallades": 0}
    def amb_cache(cache, clau, fn, ym=None):
        """Memòria cau d'Elo (tools/elo_mensual.py): el club es relegeix un cop al mes; un rival només quan hi ha una partida d'un mes que encara no té."""
        return _amb_cache(cache, clau, fn, ym or mes_ara, estat, lambda: time.time() - T_INICI > LIMIT, mes_consulta=mes_consulta_fide())
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

    # Elo FIDE mensual dels rivals (per codi FIDE a ratings.fide.com); es desa a la memoria cau i es completa en diverses execucions
    LIMIT = 75 * 60
    for r in resultats:
        for g in r.get("partides", []):
            if g.get("fid"):
                try:
                    amb_cache(c_fide, g["fid"], hist_fide, mes_partida(r, g))
                except Exception as e:
                    pass
    json.dump(c_fide, open(D_HI, "w", encoding="utf-8"), ensure_ascii=False)
    print(f"[{int(time.time() - T_INICI) // 60} min] historials FIDE desats: {len(c_fide)}", flush=True)
    LIMIT = 40 * 60
    # variacio de l'Elo FCE i FIDE de cada torneig, calculada amb l'Elo mensual de cada jugador
    per_nom = {j["nom"]: j for j in club}
    hist, hist_f, n_elo, n_fide = {}, {}, 0, 0
    MOD_CMS = {str(o["tnr"]): o.get("modalitat") for o in carrega("data/elo-compilat.json", {}).get("tornejos", [])}
    ELO_N = {"fce": 0, "fide": 0}
    def h_fce_de(j):
        if j["id"] not in hist:
            hist[j["id"]] = amb_cache(c_fce, j["id"], hist_fce)
        return hist[j["id"]]

    def h_fide_de(j):
        if j.get("fide") and j["fide"] not in hist_f:
            try:
                hist_f[j["fide"]] = amb_cache(c_fide, j["fide"], hist_fide) or {}
            except Exception as e:
                hist_f[j["fide"]] = {}
                print("  historial FIDE no disponible per a", j["nom"], e)
        return hist_f.get(j.get("fide"), {})

    def calcula_elo(r, fce=True):
        a, b = aplica_elo(r, per_nom, MOD_CMS, h_fce_de, h_fide_de, c_fide, fce=fce)       # el càlcul és a tools/elo_calc.py
        ELO_N["fce"] += a
        ELO_N["fide"] += b
    import elo_fce
    _ctx = elo_fce.contexte(".")
    _ctx.posa_club(club, c_fce)
    _ctx.prepara(resultats, carrega("data/lliga-2026.json", {}), {str(o["tnr"]): o for o in carrega("data/elo-compilat.json", {}).get("tornejos", [])})
    for r in resultats:
        calcula_elo(r)
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
            n_ll += calcula_lliga(ll, fide_de, hist_de, lambda i: per_id.get(i, {}).get("categoria"))        # el càlcul és a tools/elo_calc.py
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
            if r.get("font") in ("info64", "ffe", "vesus", "manual") or r["fi"] >= des or (r["jugador"], r["tnr"]) in ja:
                continue
            if (r["tnr"] not in llocs or not llocs[r["tnr"]].get("inici") or not llocs[r["tnr"]].get("ritme_ll")) and n_lloc < 60:       # els antics no tenien el lloc ni la data d'inici llegits (es completen a poc a poc, 60 per execució)
                n_lloc += 1
                try:
                    time.sleep(1.2)
                    ll = llegeix_lloc(r["tnr"])
                    if ll:
                        llocs[r["tnr"]] = ll
                    elif r["tnr"] in llocs:
                        llocs[r["tnr"]]["inici"] = llocs[r["tnr"]].get("inici") or ""
                except Exception as e:
                    print("  no s'ha pogut llegir el lloc", r["tnr"], e)
            ll = llocs.get(r["tnr"]) or {}
            if ll.get("inici"):
                r["inici"] = ll["inici"]
            if ll.get("modalitat"):
                r["modalitat"], r["ritme"] = ll["modalitat"], ll.get("ritme", "")
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
        i64 = carrega("data/info64-jugadors.json", {"resultats": []}).get("resultats", []) + carrega("data/ffe-jugadors.json", {"resultats": []}).get("resultats", []) + carrega("data/vesus-jugadors.json", {"resultats": []}).get("resultats", []) + resultats_manuals()   # + FFE (França) + Vesus + torneigs entrats a mà (CMS)
        mots = lambda n: set(w for w in re.sub(r"[^a-z0-9]+", " ", norm(n)).split() if len(w) > 2)
        n_i64 = 0
        resultats = [r for r in resultats if r.get("font") not in ("info64", "ffe", "vesus", "manual")]
        for r in i64:
            dup = any(x["jugador"] == r["jugador"] and x["fi"] == r["fi"] and (x.get("modalitat") or "Standard") == (r.get("modalitat") or "Standard") and len(mots(x["torneig"]) & mots(r["torneig"])) >= max(1, min(len(mots(x["torneig"])), len(mots(r["torneig"]))) // 2)
                      for x in resultats if x.get("font") not in ("info64", "ffe", "vesus", "manual"))
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
        resultats, _dups = deduplica(resultats, tornejos)       # el mateix torneig arribat per dues vies (dues adreces de Chess-Results, Info64, Vesus, CSV...)
        print(f"Duplicats: {len(_dups)} resultats repetits descartats")
        resultats.sort(key=lambda r: (r["fi"], r["jugador"]), reverse=True)
        # la variació d'Elo de totes les fonts es calcula igual, amb l'Elo FIDE real del mes (la que dona Info64 només és un control)
        for r in resultats:
            if r.get("font") in ("info64", "ffe", "vesus", "manual"):
                for g in r.get("partides", []):
                    g.pop("fide", None)
                if r.get("elo_fide"):
                    r["elo_fide_font"] = r.pop("elo_fide")
                calcula_elo(r, fce=False)
                if not r.get("elo_fide") and r.get("elo_fide_font"):
                    r["elo_fide"] = r.pop("elo_fide_font")
    except Exception as e:
        print("  Info64: no s'ha pogut afegir", e)
    # cada resultat individual ha de sortir a la classificació del seu torneig (si es reaprofita el torneig d'una execució anterior, hi pot faltar algú)
    for r in resultats:
        t = tornejos.get(r["tnr"]); cl = (t or {}).get("classificacio") or {}
        if t and isinstance(cl.get("jugadors"), list) and not t.get("equips") and r.get("lloc") is not None and not any(x["nom"] == r["jugador"] for x in cl["jugadors"]):
            cl["jugadors"].append({"nom": r["jugador"], "lloc": r["lloc"], "punts": r["punts"]})
    print(f"Elo estimat: FCE {ELO_N["fce"]} resultats, FIDE {ELO_N["fide"]} resultats; historial FCE de {len(hist)} jugadors, FIDE de {sum(1 for v in hist_f.values() if v)} jugadors")
    json.dump({"actualitzat": ara, "des": des, "resultats": resultats}, open(D_RES, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    json.dump({"actualitzat": ara, "tornejos": sorted(tornejos.values(), key=lambda x: x["fi"], reverse=True)},
              open("data/torneigs-jugadors.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    desa_elo_fide(c_fide, c_fce)
    print(f"Resum de torneigs: {len(tornejos)}")
    print(f"Torneigs propers d'Info64 a la llista de propers: {previs_info64()}")
    try:
        from elo_previsio import calcula as previsio_elo
        print(f"Previsió d'Elo FIDE de la llista següent: {previsio_elo('.')} jugadors")
    except Exception as e:
        print("  Previsió d'Elo no calculable", e)
    try:
        from elo_fce import calcula as previsio_fce
        print(f"Previsió d'Elo FCE de la llista següent: {previsio_fce('.')} jugadors")
    except Exception as e:
        print("  Previsió d'Elo FCE no calculable", e)


if __name__ == "__main__":
    a = sys.argv[1:]
    if "--prova-cr" in a:
        t = open(a[a.index("--prova-cr") + 1], encoding="utf-8").read()
        r = analitza_cr(t, a[a.index("--prova-cr") + 2])
        print(len(r), "torneigs"); print(json.dumps(r[:3], ensure_ascii=False, indent=1))
    else:
        main(a[a.index("--des") + 1] if "--des" in a else "2026-09-01")
