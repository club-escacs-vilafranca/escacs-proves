#!/usr/bin/env python3
"""Afegeix al calendari (data/calendari-altres.json) els torneigs on han jugat els nostres jugadors i que encara no hi surten.
Fonts: data/resultats-jugadors.json (Chess-Results, Info64 i FFE): nom, lloc, dates, rondes i enllaç del torneig; no cal cap petició a la xarxa.
Un torneig ja és al calendari si qualsevol esdeveniment dels 4 calendaris coincideix en dates i en nom (mateixa lògica que avis_elo.py) o si el
número de Chess-Results surt a l'enllaç. No s'hi afegeixen el Minicircuit ni els torneigs del club. Els afegits tenen id «auto-<tnr>» i es poden
corregir o esborrar al CMS (si en canvies el nom, mai no es tornen a crear: ja hi són per l'id).
Ús: python3 tools/calendari_auto.py [--prova]"""
import json, re, sys
from datetime import date, timedelta
sys.path.insert(0, "tools")
from avis_elo import carrega, tokens

ALTRES = "data/calendari-altres.json"
CALS = ("calendari-oficial", "calendari-altres", "calendari-propi", "calendari-fide")
FINESTRA = 45      # dies enrere: només es miren torneigs acabats fa poc, en curs o futurs (els antics ja no interessen al calendari)


def torneigs():
    out = {}
    for r in carrega("data/resultats-jugadors.json", {}).get("resultats", []):
        if r["fi"] < (date.today() - timedelta(days=FINESTRA)).isoformat() or re.search(r"mini[\s-]?circuit|vilafranca", r["torneig"], re.I):   # el Minicircuit i els torneigs del club ja hi són
            continue
        t = out.setdefault(r["tnr"], {"tnr": r["tnr"], "nom": r["torneig"], "inici": r.get("inici") or r["fi"], "fi": r["fi"], "lloc": r.get("lloc") or r.get("ciutat") or "",
                                      "rondes": r.get("rondes"), "font": r.get("font"), "url": r.get("url", ""), "mod": r.get("modalitat")})
        t["fi"] = max(t["fi"], r["fi"])
        t["inici"] = min(t["inici"], r.get("inici") or r["fi"])
        t["rondes"] = t["rondes"] or r.get("rondes")
        t["lloc"] = t["lloc"] or r.get("lloc") or r.get("ciutat") or ""
    return out


def ja_al_calendari(t, ev):
    for e in ev:
        s = e.get("sch", {})
        ini, fi = s.get("start"), s.get("end") or s.get("start")
        if t["tnr"] in (e.get("url") or "") or e.get("id") == "auto-" + t["tnr"]:
            return True
        if not ini or ini > t["fi"] or (fi or ini) < t["inici"]:
            continue
        a, b = tokens(t["nom"]), tokens(e["name"])
        if a and b and len(a & b) / len(a | b) >= 0.2:
            return True
    return False


def url_de(t):
    if t["font"] == "chess-results":
        return "https://chess-results.com/tnr%s.aspx?lan=1" % t["tnr"]
    return t["url"]


def detalls(t):
    """Lloc, federació, ritme i rondes de la pàgina del torneig a Chess-Results (només a Actions: la xarxa del sandbox no hi arriba)."""
    if t["font"] != "chess-results":
        return {}
    try:
        import jugadors as J
        pag = J.req("https://s1.chess-results.com/tnr%s.aspx?lan=1" % t["tnr"])
        text = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", pag))
        def camp(n):
            m = re.search(r"\b%s\s+(.*?)\s+%s" % (n, J.ETIQ), text)
            return m.group(1).strip() if m else ""
        fed = re.search(r"\(\s*([A-Z]{3})\s*\)", camp("Federation"))
        lloc = camp("Location")
        return {"lloc": lloc, "fed": fed.group(1) if fed else "", "ritme": camp("Time control"), "rondes": camp("Number of rounds"),
                "fora": J.fora_de_catalunya(lloc, fed.group(1) if fed else "")}
    except Exception as e:
        print("  (no s'han pogut llegir els detalls de %s: %s)" % (t["tnr"], str(e)[:80]))
        return {}


def evento(t, d=None):
    d = d or {}
    font = {"chess-results": "Chess-Results", "info64": "Info64", "ffe": "la federació francesa"}.get(t["font"], "els resultats")
    lloc = d.get("lloc") or t["lloc"] or ""
    rondes = d.get("rondes") or t["rondes"]
    dades = [x for x in (("%s rondes" % rondes) if rondes else "", ("Ritme: " + d["ritme"]) if d.get("ritme") else "", t["mod"] or "") if x]
    scope = ("CAT" if not d.get("fora") else "ESP" if d.get("fed") == "ESP" else "INT") if d else ("CAT" if t["font"] == "chess-results" else "INT")
    return {"id": "auto-" + t["tnr"], "name": re.sub(r"\s+", " ", t["nom"]).strip(), "type": "altres", "scope": scope,
            "place": lloc, "format": " · ".join(dades + ["Afegit automàticament: hi han jugat jugadors del club (dades de %s)" % font]),
            "sch": {"kind": "dies" if t["fi"] != t["inici"] else "dia", "start": t["inici"], "end": t["fi"] if t["fi"] != t["inici"] else "", "weeks": None},
            "source": "auto", "status": "ok", "url": url_de(t)}


def main():
    ev = []
    for f in CALS:
        ev += carrega("data/%s.json" % f, {}).get("events", [])
    altres = carrega(ALTRES, {"events": []})
    nous = [evento(t, None if "--prova" in sys.argv else detalls(t)) for t in sorted(torneigs().values(), key=lambda t: t["inici"]) if not ja_al_calendari(t, ev)]
    for e in nous:
        print("  + %s · %s · %s–%s · %s" % (e["id"], e["name"], e["sch"]["start"], e["sch"]["end"] or "", e["place"]))
    print("Torneigs nous al calendari:", len(nous))
    if nous and "--prova" not in sys.argv:
        altres["events"] += nous
        json.dump(altres, open(ALTRES, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        open(ALTRES, "a").write("\n")


if __name__ == "__main__":
    main()
