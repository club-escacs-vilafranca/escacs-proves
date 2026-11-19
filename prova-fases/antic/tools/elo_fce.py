"""Elo FCE estimat de les partides dels jugadors del club (sense xarxa) i previsió de la llista següent.

Regles (comprovades amb les taules de la FCE: 291 de 305 variacions mensuals exactes al maig-novembre del 2026):
  - Puntuació esperada = taula de la FIDE (B.02 8.1.2) ESTESA sense el límit de 400 punts (fins a .99 i 1.0). Variació = K x (resultat - esperat).
  - K estàndard com la FIDE: 40 als Sub-18 amb Elo < 2300, 20 (10 amb 2400 o més) a la resta, i 40 als jugadors nous (Elo des del 2026) fins a 30 partides.
    K ràpid i llampec: 20 (10 amb 2400 o més) per a tothom, sense dividir. El llampec compta amb l'Elo ràpid.
  - Incompareixença del rival (+.-, -.+): un quart de la K del RIVAL. Rival VACANT: un quart de la K pròpia. Els byes no compten.
  - Elo propi: el de la llista en vigor el dia de la partida. Elo del rival: el de la llista del mes de la partida, de l'historial mensual de la FCE
    (data/brut/fce_mensual/AAAAMM.json.gz); si no se sap qui és, l'Elo de Chess-Results (RtgN) i, si no n'hi ha, FIDE + diferencial.
  - Cada torneig entra a la llista del mes següent al que acaba (tall estricte, 3 dies abans de l'1: vegeu llista_de), llevat que el torneig tingui
    «llista_fce» a data/elo/<tnr>.json (per als que la FCE penja tard).
"""
import datetime, glob, gzip, json, os, re, sys, unicodedata
from collections import defaultdict

sys.path.insert(0, os.path.dirname(__file__))
from elo_calc import (_TAULA_FIDE, elo_a, fce_a_partir_de, llista_de, modalitat_elo, ratings_rival)

PUNTS = {"1": 1, "+": 1, "½": .5, "0": 0, "-": 0}
_TAULA_FCE = _TAULA_FIDE + [(432, .93), (456, .94), (484, .95), (517, .96), (559, .97), (619, .98), (735, .99)]


def esperat_fce(d):
    """Puntuació esperada del jugador; d = Elo del rival - Elo del jugador. Sense límit de 400 punts."""
    a = abs(d)
    pd = next((p for lim, p in _TAULA_FCE if a <= lim), 1.0)
    return 1 - pd if d > 0 else pd


def _norm(x):
    x = unicodedata.normalize("NFD", (x or "").lower())
    x = "".join(c for c in x if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z ]", " ", x).split()


def es_sub(categoria):
    m = re.search(r"Sub-?\s*(\d+)", categoria or "")
    return bool(m and int(m.group(1)) <= 18)


def k_base(elo, categoria, rapid):
    """K sense comptador de partides: 40 als Sub-18 amb Elo < 2300 (només estàndard), si no 20 (10 amb 2400 o més)."""
    if not rapid and es_sub(categoria) and elo < 2300:
        return 40
    return 20 if elo < 2400 else 10


