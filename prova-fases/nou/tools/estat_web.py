#!/usr/bin/env python3
"""Estat de la web i avisos per a la portada del panell (admin/portada.html).

Escriu data/estat-web.json (el que llegeix la portada) i data/estat-execucions.json (la memòria de l'última execució de cada procés).
No fa servir xarxa ni l'API de GitHub: tot surt dels fitxers del repositori, així segueix funcionant quan el repositori sigui privat.
L'acció «5 · Web · Estat de la web» l'executa cada vegada que canvia alguna cosa a data/, cada vegada que acaba un procés i cada dia.
Si s'executa després d'un altre procés (workflow_run), l'entorn porta RUN_NAME, RUN_CONCLUSION, RUN_START, RUN_END i RUN_URL.
Ús: python3 tools/estat_web.py [arrel]"""
import datetime, glob, json, os, re, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from edicions import tornejos, insc

CMS = "/admin/#/collections/"
MESOS = ["gener", "febrer", "març", "abril", "maig", "juny", "juliol", "agost", "setembre", "octubre", "novembre", "desembre"]


def carrega(p, per_defecte):
    try:
        return json.load(open(p, encoding="utf-8"))
    except Exception:
        return per_defecte


def ara_utc():
    return datetime.datetime.now(datetime.timezone.utc)


def parse(t):
    """Data/hora ISO (amb o sense zona) -> datetime UTC, o None."""
    try:
        d = datetime.datetime.fromisoformat(str(t).replace("Z", "+00:00"))
        return d if d.tzinfo else d.replace(tzinfo=datetime.timezone.utc)
    except Exception:
        return None


def enllac_torneig(arxiu, edicions_fitxer=False):
    if edicions_fitxer:
        return CMS + "edicions"      # l'Obert té les edicions en fitxes pròpies
    return CMS + "tornejos/entries/" + os.path.basename(arxiu).replace(".json", "")


def avisos_tornejos(arrel, avui):
    out, futures = [], []
    iso = avui.isoformat()
    for f, d in tornejos(arrel):
        nom, lnk = d.get("name") or os.path.basename(f), enllac_torneig(f, d.get("_edicions_fitxer"))
        tid = d.get("id")
        for e in d.get("editions", []):
            any_ = e.get("year")
            n0 = len(out)
            et = f"{nom} {any_}"
            des, ab = e.get("despres") or {}, e.get("abans") or {}
            val = des.get("validat") or {}
            if des.get("cronica") and not val.get("cronica"):
                out.append({"tipus": "validar", "gravetat": "mitja", "text": f"Crònica per validar: {et}", "enllac": lnk})
            if des.get("premis_text") and not val.get("premis"):
                out.append({"tipus": "validar", "gravetat": "mitja", "text": f"Premis per validar: {et}", "enllac": lnk})
            if e.get("status") == "acabat" and not des.get("cronica") and not any(j.get("cronica") for j in e.get("jornades") or []):
                out.append({"tipus": "pendent", "gravetat": "info", "text": f"Edició acabada sense crònica: {et}", "enllac": lnk})
            if e.get("status") == "proper" and (any(not j.get("d") for j in e.get("jornades") or []) or "confirmar" in (e.get("datesText") or "").lower()):
                if str(any_) <= str(avui.year):          # aquest any: urgent; els anys vinents s'agrupen en un sol avís
                    out.append({"tipus": "dates", "gravetat": "mitja", "text": f"Dates per confirmar: {et}", "enllac": lnk})
                else:
                    futures.append((et, f"{tid}/{any_}"))
            inici_i, fins = insc(e)
            if ab.get("url") and fins and iso <= fins and inici_i <= iso:
                if not ab.get("cartell") and not any(x.get("url") for x in ab.get("docs") or []):
                    out.append({"tipus": "inscripcio", "gravetat": "alta", "text": f"Inscripcions obertes sense cartell ni bases: {et}", "enllac": lnk})
                dies = (datetime.date.fromisoformat(fins) - avui).days
                if dies <= 3:
                    out.append({"tipus": "inscripcio", "gravetat": "info", "text": f"Les inscripcions de {et} tanquen {'avui' if dies <= 0 else 'd\'aquí ' + str(dies) + ' dies'}", "enllac": lnk})
            for j in e.get("jornades") or []:
                nomj = f"{et} · {j.get('d') or 'sense data'}"
                if j.get("cronica") and not j.get("cronica_validada"):
                    out.append({"tipus": "validar", "gravetat": "mitja", "text": f"Crònica de jornada per validar: {nomj}", "enllac": lnk})
                if j.get("d", "") > iso and j.get("estat") != "suspesa" and j.get("inscripcio") and not j.get("cartell"):
                    out.append({"tipus": "inscripcio", "gravetat": "mitja", "text": f"Jornada amb inscripció però sense cartell: {nomj}", "enllac": lnk})
                if j.get("d") and j["d"] < iso and j.get("estat") != "suspesa" and not j.get("puntuacio") and d.get("id") == "minicircuit-penedes" and str(any_) == str(avui.year):
                    out.append({"tipus": "pendent", "gravetat": "alta", "text": f"Jornada jugada sense puntuació del circuit: {nomj}", "enllac": lnk})
            for a in out[n0:]:
                a.setdefault("ed", f"{tid}/{any_}")
    if futures:
        out.append({"tipus": "dates", "gravetat": "info", "text": "", "detall": [x[0] for x in futures], "eds": [x[1] for x in futures], "enllac": CMS + "edicions"})
    return out


