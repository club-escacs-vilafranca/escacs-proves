#!/usr/bin/env python3
"""Validesa per a l'Elo (i modalitat) dels tornejos de Chess-Results, i avís dels que no es poden classificar.

Regles automàtiques (cada torneig, per a l'Elo FCE i per a l'Elo FIDE):
  - Minicircuit: no val.
  - Exclusius de la categoria Sub-8 de Catalunya: val per a la FCE però no per a la FIDE (si són del calendari FEDA o FIDE, segueixen aquell calendari).
  - Surt al calendari de la FCE: val per a la FCE i per a la FIDE.
  - Surt al calendari de la FEDA o de la FIDE: val per a la FIDE però no per a la FCE.
  - Qualsevol altre: «?» (no ho sabem).
Cada torneig té un fitxer a data/elo/<tnr>.json (es crea sol, amb aquests valors, i el club el pot canviar al backoffice: filtres per «?», etc.).
Mai no es toca el que el club ja ha marcat. data/elo-compilat.json és el que llegeix la web i el càlcul d'Elo (modalitat).
Dels tornejos que queden amb «?» (validesa o modalitat) i que encara no s'han avisat, es crea UNA incidència de GitHub (que arriba per correu).
Ús: python3 tools/avis_elo.py [--cap-incidencia]   (amb GH_TOKEN a l'entorn i la comanda `gh`)"""
import json, unicodedata, os, re, subprocess, sys, unicodedata

SITE = os.environ.get("SITE_URL", "https://club-escacs-vilafranca.pages.dev")
REPO = os.environ.get("GITHUB_REPOSITORY", "")


def carrega(p, per_defecte):
    try:
        return json.load(open(p, encoding="utf-8"))
    except Exception:
        return per_defecte


def norm(t):
    return re.sub(r"[^a-z0-9 ]", " ", unicodedata.normalize("NFKD", t.lower()).encode("ascii", "ignore").decode())


PARAULES_BUIDES = set("de d del la el les els i per torneig obert open escacs xadrez a en al grup 2026 2025 campionat".split())


def tokens(t):
    return {w for w in norm(t).split() if w not in PARAULES_BUIDES and len(w) > 2 and not re.fullmatch(r"[ivxlc]+", w)}


def calendari():
    ev = []
    for f in ("calendari-oficial", "calendari-altres", "calendari-propi", "calendari-fide"):
        ev += carrega("data/%s.json" % f, {}).get("events", [])
    return ev


def classifica(t, ev):
    nom = t["torneig"].lower()
    if re.search(r"mini[\s-]?circuit", nom):
        return {"fce": "no", "fide": "no", "per": "Minicircuit"}
    a, b = (t.get("inici") or t["fi"])[:10], t["fi"][:10]
    millor = None
    for e in ev:
        s = e.get("sch", {})
        ini, fi = s.get("start"), s.get("end") or s.get("start")
        if not ini or ini > b or (fi or ini) < a:
            continue
        j = len(tokens(t["torneig"]) & tokens(e["name"])) / max(1, len(tokens(t["torneig"]) | tokens(e["name"])))
        if t["tnr"] in (e.get("url") or ""):
            j = 9
        if j >= 0.25 and (not millor or j > millor[0]):
            millor = (j, e)
    src = millor[1].get("source") if millor else None
    if re.search(r"sub[\s-]?8\b", nom) and src not in ("feda", "fide"):      # Sub-8 de Catalunya: FCE sí, FIDE no (els de la FEDA o la FIDE segueixen el seu calendari)
        return {"fce": "si", "fide": "no", "per": "Exclusiu Sub-8"}
    if millor:
        if src == "fce":
            return {"fce": "si", "fide": "si", "per": "Calendari FCE"}
        if src in ("feda", "fide"):
            return {"fce": "no", "fide": "si", "per": "Calendari " + src.upper()}
    return {"fce": "?", "fide": "?", "per": ""}