class Ctx:
    """Dades de suport (rivals de tota la FCE, K manuals, ordre de partides) carregades del disc."""

    def __init__(self, arrel="."):
        self.arrel = arrel
        self.mens = {}
        for f in sorted(glob.glob(os.path.join(arrel, "data/brut/fce_mensual/*.json.gz"))):
            self.mens[os.path.basename(f)[:6]] = json.load(gzip.open(f, "rt", encoding="utf-8"))
        tots = []
        try:
            tots = json.load(gzip.open(os.path.join(arrel, "data/brut/fce_tots.json.gz"), "rt", encoding="utf-8"))["jugadors"]
        except Exception:
            pass
        self.tots, self.per_token = {}, defaultdict(list)
        for j in tots:
            c, _, p = j["n"].partition(",")
            j["nt"], j["ct"] = set(_norm(c) + _norm(p)), set(_norm(j.get("cl", "")))
            self.tots[j["id"]] = j
            for t in j["nt"]:
                self.per_token[t].append(j)
        self.cache = {}
        self.clubs_fce = [frozenset(w for w in _norm(c) if len(w) >= 3 and w not in ("club", "escacs", "esc")) for c in {j.get("cl", "") for j in tots}]
        self.clubs_fce = [c for c in self.clubs_fce if c]
        self.municipis = set()
        try:
            for n in json.load(open(os.path.join(arrel, "data/municipis-catalunya.json"), encoding="utf-8")):
                m = re.match(r"^(.*),\s*(l'|la|el|els|les)$", n)
                for v in ([n] if not m else [m.group(1), m.group(2) + ("" if m.group(2).endswith("'") else " ") + m.group(1)]):
                    v = " ".join(_norm(v))
                    if len(v) >= 4:
                        self.municipis.add(v)
        except Exception:
            pass
        try:
            self.k_manual = {k: v for k, v in json.load(open(os.path.join(arrel, "data/elo-k-manual.json"), encoding="utf-8")).items() if not k.startswith("_")}
        except Exception:
            self.k_manual = {}
        self.llista_tnr, self.valid_fce = {}, {}
        for f in glob.glob(os.path.join(arrel, "data/elo/*.json")):
            try:
                d = json.load(open(f, encoding="utf-8"))
            except Exception:
                continue
            tnr = d.get("tnr") or os.path.basename(f)[:-5]
            if d.get("llista_fce"):
                self.llista_tnr[str(tnr)] = str(d["llista_fce"])
        self.ordre = {}              # nom del jugador -> dates (ordenades) de les partides estàndard valides, per al comptador de 30 partides
        self.jug_per_fide, self.jug_per_nom, self.hist = {}, {}, {}
        try:
            self.posa_club(json.load(open(os.path.join(arrel, "data/jugadors.json"), encoding="utf-8")).get("jugadors", []),
                           json.load(open(os.path.join(arrel, "data/brut/hist_fce.json"), encoding="utf-8")))
        except Exception:
            pass

    def posa_club(self, jugadors, hist_fce):
        self.jug_per_nom = {j["nom"]: j for j in jugadors}
        self.jug_per_fide = {str(j["fide"]): j for j in jugadors if j.get("fide")}
        self.hist = hist_fce

    def hist_de(self, j):
        return (self.hist.get(str(j["id"])) or {}).get("h") or None

    def prepara(self, resultats, lliga=None, compilat=None):
        """Dates de les partides estàndard de cada jugador (per al comptador de 30 partides). `compilat` = {tnr: fila}; els tornejos sense validesa FCE no compten."""
        compilat = compilat or {}
        out = defaultdict(list)
        for r in resultats:
            c = compilat.get(str(r.get("tnr")))
            if r.get("font") != "chess-results" or r.get("fora_cat") or (c and c.get("fce") == "no") or str(r.get("tnr")) == "1379161":
                continue
            if ((c or {}).get("modalitat") or modalitat_elo(r).capitalize()).lower() != "standard":
                continue
            for g in r.get("partides", []):
                if g.get("inc") or g.get("res") not in ("1", "0", "½"):
                    continue
                out[r["jugador"]].append(g.get("data") or r["fi"])
        noms = {str(j["id"]): j["nom"] for j in self.jug_per_nom.values()}
        for gr in (lliga or {}).get("grups", []):
            for rd in gr.get("rondes", []):
                for t in rd.get("taulers") or []:
                    if t.get("inc") not in (None, "") and t.get("res") in ("1", "0", "½") and noms.get(str(t.get("idn"))) and rd.get("data"):
                        out[noms[str(t["idn"])]].append(rd["data"])
        for nom, v in out.items():
            self.ordre[nom] = sorted(v)

    # -------------------------------------------------- K
    def k_estandard(self, j, R, data, h=None, categoria=None):
        """K estàndard d'un jugador del club a la `data` (AAAA-MM-DD). `h` = el seu historial FCE (si no, el de la còpia del club)."""
        for m in self.k_manual.get(j["nom"], []):
            if data <= m["fins"]:
                return m["k"]
        cat = categoria if categoria is not None else j.get("categoria")
        if es_sub(cat) and R < 2300:
            return 40
        h = h or self.hist_de(j)
        if h and min(h) >= "202601":
            n = sum(1 for d in self.ordre.get(j["nom"], []) if d < data)
            if n < 30:
                return 40
        return 20 if R < 2400 else 10

    # -------------------------------------------------- rivals
    def club_fce(self, club):
        """True si `club` (tal com surt a Chess-Results, pot anar tallat) és un club de la llista de la FCE: un rival d'un club català té llicència i Elo FCE encara que ja no surti a la llista actual."""
        w = frozenset(x for x in _norm(club) if len(x) >= 3 and x not in ("club", "escacs", "esc"))
        if w and any(w <= c or c <= w for c in self.clubs_fce):
            return True
        txt = " " + " ".join(_norm(club)) + " "         # club d'un municipi català (encara que el club ja no tingui federats a la llista)
        return any(" " + m + " " in txt for m in self.municipis)

    def rival_fce(self, g):
        """Federat de la FCE que és el rival, o None si no es pot saber sense dubtes (varis candidats sense desempat)."""
        rv = g.get("rival")
        if not rv:
            return None
        ck = (rv, g.get("club"), g.get("rn"), g.get("ri"))
        if ck in self.cache:
            return self.cache[ck]
        t = _norm(rv)
        cand = [j for j in self.per_token.get(t[0], []) if set(t) <= j["nt"]] if t else []
        if not cand and t:       # variants d'escriptura (Joaquin/Joaquim): tots els mots del nom coincideixen amb un d'aquest federat amb com a màxim una lletra de diferència
            def prop(w, nt):
                return w in nt or (len(w) >= 5 and any(len(x) == len(w) and sum(a_ != b_ for a_, b_ in zip(w, x)) <= 1 for x in nt))
            ref0 = g.get("rn") or 0
            cand = [j for j in self.tots.values() if all(prop(w, j["nt"]) for w in t) and ref0
                    and any((m.get(j["id"]) or [None])[0] == ref0 for m in self.mens.values())]
        ct = {w for w in _norm(g.get("club") or "") if len(w) > 1}
        ref = g.get("rn") or 0

        def punts(j):
            x = 0
            if ref and any((m.get(j["id"]) or [None])[0] == ref for m in self.mens.values()):
                x += 10
            cj = {w for w in j["ct"] if len(w) > 1}
            if ct and cj and len(ct & cj) >= max(1, min(len(ct), len(cj)) - 1):      # sense inicials soltes («C.E.»), que no distingeixen clubs
                x += 3
            return x
        pick = None
        if len(cand) == 1:
            # un sol candidat pel nom: si Chess-Results no li dona Elo nacional (rn buit) i el club no coincideix, és un homònim d'una altra federació (p. ex. «Alberto Hernandez», C.A. Isla Bonita, no «Hernandez Bermudez, Alberto», Premià)
            if ref or punts(cand[0]) > 0 or not ct:
                pick = cand[0]
        elif cand:
            ss = sorted(((punts(j), j["id"], j) for j in cand), key=lambda z: -z[0])
            if ss[0][0] > 0 and ss[0][0] > ss[1][0]:
                pick = ss[0][2]
        self.cache[ck] = pick
        return pick

    def elo_rival(self, g, ym, rapid):
        j = self.rival_fce(g)
        if not j:
            return None
        v = (self.mens.get(ym) or {}).get(j["id"])
        return v[1 if rapid else 0] if v else None

    def novell(self, j):
        """Federat que apareix a la llista després de gener del 2026 (K 40 fins a 30 partides)."""
        for m in sorted(self.mens):
            if (self.mens[m] or {}).get(j["id"]):
                return m > "202601"
        return False

    def k_rival(self, g, opp, ym, rapid):
        """K del rival per a una incompareixença: del club (amb comptador i K manual) si és dels nostres; si no, per categoria i antiguitat."""
        rj = self.jug_per_fide.get(str(g.get("fid") or ""))
        data = g.get("data") or ""
        if rj:
            return self.k_estandard(rj, opp, data or ym + "-01") if not rapid else k_base(opp, rj.get("categoria"), True)
        j = self.rival_fce(g)
        cat = j.get("d") if j else ""
        if not rapid and j and self.novell(j):
            return 40
        return k_base(opp, cat, rapid)


