#!/usr/bin/env python3
"""FIDE -> tornejos dels jugadors del club (data/fide-tornejos.json) i comparació amb els que ja tenim (data/fide-pendents.json).
FIDE diu ON ha jugat cada jugador (nom, lloc, país, dates de les rondes ja jugades, ritme); les fonts del país en donen les partides.
Per a cada jugador amb codi FIDE, cada mes del tram i cada ritme (t=0 clàssic, 1 ràpid, 2 blitz) es demana la llista de tornejos puntuables
(a_indv_calculation.php, amb reintents perquè des de GitHub FIDE dona timeouts intermitents). No es desa cap dada dels rivals.
Ús: python3 tools/fide_tornejos.py [--mesos=AAAA-MM..AAAA-MM] (per defecte: gener de l'any en curs fins al mes passat)."""
import html as H, json, os, re, sys, time, unicodedata, urllib.request
from datetime import date, datetime, timedelta, timezone

UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"
URL = "https://ratings.fide.com/a_indv_calculation.php?id_number={id}&rating_period={per}-01&t={t}"
RITMES = {0: "Clàssic", 1: "Ràpid", 2: "Blitz"}
FONT_PER_PAIS = {"FRA": "FFE", "ITA": "Vesus", "ESP": "Info64"}
EXCLOSOS = re.compile(r"lliga\s+catalana|liga\s+catalana", re.I)     # la Lliga Catalana s'agafa del web de la FCE amb un altre procediment
SORTIDA, PENDENTS = "data/fide-tornejos.json", "data/fide-pendents.json"
OPC = dict(a[2:].split("=", 1) for a in sys.argv[1:] if a.startswith("--") and "=" in a)


def sa(t):
    return re.sub(r"[^a-z0-9]+", " ", unicodedata.normalize("NFKD", H.unescape(t or "")).encode("ascii", "ignore").decode().lower()).strip()


def mesos():
    avui = datetime.now(timezone.utc).date()
    if "mesos" in OPC:
        a, b = OPC["mesos"].split("..") if ".." in OPC["mesos"] else (OPC["mesos"], OPC["mesos"])
    else:
        a, b = f"{avui.year}-01", (avui.replace(day=1) - timedelta(days=1)).strftime("%Y-%m")
    out, (y, m), (y2, m2) = [], map(int, a.split("-")), map(int, b.split("-"))
    while (y, m) <= (y2, m2):
        out.append(f"{y}-{m:02d}")
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


PW = {}


def pagina():
    """Pàgina d'un navegador real (Playwright) oberta al perfil de FIDE: des de GitHub, urllib dona timeout sempre, però el navegador hi arriba."""
    if "pg" not in PW:
        from playwright.sync_api import sync_playwright
        PW["p"] = sync_playwright().start()
        PW["b"] = PW["p"].chromium.launch()
        PW["pg"] = PW["b"].new_page(user_agent=UA)
        for i in range(5):
            try:
                PW["pg"].goto("https://ratings.fide.com/", wait_until="domcontentloaded", timeout=45000)
                break
            except Exception as e:
                print(f"    FIDE (pàgina inicial): intent {i + 1} fallit ({type(e).__name__})", flush=True)
                time.sleep(5)
    return PW["pg"]


SEGUIDES = [0]


def una_vegada(fide, per, t, intents=4):
    for i in range(intents):
        if SEGUIDES[0] >= 8:         # FIDE no respon des d'aquest servidor: no té sentit esperar una hora, es surt de seguida i es reintenta més tard
            print("::error::FIDE no és accessible des d'aquest servidor ara mateix (8 fallades seguides); s'atura i es reintentarà més tard")
            sys.exit(2)
        try:
            r = pagina().evaluate("u => fetch(u, {headers: {'X-Requested-With': 'XMLHttpRequest'}}).then(r => r.text())", URL.format(id=fide, per=per, t=t))
            SEGUIDES[0] = 0
            return r
        except Exception as e:
            SEGUIDES[0] += 1
            print(f"    FIDE {per} t={t}: intent {i + 1} fallit ({type(e).__name__})", flush=True)
            time.sleep(4 * (i + 1))
    return None


BUIT_REAL = "No records found in individual calculations"


def demana(fide, per, t):
    """HTML de la llista de tornejos d'un període. Tres casos: contingut (tornejos), «No records found…» (període realment buit: es dona per bo)
    o resposta en blanc, que vol dir que FIDE ens està limitant el ritme: s'espera cada cop més i es reintenta; si no es resol, None (mai es dona un buit fals per bo)."""
    for espera in (0, 4, 12, 30, 60):
        time.sleep(espera)
        h = una_vegada(fide, per, t)
        if h is None:
            return None
        if BUIT_REAL in h or len(h.strip()) >= 100:
            return h
    return None


def analitza(h):
    """[{event, nom, lloc, pais, inici, fi}] d'una resposta de FIDE (sense dades de rivals)."""
    out = []
    for m in re.finditer(r'report\.phtml\?event=(\d+)[^>]*>([^<]+)</a>.*?<strong>([^<]*)</strong>\s*((?:<span class="dates_span">[^<]*</span>\s*)+)', h, re.S):
        lloc = H.unescape(m.group(3)).strip()
        pais = lloc.split()[-1] if lloc.split() else ""
        dates = re.findall(r">(\d{4}-\d\d-\d\d)<", m.group(4))
        out.append({"event": m.group(1), "nom": H.unescape(m.group(2)).strip(), "lloc": " ".join(lloc.split()[:-1]), "pais": pais,
                    "inici": min(dates) if dates else None, "fi": max(dates) if dates else None})
    return out