def tornejos_cr():
    per_tnr = {}
    for r in carrega("data/resultats-jugadors.json", {}).get("resultats", []):
        if r.get("font") not in (None, "chess-results", "info64", "ffe"):      # Chess-Results i Info64 (Mundial, Espanya...)
            continue
        t = per_tnr.setdefault(r["tnr"], {"tnr": r["tnr"], "torneig": r["torneig"], "fi": r["fi"], "inici": r.get("inici"), "url": r.get("url", ""),
                                          "modalitat": r.get("modalitat"), "mod_coneguda": "modalitat_dubtosa" in r, "mod_dubtosa": bool(r.get("modalitat_dubtosa"))})
        t["fi"] = max(t["fi"], r["fi"])
    return per_tnr


# ---- Un fitxer per torneig a data/elo/<tnr>.json (és el que edita el CMS: hi ha filtres i cerca) i un compilat que llegeix la web ----
D_ELO = "data/elo"
D_COMP = "data/elo-compilat.json"


def llegeix_entrades():
    out = {}
    if os.path.isdir(D_ELO):
        for n in sorted(os.listdir(D_ELO)):
            if n.endswith(".json"):
                e = carrega(os.path.join(D_ELO, n), None)
                if e:
                    e["tnr"] = str(e.get("tnr") or n[:-5])
                    out[e["tnr"]] = e
    return out