_CTX = None


def contexte(arrel="."):
    global _CTX
    if _CTX is None or _CTX.arrel != arrel:
        _CTX = Ctx(arrel)
    return _CTX


def opp_joc(g, r, ctx, rapid, hist_club, ym):
    """Elo FCE del rival d'una partida: club (a la data), federat identificat (llista del mes), RtgN de Chess-Results o FIDE + diferencial."""
    rj = ctx.jug_per_fide.get(str(g.get("fid") or ""))
    if rj:
        h = ctx.hist_de(rj)
        v = elo_a(h, ym, rapid) if h else None
        if v:
            return v
    v = ctx.elo_rival(g, ym, rapid)
    if v:
        return v
    rn, ri = ratings_rival(g)
    if rn:
        return rn
    base = ri or g.get("rp") or None
    if base and ctx.club_fce(g.get("club")):
        return base      # club català: té Elo FCE (no surt a la llista actual) i és a prop del FIDE/performance; la taula FIDE→FCE només val per a federats d'altres federacions
       # sense cap Elo: la seva performance del torneig (guardada per cr_font quan el torneig ha acabat)
    return fce_a_partir_de(base) if base else None


def variacio_fce(r, hist, j, ctx=None):
    """Variació estimada de l'Elo FCE d'un torneig d'un jugador del club (escriu g["fce"] a cada partida). Torna {"var","partides","elo_inici","estimat"} o None."""
    ctx = ctx or contexte()
    rapid = modalitat_elo(r) in ("rapid", "blitz")
    tot, n, inici = 0.0, 0, None
    for g in r.get("partides", []):
        g.pop("fce", None)
        if g.get("res") not in PUNTS:
            continue
        rival = str(g.get("rival", "")).strip().lower()
        if rival in ("bye", "descans", "descanso", ""):
            continue
        data = g.get("data") or r.get("inici") or r["fi"]
        ym = data[:7].replace("-", "")
        R = elo_a(hist, ym, rapid)
        if not R:
            continue
        opp = opp_joc(g, r, ctx, rapid, hist, ym)
        s = PUNTS[g["res"]]
        if g.get("inc"):
            if not opp:
                continue
            k = ctx.k_rival(g, opp, ym, rapid)
            # K de la incompareixença = la més baixa de les dues (jugador i rival): Salvador Lluverol guanya per incompareixença contra un Sub-10 (K 40) i la FCE compta 5 (¼ de 20), no 10; amb les 29 incompareixences de l'any no n'empitjora cap
            own = k_base(R, j.get("categoria"), True) if rapid else ctx.k_estandard(j, R, data, hist)
            k = min(k, own)
            d = (k / 4) * (1 if s == 1 else -1)
            g["fce"] = {"d": round(d, 1), "k": k, "r": R, "opp": opp, "inc": True}
        else:
            if not opp:
                continue
            k = k_base(R, j.get("categoria"), True) if rapid else ctx.k_estandard(j, R, data, hist)
            d = k * (s - esperat_fce(opp - R))
            g["fce"] = {"d": round(d, 1), "k": k, "r": R, "opp": opp}
        tot += d
        n += 1
        inici = inici or R
    return {"var": round(tot, 1), "partides": n, "elo_inici": inici, "estimat": True} if n else None


