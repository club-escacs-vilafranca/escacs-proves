#!/usr/bin/env python3
"""Resultats dels jugadors del club a Vesus (vesus.org, plataforma italiana) -> data/vesus-jugadors.json.
Només mira endavant: els esdeveniments «en curs» i els «propers» (mai l'arxiu). Per a cada torneig obre la pàgina, mira si hi ha jugadors ESP, descarta els
jugadors que no són del club (nom) i confirma que són la mateixa persona pel codi FIDE de la seva fitxa. Les partides surten amb el rival, el seu Elo i el
resultat; la variació FIDE la calcula aquest script (la de Vesus es desa només com a control: `var_vesus`).
Els torneigs que ja arriben per Chess-Results (ritmes lents) es descarten en integrar-los al pas comú; aquí interessen els que no hi són (p. ex. el blitz).
Ús: python3 tools/vesus.py [--torneigs id1,id2]   (per provar amb torneigs concrets, inclosos els ja acabats)"""
import json, os, re, sys, time, unicodedata
from datetime import datetime, timezone
from playwright.sync_api import sync_playwright

BASE = "https://vesus.org"
SORTIDA = "data/vesus-jugadors.json"
VERSIO = 1
LIMIT_TEMPS = int(os.environ.get("VESUS_LIMIT", 14 * 60))     # segons de feina com a màxim (el workflow talla als 20 min)
TITOLS = {"GM", "IM", "FM", "CM", "WGM", "WIM", "WFM", "WCM", "CN", "1N", "2N", "3N", "NM"}
RITMES = {"Blitz": "Blitz", "Rapid": "Rapid", "Standard": "Standard", "Bullet": "Bullet"}


def sa(t):
    return re.sub(r"[^a-z0-9]+", " ", unicodedata.normalize("NFKD", t or "").encode("ascii", "ignore").decode().lower()).strip()


def nom_public(cr):
    if "," not in cr:
        return cr.strip()
    cog, nom = [x.strip() for x in cr.split(",", 1)]
    return f"{nom.title()} {cog.title()}"


def linies(pg):
    return [l.strip() for l in pg.evaluate("() => document.body.innerText").split("\n") if l.strip()]


def carrega(pg, url, espera=3500):
    pg.goto(url, wait_until="networkidle", timeout=60000)
    pg.wait_for_timeout(espera)


def torneigs_llista(pg, url):
    """Identificadors dels torneigs d'un llistat (en curs / propers); Vesus enllaça cada torneig, no l'esdeveniment."""
    pg.goto(url, wait_until="networkidle", timeout=60000); pg.wait_for_timeout(3000)
    return pg.evaluate("() => [...new Set([...document.querySelectorAll('a[href^=\"/tournament/\"]')].map(a => a.getAttribute('href').split('/')[2].split('?')[0]))]")


def k_fide(elo, any_naix):
    if any_naix and datetime.now().year - any_naix < 18 and elo < 2300:
        return 40
    return 10 if elo >= 2400 else 20


def delta(r, opp, res, k):
    s = {"1": 1.0, "½": 0.5, "0": 0.0}[res]
    we = 1 / (1 + 10 ** ((opp - r) / 400))
    return round(k * (s - we), 1)


def pagina_jugador(pg, href):
    carrega(pg, BASE + href, 3500)
    L = linies(pg)
    d = {}
    for i, l in enumerate(L):
        if l.endswith(":") and i + 1 < len(L):
            d[l[:-1]] = L[i + 1]
    capcalera = []
    for i, l in enumerate(L):
        if l == "DETAILS":
            capcalera = L[max(0, i - 12):i]
            break
    ritme = next((RITMES[c] for c in capcalera if c in RITMES), "")
    dates = re.findall(r"\d\d/\d\d/\d{4}", " ".join(capcalera))
    iso = lambda s: s[6:] + "-" + s[3:5] + "-" + s[:2]
    h1 = pg.evaluate("() => (document.querySelector('h1,h2') || {}).innerText || ''").strip()
    # partides: files després de «Pairings»; Rd., Res., Num., [títol], Nom, Fed, Rtg., Pts., Pos., Rtg.P.
    try:
        i0 = L.index("Rtg.P.", L.index("Pairings")) + 1
    except ValueError:
        i0 = len(L)
    fi_ = next((i for i in range(i0, len(L)) if L[i].startswith(("Privacy", "New · Official"))), len(L))
    tok = L[i0:fi_]
    files, cur = [], []
    # cada fila comença amb el número de ronda; amb Res. a continuació (0, 1, ½, +, -)
    for t in tok:
        cur.append(t)
        if len(cur) >= 4 and re.fullmatch(r"[A-Z]{3}", cur[-5] if len(cur) >= 5 else "") and re.fullmatch(r"\d+(\.\d+)?|½", cur[-3]) and re.fullmatch(r"\d+", cur[-2]) and re.fullmatch(r"\d+", cur[-1]):
            files.append(cur); cur = []
    noms = []
    for c in capcalera:
        if re.match(r"\d\d/\d\d/\d{4}", c):
            break
        if c in ("CONTACTS", "SUPPORT") or c.isdigit() or c.startswith("Photo:"):
            continue
        noms.append(c)
    return {"meta": d, "ritme": ritme, "noms": noms, "dates": [iso(x) for x in dates[:2]], "titol_pag": h1, "capcalera": capcalera, "files": files, "resta": cur}