def desa_entrada(e):
    os.makedirs(D_ELO, exist_ok=True)
    json.dump(e, open(os.path.join(D_ELO, "%s.json" % e["tnr"]), "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    open(os.path.join(D_ELO, "%s.json" % e["tnr"]), "a").write("\n")


def compila():
    """data/elo-compilat.json: el que llegeix la web (tnr, validesa FCE i FIDE, modalitat), a partir dels fitxers de data/elo/."""
    ent = llegeix_entrades()
    llista = [{"tnr": t, "nom": e.get("nom", ""), "fce": e.get("fce") or "auto", "fide": e.get("fide") or "auto", "modalitat": e.get("modalitat") or "auto"}
              for t, e in sorted(ent.items(), key=lambda a: (a[1].get("data", ""), a[0]), reverse=True)]
    json.dump({"tornejos": llista}, open(D_COMP, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    return ent


def migra_antic(tornejos):
    """Primer cop: passa data/elo-torneigs.json (llista única, que s'editava al CMS) a un fitxer per torneig, respectant el que ja s'havia marcat."""
    antic = carrega("data/elo-torneigs.json", None)
    if not antic:
        return
    ent = antic.get("tornejos", [])
    for tnr, t in tornejos.items():
        millor = None
        for o in ent:
            n = str(o.get("nom", "")).lower()
            if n and n in t["torneig"].lower() and (not millor or len(n) > len(str(millor["nom"]))):
                millor = o
        if millor and not os.path.exists(os.path.join(D_ELO, "%s.json" % tnr)):
            desa_entrada({"tnr": tnr, "nom": t["torneig"], "data": t["fi"], "fce": millor.get("fce", "auto"), "fide": millor.get("fide", "auto"), "url": t["url"]})
    os.remove("data/elo-torneigs.json")


def sincronitza(auto, tornejos):
    """Crea el fitxer dels tornejos nous amb el valor automàtic (perquè es puguin revisar i canviar a mà) i hi afegeix la modalitat quan ja se sap.
    Mai no es toca el que el club ja ha marcat."""
    ent = llegeix_entrades()
    for tnr, t in tornejos.items():
        orig = dict(ent[tnr]) if ent.get(tnr) else None
        e = ent.get(tnr)
        if not e:
            a = auto[tnr]
            e = {"tnr": tnr, "nom": t["torneig"], "data": t["fi"], "fce": a["fce"], "fide": a["fide"], "url": t["url"]}
        if not e.get("modalitat"):
            nom = unicodedata.normalize("NFKD", t["torneig"] or "").encode("ascii", "ignore").decode().lower()
            if re.search(r"llampec|blitz|relampago|bullet", nom):
                e["modalitat"] = "Blitz"
            elif re.search(r"rapid|actiu|rapides", nom):
                e["modalitat"] = "Rapid"
            elif t["modalitat"] and not t["mod_dubtosa"]:
                e["modalitat"] = t["modalitat"]
            elif re.search(r"calculin|nocturn|pizza|solidari|festa major|infantil", nom):
                e["modalitat"] = "?"          # «?»: format que pot ser ràpid o estàndard; cal que el club ho confirmi
            else:
                e["modalitat"] = "Standard"   # sense paraula clau: obert/campionat de ritme estàndard (el club ho pot canviar)
        if orig != e:
            desa_entrada(e)


def dubtosos(tornejos):
    ent = llegeix_entrades()
    out = []
    for tnr, t in tornejos.items():
        e = ent.get(tnr, {})
        motius = []
        if "?" in (e.get("fce"), e.get("fide")) or "auto" in (e.get("fce"), e.get("fide")):
            motius.append("Elo")
        if e.get("modalitat") == "?":
            motius.append("modalitat")
        if motius:
            out.append({**t, "motius": motius})
    return sorted(out, key=lambda x: x["fi"])


def main():
    ev = calendari()
    tornejos = tornejos_cr()
    auto = {tnr: classifica(t, ev) for tnr, t in tornejos.items()}
    json.dump(auto, open("data/elo-auto.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    prova = "--cap-incidencia" in sys.argv
    if not prova:
        migra_antic(tornejos)
        sincronitza(auto, tornejos)
        compila()
    avisats = set(carrega("data/brut/elo_avisats.json", []))
    nous = []
    for t in dubtosos(tornejos):
        pend = [m for m in t["motius"] if ("mod:" + t["tnr"] if m == "modalitat" else t["tnr"]) not in avisats]
        if pend:
            nous.append({**t, "motius": pend})
    if not nous:
        print("Cap torneig nou per revisar (Elo).")
        return
    cos = ("Hi ha tornejos nous dels quals no sabem si valen per a l'Elo (FCE i/o FIDE) o a quina modalitat (estàndard, ràpid o blitz) pertanyen. "
           "A la web surten amb un **?** davant la variació d'Elo.\n\n"
           "**Què cal fer:** entra al [backoffice](%s/admin/) → *Validesa per a l'Elo* → filtra per «FCE ?», «FIDE ?» o «Modalitat ?», obre cada torneig i marca "
           "el que correspongui. Pots trobar-ne les bases a l'enllaç de Chess-Results.\n\n" % SITE)
    cos += "\n".join("- %s (%s) — dubte: %s — [Enllaç](%s)" % (t["torneig"], t["fi"], ", ".join(t["motius"]), t["url"]) for t in nous)
    titol = "Revisar tornejos (Elo i modalitat): %s" % (nous[0]["torneig"] if len(nous) == 1 else "%d tornejos" % len(nous))
    if prova or not os.environ.get("GH_TOKEN"):
        print(titol + "\n\n" + cos)
        return                    # prova: no es desa res
    r = subprocess.run(["gh", "issue", "create", "--title", titol, "--body", cos] + (["--repo", REPO] if REPO else []), capture_output=True, text=True)
    print(r.stdout, r.stderr)
    if r.returncode != 0:
        sys.exit(0)           # que un error d'avís no trenqui l'actualització; es tornarà a provar la nit següent
    os.makedirs("data/brut", exist_ok=True)
    json.dump(sorted(avisats | {("mod:" + t["tnr"] if m == "modalitat" else t["tnr"]) for t in nous for m in t["motius"]}), open("data/brut/elo_avisats.json", "w"), indent=1)


if __name__ == "__main__":
    main()
