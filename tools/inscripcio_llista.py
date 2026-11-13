#!/usr/bin/env python3
"""Llista de jugadors per al formulari d'inscripció (cerca per cognom).

Base: llista pública de FIDE (jugadors d'Espanya: ID, nom, sexe, títol, Elo estàndard/ràpid/blitz, any de naixement).
Es complementa amb el que sabem nosaltres: socis del club (ID FIDE, Elo FCE estàndard i ràpid) i jugadors dels resultats importats.

  python3 tools/inscripcio_llista.py --fide   # descarrega la llista de FIDE (acció de GitHub, cada mes)
  python3 tools/inscripcio_llista.py --fce    # descarrega l'Elo FCE (estàndard i ràpid) de tots els jugadors federats a Catalunya
  python3 tools/inscripcio_llista.py          # només refà la fusió amb la còpia desada de FIDE (data/brut/fide_esp.json)
Sortida: data/inscripcio-jugadors.json
"""
import glob, gzip, json, os, re, subprocess, sys, unicodedata, zipfile
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

ARREL = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
FIDE_URL = "https://ratings.fide.com/download/players_list_xml.zip"
BRUT = os.path.join(ARREL, "data/brut/fide_esp.json.gz")
SORTIDA = os.path.join(ARREL, "data/inscripcio")
FCE_URL = "https://escacs.cat/components/com_fce/gmvw20/conn/resultatCerca.php"
FCE_BRUT = os.path.join(ARREL, "data/brut/fce_tots.json.gz")


def norm(s):
    s = unicodedata.normalize("NFD", s or "")
    return re.sub(r"[^a-z0-9 ]+", " ", "".join(c for c in s if unicodedata.category(c) != "Mn").lower()).strip()


def tokens(s):
    return set(norm(s).split())


def llegeix(p):
    with open(os.path.join(ARREL, p), encoding="utf-8") as f:
        return json.load(f)


def int0(x):
    try:
        return int(x)
    except (TypeError, ValueError):
        return 0