def avisos_revisions(arrel):
    out = []
    pend = [x for x in carrega(os.path.join(arrel, "data/revisio-federats.json"), {}).get("elements", []) if not x.get("revisat")]
    if pend:
        out.append({"tipus": "revisar", "gravetat": "mitja", "text": f"Federats / no federats dubtosos per revisar: {len(pend)}", "enllac": CMS + "revisions/entries/revisio-federats"})
    sense = [f for f in glob.glob(os.path.join(arrel, "data/elo/*.json")) if "?" in (carrega(f, {}).get("fce"), carrega(f, {}).get("fide"), carrega(f, {}).get("modalitat"))]
    if sense:
        out.append({"tipus": "revisar", "gravetat": "mitja", "text": f"Tornejos sense classificar per a l'Elo: {len(sense)}", "enllac": CMS + "validesaelo"})
    return out


FONTS = [("Jugadors del club i resultats de Chess-Results", "data/resultats-jugadors.json", 2),
         ("Info64 (FEDA)", "data/info64-jugadors.json", 2),
         ("Vesus (Itàlia)", "data/vesus-jugadors.json", 40),
         ("FFE (França)", "data/ffe-jugadors.json", 10),
         ("Lliga Catalana", "data/lliga-%d.json" % datetime.date.today().year, 4),
         ("Torneigs per començar", "data/previs-jugadors.json", 2)]


def fonts(arrel, ara):
    out = []
    for nom, ruta, dies_max in FONTS:
        d = carrega(os.path.join(arrel, ruta), None)
        t = parse((d or {}).get("actualitzat")) if isinstance(d, dict) else None
        dies = (ara - t).days if t else None
        out.append({"nom": nom, "actualitzat": t.strftime("%Y-%m-%dT%H:%MZ") if t else None, "dies": dies, "antic": bool(dies is not None and dies > dies_max)})
    return out


def execucions(arrel, ara):
    """Actualitza i torna la memòria de l'última execució de cada procés."""
    p = os.path.join(arrel, "data/estat-execucions.json")
    mem = carrega(p, {})
    nom = os.environ.get("RUN_NAME", "")
    if nom:
        ini, fi = parse(os.environ.get("RUN_START")), parse(os.environ.get("RUN_END"))
        ant = mem.get(nom) or {}
        concl = os.environ.get("RUN_CONCLUSION", "")
        mem[nom] = {"conclusio": concl, "fi": fi.strftime("%Y-%m-%dT%H:%MZ") if fi else ara.strftime("%Y-%m-%dT%H:%MZ"),
                    "minuts": round((fi - ini).total_seconds() / 60) if ini and fi else None, "url": os.environ.get("RUN_URL", ""),
                    "fallades_seguides": 0 if concl == "success" else (ant.get("fallades_seguides") or 0) + 1}
    if nom or not os.path.exists(p):
        json.dump(mem, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=1, sort_keys=True)     # el fitxer ha d'existir sempre (l'acció el desa)
    return mem


