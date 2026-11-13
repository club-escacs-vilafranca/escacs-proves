#!/usr/bin/env python3
"""Resultats dels jugadors del club a Info64 (info64.org, la plataforma de la FEDA: Campionats d'Espanya, oberts, etc.) -> data/info64-jugadors.json.
Cerca cada jugador pel cognom, es queda amb els torneigs des de la data `des` (per defecte l'1 de gener de l'any en curs) i confirma que és la mateixa
persona pel codi FIDE de la seva fitxa. Info64 ja dona la variació d'Elo FIDE de cada partida, i s'aprofita tal com ve.
Necessita un navegador real (Playwright). Ús: python3 tools/info64.py [des]"""
import json, os, re, sys, time, unicodedata
from datetime import datetime, timedelta, timezone
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

sys.path.insert(0, os.path.dirname(__file__))
from importar_chessresults import nom_public

BASE = "https://info64.org"
_ARGS = [a for a in sys.argv[1:] if not a.startswith("--")]
DES = _ARGS[0] if _ARGS else f"{datetime.now().year}-01-01"
SEGUIMENT = "--seguiment" in sys.argv      # només torna a mirar els jugadors amb un torneig encara en curs (o acabat ahir); no cerca torneigs nous
PENDENTS = "--pendents" in sys.argv        # només diu quants jugadors tenen un torneig en curs (per saber si val la pena obrir el navegador)
SORTIDA = "data/info64-jugadors.json"
VERSIO = 3          # puja-la quan canviï el format: força tornar a llegir els torneigs ja acabats
TITOLS = re.compile(r"^(?:GM|IM|FM|CM|WGM|WIM|WFM|WCM|NM)\s+")


def sa(t):
    return re.sub(r"[^a-z0-9]+", " ", unicodedata.normalize("NFKD", t or "").encode("ascii", "ignore").decode().lower()).strip()


def num(x):
    x = (x or "").strip().replace(",", ".")
    try:
        return float(x)
    except ValueError:
        return None


def res(x):
    x = (x or "").strip()
    return {"1": "1", "1.0": "1", "0": "0", "0.0": "0", "0.5": "½", "½": "½", "+": "+", "-": "-"}.get(x.replace(",", "."), "")


def nom_torneig(n):
    """Campionats d'Espanya d'edats: un sol torneig per als lents i un altre per als ràpids, amb un grup per edat (Sub-12...)."""
    m = re.match(r"^\s*(?:CE|CAMPEONATO\s+DE\s+ESPA[ÑN]A)\b(.*)$", n or "", re.I)
    if not m:
        return (n or "").strip()
    resta = m.group(1)
    sub = re.search(r"\bsub[\s-]*0*(\d+)\b", resta, re.I)
    if not sub:
        return (n or "").strip()
    rapid = bool(re.search(r"r[aá]pid|blitz|relampago|relámpago", resta, re.I))
    any_ = re.search(r"\b(20\d\d)\b", resta)
    base = "Campeonato de España" + (" Rápido" if rapid else "")
    return f"{base} {any_.group(1) if any_ else ''} Sub-{int(sub.group(1))}".replace("  ", " ").strip()


def punts_txt(x):
    v = num(x)
    return "" if v is None else (str(int(v)) if v == int(v) else str(v))


def dates_rondes(inici, fi, n):
    """Info64 no dona la data de cada ronda a la fitxa: es reparteixen entre l'inici i el final del torneig (aproximat)."""
    try:
        a, b = datetime.strptime(inici, "%Y-%m-%d"), datetime.strptime(fi, "%Y-%m-%d")
    except Exception:
        return {}
    dies = (b - a).days
    return {r: (a + __import__("datetime").timedelta(days=round(dies * (r - 1) / max(n - 1, 1)))).strftime("%Y-%m-%d") for r in range(1, n + 1)}


def modalitat(n):
    n = sa(n)
    return "Blitz" if re.search(r"blitz|relampago|llampec", n) else "Rapid" if re.search(r"rapid|actius|rapides", n) else "Standard"


def carrega(pg, url, espera=5000):
    pg.goto(BASE + url, wait_until="domcontentloaded", timeout=90000)
    pg.wait_for_timeout(espera)
    return BeautifulSoup(pg.content(), "html.parser")


