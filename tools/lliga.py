#!/usr/bin/env python3
"""Lliga Catalana (escacs.cat) -> data/lliga-<any>.json: classificacio i resultats per rondes dels grups on juga el club.
Ús: python3 tools/lliga.py [any] [carpeta_mostres]   (sense carpeta, consulta escacs.cat)"""
import html, json, re, sys, time, urllib.parse, urllib.request
from datetime import datetime, timezone
from pathlib import Path

ARREL = Path(__file__).resolve().parent.parent
URL = "https://escacs.cat/components/com_fce/gmvw20/conn/serveisLliga.php"
UA = "Mozilla/5.0 ClubEscacsVilafranca"
ID_CLUB = "290"          # Vilafranca, C.E.
NOM = "VILAFRANCA"


def crida(**p):
    u = URL + "?" + urllib.parse.urlencode(p)
    return urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": UA}), timeout=90).read().decode("utf8", "ignore")


def net(s):
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", s))).strip()


def classificacio(h):
    out = []
    for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", h, flags=re.S):
        tds = [net(x) for x in re.findall(r"<td[^>]*>(.*?)</td>", tr, flags=re.S)]
        if len(tds) < 6 or not tds[0].isdigit():
            continue
        cl = int(tds[-2]) if tds[-2].isdigit() else 99      # Class. = lloc a la classificació; el primer número és el de la taula creuada
        out.append({"pos": cl, "equip": tds[1], "punts": tds[-4], "ds": tds[-3]})
    return sorted(out, key=lambda x: x["pos"])


def rondes(js):
    out = []
    for e in js:
        m = re.search(r"Ronda:\s*(\d+)\s*-\s*(\d\d)-(\d\d)-(\d{4})", e.get("entradaCalendari", ""))
        if not m:
            continue
        for loc, res, vis, idp in e.get("partides", []):
            r = re.match(r"\s*([\d½.,]+)\s*-\s*([\d½.,]+)\s*$", res or "")
            out.append({"ronda": int(m[1]), "data": f"{m[4]}-{m[3]}-{m[2]}", "local": loc, "visitant": vis,
                        "res_l": r[1] if r else "", "res_v": r[2] if r else "", "id": str(idp),
                        "nostre": "local" if loc.upper().startswith(NOM) else "visitant"})
    return sorted(out, key=lambda x: x["ronda"])


# Normativa (circulars de la Territorial de Barcelona 07/2026 i CAT 08/2026), grups de 10 equips; els de 8 (Promoció sub-12) no hi surten.
#   up: ascens directe · po_up: playoff d'ascens · down: descens · po_down: playoff de descens
#   cmp_up / cmp_down: nombre de places que es reparteixen comparant els 2ns / 7ens de TOTS els grups (no es pot saber amb un sol grup)
REGLES = {
    "segona divisió": {"up": [1], "po_up": [2], "down": [9, 10], "po_down": [8], "olimpic": False},
    "preferent": {"up": [1], "po_up": [2], "down": [8, 9, 10], "cmp_down": {7: 2}, "olimpic": False},
    "primera provincial": {"up": [1], "down": [9, 10], "olimpic": False},
    "segona provincial": {"up": [1], "cmp_up": {2: 2}, "down": [9, 10], "olimpic": False},
    "tercera provincial": {"up": [1], "cmp_up": {2: 1}, "olimpic": True},
}


def regla(nom, n):
    if n != 10:
        return None
    for k, r in REGLES.items():
        if k in nom.lower():
            return r
    return None