def grup_base(nom):
    """Nom sense el grup/secció (Grup A, Group B, Torneo_C...) per ajuntar els grups d'un mateix torneig."""
    n = sa(nom)
    n = re.sub(r"\b(grup|group|grupo|torneo|open|cat|categoria)\s*[a-z0-9]\b$", "", n).strip()
    return n


def cap_resultat(r, club, fide_t):
    """True si un resultat que ja tenim (qualsevol font) correspon al torneig de FIDE per al mateix jugador."""
    if r.get("jugador") != club:
        return False
    ini, fi = r.get("inici") or r.get("fi"), r.get("fi")
    if not (ini and fi and fide_t["inici"]):
        return False
    try:
        a, b = date.fromisoformat(ini), date.fromisoformat(fi)
        x, y = date.fromisoformat(fide_t["inici"]), date.fromisoformat(fide_t["fi"])
    except ValueError:
        return False
    buit = {"de", "del", "la", "el", "d", "l", "i", "open", "obert", "torneo", "grup", "group", "rondas", "ronda", "2026", "2025"}
    t1 = set(sa(r.get("torneig")).split()) - buit
    t2 = set(sa(fide_t["nom"]).split()) - buit
    puntuacio = len(t1 & t2) / max(1, min(len(t1), len(t2)))
    distancia = max((x - b).days, (a - y).days, 0)          # 0 = les dates se solapen; FIDE només dona les rondes ja jugades, el torneig pot acabar més tard
    return (distancia <= 4 and puntuacio >= 0.34) or (distancia <= 60 and puntuacio >= 0.6)


def carrega(p, per_defecte):
    return json.load(open(p, encoding="utf-8")) if os.path.exists(p) else per_defecte


def compara(llista, ms):
    """Creua la llista de FIDE amb el que ja tenim (Chess-Results, FFE, Info64) i desa els pendents. Ignora el que s'ha jugat abans del tram (p. ex. el desembre anterior)."""
    principi = ms[0] + "-01"
    tenim = []
    for f in ("resultats-jugadors", "ffe-jugadors", "info64-jugadors"):
        tenim += carrega(f"data/{f}.json", {}).get("resultats", [])
    pendents, trobats, exclosos = [], 0, 0
    for e in llista:
        if e["fi"] and e["fi"] < principi:
            continue
        if EXCLOSOS.search(e["nom"]):
            exclosos += 1
            continue
        if any(cap_resultat(r, e["jugador"], e) for r in tenim):
            trobats += 1
            continue
        pendents.append({"jugador": e["jugador"], "nom": e["nom"], "lloc": e["lloc"], "pais": e["pais"], "inici": e["inici"], "fi": e["fi"], "ritmes": e["ritmes"],
                         "grup": grup_base(e["nom"]), "buscar_a": [FONT_PER_PAIS.get(e["pais"], "Chess-Results")] + (["Chess-Results"] if e["pais"] in FONT_PER_PAIS else [])})
    json.dump({"actualitzat": datetime.now(timezone.utc).isoformat(timespec="seconds"), "pendents": pendents},
              open(PENDENTS, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"Tornejos a FIDE: {len(llista)} · ja trobats: {trobats} · Lliga Catalana (a part): {exclosos} · pendents: {len(pendents)}")
    for p in pendents:
        print(f"  PENDENT {p['jugador']} · {p['inici']} · {p['nom'][:55]} · {p['lloc']} {p['pais']} → {' / '.join(p['buscar_a'])}")


def main():
    club = carrega("data/jugadors.json", {"jugadors": []})["jugadors"]
    ms = mesos()
    print("Mesos:", ms[0], "→", ms[-1], "· jugadors amb codi FIDE:", sum(1 for j in club if j.get("fide")), flush=True)
    tornejos, fallades = {}, []

    def llegeix(j, per, t):
        """Demana un període i hi afegeix els tornejos; torna True si ha tornat contingut, False si és buit, None si FIDE no ha respost."""
        h = demana(j["fide"], per, t)
        if h is None:
            return None
        for x in analitza(h):
            e = tornejos.setdefault((j["nom"], x["event"]), {**x, "jugador": j["nom"], "ritmes": []})
            e["inici"], e["fi"] = min(e["inici"], x["inici"]), max(e["fi"], x["fi"])
            if RITMES[t] not in e["ritmes"]:
                e["ritmes"].append(RITMES[t])
        return BUIT_REAL not in h

    for j in club:
        if not j.get("fide"):
            continue
        for per in ms:
            for t in RITMES:
                r = llegeix(j, per, t)
                if r is None:
                    fallades.append((j["nom"], per, t))
                time.sleep(1.5)
        print(f"  {j['nom']}: {sum(1 for k in tornejos if k[0] == j['nom'])} tornejos", flush=True)
    llista = sorted(tornejos.values(), key=lambda e: (e["inici"] or "", e["jugador"]))
    os.makedirs("data", exist_ok=True)
    json.dump({"actualitzat": datetime.now(timezone.utc).isoformat(timespec="seconds"), "mesos": ms, "fallades": [list(f) for f in fallades], "tornejos": llista},
              open(SORTIDA, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    compara(llista, ms)
    if fallades:
        print(f"::warning::FIDE no ha respost en {len(fallades)} consultes (després de 5 intents)")
        sys.exit(1)       # un resultat incomplet no es dona per bo: l'acció surt en vermell


if __name__ == "__main__":
    main()
