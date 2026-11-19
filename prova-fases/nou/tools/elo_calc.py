"""Càlcul de la variació d'Elo (FCE estimat i FIDE) dels torneigs dels jugadors del club.

Aquest mòdul no fa servir la xarxa: només rep dades (resultats amb les seves partides i l'historial mensual d'Elo) i torna números.
Es pot provar i repetir tantes vegades com calgui sense baixar res. L'utilitza tools/jugadors.py.
"""
import datetime, glob, json, os, re, sys, unicodedata

# ---------------------------------------------------------------- Elo FCE estimat per torneig
DIF_FIDE_FCE = [(2401, 25, 2450), (2250, 50, 2325), (2100, 75, 2205), (1950, 105, 2095), (1800, 145, 1990), (1650, 190, 1890), (0, 240, 0)]


def fce_a_partir_de(base):
    """Taula d'equivalència FIDE -> Elo català de la FCE (factor corrector, amb mínim)."""
    for llindar, suma, minim in DIF_FIDE_FCE:
        if base >= llindar:
            return max(base + suma, minim)
    return base


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


def variacio_fce(r, hist, j):
    """Variació estimada de l'Elo FCE d'un torneig (regles a tools/elo_fce.py). `j` = el jugador del club (o només la seva categoria)."""
    from elo_fce import variacio_fce as _v
    if not isinstance(j, dict):
        j = {"nom": r.get("jugador", ""), "categoria": j}
    return _v(r, hist, j)


def llista_de(dia, dies=None):
    """Primera llista (AAAAMM) on entra una partida jugada el `dia` (AAAA-MM-DD). Les partides des del dia 29 del mes (a febrer, l'últim dia) ja no entren a la llista de l'1 del mes següent sinó a la posterior (regla de la FCE: 29 de març → llista de maig).
    `dies` (només proves): si es dona, el tall és `dies` dies abans de l'1 del mes següent."""
    d = datetime.date.fromisoformat(dia)
    y, m = d.year, d.month
    ult = (datetime.date(y + (m == 12), m % 12 + 1, 1) - datetime.timedelta(days=1)).day
    tall = (lambda: d.day >= min(29, ult)) if dies is None else (lambda: d >= datetime.date(y + (m == 12), m % 12 + 1, 1) - datetime.timedelta(days=dies))
    y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    if tall():
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return f"{y}{m:02d}"


def ym_ref(dates, dia, llarg):
    """Mes (AAAAMM) de la llista amb què la FIDE calcula una partida. Torneig curt (partides seguides): la llista vigent el primer dia del torneig, per a tot el torneig.
    Torneig llarg (setmanal, trams per rondes): la llista vigent el dia de cada ronda."""
    ds = [d for d in dates if d]
    if llarg or not ds:
        return dia[:7].replace("-", "")
    return min(ds)[:7].replace("-", "")


def torneig_llarg(dates, inici=None, fi=None):
    """Llarg si les partides del jugador ho són, o si el torneig sencer (inici-fi) dura més de 30 dies."""
    if es_llarg(dates):
        return True
    return bool(inici and fi) and (datetime.date.fromisoformat(fi) - datetime.date.fromisoformat(inici)).days > 30


def es_llarg(dates):
    """Torneig llarg (la FIDE el comunica per trams de rondes): més de 30 dies o rondes separades 5 dies o més (setmanals)."""
    ds = sorted({d for d in dates if d})
    if len(ds) < 2:
        return False
    dd = [datetime.date.fromisoformat(d) for d in ds]
    return (dd[-1] - dd[0]).days > 30 or any((b - a).days >= 5 for a, b in zip(dd, dd[1:]))


# Rival: només compta l'Elo FIDE del mateix mes de la partida (si aquell mes no surt a la llista, no té Elo: no s'arrossega el d'un mes anterior).
def fide_a(hist, ym, modal):
    ms = [m for m in hist if m <= ym and hist[m].get(modal)]
    return hist[max(ms)][modal] if ms else None


