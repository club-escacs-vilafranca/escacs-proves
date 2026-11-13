#!/usr/bin/env python3
"""Resultats dels jugadors del club a tornejos homologats FIDE de la federació francesa (echecs.asso.fr) -> data/ffe-jugadors.json.
La FFE (sense robots.txt) publica, per a cada torneig FIDE, la llista de participants i la classificació, amb la bandera de federació però SENSE
l'ID FIDE: per això s'identifica cada jugador pel nom (cognoms + nom) i la bandera ESP, i el resultat es marca amb `identitat: "nom+ESP"`.
Escaneja les llistes mensuals «Tournois homologués FIDE» (Tournois.aspx -> ListeTournois.aspx?Action=FIDE&Level=N), amb 1 petició per segon,
i recorda els torneigs ja revisats (data/brut/ffe_vistos.json) per no tornar-los a llegir. Ús: python3 tools/ffe.py [des=AAAA-MM-DD] [--recent]"""
import html as H, json, os, re, sys, time, unicodedata, urllib.parse, urllib.request
from datetime import datetime, timedelta, timezone

BASE = "https://www.echecs.asso.fr"
UA = "Mozilla/5.0 (compatible; club-escacs-vilafranca; +https://github.com/club-escacs-vilafranca/web-club)"
SORTIDA, VISTOS = "data/ffe-jugadors.json", "data/brut/ffe_vistos.json"
args = [a for a in sys.argv[1:] if not a.startswith("--")]
DES = args[0] if args else "2026-02-01"
FINS = args[1] if len(args) > 1 else None      # límit superior opcional (AAAA-MM-DD), per repartir l'escaneig llarg en trams
RECENT = "--recent" in sys.argv          # només els darrers 30 dies (cerca habitual de cada nit)
OPC = dict(a[2:].split("=", 1) for a in sys.argv[1:] if a.startswith("--") and "=" in a)
TORNEIG = OPC.get("torneig")    # --torneig=nom: només els torneigs el nom dels quals el conté (cerca per nom, p. ex. detectat a FIDE)
MES_FIDE = OPC.get("mes")                # --mes=AAAA-MM: només la llista mensual FIDE d'aquest mes (el mes en què el torneig entra a FIDE)
MAX_MIN = int(OPC.get("max-minuts", "0") or 0)   # pressupost de temps: desa i surt net abans que GitHub talli l'acció
T0 = time.time()
MESOS = ["janvier", "fevrier", "mars", "avril", "mai", "juin", "juillet", "aout", "septembre", "octobre", "novembre", "decembre"]
VERSIO = 1


def sa(t):
    return re.sub(r"[^a-z0-9]+", " ", unicodedata.normalize("NFKD", H.unescape(t or "")).encode("ascii", "ignore").decode().lower()).strip()


def get(u, dades=None, intents=3):
    for i in range(intents):
        try:
            rq = urllib.request.Request(u, urllib.parse.urlencode(dades).encode() if dades else None, headers={"User-Agent": UA})
            r = urllib.request.urlopen(rq, timeout=60).read().decode("utf-8", "replace")
            time.sleep(1)
            return r
        except Exception as e:
            if i == intents - 1:
                raise
            time.sleep(5 * (i + 1))


def nivells():
    """{(any, mes): level} de les opcions «FIDE <Mes> <Any>» de Tournois.aspx."""
    h = get(BASE + "/Tournois.aspx")
    sel = re.search(r'<select[^>]*DropHomologuesFide.*?</select>', h, re.S).group(0)
    d = {}
    for v, t in re.findall(r'<option[^>]*value="([^"]*)"[^>]*>([^<]*)', sel):
        m = re.match(r"FIDE\s+(\S+)\s+(\d{4})", sa(t).replace(" ", " ") and H.unescape(t).strip())
        if m:
            mes = sa(m.group(1))
            if mes in MESOS:
                d[(int(m.group(2)), MESOS.index(mes) + 1)] = v
    return d