# ---------------------------------------------------------------- previsió
def mes_seguent(ym):
    y, m = int(ym[:4]), int(ym[4:]) + 1
    return f"{y + (m > 12)}{(m - 1) % 12 + 1:02d}"


def llista_fce(r, ctx):
    """Llista (AAAAMM) on entra la variació FCE d'un torneig: la manual del CMS o la del dia que acaba."""
    return ctx.llista_tnr.get(str(r["tnr"])) or llista_de(r["fi"])


def arrodoneix(x):
    import math
    return int(math.floor(abs(x) + .5)) * (1 if x >= 0 else -1)


def previsio_fce(j, resultats_jugador, compilat, ctx):
    """Previsió de l'Elo FCE de la llista següent: {'prev_fce', 'prev_fce_n', 'prev_fce_ant', 'prev_fce_r', 'prev_fce_r_n', 'prev_fce_r_ant'} (només les que tenen partides pendents)."""
    h = ctx.hist_de(j)
    out = {}
    if not h:
        return out
    for rapid, sufix in ((False, ""), (True, "_r")):
        ms = [m for m in h if h[m][1 if rapid else 0]]
        if not ms:
            continue
        ult = max(ms)
        seg = mes_seguent(ult)
        tot, n = 0.0, 0
        for r in resultats_jugador:
            c = compilat.get(str(r["tnr"])) or {}
            if c.get("fce") == "no" or str(r["tnr"]) == "1379161" or r.get("fora_cat") or r.get("font") != "chess-results":
                continue
            if (modalitat_elo(r) in ("rapid", "blitz")) != rapid:
                continue
            if llista_fce(r, ctx) != seg:
                continue
            for g in r.get("partides", []):
                if g.get("fce"):
                    tot += g["fce"]["d"]
                    n += 1
        # tornejos que encara no entren a la llista següent sinó a una de posterior (p. ex. acaben a partir del dia de tall)
        pend = {}
        for r in resultats_jugador:
            c = compilat.get(str(r["tnr"])) or {}
            if c.get("fce") == "no" or str(r["tnr"]) == "1379161" or r.get("fora_cat") or r.get("font") != "chess-results":
                continue
            if (modalitat_elo(r) in ("rapid", "blitz")) != rapid:
                continue
            L = llista_fce(r, ctx)
            if L > seg:
                v = sum(g["fce"]["d"] for g in r.get("partides", []) if g.get("fce"))
                pend.setdefault(L, []).append({"t": r["torneig"], "d": round(v, 1)})
        if pend:
            out["pend_fce" + sufix] = [{"llista": L, "d": round(sum(x["d"] for x in v), 1), "tornejos": v} for L, v in sorted(pend.items())]
        if n:
            a = h[ult][1 if rapid else 0]
            out["prev_fce" + sufix] = a + arrodoneix(tot)
            out["prev_fce%s_n" % sufix] = n
            out["prev_fce%s_ant" % sufix] = a
    return out


