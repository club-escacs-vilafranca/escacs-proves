#!/usr/bin/env python3
"""Elo mensual dels jugadors del club (FCE i FIDE) i dels seus rivals.

Què fa:
  - El dia 1 de cada mes (si la FIDE i la FCE ja han publicat la llista nova) torna a llegir l'historial d'Elo de tots els jugadors del club.
  - Els rivals NO es tornen a llegir cada mes: només quan surt una partida d'un mes del qual encara no tenim el seu Elo.
  - Desa data/brut/hist_fce.json i data/brut/hist_fide.json ({id: {"mes": mes de la consulta, "h": {YYYYMM: ...}}}) i data/brut/elo_mensual.json (el que ja està fet aquest mes).
La llista pública de la FIDE (data/brut/fide_esp.json.gz, la mateixa que fa servir la llista d'inscripcions) porta l'Elo del mes de tots els jugadors d'Espanya:
si es pot baixar, d'allà s'actualitza el club i tots els rivals espanyols que ja tenim d'una sola vegada; només es consulta jugador per jugador el que no hi surt (estrangers, inactius).
Aquest mòdul també el fa servir tools/jugadors.py (amb la mateixa memòria cau), de manera que només es demana a la xarxa el que falta.

Ús: python3 tools/elo_mensual.py [--mes AAAAMM]
"""
import datetime, gzip, html, json, os, re, sys, time
sys.path.insert(0, os.path.dirname(__file__))
from xarxa import req

D_HF, D_HI, D_MARCA = "data/brut/hist_fce.json", "data/brut/hist_fide.json", "data/brut/elo_mensual.json"
D_JUG, D_RES = "data/jugadors.json", "data/resultats-jugadors.json"
D_LLISTA = "data/brut/fide_esp.json.gz"


def carrega(p, per_defecte):
    try:
        return json.load(open(p, encoding="utf-8"))
    except Exception:
        return per_defecte


def mes_actual(avui=None):
    return (avui or datetime.datetime.now(datetime.timezone.utc)).strftime("%Y%m")


def mes_consulta_fide(avui=None):
    """Mes amb què es marca una consulta a la FIDE. El dia 1 la llista nova pot no estar publicada encara: es marca amb el mes anterior i es torna a demanar."""
    avui = avui or datetime.datetime.now(datetime.timezone.utc)
    if avui.day >= 2:
        return mes_actual(avui)
    return (avui.replace(day=1) - datetime.timedelta(days=1)).strftime("%Y%m")


def mes_partida(r, g):
    """Mes (AAAAMM) d'una partida: el de la seva data, o el del torneig."""
    return (g.get("data") or r.get("inici") or r["fi"])[:7].replace("-", "")


def hist_fce(idj):
    """Elo mensual (estàndard, ràpid) d'un jugador: {YYYYMM: (std, ràpid)} de cercaelo.php."""
    txt = req(f"https://escacs.cat/components/com_fce/gmvw20/conn/cercaelo.php?idJugador={idj}&type=1", intents=2, espera=2, temps=20)
    txt = html.unescape(re.sub(r"<[^>]+>", " ", txt))
    if not os.path.exists("data/brut/cercaelo_mostra.txt"):
        os.makedirs("data/brut", exist_ok=True)
        open("data/brut/cercaelo_mostra.txt", "w", encoding="utf-8").write(f"idJugador={idj}\n{txt[:3000]}")
    out = {}
    parts = re.split(r"\b(20\d{2}(?:0[1-9]|1[0-2]))\b", txt)
    for i in range(1, len(parts) - 1, 2):
        nums = [int(x) for x in re.findall(r"\b\d{3,4}\b", parts[i + 1])[:2]]
        if nums:
            out[parts[i]] = (nums[0], nums[1] if len(nums) > 1 else None)
    return out