def cerca(pg, cognoms):
    """Files de la cerca de jugadors: [{nom, torneig, inici, fi, href_jugador, href_torneig}]."""
    s = carrega(pg, "/search-player?hl=ca&name=" + cognoms.replace(" ", "+"), 3000)
    out = []
    for tr in s.select("table tbody tr"):
        td = tr.select("td")
        if len(td) < 6:
            continue
        a1, a2 = td[1].select_one("a"), td[3].select_one("a")
        if not a1 or not a2:
            continue
        out.append({"nom": td[1].get_text(" ", strip=True), "torneig": td[3].get_text(" ", strip=True), "inici": td[4].get_text(strip=True),
                    "fi": td[5].get_text(strip=True), "href": a1["href"], "href_t": a2["href"]})
    return out


def fitxa(pg, href):
    """Fitxa d'un jugador en un torneig: dades generals i partides amb la variació FIDE que dona Info64."""
    s = carrega(pg, href + "?hl=ca", 3000)
    d = {}
    for tr in s.select("table")[0].select("tr") if s.select("table") else []:
        if tr.th and tr.td:
            d[tr.th.get_text(" ", strip=True)] = tr.td.get_text(" ", strip=True)
    elo, fide = None, ""
    m = re.match(r"(\d+)?\s*(\d{5,10})?", d.get("ELO FIDE", ""))
    if m:
        elo, fide = (int(m.group(1)) if m.group(1) else None), (m.group(2) or "")
    var = next((num(v) for k, v in d.items() if k.lower().startswith(("variació fide", "variacion fide", "fide variation", "fide rating"))), None)
    k = next((int(re.search(r"K=(\d+)", kk).group(1)) for kk in d if re.search(r"K=(\d+)", kk)), None)
    partides = []
    tb = s.select_one("#player-results")
    for tr in (tb.select("tbody tr") if tb else []):
        c = [x.get_text(" ", strip=True) for x in tr.select("td")]
        if len(c) < 10 or not c[0].isdigit():
            continue
        nom_f = c[4]
        m2 = re.match(r"(.*?)\s+(\d{4,10})$", nom_f)
        nom_r, fid_r = (m2.group(1), m2.group(2)) if m2 else (nom_f, "")
        nom_r = TITOLS.sub("", nom_r.strip())
        cls = tr.select("td")[2].get("class") or []
        color = "w" if "white" in cls else "s" if "black" in cls else ""
        r_ = res(c[8])
        if not nom_r or not r_:
            continue
        v = num(c[9])
        g = {"ronda": int(c[0]), "rival": nom_public(nom_r) if "," in nom_r else nom_r, "rtg_i": int(c[6]) if c[6].isdigit() else None, "bo": int(c[1]) if c[1].isdigit() else None,
             "color": color, "res": r_, "club": c[5], "fid": ""}
        if v is not None and elo and c[6].isdigit() and r_ in ("1", "0", "½"):
            g["fide"] = {"d": v, "k": k or 40, "r": elo, "opp": int(c[6])}
        partides.append(g)
    return {"nom": d.get("Nom", ""), "fide": fide, "elo": elo, "lloc": int(d["Classificació final"]) if d.get("Classificació final", "").isdigit() else None,
            "punts": d.get("Punts", ""), "var": var, "k": k, "partides": partides,
            "titol": (s.select_one("h1").get_text(" ", strip=True) if s.select_one("h1") else ""),
            "lloc_dates": next((p.get_text(" ", strip=True) for p in s.select("h1 ~ *") if re.search(r"\d\d/\d\d/\d{4}", p.get_text()) and len(p.get_text()) < 150), "")}


def calendari_rondes(pg, href_t):
    """Data de cada ronda segons la pàgina de calendari del torneig (/schedule): {ronda: 'AAAA-MM-DD'}."""
    try:
        s = carrega(pg, href_t + "/schedule?hl=ca", 3000)
    except Exception:
        return {}
    out = {}
    for tr in s.select("table tr"):
        a, c = tr.select_one("a"), [x.get_text(" ", strip=True) for x in tr.select("td")]
        m = re.search(r"(\d+)\s*$", a.get_text(" ", strip=True)) if a else None
        d = next((re.search(r"\d{4}-\d\d-\d\d", x) for x in c if re.search(r"\d{4}-\d\d-\d\d", x)), None)
        if m and d:
            out[int(m.group(1))] = d.group(0)
    return out


def participants(pg, href_t):
    s = carrega(pg, href_t + "/standings?hl=ca", 3000)
    tb = next((t for t in s.select("table") if t.select("tbody tr")), None)
    return len(tb.select("tbody tr")) if tb else None