def estat(g, nostre):
    """Zona de la classificació on és el nostre equip i amb quina certesa."""
    cl = g["classificacio"]
    r = regla(g["nom"], len(cl))
    tot = len(cl) - 1                                  # rondes de la fase regular
    jug = sum(1 for x in g["rondes"] if x["res_l"] != "")
    queden = max(0, tot - jug)
    me = next(c for c in cl if c["equip"] == nostre)
    p = me["pos"]
    if not r:
        return {"zona": "", "text": "", "segur": False, "queden": queden}
    maxr = 4 if r["olimpic"] else 1                    # punts màxims per ronda (4 taulers a Tercera, 1 de matx a la resta)
    def num(x):
        x = x.strip().replace(",", ".")
        return float(x.replace("½", "") + (".5" if "½" in x else "") if x != "½" else 0.5) if x else 0.0
    pts = {c["equip"]: num(c["punts"]) for c in cl}
    meu = pts[nostre]
    altres = [v for k, v in pts.items() if k != nostre]
    max_meu = meu + queden * maxr
    # millor posició possible i pitjor possible (els empats compten en contra)
    millor = 1 + sum(1 for v in altres if v > max_meu)
    pitjor = 1 + sum(1 for v in altres if v + queden * maxr >= meu)
    def dins(zona):
        return zona and p in zona
    zones = [("up", "Zona d'ascens directe"), ("po_up", "Zona de playoff d'ascens"), ("po_down", "Zona de playoff de descens"), ("down", "Zona de descens")]
    zona, text = "mante", "Es manté a la categoria"
    for z, t in zones:
        if p in r.get(z, []):
            zona, text = z, t
    if zona == "mante":
        if p in r.get("cmp_up", {}):
            zona, text = "cmp_up", "Pot pujar si és dels millors %dns classificats de tots els grups (depèn dels altres grups)" % p
        elif p in r.get("cmp_down", {}):
            zona, text = "cmp_down", "Pot baixar si és dels pitjors %dens classificats de tots els grups (depèn dels altres grups)" % p
    if zona in ("up", "po_up", "po_down", "down"):
        z = r[zona]
    else:
        z = [p]
    segur = queden == 0 or (millor >= min(z) and pitjor <= max(z)) if zona in ("up", "po_up", "po_down", "down") else queden == 0
    if zona == "mante" and queden:
        # es manté segur si ni de lluny pot arribar a cap zona
        zs = sum([r.get(k, []) for k in ("up", "po_up", "po_down", "down")], [])
        segur = all(q < millor or q > pitjor for q in zs)
    return {"zona": zona, "text": text, "segur": bool(segur), "queden": queden, "millor": millor, "pitjor": pitjor, "pos": p}


def nom_curt(n):
    """'SERRADELL ESTEVE, SILVIA' -> 'Silvia Serradell' (Nom Primer-cognom)."""
    n = (n or "").strip()
    if "," in n:
        cog, nom = [x.strip() for x in n.split(",", 1)]
    else:
        cog, nom = n, ""
    cog1 = cog.split()[0] if cog else ""
    f = lambda t: " ".join(w.capitalize() for w in re.split(r"\s+", t) if w)
    return (f(nom.split()[0] if nom else "") + " " + f(cog1)).strip() or n


def punts_partida(res):
    """'1-0', '½-½', '0 - 1' -> (local, visitant) com a text; None si no es pot llegir."""
    m = re.match(r"\s*([01½]|0[.,]5)\s*[-–]\s*([01½]|0[.,]5)\s*$", res or "")
    return (m[1].replace("0,5", "½").replace("0.5", "½"), m[2].replace("0,5", "½").replace("0.5", "½")) if m else None


def id_jugador(p, costat):
    """Codi FCE del jugador d'un costat (Local/Visitant) d'una partida; el nom exacte del camp es dedueix de la resposta."""
    cands = [(k, v) for k, v in p.items() if k.endswith(costat) and re.match(r"(codi|id|jug|llic)", k, re.I) and not re.match(r"(nom|elo|inc|pun)", k, re.I)
             and str(v).strip().isdigit()]
    cands.sort(key=lambda kv: (not re.search("codi", kv[0], re.I), kv[0]))
    return str(cands[0][1]).strip() if cands else ""


def taulers(dades, nostre_local):
    out = []
    pm = Path(ARREL / "data" / "brut" / "mostra_partida_lliga.json")
    if dades.get("partides") and not pm.exists():
        pm.parent.mkdir(parents=True, exist_ok=True)
        pm.write_text(json.dumps(dades["partides"][:2], ensure_ascii=False, indent=1), "utf8")
    for p in dades.get("partides", []):
        pr = punts_partida(p.get("resultat", ""))
        if p.get("nomLocal") in (None, "") and p.get("nomVisitant") in (None, ""):
            continue
        nostre, rival = ("Local", "Visitant") if nostre_local else ("Visitant", "Local")
        t = {"bo": str(p.get("tauler") or ""), "nostre": nom_curt(p.get("nom" + nostre)), "rival": nom_curt(p.get("nom" + rival)),
             "res": (pr[0] if nostre_local else pr[1]) if pr else (p.get("resultat") or ""),
             "color": ("N" if (p.get("colors") == "nb") == nostre_local else "B") if p.get("colors") in ("nb", "bn") else "",
             "elo": str(p.get("elo" + nostre) or ""), "elo_rival": str(p.get("elo" + rival) or ""), "inc": str(p.get("inc" + nostre) or ""),
             "idn": id_jugador(p, nostre), "idr": id_jugador(p, rival)}
        out.append(t)
    return out