def baixa_fide():
    """Descarrega la llista de FIDE i es queda amb els jugadors d'Espanya. Desa data/brut/fide_esp.json."""
    print("Descarregant", FIDE_URL, flush=True)
    cami = "/tmp/fide_players.zip"
    # curl -4 (IPv4) perquè des de les màquines de GitHub la connexió de Python se'n va per temps d'espera
    subprocess.run(["curl", "-4", "-sSL", "--connect-timeout", "20", "--retry", "2", "--retry-delay", "5", "-m", "900", "-A", "Mozilla/5.0", "-o", cami, FIDE_URL], check=True)
    print(os.path.getsize(cami) // 1024, "KB descarregats", flush=True)
    z = zipfile.ZipFile(cami)
    nom = z.namelist()[0]
    sortida, total = [], 0
    with z.open(nom) as f:
        for _, el in ET.iterparse(f, events=("end",)):
            if el.tag != "player":
                continue
            total += 1
            g = lambda k: (el.findtext(k) or "").strip()
            if g("country") == "ESP":
                std, rap, bli = int0(g("rating")), int0(g("rapid_rating")), int0(g("blitz_rating"))
                actiu = "i" not in g("flag").lower()
                if std or rap or bli or actiu:
                    sortida.append({"f": g("fideid"), "n": g("name"), "s": g("sex"), "t": g("title"), "e": std, "er": rap, "eb": bli, "y": int0(g("birthday"))})
            el.clear()
    print(total, "jugadors a la llista;", len(sortida), "d'Espanya", flush=True)
    if len(sortida) < 5000:
        raise SystemExit("Massa pocs jugadors d'Espanya: el format de la llista potser ha canviat. No es desa res.")
    os.makedirs(os.path.dirname(BRUT), exist_ok=True)
    with gzip.open(BRUT, "wt", encoding="utf-8") as f:
        json.dump({"descarregat": datetime.now(timezone.utc).strftime("%Y-%m-%d"), "jugadors": sortida}, f, ensure_ascii=False, separators=(",", ":"))
    return sortida


def baixa_fce():
    """Una sola consulta a la FCE sense filtrar per club: tots els jugadors amb Elo estàndard (elo) i ràpid (eloR)."""
    import time, urllib.parse, urllib.request
    dades = urllib.parse.urlencode({"idJugador": "", "nomLLarg": "", "elo_XYZ1": "", "elo_XYZ2": "", "idClub": "", "titol": "", "edat": "", "sexe": "",
                                    "limitNoRows": "50000", "nomFitxa": "c_jugadors_0.xml", "dadesCercar": "jugadors_0.xml"}).encode()
    cap = {"User-Agent": "Mozilla/5.0 (compatible; club-escacs-vilafranca)", "X-Requested-With": "XMLHttpRequest",
           "Referer": "https://escacs.cat/index.php/component/fce?op=2", "Origin": "https://escacs.cat",
           "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8"}
    ultim = None
    for i in range(4):
        try:
            with urllib.request.urlopen(urllib.request.Request(FCE_URL, data=dades, headers=cap), timeout=120) as r:
                j = json.loads(r.read().decode("utf-8", "replace"))
            fila = (j.get("source") or {}).get("localdata") or j.get("localdata") or []
            sortida = []
            for f in fila:
                if not f.get("nomLlarg"):
                    continue
                sortida.append({"id": str(f.get("idJugador") or ""), "n": f["nomLlarg"].strip(), "e": int0(f.get("elo")), "er": int0(f.get("eloR")),
                                "cl": (f.get("nomClub") or "").strip(), "s": f.get("sexe") or ""})
            if len(sortida) < 3000:
                raise RuntimeError("la llista de la FCE és massa curta (%d)" % len(sortida))
            os.makedirs(os.path.dirname(FCE_BRUT), exist_ok=True)
            with gzip.open(FCE_BRUT, "wt", encoding="utf-8") as g:
                json.dump({"jugadors": sortida}, g, ensure_ascii=False, separators=(",", ":"))
            print("FCE:", len(sortida), "jugadors baixats")
            return sortida
        except Exception as e:
            ultim = e
            print("FCE: intent", i + 1, "fallit:", e)
            time.sleep(5 * (i + 1))
    raise ultim


def nom_visible(n):
    """«Cognom Cognom, Nom» -> «Nom Cognom Cognom»."""
    if "," in n:
        c, p = n.split(",", 1)
        return (p.strip() + " " + c.strip()).strip()
    return n.strip()


def main():
    fide = baixa_fide() if "--fide" in sys.argv else (json.load(gzip.open(BRUT, "rt", encoding="utf-8"))["jugadors"] if os.path.exists(BRUT) else [])
    fce = baixa_fce() if "--fce" in sys.argv else (json.load(gzip.open(FCE_BRUT, "rt", encoding="utf-8"))["jugadors"] if os.path.exists(FCE_BRUT) else [])
    per_id, llista = {}, []
    for x in fide:
        d = {"n": nom_visible(x["n"]), "f": x["f"], "_tk": tokens(x["n"]), "_cog": x["n"].split(",")[0]}
        for k in ("s", "t"):
            if x.get(k):
                d[k] = x[k]
        for k in ("e", "er", "eb", "y"):
            if x.get(k):
                d[k] = x[k]
        per_id[x["f"]] = d
        llista.append(d)
    per_tokens = {}
    for d in llista:
        for t in d["_tk"]:
            per_tokens.setdefault(t, []).append(d)

    def troba(nom, elo_fide=0):
        tk = tokens(nom)
        if not tk:
            return None
        cand = per_tokens.get(next(iter(sorted(tk, key=lambda t: len(per_tokens.get(t, [])))), ""), [])
        cand = [d for d in cand if tk <= d["_tk"]]
        if len(cand) > 1 and elo_fide:
            c2 = [d for d in cand if d.get("e") == elo_fide]
            cand = c2 or cand
        return cand[0] if len(cand) == 1 else None

    sense_id = {}  # jugadors que no són a FIDE (o no els hem pogut lligar)

    def per_nom(nom):
        k = " ".join(sorted(norm(nom).split()))
        return sense_id.setdefault(k, {"n": nom})

    # 0) Elo FCE de tots els jugadors federats a Catalunya (la FCE no dona l'ID FIDE: es lliga pel nom)
    def troba_fce(nom):
        d = troba(nom)
        if d:
            return d
        cog, _, pre = nom.partition(",")
        ct, ft = tokens(cog), tokens(pre)
        if not ct or not ft:
            return None
        cand = per_tokens.get(next(iter(sorted(ct, key=lambda t: len(per_tokens.get(t, [])))), ""), [])
        cand = [x for x in cand if ct <= x["_tk"] and any(a[:3] == b[:3] for a in ft for b in (x["_tk"] - ct))]
        return cand[0] if len(cand) == 1 else None

    fce_lligats = fce_sols = 0
    for x in fce:
        d = troba_fce(x["n"])
        if d:
            fce_lligats += 1
        else:
            d = per_nom(nom_visible(x["n"]))
            fce_sols += 1
        if x.get("e"):
            d["c"] = x["e"]
        if x.get("er"):
            d["cr"] = x["er"]
        if x.get("s") and not d.get("s"):
            d["s"] = x["s"]
        if x.get("cl") and not d.get("cl"):
            d["cl"] = x["cl"].title()
    if fce:
        print("FCE: %d lligats amb FIDE, %d només FCE" % (fce_lligats, fce_sols))
    # 1) jugadors dels resultats importats: club i Elo FCE (segons el ritme del torneig)
    for fitxer in sorted(glob.glob(os.path.join(ARREL, "data/resultats/*.json"))):
        try:
            r = json.load(open(fitxer, encoding="utf-8"))
            lst = r["jugadors"]
        except Exception:
            continue
        b = os.path.basename(fitxer)
        ritme = "rapid" if "rapides" in b else ("std" if "obert" in b else "")
        for x in lst:
            if not x.get("nom"):
                continue
            d = troba(x["nom"], int0(x.get("fide")) if ritme == "std" else 0) or per_nom(x["nom"])
            for k, kk in (("s", "sexe"), ("t", "titol")):
                if x.get(kk) and not d.get(k):
                    d[k] = x[kk]
            if x.get("club"):
                d["cl"] = x["club"]
            if x.get("elo") and ritme:
                d["c" if ritme == "std" else "cr"] = int(x["elo"])
            if x.get("fide") and not d.get("f") and ritme:
                d["e" if ritme == "std" else "er"] = int(x["fide"])
    # 2) socis del club: ID FIDE, Elo FCE i FIDE
    for j in llegeix("data/jugadors.json")["jugadors"]:
        d = per_id.get(str(j.get("fide") or "")) or troba(j.get("nom") or "") or per_nom(j["nom"])
        if d.get("_tk"):
            # té registre FIDE: es mostra el nom complet de FIDE (dos cognoms) i el nom curt del club queda cercable
            if norm(d["n"]) != norm(j["nom"]):
                d["a"] = j["nom"]
        else:
            d["n"] = j["nom"]
        d["_cog"] = d.get("_cog") or j["nom"]
        d["soci"] = 1
        d["cl"] = "Vilafranca"
        if j.get("fide"):
            d["f"] = str(j["fide"])
        if j.get("sexe"):
            d["s"] = j["sexe"]
        if j.get("elo"):
            d["c"] = int(j["elo"])
        if j.get("elo_rapid"):
            d["cr"] = int(j["elo_rapid"])
        if j.get("elo_fide") and not d.get("e"):
            d["e"] = int(j["elo_fide"])
        if j.get("elo_fide_rapid") and not d.get("er"):
            d["er"] = int(j["elo_fide_rapid"])
    tot = llista + list(sense_id.values())
    # un fitxer per lletra: cada jugador va a la lletra de cadascun dels seus cognoms (el navegador només baixa les lletres que cerques)
    ORDRE = ["f", "n", "s", "t", "e", "er", "eb", "y", "c", "cr", "soci", "cl", "a"]
    trossos = {}
    for d in tot:
        nom_orig = d.get("_cog") or d["n"]
        inicials = {(t[0] if t[0].isalpha() else "_") for t in norm(nom_orig).split()}
        fila = [d.get(k, 0 if k in ("e", "er", "eb", "y", "c", "cr", "soci") else "") for k in ORDRE]
        for ini in inicials:
            trossos.setdefault(ini, []).append(fila)
    os.makedirs(SORTIDA, exist_ok=True)
    for f in glob.glob(os.path.join(SORTIDA, "*.json")):
        os.remove(f)
    for ini, files in trossos.items():
        files.sort(key=lambda r: norm(r[1]))
        with open(os.path.join(SORTIDA, ini + ".json"), "w", encoding="utf-8") as f:
            json.dump({"c": ORDRE, "j": files}, f, ensure_ascii=False, separators=(",", ":"))
    with open(os.path.join(ARREL, "data/inscripcio-index.json"), "w", encoding="utf-8") as f:
        json.dump({"actualitzat": datetime.now(timezone.utc).strftime("%Y-%m-%d"), "font": "FIDE (Espanya) + socis i resultats del club", "lletres": sorted(trossos)}, f, ensure_ascii=False)
    print(len(tot), "jugadors;", sum(1 for d in tot if d.get("y")), "amb any de naixement;", sum(1 for d in tot if d.get("soci")), "socis;", len(trossos), "fitxers")


if __name__ == "__main__":
    main()