def main():
    club = json.load(open("data/jugadors.json", encoding="utf-8"))["jugadors"]
    antic = {}
    if os.path.exists(SORTIDA):
        antic = {(r["fide"] or r["jugador"], r["tnr"]): r for r in json.load(open(SORTIDA, encoding="utf-8")).get("resultats", [])}
    resultats, noms_cercats, part_cache, cal_cache = [], {}, {}, {}
    inici = time.time()
    ahir = (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%d")
    en_curs = {k[0] for k, r in antic.items() if r.get("fi", "0") >= ahir}
    if PENDENTS:
        print(len([j for j in club if (j["fide"] or j["nom"]) in en_curs]))
        return
    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page()
        for j in club:
            if time.time() - inici > 50 * 60:
                print("Límit de temps: es completa a la propera execució")
                break
            if SEGUIMENT and (j["fide"] or j["nom"]) not in en_curs:
                resultats += [r for k, r in antic.items() if k[0] == (j["fide"] or j["nom"]) and r.get("fi", "0") >= DES]   # res de nou: es conserva
                continue
            cog = (j["nom_cr"].split(",")[0]).strip()
            clau = sa(cog)
            if clau not in noms_cercats:
                try:
                    noms_cercats[clau] = cerca(pg, clau)
                except Exception as e:
                    print("  cerca fallida", clau, str(e)[:100])
                    noms_cercats[clau] = []
            nom_ok = sa(j["nom_cr"].replace(",", " "))
            for f in noms_cercats[clau]:
                if f["fi"] < DES or sa(f["nom"].replace(",", " ")) != nom_ok or re.search(r"tecnificaci", f["torneig"], re.I):
                    continue                              # les concentracions de tecnificació són entrenaments, no torneigs
                tnr = "i64-" + f["href_t"].strip("/")
                k = (j["fide"] or j["nom"], tnr)
                if k in antic and antic[k].get("v") == VERSIO and antic[k].get("fi", "9") < (datetime.now(timezone.utc).strftime("%Y-%m-%d")):
                    resultats.append(antic[k])            # un torneig acabat no canvia
                    continue
                try:
                    d = fitxa(pg, f["href"])
                    if j["fide"] and d["fide"] and d["fide"] != j["fide"]:
                        continue                          # un homònim
                    if not any(g["res"] in ("1", "0", "½") for g in d["partides"]):
                        continue                          # cap partida jugada de veritat (incompareixences)
                    mx = max(g["ronda"] for g in d["partides"])
                    if f["href_t"] not in cal_cache:
                        cal_cache[f["href_t"]] = calendari_rondes(pg, f["href_t"])
                    dr = {**dates_rondes(f["inici"], f["fi"], mx), **cal_cache[f["href_t"]]}
                    for g in d["partides"]:
                        g["data"] = dr.get(g["ronda"], f["fi"])
                    if f["href_t"] not in part_cache:
                        part_cache[f["href_t"]] = participants(pg, f["href_t"])
                    resultats.append({"jugador": j["nom"], "fide": j["fide"], "font": "info64", "v": VERSIO, "tnr": tnr, "snr": None, "torneig": nom_torneig(f["torneig"]), "fi": f["fi"],
                                      "inici": f["inici"], "club": "", "fed": "ESP", "lloc": d["lloc"], "rondes": len(d["partides"]), "de": part_cache[f["href_t"]],
                                      "url": BASE + f["href_t"], "punts": punts_txt(d["punts"]), "modalitat": modalitat(f["torneig"]), "rtg_i": d["elo"],
                                      "elo_fide": {"var": d["var"], "k": d["k"]} if d["var"] is not None else None, "partides": d["partides"]})
                    print("  ", j["nom"], "-", f["torneig"], len(d["partides"]), "partides")
                except Exception as e:
                    print("  error", j["nom"], f["torneig"], str(e)[:100])
        b.close()
    # Si una cerca falla o no torna res (la web d'Info64 canvia o no respon), no es perden els resultats que ja teníem
    tenim = {(r["fide"] or r["jugador"], r["tnr"]) for r in resultats}
    conservats = [r for k, r in antic.items() if k not in tenim and r.get("v") == VERSIO and r.get("fi", "0") >= DES]
    if conservats:
        print(f"Es conserven {len(conservats)} resultats anteriors que no s'han tornat a llegir")
        resultats += conservats
    if not resultats and not antic:
        print("Cap resultat: no es toca el fitxer.")
        return
    resultats.sort(key=lambda r: (r["fi"], r["jugador"]), reverse=True)
    json.dump({"actualitzat": datetime.now(timezone.utc).isoformat(timespec="seconds"), "des": DES, "resultats": resultats}, open(SORTIDA, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(len(resultats), "resultats d'Info64")


if __name__ == "__main__":
    main()