def llista(level):
    """Torneigs d'una llista mensual (totes les pàgines): [{ref, ciutat, nom, data}]."""
    u = f"{BASE}/ListeTournois.aspx?Action=FIDE&Level={level}"
    h, pag, out = get(u), 1, []
    while True:
        any_ = None
        for m in re.finditer(r'<td class="liste_titre"[^>]*>(.*?)</td>|<tr class=liste_(?:fonce|clair)>(.*?)</tr>', h, re.S):
            if m.group(1) is not None:
                t = sa(re.sub(r"<[^>]+>", " ", m.group(1)))
                mm = re.search(r"(\w+) (\d{4})$", t)
                any_ = int(mm.group(2)) if mm else any_
                continue
            fila = m.group(2)
            r = re.search(r"FicheTournoi\.aspx\?Ref=(\d+)[^>]*>([^<]*)</a>", fila)
            tds = re.findall(r"<td[^>]*>(.*?)</td>", fila, re.S)
            if r and len(tds) >= 5:
                out.append({"ref": r.group(1), "nom": H.unescape(r.group(2)).strip(), "ciutat": H.unescape(re.sub(r"<[^>]+>", "", tds[1])).strip(),
                            "data_txt": re.sub(r"<[^>]+>", "", tds[4]).strip(), "any": any_})
        print(f"    llista {level} pàg. {pag}: {len(out)} torneigs", flush=True)
        pag += 1
        if pag > 40 or not re.search(r"PagerFooter'\s*,\s*'%d'" % pag, h):
            break
        v = {k: H.unescape(x) for k, x in re.findall(r'<input[^>]*type="hidden"[^>]*name="([^"]+)"[^>]*value="([^"]*)"', h)}
        v["__EVENTTARGET"], v["__EVENTARGUMENT"] = "ctl00$ContentPlaceHolderMain$PagerFooter", str(pag)
        n0 = len(out)
        h = get(u, v)
        if not re.search(r"FicheTournoi\.aspx\?Ref=(?!(?:%s)\b)" % "|".join(t["ref"] for t in out) , h):
            break
    return out


def mes_num(t):
    """Mes francès (complet o abreujat: sept., oct., juil.) -> 1..12."""
    t = sa(t).replace(" ", "")
    for i, m in enumerate(MESOS):
        if t == m or (len(t) >= 3 and m.startswith(t)) or (t.startswith(m[:4]) and len(t) <= 5):
            return i + 1
    return None


def data_iso(txt, any_):
    m = re.match(r"(\d+)\s+(\S+)", sa(txt) and H.unescape(txt).strip())
    if not m:
        return None
    mes = mes_num(m.group(2))
    if not mes:
        return None
    return "%04d-%02d-%02d" % (any_ or datetime.now().year, mes, int(m.group(1)))


def files(h):
    return [[re.sub(r"\s+", " ", H.unescape(re.sub(r"<[^>]+>", " ", c))).strip() for c in re.findall(r"<td[^>]*>(.*?)</td>", f, re.S)] + [
        (re.search(r"flags/(\w+)\.GIF", f, re.I) or [None, ""])[1]] for f in re.findall(r"<tr class=papi_liste_\w>(.*?)</tr>", h, re.S)]


def tokens(n):
    return [w for w in sa(n).split() if len(w) > 1]


def troba(nom_ffe, club):
    """Jugador del club que correspon a «COGNOM(S) Nom» de la FFE: mateixos mots que el nom complet de la federació (nom_cr) o que el nom curt; si dos jugadors coincideixen, cap."""
    t = set(tokens(nom_ffe))
    c = []
    for j in club:
        if len(t) >= 2 and (t == set(tokens(j.get("nom_cr") or "")) or t == set(tokens(j["nom"]))):
            c.append(j)
    return c[0] if len(c) == 1 else None