def main():
    any_ = sys.argv[1] if len(sys.argv) > 1 else str(datetime.now().year)
    mostres = Path(sys.argv[2]) if len(sys.argv) > 2 else None

    def llegeix(nom, **p):
        if mostres:
            f = mostres / nom
            return f.read_text("utf8") if f.exists() else ""
        return crida(**p)

    antics = {}
    try:
        for g in json.loads((ARREL / "data" / f"lliga-{any_}.json").read_text("utf8"))["grups"]:
            for r in g["rondes"]:
                if r.get("taulers"):
                    antics[(g["id"], r["id"])] = r["taulers"]
    except Exception:
        pass
    cats = json.loads(llegeix(f"categories_{any_}.json", task="categoriesAny", temporada=any_) or "[]")
    grups = []
    for gid, gnom in cats:
        q = llegeix(f"quadre_{any_}_{gid}.json", task="quadreClassificacio", idGrup=gid, idClub="", temporada=any_)
        try:
            cl = classificacio(json.loads(q)["html"])
        except Exception:
            continue
        if not any(c["equip"].upper().startswith(NOM) for c in cl):
            continue
        cal = llegeix(f"calendari_{gid}.json", task="calendari", idGrup=gid, idClub=ID_CLUB, temporada=any_)
        try:
            rs = rondes(json.loads(cal))
        except Exception:
            rs = []
        # detall per taulers (només es demana el que encara no tenim i ja s'ha jugat)
        for r in rs:
            ant = antics.get((gid, r["id"]))
            if ant and (all("idn" in t for t in ant) or mostres):
                r["taulers"] = ant
            elif r["res_l"] != "" and not mostres:
                try:
                    time.sleep(0.4)
                    tl = taulers(json.loads(crida(task="obtePartidesCalendari", resultats="true", idCalendari=r["id"])), r["nostre"] == "local")
                    if tl:
                        r["taulers"] = tl
                except Exception as e:
                    print("  sense taulers de la ronda", r["ronda"], e)
        grups.append({"id": gid, "nom": gnom, "equip": "", "classificacio": cl, "rondes": rs})
        print(gid, gnom, len(cl), "equips", len(rs), "rondes")
    if not grups:
        print("Cap grup: no toco el fitxer"); return
    # nom dels nostres equips segons el nom amb què apareixen a la classificació (VILAFRANCA = A, VILAFRANCA B, VILAFRANCA SUB12 B...)
    for g in grups:
        nostre = next(c["equip"] for c in g["classificacio"] if c["equip"].upper().startswith(NOM))
        m = re.match(NOM + r"\s*(SUB[\s-]?(\d+))?\s*([A-Z])?$", nostre.upper())
        if m:
            lletra = m[3] or "A"
            g["equip"] = f"CE Vilafranca sub-{m[2]} {lletra}" if m[1] else f"CE Vilafranca {lletra}"
        g["nom_lliga"] = nostre
        g["olimpic"] = bool(regla(g["nom"], len(g["classificacio"])) and regla(g["nom"], len(g["classificacio"]))["olimpic"]) or bool(re.search(r"sub12|promoci", g["nom"], re.I))
        g["zones"] = {k: v for k, v in (regla(g["nom"], len(g["classificacio"])) or {}).items() if k in ("up", "po_up", "po_down", "down", "cmp_up", "cmp_down")}
        g["estat"] = estat(g, nostre)
    sortida = {"temporada": any_, "actualitzat": datetime.now(timezone.utc).isoformat(timespec="seconds"), "grups": grups}
    (ARREL / "data" / f"lliga-{any_}.json").write_text(json.dumps(sortida, ensure_ascii=False, indent=1) + "\n", "utf8")
    print(len(grups), "grups desats")


main()