def fide_mes(hist, ym, modal):
    """Elo FIDE de la llista del mes exacte `ym`; si aquell mes no hi surt, no té Elo (no s'arrossega el d'un mes anterior)."""
    return (hist.get(ym) or {}).get(modal) or None


def variacio_fide(r, hist, categoria, hist_riv=None):
    """Variacio de l'Elo FIDE calculada per nosaltres amb l'Elo FIDE del mes de cada ronda; els rivals sense Elo FIDE no compten.
    Si no tenim l'historial de la FIDE, s'usa l'Elo internacional de la llista inicial del torneig."""
    modal = modalitat_elo(r)
    tot, n, inici = 0.0, 0, None
    dates = [g.get("data") for g in r.get("partides", [])] or [r.get("inici") or r["fi"]]
    llarg = torneig_llarg(dates, r.get("inici"), r.get("fi"))
    for g in r.get("partides", []):
        if g.get("inc") or g["res"] not in ("1", "0", "½", "+", "-"):
            continue
        ym = ym_ref(dates, g.get("data") or r.get("inici") or r["fi"], llarg)   # llista del primer dia del torneig/tram, no la del mes de cada partida
        R = fide_mes(hist, ym, modal) or (r.get("rtg_i") if modal == "standard" and not hist else None)
        hr = (hist_riv or {}).get(str(g.get("fid"))) if g.get("fid") else None
        ri = (hr["h"].get(ym) or {}).get(modal) if hr and hr.get("h") else (None if hr else ratings_rival(g)[1])
        if not R or not ri:
            continue
        s = {"1": 1, "+": 1, "½": 0.5, "0": 0, "-": 0}[g["res"]]
        k = k_fide(R, categoria)
        g["fide"] = {"d": round(k * (s - esperat_fide(ri - R)), 1), "k": k, "r": R, "opp": ri}
        tot += k * (s - esperat_fide(ri - R))
        n += 1
        inici = inici or R
    return {"var": round(tot, 1), "partides": n, "elo_inici": inici, "estimat": True} if n else None


def norm(x):
    x = unicodedata.normalize("NFKD", x or "").encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z]+", " ", x).strip()


def aplica_elo(r, per_nom, mod_cms, hist_fce_de, hist_fide_de, c_fide, fce=True):
    """Calcula la modalitat i la variació d'Elo (FCE estimat i FIDE) d'un resultat i ho escriu a `r`.
    hist_fce_de(j) i hist_fide_de(j) donen l'historial mensual del jugador `j` (poden anar a la xarxa o llegir la memòria cau).
    Torna (calculat FCE, calculat FIDE)."""
    r.pop("modalitat_dubtosa", None)
    if not r.get("modalitat"):          # si la pagina no ho diu, pel nom del torneig
        n_ = norm(r["torneig"])
        kw = re.search(r"llampec|blitz|actius|rapid|rapides", n_)
        r["modalitat"] = "Blitz" if re.search(r"llampec|blitz", n_) else "Rapid" if re.search(r"actius|rapid|rapides", n_) else "Standard"
        r["modalitat_dubtosa"] = not kw             # deduïda pel nom i sense cap paraula clau: ho ha de revisar el club
    r["modalitat_dubtosa"] = bool(r.get("modalitat_dubtosa"))
    if mod_cms.get(str(r["tnr"])) in ("Standard", "Rapid", "Blitz"):      # el que el club ha marcat al backoffice (Validesa per a l'Elo)
        r["modalitat"], r["modalitat_dubtosa"] = mod_cms[str(r["tnr"])], False
    j = per_nom.get(r["jugador"])
    if not j or not r.get("partides"):
        return 0, 0
    n_fce = n_fide = 0
    try:
        if not fce:
            raise StopIteration          # fonts de fora de Catalunya (Info64, Vesus, a mà): la FCE no les avalua
        h = hist_fce_de(j)
        v = variacio_fce(r, h, j) if h and not r.get("fora_cat") else None
        if v:
            r["elo_fce"] = v
            n_fce = 1
        elif r.get("fora_cat"):
            r.pop("elo_fce", None)
    except StopIteration:
        pass
    except Exception as e:
        print("  Elo FCE no disponible per a", r["jugador"], e)
    try:
        v = None if re.search(r"sub[\s-]?8\b|mini[\s-]?circuit", r["torneig"].lower()) else variacio_fide(r, hist_fide_de(j), j.get("categoria"), c_fide)   # els sub-8 i el Minicircuit no valen per a l'EloIDE
        if v:
            r["elo_fide"] = v
            n_fide = 1
    except Exception as e:
        print("  Elo FIDE no calculable per a", r["jugador"], e)
    return n_fce, n_fide