def main():
    club = json.load(open("data/jugadors.json", encoding="utf-8"))["jugadors"]
    avui = datetime.now(timezone.utc).date()
    des = (avui - timedelta(days=30)).isoformat() if RECENT else DES
    vistos = json.load(open(VISTOS, encoding="utf-8")) if os.path.exists(VISTOS) else {}
    antic = json.load(open(SORTIDA, encoding="utf-8")).get("resultats", []) if os.path.exists(SORTIDA) else []
    resultats = {(r["fide"] or r["jugador"], r["tnr"]): r for r in antic if r.get("v") == VERSIO}
    niv = nivells()
    desd = datetime.fromisoformat(des).date()
    lim = datetime.fromisoformat(FINS).date() if FINS else avui
    sup = (lim.year + (lim.month == 12), lim.month % 12 + 1)
    claus = sorted(k for k in niv if (k[0], k[1]) >= (desd.year, desd.month) and (k[0], k[1]) <= sup)
    if MES_FIDE:
        a, m = MES_FIDE.split("-")
        claus = [k for k in claus if k == (int(a), int(m))] or [k for k in niv if k == (int(a), int(m))]
    print("Llistes mensuals a revisar:", claus)
    nous = 0

    def desa():
        os.makedirs("data/brut", exist_ok=True)
        json.dump(vistos, open(VISTOS, "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
        json.dump({"actualitzat": datetime.now(timezone.utc).isoformat(timespec="seconds"), "des": DES, "resultats": sorted(resultats.values(), key=lambda r: (r["fi"], r["jugador"]))},
                  open(SORTIDA, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    for k in claus:
        ll = llista(niv[k])
        print("  exemples:", [(t["ref"], t["data_txt"], t["any"], data_iso(t["data_txt"], t["any"])) for t in ll[:2] + ll[-2:]], flush=True)
        for t in ll:
            if MAX_MIN and time.time() - T0 > MAX_MIN * 60:
                print("Pressupost de temps esgotat: es desa i se surt (es continuarà a la propera execució)", flush=True)
                desa()
                return
            fi = data_iso(t["data_txt"], t["any"])
            if not fi or fi < des or fi > (FINS or avui.isoformat()):
                continue
            if TORNEIG and sa(TORNEIG) not in sa(t["nom"]):
                continue
            ref = t["ref"]
            v = vistos.get(ref)
            if v and v.get("v") == VERSIO and v.get("fi") < (avui - timedelta(days=3)).isoformat():
                esp = v["esp"]
            else:
                ls = get(f"{BASE}/Resultats.aspx?URL=Tournois/Id/{ref}/{ref}&Action=Ls")
                esp = [f[2] for f in files(ls) if len(f) >= 3 and f[-1].upper() == "ESP"]
                vistos[ref] = {"v": VERSIO, "fi": fi, "esp": esp}
            hit = {}
            for n in esp:
                j = troba(n, club)
                if j:
                    hit[n] = j
            if not hit:
                continue
            fitxa = get(f"{BASE}/FicheTournoi.aspx?Ref={ref}")
            txt = re.sub(r"\s+", " ", H.unescape(re.sub(r"<[^>]+>", " ", fitxa)))
            rondes = int((re.search(r"Nombre de rondes\s*:\s*(\d+)", txt) or [0, 0])[1] or 0)
            cl = files(get(f"{BASE}/Resultats.aspx?URL=Tournois/Id/{ref}/{ref}&Action=Cl"))
            cl = [f for f in cl if len(f) >= 11]
            for n, j in hit.items():
                f = next((f for f in cl if sa(f[2]) == sa(n)), None)
                if not f:
                    print("  sense classificació:", t["nom"], n)
                    continue
                punts = f[8].replace(" ", "")
                lloc = int(f[0]) if f[0].isdigit() else None
                elo = re.match(r"(\d+)", f[3])
                r = {"jugador": j["nom"], "fide": j.get("fide") or "", "font": "ffe", "v": VERSIO, "tnr": "ffe-" + ref, "snr": None,
                     "torneig": t["nom"], "fi": fi, "inici": fi, "club": "", "fed": "ESP", "lloc": lloc, "rondes": rondes or None, "de": len(cl),
                     "url": f"{BASE}/FicheTournoi.aspx?Ref={ref}", "punts": punts,
                     "modalitat": "Ràpid" if re.search(r"rapide|blitz", t["nom"], re.I) else "Standard", "rtg_i": int(elo.group(1)) if elo else None,
                     "ciutat": t["ciutat"], "identitat": "nom+ESP", "partides": []}
                if (r["fide"] or r["jugador"], r["tnr"]) not in resultats:
                    nous += 1
                resultats[(r["fide"] or r["jugador"], r["tnr"])] = r
                print("  TROBAT:", j["nom"], "→", t["nom"], fi, "lloc", lloc, "punts", r["punts"])
        desa()
        print("Mes revisat:", k, "· torneigs vistos:", len(vistos), flush=True)
    desa()
    print(f"Torneigs revisats: {len(vistos)}; resultats del club: {len(resultats)} ({nous} de nous)")


if __name__ == "__main__":
    main()