def hist_fide(fide):
    """Elo FIDE mensual d'un jugador (ratings.fide.com): {YYYYMM: {"standard": x, "rapid": y, "blitz": z}}. Si no es pot llegir, {}."""
    txt = req(f"https://ratings.fide.com/a_chart_data.phtml?event={fide}&period=0", data={}, headers={"X-Requested-With": "XMLHttpRequest"}, intents=2, espera=2, temps=20).strip().lstrip("\ufeff").strip()
    if not txt:
        raise RuntimeError("resposta buida de la FIDE (limit de consultes?)")
    if not os.path.exists("data/brut/fide_mostra.txt"):
        os.makedirs("data/brut", exist_ok=True)
        open("data/brut/fide_mostra.txt", "w", encoding="utf-8").write(f"event={fide}\n{txt[:3000]}")
    MES = {m: i + 1 for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"])}
    try:
        dades = json.loads(txt)
    except Exception:
        return {}
    if isinstance(dades, dict):
        dades = next((v for v in dades.values() if isinstance(v, list)), [])
    out = {}
    for it in dades if isinstance(dades, list) else []:
        if not isinstance(it, dict):
            continue
        ym = None
        per = str(it.get("period") or it.get("date") or "")
        mm = re.match(r"(\d{4})-(\d\d)", per)
        if mm:
            ym = mm.group(1) + mm.group(2)
        else:
            mm = re.match(r"(\d{4})-([A-Za-z]{3})", str(it.get("date_2") or ""))
            if mm and mm.group(2).lower() in MES:
                ym = f"{mm.group(1)}{MES[mm.group(2).lower()]:02d}"
        if not ym:
            continue

        def val(*ks):
            for k in ks:
                for kk in it:
                    if kk.lower() == k and str(it[kk]).strip().isdigit() and int(it[kk]) > 0:
                        return int(it[kk])
        out[ym] = {"standard": val("rating"), "rapid": val("rapid_rtng"), "blitz": val("blitz_rtng")}
    return out

def cal_demanar(entrada, ym_necessari):
    """Cal tornar a llegir l'historial si no el tenim o si es va llegir abans del mes que necessitem (aleshores no pot contenir el seu Elo)."""
    return not entrada or entrada["mes"] < ym_necessari


def amb_cache(cache, clau, fn, ym_necessari, estat, fora_de_temps, mes_consulta=None):
    """Historial d'Elo de `clau` de la memòria cau; només el demana a la xarxa si cal_demanar. `estat` guarda les fallades de la FIDE i el que ja s'ha demanat en aquesta execució.
    Torna None si no se'n té cap dada. `fora_de_temps()` diu si s'ha esgotat el temps de feina."""
    e = cache.get(str(clau))
    fide_ = fn is hist_fide
    if not cal_demanar(e, ym_necessari) or (id(cache), str(clau)) in estat.setdefault("fets", set()) or fora_de_temps():
        return e["h"] if e else None                          # el passat no canvia: no es torna a demanar
    if fide_ and estat.get("fallades", 0) >= 4:               # la FIDE ens limita: es deixa per a la propera execucio
        return e["h"] if e else None
    time.sleep(3.0 if fide_ else 1.2)
    try:
        h = fn(clau)
    except Exception:
        if fide_:
            estat["fallades"] = estat.get("fallades", 0) + 1
        raise
    if fide_:
        estat["fallades"] = 0
    estat["fets"].add((id(cache), str(clau)))
    if h or fide_:                                            # FIDE: una llista sense Elo vol dir jugador sense Elo, i es desa igualment
        cache[str(clau)] = {"mes": mes_consulta or ym_necessari, "h": h}
    return h


def _publicat(club, clau_club, fn, mes):
    """Ha publicat ja la font la llista del mes? Es comprova amb un jugador que tingui Elo (fins a 5 intents).
    Torna (publicat, mostra): la mostra és (codi, Elo estàndard del mes) del jugador comprovat."""
    for j in [x for x in club if x.get(clau_club)][:5]:
        try:
            time.sleep(1.5)
            h = fn(j[clau_club])
        except Exception as e:
            print("  no s'ha pogut comprovar", j["nom"], e)
            continue
        if h:
            if mes not in h:
                return False, None
            v = h[mes]
            return True, (j[clau_club], (v.get("standard") if isinstance(v, dict) else v[0]) or None)
    return False, None


def llista_fide_del_mes(mes, mostra=None, baixa=None):
    """La llista en bloc de la FIDE d'aquest mes (data/brut/fide_esp.json.gz), o None si no es pot tenir.
    Si la còpia desada ja és d'aquest mes i coincideix amb la mostra del gràfic de la FIDE, s'usa tal qual; si no, es baixa.
    La comprovació amb la mostra evita fer servir una llista del mes anterior baixada abans que la FIDE publiqués la nova."""
    def llegeix():
        try:
            return json.load(gzip.open(D_LLISTA, "rt", encoding="utf-8"))
        except Exception:
            return None

    def bona(d):
        if not d or d.get("descarregat", "")[:7].replace("-", "") != mes:
            return False
        if mostra:
            x = next((y for y in d["jugadors"] if y["f"] == str(mostra[0])), None)
            return bool(x) and (x["e"] or None) == mostra[1]
        return True
    d = llegeix()
    if bona(d):
        return d
    try:
        if baixa:
            baixa()
        else:
            import inscripcio_llista
            inscripcio_llista.baixa_fide()
    except BaseException as e:           # SystemExit inclòs: si la FIDE bloqueja la màquina, es continua jugador per jugador
        print("  no s'ha pogut baixar la llista en bloc de la FIDE:", e)
        return None
    d = llegeix()
    if bona(d):
        return d
    print("  la llista en bloc de la FIDE no coincideix amb la del gràfic (potser encara és la del mes anterior); no s'usa")
    return None


def aplica_llista_fide(c_fide, llista, mes):
    """Afegeix el mes a l'historial de cada jugador de la memòria cau que surt a la llista en bloc. Torna quants n'ha actualitzat."""
    per_id = {x["f"]: x for x in llista["jugadors"]}
    n = 0
    for f, e in c_fide.items():
        x = per_id.get(str(f))
        if not x or not isinstance(e.get("h"), dict):
            continue
        e["h"][mes] = {"standard": x["e"] or None, "rapid": x["er"] or None, "blitz": x["eb"] or None}
        e["mes"] = mes
        n += 1
    return n


def main():
    mes = sys.argv[sys.argv.index("--mes") + 1] if "--mes" in sys.argv else mes_actual()
    T0 = time.time()
    fora = lambda: time.time() - T0 > 40 * 60
    club = carrega(D_JUG, {"jugadors": []}).get("jugadors", [])
    marca = carrega(D_MARCA, {})
    c_fce, c_fide = carrega(D_HF, {}), carrega(D_HI, {})
    estat = {}
    for nom, clau_club, fn, cache, ruta in (("fce", "id", hist_fce, c_fce, D_HF), ("fide", "fide", hist_fide, c_fide, D_HI)):
        if marca.get(nom) == mes:
            print(f"{nom.upper()}: ja fet per al mes {mes}")
            continue
        publicat, mostra = _publicat(club, clau_club, fn, mes)
        if not publicat:
            print(f"{nom.upper()}: la llista de {mes} encara no és publicada; es tornarà a provar")
            continue
        if nom == "fide":
            llista = llista_fide_del_mes(mes, mostra)
            if llista:
                print(f"FIDE: llista en bloc de {mes}: {aplica_llista_fide(cache, llista, mes)} jugadors de la memòria cau actualitzats sense consultar-los un per un")
            else:
                print("FIDE: sense llista en bloc; es consulta jugador per jugador")
        n = 0
        for j in club:
            if j.get(clau_club):
                try:
                    amb_cache(cache, j[clau_club], fn, mes, estat, fora, mes_consulta=mes)
                    n += 1
                except Exception as e:
                    print("  historial no disponible per a", j["nom"], e)
        completat = all(not cal_demanar(cache.get(str(j[clau_club])), mes) for j in club if j.get(clau_club))
        json.dump(cache, open(ruta, "w", encoding="utf-8"), ensure_ascii=False)
        if completat:
            marca[nom] = mes
        print(f"{nom.upper()}: {n} jugadors del club revisats; {'completat' if completat else 'queden jugadors per a la propera execució'}")
    # rivals: només els que tenen una partida d'un mes del qual no tenim el seu Elo
    pendents = {}
    for r in carrega(D_RES, {"resultats": []}).get("resultats", []):
        for g in r.get("partides", []):
            if g.get("fid"):
                ym = mes_partida(r, g)
                pendents[str(g["fid"])] = max(pendents.get(str(g["fid"]), ""), ym)
    cal = {f: ym for f, ym in pendents.items() if cal_demanar(c_fide.get(f), ym)}
    print(f"Rivals sense Elo del mes de la partida: {len(cal)} de {len(pendents)}")
    for f, ym in sorted(cal.items()):
        try:
            amb_cache(c_fide, f, hist_fide, ym, estat, fora, mes_consulta=mes_consulta_fide())
        except Exception as e:
            print("  rival no disponible", f, e)
    json.dump(c_fide, open(D_HI, "w", encoding="utf-8"), ensure_ascii=False)
    json.dump(marca, open(D_MARCA, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"[{int(time.time() - T0) // 60} min] fet")


if __name__ == "__main__":
    main()