FONTS_EXTERNES = ("info64", "ffe", "vesus", "manual")


def calcula_lliga(ll, fide_de, hist_de, categoria_de, forca=False):
    """Variació d'Elo FIDE de cada partida de la Lliga (un fitxer data/lliga-<any>.json ja carregat), amb l'Elo FIDE real del mes de la ronda.
    `fide_de(codi FCE)` torna el codi FIDE, `hist_de(codi FIDE)` l'historial mensual (o None si no es té) i `categoria_de(codi FCE)` la categoria d'edat per a la K.
    Les partides que ja tenen càlcul (`fide`) no es toquen; si ningú del duel té Elo FIDE, es marca amb {} i no es torna a provar. Torna quantes partides s'han calculat."""
    n = 0
    for g in ll.get("grups", []):
        dates_g = [x.get("data") for x in g.get("rondes", [])]
        sub = bool(re.search(r"promoci\w*\s+sub", g.get("nom", ""), re.I))   # les lligues Promoció Sub-12 no compten per a l'Elo FIDE
        for rd in g.get("rondes", []):
            ym = ym_ref(dates_g, rd["data"], True) if rd.get("data") else ""
            for t in rd.get("taulers") or []:
                if t.get("fide_manual") or (t.get("fide") is not None and not forca) or not (t.get("idn") and t.get("idr") and ym) or t.get("res") not in ("1", "0", "½"):
                    continue
                if sub:
                    t["fide"] = {}
                    continue
                hn, hr = hist_de(fide_de(t["idn"])), hist_de(fide_de(t["idr"]))
                R = fide_mes(hn, ym, "standard") if hn else None
                ri = fide_mes(hr, ym, "standard") if hr else None
                if not R or not ri:
                    if hn is not None and hr is not None:
                        t["fide"] = {}               # sense Elo FIDE: no es torna a provar
                    continue
                k = k_fide(R, categoria_de(t["idn"]))
                sc = {"1": 1, "½": 0.5, "0": 0}[t["res"]]
                t["fide"] = {"d": round(k * (sc - esperat_fide(ri - R)), 1), "k": k, "r": R, "opp": ri}
                n += 1
    return n


def recalcula_lliga(arrel=".", forca=False):
    """Calcula les partides de la Lliga que encara no tenen variació FIDE amb els historials i codis ja desats (sense xarxa). Torna quantes n'ha calculat."""
    def carrega(x, per_defecte):
        try:
            return json.load(open(os.path.join(arrel, x), encoding="utf-8"))
        except Exception:
            return per_defecte
    per_id = {str(j["id"]): j for j in carrega("data/jugadors.json", {"jugadors": []}).get("jugadors", [])}
    codis, c_fide = carrega("data/brut/codis_fide.json", {}), carrega("data/brut/hist_fide.json", {})
    fide_de = lambda i: str(per_id[i]["fide"]) if per_id.get(i, {}).get("fide") else codis.get(i, "")
    hist_de = lambda f: (c_fide.get(f) or {}).get("h") if f else None
    total = 0
    for fl in sorted(glob.glob(os.path.join(arrel, "data/lliga-*.json"))):
        ll = json.load(open(fl, encoding="utf-8"))
        n = calcula_lliga(ll, fide_de, hist_de, lambda i: per_id.get(i, {}).get("categoria"), forca)
        antic = open(fl, encoding="utf-8").read()
        nou = json.dumps(ll, ensure_ascii=False, indent=1) + "\n"
        if nou != antic:
            open(fl, "w", encoding="utf-8").write(nou)
        total += n
    print(f"Lliga: variació FIDE de {total} partides calculades")
    return total