# ---- Terminis (es poden canviar aquí) ----
DIES_VERMELL_ABANS = 30        # falta un mes o menys per començar i queda alguna cosa de «Abans»: vermell
DIES_GROC_ABANS = 60           # falta entre 1 i 2 mesos i queda alguna cosa: groc
DIES_CR = 7                    # falta una setmana o menys i no hi ha Chess-Results (ni «sense resultats en línia»): vermell
DIES_MOSTRA_CR = 14            # el pas «Chess-Results» surt a la llista quan falten aquests dies o menys
DIES_RESULTATS = 2             # ha acabat fa aquests dies o més i encara no hi ha resultats: vermell
DIES_PENDENT_DESPRES = 14      # ha acabat fa 2 setmanes o més i encara falta alguna cosa de «Després» (crònica, premis...): vermell
DIES_ACABADES = 120            # les edicions acabades fa més d'aquests dies ja no surten al quadre


def _dia(x):
    try:
        return datetime.date.fromisoformat(str(x)[:10])
    except Exception:
        return None


def _sch(sch):
    """(inici, final) d'una programació del calendari (kinds: dia, dates, dies, setmanal)."""
    if not sch or not sch.get("start"):
        return None, None
    ini = _dia(sch["start"])
    k = sch.get("kind")
    if k == "dates" and sch.get("dates"):
        return _dia(sch["dates"][0]) or ini, _dia(sch["dates"][-1])
    if k == "dies":
        return ini, _dia(sch.get("end")) or ini
    if k == "setmanal" and ini:
        return ini, ini + datetime.timedelta(days=7 * (int(sch.get("weeks") or 1) - 1))
    return ini, ini


def rang_edicio(e, events):
    """(inici, final) previstos d'una edició: dies de les dades, jornades o esdeveniment del calendari; (None, None) si no es coneixen."""
    dies = sorted(x for x in ((e.get("abans") or {}).get("dades") or {}).get("dies") or [] if x)
    if dies:
        return _dia(dies[0]), _dia(dies[-1])
    jd = sorted(j["d"] for j in e.get("jornades") or [] if j.get("d"))
    if jd:
        return _dia(jd[0]), _dia(jd[-1])
    prev = _dia((e.get("avancat") or {}).get("ordre_previst"))        # data aproximada escrita al panell
    if prev:
        return prev, prev
    ev = events.get((e.get("avancat") or {}).get("ev"))
    if ev and ev.get("sch"):
        return _sch(ev["sch"])
    ult = None                                                        # últim dia que surt al text de dates («25 i 26 de juny»)
    for m in re.finditer(r"(\d{1,2})\s+(?:de\s+|d['’]\s*)?(" + "|".join(MESOS) + ")", (e.get("datesText") or "").lower()):
        try:
            ult = datetime.date(int(e.get("year")), MESOS.index(m.group(2)) + 1, int(m.group(1)))
        except Exception:
            pass
    return (ult, ult) if ult else (None, None)


def resultats_existents(arrel):
    out = set()
    for n in carrega(os.path.join(arrel, "data/resultats/index.json"), []):
        r = carrega(os.path.join(arrel, "data/resultats", n + ".json"), {})
        if r.get("torneig"):
            out.add((r["torneig"], str(r.get("any"))))
    return out


