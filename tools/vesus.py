#!/usr/bin/env python3
"""Resultats dels jugadors del club a Vesus (vesus.org, plataforma italiana) -> data/vesus-jugadors.json.
Només mira endavant: els esdeveniments «en curs» i els «propers» (mai l'arxiu). Per a cada esdeveniment obre el resum de la federació ESP, descarta els
jugadors que no són del club (nom) i confirma que són la mateixa persona pel codi FIDE de la seva fitxa. Les partides surten amb el rival, el seu Elo i el
resultat; la variació FIDE la calcula aquest script (la de Vesus es desa només com a control: `var_vesus`).
Els torneigs que ja arriben per Chess-Results (ritmes lents) es descarten en integrar-los al pas comú; aquí interessen els que no hi són (p. ex. el blitz).
Ús: python3 tools/vesus.py [--esdeveniments id1,id2]   (per provar amb esdeveniments concrets, inclosos els ja acabats)"""
import json, os, re, sys, unicodedata
from datetime import datetime, timezone
from playwright.sync_api import sync_playwright

BASE = "https://vesus.org"
SORTIDA = "data/vesus-jugadors.json"
VERSIO = 1
TITOLS = {"GM", "IM", "FM", "CM", "WGM", "WIM", "WFM", "WCM", "CN", "1N", "2N", "3N", "NM"}
RITMES = {"Blitz": "Blitz", "Rapid": "Ràpid", "Standard": "Standard", "Bullet": "Bullet"}


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


def events_llista(pg, url):
    carrega(pg, url)
    return pg.evaluate("() => [...new Set([...document.querySelectorAll('a[href^=\"/event/\"]')].map(a => a.getAttribute('href').split('/')[2]))]")


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
    return {"meta": d, "ritme": ritme, "dates": [iso(x) for x in dates[:2]], "titol_pag": h1, "capcalera": capcalera, "files": files, "resta": cur}


def partides_de(files):
    out = []
    for f in files:
        try:
            rd, res = int(f[0]), f[1]
            fed, rtg = f[-5], f[-4]
            nom = f[-6]
            if res not in ("1", "0", "½"):
                out.append({"ronda": rd, "res": res, "rival": "", "inc": True, "brut": f})
                continue
            out.append({"ronda": rd, "rival": nom_public(nom) if "," in nom else nom, "rtg_i": int(rtg) if rtg.isdigit() else None, "res": res, "club": fed, "fid": "", "color": "", "num_rival": f[2]})
        except Exception:
            out.append({"ronda": None, "brut": f})
    return out


def main():
    arg = next((a for a in sys.argv[1:] if a.startswith("--esdeveniments")), None)
    forcats = (sys.argv[sys.argv.index(arg) + 1] if arg == "--esdeveniments" else arg.split("=", 1)[1]).split(",") if arg else None
    club = json.load(open("data/jugadors.json", encoding="utf-8"))["jugadors"]
    if os.environ.get("NOMES_PROVA"):
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
    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page(user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36")
        en_curs = forcats or events_llista(pg, BASE + "/inprogress")
        propers = [] if forcats else [e for e in events_llista(pg, BASE + "/") if e not in en_curs]
        print(f"Vesus: {len(en_curs)} esdeveniments en curs, {len(propers)} de propers")
        for ev, futur in [(e, False) for e in en_curs] + [(e, True) for e in propers]:
            try:
                carrega(pg, f"{BASE}/event/{ev}/federationSummary?federation=ESP", 3000)
                L = linies(pg)
                nom_ev = next((L[i + 1] for i, l in enumerate(L) if l == "Wear your way of living chess."), "")
                # l'esdeveniment és el primer títol després del menú; es llegeix millor de la capçalera
                cap = pg.evaluate("() => { const h = document.querySelector('h1,h2'); return h ? h.innerText : ''; }").strip()
                nom_ev = cap or nom_ev
                links = pg.evaluate("() => [...document.querySelectorAll('a[href*=\"rankedId=\"]')].map(a => a.getAttribute('href'))")
                # seccions: nom del torneig = línia abans de «UNFOLD ALL»/«FOLD ALL»; jugadors = el text abans de «ESP»
                jug = []   # (torneig, nom)
                sec = ""
                for i, l in enumerate(L):
                    if i + 1 < len(L) and L[i + 1] in ("UNFOLD ALL", "FOLD ALL"):
                        sec = l
                    if l == "ESP" and i > 0:
                        nm = L[i - 1]
                        if nm in TITOLS and i > 1:
                            nm = L[i - 2]
                        jug.append((sec, nm))
                if len(jug) != len(links):
                    print(f"  {ev}: {len(jug)} jugadors ESP però {len(links)} enllaços; es fa servir el mínim", flush=True)
                for (sec, nm), href in zip(jug, links):
                    j = club_per_nom(nm)
                    if not j:
                        continue
                    if futur:
                        previs.append({"esdeveniment": ev, "nom_esdeveniment": nom_ev, "torneig": sec, "jugador": nom_public(j["nom_cr"]), "fide": j.get("fide"), "url": f"{BASE}/event/{ev}"})
                        continue
                    f = pagina_jugador(pg, href)
                    m = f["meta"]
                    fide = re.sub(r"\D", "", m.get("Fide Id", ""))
                    if not fide or fide != str(j.get("fide") or ""):
                        print(f"  {ev}: «{nm}» no coincideix en FIDE ({fide} ≠ {j.get('fide')}); descartat")
                        continue
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
                    resultats.append({"jugador": nom_public(j["nom_cr"]), "fide": fide, "font": "vesus", "v": VERSIO, "tnr": f"vesus-{href.split('/')[2].split('?')[0]}",
                                      "snr": None, "torneig": f"{nom_ev} · {sec}" if sec else nom_ev, "fi": fi or "", "inici": ini or None, "club": "", "fed": "ESP",
                                      "lloc": int(m["Position"]) if m.get("Position", "").isdigit() else None, "rondes": len([g for g in parts if g.get("ronda")]), "de": None,
                                      "url": BASE + href.split("?")[0], "punts": m.get("Points", ""), "modalitat": f["ritme"], "rtg_i": rtg,
                                      "elo_fide": {"var": round(tot, 1), "k": k}, "var_vesus": m.get("Rating change"), "partides": parts})
                    print(f"  {ev}: {nom_public(j['nom_cr'])} · {sec} · {m.get('Points')} pts · {len(parts)} partides · var {round(tot, 1)} (Vesus {m.get('Rating change')}) · ritme {f['ritme']} · {f['dates']}", flush=True)
                    if os.environ.get("NOMES_PROVA"):
                        resultats[-1]["_cap"] = f["capcalera"]; resultats[-1]["_titol"] = f["titol_pag"]; resultats[-1]["_resta"] = f["resta"]
                vistos.append(ev)
            except Exception as e:
                print(f"  {ev}: error {type(e).__name__}: {str(e)[:150]}", flush=True)
        b.close()
    os.makedirs("data", exist_ok=True)
    json.dump({"actualitzat": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%MZ"), "resultats": resultats, "previs": previs}, open(SORTIDA, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"Vesus: {len(resultats)} resultats i {len(previs)} inscripcions properes ({len(vistos)} esdeveniments mirats)")


if __name__ == "__main__":
    main()