def calcula(arrel="."):
    """Escriu a data/jugadors.json els camps prev_fce* de cada jugador. Torna quants en té."""
    def carrega(x, d):
        try:
            return json.load(open(os.path.join(arrel, x), encoding="utf-8"))
        except Exception:
            return d
    dj = carrega("data/jugadors.json", None)
    if not dj:
        return 0
    res = carrega("data/resultats-jugadors.json", {}).get("resultats", [])
    comp = {str(t["tnr"]): t for t in carrega("data/elo-compilat.json", {}).get("tornejos", [])}
    ctx = contexte(arrel)
    ctx.posa_club(dj.get("jugadors", []), carrega("data/brut/hist_fce.json", {}))
    ctx.prepara(res, carrega("data/lliga-2026.json", {}), comp)
    per = defaultdict(list)
    for r in res:
        per[r["jugador"]].append(r)
    n_ = 0
    for j in dj.get("jugadors", []):
        for c in [k for k in j if k.startswith(("prev_fce", "pend_fce"))]:
            j.pop(c, None)
        # les variacions per partida es calculen aquí perquè la previsió no depengui de l'ordre dels altres passos
        h = ctx.hist_de(j)
        if not h:
            continue
        for r in per.get(j["nom"], []):
            if r.get("partides") and not r.get("fora_cat") and r.get("font") == "chess-results":
                variacio_fce(r, h, j, ctx)
        p = previsio_fce(j, per.get(j["nom"], []), comp, ctx)
        if p:
            j.update(p)
            n_ += 1
    open(os.path.join(arrel, "data/jugadors.json"), "w", encoding="utf-8").write(json.dumps(dj, ensure_ascii=False, indent=1))
    return n_


if __name__ == "__main__":
    print("Previsió d'Elo FCE:", calcula("."), "jugadors")


def omple_emparellaments(resultats, ctx):
    """Emparellaments (partides futures): posa com a Elo del rival l'Elo FCE de l'última llista si és un federat que es pot identificar sense dubtes (el de Chess-Results és el d'inici de torneig o buit)."""
    if not ctx.mens:
        return 0
    ult = max(ctx.mens)
    n = 0
    for r in resultats:
        rapid = str(r.get("modalitat") or "").lower() in ("rapid", "ràpid", "blitz")
        for g in r.get("emparellaments") or []:
            if g.get("bye"):
                continue
            v = ctx.elo_rival(g, ult, rapid)
            if v:
                g["rtg_n"] = v
                n += 1
    return n