def tasques(arrel, avui):
    """Quadre de comandament: per a cada edició amb coses pendents, la fase (abans, durant, després), què falta i com d'urgent és."""
    events = {}
    for n in ("calendari-propi", "calendari-oficial", "calendari-altres"):
        for ev in carrega(os.path.join(arrel, f"data/{n}.json"), {}).get("events", []):
            events[ev.get("id")] = ev
    res = resultats_existents(arrel)
    out = []
    for f, d in tornejos(arrel):
        tid = d.get("id")
        for e in d.get("editions", []):
            if e.get("jornades"):
                continue          # circuits: tenen els seus propis avisos
            ab, du, de = e.get("abans") or {}, e.get("durant") or {}, e.get("despres") or {}
            dd = ab.get("dades")
            ini, fi = rang_edicio(e, events)
            fi = fi or ini
            if ini and avui > fi:
                fase = "despres"
            elif ini and avui >= ini:
                fase = "durant"
            elif ini:
                fase = "abans"
            else:
                fase = {"acabat": "despres", "enCurs": "durant"}.get(e.get("status"), "abans")
            cr_ok = bool(du.get("cr")) or bool(du.get("sense_resultats"))
            falta, fet, gravetat, quan = [], 0, "info", ""
            if fase == "abans":
                if dd is None:
                    continue
                dies_fins = (ini - avui).days if ini else None
                passos = [
                    ("Dates dels dies de joc", bool(dd.get("dies"))),
                    ("Hora i ritme", bool(dd.get("hora") and dd.get("temps_min"))),
                    ("Sistema i rondes", bool(dd.get("sistema") and dd.get("rondes"))),
                    ("Lloc", bool(dd.get("lloc"))),
                    ("Preus", dd.get("preu_general") not in (None, "")),
                    ("Termini d'inscripció", bool(insc(e)[1])),
                    ("Direcció i àrbitre", bool(dd.get("direccio") and dd.get("arbitre"))),
                    ("PDF de les bases", any(x.get("url") for x in ab.get("docs") or [])),
                    ("Cartell", bool(ab.get("cartell"))),
                ]
                mostra_cr = dies_fins is not None and dies_fins <= DIES_MOSTRA_CR
                if mostra_cr:
                    passos.append(("Chess-Results (o marcar «sense resultats en línia»)", cr_ok))
                falta = [n for n, ok in passos if not ok]
                fet, total = sum(1 for _, ok in passos if ok), len(passos)
                if not falta:
                    continue
                if dies_fins is None:
                    quan = "Sense data"
                else:
                    quan = "Comença avui" if dies_fins == 0 else f"Comença d'aquí {dies_fins} dies"
                    sense_cr = mostra_cr and not cr_ok
                    if dies_fins <= DIES_CR and sense_cr:
                        gravetat = "alta"
                    elif dies_fins <= DIES_VERMELL_ABANS and any(n != passos[-1][0] or not mostra_cr for n in falta):
                        gravetat = "alta"
                    elif dies_fins <= DIES_GROC_ABANS:
                        gravetat = "mitja"
            elif fase == "durant":
                passos = [("Chess-Results (o marcar «sense resultats en línia»)", cr_ok)]
                falta = [n for n, ok in passos if not ok]
                fet, total = len(passos) - len(falta), len(passos)
                if not falta:
                    continue
                gravetat, quan = "mitja", "En joc ara"
            else:
                dies_des = (avui - fi).days if fi else None
                if dies_des is None or dies_des > DIES_ACABADES:
                    continue          # sense data no sabem si és recent: continua l'avís antic «acabada sense crònica»
                tinc_res = any(r[0] == tid or r[0].startswith(str(tid)) or str(tid).startswith(r[0]) for r in res if r[1] == str(e.get("year")))
                tinc_res = tinc_res or bool(du.get("sense_resultats") or de.get("premis") or de.get("premis_text") or de.get("classif_text") or de.get("classif_enganxa") or de.get("classif_csv") or de.get("after") or (de.get("validat") or {}).get("premis"))
                val = de.get("validat") or {}
                passos = [("Resultats i classificació", tinc_res)]
                if de.get("premis") or de.get("premis_text"):
                    passos.append(("Validar els premis", bool(val.get("premis"))))
                if de.get("cronica"):
                    passos.append(("Validar la crònica", bool(val.get("cronica"))))
                else:
                    passos.append(("Crònica", False))
                falta = [n for n, ok in passos if not ok]
                fet, total = len(passos) - len(falta), len(passos)
                if not falta:
                    continue
                quan = "Ha acabat" + (f" fa {dies_des} dies" if dies_des is not None else "")
                if dies_des is not None and dies_des >= DIES_RESULTATS and not tinc_res:
                    gravetat = "alta"
                elif dies_des is not None and dies_des >= DIES_PENDENT_DESPRES:
                    gravetat = "alta"
                elif dies_des is not None and dies_des >= DIES_RESULTATS:
                    gravetat = "mitja"
            nom = d.get("name") or os.path.basename(f)
            clau = f"{tid}/{e.get('year')}"
            out.append({"nom": f"{nom} {e.get('year')}", "fase": fase, "gravetat": gravetat, "quan": quan, "fet": fet, "total": total,
                        "falta": falta, "ed": clau, "inici": ini.isoformat() if ini else "",
                        "enllac": (CMS + f"edicions/entries/{tid}-{e.get('year')}") if d.get("_edicions_fitxer") else enllac_torneig(f)})
    ordre = {"alta": 0, "mitja": 1, "info": 2}
    out.sort(key=lambda t: (ordre[t["gravetat"]], t["inici"] or "9999", t["nom"]))
    return out