def recalcula_fitxer(arrel="."):
    """Torna a calcular l'Elo de tots els resultats de data/resultats-jugadors.json amb els historials ja desats (sense xarxa).
    Només escriu el fitxer si alguna cosa canvia. Torna el nombre de resultats que han canviat."""
    def p(x):
        return os.path.join(arrel, x)

    def carrega(x, per_defecte):
        try:
            return json.load(open(p(x), encoding="utf-8"))
        except Exception:
            return per_defecte
    club = carrega("data/jugadors.json", {"jugadors": []}).get("jugadors", [])
    per_nom = {j["nom"]: j for j in club}
    c_fce, c_fide = carrega("data/brut/hist_fce.json", {}), carrega("data/brut/hist_fide.json", {})
    mod_cms = {str(o["tnr"]): o.get("modalitat") for o in carrega("data/elo-compilat.json", {}).get("tornejos", [])}
    dades = carrega("data/resultats-jugadors.json", None)
    if not dades:
        print("No hi ha data/resultats-jugadors.json")
        return 0
    abans = json.dumps(dades, ensure_ascii=False, indent=1)
    import elo_fce
    ctx = elo_fce.contexte(arrel)
    ctx.posa_club(club, c_fce)
    ctx.prepara(dades.get("resultats", []), carrega("data/lliga-2026.json", {}), {str(o["tnr"]): o for o in carrega("data/elo-compilat.json", {}).get("tornejos", [])})
    h_fce = lambda j: (c_fce.get(str(j["id"])) or {}).get("h") or None
    h_fide = lambda j: (c_fide.get(str(j.get("fide"))) or {}).get("h") or {}
    n_fce = n_fide = canvis = 0
    elo_fce.omple_emparellaments(dades.get("resultats", []), ctx)
    for r in dades.get("resultats", []):
        v_abans = json.dumps(r, ensure_ascii=False, sort_keys=True)
        externa = r.get("font") in FONTS_EXTERNES
        if externa:
            for g in r.get("partides", []):
                g.pop("fide", None)
            if "elo_fide_font" in r:
                r.pop("elo_fide", None)               # el que hi ha és el nostre càlcul anterior; el de la font ja està guardat
            elif r.get("elo_fide"):
                r["elo_fide_font"] = r.pop("elo_fide")
        a, b = aplica_elo(r, per_nom, mod_cms, h_fce, h_fide, c_fide, fce=not externa)
        n_fce += a
        n_fide += b
        if externa and not r.get("elo_fide") and r.get("elo_fide_font"):
            r["elo_fide"] = r.pop("elo_fide_font")
        elif externa and "elo_fide_font" in r and r.get("elo_fide_font") == r.get("elo_fide"):
            r.pop("elo_fide_font")                    # no era de la font, era un càlcul nostre anterior
        if json.dumps(r, ensure_ascii=False, sort_keys=True) != v_abans:
            canvis += 1
    despres = json.dumps(dades, ensure_ascii=False, indent=1)
    print(f"Elo recalculat: FCE {n_fce} resultats, FIDE {n_fide} resultats; {canvis} resultats han canviat")
    if despres != abans:
        open(p("data/resultats-jugadors.json"), "w", encoding="utf-8").write(despres)
    return canvis


if __name__ == "__main__":
    _arrel = sys.argv[1] if len(sys.argv) > 1 else "."
    recalcula_fitxer(_arrel)
    recalcula_lliga(_arrel)
