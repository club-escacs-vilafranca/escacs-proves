#!/usr/bin/env python3
"""Converteix els CSV de resultats de resultats-csv/*.csv en torneigs de data/manual-jugadors.json.

Un CSV = un o més torneigs; una fila = una partida d'un jugador del club (o una fila sola amb el resultat global si no hi ha partides).
Un torneig que ja hi era (mateix nom i mateix últim dia) se substitueix sencer; els altres no es toquen. Es pot tornar a pujar el mateix CSV corregit.
Si hi ha qualsevol error, no es canvia res i es diu quina fila i quin és el problema.
Ús:  python3 tools/csv_resultats.py [carpeta-csv]
"""
import csv, datetime, glob, io, json, os, re, sys

CAPS = ["torneig", "inici", "fi", "ciutat", "ritme", "enllac", "rondes", "participants", "jugador", "punts", "lloc",
        "ronda", "dia", "rival", "elo_rival", "fide_rival", "club_rival", "color", "resultat"]
ALIES = {"enllaç": "enllac", "nom del torneig": "torneig", "primer dia": "inici", "ultim dia": "fi", "últim dia": "fi", "modalitat": "ritme",
         "elo rival": "elo_rival", "fide rival": "fide_rival", "club rival": "club_rival", "data": "dia", "punts totals": "punts"}
RES = {"1": "1", "1-0": "1", "0": "0", "0-1": "0", "½": "½", "0.5": "½", "0,5": "½", "1/2": "½", "=": "½", "x": "½", "+": "+", "-": "-", "t": "½", "g": "1", "p": "0"}
COLOR = {"w": "w", "b": "w", "blanques": "w", "blanc": "w", "s": "s", "n": "s", "negres": "s", "negre": "s", "": ""}
RITME = {"standard": "Standard", "estandard": "Standard", "estàndard": "Standard", "clàssic": "Standard", "classic": "Standard", "rapid": "Rapid", "ràpid": "Rapid", "rapida": "Rapid", "ràpides": "Rapid",
         "rapides": "Rapid", "blitz": "Blitz", "": "Standard"}
ESPAI = re.compile(r"\s+")


def llegeix_text(ruta):
    b = open(ruta, "rb").read()
    for enc in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            return b.decode(enc)
        except UnicodeDecodeError:
            pass


def files(ruta):
    t = llegeix_text(ruta)
    sep = max(";,\t", key=lambda c: t.split("\n")[0].count(c))     # Excel en català/castellà desa amb «;»
    rd = csv.reader(io.StringIO(t), delimiter=sep)
    cap = None
    for n, f in enumerate(rd, 1):
        if not any(c.strip() for c in f):
            continue
        if cap is None:
            cap = [ALIES.get(c.strip().lower(), c.strip().lower()) for c in f]
            falten = [c for c in ("torneig", "fi", "jugador") if c not in cap]
            if falten:
                raise ValueError(f"{os.path.basename(ruta)}: a la primera fila falten les columnes {', '.join(falten)}")
            continue
        yield n, {c: ESPAI.sub(" ", (f[i] if i < len(f) else "")).strip() for i, c in enumerate(cap)}


def data(v, n, camp, errs, obligatori=False):
    if not v:
        if obligatori:
            errs.append(f"fila {n}: falta {camp}")
        return ""
    m = re.match(r"(\d{4})-(\d\d?)-(\d\d?)$", v) or re.match(r"(\d\d?)[/.-](\d\d?)[/.-](\d{4})$", v)
    try:
        if m and len(m.group(1)) == 4:
            d = datetime.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        elif m:
            d = datetime.date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
        else:
            raise ValueError
    except ValueError:
        errs.append(f"fila {n}: {camp} «{v}» no és una data (escriu-la com 2026-05-23 o 23/05/2026)")
        return ""
    return d.isoformat()


def enter(v, n, camp, errs):
    if not v:
        return None
    try:
        return int(float(v.replace(",", ".")))
    except ValueError:
        errs.append(f"fila {n}: {camp} «{v}» ha de ser un número")
        return None