def main(arrel="."):
    ara = ara_utc()
    avui = ara.date()
    mem = execucions(arrel, ara)
    TASQUES = tasques(arrel, avui)
    cobertes = {t["ed"] for t in TASQUES}
    av = []
    for a in avisos_tornejos(arrel, avui):
        if "eds" in a:                       # avís agrupat: només les edicions que no surten ja al quadre de tornejos
            resta = [(t, k) for t, k in zip(a["detall"], a["eds"]) if k not in cobertes]
            if not resta:
                continue
            a = {**a, "detall": [t for t, _ in resta], "text": f"Edicions de properes temporades amb dates per confirmar: {len(resta)}"}
            a.pop("eds")
        elif a.get("ed") in cobertes and a["tipus"] != "inscripcio":
            continue
        av.append(a)
    av += avisos_revisions(arrel)
    for n, e in sorted(mem.items()):
        if e.get("conclusio") not in ("success", "", None, "skipped"):
            av.append({"tipus": "execucio", "gravetat": "alta", "text": f"Ha fallat «{n}» ({e['fallades_seguides']} cops seguits)", "enllac": e.get("url") or ""})
    fs = fonts(arrel, ara)
    for f in fs:
        if f["antic"]:
            av.append({"tipus": "execucio", "gravetat": "mitja", "text": f"Dades antigues: «{f['nom']}» fa {f['dies']} dies que no s'actualitza", "enllac": ""})
    m = carrega(os.path.join(arrel, "data/minuts.json"), {})
    consum = None
    if m.get("limit"):
        consum = {"gastats": m.get("gastats"), "limit": m["limit"], "previsio": m.get("previsio_final_de_mes"), "mes": m.get("mes"), "actualitzat": m.get("actualitzat")}
        if (m.get("previsio_final_de_mes") or 0) > m["limit"]:
            av.append({"tipus": "consum", "gravetat": "alta", "text": f"Els minuts d'Actions d'aquest mes passaran del límit (previsió {m['previsio_final_de_mes']} de {m['limit']})", "enllac": ""})
    ordre = {"alta": 0, "mitja": 1, "info": 2}
    av.sort(key=lambda a: (ordre[a["gravetat"]], a["text"]))
    sortida = {"generat": ara.strftime("%Y-%m-%dT%H:%MZ"), "avisos": av, "tasques": TASQUES, "fonts": fs,
               "execucions": [{"nom": n, **e} for n, e in sorted(mem.items(), key=lambda kv: kv[1].get("fi") or "", reverse=True)], "consum": consum}
    p = os.path.join(arrel, "data/estat-web.json")
    ant = carrega(p, {})
    if {k: v for k, v in ant.items() if k != "generat"} != {k: v for k, v in sortida.items() if k != "generat"}:
        json.dump(sortida, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"Estat de la web: {len(av)} avisos ({sum(1 for a in av if a['gravetat'] == 'alta')} d'alts), {len(mem)} processos amb historial")
    for a in av:
        print(f"  [{a['gravetat']}] {a['text']}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else ".")