def partides_de(files):
    # Vesus dona 1399 als jugadors sense Elo (valor per defecte): no és un Elo real i no s'usa per calcular la variació
    out = []
    for f in files:
        try:
            rd, res = int(f[0]), f[1]
            fed, rtg = f[-5], f[-4]
            nom = f[-6]
            if res not in ("1", "0", "½"):
                out.append({"ronda": rd, "res": res, "rival": "", "inc": True, "brut": f})
                continue
            out.append({"ronda": rd, "rival": nom_public(nom) if "," in nom else nom, "rtg_i": int(rtg) if rtg.isdigit() and rtg != "1399" else None, "res": res, "club": fed, "fid": "", "color": "", "num_rival": f[2]})
        except Exception:
            out.append({"ronda": None, "brut": f})
    return out


def main():
    arg = next((a for a in sys.argv[1:] if a.startswith("--torneigs")), None)
    forcats = (sys.argv[sys.argv.index(arg) + 1] if arg == "--torneigs" else arg.split("=", 1)[1]).split(",") if arg else None
    club = json.load(open("data/jugadors.json", encoding="utf-8"))["jugadors"]
    club = [x for x in club if x.get("fide")]
    per_nom = {}
    for j in club:
        per_nom.setdefault(frozenset(sa(j["nom_cr"]).split()), j)
    fides = {j["fide"]: j for j in club if j.get("fide")}

    def club_per_nom(nom_v):
        tk = set(sa(nom_v).split())
        if frozenset(tk) in per_nom:
            return per_nom[frozenset(tk)]
        return next((j for k, j in per_nom.items() if len(tk) >= 2 and tk <= k), None)

    resultats, previs, vistos = [], [], []
    MAX_PROPERS = int(os.environ.get("VESUS_MAX_PROPERS", "60"))
    inici_t = time.time()
    try:
        ant = json.load(open(SORTIDA, encoding="utf-8"))
    except Exception:
        ant = {}
    fallades, aturat = 0, False          # salvaguarda: 5 errors seguits = no es consulta res més
    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page(user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36")
        en_curs = forcats or torneigs_llista(pg, BASE + "/inprogress")
        propers = [] if forcats else [t for t in torneigs_llista(pg, BASE + "/") if t not in en_curs][:MAX_PROPERS]
        # els propers on ja teníem jugadors inscrits en l'execució anterior es llegeixen ara com a torneigs normals (poden haver començat o acabat des d'aleshores)
        extres = [] if forcats else [t for t in dict.fromkeys(p["torneig"] for p in ant.get("previs", [])) if t not in en_curs]
        sense_nostres = set(ant.get("sense_nostres", []))      # torneigs en curs sense cap jugador d'Espanya: no tornen a canviar
        en_curs = [t for t in en_curs if t not in sense_nostres]
        propers = [t for t in propers if t not in extres]
        print(f"Vesus: {len(en_curs)} torneigs en curs, {len(extres)} anteriorment propers, {len(propers)} de propers")
        for tid, futur in [(t, False) for t in en_curs + extres] + [(t, True) for t in propers]:
            if time.time() - inici_t > LIMIT_TEMPS:
                print(f"Límit de temps ({LIMIT_TEMPS // 60} min): es completa a la propera execució")
                aturat = True
                break
            if fallades >= 5:
                print("Vesus no respon (5 errors seguits): no es consulta res més; es conserva el que hi havia")
                aturat = True
                break
            try:
                pg.goto(f"{BASE}/tournament/{tid}", wait_until="domcontentloaded", timeout=60000); pg.wait_for_timeout(5000)
                L = linies(pg)
                fallades = 0
                if "ESP" not in L:
                    vistos.append(tid)
                    if not futur:
                        sense_nostres.add(tid)
                    continue
                links = pg.evaluate("() => [...document.querySelectorAll('a[href*=\"rankedId=\"]')].map(a => [a.getAttribute('href'), a.innerText.trim()])")
                trobats = {}
                for i, l in enumerate(L):
                    if l == "ESP":
                        for c in (L[i - 1], L[i + 1] if i + 1 < len(L) else "", L[i - 2], L[i + 2] if i + 2 < len(L) else ""):
                            if "," in c and club_per_nom(c):
                                trobats[c] = club_per_nom(c); break
                for nm, j in trobats.items():
                    href = next((h for h, t in links if t == nm), None)
                    if not href:
                        print(f"  {tid}: «{nm}» sense enllaç a la fitxa", flush=True); continue
                    if futur:
                        previs.append({"torneig": tid, "jugador": nom_public(j["nom_cr"]), "fide": j.get("fide"), "url": f"{BASE}/tournament/{tid}"})
                        continue
                    f = pagina_jugador(pg, href)
                    m = f["meta"]
                    fide = re.sub(r"\D", "", m.get("Fide Id", ""))
                    if not fide or fide != str(j.get("fide") or ""):
                        print(f"  {tid}: «{nm}» no coincideix en FIDE ({fide} ≠ {j.get('fide')}); descartat"); continue
                    rtg = int(m["Rating"]) if m.get("Rating", "").isdigit() else None
                    any_n = int(m["Year"]) if m.get("Year", "").isdigit() else None
                    k = k_fide(rtg or 0, any_n)
                    parts = partides_de(f["files"])
                    tot = 0.0
                    for g in parts:
                        if rtg and g.get("rtg_i") and g.get("res") in ("1", "0", "½"):
                            g["fide"] = {"d": delta(rtg, g["rtg_i"], g["res"], k), "k": k, "r": rtg, "opp": g["rtg_i"]}
                            tot += g["fide"]["d"]
                    ini, fi = (f["dates"] + ["", ""])[:2] if f["dates"] else ("", "")
                    nom_t = " · ".join(x for x in f["noms"] if x)
                    resultats.append({"jugador": nom_public(j["nom_cr"]), "fide": fide, "font": "vesus", "v": VERSIO, "tnr": f"vesus-{tid}",
                                      "snr": None, "torneig": nom_t, "fi": fi or "", "inici": ini or None, "club": "", "fed": "ESP",
                                      "lloc": int(m["Position"]) if m.get("Position", "").isdigit() else None, "rondes": len([g for g in parts if g.get("ronda")]), "de": len(links) or None,
                                      "url": f"{BASE}/tournament/{tid}", "punts": m.get("Points", ""), "modalitat": f["ritme"], "rtg_i": rtg,
                                      "elo_fide": {"var": round(tot, 1), "k": k}, "var_vesus": m.get("Rating change"), "partides": parts})
                    print(f"  {tid}: {nom_public(j['nom_cr'])} · {nom_t} · {m.get('Points')} pts · {len(parts)} partides · var {round(tot, 1)} (Vesus {m.get('Rating change')}) · ritme {f['ritme']} · {f['dates']}", flush=True)
                vistos.append(tid)
            except Exception as e:
                print(f"  {tid}: error {type(e).__name__}: {str(e)[:150]}", flush=True)
                fallades += 1
        b.close()
    # el que no s'ha tornat a llegir es conserva: resultats de torneigs ja acabats (no surten a «en curs») i propers que encara no s'han pogut revisar
    nous = {r["tnr"] for r in resultats}
    any_ = datetime.now(timezone.utc).strftime("%Y")
    resultats += [r for r in ant.get("resultats", []) if r["tnr"] not in nous and (r.get("fi") or any_)[:4] >= any_]
    llegits = set(vistos) | {r["tnr"].replace("vesus-", "") for r in resultats}
    previs += [p for p in ant.get("previs", []) if p["torneig"] not in {x["torneig"] for x in previs} and (aturat or p["torneig"] not in llegits)]
    os.makedirs("data", exist_ok=True)
    json.dump({"actualitzat": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%MZ"), "resultats": resultats, "previs": previs, "sense_nostres": sorted(sense_nostres)}, open(SORTIDA, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"Vesus: {len(resultats)} resultats i {len(previs)} inscripcions properes ({len(vistos)} esdeveniments mirats)")


if __name__ == "__main__":
    main()