def converteix(ruta, nostres=None):
    """Torna (llista de torneigs, errors)."""
    errs, tornejos = [], {}
    for n, f in files(ruta):
        nom, fi = f.get("torneig", ""), data(f.get("fi", ""), n, "l'últim dia", errs, True)
        if not nom:
            errs.append(f"fila {n}: falta el nom del torneig")
            continue
        t = tornejos.setdefault((nom, fi), {"nom": nom, "inici": "", "fi": fi, "ciutat": "", "modalitat": "Standard", "url": "", "rondes": None, "participants": None, "jugadors": {}})
        for c, k in (("ciutat", "ciutat"), ("enllac", "url")):
            if f.get(c) and not t[k]:
                t[k] = f[c]
        if f.get("inici") and not t["inici"]:
            t["inici"] = data(f["inici"], n, "el primer dia", errs)
        if f.get("ritme") and f["ritme"].lower() in RITME:
            t["modalitat"] = RITME[f["ritme"].lower()]
        elif f.get("ritme"):
            errs.append(f"fila {n}: ritme «{f['ritme']}» no és Standard, Rapid ni Blitz")
        for c in ("rondes", "participants"):
            if f.get(c) and t[c] is None:
                t[c] = enter(f[c], n, c, errs)
        jug = f.get("jugador", "")
        if not jug:
            errs.append(f"fila {n}: falta el jugador")
            continue
        if nostres is not None and jug not in nostres:
            errs.append(f"fila {n}: el jugador «{jug}» no surt a la llista del club (escriu-lo exactament com a la web, p. ex. «Silvia Serradell»)")
        j = t["jugadors"].setdefault(jug, {"jugador": jug, "punts": "", "lloc": None, "partides": []})
        if f.get("punts"):
            j["punts"] = f["punts"].replace(",", ".")
        if f.get("lloc"):
            j["lloc"] = enter(f["lloc"], n, "lloc", errs)
        if f.get("rival") or f.get("resultat"):
            r = RES.get(f.get("resultat", "").lower())
            if not r:
                errs.append(f"fila {n}: resultat «{f.get('resultat', '')}» no vàlid (usa 1, 0, ½, 0.5, + o -)")
            if not f.get("rival"):
                errs.append(f"fila {n}: falta el rival")
            col = COLOR.get(f.get("color", "").lower())
            if col is None:
                errs.append(f"fila {n}: color «{f['color']}» no vàlid (usa b/n, w/s o deixa-ho buit)")
            g = {"ronda": enter(f.get("ronda", ""), n, "ronda", errs), "rival": f.get("rival", ""), "rtg_i": enter(f.get("elo_rival", ""), n, "elo_rival", errs),
                 "fid": re.sub(r"\D", "", f.get("fide_rival", "")), "club": f.get("club_rival", ""), "color": col or "", "res": r or ""}
            if not g["ronda"]:
                errs.append(f"fila {n}: falta la ronda")
            d = data(f.get("dia", ""), n, "el dia", errs)
            if d:
                g["data"] = d
            j["partides"].append(g)
    out = []
    for t in tornejos.values():
        t["jugadors"] = list(t["jugadors"].values())
        for j in t["jugadors"]:
            if not j["punts"]:
                j["punts"] = str(sum({"1": 1, "½": .5, "+": 1}.get(g["res"], 0) for g in j["partides"])).replace(".0", "")
            rondes = [g["ronda"] for g in j["partides"] if g["ronda"]]
            if len(rondes) != len(set(rondes)):
                errs.append(f"{t['nom']}, {j['jugador']}: hi ha dues partides amb el mateix número de ronda")
        if not t["inici"]:
            t["inici"] = t["fi"]
        if t["inici"] > t["fi"]:
            errs.append(f"{t['nom']}: el primer dia és posterior a l'últim")
        out.append(t)
    return out, errs


def main(carpeta="resultats-csv", desti="data/manual-jugadors.json", jug="data/jugadors.json"):
    nostres = {j["nom"] for j in json.load(open(jug, encoding="utf-8")).get("jugadors", [])} if os.path.exists(jug) else None
    rutes = [r for r in sorted(glob.glob(os.path.join(carpeta, "*.csv"))) if not os.path.basename(r).upper().startswith("PLANTILLA")]
    nous, errs = [], []
    for r in rutes:
        try:
            t, e = converteix(r, nostres)
            nous += t
            errs += [f"{os.path.basename(r)}, {x}" for x in e]
        except Exception as e:
            errs.append(f"{os.path.basename(r)}: no s'ha pogut llegir ({e})")
    if errs:
        print("NO S'HA CANVIAT RES. Cal corregir:")
        for e in errs:
            print(" -", e)
        return 1
    d = json.load(open(desti, encoding="utf-8")) if os.path.exists(desti) else {"actualitzat": "", "torneigs": []}
    claus = {(t["nom"], t["fi"]) for t in nous}
    d["torneigs"] = [t for t in d.get("torneigs", []) if (t.get("nom"), t.get("fi")) not in claus] + nous
    d["torneigs"].sort(key=lambda t: t["fi"], reverse=True)
    json.dump(d, open(desti, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"{len(nous)} torneigs importats de {len(rutes)} fitxers CSV ({sum(len(j['partides']) for t in nous for j in t['jugadors'])} partides).")
    return 0


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:2]))
